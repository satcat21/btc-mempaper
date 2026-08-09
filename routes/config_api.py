"""Mempool validation, session status, and reading/writing configuration.
"""

from utils.translations import translations
from flask import jsonify
from flask import request
from flask import session
from managers.auth_manager import require_auth
from utils.technical_config import MEMPOOL_ONION_PRESETS
from utils.technical_config import build_mempool_proxies
import threading
import time
import traceback

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the config api routes."""
    from mempaper_app import _read_reboot_time, _safe_error

    @self.app.route('/api/tang/validate', methods=['GET'])
    @require_auth(self.auth_manager)
    def validate_tang_connection():
        """Check the Tang link end to end and return per-step status.

        Accepts url and thumbprint as query parameters so the config page can
        test what is currently typed into the form, before it is saved.
        """
        from managers.tang_manager import TangManager
        from flask import request as _request

        url = _request.args.get('url')
        thumbprint = _request.args.get('thumbprint')
        manager = TangManager(self.config_manager)
        try:
            checks = manager.check(url=url, thumbprint=thumbprint)
        except Exception as e:
            checks = [{'name': 'Tang check', 'ok': False, 'error': str(e)[:200]}]

        # Offer the value the operator needs when nothing is pinned yet, so the
        # page can fill it in rather than making them copy it off the server.
        suggested = ''
        for check in checks:
            if check['name'] == 'Advertisement valid' and check.get('detail'):
                suggested = check['detail']
        return jsonify({'checks': checks, 'suggested_thumbprint': suggested})

    @self.app.route('/api/tang/discover', methods=['GET'])
    @require_auth(self.auth_manager)
    def discover_tang_servers():
        """Tang servers advertising themselves over mDNS, if any."""
        from managers.tang_manager import TangManager
        try:
            return jsonify({'servers': TangManager(self.config_manager).discover()})
        except Exception as e:
            return jsonify({'servers': [], 'error': str(e)[:200]})

    @self.app.route('/api/mempool/validate', methods=['GET'])
    @require_auth(self.auth_manager)
    def validate_mempool_connection():
        """Check each mempool API endpoint and return per-check status."""
        import time as _time
        import concurrent.futures
        from requests.auth import HTTPBasicAuth as _Auth
        import requests as _req

        cfg = self.config_manager.get_current_config()
        host       = cfg.get('mempool_host', '127.0.0.1')
        rest_port  = cfg.get('mempool_rest_port', 4081)
        ws_port    = cfg.get('mempool_ws_port', 8999)
        ws_path    = cfg.get('mempool_ws_path', '/api/v1/ws')
        use_https  = cfg.get('mempool_use_https', False)
        verify_ssl = cfg.get('mempool_verify_ssl', True)
        username   = cfg.get('mempool_username', '')
        password   = cfg.get('mempool_password', '')

        from utils.technical_config import build_mempool_api_url
        base_url = build_mempool_api_url(host, rest_port, use_https)
        auth = _Auth(username, password) if username and password else None
        ws_scheme = 'wss' if use_https else 'ws'

        # Tor adds 1-4 s per request, so the clearnet timeouts below would
        # report a healthy onion service as timing out. Widen them, and
        # route the checks through the same proxy the app itself uses.
        _proxies = build_mempool_proxies(cfg)
        _via_tor = bool(_proxies)
        _rest_timeout = (10, 25) if _via_tor else (3, 5)
        _ws_connect_timeout = 20 if _via_tor else 3
        _ws_read_timeout = 20 if _via_tor else 5

        checks_def = [
            ('Block height',  f'{base_url}/blocks/tip/height'),
            ('Price API',     f'{base_url}/v1/prices'),
            ('Fee data',      f'{base_url}/v1/fees/recommended'),
            ('Network stats', f'{base_url}/v1/mining/hashrate/1m'),
            ('Wallet API',    f'{base_url}/v1/validate-address/1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'),
        ]

        ws_url = f'{ws_scheme}://{host}:{ws_port}{ws_path}'

        def _check(name, url):
            t0 = _time.time()
            try:
                r = _req.get(url, timeout=_rest_timeout, verify=verify_ssl,
                             auth=auth, proxies=_proxies)
                latency = round((_time.time() - t0) * 1000)
                if not r.ok:
                    snippet = r.text[:200].strip() if r.text else ''
                    hint = ''
                    if r.status_code == 401:
                        hint = 'Authentication required — check username/password in Advanced settings.'
                    elif r.status_code == 403:
                        hint = 'Access forbidden — your mempool may require auth or IP whitelisting.'
                    elif r.status_code == 404:
                        hint = 'Endpoint not found — this feature may not be supported by your mempool backend (Electrs vs full Mempool.space).'
                    elif r.status_code == 502:
                        hint = 'Bad gateway — mempool backend may be down or Electrum connection is broken.'
                    elif r.status_code == 503:
                        hint = 'Service unavailable — mempool service may still be starting up.'
                    error = f'HTTP {r.status_code}'
                    if hint:
                        error += f' — {hint}'
                    if snippet:
                        error += f'\nResponse: {snippet}'
                    return {'name': name, 'url': url, 'ok': False,
                            'latency_ms': latency, 'detail': f'HTTP {r.status_code}',
                            'error': error}
                return {'name': name, 'url': url, 'ok': True,
                        'latency_ms': latency,
                        'detail': f'HTTP {r.status_code}'}
            except _req.exceptions.ConnectTimeout:
                return {'name': name, 'url': url, 'ok': False,
                        'error': f'Connection timed out ({_rest_timeout[0]} s) — '
                                 + ('is the Tor daemon running and reachable?' if _via_tor
                                    else 'check host/port and firewall rules.')}
            except _req.exceptions.ReadTimeout:
                return {'name': name, 'url': url, 'ok': False,
                        'error': f'Server connected but response timed out ({_rest_timeout[1]} s) — '
                                 + ('slow Tor circuit, or the onion service is down.' if _via_tor
                                    else 'mempool may be overloaded.')}
            except _req.exceptions.SSLError as e:
                return {'name': name, 'url': url, 'ok': False,
                        'error': f'SSL error: {str(e)[:150]} — try disabling "Verify SSL" in Advanced settings.'}
            except _req.exceptions.ConnectionError as e:
                return {'name': name, 'url': url, 'ok': False,
                        'error': f'Connection refused — is mempool running at {host}:{rest_port}? ({str(e)[:80]})'}
            except Exception as e:
                return {'name': name, 'url': url, 'ok': False, 'error': str(e)[:200]}

        def _check_ws():
            import socket as _socket
            import ssl as _ssl
            import base64 as _b64
            import os as _os
            from urllib.parse import urlparse as _urlparse

            t0 = _time.time()
            try:
                p = _urlparse(ws_url)
                h = p.hostname
                port = p.port or (443 if ws_scheme == 'wss' else 80)
                path_str = p.path or '/api/v1/ws'

                if _via_tor:
                    # A plain socket ignores the SOCKS proxy entirely and would
                    # try to resolve the .onion locally, which always fails.
                    # PySocks (already a dependency) proxies at socket level;
                    # rdns=True keeps resolution on the Tor side.
                    import socks as _socks
                    sock = _socks.socksocket()
                    sock.set_proxy(_socks.SOCKS5,
                                   cfg.get('tor_socks_host', '127.0.0.1'),
                                   int(cfg.get('tor_socks_port', 9050)),
                                   rdns=True)
                    sock.settimeout(_ws_connect_timeout)
                    sock.connect((h, port))
                else:
                    sock = _socket.create_connection((h, port), timeout=_ws_connect_timeout)

                if ws_scheme == 'wss':
                    ctx = _ssl.create_default_context()
                    # create_default_context() still permits TLS 1.0/1.1;
                    # pin the floor to 1.2. Independent of verify_ssl below,
                    # which only controls certificate checking for
                    # self-signed mempool instances.
                    ctx.minimum_version = _ssl.TLSVersion.TLSv1_2
                    if not verify_ssl:
                        ctx.check_hostname = False
                        ctx.verify_mode = _ssl.CERT_NONE
                    sock = ctx.wrap_socket(sock, server_hostname=h)

                key = _b64.b64encode(_os.urandom(16)).decode()
                hdrs = [
                    f'GET {path_str} HTTP/1.1',
                    f'Host: {p.netloc}',
                    'Upgrade: websocket',
                    'Connection: Upgrade',
                    f'Sec-WebSocket-Key: {key}',
                    'Sec-WebSocket-Version: 13',
                ]
                if username and password:
                    creds = _b64.b64encode(f'{username}:{password}'.encode()).decode()
                    hdrs.append(f'Authorization: Basic {creds}')

                sock.sendall(('\r\n'.join(hdrs) + '\r\n\r\n').encode())
                sock.settimeout(_ws_read_timeout)

                resp = b''
                while b'\r\n\r\n' not in resp:
                    chunk = sock.recv(2048)
                    if not chunk:
                        break
                    resp += chunk
                try:
                    sock.close()
                except Exception:
                    pass

                first_line = resp.decode('utf-8', errors='replace').split('\r\n')[0]
                if ' 101 ' in first_line:
                    return {'name': 'WebSocket', 'url': ws_url, 'ok': True,
                            'latency_ms': round((_time.time() - t0) * 1000),
                            'detail': '101 Switching Protocols'}
                else:
                    return {'name': 'WebSocket', 'url': ws_url, 'ok': False,
                            'error': first_line or 'No response from server'}
            except Exception as e:
                return {'name': 'WebSocket', 'url': ws_url, 'ok': False, 'error': str(e)[:120]}

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(_check, n, u) for n, u in checks_def]
            ws_future = pool.submit(_check_ws)
            results = [f.result() for f in concurrent.futures.as_completed(futures + [ws_future])]

        order = {n: i for i, (n, _) in enumerate(checks_def)}
        order['WebSocket'] = len(checks_def)
        results.sort(key=lambda r: order.get(r['name'], 99))

        return jsonify({'checks': results, 'ws_url': ws_url})

    @self.app.route('/api/donations', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_donations():
        """Return donation history (most recent first)."""
        return jsonify({
            'donations': self._donation_history,
            'latest': self._latest_donation,
        })

    @self.app.route('/api/session/status', methods=['GET'])
    def session_status():
        """Get current session status and remaining time."""
        return jsonify(self.auth_manager.get_session_info())

    @self.app.route('/api/session/refresh', methods=['POST'])
    @require_auth(self.auth_manager)
    def session_refresh():
        """Refresh the current session to extend its lifetime."""
        if self.auth_manager.refresh_session():
            return jsonify({
                'success': True,
                'message': 'Session refreshed successfully',
                'session_info': self.auth_manager.get_session_info()
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Session could not be refreshed'
            }), 401

    @self.app.route('/api/config', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_config():
        """Get current configuration including secure wallet addresses."""
        try:
            # Get current language and translations
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            # Allow ?lang= override so the client can request schema/category labels
            # in a specific language without changing the saved config language.
            req_lang = request.args.get('lang', lang)
            schema_translations = translations.get(req_lang, current_translations) if req_lang in translations else current_translations

            # Get the regular configuration
            config_data = self.config_manager.get_current_config()

            # Add wallet addresses from secure configuration if available
            if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api.secure_config_manager:
                secure_config = self.image_renderer.wallet_api.secure_config_manager.load_secure_config()
                if secure_config and 'wallet_balance_addresses_with_comments' in secure_config:
                    wallet_addresses = secure_config['wallet_balance_addresses_with_comments']
                    config_data['wallet_balance_addresses_with_comments'] = wallet_addresses

                    # Include cached balances in the configuration
                    try:
                        if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                            cached_data = self.image_renderer.wallet_api.get_cached_wallet_balances()

                            if cached_data and 'addresses' in cached_data:
                                address_balances = {}
                                for addr_info in cached_data['addresses']:
                                    if 'address' in addr_info and 'balance_btc' in addr_info:
                                        address_balances[addr_info['address']] = addr_info['balance_btc']

                                if 'xpubs' in cached_data:
                                    for xpub_info in cached_data['xpubs']:
                                        if 'xpub' in xpub_info and 'balance_btc' in xpub_info:
                                            address_balances[xpub_info['xpub']] = xpub_info['balance_btc']

                                for addr_entry in wallet_addresses:
                                    if 'address' in addr_entry:
                                        address = addr_entry['address']
                                        addr_entry['cached_balance'] = address_balances.get(address, 0.0)

                                config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                                config_data['wallet_total_balance'] = cached_data.get('total_btc', 0.0)

                    except Exception as balance_error:
                        pass  # Continue without cached balances if there's an error

            from flask import session as _session
            # Compact holiday dict for config-page preview widgets.
            # Shape: {"MM-DD": {"en": "Title", "de": "...", ...}, ...}
            try:
                from lib.btc_holidays import btc_holidays as _btc_h
                btc_h_compact = {
                    k: {lng: entry[lng]['title'] for lng in entry}
                    for k, v in _btc_h.items() if v for entry in [v[0]]
                }
            except Exception:
                btc_h_compact = {}
            _rbt = _read_reboot_time()
            return jsonify({
                'config': config_data,
                'schema': self.config_manager.get_config_schema(schema_translations),
                'categories': self.config_manager.get_categories(schema_translations),
                'color_options': self.config_manager.get_color_options(),
                # Offered as dropdown suggestions on the mempool host field
                # when Tor is enabled; the field stays free-text so a
                # self-hosted hidden service can be entered instead.
                'mempool_onion_presets': MEMPOOL_ONION_PRESETS,
                'current_user': _session.get('username', ''),
                'btc_holidays': btc_h_compact,
                'reboot_window': {'hour': _rbt[0], 'minute': _rbt[1]} if _rbt else None,
            })
        except Exception as e:
            print(f"Error in get_config: {e}")
            traceback.print_exc()
            return jsonify({'error': _safe_error(e)}), 500

    @self.app.route('/api/translations/<language>', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_translations(language):
        """Get translations for a specific language."""
        try:
            from utils.translations import translations
            language_translations = translations.get(language, translations["en"])
            return jsonify({
                'success': True,
                'translations': language_translations
            })
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/config/preview-data', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_config_preview_data():
        """Return live data for config-page preview cards (price, bitaxe, wallet)."""
        try:
            cfg = self.config_manager.get_current_config()
            currency_symbols = {'USD':'$','EUR':'€','GBP':'£','CAD':'C$','CHF':'CHF','AUD':'A$','JPY':'¥'}
            price_currency_override = request.args.get('price_currency')
            wallet_currency_override = request.args.get('wallet_currency')

            # Price
            price_data = self._precache.get('price_data') if hasattr(self, '_precache') else None
            price_payload = None
            # Resolve the effective currency for the price preview
            effective_price_currency = price_currency_override or (
                price_data.get('currency', 'USD') if price_data else 'USD')

            # Use the cached all_prices dict so any currency costs zero extra API calls
            all_prices = (
                self._precache.get('all_prices')
                or (price_data.get('all_prices') if price_data else None)
                or self.image_renderer.btc_price_api.get_all_prices()
            )
            if all_prices and effective_price_currency in all_prices:
                pv = all_prices[effective_price_currency]
                price_payload = {
                    'price': pv,
                    'currency': effective_price_currency,
                    'symbol': currency_symbols.get(effective_price_currency, effective_price_currency),
                    'moscow_time': int(100_000_000 / pv) if pv > 0 else 0,
                }
            elif price_data and not price_data.get('error'):
                currency = price_data.get('currency', 'USD')
                price_val = price_data.get('price_in_selected_currency', price_data.get('currency_price', 0))
                price_payload = {
                    'price': price_val,
                    'currency': currency,
                    'symbol': currency_symbols.get(currency, currency),
                    'moscow_time': price_data.get('moscow_time', 0),
                }

            # Bitaxe — aggregate from pre-cache or live fetch
            bitaxe_payload = None
            bitaxe_data = self._precache.get('bitaxe_data') if hasattr(self, '_precache') else None
            _bitaxe_stale_offline = bool(bitaxe_data) and bitaxe_data.get('miners_total', 0) > 0 and bitaxe_data.get('miners_online', 0) == 0
            if (not bitaxe_data or _bitaxe_stale_offline) and hasattr(self.image_renderer, 'bitaxe_api'):
                try:
                    fresh_bitaxe_data = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                    if fresh_bitaxe_data and not fresh_bitaxe_data.get('error'):
                        bitaxe_data = fresh_bitaxe_data
                        if hasattr(self, '_precache'):
                            self._precache['bitaxe_data'] = bitaxe_data
                            self._precache['bitaxe_last_update'] = time.time()
                    elif not bitaxe_data:
                        bitaxe_data = fresh_bitaxe_data
                except Exception:
                    pass
            if bitaxe_data and not bitaxe_data.get('error'):
                ths = bitaxe_data.get('total_hashrate_ths', 0)
                online = bitaxe_data.get('miners_online', 0)
                total = bitaxe_data.get('miners_total', 0)
                best_diff = bitaxe_data.get('best_difficulty', 0)
                valid_blocks = bitaxe_data.get('valid_blocks', 0)
                bitaxe_payload = {
                    'hashrate_ths': ths,
                    'miners_online': online,
                    'miners_total': total,
                    'best_difficulty': best_diff,
                    'valid_blocks': valid_blocks,
                    'display_mode': cfg.get('bitaxe_display_mode', 'blocks'),
                }

            # Wallet — from cache
            wallet_payload = None
            try:
                cached_wallet = self.image_renderer.wallet_api.get_cached_wallet_balances()
                if cached_wallet:
                    total_btc = cached_wallet.get('total_btc', 0)
                    wallet_currency = wallet_currency_override or cfg.get('wallet_balance_currency', 'EUR')
                    # Compute fiat value from all_prices cache — zero extra API calls
                    fiat_value = None
                    wp_price = (all_prices or {}).get(wallet_currency)
                    if wp_price:
                        fiat_value = total_btc * wp_price
                    elif price_payload and price_payload['currency'] == wallet_currency:
                        fiat_value = total_btc * price_payload['price']
                    wallet_payload = {
                        'total_btc': total_btc,
                        'fiat_value': fiat_value,
                        'currency': wallet_currency,
                        'symbol': currency_symbols.get(wallet_currency, wallet_currency),
                        'has_wallets': bool(cfg.get('wallet_balance_addresses_with_comments')),
                    }
            except Exception:
                pass

            # Donation — return both latest and largest so the JS preview can
            # switch modes without a save/refresh cycle.
            donation_payload = None
            try:
                def _don_to_payload(d, mode=None):
                    if not d or not d.get('amount_sats'):
                        return None
                    hdr = ''
                    if hasattr(self.image_renderer, '_build_donation_header_text'):
                        hdr = self.image_renderer._build_donation_header_text(
                            d.get('amount_sats', 0), d.get('timestamp', ''), mode=mode)
                    return {
                        'amount_sats': d.get('amount_sats', 0),
                        'message': d.get('message', ''),
                        'timestamp': d.get('timestamp', ''),
                        'header_text': hdr,
                    }
                p_latest  = _don_to_payload(self._latest_donation,       mode='latest')
                p_highest = _don_to_payload(self._highest_donation,      mode='highest')
                _active_don = self._get_active_donation()
                _eff_mode = _active_don.get('_effective_mode', 'latest') if _active_don else 'latest'
                p_auto    = _don_to_payload(_active_don, mode=_eff_mode)
                if p_latest or p_highest or p_auto:
                    donation_payload = {
                        'latest':  p_latest,
                        'highest': p_highest,
                        'auto':    p_auto,
                    }
            except Exception:
                pass

            # Network stats — from precache; fetch synchronously if not cached yet.
            # Resolved before the halving payload below, which needs the block pace.
            network_payload = None
            net = None
            try:
                net = self._precache.get('network_data') if hasattr(self, '_precache') else None
                if not net or net.get('error'):
                    fresh = self.mempool_api.get_network_stats()
                    if fresh:
                        # Use it either way — a partial result still has the pace
                        # fields — but never let an errored one warm the precache.
                        net = fresh
                        if not fresh.get('error') and hasattr(self, '_precache'):
                            import time as _time
                            self._precache['network_data'] = net
                            self._precache['network_last_update'] = _time.time()
                # An error marker means the hashrate lookup failed; the card is
                # skipped, but `net` still carries the pace fields for the halving.
                if net and not net.get('error'):
                    network_payload = {
                        'hashrate': net.get('currentHashrate', 0),
                        'difficulty': net.get('currentDifficulty', 0),
                    }
            except Exception:
                net = None

            # Countdown + Halving — computed from current block height
            countdown_payload = None
            halving_payload = None
            try:
                from lib.image_renderer import ImageRenderer as _IR
                bh = self.current_block_height
                if not bh:
                    # Not resolved yet — e.g. right after a reboot, before the
                    # startup block-height check has run or if it failed because
                    # Wi-Fi wasn't reconnected yet. Fall back to a live lookup
                    # (mirrors the network/Bitaxe fallbacks below) so the
                    # countdown/halving cards don't stay stuck until the next
                    # real block arrives (countdown_updated only fires then).
                    try:
                        info = self.mempool_api.get_current_block_info()
                        bh = info.get('block_height') if info else None
                    except Exception:
                        bh = None
                if bh:
                    sup = _IR._compute_supply_stats(bh)
                    countdown_payload = {
                        'remaining_btc': round(sup['remaining_btc'], 2),
                        'pct_mined': sup['pct_mined'],
                    }
                    hal = _IR._compute_halving_stats(bh, net)
                    countdown_payload['block_height'] = int(bh)
                    halving_payload = {
                        'days_remaining': hal['days_remaining'],
                        'hours_remaining': hal['hours_remaining'],
                        'estimated_date': hal['estimated_date'].isoformat() if hal.get('estimated_date') else None,
                    }
            except Exception:
                pass

            return jsonify({
                'price': price_payload,
                'bitaxe': bitaxe_payload,
                'wallet': wallet_payload,
                'donation': donation_payload,
                'countdown': countdown_payload,
                'halving': halving_payload,
                'network': network_payload,
                'block_hash': self.current_block_hash,
            })
        except Exception as e:
            return jsonify({'error': _safe_error(e)}), 500

    @self.app.route('/api/config', methods=['POST'])
    @require_auth(self.auth_manager)
    def save_config():
        """Save configuration changes."""
        try:
            # Refresh session on any authenticated activity
            self.auth_manager.refresh_session()

            # Store old config for comparison
            old_config = dict(self.config) if hasattr(self, 'config') else None

            new_config = request.json or {}
            if not isinstance(new_config, dict):
                return jsonify({'success': False, 'message': 'Invalid configuration payload'}), 400

            # Handle admin username rename server-side so the admin_users mapping and
            # the current session stay in sync even for legacy sessions missing username.
            old_admin_username = str((old_config or {}).get('admin_username') or '').strip()
            requested_admin_username = str(new_config.get('admin_username') or '').strip()
            session_username = str(session.get('username') or '').strip()

            if requested_admin_username:
                new_config['admin_username'] = requested_admin_username

            if old_admin_username and requested_admin_username and requested_admin_username != old_admin_username:
                with self.config_manager.config_lock:
                    admin_users = dict(self.config_manager.config.get('admin_users') or {})

                if admin_users:
                    if not session_username:
                        return jsonify({'success': False, 'message': 'Session username is missing'}), 401

                    if session_username not in admin_users:
                        return jsonify({'success': False, 'message': 'Authenticated user not found'}), 403

                    rename_source = session_username

                    if requested_admin_username in admin_users and requested_admin_username != rename_source:
                        return jsonify({'success': False, 'message': 'Username already taken'}), 409

                    if requested_admin_username != rename_source:
                        admin_users[requested_admin_username] = admin_users.pop(rename_source)
                    new_config['admin_users'] = admin_users

            if self.config_manager.save_config(new_config):
                if requested_admin_username and (
                    requested_admin_username != old_admin_username or not session_username
                ):
                    session['username'] = requested_admin_username

                # Get validated new config from manager
                validated_new_config = self.config_manager.get_current_config()

                # _on_config_change must run synchronously: it reads self.config as
                # old_config for comparison and may update self.config itself.
                self._on_config_change(validated_new_config)

                # Update local config reference (may already be set by _on_config_change)
                self.config = self.config_manager.get_current_config()
                self.auth_manager.config = self.config

                # Capture everything the background thread needs before returning.
                _old_cfg = old_config
                _new_cfg = new_config
                _show_wallet = new_config.get("show_wallet_balances_block", True)

                def _post_save_background():
                    try:
                        # Clean up cache for removed wallet addresses
                        if _old_cfg:
                            self._cleanup_removed_wallet_caches(_old_cfg, _new_cfg)

                        # Reinitialize components (creates new ImageRenderer + API clients)
                        self._reinitialize_after_config_change(_old_cfg)

                        # Seed change-detection so the first post-save socket emit
                        # does not appear as "new" data on the dashboard.
                        self._seed_bitaxe_emission_state()

                        # Push live Bitaxe/found-block data to the config page.
                        # _emit_config_page_updates() makes HTTP calls to miner IPs —
                        # running it here prevents it from blocking the save response.
                        self._emit_config_page_updates()

                        # Fetch fresh wallet balances and push when ready
                        if _show_wallet:
                            try:
                                cached_before = self.image_renderer.wallet_api.get_cached_wallet_balances() or {}
                                fresh = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=True)
                                if fresh and not fresh.get('error'):
                                    self.image_renderer.wallet_api.update_cache(fresh)
                                    if hasattr(self, 'socketio') and self.socketio:
                                        emit_data = dict(fresh)
                                        emit_data['after_config_save'] = True
                                        emit_data['prev_addresses'] = cached_before.get('addresses', [])
                                        emit_data['prev_xpubs'] = cached_before.get('xpubs', [])
                                        self.socketio.emit('wallet_balance_updated', emit_data, room='authenticated')
                            except Exception as e:
                                print(f"⚠️ Background wallet refresh after config save failed: {e}")
                    except Exception as e:
                        print(f"⚠️ Post-save background task failed: {e}")

                threading.Thread(target=_post_save_background, daemon=True).start()

                return jsonify({
                    'success': True,
                    'message': 'Configuration saved successfully',
                    'current_user': session.get('username', '')
                })
            else:
                return jsonify({'success': False, 'message': 'Failed to save configuration'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 400
