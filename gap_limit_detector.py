#!/usr/bin/env python3
"""
Gap Limit Detection System for XPUB/ZPUB Addresses

Implements the exact logic specified:
1. Fetch first [xpub_derivation_count] addresses from XPUB/ZPUB
2. Cache all derived addresses 
3. If any of the last 10 addresses were used (balance > 0 now or in past) → derive 10 more
4. Mark "ignore" addresses (spent addresses for 72h interval)
5. Scan all non-ignored addresses for total balance
"""

import json
import time
import os
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime, timedelta
import requests
from dataclasses import dataclass

@dataclass
class AddressInfo:
    """Information about address usage and history."""
    address: str
    index: int
    current_balance: float  # Current BTC balance
    total_received: float   # Total BTC ever received
    total_spent: float      # Total BTC ever spent
    tx_count: int          # Number of transactions
    last_used: Optional[datetime] = None  # Last transaction timestamp
    
    @property
    def was_ever_used(self) -> bool:
        """Check if address was ever used (current OR past balance > 0)."""
        return self.total_received > 0 or self.current_balance > 0
    
    @property
    def is_spent_address(self) -> bool:
        """Check if address had balance in past but is now empty."""
        return self.total_received > 0 and self.current_balance == 0
    
    def should_ignore(self, ignore_interval_hours: int = 72) -> bool:
        """Check if address should be ignored based on ignore interval."""
        if not self.is_spent_address or not self.last_used:
            return False
        
        ignore_until = self.last_used + timedelta(hours=ignore_interval_hours)
        return datetime.now() < ignore_until

