"""Wallet balances, block-reward lookups and Bitaxe miner stats.
"""

from flask import jsonify
from flask import request
from managers.auth_manager import require_auth
import os
import traceback

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the wallet routes."""
    from mempaper_app import _safe_error

    @self.app.route('/api/wallet_balance', methods=['POST'])
    @require_auth(self.auth_manager)
    def refresh_wallet_balances():
        """Refresh wallet balances for the provided addresses."""
        try:
            request_data = request.json
            if not request_data or 'addresses' not in request_data:
                return jsonify({'success': False, 'message': 'No addresses provided'}), 400

            addresses = request_data['addresses']
            if not isinstance(addresses, list):
                return jsonify({'success': False, 'message': 'Addresses must be a list'}), 400

            # Extract just the address strings for the wallet API
            address_list = []
            for addr_entry in addresses:
                if isinstance(addr_entry, dict) and 'address' in addr_entry:
                    address_list.append(addr_entry['address'])
                elif isinstance(addr_entry, str):
                    address_list.append(addr_entry)

            if not address_list:
                return jsonify({'success': True, 'balances': []})

            # Use the wallet API to fetch balances
            try:
                balances = []
                for address in address_list:
                    # Determine address type and use appropriate method
                    address = address.strip()
                    if not address:
                        balances.append(0.0)
                        continue

                    try:
                        if address.startswith(('xpub', 'zpub', 'ypub')):
                            # Use xpub balance method for extended public keys
                            balance = self.image_renderer.wallet_api.get_xpub_balance(address)
                        else:
                            # Use regular address balance method
                            balance = self.image_renderer.wallet_api.get_address_balance(address)

                        balances.append(balance)

                    except Exception as addr_error:
                        print(f"Error fetching balance for {address}: {addr_error}")
                        balances.append(0.0)

                # Emit WebSocket event with updated cache after manual refresh
                cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                if hasattr(self, 'socketio') and self.socketio and cached_wallet_data:
                    self.socketio.emit('wallet_balance_updated', cached_wallet_data, room='authenticated')
                    print("📡 [MANUAL] Balance update broadcasted via WebSocket")

                return jsonify({
                    'success': True,
                    'balances': balances
                })

            except Exception as wallet_error:
                print(f"Wallet balance API error: {wallet_error}")
                # Return zeros if wallet API fails
                return jsonify({
                    'success': True,
                    'balances': [0.0] * len(address_list),
                    'warning': 'Could not fetch live balances, showing cached/zero values'
                })

        except Exception as e:
            print(f"Error in refresh_wallet_balances: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/wallet_balance_cached', methods=['POST'])
    @require_auth(self.auth_manager)
    def get_cached_wallet_balances():
        """Get cached wallet balances for the provided addresses."""
        try:
            request_data = request.json
            if not request_data or 'addresses' not in request_data:
                return jsonify({'success': False, 'message': 'No addresses provided'}), 400

            addresses = request_data['addresses']
            if not isinstance(addresses, list):
                return jsonify({'success': False, 'message': 'Addresses must be a list'}), 400

            # Extract just the address strings for the wallet API
            address_list = []
            for addr_entry in addresses:
                if isinstance(addr_entry, dict) and 'address' in addr_entry:
                    address_list.append(addr_entry['address'])
                elif isinstance(addr_entry, str):
                    address_list.append(addr_entry)

            if not address_list:
                return jsonify({'success': True, 'balances': []})

            # Get cached wallet data
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()

            balances = []
            for address in address_list:
                address = address.strip()
                if not address:
                    balances.append(0.0)
                    continue

                balance = 0.0  # Default balance

                if cached_wallet_data:
                    # Check if address is an xpub/ypub/zpub
                    if address.startswith(('xpub', 'zpub', 'ypub')):
                        # Look for xpub data in cache (array format)
                        xpub_entries = cached_wallet_data.get('xpubs', [])
                        for xpub_entry in xpub_entries:
                            if xpub_entry.get('xpub') == address:
                                balance = xpub_entry.get('balance_btc', 0.0)
                                break
                    else:
                        # Look for regular address in cache (array format)
                        address_entries = cached_wallet_data.get('addresses', [])
                        for addr_entry in address_entries:
                            if addr_entry.get('address') == address:
                                balance = addr_entry.get('balance_btc', 0.0)
                                break

                balances.append(balance)

            return jsonify({
                'success': True,
                'balances': balances,
                'cached': True
            })

        except Exception as e:
            print(f"Error in get_cached_wallet_balances: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/clear_wallet_cache', methods=['POST'])
    @require_auth(self.auth_manager)
    def clear_wallet_cache():
        """Clear all cached wallet data (balances, derivation, addresses)."""
        try:
            removed = []
            for cache_file in [
                'cache/wallet_balances.json',
                'cache/async_wallet_address_cache.sensitive.json',
            ]:
                try:
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                        removed.append(cache_file)
                except OSError:
                    pass
            # Clear address derivation cache if it exists
            if hasattr(self.image_renderer, 'wallet_api'):
                api = self.image_renderer.wallet_api
                if hasattr(api, 'address_derivation') and hasattr(api.address_derivation, 'unified_cache'):
                    try:
                        api.address_derivation.unified_cache.clear_cache('address_derivation_cache')
                        removed.append('address_derivation_cache')
                    except Exception:
                        pass
                if hasattr(api, 'unified_cache'):
                    # These are the section names the unified cache actually
                    # registers. wallet_balance_cache is the one the config
                    # preview reads, and it was missing here — so the old total
                    # came back on the next page load even though every address
                    # had been removed.
                    for cache_name in ['wallet_balance_cache', 'optimized_balance_cache']:
                        try:
                            api.unified_cache.clear_cache(cache_name)
                            removed.append(cache_name)
                        except Exception:
                            pass
                # The API also holds decoded copies in memory; the process is
                # not restarting, so clearing only the store leaves these live.
                api._wallet_cache = None
                if hasattr(api, '_balance_cache'):
                    api._balance_cache = {}
            print(f"🧹 Wallet cache cleared: {', '.join(removed) if removed else 'no files found'}")
            return jsonify({'success': True, 'cleared': removed})
        except Exception as e:
            print(f"Error clearing wallet cache: {e}")
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/block-rewards/<address>/found-blocks', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_found_blocks_count(address):
        """Get the number of found blocks for a specific Bitcoin address."""
        try:
            if not address:
                return jsonify({'success': False, 'message': 'No address provided'}), 400

            # Get found blocks count from block monitor
            found_blocks = 0

            if hasattr(self, 'block_monitor') and self.block_monitor:
                # Check if this address is in the monitored addresses
                current_config = self.config_manager.get_current_config()

                # Support both table format and legacy format
                monitored_addresses = set()

                # New table format
                block_reward_table = current_config.get("block_reward_addresses_table", [])
                for entry in block_reward_table:
                    if isinstance(entry, dict) and entry.get("address"):
                        monitored_addresses.add(entry["address"])

                if address in monitored_addresses:
                    # Use new cache system for fast retrieval
                    found_blocks = self.block_monitor.get_coinbase_count(address)
                else:
                    found_blocks = 0

            return jsonify({
                'success': True,
                'address': address,
                'found_blocks': found_blocks
            })

        except Exception as e:
            print(f"Error in get_found_blocks_count: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': _safe_error(e)}), 500
