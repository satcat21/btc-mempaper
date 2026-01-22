"""
Block Reward Cache System

Implements efficient caching of coinbase transaction counts per address with
incremental updates and recovery capabilities.

Cache Structure:
{
    "addresses": {
        "address1": {
            "total_coinbase_count": 5,
            "synced_height": 850000,
            "last_updated": 1693737600,
            "first_block_found": 840000,
            "latest_block_found": 849500
        }
    },
    "global_sync_height": 850000,
    "cache_version": "1.0",
    "last_full_scan": 1693737600
}
"""

import json
import os
import requests
import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import urllib3

# Import unified secure cache
try:
    from unified_secure_cache import get_unified_cache
    UNIFIED_CACHE_AVAILABLE = True
except ImportError:
    UNIFIED_CACHE_AVAILABLE = False
    print("⚠️ Unified secure cache not available, using local cache")

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BlockRewardCache:
    """Manages cached coinbase transaction counts with incremental updates."""
    
    def __init__(self, config_manager=None, cache_file="cache/block_reward_cache.json"):
        """
        Initialize block reward cache.
        
        Args:
            config_manager: ConfigManager instance for mempool configuration
            cache_file: Path to cache file (fallback for non-secure mode)
        """
        self.config_manager = config_manager
        self.cache_file = cache_file
        self.cache_lock = threading.RLock()
        self.cache_data = {
            "addresses": {},
            "global_sync_height": 0,
            "cache_version": "1.0",
            "last_full_scan": 0
        }
        
        # Try to use unified secure cache, fallback to individual file
        self.use_secure_cache = UNIFIED_CACHE_AVAILABLE
        if self.use_secure_cache:
            try:
                self.unified_cache = get_unified_cache()
                # print(f"🔐 Using unified secure cache for block reward data")
            except Exception as e:
                print(f"⚠️ Failed to initialize secure cache: {e}")
                self.use_secure_cache = False
        
        # Load existing cache
        self._load_cache()
        
        print(f"🗄️ Block reward cache initialized with {len(self.cache_data['addresses'])} addresses")
        if self.cache_data['global_sync_height'] > 0:
            print(f"📊 Global sync height: {self.cache_data['global_sync_height']}")
    
    def _get_mempool_base_url(self) -> str:
        """Get mempool API base URL with unified host field and HTTPS support."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            mempool_host = config.get("mempool_host", "127.0.0.1")
            mempool_rest_port = config.get("mempool_rest_port", 4081)
            mempool_use_https = config.get("mempool_use_https", False)
            
            # Build URL with proper protocol
            protocol = "https" if mempool_use_https else "http"
            
            # Don't include port in URL if using standard ports with domain/hostname
            if (mempool_use_https and str(mempool_rest_port) in ["443", "80"]) or \
               (not mempool_use_https and str(mempool_rest_port) in ["80", "443"]):
                return f"{protocol}://{mempool_host}/api"
            else:
                return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
        
        # Fallback
        return "http://127.0.0.1:4081/api"
    
    def _get_mempool_verify_ssl(self) -> bool:
        """Get SSL verification setting from configuration."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            return config.get("mempool_verify_ssl", True)
        return True
    
    def _crop_address_for_log(self, address: str) -> str:
        """
        Crop Bitcoin address for privacy in logs.
        Shows first 6 and last 6 characters with ... in between.
        
        Args:
            address: Full Bitcoin address
            
        Returns:
            Cropped address string (e.g., "bc1qwa...y2qpqy")
        """
        if len(address) <= 12:
            return address  # Don't crop if address is too short
        return f"{address[:6]}...{address[-6:]}"
    
    def _load_cache(self):
        """Load cache from secure storage or file."""
        try:
            if self.use_secure_cache:
                # Load from unified secure cache
                cache_data = self.unified_cache.get_cache("block_reward_cache")
                if cache_data and self._validate_cache_structure(cache_data):
                    self.cache_data = cache_data
                    # print(f"✅ Loaded block reward cache from secure storage")
                else:
                    print(f"📁 No secure cache data, initializing new cache")
                    self._save_cache()
            else:
                # Fallback to individual file
                # Ensure cache directory exists
                cache_dir = os.path.dirname(self.cache_file)
                if cache_dir and not os.path.exists(cache_dir):
                    os.makedirs(cache_dir, exist_ok=True)
                    print(f"📁 Created cache directory: {cache_dir}")
                
                if os.path.exists(self.cache_file):
                    with open(self.cache_file, 'r') as f:
                        loaded_data = json.load(f)
                        
                    # Validate cache structure
                    if self._validate_cache_structure(loaded_data):
                        self.cache_data = loaded_data
                        # print(f"✅ Loaded block reward cache from {self.cache_file}")
                    else:
                        print(f"⚠️ Invalid cache structure, initializing new cache")
                        self._save_cache()
                else:
                    print(f"📁 No existing cache file, creating new one")
                    self._save_cache()
                
        except Exception as e:
            print(f"❌ Error loading cache: {e}")
            # Initialize with default structure on error
            self._save_cache()
    
    def _validate_cache_structure(self, data: Dict) -> bool:
        """Validate cache data structure."""
        required_keys = ["addresses", "global_sync_height", "cache_version"]
        return all(key in data for key in required_keys)
    
    def _save_cache(self):
        """Save cache to secure storage or file."""
        try:
            with self.cache_lock:
                # Add metadata
                self.cache_data["last_updated"] = time.time()
                
                if self.use_secure_cache:
                    # Save to unified secure cache
                    self.unified_cache.set_cache("block_reward_cache", self.cache_data)
                else:
                    # Fallback to individual file
                    # Create backup before saving
                    if os.path.exists(self.cache_file):
                        backup_file = f"{self.cache_file}.backup"
                        import shutil
                        shutil.copy2(self.cache_file, backup_file)
                    
                    # Save cache
                    with open(self.cache_file, 'w') as f:
                        json.dump(self.cache_data, f, indent=2)
                    
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            # If secure cache fails, try fallback to file
            if self.use_secure_cache:
                print(f"🔄 Falling back to individual cache file")
                self.use_secure_cache = False
                self._save_cache()
    
    def get_current_block_height(self) -> Optional[int]:
        """Get current blockchain height from mempool API."""
        try:
            base_url = self._get_mempool_base_url()
            verify_ssl = self._get_mempool_verify_ssl()
            response = requests.get(f"{base_url}/blocks/tip/height", timeout=10, verify=verify_ssl)
            response.raise_for_status()
            return int(response.text.strip())
        except Exception as e:
            print(f"⚠️ Error getting current block height: {e}")
            return None
    
    def get_coinbase_count(self, address: str) -> int:
        """
        Get cached coinbase count for address.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            Number of coinbase transactions found for this address
        """
        with self.cache_lock:
            addr_data = self.cache_data["addresses"].get(address, {})
            return addr_data.get("total_coinbase_count", 0)
    
    def get_address_sync_height(self, address: str) -> int:
        """Get the sync height for a specific address."""
        with self.cache_lock:
            addr_data = self.cache_data["addresses"].get(address, {})
            return addr_data.get("synced_height", 0)
    
    def add_new_address(self, address: str, scan_from_height: Optional[int] = None) -> bool:
        """
        Add a new address to monitoring and perform initial scan using transaction history.
        
        Args:
            address: Bitcoin address to monitor
            scan_from_height: Minimum height to consider (for filtering, optional)
            
        Returns:
            True if successfully added and scanned
        """
        print(f"🔍 Adding new address to block reward monitoring: {self._crop_address_for_log(address)}")
        
        with self.cache_lock:
            # Check if address already exists
            if address in self.cache_data["addresses"]:
                print(f"📍 Address {self._crop_address_for_log(address)} already in cache")
                return True
            
            # Initialize address entry
            current_height = self.get_current_block_height()
            if current_height is None:
                print(f"❌ Cannot get current block height, cannot add address")
                return False
            
            # Set minimum height for filtering (default to block 1 for complete history)
            min_height = scan_from_height if scan_from_height is not None else 1
            
            print(f"⏳ Performing transaction history scan for {self._crop_address_for_log(address)} (filtering blocks >= {min_height})")
            
            # Perform historical scan using transaction history API
            coinbase_count = self._scan_address_history(address, min_height, current_height)
            
            # Add to cache
            self.cache_data["addresses"][address] = {
                "total_coinbase_count": coinbase_count,
                "synced_height": current_height,
                "last_updated": time.time(),
                "first_block_found": None,
                "latest_block_found": None,
                "scan_method": "transaction_history"  # Track which method was used
            }
            
            # Update global sync height
            self.cache_data["global_sync_height"] = max(
                self.cache_data["global_sync_height"], 
                current_height
            )
            
            self._save_cache()
            
            print(f"✅ Address {self._crop_address_for_log(address)} added with {coinbase_count} coinbase transactions found")
            return True
    
    def _scan_address_history(self, address: str, start_height: int, end_height: int) -> int:
        """
        Scan address transaction history for coinbase transactions using mempool API.
        This is much more efficient than scanning entire blockchain.
        
        Args:
            address: Bitcoin address to scan for
            start_height: Starting block height (used for filtering)
            end_height: Ending block height (used for filtering)
            
        Returns:
            Number of coinbase transactions found
        """
        coinbase_count = 0
        base_url = self._get_mempool_base_url()
        verify_ssl = self._get_mempool_verify_ssl()
        
        print(f"🔍 Scanning transaction history for address {self._crop_address_for_log(address)}")
        
        try:
            # Get all transactions for this address
            # Use the address API endpoint to get transaction history
            tx_response = requests.get(f"{base_url}/address/{address}/txs", timeout=30, verify=verify_ssl)
            
            if not tx_response.ok:
                print(f"⚠️ Failed to get transactions for address {self._crop_address_for_log(address)}: {tx_response.status_code}")
                return 0
            
            transactions = tx_response.json()
            
            if not transactions:
                print(f"📭 No transactions found for address {self._crop_address_for_log(address)}")
                return 0
            
            print(f"📊 Found {len(transactions)} transactions for address {self._crop_address_for_log(address)}")
            
            # Check each transaction to see if it's a coinbase transaction
            for i, tx in enumerate(transactions):
                try:
                    # Get block height for this transaction
                    tx_block_height = tx.get('status', {}).get('block_height')
                    
                    # Skip if transaction is not confirmed or outside our height range
                    if not tx_block_height:
                        continue
                        
                    if tx_block_height < start_height or tx_block_height > end_height:
                        continue
                    
                    # Check if this is a coinbase transaction
                    # Coinbase transactions have no inputs (vin is empty or has coinbase input)
                    vin = tx.get('vin', [])
                    
                    # Check for coinbase using multiple methods for compatibility
                    is_coinbase = False
                    if len(vin) == 1:
                        input_data = vin[0]
                        # Method 1: Check is_coinbase field (local mempool API)
                        if input_data.get('is_coinbase', False):
                            is_coinbase = True
                        # Method 2: Check for coinbase field (some APIs)
                        elif 'coinbase' in input_data:
                            is_coinbase = True
                        # Method 3: Check for null txid (coinbase pattern)
                        elif input_data.get('txid') == '0000000000000000000000000000000000000000000000000000000000000000':
                            is_coinbase = True
                    
                    if is_coinbase:
                        # This is a coinbase transaction
                        coinbase_count += 1
                        print(f"🎯 Found coinbase transaction at height {tx_block_height}: {tx['txid']}")
                        
                        # Update first/latest block found in cache
                        with self.cache_lock:
                            addr_data = self.cache_data["addresses"].get(address, {})
                            if addr_data.get("first_block_found") is None or tx_block_height < addr_data.get("first_block_found", float('inf')):
                                addr_data["first_block_found"] = tx_block_height
                            if addr_data.get("latest_block_found") is None or tx_block_height > addr_data.get("latest_block_found", 0):
                                addr_data["latest_block_found"] = tx_block_height
                    
                    # Progress update every 100 transactions
                    if (i + 1) % 100 == 0:
                        progress = ((i + 1) / len(transactions)) * 100
                        print(f"📊 Scan progress: {progress:.1f}% ({i + 1}/{len(transactions)} transactions)")
                
                except Exception as e:
                    print(f"⚠️ Error checking transaction {tx.get('txid', 'unknown')}: {e}")
                    continue
            
            # If we have more transactions, check for pagination
            # Some mempool APIs support pagination for addresses with many transactions
            if len(transactions) >= 25:  # Common page size
                print(f"📄 Address may have more transactions, checking for additional pages...")
                coinbase_count += self._scan_additional_pages(address, start_height, end_height, len(transactions))
            
        except Exception as e:
            print(f"❌ Error scanning address history for {address}: {e}")
            return 0
        
        print(f"✅ Scan complete: {coinbase_count} coinbase transactions found for {address}")
        return coinbase_count
    
    def _scan_additional_pages(self, address: str, start_height: int, end_height: int, offset: int) -> int:
        """
        Scan additional pages of transaction history for addresses with many transactions.
        
        Args:
            address: Bitcoin address to scan
            start_height: Starting block height
            end_height: Ending block height  
            offset: Number of transactions already processed
            
        Returns:
            Additional coinbase transactions found
        """
        additional_coinbase = 0
        base_url = self._get_mempool_base_url()
        
        try:
            # Try to get next page of transactions
            # Different mempool implementations may use different pagination schemes
            pagination_urls = [
                f"{base_url}/address/{address}/txs/chain/{offset}",  # Chain-based pagination
                f"{base_url}/address/{address}/txs?offset={offset}"   # Offset-based pagination
            ]
            
            for pagination_url in pagination_urls:
                try:
                    response = requests.get(pagination_url, timeout=30, verify=self._get_mempool_verify_ssl())
                    if response.ok:
                        transactions = response.json()
                        if transactions:
                            print(f"📄 Processing additional page with {len(transactions)} transactions")
                            
                            for tx in transactions:
                                try:
                                    tx_block_height = tx.get('status', {}).get('block_height')
                                    
                                    if not tx_block_height:
                                        continue
                                        
                                    if tx_block_height < start_height or tx_block_height > end_height:
                                        continue
                                    
                                    vin = tx.get('vin', [])
                                    
                                    # Check for coinbase using multiple methods for compatibility
                                    is_coinbase = False
                                    if len(vin) == 1:
                                        input_data = vin[0]
                                        # Method 1: Check is_coinbase field (local mempool API)
                                        if input_data.get('is_coinbase', False):
                                            is_coinbase = True
                                        # Method 2: Check for coinbase field (some APIs)
                                        elif 'coinbase' in input_data:
                                            is_coinbase = True
                                        # Method 3: Check for null txid (coinbase pattern)
                                        elif input_data.get('txid') == '0000000000000000000000000000000000000000000000000000000000000000':
                                            is_coinbase = True
                                    
                                    if is_coinbase:
                                        additional_coinbase += 1
                                        print(f"🎯 Found additional coinbase transaction at height {tx_block_height}: {tx['txid']}")
                                        
                                except Exception as e:
                                    continue
                            
                            # If this page has transactions, there might be more
                            if len(transactions) >= 25:
                                additional_coinbase += self._scan_additional_pages(address, start_height, end_height, offset + len(transactions))
                            
                            break  # Successfully processed a page, don't try other URLs
                            
                except Exception as e:
                    continue  # Try next pagination URL
            
        except Exception as e:
            print(f"⚠️ Error scanning additional pages for {address}: {e}")
        
        return additional_coinbase
    
    def update_for_new_block(self, block_hash: str, block_height: int) -> bool:
        """
        Update cache when a new block is found.
        
        Args:
            block_hash: Hash of the new block
            block_height: Height of the new block
            
        Returns:
            True if cache was updated
        """
        try:
            base_url = self._get_mempool_base_url()
            verify_ssl = self._get_mempool_verify_ssl()
            
            # Get block transactions
            txids_response = requests.get(f"{base_url}/block/{block_hash}/txids", timeout=10, verify=verify_ssl)
            if not txids_response.ok:
                return False
            
            txids = txids_response.json()
            if not txids:
                return False
            
            # Get coinbase transaction (first in list)
            coinbase_txid = txids[0]
            
            # Get coinbase transaction details
            tx_response = requests.get(f"{base_url}/tx/{coinbase_txid}", timeout=10, verify=verify_ssl)
            if not tx_response.ok:
                return False
            
            tx_data = tx_response.json()
            
            # Check if coinbase pays to any of our monitored addresses
            updated = False
            
            with self.cache_lock:
                monitored_addresses = set(self.cache_data["addresses"].keys())
                
                for vout in tx_data.get('vout', []):
                    address = vout.get('scriptpubkey_address')
                    if address in monitored_addresses:
                        # Update cache for this address
                        addr_data = self.cache_data["addresses"][address]
                        addr_data["total_coinbase_count"] += 1
                        addr_data["synced_height"] = block_height
                        addr_data["last_updated"] = time.time()
                        addr_data["latest_block_found"] = block_height
                        
                        if addr_data.get("first_block_found") is None:
                            addr_data["first_block_found"] = block_height
                        
                        updated = True
                        
                        value_btc = vout.get('value', 0) / 1e8
                        print(f"🎯 Block reward found! {address}: {value_btc:.8f} BTC at height {block_height}")
                
                # Update global sync height
                self.cache_data["global_sync_height"] = max(
                    self.cache_data["global_sync_height"], 
                    block_height
                )
            
            if updated:
                self._save_cache()
            
            return updated
            
        except Exception as e:
            print(f"❌ Error updating cache for new block {block_hash}: {e}")
            return False
    
    def sync_address_to_current(self, address: str) -> bool:
        """
        Sync a specific address to current blockchain height.
        For small gaps, uses block scanning. For large gaps, uses transaction history.
        
        Args:
            address: Address to sync
            
        Returns:
            True if sync completed successfully
        """
        current_height = self.get_current_block_height()
        if current_height is None:
            return False
        
        with self.cache_lock:
            addr_data = self.cache_data["addresses"].get(address)
            if not addr_data:
                print(f"⚠️ Address {self._crop_address_for_log(address)} not in cache, cannot sync")
                return False
            
            synced_height = addr_data.get("synced_height", 0)
            
            if synced_height >= current_height:
                print(f"✅ Address {self._crop_address_for_log(address)} already synced to height {synced_height}")
                return True
            
            blocks_to_sync = current_height - synced_height
            print(f"🔄 Syncing address {self._crop_address_for_log(address)} from height {synced_height + 1} to {current_height} ({blocks_to_sync} blocks)")
            
            new_coinbase_count = 0
            
            # Use different strategies based on gap size
            # Transaction history is much more efficient for gaps larger than 50 blocks
            if blocks_to_sync <= 50:
                # Small gap: use block scanning (more efficient for recent blocks)
                print(f"📊 Using block scanning for {blocks_to_sync} blocks")
                new_coinbase_count = self._scan_blocks_for_address(address, synced_height + 1, current_height)
            else:
                # Large gap: use transaction history and filter by height (much faster)
                print(f"📊 Using transaction history scanning for {blocks_to_sync} blocks")
                new_coinbase_count = self._scan_address_history(address, synced_height + 1, current_height)
            
            # Update cache
            addr_data["total_coinbase_count"] += new_coinbase_count
            addr_data["synced_height"] = current_height
            addr_data["last_updated"] = time.time()
            
            self._save_cache()
            
            print(f"✅ Address {self._crop_address_for_log(address)} synced: +{new_coinbase_count} new coinbase transactions")
            return True
    
    def _scan_blocks_for_address(self, address: str, start_height: int, end_height: int) -> int:
        """
        Scan specific block range for coinbase transactions to an address.
        Optimized with batch processing and progress reporting.
        
        Args:
            address: Bitcoin address to scan for
            start_height: Starting block height
            end_height: Ending block height
            
        Returns:
            Number of coinbase transactions found
        """
        coinbase_count = 0
        base_url = self._get_mempool_base_url()
        verify_ssl = self._get_mempool_verify_ssl()
        total_blocks = end_height - start_height + 1
        batch_size = 10  # Process in smaller batches for better progress reporting
        
        print(f"🔍 Block scanning {total_blocks} blocks for address {self._crop_address_for_log(address)}")
        
        start_time = time.time()
        processed_blocks = 0
        
        for batch_start in range(start_height, end_height + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, end_height)
            
            # Progress reporting
            progress_pct = (processed_blocks / total_blocks) * 100
            elapsed_time = time.time() - start_time
            if processed_blocks > 0:
                eta = (elapsed_time / processed_blocks) * (total_blocks - processed_blocks)
                print(f"📊 Scanning progress: {processed_blocks}/{total_blocks} blocks ({progress_pct:.1f}%) - ETA: {eta:.1f}s")
            
            # Process batch
            for height in range(batch_start, batch_end + 1):
                try:
                    # Get block hash
                    block_response = requests.get(f"{base_url}/block-height/{height}", timeout=10, verify=verify_ssl)
                    if not block_response.ok:
                        processed_blocks += 1
                        continue
                    
                    block_hash = block_response.text.strip()
                    
                    # Get coinbase transaction directly using block info endpoint (more efficient)
                    block_response = requests.get(f"{base_url}/block/{block_hash}", timeout=10, verify=verify_ssl)
                    if not block_response.ok:
                        processed_blocks += 1
                        continue
                    
                    block_data = block_response.json()
                    
                    # Get the first transaction (coinbase) directly from block data
                    if 'tx' in block_data and len(block_data['tx']) > 0:
                        coinbase_tx = block_data['tx'][0]
                        
                        # Check if any output goes to our address
                        for vout in coinbase_tx.get('vout', []):
                            if vout.get('scriptpubkey_address') == address:
                                coinbase_count += 1
                                print(f"🎯 Found coinbase transaction at height {height}: {coinbase_tx.get('txid', 'unknown')}")
                                
                                # Update latest block found
                                with self.cache_lock:
                                    addr_data = self.cache_data["addresses"].get(address, {})
                                    if addr_data.get("latest_block_found") is None or height > addr_data.get("latest_block_found", 0):
                                        addr_data["latest_block_found"] = height
                                break
                    
                    processed_blocks += 1
                    
                    # Reduced delay (was 0.01s, now 0.005s)
                    time.sleep(0.005)
                    
                except Exception as e:
                    print(f"⚠️ Error scanning block {height}: {e}")
                    processed_blocks += 1
                    continue
        
        # Final progress report
        elapsed_time = time.time() - start_time
        print(f"✅ Block scanning complete: {total_blocks} blocks in {elapsed_time:.2f}s ({total_blocks/elapsed_time:.1f} blocks/sec)")
        
        return coinbase_count
    
    def sync_all_addresses(self) -> bool:
        """
        Sync all monitored addresses to current blockchain height.
        This is used for recovery when the system was down.
        
        Returns:
            True if all addresses synced successfully
        """
        current_height = self.get_current_block_height()
        if current_height is None:
            return False
        
        with self.cache_lock:
            addresses = list(self.cache_data["addresses"].keys())
        
        success_count = 0
        for address in addresses:
            if self.sync_address_to_current(address):
                success_count += 1
        
        # Update global sync height to current blockchain height after sync
        with self.cache_lock:
            self.cache_data["global_sync_height"] = current_height
            self._save_cache()
        
        print(f"📊 Sync complete: {success_count}/{len(addresses)} addresses synced successfully")
        return success_count == len(addresses)
    
    def remove_address(self, address: str) -> bool:
        """
        Remove an address from monitoring.
        
        Args:
            address: Address to remove
            
        Returns:
            True if address was removed
        """
        with self.cache_lock:
            if address in self.cache_data["addresses"]:
                del self.cache_data["addresses"][address]
                self._save_cache()
                print(f"🗑️ Removed address {address} from block reward cache")
                return True
            else:
                print(f"⚠️ Address {address} not found in cache")
                return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.cache_lock:
            total_coinbase = sum(
                addr_data.get("total_coinbase_count", 0) 
                for addr_data in self.cache_data["addresses"].values()
            )
            
            return {
                "total_addresses": len(self.cache_data["addresses"]),
                "total_coinbase_transactions": total_coinbase,
                "global_sync_height": self.cache_data["global_sync_height"],
                "last_updated": self.cache_data.get("last_updated", 0),
                "cache_file_size": os.path.getsize(self.cache_file) if os.path.exists(self.cache_file) else 0
            }
    
    def update_monitored_addresses(self, addresses: List[str]) -> bool:
        """
        Update the list of monitored addresses based on configuration.
        Adds new addresses and removes old ones.
        
        Args:
            addresses: List of addresses to monitor
            
        Returns:
            True if update completed successfully
        """
        with self.cache_lock:
            current_addresses = set(self.cache_data["addresses"].keys())
            new_addresses = set(addresses)
            
            # Remove addresses no longer in config
            to_remove = current_addresses - new_addresses
            for address in to_remove:
                self.remove_address(address)
            
            # Add new addresses
            to_add = new_addresses - current_addresses
            for address in to_add:
                self.add_new_address(address)
            
            return True