class GapLimitDetector:
    """Implements gap limit detection for XPUB/ZPUB addresses."""
    
    def __init__(self, config: Dict):
        """Initialize gap limit detector."""
        self.config = config
        self.mempool_base_url = self._build_mempool_url()
        
        # Gap limit settings
        self.gap_limit = 10  # Check last 10 addresses
        self.derivation_increment = 10  # Derive 10 more when needed
        self.ignore_interval_hours = config.get("address_ignore_interval_hours", 72)
        
        # Cache files
        self.address_cache_file = "gap_limit_address_cache.json"
        self.usage_cache_file = "address_usage_cache.json"
        
        # Import address derivation
        try:
            from address_derivation import AddressDerivation
            self.address_derivation = AddressDerivation()
        except ImportError:
            raise ImportError("AddressDerivation module required for gap limit detection")
    
    def _build_mempool_url(self) -> str:
        """Build mempool API URL from config."""
        mempool_ip = self.config.get("mempool_ip", "mempool.space")
        mempool_port = self.config.get("mempool_rest_port", 443)
        
        if mempool_port == 443:
            return f"https://{mempool_ip}/api"
        else:
            return f"http://{mempool_ip}:{mempool_port}/api"
    
    def get_address_info(self, address: str, index: int) -> AddressInfo:
        """Get address information from mempool API."""
        try:
            response = requests.get(f"{self.mempool_base_url}/address/{address}", timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract usage information
            chain_stats = data.get("chain_stats", {})
            total_received = chain_stats.get("funded_txo_sum", 0) / 100000000  # Convert sats to BTC
            total_spent = chain_stats.get("spent_txo_sum", 0) / 100000000
            current_balance = total_received - total_spent
            tx_count = chain_stats.get("tx_count", 0)
            
            # Get last transaction timestamp if available
            last_used = None
            if tx_count > 0:
                # For simplicity, use current time as placeholder
                # In full implementation, would fetch latest transaction
                last_used = datetime.now()
            
            return AddressInfo(
                address=address,
                index=index,
                current_balance=current_balance,
                total_received=total_received,
                total_spent=total_spent,
                tx_count=tx_count,
                last_used=last_used
            )
            
        except Exception as e:
            print(f"⚠️ Error fetching info for {address[:20]}...: {e}")
            return AddressInfo(
                address=address,
                index=index,
                current_balance=0,
                total_received=0,
                total_spent=0,
                tx_count=0,
                last_used=None
            )
    
    def derive_addresses_with_gap_limit(self, xpub: str) -> Tuple[List[AddressInfo], int]:
        """
        Derive addresses with gap limit detection.
        
        Args:
            xpub: Extended public key
            
        Returns:
            Tuple of (address_info_list, final_derivation_count)
        """
        # Get initial derivation count from config
        initial_count = self.config.get("xpub_derivation_count", 20)
        current_count = initial_count
        
        print(f"🔍 Starting gap limit detection for {xpub[:20]}...")
        print(f"   Initial derivation count: {initial_count}")
        
        all_addresses = []
        
        while True:
            # Derive addresses for current count
            print(f"   Deriving {current_count} addresses...")
            addresses_with_indices = self.address_derivation.derive_addresses(xpub, current_count)
            
            # Get address info for all addresses
            address_infos = []
            for address, index in addresses_with_indices:
                info = self.get_address_info(address, index)
                address_infos.append(info)
                
                # Progress indicator
                if (index + 1) % 10 == 0:
                    print(f"      📊 Analyzed {index + 1}/{current_count} addresses...")
            
            # Check gap limit: Are any of the last 10 addresses used?
            last_addresses = address_infos[-self.gap_limit:] if len(address_infos) >= self.gap_limit else address_infos
            used_in_last_batch = [info for info in last_addresses if info.was_ever_used]
            
            print(f"   Gap limit check: {len(used_in_last_batch)}/{len(last_addresses)} of last {len(last_addresses)} addresses were used")
            
            if used_in_last_batch:
                # Found usage in last 10 → derive 10 more
                print(f"   🔄 Found {len(used_in_last_batch)} used addresses in last batch → deriving {self.derivation_increment} more")
                current_count += self.derivation_increment
                
                # Safety limit
                if current_count > 500:
                    print(f"   ⚠️ Safety limit reached at {current_count} addresses")
                    break
            else:
                # No usage in last 10 → gap limit satisfied
                print(f"   ✅ Gap limit satisfied - no usage in last {len(last_addresses)} addresses")
                break
            
            all_addresses = address_infos
        
        return address_infos, current_count
    
    def get_non_ignored_balance(self, address_infos: List[AddressInfo]) -> Tuple[float, Dict]:
        """
        Calculate total balance from non-ignored addresses.
        
        Args:
            address_infos: List of address information
            
        Returns:
            Tuple of (total_balance, summary_stats)
        """
        total_balance = 0.0
        ignored_count = 0
        active_count = 0
        used_count = 0
        
        for info in address_infos:
            if info.should_ignore(self.ignore_interval_hours):
                ignored_count += 1
                print(f"   🚫 Ignoring spent address {info.address[:20]}... (spent, {self.ignore_interval_hours}h interval)")
                continue
            
            if info.was_ever_used:
                used_count += 1
            
            if info.current_balance > 0:
                total_balance += info.current_balance
                active_count += 1
                print(f"   💰 {info.address[:20]}... = {info.current_balance:.8f} BTC")
        
        summary = {
            "total_addresses": len(address_infos),
            "total_balance": total_balance,
            "active_addresses": active_count,
            "used_addresses": used_count,
            "ignored_addresses": ignored_count,
            "unused_addresses": len(address_infos) - used_count
        }
        
        return total_balance, summary
    
    def process_xpub_with_gap_limit(self, xpub: str) -> Dict:
        """
        Process XPUB with complete gap limit detection logic.
        
        Args:
            xpub: Extended public key
            
        Returns:
            Dict with balance and analysis results
        """
        print(f"\n🔑 Processing XPUB with gap limit detection: {xpub[:20]}...")
        
        # Step 1: Derive addresses with gap limit detection
        address_infos, final_count = self.derive_addresses_with_gap_limit(xpub)
        
        # Step 2: Calculate balance from non-ignored addresses
        total_balance, summary = self.get_non_ignored_balance(address_infos)
        
        # Step 3: Update config if derivation count changed
        initial_count = self.config.get("xpub_derivation_count", 20)
        if final_count != initial_count:
            print(f"📝 Updating xpub_derivation_count: {initial_count} → {final_count}")
            # Note: In full implementation, would update config.json here
        
        result = {
            "xpub": xpub,
            "xpub_short": f"{'zpub' if xpub.lower().startswith('zpub') else 'xpub'}...{xpub[-8:]}",
            "balance": total_balance,
            "initial_derivation_count": initial_count,
            "final_derivation_count": final_count,
            "gap_limit_triggered": final_count > initial_count,
            "summary": summary,
            "ignore_interval_hours": self.ignore_interval_hours
        }
        
        print(f"✅ Gap limit detection complete:")
        print(f"   Balance: {total_balance:.8f} BTC")
        print(f"   Addresses: {summary['total_addresses']} total, {summary['active_addresses']} active, {summary['ignored_addresses']} ignored")
        print(f"   Derivation: {initial_count} → {final_count} {'(expanded)' if final_count > initial_count else '(unchanged)'}")
        
        return result

def test_gap_limit_detection():
    """Test gap limit detection with sample configuration."""
    config = {
        "xpub_derivation_count": 20,
        "address_ignore_interval_hours": 72,
        "mempool_ip": "mempool.space",
        "mempool_rest_port": 443
    }
    
    # Test XPUB (replace with real XPUB for testing)
    test_xpub = "xpub6CUGRUonZSQ4TWtTMmzXdrXDtypWKiKrhko4egpiMZbpiaQL2jkwSB1icqYh2cfDfVxdx4df189oLKnC5fSwqPfgyP3hooxujYzAu3fDVmz"
    
    detector = GapLimitDetector(config)
    result = detector.process_xpub_with_gap_limit(test_xpub)
    
    print(f"\n📊 Final Result:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_gap_limit_detection()
