"""
Configuration Observer and Asynchronous Address Cache Manager

Monitors wallet configuration changes and proactively rebuilds address cache
to ensure instant access during balance fetching operations.

"""

import json
import hashlib
import time
import threading
import os
from typing import Dict, List, Set, Optional, Callable, Tuple
import queue
from datetime import datetime

from address_derivation import AddressDerivation

# Optional import for secure cache - graceful fallback if not available
try:
    from secure_cache_manager import SecureCacheManager
    SECURE_CACHE_AVAILABLE = True
except ImportError:
    SECURE_CACHE_AVAILABLE = False


class ConfigurationObserver:
    """Monitors configuration changes and triggers cache updates."""
    
    def __init__(self, config_file: str = "config.json", cache_manager: 'AsyncAddressCacheManager' = None):
        """
        Initialize configuration observer.
        
        Args:
            config_file: Path to configuration file to monitor
            cache_manager: Cache manager to notify of changes
        """
        self.config_file = config_file
        self.cache_manager = cache_manager
        self.last_config_hash = None
        self.last_wallet_config_hash = None
        self.is_monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
        # Initialize with current config
        self._update_config_hashes()
    
    def _calculate_config_hash(self, config: Dict) -> str:
        """Calculate hash of entire configuration."""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def _calculate_wallet_config_hash(self, config: Dict) -> str:
        """Calculate hash of wallet-specific configuration."""
        wallet_config = {
            "wallet_balance_addresses": config.get("wallet_balance_addresses", []),
            "xpub_derivation_count": config.get("xpub_derivation_count", 20)
        }
        config_str = json.dumps(wallet_config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def _load_config(self) -> Optional[Dict]:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading config: {e}")
        return None
    
    def _update_config_hashes(self):
        """Update stored configuration hashes."""
        config = self._load_config()
        if config:
            self.last_config_hash = self._calculate_config_hash(config)
            self.last_wallet_config_hash = self._calculate_wallet_config_hash(config)
    
    def check_for_changes(self) -> Dict[str, bool]:
        """
        Check for configuration changes.
        
        Returns:
            Dict indicating which types of changes were detected
        """
        config = self._load_config()
        if not config:
            return {"config_changed": False, "wallet_config_changed": False}
        
        current_config_hash = self._calculate_config_hash(config)
        current_wallet_config_hash = self._calculate_wallet_config_hash(config)
        
        config_changed = current_config_hash != self.last_config_hash
        wallet_config_changed = current_wallet_config_hash != self.last_wallet_config_hash
        
        if config_changed:
            print(f"📋 Configuration change detected")
            self.last_config_hash = current_config_hash
        
        if wallet_config_changed:
            print(f"💳 Wallet configuration change detected")
            self.last_wallet_config_hash = current_wallet_config_hash
            
            # Notify cache manager
            if self.cache_manager:
                self.cache_manager.queue_cache_rebuild(config)
        
        return {
            "config_changed": config_changed,
            "wallet_config_changed": wallet_config_changed
        }
    
    def start_monitoring(self, check_interval: float = 2.0):
        """
        Start monitoring configuration file for changes.
        
        Args:
            check_interval: Seconds between configuration checks
        """
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.stop_event.clear()
        
        def monitor_loop():
            print(f"👁️ Started monitoring {self.config_file} (every {check_interval}s)")
            
            while not self.stop_event.wait(check_interval):
                try:
                    self.check_for_changes()
                except Exception as e:
                    print(f"⚠️ Error during config monitoring: {e}")
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring configuration file."""
        if self.is_monitoring:
            self.stop_event.set()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5.0)
            self.is_monitoring = False
            print(f"🛑 Stopped monitoring {self.config_file}")


class AsyncAddressCacheManager:
    """Manages asynchronous address derivation and caching."""
    
    def __init__(self, cache_file: str = "async_wallet_address_cache.json"):
        """
        Initialize async cache manager.
        
        Args:
            cache_file: Path to cache file
        """
        self.cache_file = cache_file
        self.address_derivation = AddressDerivation()
        
        # Initialize cache with security if available
        if SECURE_CACHE_AVAILABLE:
            self.secure_cache_manager = SecureCacheManager(self.cache_file)
            self.cache = self.secure_cache_manager.load_cache()
            print(f"🔐 Using secure encrypted async cache")
        else:
            self.cache = self._load_cache()
            print(f"⚠️ Using plain text async cache (secure cache unavailable)")
        
        self.work_queue = queue.Queue()
        self.worker_thread = None
        self.is_running = False
        self.stop_event = threading.Event()
        self.callbacks = []  # Callbacks to notify when cache updates complete
        
        # Start worker thread
        self.start_worker()
    
    def _load_cache(self) -> Dict:
        """Load cache from file."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                    print(f"📂 Loaded async address cache with {len(cache)} entries")
                    return cache
        except Exception as e:
            print(f"⚠️ Failed to load async cache: {e}")
        
        return {}
    
    def _save_cache(self) -> bool:
        """Save cache to file."""
        if hasattr(self, 'secure_cache_manager') and SECURE_CACHE_AVAILABLE:
            # Use secure cache manager
            return self.secure_cache_manager.save_cache(self.cache)
        else:
            # Fallback to plain text cache with atomic write
            try:
                # Write to temporary file first, then atomic rename
                temp_file = self.cache_file + '.tmp'
                with open(temp_file, 'w') as f:
                    json.dump(self.cache, f, indent=2)
                
                # Atomic rename
                if os.path.exists(self.cache_file):
                    os.remove(self.cache_file)
                os.rename(temp_file, self.cache_file)
                
                return True
            except Exception as e:
                print(f"⚠️ Failed to save async cache: {e}")
                # Clean up temp file
                temp_file = self.cache_file + '.tmp'
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                return False
    
    def _calculate_cache_key(self, config: Dict) -> str:
        """Calculate cache key for configuration."""
        wallet_config = {
            "wallet_balance_addresses": sorted(config.get("wallet_balance_addresses", [])),
            "xpub_derivation_count": config.get("xpub_derivation_count", 20)
        }
        config_str = json.dumps(wallet_config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    def get_cached_addresses(self, config: Dict) -> Optional[Dict[str, List[str]]]:
        """
        Get cached addresses for configuration.
        
        Args:
            config: Wallet configuration
            
        Returns:
            Dict mapping XPUBs to their derived addresses, or None if not cached
        """
        cache_key = self._calculate_cache_key(config)
        
        if cache_key in self.cache:
            cached_entry = self.cache[cache_key]
            print(f"🚀 Async cache HIT for wallet config")
            return cached_entry.get("address_mapping", {})
        
        return None
    
    def get_addresses(self, cache_key: str) -> Optional[List[str]]:
        """
        Get cached addresses for a simple cache key (used by wallet_balance_api).
        
        Args:
            cache_key: Cache key in format "xpub...:count"
            
        Returns:
            List of addresses if cached, None if not found
        """
        # Check if this key exists in our cache as a simple entry
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if isinstance(entry, dict) and 'addresses' in entry:
                return entry['addresses']
            elif isinstance(entry, list):
                # Legacy format - just a list of addresses
                return entry
        
        return None
    
    def cache_addresses(self, cache_key: str, addresses: List[str]):
        """
        Cache addresses for a simple cache key (used by wallet_balance_api).
        
        Args:
            cache_key: Cache key in format "xpub...:count"
            addresses: List of addresses to cache
        """
        self.cache[cache_key] = {
            'addresses': addresses,
            'timestamp': time.time(),
            'count': len(addresses)
        }
        
        # Save cache immediately for simple caching
        self._save_cache()
        print(f"💾 Async cached {len(addresses)} addresses for key {cache_key[:20]}...")
    
    def get_addresses_with_indices(self, cache_key: str) -> Optional[List[Tuple[str, int]]]:
        """
        Get cached addresses with their derivation indices.
        
        Args:
            cache_key: Cache key in format "xpub...:count"
            
        Returns:
            List of (address, index) tuples if cached, None if not found
        """
        # Check if this key exists in our cache as a simple entry
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if isinstance(entry, dict) and 'addresses' in entry:
                # Return addresses with sequential indices
                addresses = entry['addresses']
                return [(addr, idx) for idx, addr in enumerate(addresses)]
            elif isinstance(entry, list):
                # Legacy format - just a list of addresses
                return [(addr, idx) for idx, addr in enumerate(entry)]
        
        return None
    
    def invalidate_cache(self, pattern: str = None):
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: Pattern to match cache keys (if None, clears all)
        """
        if pattern is None:
            # Clear all cache
            self.cache.clear()
            print(f"🗑️ Cleared all async cache entries")
        else:
            # Clear entries matching pattern
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
            print(f"🗑️ Cleared {len(keys_to_remove)} async cache entries matching '{pattern}'")
        
        self._save_cache()
    
    def queue_cache_rebuild(self, config: Dict):
        """
        Queue a cache rebuild for the given configuration.
        
        Args:
            config: Wallet configuration that changed
        """
        work_item = {
            "type": "rebuild_cache",
            "config": config,
            "timestamp": time.time()
        }
        
        try:
            # Clear any existing rebuild tasks for efficiency
            temp_queue = queue.Queue()
            rebuild_queued = False
            
            while not self.work_queue.empty():
                try:
                    item = self.work_queue.get_nowait()
                    if item["type"] != "rebuild_cache":
                        temp_queue.put(item)
                    else:
                        rebuild_queued = True
                except queue.Empty:
                    break
            
            # Put back non-rebuild items
            while not temp_queue.empty():
                self.work_queue.put(temp_queue.get())
            
            # Add the new rebuild task
            self.work_queue.put(work_item)
            
            if not rebuild_queued:
                print(f"📋 Queued address cache rebuild")
            else:
                print(f"📋 Replaced existing cache rebuild task")
                
        except Exception as e:
            print(f"⚠️ Failed to queue cache rebuild: {e}")
    
    def _rebuild_cache(self, config: Dict):
        """
        Rebuild address cache for configuration.
        
        Args:
            config: Wallet configuration
        """
        try:
            start_time = time.time()
            
            wallet_entries = config.get("wallet_balance_addresses", [])
            derivation_count = config.get("xpub_derivation_count", 20)
            
            if not wallet_entries:
                print(f"📋 No wallet entries to cache")
                return
            
            print(f"🔄 Rebuilding address cache for {len(wallet_entries)} entries...")
            
            # Separate XPUBs/ZPUBs and regular addresses
            xpubs = [entry for entry in wallet_entries if entry.lower().startswith(("xpub", "zpub"))]
            addresses = [entry for entry in wallet_entries if not entry.lower().startswith(("xpub", "zpub"))]
            
            address_mapping = {}
            total_derived = 0
            
            # Derive addresses for each XPUB/ZPUB
            for xpub in xpubs:
                try:
                    # Check if gap limit detection is enabled
                    enable_gap_limit = config.get("xpub_enable_gap_limit", False)
                    
                    if enable_gap_limit:
                        print(f"� Running gap limit detection for new ZPUB {xpub[:20]}...")
                        # Import gap limit detection from wallet balance API
                        try:
                            from wallet_balance_api import WalletBalanceAPI
                            temp_api = WalletBalanceAPI(config)
                            derived_addresses, final_count = temp_api.derive_addresses_with_gap_limit(xpub)
                            address_list = [addr for addr, idx in derived_addresses]
                            print(f"✅ Gap limit detection: 20 → {final_count} addresses for {xpub[:20]}...")
                        except Exception as gap_error:
                            print(f"⚠️ Gap limit detection failed for {xpub[:20]}...: {gap_error}")
                            print(f"🔄 Falling back to basic derivation ({derivation_count} addresses)")
                            derived_addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
                            address_list = [addr for addr, idx in derived_addresses]
                    else:
                        print(f"🔑 Deriving {derivation_count} addresses from {xpub[:20]}... (gap limit disabled)")
                        derived_addresses = self.address_derivation.derive_addresses(xpub, derivation_count)
                        address_list = [addr for addr, idx in derived_addresses]
                    
                    address_mapping[xpub] = address_list
                    total_derived += len(address_list)
                    
                    print(f"✅ Cached {len(address_list)} addresses for {xpub[:20]}...")
                    
                except Exception as e:
                    print(f"⚠️ Failed to derive addresses for {xpub[:20]}...: {e}")
                    address_mapping[xpub] = []
            
            # Include regular addresses in mapping
            if addresses:
                address_mapping["_direct_addresses"] = addresses
            
            # Calculate cache key and store
            cache_key = self._calculate_cache_key(config)
            
            self.cache[cache_key] = {
                "address_mapping": address_mapping,
                "derivation_count": derivation_count,
                "total_xpubs": len(xpubs),
                "total_addresses": len(addresses),
                "total_derived": total_derived,
                "cached_at": time.time(),
                "build_duration": time.time() - start_time
            }
            
            # Save to disk
            if self._save_cache():
                duration = time.time() - start_time
                print(f"💾 Cache rebuild complete: {total_derived} addresses derived in {duration:.2f}s")
                
                # Notify callbacks
                self._notify_callbacks("cache_rebuilt", {
                    "total_derived": total_derived,
                    "duration": duration,
                    "config": config
                })
            else:
                print(f"❌ Failed to save rebuilt cache")
                
        except Exception as e:
            print(f"⚠️ Error rebuilding cache: {e}")
    
    def _worker_loop(self):
        """Main worker loop for processing async tasks."""
        print(f"🔧 Started async address cache worker")
        
        while not self.stop_event.is_set():
            try:
                # Wait for work with timeout
                work_item = self.work_queue.get(timeout=1.0)
                
                if work_item["type"] == "rebuild_cache":
                    self._rebuild_cache(work_item["config"])
                
                self.work_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ Error in cache worker: {e}")
    
    def start_worker(self):
        """Start the async worker thread."""
        if self.is_running:
            return
        
        self.is_running = True
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def stop_worker(self):
        """Stop the async worker thread."""
        if self.is_running:
            self.stop_event.set()
            if self.worker_thread:
                self.worker_thread.join(timeout=5.0)
            self.is_running = False
            print(f"🛑 Stopped async address cache worker")
    
    def add_callback(self, callback: Callable):
        """Add callback to be notified of cache events."""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self, event_type: str, data: Dict):
        """Notify all callbacks of an event."""
        for callback in self.callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"⚠️ Error in cache callback: {e}")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        total_entries = len(self.cache)
        total_addresses = 0
        total_derived = 0
        
        for entry in self.cache.values():
            mapping = entry.get("address_mapping", {})
            for key, addresses in mapping.items():
                if key == "_direct_addresses":
                    total_addresses += len(addresses)
                else:
                    total_derived += len(addresses)
        
        cache_size = 0
        if os.path.exists(self.cache_file):
            cache_size = os.path.getsize(self.cache_file)
        
        return {
            "total_entries": total_entries,
            "total_direct_addresses": total_addresses,
            "total_derived_addresses": total_derived,
            "cache_file_size": cache_size,
            "cache_file": self.cache_file,
            "worker_running": self.is_running,
            "queue_size": self.work_queue.qsize()
        }


class WalletConfigurationManager:
    """Unified manager for wallet configuration monitoring and caching."""
    
    def __init__(self, config_file: str = "config.json"):
        """
        Initialize wallet configuration manager.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.cache_manager = AsyncAddressCacheManager()
        self.observer = ConfigurationObserver(config_file, self.cache_manager)
        
        # Set up initial cache
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Initialize cache with current configuration."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    print(f"🔄 Initializing address cache...")
                    self.cache_manager.queue_cache_rebuild(config)
        except Exception as e:
            print(f"⚠️ Failed to initialize cache: {e}")
    
    def start_monitoring(self, check_interval: float = 2.0):
        """Start monitoring for configuration changes."""
        self.observer.start_monitoring(check_interval)
    
    def stop_monitoring(self):
        """Stop monitoring and clean up resources."""
        self.observer.stop_monitoring()
        self.cache_manager.stop_worker()
    
    def get_addresses_for_config(self, config: Dict) -> Optional[Dict[str, List[str]]]:
        """Get addresses for configuration (from cache if available)."""
        return self.cache_manager.get_cached_addresses(config)
    
    def force_cache_rebuild(self):
        """Force a cache rebuild with current configuration."""
        self._initialize_cache()
    
    def get_status(self) -> Dict:
        """Get status of monitoring and caching system."""
        cache_stats = self.cache_manager.get_cache_stats()
        
        return {
            "monitoring_active": self.observer.is_monitoring,
            "worker_active": self.cache_manager.is_running,
            "cache_entries": cache_stats["total_entries"],
            "derived_addresses": cache_stats["total_derived_addresses"],
            "queue_size": cache_stats["queue_size"],
            "cache_file_size": cache_stats["cache_file_size"]
        }


def test_configuration_management():
    """Test the configuration management system."""
    print("🧪 Configuration Management Test")
    print("=" * 40)
    
    # Create manager
    manager = WalletConfigurationManager()
    
    # Add callback to monitor cache events
    def cache_callback(event_type, data):
        if event_type == "cache_rebuilt":
            print(f"🎉 Cache rebuilt: {data['total_derived']} addresses in {data['duration']:.2f}s")
    
    manager.cache_manager.add_callback(cache_callback)
    
    # Start monitoring
    manager.start_monitoring(1.0)  # Check every second for testing
    
    print(f"📊 Initial status:")
    status = manager.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    # Wait a bit for initial cache build
    import time
    print(f"\n⏳ Waiting for initial cache build...")
    time.sleep(5)
    
    # Check status again
    print(f"\n📊 Status after cache build:")
    status = manager.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    # Clean up
    manager.stop_monitoring()
    
    print(f"\n✅ Configuration management test complete")


if __name__ == "__main__":
    test_configuration_management()
