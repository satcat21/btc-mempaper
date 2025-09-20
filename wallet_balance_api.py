"""
Wallet Balance API Module

Handles fetching Bitcoin wallet balances from addresses and XPUBs with 
deduplication logic to avoid double-counting addresses already included in XPUBs.
Uses local address derivation from XPUB/ZPUB keys for better control.

"""

import requests
import urllib3
import hashlib
import json
import time
import os
import threading
from typing import Dict, List, Optional, Union, Tuple
from datetime import datetime, timedelta

# Optional import for secure config - graceful fallback if not available
try:
    from secure_config_manager import SecureConfigManager
    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    SECURE_CONFIG_AVAILABLE = False

# Optional import for privacy utilities - graceful fallback if not available
try:
    from privacy_utils import BitcoinPrivacyMasker, print_privacy_safe
    PRIVACY_UTILS_AVAILABLE = True
except ImportError:
    PRIVACY_UTILS_AVAILABLE = False
    # Fallback to regular print if privacy utils not available
    def print_privacy_safe(message, **kwargs):
        print(message)

import threading
from typing import Dict, List, Set, Optional, Union, Tuple
from address_derivation import AddressDerivation
import os
import json
import hashlib
import time

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Optional import for async cache - graceful fallback if not available
try:
    from config_observer import AsyncAddressCacheManager
    ASYNC_CACHE_AVAILABLE = True
except ImportError:
    ASYNC_CACHE_AVAILABLE = False

# Optional import for secure cache - graceful fallback if not available
try:
    from secure_cache_manager import SecureCacheManager
    SECURE_CACHE_AVAILABLE = True
except ImportError:
    SECURE_CACHE_AVAILABLE = False

# Optional import for unified secure cache - graceful fallback if not available
try:
    from unified_secure_cache import get_unified_cache
    UNIFIED_CACHE_AVAILABLE = True
except ImportError:
    UNIFIED_CACHE_AVAILABLE = False


