#!/usr/bin/env python3
"""
Adaptive XPUB Derivation System
Intelligently adjusts the derivation count based on actual address usage patterns.
"""

import json
import time
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import requests
from dataclasses import dataclass

@dataclass
class AddressUsageInfo:
    """Information about address usage."""
    address: str
    index: int
    total_received: float  # Total BTC ever received
    current_balance: float  # Current BTC balance
    tx_count: int  # Number of transactions
    first_seen: Optional[str] = None  # First transaction date
    last_seen: Optional[str] = None   # Last transaction date
    
    @property
    def is_used(self) -> bool:
        """Check if address has ever been used."""
        return self.total_received > 0 or self.tx_count > 0
    
    @property
    def is_active(self) -> bool:
        """Check if address currently has balance."""
        return self.current_balance > 0

class AdaptiveXpubManager:
    """Manages adaptive XPUB derivation with usage-based optimization."""
    
    def __init__(self, config: Dict = None):
        """Initialize adaptive XPUB manager."""
        self.config = config or {}
        self.mempool_base_url = self._build_mempool_url()
        
        # Adaptive derivation settings
        self.min_derivation_count = 10  # Always start with at least 10
        self.derivation_increment = 10  # Increase by 10 when needed
        self.max_derivation_count = 200  # Safety limit
        self.unused_buffer = 5  # Number of unused addresses to keep at end
        
        # Cache file for usage data
        self.usage_cache_file = "address_usage_analytics.json"
        self.last_analysis_file = "last_derivation_analysis.json"
        
        # Load existing data
        self.usage_cache = self._load_usage_cache()
        self.last_analysis = self._load_last_analysis()
    
    def _build_mempool_url(self) -> str:
        """Build mempool API base URL from config."""
        mempool_ip = self.config.get("mempool_ip", "127.0.0.1")
        mempool_port = self.config.get("mempool_rest_port", 443)
        
        # Build API URL
        return f"https://{mempool_ip}:{mempool_port}/api"
    
    def _load_usage_cache(self) -> Dict:
        """Load usage analytics cache."""
        try:
            if os.path.exists(self.usage_cache_file):
                with open(self.usage_cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load usage cache: {e}")
        return {}
    
    def _save_usage_cache(self):
        """Save usage analytics cache."""
        try:
            with open(self.usage_cache_file, 'w') as f:
                json.dump(self.usage_cache, f, indent=2)
        except Exception as e:
            print(f"❌ Could not save usage cache: {e}")
    
    def _load_last_analysis(self) -> Dict:
        """Load last analysis timestamp."""
        try:
            if os.path.exists(self.last_analysis_file):
                with open(self.last_analysis_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load last analysis: {e}")
        return {}
    
    def _save_last_analysis(self, analysis_data: Dict):
        """Save last analysis data."""
        try:
            with open(self.last_analysis_file, 'w') as f:
                json.dump(analysis_data, f, indent=2)
        except Exception as e:
            print(f"❌ Could not save last analysis: {e}")
    
    def get_address_usage_info(self, address: str) -> AddressUsageInfo:
        """
        Get usage information for a single address from mempool API.
        
        Args:
            address: Bitcoin address to analyze
            
        Returns:
            AddressUsageInfo object with usage data
        """
        try:
            # Get address stats from mempool API
            response = requests.get(f"{self.mempool_base_url}/address/{address}", timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract usage information
            total_received = data.get("chain_stats", {}).get("funded_txo_sum", 0) / 100000000  # Convert sats to BTC
            current_balance = (data.get("chain_stats", {}).get("funded_txo_sum", 0) - 
                             data.get("chain_stats", {}).get("spent_txo_sum", 0)) / 100000000
            tx_count = data.get("chain_stats", {}).get("tx_count", 0)
            
            return AddressUsageInfo(
                address=address,
                index=-1,  # Will be set by caller
                total_received=total_received,
                current_balance=current_balance,
                tx_count=tx_count
            )
            
        except Exception as e:
            print(f"⚠️ Could not fetch usage data for {address[:20]}...: {e}")
            return AddressUsageInfo(
                address=address,
                index=-1,
                total_received=0,
                current_balance=0,
                tx_count=0
            )
    
    def analyze_xpub_usage(self, xpub: str, current_derivation_count: int) -> Dict:
        """
        Analyze XPUB usage patterns and determine optimal derivation count.
        
        Args:
            xpub: Extended public key to analyze
            current_derivation_count: Current derivation count
            
        Returns:
            Dictionary with analysis results and recommendations
        """
        print(f"🔍 Analyzing XPUB usage patterns...")
        print(f"   XPUB: {xpub[:30]}...")
        print(f"   Current derivation count: {current_derivation_count}")
        
        # Import here to avoid circular imports
        from address_derivation import AddressDerivation
        derivation = AddressDerivation()
        
        try:
            # Derive addresses
            derived_addresses = derivation.derive_addresses(xpub, current_derivation_count)
            addresses_with_indices = [(addr, idx) for addr, idx in derived_addresses]
            
            print(f"   📍 Analyzing {len(addresses_with_indices)} addresses...")
            
            # Analyze each address
            usage_stats = []
            used_addresses = 0
            active_addresses = 0
            highest_used_index = -1
            
            for i, (address, index) in enumerate(addresses_with_indices):
                # Check cache first
                cache_key = f"{xpub}:{address}"
                if cache_key in self.usage_cache:
                    cached_data = self.usage_cache[cache_key]
                    usage_info = AddressUsageInfo(
                        address=address,
                        index=index,
                        total_received=cached_data.get("total_received", 0),
                        current_balance=cached_data.get("current_balance", 0),
                        tx_count=cached_data.get("tx_count", 0)
                    )
                else:
                    # Fetch fresh data
                    usage_info = self.get_address_usage_info(address)
                    usage_info.index = index
                    
                    # Cache the result
                    self.usage_cache[cache_key] = {
                        "total_received": usage_info.total_received,
                        "current_balance": usage_info.current_balance,
                        "tx_count": usage_info.tx_count,
                        "last_checked": time.time()
                    }
                
                usage_stats.append(usage_info)
                
                if usage_info.is_used:
                    used_addresses += 1
                    highest_used_index = max(highest_used_index, index)
                
                if usage_info.is_active:
                    active_addresses += 1
                
                # Progress indicator
                if (i + 1) % 10 == 0:
                    print(f"      📊 Analyzed {i + 1}/{len(addresses_with_indices)} addresses...")
            
            # Save updated cache
            self._save_usage_cache()
            
            # Calculate statistics
            unused_addresses = len(addresses_with_indices) - used_addresses
            unused_at_end = 0
            
            # Count unused addresses at the end
            for usage_info in reversed(usage_stats):
                if not usage_info.is_used:
                    unused_at_end += 1
                else:
                    break
            
            # Determine if we need more addresses
            last_5_addresses = usage_stats[-5:] if len(usage_stats) >= 5 else usage_stats
            last_5_used = sum(1 for addr in last_5_addresses if addr.is_used)
            
            # Calculate recommended derivation count
            recommended_count = current_derivation_count
            
            if last_5_used > 0:
                # If any of the last 5 addresses are used, increase derivation count
                recommended_count = current_derivation_count + self.derivation_increment
                recommendation_reason = f"Found {last_5_used} used addresses in the last 5 positions"
            elif unused_at_end < self.unused_buffer:
                # If we don't have enough unused buffer, increase
                recommended_count = current_derivation_count + self.derivation_increment
                recommendation_reason = f"Only {unused_at_end} unused addresses at end (need {self.unused_buffer} buffer)"
            else:
                recommendation_reason = "Current derivation count appears sufficient"
            
            # Apply limits
            recommended_count = max(self.min_derivation_count, min(recommended_count, self.max_derivation_count))
            
            # Build analysis result
            analysis_result = {
                "xpub_prefix": xpub[:30] + "...",
                "timestamp": time.time(),
                "current_derivation_count": current_derivation_count,
                "recommended_derivation_count": recommended_count,
                "should_increase": recommended_count > current_derivation_count,
                "recommendation_reason": recommendation_reason,
                "statistics": {
                    "total_addresses": len(addresses_with_indices),
                    "used_addresses": used_addresses,
                    "unused_addresses": unused_addresses,
                    "active_addresses": active_addresses,
                    "highest_used_index": highest_used_index,
                    "unused_at_end": unused_at_end,
                    "last_5_used": last_5_used,
                    "usage_percentage": (used_addresses / len(addresses_with_indices)) * 100
                },
                "address_usage": [
                    {
                        "index": info.index,
                        "address": info.address,
                        "is_used": info.is_used,
                        "is_active": info.is_active,
                        "total_received": info.total_received,
                        "current_balance": info.current_balance,
                        "tx_count": info.tx_count
                    }
                    for info in usage_stats
                ]
            }
            
            # Save analysis result
            self._save_last_analysis(analysis_result)
            
            return analysis_result
            
        except Exception as e:
            print(f"❌ Error analyzing XPUB usage: {e}")
            return {
                "error": str(e),
                "timestamp": time.time(),
                "current_derivation_count": current_derivation_count,
                "recommended_derivation_count": current_derivation_count
            }
    
    def should_run_daily_analysis(self) -> bool:
        """Check if daily analysis should be run."""
        if not self.last_analysis:
            return True
        
        last_run = self.last_analysis.get("timestamp", 0)
        now = time.time()
        
        # Run if more than 24 hours have passed
        return (now - last_run) > (24 * 60 * 60)
    
    def generate_usage_report(self, analysis_result: Dict) -> str:
        """Generate human-readable usage report."""
        if "error" in analysis_result:
            return f"❌ Analysis failed: {analysis_result['error']}"
        
        stats = analysis_result["statistics"]
        
        report = f"""
📊 XPUB Address Usage Analysis Report
{'=' * 50}

🔑 XPUB: {analysis_result['xpub_prefix']}
📅 Analysis Date: {datetime.fromtimestamp(analysis_result['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}

📈 Current Statistics:
   • Total Addresses Derived: {stats['total_addresses']}
   • Used Addresses: {stats['used_addresses']} ({stats['usage_percentage']:.1f}%)
   • Unused Addresses: {stats['unused_addresses']}
   • Active Addresses (with balance): {stats['active_addresses']}
   • Highest Used Index: {stats['highest_used_index']}
   • Unused Buffer at End: {stats['unused_at_end']}

🎯 Derivation Count Analysis:
   • Current: {analysis_result['current_derivation_count']}
   • Recommended: {analysis_result['recommended_derivation_count']}
   • Should Increase: {'🔴 YES' if analysis_result['should_increase'] else '🟢 NO'}
   • Reason: {analysis_result['recommendation_reason']}

📋 Last 5 Addresses Status:
   • Used in Last 5: {stats['last_5_used']}/5
   • This indicates: {'🔴 HIGH USAGE - Need more addresses' if stats['last_5_used'] > 0 else '🟢 LOW USAGE - Sufficient addresses'}

💡 Recommendations:
"""
        
        if analysis_result['should_increase']:
            report += f"   🔄 Increase xpub_derivation_count to {analysis_result['recommended_derivation_count']}\n"
            report += f"   📈 This will provide more unused addresses for future transactions\n"
        else:
            report += f"   ✅ Current derivation count is sufficient\n"
            report += f"   📊 {stats['unused_at_end']} unused addresses provide adequate buffer\n"
        
        return report
    
    def get_optimization_suggestion(self) -> Dict:
        """Get optimization suggestion based on last analysis."""
        if not self.last_analysis or "error" in self.last_analysis:
            return {
                "should_optimize": False,
                "message": "No valid analysis data available. Run analysis first."
            }
        
        analysis = self.last_analysis
        
        return {
            "should_optimize": analysis.get("should_increase", False),
            "current_count": analysis.get("current_derivation_count", 0),
            "recommended_count": analysis.get("recommended_derivation_count", 0),
            "reason": analysis.get("recommendation_reason", ""),
            "last_analysis": datetime.fromtimestamp(analysis["timestamp"]).strftime('%Y-%m-%d %H:%M:%S'),
            "statistics": analysis.get("statistics", {})
        }

def main():
    """Main function for testing the adaptive XPUB manager."""
    print("🧪 Testing Adaptive XPUB Manager")
    
    # Load config
    try:
        with open("config.json", 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Could not load config: {e}")
        return
    
    manager = AdaptiveXpubManager(config)
    
    # Test with a sample XPUB (replace with actual XPUB)
    test_xpub = "xpub6CatWdiZiodmUeTDp8LT5or8nmbKNcuyvz7WyksVFkKB4RHwCD3XyuvPEbvqAeVjZWdvGFv3GXuG5w9VeYAp2QAuVuKa8nLTD7Aa3yf1E52"
    current_count = config.get("xpub_derivation_count", 50)
    
    # Run analysis
    result = manager.analyze_xpub_usage(test_xpub, current_count)
    
    # Generate report
    report = manager.generate_usage_report(result)
    print(report)
    
    # Get optimization suggestion
    suggestion = manager.get_optimization_suggestion()
    print(f"\n🎯 Optimization Suggestion: {suggestion}")

if __name__ == "__main__":
    main()
