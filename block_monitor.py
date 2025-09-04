"""
Block Reward Monitor Module

Monitors Bitcoin addresses for coinbase transactions (block rewards) and maintains
a count of valid blocks found. This integrates with the new BlockRewardCache system
for efficient caching and incremental updates.

"""

import json
import os
import requests
import threading
import time
from typing import List, Set, Dict, Any
import urllib3

# Import the new caching system
from block_reward_cache import BlockRewardCache

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Handle optional websocket dependency
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ websocket-client not installed. Block monitoring will work but without real-time updates.")
    print("📦 To install: pip install websocket-client")


class BlockRewardMonitor:
    """Monitors BTC addresses for block rewards and tracks valid blocks count."""
    
    def __init__(self, config_manager=None):
        """
        Initialize block reward monitor with new caching system.
        
        Args:
            config_manager: ConfigManager instance for getting monitored addresses
        """
        self.config_manager = config_manager
        self.valid_blocks_file = "valid_blocks_count.json"  # Legacy file for compatibility
        self.monitored_addresses = set()
        self.valid_blocks_count = 0
        self.blocks_by_address = {}  # Track found blocks per address
        self.ws = None
        self.monitoring_thread = None
        self.running = False
        
        # Initialize new caching system
        self.cache = BlockRewardCache(config_manager)
        
        # Load existing count and migrate to new system if needed
        self._load_and_migrate_legacy_data()
        
        # Update addresses from config
        self._update_monitored_addresses()
        # Load existing count and migrate to new system if needed
        self._load_and_migrate_legacy_data()
        
        # Update addresses from config
        self._update_monitored_addresses()
        
        # Log mempool configuration
        base_url = self._get_mempool_base_url()
        ws_url = self._get_mempool_ws_url()
        print(f"📡 Block monitor using mempool API: {base_url}")
        print(f"🔗 Block monitor WebSocket: {ws_url}")
    
    def _load_and_migrate_legacy_data(self):
        """Load legacy data and migrate to new caching system if needed."""
        try:
            if os.path.exists(self.valid_blocks_file):
                with open(self.valid_blocks_file, 'r') as f:
                    data = json.load(f)
                    self.valid_blocks_count = data.get("valid_blocks", 0)
                    self.blocks_by_address = data.get("blocks_by_address", {})
                    
                    print(f"📊 Loaded legacy valid blocks count: {self.valid_blocks_count}")
                    if self.blocks_by_address:
                        # Crop addresses for privacy in logs
                        cropped_blocks = {self.cache._crop_address_for_log(addr): count 
                                         for addr, count in self.blocks_by_address.items()}
                        print(f"📍 Legacy per-address blocks: {cropped_blocks}")
                    
                    # Note: Legacy data is kept for backward compatibility
                    # New system uses BlockRewardCache for more detailed tracking
                    
        except Exception as e:
            print(f"⚠️ Error loading legacy valid blocks count: {e}")
            self.valid_blocks_count = 0
            self.blocks_by_address = {}
    
    def _get_mempool_base_url(self) -> str:
        """Get mempool API base URL from configuration."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            mempool_ip = config.get("mempool_ip")
            mempool_rest_port = config.get("mempool_rest_port")
            
            if not mempool_ip or not mempool_rest_port:
                raise ValueError("❌ Mempool configuration missing. Please configure mempool_ip and mempool_rest_port.")
            
            return f"https://{mempool_ip}:{mempool_rest_port}/api"
        else:
            raise ValueError("❌ No configuration manager available. Cannot connect to mempool without configuration.")
    
    def _get_mempool_ws_url(self) -> str:
        """Get mempool WebSocket URL from configuration."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            mempool_ip = config.get("mempool_ip")
            mempool_ws_port = config.get("mempool_ws_port")
            
            if not mempool_ip or not mempool_ws_port:
                raise ValueError("❌ Mempool WebSocket configuration missing. Please configure mempool_ip and mempool_ws_port.")
            
            return f"ws://{mempool_ip}:{mempool_ws_port}/api/v1/ws"
        else:
            raise ValueError("❌ No configuration manager available. Cannot connect to mempool WebSocket without configuration.")
    
    def _load_valid_blocks_count(self):
        """Load valid blocks count from file."""
        try:
            if os.path.exists(self.valid_blocks_file):
                with open(self.valid_blocks_file, 'r') as f:
                    data = json.load(f)
                    self.valid_blocks_count = data.get("valid_blocks", 0)
                    self.blocks_by_address = data.get("blocks_by_address", {})
                    print(f"📊 Loaded valid blocks count: {self.valid_blocks_count}")
                    if self.blocks_by_address:
                        # Crop addresses for privacy in logs
                        cropped_blocks = {self.cache._crop_address_for_log(addr): count 
                                         for addr, count in self.blocks_by_address.items()}
                        print(f"📍 Per-address blocks: {cropped_blocks}")
        except Exception as e:
            print(f"⚠️ Error loading valid blocks count: {e}")
            self.valid_blocks_count = 0
            self.blocks_by_address = {}
    
    def _save_valid_blocks_count(self):
        """Save valid blocks count to file."""
        try:
            data = {
                "valid_blocks": self.valid_blocks_count,
                "blocks_by_address": self.blocks_by_address,
                "last_updated": time.time(),
                "monitored_addresses": list(self.monitored_addresses)
            }
            with open(self.valid_blocks_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving valid blocks count: {e}")
    
    def _update_monitored_addresses(self):
        """Update monitored addresses from config and sync with cache system."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            
            # Get addresses from block reward monitoring table
            monitored_addresses = []
            
            # New table format
            block_reward_table = config.get("block_reward_addresses_table", [])
            for entry in block_reward_table:
                if isinstance(entry, dict) and entry.get("address"):
                    monitored_addresses.append(entry["address"])
            
            # Remove duplicates
            monitored_addresses = list(set(monitored_addresses))
            
            self.monitored_addresses = set(monitored_addresses)
            print(f"📍 Monitoring {len(self.monitored_addresses)} addresses for block rewards")
            
            # Update cache system with new addresses
            if monitored_addresses:
                print(f"🔄 Updating cache system with {len(monitored_addresses)} addresses")
                self.cache.update_monitored_addresses(monitored_addresses)
    
    def get_valid_blocks_count(self) -> int:
        """Get current valid blocks count (legacy method for compatibility)."""
        return self.valid_blocks_count
    
    def get_coinbase_count(self, address: str) -> int:
        """
        Get coinbase transaction count for a specific address using the cache system.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            Number of coinbase transactions found for this address
        """
        return self.cache.get_coinbase_count(address)
    
    def increment_valid_blocks(self, block_hash: str, txid: str, address: str, value_sats: int):
        """
        Increment valid blocks count and log the finding.
        
        Args:
            block_hash: Hash of the block containing the reward
            txid: Transaction ID of the coinbase transaction
            address: Address that received the reward
            value_sats: Value in satoshis
        """
        # Legacy tracking for backward compatibility
        self.valid_blocks_count += 1
        
        # Track per-address count (legacy)
        if address in self.blocks_by_address:
            self.blocks_by_address[address] += 1
        else:
            self.blocks_by_address[address] = 1
        
        # Save legacy data
        self._save_valid_blocks_count()
        
        # Extract block height from block hash if possible
        block_height = None
        try:
            base_url = self._get_mempool_base_url()
            response = requests.get(f"{base_url}/block/{block_hash}", timeout=5, verify=False)
            if response.ok:
                block_data = response.json()
                block_height = block_data.get('height')
        except Exception as e:
            print(f"⚠️ Could not get block height for {block_hash}: {e}")
        
        # Update new cache system
        if block_height:
            self.cache.update_for_new_block(block_hash, block_height)
        
        btc_value = value_sats / 1e8
        cropped_address = self.cache._crop_address_for_log(address)
        print(f"🎯 BLOCK REWARD FOUND! Block: {block_hash[:16]}... -> {cropped_address}: {btc_value:.8f} BTC")
        print(f"📊 Total valid blocks found: {self.valid_blocks_count}")
        print(f"📍 Blocks for {cropped_address}: {self.blocks_by_address[address]}")
        if block_height:
            print(f"🏗️ Block height: {block_height}")
    
    def sync_cache_to_current(self) -> bool:
        """
        Sync all monitored addresses in cache to current blockchain height.
        This should be called on startup to catch up on any missed blocks.
        
        Returns:
            True if sync completed successfully
        """
        print(f"🔄 Starting cache sync to current blockchain height...")
        return self.cache.sync_all_addresses()
    
    def check_coinbase_for_addresses(self, tx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check if coinbase transaction pays to any monitored addresses.
        
        Args:
            tx: Transaction data from mempool API
            
        Returns:
            List of found payouts
        """
        found = []
        for vout in tx.get('vout', []):
            addr = vout.get('scriptpubkey_address')
            if addr in self.monitored_addresses:
                found.append({
                    'address': addr,
                    'value_sats': vout['value'],
                    'txid': tx['txid'],
                    'block_height': tx.get('status', {}).get('block_height')
                })
        return found
    
    def fetch_coinbase_tx(self, block_hash: str) -> Dict[str, Any]:
        """Fetch and return the coinbase transaction details from a block."""
        try:
            BASE_URL = self._get_mempool_base_url()
            
            # Try different endpoints - some mempool instances have different API structures
            endpoints_to_try = [
                f"{BASE_URL}/block/{block_hash}/txids",
                f"{BASE_URL}/block/{block_hash}/transactions",
                f"{BASE_URL}/block/{block_hash}/txs"
            ]
            
            txids = None
            for endpoint in endpoints_to_try:
                try:
                    print(f"🔍 Trying endpoint: {endpoint}")
                    # Use verify=False for self-signed HTTPS certificates
                    txids_resp = requests.get(endpoint, timeout=10, verify=False)
                    txids_resp.raise_for_status()
                    txids = txids_resp.json()
                    print(f"✅ Successfully got txids from: {endpoint}")
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        print(f"⚠️ Endpoint not found: {endpoint}")
                        continue
                    else:
                        print(f"⚠️ HTTP error for {endpoint}: {e}")
                        continue
                except Exception as e:
                    print(f"⚠️ Error with endpoint {endpoint}: {e}")
                    continue
            
            if not txids:
                print(f"⚠️ Could not fetch transaction IDs for block {block_hash} from any endpoint")
                return {}
            
            # Handle different response formats
            if isinstance(txids, list):
                transaction_ids = txids
            elif isinstance(txids, dict) and 'txids' in txids:
                transaction_ids = txids['txids']
            elif isinstance(txids, dict) and 'transactions' in txids:
                transaction_ids = txids['transactions']
            else:
                print(f"⚠️ Unexpected txids format: {type(txids)}")
                return {}
            
            if not transaction_ids:
                print(f"⚠️ No transactions found in block {block_hash}")
                return {}
            
            # First transaction is always coinbase
            coinbase_txid = transaction_ids[0]
            
            # Get coinbase transaction details
            tx_resp = requests.get(f"{BASE_URL}/tx/{coinbase_txid}", timeout=10, verify=False)
            tx_resp.raise_for_status()
            
            return tx_resp.json()
            
        except Exception as e:
            print(f"⚠️ Error fetching coinbase transaction for block {block_hash}: {e}")
            return {}
    
    def start_monitoring(self):
        """Start WebSocket monitoring for new blocks."""
        if not WEBSOCKET_AVAILABLE:
            print("⚠️ WebSocket monitoring unavailable (websocket-client not installed)")
            print("📊 Block rewards will still be counted manually, but not in real-time")
            return
            
        if self.running:
            print("📡 Block monitoring already running")
            return
            
        if not self.monitored_addresses:
            print("⚠️ No addresses to monitor for block rewards")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitor_blocks, daemon=True)
        self.monitoring_thread.start()
        print(f"📡 Started block reward monitoring for {len(self.monitored_addresses)} addresses")
    
    def stop_monitoring(self):
        """Stop WebSocket monitoring."""
        self.running = False
        if self.ws:
            self.ws.close()
        print("🛑 Stopped block reward monitoring")
    
    def _monitor_blocks(self):
        """WebSocket monitoring loop."""
        if not WEBSOCKET_AVAILABLE:
            return
            
        while self.running:
            try:
                ws_url = self._get_mempool_ws_url()
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception as e:
                print(f"⚠️ WebSocket error: {e}")
                if self.running:
                    print("🔄 Reconnecting in 30 seconds...")
                    time.sleep(30)
    
    def _on_open(self, ws):
        """WebSocket connection opened."""
        print("📡 WebSocket connected, subscribing to blocks...")
        ws.send(json.dumps({"action": "want", "data": ["blocks"]}))
    
    def _on_message(self, ws, message):
        """Handle WebSocket message."""
        try:
            data = json.loads(message)
            if data.get("block"):
                block_hash = data["block"]["id"]
                print(f"🆕 New block: {block_hash[:16]}...")
                
                # Give the mempool a moment to process the new block before fetching transactions
                time.sleep(2)
                
                # Fetch coinbase transaction with retry logic
                coinbase_tx = self._fetch_coinbase_with_retry(block_hash)
                if coinbase_tx:
                    # Check for payouts to monitored addresses
                    payouts = self.check_coinbase_for_addresses(coinbase_tx)
                    for payout in payouts:
                        self.increment_valid_blocks(
                            block_hash, 
                            payout['txid'], 
                            payout['address'], 
                            payout['value_sats']
                        )
        except Exception as e:
            print(f"⚠️ Error processing WebSocket message: {e}")
    
    def _fetch_coinbase_with_retry(self, block_hash: str, max_retries: int = 3) -> Dict[str, Any]:
        """Fetch coinbase transaction with retry logic for newly mined blocks."""
        for attempt in range(max_retries):
            try:
                coinbase_tx = self.fetch_coinbase_tx(block_hash)
                if coinbase_tx:
                    return coinbase_tx
                else:
                    print(f"🔄 Attempt {attempt + 1}/{max_retries}: Block {block_hash[:16]}... not ready yet, waiting...")
                    time.sleep(5)  # Wait longer between retries
            except Exception as e:
                print(f"🔄 Attempt {attempt + 1}/{max_retries} failed: {e}")
                time.sleep(5)
        
        print(f"⚠️ Failed to fetch coinbase transaction for block {block_hash[:16]}... after {max_retries} attempts")
        return {}
    
    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        print(f"⚠️ WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        print("📡 WebSocket connection closed")
        if self.running:
            print("🔄 Will attempt to reconnect...")


# Global instance for use in the main application
block_monitor = None

def initialize_block_monitor(config_manager):
    """Initialize the global block monitor instance."""
    global block_monitor
    block_monitor = BlockRewardMonitor(config_manager)
    return block_monitor

def get_block_monitor():
    """Get the global block monitor instance."""
    return block_monitor
