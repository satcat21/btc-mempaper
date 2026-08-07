"""Bitaxe miner telemetry: per-device best-difficulty lookups."""

import traceback

from flask import jsonify
from managers.auth_manager import require_auth


def register(self):
    """Register the bitaxe routes."""
    from mempaper_app import _safe_error

    @self.app.route('/api/bitaxe/<ip>/best-diff', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_bitaxe_best_diff(ip):
        """Get the best difficulty for a specific Bitaxe miner."""
        try:
            if not ip:
                return jsonify({'success': False, 'message': 'No IP provided'}), 400

            # Reject before any request is made: this value comes straight
            # from the request path and used to be interpolated into the
            # miner URL unvalidated (SSRF).
            from lib.bitaxe_api import parse_miner_address
            if parse_miner_address(ip) is None:
                return jsonify({'success': False,
                                'message': 'Invalid miner address'}), 400

            from lib.bitaxe_api import BitaxeAPI
            bitaxe_api = getattr(self.image_renderer, 'bitaxe_api', None) or BitaxeAPI()
            miner_info = bitaxe_api.get_miner_info(ip)

            best_diff = miner_info.get('best_diff', 0)
            online = miner_info.get('online', False)
            hashrate_avg_ghs = miner_info.get('hashrate_avg_ghs', miner_info.get('hashrate_ghs', 0))
            hashrate_avg_label = miner_info.get('hashrate_avg_label', 'current')

            return jsonify({
                'success': True,
                'ip': ip,
                'best_diff': best_diff,
                'online': online,
                'hashrate_avg_ghs': hashrate_avg_ghs,
                'hashrate_avg_label': hashrate_avg_label,
            })

        except Exception as e:
            print(f"Error in get_bitaxe_best_diff: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': _safe_error(e)}), 500
