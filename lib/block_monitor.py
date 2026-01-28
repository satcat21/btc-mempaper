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
from lib.block_reward_cache import BlockRewardCache

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
    
    def __init__(self, config_manager=None, image_generation_callback=None, new_block_notification_callback=None):
        """
        Initialize block reward monitor with new caching system.
        
        Args:
            config_manager: ConfigManager instance for getting monitored addresses
            image_generation_callback: Optional callback to trigger image generation on new blocks
            new_block_notification_callback: Optional callback to notify web clients about new blocks
        """
        self.config_manager = config_manager
        self.image_generation_callback = image_generation_callback
        self.new_block_notification_callback = new_block_notification_callback
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
        
        # Update addresses from config (this will also clean up legacy data)
        self._update_monitored_addresses()
        
        # Debug: Check if image generation callback is set
        if not self.image_generation_callback:
        # if self.image_generation_callback:
        #    print("✅ Block monitor: Image generation callback is SET - will trigger image updates on new blocks")
        # else:
            print("⚠️ Block monitor: No image generation callback - only monitoring block rewards")
        
        # Log mempool configuration
        base_url = self._get_mempool_base_url()
        ws_url = self._get_mempool_ws_url()
        # API endpoint already logged in mempaper_app._init_api_clients
        # print(f"🌐 Block monitor using mempool API: {base_url}")
        print(f"📶 Block monitor WebSocket: {ws_url}")
    
    def _load_and_migrate_legacy_data(self):
        """Load legacy data and migrate to new caching system if needed."""
        try:
            if os.path.exists(self.valid_blocks_file):
                with open(self.valid_blocks_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.valid_blocks_count = data.get("valid_blocks", 0)
                        self.blocks_by_address = data.get("blocks_by_address", {})
                    else:
                        print(f"⚠️ Unexpected legacy data type: {type(data)} value={data}")
                        self.valid_blocks_count = 0
                        self.blocks_by_address = {}
                    
                    print(f"💾 Loaded legacy valid blocks count: {self.valid_blocks_count}")
                    if self.blocks_by_address:
                        # Crop addresses for privacy in logs
                        cropped_blocks = {self.cache._crop_address_for_log(addr): count 
                                         for addr, count in self.blocks_by_address.items()}
                        print(f"👁️ Legacy per-address blocks: {cropped_blocks}")
                    
                    # Note: Legacy data is kept for backward compatibility
                    # New system uses BlockRewardCache for more detailed tracking
                    
        except Exception as e:
            print(f"⚠️ Error loading legacy valid blocks count: {e}")
            self.valid_blocks_count = 0
            self.blocks_by_address = {}
    
    def _get_mempool_base_url(self) -> str:
        """Get mempool API base URL from configuration with domain and HTTPS support."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            mempool_host = config.get("mempool_host", "127.0.0.1") if isinstance(config, dict) else "127.0.0.1"
            mempool_rest_port = config.get("mempool_rest_port") if isinstance(config, dict) else None
            mempool_use_https = config.get("mempool_use_https", False) if isinstance(config, dict) else False
            
            if not mempool_rest_port:
                raise ValueError("❌ Mempool configuration missing. Please configure mempool_rest_port.")
            
            if not mempool_host:
                raise ValueError("❌ Mempool configuration missing. Please configure mempool_host.")
            
            # Build URL with proper protocol
            protocol = "https" if mempool_use_https else "http"
            
            # Check if host looks like a domain (contains dots but not just IP)
            # Skip port for domains using standard ports (80/443)
            is_domain = "." in mempool_host and not mempool_host.replace(".", "").isdigit()
            
            if is_domain:
                if (mempool_use_https and mempool_rest_port in ["443", "80"]) or \
                   (not mempool_use_https and mempool_rest_port in ["80", "443"]):
                    return f"{protocol}://{mempool_host}/api"
                else:
                    return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
            else:
                # Always include port for IP addresses
                return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
        else:
            raise ValueError("❌ No configuration manager available. Cannot connect to mempool without configuration.")
    
    def _get_mempool_ws_url(self) -> str:
        """Get mempool WebSocket URL from configuration with WSS support."""
        if self.config_manager:
            config = self.config_manager.get_current_config()
            mempool_host = config.get("mempool_host", "127.0.0.1") if isinstance(config, dict) else "127.0.0.1"
            mempool_ws_port = config.get("mempool_ws_port") if isinstance(config, dict) else None
            mempool_ws_path = config.get("mempool_ws_path", "/api/v1/ws") if isinstance(config, dict) else "/api/v1/ws"
            mempool_use_https = config.get("mempool_use_https", False) if isinstance(config, dict) else False
            
            if not mempool_ws_port:
                raise ValueError("❌ Mempool WebSocket configuration missing. Please configure mempool_ws_port.")
            
            if not mempool_host:
                raise ValueError("❌ Mempool configuration missing. Please configure mempool_host.")
            
            # Build WebSocket URL with proper protocol
            protocol = "wss" if mempool_use_https else "ws"
            
            # Normalize port to string for comparison
            port_str = str(mempool_ws_port) if mempool_ws_port is not None else ""
            
            # Always omit standard ports to avoid 404s with some reverse proxies/load balancers
            # This applies to both domains and IP addresses
            is_standard_port = (mempool_use_https and port_str == "443") or (not mempool_use_https and port_str == "80")
            
            if is_standard_port:
                return f"{protocol}://{mempool_host}{mempool_ws_path}"
            else:
                return f"{protocol}://{mempool_host}:{mempool_ws_port}{mempool_ws_path}"
        else:
            raise ValueError("❌ No configuration manager available. Cannot connect to mempool WebSocket without configuration.")
    
    def _load_valid_blocks_count(self):
        """Load valid blocks count from file."""
        try:
            if os.path.exists(self.valid_blocks_file):
                with open(self.valid_blocks_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.valid_blocks_count = data.get("valid_blocks", 0)
                        self.blocks_by_address = data.get("blocks_by_address", {})
                    else:
                        print(f"⚠️ Unexpected valid blocks data type: {type(data)} value={data}")
                        self.valid_blocks_count = 0
                        self.blocks_by_address = {}
                    print(f"💾 Loaded valid blocks count: {self.valid_blocks_count}")
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
            block_reward_table = config.get("block_reward_addresses_table", []) if isinstance(config, dict) else []
            for entry in block_reward_table:
                if isinstance(entry, dict) and "address" in entry:
                    monitored_addresses.append(entry["address"])
            
            # Remove duplicates
            monitored_addresses = list(set(monitored_addresses))
            
            self.monitored_addresses = set(monitored_addresses)
            if len(self.monitored_addresses) > 0:
                print(f"👁️ Monitoring {len(self.monitored_addresses)} addresses for block rewards")
            
            # Clean up legacy blocks_by_address data for addresses no longer monitored
            if hasattr(self, 'blocks_by_address') and self.blocks_by_address:
                current_legacy_addresses = set(self.blocks_by_address.keys())
                addresses_to_remove = current_legacy_addresses - self.monitored_addresses
                
                if addresses_to_remove:
                    print(f"💾 Cleaning up legacy data for {len(addresses_to_remove)} removed addresses")
                    
                    # Calculate total blocks to subtract before removing addresses
                    removed_count = sum(self.blocks_by_address.get(addr, 0) for addr in addresses_to_remove)
                    
                    for addr in addresses_to_remove:
                        # Privacy log the removal
                        cropped_addr = self.cache._crop_address_for_log(addr) if hasattr(self.cache, '_crop_address_for_log') else addr[:6] + '...' + addr[-6:]
                        print(f"💾 Removing legacy data for address: {cropped_addr}")
                        del self.blocks_by_address[addr]
                    
                    # Update valid_blocks_count by subtracting removed address counts
                    self.valid_blocks_count = max(0, self.valid_blocks_count - removed_count)
                    
                    # Save the cleaned legacy data
                    self._save_valid_blocks_count()
            
            # Update cache system with new addresses
            if monitored_addresses:
                print(f"💾 Updating cache system with {len(monitored_addresses)} addresses")
                self.cache.update_monitored_addresses(monitored_addresses)
            else:
                # Clean up cache system if no addresses to monitor (silent when wallet monitoring disabled)
                self.cache.update_monitored_addresses([])
    
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
                if isinstance(block_data, dict):
                    block_height = block_data.get('height')
                else:
                    print(f"⚠️ Unexpected block_data type: {type(block_data)} value={block_data}")
                    block_height = None
        except Exception as e:
            print(f"⚠️ Could not get block height for {block_hash}: {e}")
        
        # Update new cache system
        if block_height:
            self.cache.update_for_new_block(block_hash, block_height)
        
        btc_value = value_sats / 1e8
        cropped_address = self.cache._crop_address_for_log(address)
        print(f"👁️ BLOCK REWARD FOUND! Block: {block_hash[:16]}... -> {cropped_address}: {btc_value:.8f} BTC")
        print(f"👁️ Total valid blocks found: {self.valid_blocks_count}")
        print(f"👁️ Blocks for {cropped_address}: {self.blocks_by_address[address]}")
        if block_height:
            print(f"👁️ Block height: {block_height}")
    
    def sync_cache_to_current(self) -> bool:
        """
        Sync all monitored addresses in cache to current blockchain height.
        This should be called on startup to catch up on any missed blocks.
        
        Returns:
            True if sync completed successfully
        """
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
        vout_list = tx.get('vout', []) if isinstance(tx, dict) else []
        for vout in vout_list:
            addr = vout.get('scriptpubkey_address') if isinstance(vout, dict) else None
            if addr in self.monitored_addresses:
                found.append({
                    'address': addr,
                    'value_sats': vout['value'],
                    'txid': tx['txid'],
                    'block_height': tx.get('status', {}).get('block_height') if isinstance(tx, dict) and isinstance(tx.get('status', {}), dict) else None
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
                    print(f"👁️ Trying endpoint: {endpoint}")
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
        """Start WebSocket monitoring for new blocks (always connects, even if no reward addresses)."""
        if not WEBSOCKET_AVAILABLE:
            print("⚠️ WebSocket monitoring unavailable (websocket-client not installed)")
            print("💾 Block rewards will still be counted manually, but not in real-time")
            return

        if self.running:
            print("⚙️ Block monitoring already running")
            return

        # Always connect to WebSocket for block notifications
        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitor_blocks, daemon=True)
        self.monitoring_thread.start()
        print(f"📶 Block monitoring started (WebSocket will notify on every new block)")

        # Startup catch-up: check current block height and process missed blocks
        try:
            base_url = self._get_mempool_base_url()
            resp = requests.get(f"{base_url}/blocks/tip", timeout=10, verify=False)
            if resp.ok:
                tip_data = resp.json()
                current_height = tip_data.get("height") if isinstance(tip_data, dict) else None
                last_cached_height = self.cache.get_last_cached_block_height() if hasattr(self.cache, "get_last_cached_block_height") else None
                if last_cached_height and current_height and current_height > last_cached_height:
                    print(f"⚙️ Missed blocks detected: {last_cached_height} → {current_height}. Generating images for missed blocks...")
                    for h in range(last_cached_height + 1, current_height + 1):
                        # Fetch block hash for height
                        block_resp = requests.get(f"{base_url}/block-height/{h}", timeout=10, verify=False)
                        if block_resp.ok:
                            block_json = block_resp.json()
                            block_hash = None
                            # Fix: Handle both dict and list responses robustly
                            if isinstance(block_json, dict):
                                block_hash = block_json.get("blockHash")
                            elif isinstance(block_json, list):
                                # Some APIs return a list of dicts
                                for item in block_json:
                                    if isinstance(item, dict) and "blockHash" in item:
                                        block_hash = item["blockHash"]
                                        break
                                if not block_hash:
                                    print(f"⚠️ Unexpected block_json list format for height {h}: {block_json}")
                            else:
                                print(f"⚠️ Unexpected block_json type for height {h}: {type(block_json)}")
                            if block_hash and self.image_generation_callback:
                                print(f"⚙️ Generating image for missed block {h}")
                                try:
                                    self.image_generation_callback(h, block_hash)
                                except Exception as e:
                                    print(f"❌ Failed to generate image for missed block {h}: {e}")
                            elif not block_hash:
                                print(f"⚠️ Could not extract block hash for missed block {h} (block_json={block_json})")
                        else:
                            print(f"⚠️ Could not fetch block hash for height {h}")
                else:
                    print("✅ No missed blocks detected at startup.")
        except Exception as e:
            print(f"⚠️ Error during startup catch-up for missed blocks: {e}")
    
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
            
        heartbeat_count = 0
        while self.running:
            try:
                if not self.config_manager:
                     # This should not happen if initialized correctly
                    mempool_verify_ssl = True
                else:
                    config = self.config_manager.get_current_config()
                    mempool_verify_ssl = config.get("mempool_verify_ssl", True)

                ws_url = self._get_mempool_ws_url()
                # print(f"🟢 [HEARTBEAT] Block monitor thread alive, connecting to WebSocket: {ws_url} (count={heartbeat_count})")
                heartbeat_count += 1
                
                # Custom headers to ensure proper handshake
                # headers = {
                #     "User-Agent": "Mempaper/2.0",
                #     "Upgrade": "websocket",
                #     "Connection": "Upgrade"
                # }

                self.ws = websocket.WebSocketApp(
                    ws_url,
                    # header=headers,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                # Configure SSL with explicit SNI support
                import ssl
                if mempool_verify_ssl:
                    # Explicitly set server_hostname for correct SNI (Server Name Indication)
                    # This fixes 404s on servers hosting multiple vhosts or behind reverse proxies
                    # that rely on SNI to route traffic to the correct backend.
                    # We also use the host from config (mempool_host) not the URL which might omit port.
                    mempool_host = self.config_manager.get_current_config().get("mempool_host", "")
                    sslopt = {
                        "cert_reqs": ssl.CERT_REQUIRED, 
                        "check_hostname": True, 
                        "server_hostname": mempool_host
                    }
                else:
                     sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
                
                self.ws.run_forever(sslopt=sslopt)
            except Exception as e:
                print(f"⚠️ WebSocket error: {e}")
                if self.running:
                    print("⚙️ Reconnecting in 30 seconds...")
                    time.sleep(30)
    
    def _on_open(self, ws):
        """WebSocket connection opened."""
        # Connection already logged by websocket_client on_open
        # print("📶 WebSocket connected, subscribing to blocks...")
        ws.send(json.dumps({"action": "want", "data": ["blocks"]}))
    
    def _on_message(self, ws, message):
        """Handle WebSocket message."""
        # print(f"🟢 [HEARTBEAT] WebSocket message received at {time.strftime('%H:%M:%S')}")
        try:
            data = json.loads(message)
            if data.get("block"):
                block_hash = data["block"]["id"]
                block_height = data["block"].get("height")
                # print(f"🟢 [HEARTBEAT] Block event received: block_height={block_height}, block_hash={block_hash}")
                # Format block height with thousand separators for better readability
                if block_height:
                    formatted_height = f"{block_height:,}".replace(",", ".")
                    print(f"👁️ New block: {formatted_height}")
                else:
                    print(f"👁️ New block: {block_hash[:16]}... (height unknown)")
                # ...existing code...
                if self.new_block_notification_callback and block_height:
                    print(f"📶 Sending new block notification to web clients for block {block_height}")
                    try:
                        self.new_block_notification_callback(block_height, block_hash)
                    except Exception as e:
                        print(f"⚠️ Failed to send block notification: {e}")
                if self.image_generation_callback and block_height:
                    print(f"⚙️ Triggering image generation for new block {block_height}")
                    try:
                        self.image_generation_callback(block_height, block_hash)
                        print(f"✅ Image generation triggered successfully for block {block_height}")
                    except Exception as e:
                        print(f"❌ Failed to trigger image generation for block {block_height}: {e}")
                        import traceback
                        traceback.print_exc()
                time.sleep(2)
                coinbase_tx = self._fetch_coinbase_with_retry(block_hash)
                if coinbase_tx:
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
            import traceback
            traceback.print_exc()
    
    def _fetch_coinbase_with_retry(self, block_hash: str, max_retries: int = 3) -> Dict[str, Any]:
        """Fetch coinbase transaction with retry logic for newly mined blocks."""
        for attempt in range(max_retries):
            try:
                coinbase_tx = self.fetch_coinbase_tx(block_hash)
                if coinbase_tx:
                    return coinbase_tx
                else:
                    print(f"⚙️ Attempt {attempt + 1}/{max_retries}: Block {block_hash[:16]}... not ready yet, waiting...")
                    time.sleep(5)  # Wait longer between retries
            except Exception as e:
                print(f"⚙️ Attempt {attempt + 1}/{max_retries} failed: {e}")
                time.sleep(5)
        
        print(f"⚠️ Failed to fetch coinbase transaction for block {block_hash[:16]}... after {max_retries} attempts")
        return {}
    
    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        print(f"⚠️ WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        print("📶 WebSocket connection closed")
        if self.running:
            print("⚙️ Will attempt to reconnect...")


# Global instance for use in the main application
block_monitor = None

def initialize_block_monitor(config_manager, image_generation_callback=None, new_block_notification_callback=None):
    """Initialize the global block monitor instance."""
    global block_monitor
    block_monitor = BlockRewardMonitor(config_manager, image_generation_callback, new_block_notification_callback)
    return block_monitor

def get_block_monitor():
    """Get the global block monitor instance."""
    return block_monitor