class WalletBalanceAPI:
    def get_batch_address_usage_info(self, addresses: List[str], batch_size: int = None) -> List[Dict]:
        """
        Fetch usage info for a batch of addresses.
        Args:
            addresses: List of Bitcoin addresses
            batch_size: Optional batch size (ignored in this implementation)
        Returns:
            List of usage info dicts for each address
        """
        results = []
        for address in addresses:
            info = self.get_address_usage_info(address)
            results.append(info)
        return results
    """API client for Bitcoin wallet balance monitoring with deduplication and address caching."""
    
    def __init__(self, config: Dict = None, use_async_cache: bool = True):
        """
        Initialize Wallet Balance API client.
        
        Args:
            config: Application configuration dictionary
            use_async_cache: Whether to use async cache manager (if available)
        """
        self.config = config or {}
        self._wallet_cache = None

        # Initialize secure configuration manager
        if SECURE_CONFIG_AVAILABLE:
            self.secure_config_manager = SecureConfigManager()
            # print(f"🔐 Secure configuration manager initialized")
        else:
            self.secure_config_manager = None
            print(f"⚠️ Secure configuration unavailable - using fallback mode")
        
        # Get mempool configuration
        mempool_ip = self.config.get("mempool_ip", "127.0.0.1")
        mempool_port = self.config.get("mempool_rest_port", 443)
        
        # Build API URL
        self.base_url = f"https://{mempool_ip}:{mempool_port}/api"
        
        # print(f"🔒 Using private mempool instance: {self.base_url}")
        
        # Initialize address derivation with caching
        self.address_derivation = AddressDerivation()
        
        # Add lock to prevent concurrent balance fetching
        self._fetch_lock = threading.Lock()
        
        # Add lock to prevent concurrent gap limit detection 
        self._gap_limit_lock = threading.Lock()
        
        # Track active gap limit detection to prevent redundant work
        self._active_gap_limit_detection = set()
        
        # Balance caching with timestamps
        self._balance_cache = {}
        self._balance_cache_timeout = 60  # Cache balance for 60 seconds by default
        
        # Initialize gap limit detection
        self.enable_gap_limit = True
        self.gap_limit = 20
        self.derivation_increment = 20
        self.address_ignore_interval_hours = 72
        
        # Enhanced gap limit detection parameters
        self.enable_bootstrap_search = True
        self.bootstrap_increment = 20
        self.bootstrap_max_addresses = 200
        
        # Debug gap limit settings
        print(f"🔍 Gap limit detection enabled (last {self.gap_limit} addresses, +{self.derivation_increment} increment)")
        if self.enable_bootstrap_search:
            print(f"🚀 Bootstrap search enabled (max {self.bootstrap_max_addresses} addresses, +{self.bootstrap_increment} increment)")
        else:
            print(f"⏭️ Bootstrap search disabled")
        
        
        # Set up caching strategy
        self.use_async_cache = use_async_cache and ASYNC_CACHE_AVAILABLE
        self.use_unified_cache = UNIFIED_CACHE_AVAILABLE
        
        # Always try to initialize unified cache for wallet balance cache
        if self.use_unified_cache:
            try:
                self.unified_cache = get_unified_cache()
                # print(f"🔐 Unified secure cache initialized for wallet data")
            except Exception as e:
                print(f"⚠️ Failed to initialize unified cache: {e}")
                self.use_unified_cache = False
        
        if self.use_async_cache:
            # Use async cache manager for optimal performance (address derivation)
            self.async_cache_manager = AsyncAddressCacheManager()
            # print(f"🚀 Using async address cache for optimal performance")
        elif not self.use_unified_cache:
            # Fallback to individual secure cache or empty cache for address data
            self.cache_file = "cache/wallet_address_cache.json"
            
            if SECURE_CACHE_AVAILABLE:
                self.secure_cache_manager = SecureCacheManager(self.cache_file)
                self.address_cache = self.secure_cache_manager.load_cache()
                # print(f"🔐 Using secure encrypted address cache")
            else:
                print(f"❌ Secure cache unavailable - using empty cache")
                self.address_cache = {}

    def _convert_to_fiat(self, btc_amount, fiat_currency):
        """
        Convert BTC amount to fiat using current price from BitcoinPriceAPI.
        Args:
            btc_amount (float): Amount in BTC
            fiat_currency (str): Fiat currency code (e.g., 'USD', 'EUR')
        Returns:
            float: Fiat value
        """
        try:
            from btc_price_api import BitcoinPriceAPI
            
            # Create temporary config with the wallet-specific currency
            temp_config = dict(self.config)
            temp_config['btc_price_currency'] = fiat_currency
            
            price_api = BitcoinPriceAPI(temp_config)
            price_data = price_api.fetch_btc_price()
            
            print(f"💱 Price API response: {price_data}")
            
            if price_data and 'error' not in price_data:
                price = price_data.get('price_in_selected_currency', 0)
                if price and price > 0:
                    result = btc_amount * price
                    if btc_amount > 0:
                        print(f"💰 Conversion: {btc_amount:.8f} BTC × {price:.2f} {fiat_currency} = {result:.2f} {fiat_currency}")
                    else:
                        print(f"💰 Current price: {price:.2f} {fiat_currency} per BTC (no wallet configured)")
                    return result
                else:
                    print(f"⚠️ Price data issue: received price={price}, unable to calculate conversion")
                    return 0.0
            else:
                error_msg = price_data.get('error', 'Unknown error') if price_data else 'No price data returned'
                print(f"❌ Price API error: {error_msg}")
                return 0.0
        except Exception as e:
            print(f"❌ Fiat conversion error: {e}")
            import traceback
            traceback.print_exc()
            return 0.0
            
            if not ASYNC_CACHE_AVAILABLE:
                print(f"📦 Async cache not available, using simple cache")
            else:
                print(f"📦 Using simple address cache (async disabled)")
        
        if self.enable_gap_limit:
            print(f"🔍 Gap limit detection enabled (last {self.gap_limit} addresses, +{self.derivation_increment} increment)")
    
    def _load_address_cache(self) -> Dict:
        """Load address derivation cache from file."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                    cache_entries = len(cache)
                    if cache_entries > 0:
                        print(f"📂 Loaded address cache with {cache_entries} entries")
                    return cache
        except Exception as e:
            print(f"⚠️ Failed to load address cache: {e}")
        
        return {}
    
    def _get_optimized_balance_cache_key(self, xpub: str) -> str:
        """Generate cache key for optimized balance monitoring."""
        return f"optimized_balance:{hashlib.sha256(xpub.encode()).hexdigest()[:16]}"
    
    def _load_optimized_balance_cache(self, xpub: str) -> Optional[Dict]:
        """Load optimized balance monitoring cache."""
        cache_key = self._get_optimized_balance_cache_key(xpub)
        
        try:
            if self.use_unified_cache:
                # Load from unified secure cache
                optimized_cache = self.unified_cache.get_cache("optimized_balance_cache")
                return optimized_cache.get(cache_key)
            else:
                # Fallback to individual file
                cache_file = f"cache/optimized_balance_cache.json"
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                        return cache_data.get(cache_key)
        except Exception as e:
            print(f"⚠️ Failed to load optimized balance cache: {e}")
        
        return None
    
    def _save_optimized_balance_cache(self, xpub: str, cache_data: Dict) -> bool:
        """Save optimized balance monitoring cache."""
        cache_key = self._get_optimized_balance_cache_key(xpub)
        
        try:
            if self.use_unified_cache:
                # Save to unified secure cache
                optimized_cache = self.unified_cache.get_cache("optimized_balance_cache")
                optimized_cache[cache_key] = cache_data
                self.unified_cache.set_cache("optimized_balance_cache", optimized_cache)
            else:
                # Fallback to individual file
                cache_file = f"cache/optimized_balance_cache.json"
                
                # Ensure cache directory exists
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                
                # Load existing cache
                existing_cache = {}
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        existing_cache = json.load(f)
                
                # Update cache
                existing_cache[cache_key] = cache_data
                
                # Save updated cache
                with open(cache_file, 'w') as f:
                    json.dump(existing_cache, f, indent=2)
                
            return True
        except Exception as e:
            print(f"⚠️ Failed to save optimized balance cache: {e}")
            return False
    
    def get_optimized_xpub_balance(self, xpub: str, startup_mode: bool = False) -> float:
        """
        Get XPUB balance using optimized monitoring strategy:
        - Full scan cached for configurable days (default: 50 days)
        - During cache validity: only monitor funded addresses + next N addresses (default: 5)
        - Trigger full rescan if any monitored address balance changes
        - Reset cache timer after successful full rescan
        
        Args:
            xpub: Extended public key (xpub/zpub)
            startup_mode: If True, use cached data only
            
        Returns:
            Balance in BTC
        """
        try:
            # Check if optimized monitoring is enabled
            # if not self.config.get('enable_optimized_balance_monitoring', True):
            #     print(f"🔄 [STANDARD] Optimized monitoring disabled - using standard method")
            #     return self.get_xpub_balance(xpub, startup_mode)
            
            # print(f"🎯 [OPTIMIZED] Starting optimized balance calculation for {xpub[:20]}...")
            
            # Get configuration values
            cache_days = 50
            buffer_addresses = 5
            
            # Load optimized cache
            cache_data = self._load_optimized_balance_cache(xpub)
            current_time = time.time()
            cache_valid_seconds = cache_days * 24 * 60 * 60  # Convert days to seconds
            
            # Check if we have a valid full scan cache
            if cache_data and (current_time - cache_data.get('last_full_scan', 0)) < cache_valid_seconds:
                # cache_age_days = (current_time - cache_data['last_full_scan']) / (24 * 60 * 60)
                # print(f"🕐 [OPTIMIZED] Using cached scan from {datetime.fromtimestamp(cache_data['last_full_scan']).strftime('%Y-%m-%d %H:%M:%S')} ({cache_age_days:.1f} days ago)")
                
                # In startup mode, always use cached data to avoid delays
                if startup_mode:
                    total_balance = cache_data.get('total_balance', 0.0)
                    print(f"🚀 [STARTUP] Using cached balance for {xpub[:20]}...: {total_balance:.8f} BTC (optimized cache)")
                    return total_balance
                
                # Get monitoring addresses (funded + next N)
                monitoring_addresses = cache_data.get('monitoring_addresses', [])
                cached_balances = cache_data.get('address_balances', {})
                
                if monitoring_addresses:
                    # print(f"👁️ [OPTIMIZED] Monitoring {len(monitoring_addresses)} critical addresses (cached full scan has {cache_data.get('funded_address_count', 0)} funded addresses)")
                    
                    # Check if any monitored address balance has changed
                    balance_changed = False
                    current_monitored_balances = {}
                    
                    for addr in monitoring_addresses:
                        current_balance = self.get_address_balance(addr)
                        current_monitored_balances[addr] = current_balance
                        cached_balance = cached_balances.get(addr, 0.0)
                        
                        if abs(current_balance - cached_balance) > 0.00000001:  # 1 satoshi precision
                            # print(f"💥 [OPTIMIZED] Balance change detected on {addr}: {cached_balance:.8f} → {current_balance:.8f} BTC")
                            balance_changed = True
                            break
                    
                    if not balance_changed:
                        # All monitored addresses unchanged - return cached total
                        total_balance = cache_data.get('total_balance', 0.0)
                        # print(f"✅ [OPTIMIZED] No changes detected, using cached balance: {total_balance:.8f} BTC")
                        # print(f"🕐 [OPTIMIZED] Cache expires in {((cache_valid_seconds - (current_time - cache_data['last_full_scan'])) / (24 * 60 * 60)):.1f} days")
                        return total_balance
                    else:
                        print(f"🔄 Balance change detected - triggering full rescan")
            
            # If in startup mode and no valid cache, return 0 to avoid blocking startup
            if startup_mode:
                print(f"🚀 [STARTUP] No cached balance available for {xpub[:20]}... - returning 0 to avoid blocking startup")
                return 0.0
                
            # Perform full scan (either first run, cache expired, or balance change detected)
            # print(f"🔍 [OPTIMIZED] Performing full address scan for {xpub[:20]}...")
            # print(f"🔍 [OPTIMIZED] Gap limit enabled: {self.enable_gap_limit}")
            
            # Get all addresses using gap limit detection - force gap limit for comprehensive scanning
            if self.enable_gap_limit:
                # Use get_xpub_addresses() which properly checks cached results before expensive detection
                # print(f"🔍 [OPTIMIZED] Using gap limit detection for comprehensive scan...")
                start_time = time.time()
                addresses = self.get_xpub_addresses(xpub, startup_mode=False)
                scan_time = time.time() - start_time
                # print(f"🔍 [OPTIMIZED] Gap limit scan completed in {scan_time:.1f}s → {len(addresses)} addresses")
            else:
                # Fallback to regular address derivation
                # print(f"🔍 [OPTIMIZED] Using regular address derivation (gap limit disabled)")
                addresses = self.get_xpub_addresses(xpub, startup_mode=False)
            if not addresses:
                print(f"⚠️ No addresses derived for {xpub[:20]}...")
                return 0.0
            
            # Calculate balances for all addresses
            address_balances = {}
            funded_addresses = []
            total_balance = 0.0
            
            print(f"🚀 Scanning {len(addresses)} addresses...")
            
            # Use parallel processing for better performance
            import concurrent.futures
            def fetch_address_balance(address):
                try:
                    balance = self.get_address_balance(address)
                    return address, balance
                except Exception as e:
                    print(f"⚠️ Error fetching balance for {address}: {e}")
                    return address, 0.0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(addresses), 10)) as executor:
                future_to_address = {executor.submit(fetch_address_balance, addr): addr for addr in addresses}
                
                for future in concurrent.futures.as_completed(future_to_address):
                    address, balance = future.result()
                    address_balances[address] = balance
                    try:
                        balance_float = float(balance)
                    except (ValueError, TypeError):
                        print(f"⚠️ Non-numeric balance for address {address}: {balance}")
                        balance_float = 0.0
                    if balance_float > 0:
                        funded_addresses.append(address)
                        total_balance += balance_float
            
            # Sort addresses by derivation index to determine monitoring range
            address_list = list(addresses)
            if self.use_async_cache:
                # For async cache, we need to get addresses with indices
                derivation_count = len(address_list)
                cached_addresses_with_indices = self.async_cache_manager.get_addresses_with_indices(f"{xpub}:{derivation_count}")
                if cached_addresses_with_indices:
                    address_list = [addr for addr, idx in sorted(cached_addresses_with_indices, key=lambda x: x[1])]
            
            # Determine monitoring addresses: funded addresses + next N after highest funded
            monitoring_addresses = []
            if funded_addresses:
                # Find indices of funded addresses
                funded_indices = []
                for funded_addr in funded_addresses:
                    try:
                        idx = address_list.index(funded_addr)
                        funded_indices.append(idx)
                    except ValueError:
                        pass
                
                if funded_indices:
                    max_funded_index = max(funded_indices)
                    
                    # Include all funded addresses
                    monitoring_addresses.extend(funded_addresses)
                    
                    # Add next N addresses after the highest funded address
                    for i in range(max_funded_index + 1, min(max_funded_index + 1 + buffer_addresses, len(address_list))):
                        if address_list[i] not in monitoring_addresses:
                            monitoring_addresses.append(address_list[i])
                    
                    # print(f"📍 [OPTIMIZED] Will monitor {len(funded_addresses)} funded + {len(monitoring_addresses) - len(funded_addresses)} buffer addresses")
            else:
                # No funded addresses - monitor first N addresses
                monitoring_addresses = address_list[:buffer_addresses]
                print(f"📍 [OPTIMIZED] No funded addresses - monitoring first {buffer_addresses} addresses")
            
            # Save optimized cache
            cache_data = {
                'last_full_scan': current_time,
                'total_balance': total_balance,
                'monitoring_addresses': monitoring_addresses,
                'address_balances': address_balances,
                'scan_address_count': len(addresses),
                'funded_address_count': len(funded_addresses),
                'cache_days': cache_days,
                'buffer_addresses': buffer_addresses
            }
            
            self._save_optimized_balance_cache(xpub, cache_data)
            
            # print(f"✅ [OPTIMIZED] Full scan complete: {total_balance:.8f} BTC from {len(funded_addresses)}/{len(addresses)} addresses")
            # print(f"🕐 [OPTIMIZED] Cache valid until {datetime.fromtimestamp(current_time + cache_valid_seconds).strftime('%Y-%m-%d %H:%M:%S')} ({cache_days} days)")
            
            return total_balance
            
        except Exception as e:
            print(f"⚠️ Error in optimized balance calculation: {e}")
            # Fallback to regular balance calculation
            return self.get_xpub_balance(xpub, startup_mode)
    
    def _save_address_cache(self) -> bool:
        """Save address derivation cache to file."""
        if hasattr(self, 'secure_cache_manager') and SECURE_CACHE_AVAILABLE:
            # Use secure cache manager
            return self.secure_cache_manager.save_cache(self.address_cache)
        else:
            print(f"❌ Secure cache manager not available - cannot save cache")
            return False
    
    def _get_cache_key(self, extended_key: str, count: int, start_index: int = 0) -> str:
        """Generate cache key for derivation parameters."""
        key_data = f"{extended_key}:{count}:{start_index}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def _get_cached_addresses(self, extended_key: str, count: int, start_index: int = 0) -> Optional[List[Tuple[str, int]]]:
        """Get derived addresses from cache if available."""
        cache_key = self._get_cache_key(extended_key, count, start_index)
        
        if cache_key in self.address_cache:
            cached_entry = self.address_cache[cache_key]
            # Verify cache entry is valid
            if (cached_entry.get("count") == count and 
                cached_entry.get("start_index") == start_index and
                "addresses" in cached_entry):
                
                # Convert back to tuples
                return [(addr, idx) for addr, idx in cached_entry["addresses"]]
        
        return None
    
    def _cache_addresses(self, extended_key: str, count: int, addresses: List[Tuple[str, int]], 
                        derivation_time: float, start_index: int = 0) -> None:
        """Cache derived addresses for future use."""
        cache_key = self._get_cache_key(extended_key, count, start_index)
        
        self.address_cache[cache_key] = {
            "extended_key_prefix": extended_key[:20] + "...",
            "count": count,
            "start_index": start_index,
            "addresses": addresses,  # List of [address, index] pairs
            "cached_at": time.time(),
            "derivation_time": derivation_time
        }
        
        # Save cache to disk (async would be better, but keeping it simple)
        self._save_address_cache()
    
    def get_cache_stats(self) -> Dict:
        """Get address derivation cache statistics."""
        total_entries = len(self.address_cache)
        total_addresses = sum(len(entry["addresses"]) for entry in self.address_cache.values())
        
        if total_entries > 0:
            total_derivation_time = sum(entry.get("derivation_time", 0) for entry in self.address_cache.values())
            avg_derivation_time = total_derivation_time / total_entries
            
            # Calculate cache file size
            cache_size = 0
            if os.path.exists(self.cache_file):
                cache_size = os.path.getsize(self.cache_file)
        else:
            total_derivation_time = 0
            avg_derivation_time = 0
            cache_size = 0
        
        return {
            "total_entries": total_entries,
            "total_addresses": total_addresses,
            "total_derivation_time": total_derivation_time,
            "avg_derivation_time": avg_derivation_time,
            "cache_file_size": cache_size,
            "cache_file": self.cache_file
        }
    
    def clear_address_cache(self) -> bool:
        """Clear all cached addresses."""
        self.address_cache = {}
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            print(f"🗑️ Address derivation cache cleared")
            return True
        except Exception as e:
            print(f"⚠️ Failed to clear address cache: {e}")
            return False

    def detect_address_conflicts(self, wallet_entries: List[str]) -> Optional[Dict[str, Union[str, List]]]:
        """
        Detect conflicts between manually added addresses and XPUB/ZPUB derived addresses.
        
        Args:
            wallet_entries: List of wallet entries (addresses, xpubs, zpubs)
            
        Returns:
            Dict with conflict details if conflicts exist, None if no conflicts
        """
        try:
            # Separate XPUBs/ZPUBs and regular addresses
            user_xpubs = [entry for entry in wallet_entries if entry.lower().startswith(("xpub", "zpub"))]
            user_addresses = [entry for entry in wallet_entries if not entry.lower().startswith(("xpub", "zpub"))]
            
            if not user_xpubs or not user_addresses:
                return None  # No potential for conflicts
            
            print(f"🔍 Checking for conflicts between {len(user_addresses)} manual addresses and {len(user_xpubs)} extended keys...")
            
            # Map each derived address to its source XPUB/ZPUB
            address_to_xpub = {}
            conflicts = []
            
            for xpub in user_xpubs:
                try:
                    derived_addresses = self.get_xpub_addresses(xpub)
                    xpub_short = f"{'zpub' if xpub.lower().startswith('zpub') else 'xpub'}...{xpub[-8:]}"
                    
                    # Check each user address against derived addresses
                    for user_addr in user_addresses:
                        if user_addr in derived_addresses:
                            conflicts.append({
                                "address": user_addr,
                                "xpub": xpub,
                                "xpub_short": xpub_short,
                                "derivation_index": None  # Will be filled below
                            })
                            address_to_xpub[user_addr] = xpub
                    
                    # For conflicts, find the derivation index
                    if conflicts:
                        derivation_count = 20
                        derived_with_index = self.address_derivation.derive_addresses(xpub, derivation_count)
                        addr_to_index = {addr: idx for addr, idx in derived_with_index}
                        
                        for conflict in conflicts:
                            if conflict["xpub"] == xpub and conflict["address"] in addr_to_index:
                                conflict["derivation_index"] = addr_to_index[conflict["address"]]
                
                except Exception as e:
                    print(f"⚠️ Error checking conflicts for {xpub[:20]}...: {e}")
                    continue
            
            if conflicts:
                return {
                    "has_conflicts": True,
                    "conflicts": conflicts,
                    "total_conflicts": len(conflicts),
                    "error_message": self._format_conflict_error(conflicts)
                }
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error detecting address conflicts: {e}")
            return None
    
    def _format_conflict_error(self, conflicts: List[Dict]) -> str:
        """
        Format a user-friendly error message for address conflicts.
        
        Args:
            conflicts: List of conflict dictionaries
            
        Returns:
            Formatted error message
        """
        if len(conflicts) == 1:
            conflict = conflicts[0]
            index_info = f" (derivation index {conflict['derivation_index']})" if conflict['derivation_index'] is not None else ""
            return (f"Address conflict detected: '{conflict['address']}' is manually added but also "
                   f"derived from {conflict['xpub_short']}{index_info}. "
                   f"Please remove either the manual address or the XPUB/ZPUB to avoid double-counting.")
        else:
            conflict_list = []
            for conflict in conflicts:
                index_info = f" (index {conflict['derivation_index']})" if conflict['derivation_index'] is not None else ""
                conflict_list.append(f"• '{conflict['address']}' from {conflict['xpub_short']}{index_info}")
            
            conflicts_text = "\n".join(conflict_list)
            return (f"Multiple address conflicts detected:\n{conflicts_text}\n\n"
                   f"These {len(conflicts)} addresses are both manually added and derived from XPUB/ZPUB keys. "
                   f"Please remove duplicates to avoid double-counting balances.")

    def get_xpub_addresses(self, xpub: str, startup_mode: bool = False) -> Set[str]:
        """
        Derive addresses from XPUB/ZPUB using local derivation with caching and gap limit detection.
        
        Args:
            xpub: Extended public key (xpub/zpub)
            startup_mode: If True, use cached data only and skip expensive gap limit detection
            
        Returns:
            Set of addresses derived from the XPUB/ZPUB
        """
        try:
            # In startup mode, skip gap limit detection and use cached data only
            if startup_mode:
                print(f"🚀 [STARTUP] Checking cached addresses for {xpub[:20]}... (gap limit detection disabled)")
                
                if self.use_async_cache:
                    # Try multiple cache keys for different possible final counts
                    for test_count in [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]:
                        cache_key = f"{xpub}:gap_limit:{test_count}"
                        cached_addresses = self.async_cache_manager.get_addresses(cache_key)
                        if cached_addresses:
                            print(f"🚀 [STARTUP] Using cached gap limit result ({test_count} addresses)")
                            return set(cached_addresses)
                    
                    # Fallback to regular cached derivation
                    derivation_count = 20
                    cached_addresses = self.async_cache_manager.get_addresses(f"{xpub}:{derivation_count}")
                    if cached_addresses:
                        print(f"🚀 [STARTUP] Using cached addresses ({derivation_count} addresses)")
                        return set(cached_addresses)
                
                print(f"⚠️ [STARTUP] No cached addresses found for {xpub[:20]}... - will use minimal derivation")
                # Return minimal addresses for startup (just derive 5 addresses quickly)
                return self._get_addresses_with_simple_cache(xpub, 5)
            
            # Use gap limit detection if enabled (bypasses cache for dynamic derivation)
            if self.enable_gap_limit:
                print(f"🔍 Gap limit detection enabled - checking for cached results first")
                
                # Check for cached gap limit results first to avoid re-running expensive detection
                if self.use_async_cache:
                    # Try multiple cache keys for different possible final counts
                    for test_count in [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]:
                        cache_key = f"{xpub}:gap_limit:{test_count}"
                        cached_addresses = self.async_cache_manager.get_addresses(cache_key)
                        if cached_addresses:
                            print(f"✅ [CACHE] Found cached gap limit result for {xpub[:20]}... ({test_count} addresses)")
                            print(f"🚀 [CACHE] Skipping gap limit detection - using cached addresses")
                            return set(cached_addresses)
                
                print(f"🔍 [FRESH] No cached gap limit results found - running detection")
                print(f"🚀 [FRESH] Starting gap limit detection for {xpub[:20]}...")
                addresses_with_indices, final_count = self.derive_addresses_with_gap_limit(xpub)
                
                # Cache the result with gap limit suffix to avoid conflicts
                if self.use_async_cache:
                    cache_key = f"{xpub}:gap_limit:{final_count}"
                    address_list = [addr for addr, idx in addresses_with_indices]
                    self.async_cache_manager.cache_addresses(cache_key, address_list)
                
                return {addr for addr, idx in addresses_with_indices}
            
            # Fallback to regular derivation
            derivation_count = 20
            
            # Use async cache if available
            if self.use_async_cache:
                return self._get_addresses_with_async_cache(xpub, derivation_count)
            else:
                return self._get_addresses_with_simple_cache(xpub, derivation_count)
            
        except Exception as e:
            print(f"⚠️ Error deriving addresses for XPUB/ZPUB {xpub[:20]}...: {e}")
            return set()
    
    def _get_addresses_with_async_cache(self, xpub: str, derivation_count: int) -> Set[str]:
        """Get addresses using async cache manager."""
        
        # If gap limit detection is enabled, check for cached gap limit results first
        if self.enable_gap_limit:
            # Try multiple cache keys for different possible final counts
            for test_count in [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]:
                cache_key = f"{xpub}:gap_limit:{test_count}"
                cached_addresses = self.async_cache_manager.get_addresses(cache_key)
                if cached_addresses:
                    print(f"🚀 Async cache HIT for {xpub[:20]}... (gap limit: {test_count} addresses)")
                    return set(cached_addresses)
            
            # No cached gap limit results - run gap limit detection
            print(f"💻 Async cache MISS for {xpub[:20]}... - running gap limit detection...")
            start_time = time.time()
            
            try:
                addresses_with_indices, final_count = self.derive_addresses_with_gap_limit(xpub)
                derivation_time = time.time() - start_time
                
                # Convert to address list for caching
                address_list = [addr for addr, idx in addresses_with_indices]
                
                # Store in async cache with gap limit key
                cache_key = f"{xpub}:gap_limit:{final_count}"
                self.async_cache_manager.cache_addresses(cache_key, address_list)
                print(f"💾 Async cached {len(address_list)} addresses with gap limit (derived in {derivation_time:.3f}s)")
                
                return set(address_list)
                
            except Exception as e:
                print(f"⚠️ Gap limit detection failed for {xpub[:20]}...: {e}")
                print(f"🔄 Falling back to regular derivation ({derivation_count} addresses)")
                # Fall through to regular caching logic below
        
        # Regular async caching (gap limit disabled or fallback)
        cache_key = f"{xpub}:{derivation_count}"
        
        # Check if addresses are already cached
        cached_addresses = self.async_cache_manager.get_addresses(cache_key)
        if cached_addresses:
            print(f"🚀 Async cache HIT for {xpub[:20]}... ({derivation_count} addresses)")
            return set(cached_addresses)
        
        # Cache miss - derive addresses and cache them
        print(f"💻 Async cache MISS for {xpub[:20]}... - deriving {derivation_count} addresses...")
        start_time = time.time()
        
        derived_addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
        derivation_time = time.time() - start_time
        
        # Convert to address list for caching
        address_list = [addr for addr, idx in derived_addresses]
        
        # Store in async cache
        self.async_cache_manager.cache_addresses(cache_key, address_list)
        print(f"💾 Async cached {len(address_list)} addresses (derived in {derivation_time:.3f}s)")
        
        return set(address_list)
    
    def _get_addresses_with_simple_cache(self, xpub: str, derivation_count: int) -> Set[str]:
        """Get addresses using simple cache (fallback)."""
        # Try to get from cache first
        cached_addresses = self._get_cached_addresses(xpub, derivation_count)
        
        if cached_addresses is not None:
            print(f"🚀 Simple cache HIT for {xpub[:20]}... ({derivation_count} addresses)")
            return {addr for addr, idx in cached_addresses}
        
        # Cache miss - derive addresses
        print(f"� Simple cache MISS for {xpub[:20]}... - deriving {derivation_count} addresses...")
        start_time = time.time()
        
        derived_addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
        
        derivation_time = time.time() - start_time
        
        # Cache the results
        self._cache_addresses(xpub, derivation_count, derived_addresses, derivation_time)
        
        address_set = {addr for addr, idx in derived_addresses}
        
        print(f"💾 Simple cached {len(address_set)} addresses (derived in {derivation_time:.3f}s)")
        
        return address_set
    
    def get_address_balance(self, address: str) -> float:
        """
        Get confirmed BTC balance (in BTC) of a single address.
        
        Args:
            address: Bitcoin address
            
        Returns:
            Balance in BTC
        """
        # Debug: Check if address is actually an object (this should NOT happen)
        if isinstance(address, dict):
            print(f"🚨 ERROR: get_address_balance received a dict instead of string: {address}")
            import traceback
            print("🚨 Call stack:")
            traceback.print_stack()
            # Try to extract address from the object
            if 'address' in address:
                print(f"🔧 Attempting to extract address: {address['address']}")
                address = address['address']
            else:
                print(f"❌ Cannot extract address from object: {address}")
                return 0.0
        elif not isinstance(address, str):
            print(f"🚨 ERROR: get_address_balance received non-string type {type(address)}: {address}")
            return 0.0
            
        try:
            url = f"{self.base_url}/address/{address}"
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            
            funded = data['chain_stats']['funded_txo_sum']
            spent = data['chain_stats']['spent_txo_sum']
            return (funded - spent) / 1e8
        except Exception as e:
            print(f"⚠️ Error fetching balance for address {address}: {e}")
            return 0.0
    
    def get_address_usage_info(self, address: str) -> Dict:
        """
        Get detailed usage information for a single address.
        
        Args:
            address: Bitcoin address
            
        Returns:
            Dict with usage information
        """
        try:
            url = f"{self.base_url}/address/{address}"
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            
            chain_stats = data.get('chain_stats', {})
            total_received = chain_stats.get('funded_txo_sum', 0) / 1e8
            total_spent = chain_stats.get('spent_txo_sum', 0) / 1e8
            current_balance = total_received - total_spent
            tx_count = chain_stats.get('tx_count', 0)
            
            return {
                'address': address,
                'current_balance': current_balance,
                'total_received': total_received,
                'total_spent': total_spent,
                'tx_count': tx_count,
                'was_ever_used': total_received > 0 or tx_count > 0,
                'is_spent_address': total_received > 0 and current_balance == 0
            }
        except Exception as e:
            print(f"⚠️ Error fetching usage info for address {address}: {e}")
            return {
                'address': address,
                'current_balance': 0,
                'total_received': 0,
                'total_spent': 0,
                'tx_count': 0,
                'was_ever_used': False,
                'is_spent_address': False
            }
    
    def derive_addresses_with_gap_limit(self, xpub: str) -> Tuple[List[Tuple[str, int]], int]:
        """
        Enhanced gap limit detection with bootstrap mode.
        
        1. Bootstrap Phase: Expand until at least one address with positive balance is found
        2. Standard Phase: Apply normal gap limit logic (expand if last 20 have usage)
        
        Args:
            xpub: Extended public key
            
        Returns:
            Tuple of (addresses_with_indices, final_derivation_count)
        """
        # Check if gap limit detection is already running for this XPUB
        if xpub in self._active_gap_limit_detection:
            print(f"⏳ [BLOCKING] Gap limit detection already running for {xpub[:20]}... - waiting for completion")
            # Wait for the active detection to complete
            while xpub in self._active_gap_limit_detection:
                time.sleep(0.5)
            print(f"✅ [BLOCKING] Gap limit detection completed for {xpub[:20]}... - proceeding with cached result")
            # Return cached result
            for test_count in [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]:
                cache_key = f"{xpub}:gap_limit:{test_count}"
                if self.use_async_cache:
                    cached_addresses = self.async_cache_manager.get_addresses(cache_key)
                    if cached_addresses:
                        addresses_with_indices = [(addr, i) for i, addr in enumerate(cached_addresses)]
                        return addresses_with_indices, test_count
            # Fallback if no cached result found
            derivation_count = 20
            addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
            return addresses, derivation_count
        
        # Acquire lock and mark as active
        with self._gap_limit_lock:
            if xpub in self._active_gap_limit_detection:
                # Double-check after acquiring lock
                print(f"⏳ [BLOCKING] Gap limit detection started by another thread for {xpub[:20]}...")
                return self.derive_addresses_with_gap_limit(xpub)  # Recursive call will wait
            
            # Mark this XPUB as having active gap limit detection
            self._active_gap_limit_detection.add(xpub)
            if PRIVACY_UTILS_AVAILABLE:
                masked_xpub = BitcoinPrivacyMasker.mask_xpub(xpub)
                print(f"🔒 [BLOCKING] Starting exclusive gap limit detection for {masked_xpub}...")
            else:
                print(f"🔒 [BLOCKING] Starting exclusive gap limit detection for {xpub[:20]}...")
        
        try:
            return self._perform_gap_limit_detection(xpub)
        finally:
            # Always remove from active set when done
            with self._gap_limit_lock:
                self._active_gap_limit_detection.discard(xpub)
                print(f"🔓 [BLOCKING] Completed gap limit detection for {xpub[:20]}...")
    
    def _perform_gap_limit_detection(self, xpub: str) -> Tuple[List[Tuple[str, int]], int]:
        """
        Perform the actual gap limit detection (called by derive_addresses_with_gap_limit).
        
        Args:
            xpub: Extended public key
            
        Returns:
            Tuple of (addresses_with_indices, final_derivation_count)
        """
        if not self.enable_gap_limit:
            # Fall back to regular derivation
            derivation_count = 20
            addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
            return addresses, derivation_count
        
        # Get initial derivation count from config
        initial_count = 20
        current_count = initial_count
        
        if PRIVACY_UTILS_AVAILABLE:
            masked_xpub = BitcoinPrivacyMasker.mask_xpub(xpub)
            print(f"🔍 Enhanced gap limit detection for {masked_xpub} (initial: {initial_count})")
        else:
            print(f"🔍 Enhanced gap limit detection for {xpub[:20]}... (initial: {initial_count})")
        
        # Phase 1: Bootstrap - find at least one address with positive balance
        bootstrap_complete = False
        addresses_with_indices = []
        
        # Store all address information across iterations
        all_addresses_info = {}  # address -> (index, usage_info)
        
        if self.enable_bootstrap_search:
            print(f"🚀 Phase 1: Bootstrap search - continue until gap limit satisfied")
            print(f"   📋 Will expand until {self.gap_limit} consecutive unused addresses found")
            
            while not bootstrap_complete:
                # Derive addresses for current count
                addresses_with_indices = self.address_derivation.derive_addresses(xpub, current_count)
                
                # Only check NEW addresses that haven't been processed yet
                new_addresses = []
                for address, index in addresses_with_indices:
                    if address not in all_addresses_info:
                        new_addresses.append((address, index))
                
                if new_addresses:
                    # Extract just the NEW addresses for batch processing
                    new_addresses_only = [addr for addr, idx in new_addresses]
                    
                    # Use batch processing for better performance on NEW addresses only
                    print(f"   📊 Batch checking {len(new_addresses_only)} NEW addresses (indices {new_addresses[0][1]}-{new_addresses[-1][1]}) for usage history...")
                    batch_usage_list = self.get_batch_address_usage_info(new_addresses_only, batch_size=20)
                    
                    # Convert list to dict for easier lookup
                    batch_usage_info = {}
                    for i, address in enumerate(new_addresses_only):
                        if i < len(batch_usage_list):
                            batch_usage_info[address] = batch_usage_list[i]
                    
                    # Store new address information
                    for address, index in new_addresses:
                        usage_info = batch_usage_info.get(address, {
                            'current_balance': 0, 
                            'was_ever_used': False,
                            'total_received': 0
                        })
                        all_addresses_info[address] = (index, usage_info)
                
                # Analyze ALL addresses (existing + new) for summary, but only display NEW ones
                positive_balance_count = 0
                ever_used_count = 0
                total_balance_found = 0
                
                if new_addresses:
                    print(f"   📋 Checking NEW addresses {new_addresses[0][1]} to {new_addresses[-1][1]}:")
                    
                    for address, index in new_addresses:
                        _, usage_info = all_addresses_info[address]
                        
                        balance = usage_info['current_balance']
                        ever_used = usage_info.get('was_ever_used', False) or usage_info.get('total_received', 0) > 0
                        
                        if balance > 0:
                            if PRIVACY_UTILS_AVAILABLE:
                                masked_address = BitcoinPrivacyMasker.mask_address(address)
                                print(f"   💰 Address {index:2d}: {masked_address} = {balance:.8f} BTC (ACTIVE)")
                            else:
                                print(f"   💰 Address {index:2d}: {address[:20]}... = {balance:.8f} BTC (ACTIVE)")
                        elif ever_used:
                            if PRIVACY_UTILS_AVAILABLE:
                                masked_address = BitcoinPrivacyMasker.mask_address(address)
                                print(f"   📝 Address {index:2d}: {masked_address} = 0.00000000 BTC (USED IN PAST)")
                            else:
                                print(f"   📝 Address {index:2d}: {address[:20]}... = 0.00000000 BTC (USED IN PAST)")
                        else:
                            if PRIVACY_UTILS_AVAILABLE:
                                masked_address = BitcoinPrivacyMasker.mask_address(address)
                                print(f"   ⭕ Address {index:2d}: {masked_address} = 0.00000000 BTC (NEVER USED)")
                            else:
                                print(f"   ⭕ Address {index:2d}: {address[:20]}... = 0.00000000 BTC (NEVER USED)")
                
                # Calculate totals from ALL addresses processed so far
                for address, (index, usage_info) in all_addresses_info.items():
                    balance = usage_info['current_balance']
                    ever_used = usage_info.get('was_ever_used', False) or usage_info.get('total_received', 0) > 0
                    
                    if balance > 0:
                        positive_balance_count += 1
                        total_balance_found += balance
                    elif ever_used:
                        ever_used_count += 1
                
                # Check gap limit: Are any of the last [gap_limit] addresses ever used?
                if len(addresses_with_indices) >= self.gap_limit:
                    last_addresses = addresses_with_indices[-self.gap_limit:]
                    used_in_last_batch = 0
                    
                    for address, index in last_addresses:
                        if address in all_addresses_info:
                            _, usage_info = all_addresses_info[address]
                            ever_used = usage_info.get('was_ever_used', False) or usage_info.get('total_received', 0) > 0
                            if ever_used:
                                used_in_last_batch += 1
                    
                    print(f"   📊 Gap analysis: {used_in_last_batch}/{self.gap_limit} of last {self.gap_limit} addresses were ever used")
                    print(f"   📊 Total summary: {positive_balance_count} active, {ever_used_count} used in past, {positive_balance_count + ever_used_count} total used")
                    
                    total_used_addresses = positive_balance_count + ever_used_count
                    
                    if used_in_last_batch == 0:
                        # Gap limit satisfied, but check if we've found ANY used addresses during bootstrap
                        if total_used_addresses > 0:
                            # We found used addresses and now have a gap - bootstrap complete
                            print(f"   ✅ Bootstrap complete - gap limit satisfied ({self.gap_limit} consecutive unused addresses)")
                            print(f"   ✅ Found {total_used_addresses} total used addresses before gap")
                            bootstrap_complete = True
                        else:
                            # No used addresses found yet - continue bootstrap search up to max limit
                            if current_count >= self.bootstrap_max_addresses:
                                print(f"   ⚠️ Bootstrap search complete - reached maximum {self.bootstrap_max_addresses} addresses")
                                print(f"   ⚠️ No used addresses found in entire range - wallet appears unused")
                                bootstrap_complete = True
                            else:
                                print(f"   🔄 No used addresses found yet, continuing bootstrap search → expanding by {self.bootstrap_increment}")
                                current_count += self.bootstrap_increment
                    else:
                        print(f"   🔄 Found {used_in_last_batch} used addresses in last batch → expanding by {self.bootstrap_increment}")
                        current_count += self.bootstrap_increment
                        
                        # Safety limit for bootstrap
                        if current_count > self.bootstrap_max_addresses:
                            print(f"   ⚠️ Bootstrap safety limit reached at {current_count} addresses")
                            print(f"   ⚠️ Proceeding with current addresses found")
                            bootstrap_complete = True
                else:
                    # Not enough addresses for gap limit check yet
                    print(f"   🔄 Need more addresses for gap limit check → expanding by {self.bootstrap_increment}")
                    current_count += self.bootstrap_increment
                    
                    # Safety limit
                    if current_count > self.bootstrap_max_addresses:
                        print(f"   ⚠️ Bootstrap safety limit reached at {current_count} addresses")
                        bootstrap_complete = True
        else:
            print(f"⏭️ Bootstrap search disabled - using standard gap limit logic")
            
            # Standard gap limit detection when bootstrap is disabled
            while True:
                # Derive addresses for current count
                addresses_with_indices = self.address_derivation.derive_addresses(xpub, current_count)
                
                # Only check NEW addresses that haven't been processed yet
                new_addresses = []
                for address, index in addresses_with_indices:
                    if address not in all_addresses_info:
                        new_addresses.append((address, index))
                
                if new_addresses:
                    # Check usage for NEW addresses only
                    print(f"   📊 Checking {len(new_addresses)} NEW addresses (indices {new_addresses[0][1]}-{new_addresses[-1][1]}) for usage...")
                    
                    for address, index in new_addresses:
                        usage_info = self.get_address_usage_info(address)
                        all_addresses_info[address] = (index, usage_info)
                
                # Check gap limit: Are any of the last [gap_limit] addresses used?
                if len(addresses_with_indices) >= self.gap_limit:
                    last_addresses = addresses_with_indices[-self.gap_limit:]
                    
                    # Check usage for last addresses
                    used_in_last_batch = 0
                    for address, index in last_addresses:
                        if address in all_addresses_info:
                            _, usage_info = all_addresses_info[address]
                            if usage_info['was_ever_used']:
                                used_in_last_batch += 1
                    
                    if used_in_last_batch > 0:
                        # Found usage in last batch → derive more
                        print(f"   🔄 Found {used_in_last_batch}/{self.gap_limit} used addresses in last batch → deriving {self.derivation_increment} more")
                        current_count += self.derivation_increment
                        
                        # Safety limit for standard phase
                        if current_count > 500:
                            print(f"   ⚠️ Standard phase safety limit reached at {current_count} addresses")
                            break
                    else:
                        # No usage in last batch → gap limit satisfied
                        print(f"   ✅ Gap limit satisfied - no usage in last {self.gap_limit} addresses")
                        break
                else:
                    # Not enough addresses to check gap limit
                    print(f"   ✅ Gap limit satisfied - only {len(addresses_with_indices)} addresses derived")
                    break

        # Convert stored address info back to the expected format (address, index) tuples
        final_addresses = []
        for address, (index, usage_info) in sorted(all_addresses_info.items(), key=lambda x: x[1][0]):
            final_addresses.append((address, index))
        
        # Report results
        if current_count != initial_count:
            expansion_reason = "bootstrap + gap limit" if self.enable_bootstrap_search else "gap limit"
            print(f"📝 Enhanced gap limit expanded derivation: {initial_count} → {current_count} ({expansion_reason})")
        else:
            print(f"📝 Enhanced gap limit result: {current_count} addresses (no expansion needed)")
        
        return final_addresses, current_count
    
    def _get_secure_wallet_entries(self) -> List[Union[str, Dict]]:
        """
        Securely load wallet addresses and XPUBs from encrypted configuration.
        Supports both old format (strings) and new format (objects with address/comment/type).
        
        Returns:
            List of wallet addresses and XPUBs (strings or objects)
        """
        if not self.secure_config_manager:
            # Fallback to config file if secure config unavailable
            print("⚠️ Secure config unavailable, using fallback from regular config")
            return []
        
        try:
            # Load secure configuration
            secure_config = self.secure_config_manager.load_secure_config()
            if not secure_config:
                print("⚠️ Failed to load secure config, using fallback")
                return []
            
            # Try new format first (objects with comments)
            wallet_entries_with_comments = secure_config.get("wallet_balance_addresses_with_comments", [])
            if wallet_entries_with_comments:
                print(f"🔐 Loaded {len(wallet_entries_with_comments)} wallet entries with comments from secure configuration")
                return wallet_entries_with_comments
            
            # Fallback to old format (simple strings)
            wallet_entries = secure_config.get("wallet_balance_addresses", [])
            
            if wallet_entries:
                print(f"🔐 Loaded {len(wallet_entries)} wallet entries (old format) from secure configuration")
                return wallet_entries
            else:
                # Fallback to regular config if no secure entries found
                fallback_entries = []
                if fallback_entries:
                    print("⚠️ No entries in secure config, using fallback from regular config")
                    print("💡 Consider migrating sensitive data to secure config")
                return fallback_entries
                
        except Exception as e:
            print(f"❌ Error loading secure wallet config: {e}")
            print("⚠️ Using fallback from regular config")
            return []

    def _parse_wallet_entries(self) -> Tuple[List[Dict], List[str], List[str]]:
        """
        Parse wallet entries from secure config, supporting both old and new format.
        
        Returns:
            Tuple of (entries_with_comments, user_addresses, user_xpubs)
        """
        # Try new format first (with comments) from secure config
        wallet_entries_with_comments = []
        
        if self.secure_config_manager:
            try:
                secure_config = self.secure_config_manager.load_secure_config()
                if secure_config:
                    wallet_entries_with_comments = secure_config.get("wallet_balance_addresses_with_comments", [])
            except Exception as e:
                print(f"⚠️ Error loading secure config for comments: {e}")
        
        # Fallback to regular config for comments format
        if not wallet_entries_with_comments:
            wallet_entries_with_comments = []

        if wallet_entries_with_comments:
            # New format with comments
            user_addresses = []
            user_xpubs = []
            
            for entry in wallet_entries_with_comments:
                if isinstance(entry, dict) and "address" in entry:
                    address = entry["address"]
                    if address.lower().startswith(("xpub", "zpub")):
                        user_xpubs.append(address)
                    else:
                        user_addresses.append(address)
                else:
                    # Fallback for malformed entries
                    if isinstance(entry, str):
                        if entry.lower().startswith(("xpub", "zpub")):
                            user_xpubs.append(entry)
                        else:
                            user_addresses.append(entry)
            
            return wallet_entries_with_comments, user_addresses, user_xpubs
        
        # Fallback to old format (simple list) from secure config
        wallet_entries = self._get_secure_wallet_entries()
        
        # Convert to new format for compatibility
        entries_with_comments = []
        user_addresses = []
        user_xpubs = []
        
        for entry in wallet_entries:
            if isinstance(entry, str):
                # Auto-detect type
                entry_type = "xpub" if entry.lower().startswith(("xpub", "zpub")) else "address"
                
                entries_with_comments.append({
                    "address": entry,
                    "comment": f"Imported {entry_type}",
                    "type": entry_type
                })
                
                if entry.lower().startswith(("xpub", "zpub")):
                    user_xpubs.append(entry)
                else:
                    user_addresses.append(entry)
        
        return entries_with_comments, user_addresses, user_xpubs
    
    def get_xpub_balance(self, xpub: str, startup_mode: bool = False) -> float:
        """
        Get confirmed BTC balance (in BTC) for an XPUB/ZPUB wallet by deriving addresses.
        
        Args:
            xpub: Extended public key (xpub/zpub)
            startup_mode: If True, use cached data only and skip expensive gap limit detection
            
        Returns:
            Balance in BTC
        """
        # Debug: Check if xpub is actually an object (this should NOT happen)
        if isinstance(xpub, dict):
            print(f"🚨 ERROR: get_xpub_balance received a dict instead of string: {xpub}")
            import traceback
            print("🚨 Call stack:")
            traceback.print_stack()
            # Try to extract xpub from the object
            if 'address' in xpub:
                print(f"🔧 Attempting to extract xpub: {xpub['address']}")
                xpub = xpub['address']
            else:
                print(f"❌ Cannot extract xpub from object: {xpub}")
                return 0.0
        elif not isinstance(xpub, str):
            print(f"🚨 ERROR: get_xpub_balance received non-string type {type(xpub)}: {xpub}")
            return 0.0
            
        import time
        try:
            # Check balance cache first (except in startup mode where we want minimal processing)
            if not startup_mode:
                cache_key = f"balance:{xpub}"
                cached_data = self._balance_cache.get(cache_key)
                if cached_data:
                    cached_balance, timestamp = cached_data
                    if time.time() - timestamp < self._balance_cache_timeout:
                        print(f"⚡ [CACHE] Using cached balance for {xpub[:20]}... ({cached_balance:.8f} BTC)")
                        return cached_balance
            
            if startup_mode:
                print(f"🚀 [STARTUP] Using cached balance for {xpub[:20]}... (gap limit detection skipped)")
            else:
                print(f"💰 Calculating balance for {xpub[:20]}... by deriving addresses")
            
            # Get all derived addresses
            addresses = self.get_xpub_addresses(xpub, startup_mode=startup_mode)
            
            if not addresses:
                print(f"⚠️ No addresses derived for {xpub[:20]}...")
                return 0.0
            
            # Calculate total balance from all addresses (in parallel for better performance)
            import concurrent.futures
            total_balance = 0.0
            addresses_with_balance = 0
            
            if len(addresses) > 10:  # Use parallel processing for larger address sets
                print(f"🚀 [PARALLEL] Fetching balances for {len(addresses)} addresses...")
                
                def fetch_address_balance(address):
                    """Fetch balance for a single address."""
                    try:
                        balance = self.get_address_balance(address)
                        return address, balance
                    except Exception as e:
                        print(f"⚠️ Error fetching balance for {address}: {e}")
                        return address, 0.0
                
                # Use ThreadPoolExecutor for parallel address balance fetching
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(addresses), 10)) as executor:
                    # Submit all address balance requests
                    future_to_address = {executor.submit(fetch_address_balance, addr): addr for addr in addresses}
                    
                    # Collect results
                    for future in concurrent.futures.as_completed(future_to_address):
                        address, balance = future.result()
                        if balance > 0:
                            total_balance += balance
                            addresses_with_balance += 1
            else:
                # Sequential processing for smaller address sets
                for address in addresses:
                    balance = self.get_address_balance(address)
                    if balance > 0:
                        total_balance += balance
                        addresses_with_balance += 1
            
            print(f"✅ XPUB/ZPUB {xpub[:20]}... total: {total_balance:.8f} BTC from {addresses_with_balance}/{len(addresses)} addresses")
            
            # Cache the balance for future requests (but not in startup mode)
            if not startup_mode:
                cache_key = f"balance:{xpub}"
                self._balance_cache[cache_key] = (total_balance, time.time())
                print(f"💾 [CACHE] Stored balance for {xpub[:20]}... (valid for {self._balance_cache_timeout}s)")
            
            return total_balance
            
        except Exception as e:
            print(f"⚠️ Error calculating balance for XPUB/ZPUB {xpub[:20]}...: {e}")
            return 0.0
    
    def fetch_wallet_balances(self, startup_mode: bool = False) -> Optional[Dict[str, Union[str, float, int, List]]]:
        """
        Fetch wallet balances with deduplication to avoid double-counting addresses.
        Includes conflict detection to prevent manually added addresses that are also
        derived from XPUB/ZPUB keys.
        
        Args:
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
        
        Returns:
            Dict containing:
            - addresses: List of individual address balances
            - xpubs: List of XPUB wallet balances  
            - total_btc: Total balance in BTC
            - total_fiat: Total balance in fiat (if enabled)
            - fiat_currency: Fiat currency used
            - unit: Display unit (BTC/sats)
            - duplicates_removed: Count of duplicate addresses removed
            - error: Error message if fetch failed or conflicts detected
            - conflicts: Conflict details if present
        """
        # Use lock to prevent concurrent balance fetching
        if not self._fetch_lock.acquire(blocking=False):
            print("⏳ Wallet balance fetch already in progress, skipping duplicate request")
            return {"error": "Balance fetch in progress"}
        
        try:
            # Parse wallet entries (supports both old and new format)
            entries_with_comments, user_addresses, user_xpubs = self._parse_wallet_entries()
            
            if not entries_with_comments:
                return {"error": "No wallet addresses, XPUBs, or ZPUBs configured"}
            
            print(f"💰 Processing {len(entries_with_comments)} wallet entries...")
            
            # Extract simple list for conflict detection (backwards compatibility)
            simple_wallet_list = [entry["address"] if isinstance(entry, dict) else entry for entry in entries_with_comments]
            
            # Check for address conflicts FIRST before processing balances
            conflicts = self.detect_address_conflicts(simple_wallet_list)
            if conflicts and conflicts.get("has_conflicts"):
                return {"error": conflicts["error_message"], "conflicts": conflicts}
            
            print(f"🔑 Found {len(user_xpubs)} extended keys and {len(user_addresses)} regular addresses")
            
            # 1. Fetch all addresses from all XPUBs/ZPUBs
            all_xpub_addresses = set()
            for xpub in user_xpubs:
                xpub_addresses = self.get_xpub_addresses(xpub)
                all_xpub_addresses.update(xpub_addresses)
            
            # 2. Filter out duplicate addresses that belong to any XPUB/ZPUB  
            filtered_addresses = [addr for addr in user_addresses if addr not in all_xpub_addresses]
            duplicates_count = len(user_addresses) - len(filtered_addresses)
            
            if duplicates_count > 0:
                print(f"🔄 Filtered out {duplicates_count} duplicate addresses already covered by XPUB/ZPUB")
            
            # 3. Fetch balances for filtered addresses with comments
            address_balances = []
            for address in filtered_addresses:
                balance = self.get_address_balance(address)
                if balance > 0:  # Only include addresses with positive balance
                    # Find comment for this address
                    comment = "Address"
                    for entry in entries_with_comments:
                        if isinstance(entry, dict) and entry.get("address") == address:
                            comment = entry.get("comment", "Address")
                            break
                    
                    address_balances.append({
                        "address": address,
                        "balance_btc": balance,
                        "comment": comment
                    })
            
            # 4. Fetch balances for XPUBs/ZPUBs with comments (in parallel)
            import concurrent.futures
            import threading
            
            def fetch_single_xpub_balance(xpub_info):
                """Fetch balance for a single XPUB/ZPUB with error handling."""
                xpub, entries_with_comments, startup_mode = xpub_info
                try:
                    print(f"🔄 [PARALLEL] Starting balance calculation for {xpub[:20]}...")
                    balance = self.get_optimized_xpub_balance(xpub, startup_mode=startup_mode)
                    
                    if balance > 0:  # Only include XPUBs/ZPUBs with positive balance
                        # Find comment for this XPUB
                        comment = "Hardware Wallet"
                        for entry in entries_with_comments:
                            if isinstance(entry, dict) and entry.get("address") == xpub:
                                comment = entry.get("comment", "Hardware Wallet")
                                break
                        
                        # Determine key type for display
                        key_type = "zpub" if xpub.lower().startswith("zpub") else "xpub"
                        result = {
                            "xpub": xpub,
                            "xpub_short": f"{key_type[:4]}...{xpub[-8:]}",
                            "balance_btc": balance,
                            "comment": comment
                        }
                        print(f"✅ [PARALLEL] {xpub[:20]}... completed: {balance:.8f} BTC")
                        return result
                    else:
                        print(f"⚪ [PARALLEL] {xpub[:20]}... completed: 0 BTC (no balance)")
                        return None
                except Exception as e:
                    print(f"❌ [PARALLEL] Error processing {xpub[:20]}...: {e}")
                    return None
            
            # Prepare XPUB info for parallel processing
            xpub_info_list = [(xpub, entries_with_comments, startup_mode) for xpub in user_xpubs]
            
            if len(user_xpubs) > 1:
                print(f"🚀 [PARALLEL] Starting parallel balance calculation for {len(user_xpubs)} wallets...")
                # Use ThreadPoolExecutor for parallel processing
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(user_xpubs), 5)) as executor:
                    # Submit all tasks
                    future_to_xpub = {executor.submit(fetch_single_xpub_balance, xpub_info): xpub_info[0] 
                                     for xpub_info in xpub_info_list}
                    
                    # Collect results as they complete
                    xpub_balances = []
                    for future in concurrent.futures.as_completed(future_to_xpub):
                        result = future.result()
                        if result:
                            xpub_balances.append(result)
                
                print(f"✅ [PARALLEL] Completed parallel wallet scanning in reduced time")
            else:
                # Single wallet - use sequential processing
                print(f"🔄 [SEQUENTIAL] Processing single wallet...")
                xpub_balances = []
                for xpub_info in xpub_info_list:
                    result = fetch_single_xpub_balance(xpub_info)
                    if result:
                        xpub_balances.append(result)
            
            # 5. Calculate total balance
            total_btc = (sum(addr["balance_btc"] for addr in address_balances) + 
                        sum(xpub["balance_btc"] for xpub in xpub_balances))
            
            # 6. Get fiat conversion using wallet-specific currency
            fiat_currency = self.config.get("wallet_balance_currency", "EUR")  # Use wallet-specific currency
            total_fiat = None
            
            if total_btc > 0:
                print(f"💰 Converting {total_btc:.8f} BTC to {fiat_currency}...")
                total_fiat = self._convert_to_fiat(total_btc, fiat_currency)
                if total_fiat:
                    print(f"✅ Conversion successful: {total_fiat:.2f} {fiat_currency}")
                else:
                    print(f"❌ Conversion failed for {fiat_currency}")
                    total_fiat = 0.0  # Set to 0 if conversion fails
            else:
                # Zero balance - show 0.00 in fiat currency
                total_fiat = 0.0
                print(f"💰 Zero balance - showing 0.00 {fiat_currency}")
            
            # 7. Determine display unit
            unit = self.config.get("wallet_balance_unit", "BTC")
            
            fetched_data = {
                "addresses": address_balances,
                "xpubs": xpub_balances,
                "total_btc": total_btc,
                "total_fiat": total_fiat,
                "fiat_currency": fiat_currency,
                "unit": unit,
                "duplicates_removed": duplicates_count,
                "show_fiat": True  # Always show fiat now that we have wallet-specific currency
            }

            self.update_cache(fetched_data)
            return fetched_data
        
        except Exception as e:
            return {"error": f"Failed to fetch wallet balances: {e}"}
        finally:
            # Always release the lock
            self._fetch_lock.release()
    
    def update_cache(self, wallet_data):
        self._wallet_cache = wallet_data
        
        if self.use_unified_cache:
            # Save to unified secure cache
            self.unified_cache.set_cache("wallet_balance_cache", wallet_data)
            print("💾 Wallet balance cache updated in unified secure storage")
        elif hasattr(self, 'secure_cache_manager') and SECURE_CACHE_AVAILABLE:
            self.secure_cache_manager.save_cache(wallet_data)
            print("💾 Wallet balance cache updated in secure storage")
        else:
            # No fallback to individual file - secure cache only
            print("⚠️ Unified secure cache not available - wallet balance not cached")
            print("⚠️ Please ensure unified secure cache is properly initialized")

    def get_cached_wallet_balances(self):
        if self.use_unified_cache:
            # Load from unified secure cache
            cache = self.unified_cache.get_cache("wallet_balance_cache")
            if cache:
                self._wallet_cache = cache
                return cache
        elif hasattr(self, 'secure_cache_manager') and SECURE_CACHE_AVAILABLE:
            cache = self.secure_cache_manager.load_cache()
            if cache:
                self._wallet_cache = cache
                return cache
        else:
            # No fallback to individual file - secure cache only
            print("⚠️ Unified secure cache not available - no cached wallet balance")
        
        return None
