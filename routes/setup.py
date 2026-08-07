"""Onboarding: nmcli wrappers, Wi-Fi scanning, the background credential-apply
worker, captive-portal detection and the /api/setup/* surface.
"""

from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from lib.image_renderer import ImageRenderer
from utils.translations import translations
import json
import os
import subprocess
import threading
import time

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the setup routes."""
    from mempaper_app import _safe_error

    def setup_mode_enabled():
        return self._is_setup_mode_enabled()

    def setup_mode_payload():
        return self._setup_mode_payload()

    def detect_wifi_interface():
        return self._detect_wifi_interface()

    def run_nmcli(args):
        """Run nmcli with sudo for setup operations.

        In AP (hotspot) mode, plain nmcli often returns empty scan results
        because the unprivileged user cannot read driver scan data.  Using
        sudo mirrors the approach in ``_nmcli()`` and delivery_state.py.
        """
        cmd = (['sudo', 'nmcli'] if os.name != 'nt' else ['nmcli']) + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=25,
            )
        except Exception:
            return None

    def scan_wifi_networks(interface):
        import time as _time

        # Get our own hotspot SSID so we can exclude it from the list
        own_ssid = self._setup_ssid_from_mac(interface) if self._is_setup_mode_enabled() else None

        # Parse 'iw scan' output directly rather than reading results back
        # via nmcli: the interface is unmanaged ('managed no') while the
        # setup hotspot is active so hostapd can bind it, and nmcli
        # reports zero networks for devices it doesn't manage even though
        # the kernel-level scan succeeds.
        iw_networks = self._scan_wifi_via_iw(interface, own_ssid=own_ssid)
        if iw_networks:
            return iw_networks

        # Fallback: nmcli (works when the interface is NM-managed)
        run_nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
        _time.sleep(2)

        result = run_nmcli([
            '-t',
            '-f',
            'IN-USE,SSID,SIGNAL,SECURITY',
            'device',
            'wifi',
            'list',
            'ifname',
            interface,
        ])
        if result is None or result.returncode != 0:
            return []

        networks = []
        seen = set()
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) < 4:
                continue
            in_use = parts[0].strip()
            ssid = parts[1].strip()
            signal = parts[2].strip()
            security = parts[3].strip()
            if not ssid or ssid in seen:
                continue
            # Never show our own hotspot in the client-network list
            if own_ssid and ssid == own_ssid:
                continue
            seen.add(ssid)
            try:
                signal_int = int(signal)
            except ValueError:
                signal_int = 0
            networks.append({
                'ssid': ssid,
                'signal': signal_int,
                'security': security,
                'in_use': in_use == '*',
                'open': security in ('', '--'),
            })

        networks.sort(key=lambda n: n.get('signal', 0), reverse=True)
        return networks

    def current_wifi_status(interface):
        result = run_nmcli(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
        if result is None or result.returncode != 0:
            return {'connected': False, 'connection': ''}

        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) < 4:
                continue
            dev, dev_type, state, connection = parts[0], parts[1], parts[2], parts[3]
            if dev == interface and dev_type == 'wifi':
                connected = state.startswith('connected') and not self._is_setup_hotspot_connection(connection)
                return {
                    'connected': connected,
                    'connection': connection,
                }

        return {'connected': False, 'connection': ''}

    # Tracks async Wi-Fi connect state so JS can poll after response is sent.
    _wifi_connect_state = {'status': 'idle', 'message': '', 'connection': ''}

    def apply_wifi_credentials_background(interface, ssid, password, hidden):
        """Runs in a background thread AFTER the HTTP response has been sent."""
        # _manual_wifi_connect_in_progress is set by the route handler before
        # this thread is even started (see setup_wifi_connect() below) — not
        # here — so the recovery monitor can never observe it as still False
        # while a connect attempt is already underway.
        try:
            _wifi_connect_state['status'] = 'connecting'
            _wifi_connect_state['message'] = f'Connecting to {ssid}...'

            # Short delay so the HTTP response definitely leaves the socket first.
            time.sleep(1)

            # A delivery-reset boot can bring the hotspot up before NetworkManager
            # itself has finished starting — wait for it here rather than let the
            # nmcli calls below fail against a not-yet-ready NM.
            if self._wait_for_nm_ready() is None:
                print('⚠️ NetworkManager not ready — aborting connect, restoring hotspot')
                _wifi_connect_state['status'] = 'failed'
                _wifi_connect_state['message'] = 'Device is still starting up — please try again in a minute.'
                self._bring_up_setup_hotspot(interface)
                return

            # Fully tear down the hotspot: stop hostapd/dnsmasq, remove iptables
            # redirects, delete ALL stale mempaper-setup profiles (there can be
            # many duplicates), and free the interface for client mode. Doesn't
            # clear the setup-mode flag — _bring_up_setup_hotspot() restores it
            # below if this connection attempt fails.
            print(f'📶 Tearing down setup hotspot to connect to {ssid}...')
            self._remove_wlan0_unmanaged_override()
            self._release_hotspot_for_probe(interface)
            self._cleanup_legacy_setup_hotspots()

            # The radio needs time to transition from AP back to managed/station
            # mode.  On RPi Zero W this can take several seconds.
            print('⏳ Waiting for radio to transition from AP to client mode...')
            time.sleep(5)

            # Force a fresh scan so NM discovers nearby networks after the
            # radio has been in AP mode (no scan results exist yet).
            self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
            time.sleep(3)

            # 'nmcli device wifi connect' creates a new NM profile which requires
            # settings.modify.system — must use sudo nmcli, not plain nmcli.
            connect_cmd = ['device', 'wifi', 'connect', ssid, 'ifname', interface]
            if password:
                connect_cmd += ['password', password]
            if hidden:
                connect_cmd += ['hidden', 'yes']

            # Try up to 3 times — the first attempt often fails because the
            # radio hasn't fully settled after AP teardown.
            max_attempts = 3
            connect_result = None
            for attempt in range(1, max_attempts + 1):
                print(f'📡 WiFi connect attempt {attempt}/{max_attempts} to {ssid}...')
                connect_result = self._nmcli(connect_cmd, timeout=45)
                if connect_result is not None and connect_result.returncode == 0:
                    print(f'✅ nmcli connect command succeeded on attempt {attempt}')
                    break
                error_hint = ''
                if connect_result is not None:
                    error_hint = (connect_result.stderr or connect_result.stdout or '').strip()
                print(f'⚠️ WiFi connect attempt {attempt} failed: {error_hint}')
                if attempt < max_attempts:
                    # Rescan and retry after a short delay
                    time.sleep(5)
                    self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
                    time.sleep(3)

            if connect_result is None or connect_result.returncode != 0:
                error_msg = 'Failed to connect to Wi-Fi network'
                if connect_result is not None and connect_result.stderr:
                    error_msg = connect_result.stderr.strip() or error_msg
                elif connect_result is not None and connect_result.stdout:
                    error_msg = connect_result.stdout.strip() or error_msg
                print(f'❌ WiFi connect failed after {max_attempts} attempts: {error_msg}')
                _wifi_connect_state['status'] = 'failed'
                _wifi_connect_state['message'] = error_msg
                # Restore hotspot so user can try again.
                self._bring_up_setup_hotspot(interface)
                return

            # Give NetworkManager a moment to fully establish the connection
            # (DHCP lease, DNS, etc.).
            print('⏳ Waiting for DHCP/DNS to settle...')
            time.sleep(8)

            # Poll for connection status (NM may still be negotiating)
            connected = False
            final_status = {}
            for poll in range(6):
                final_status = current_wifi_status(interface)
                if final_status.get('connected'):
                    connected = True
                    break
                time.sleep(3)

            if connected:
                try:
                    if os.path.exists(self.setup_mode_flag_path):
                        os.remove(self.setup_mode_flag_path)
                except OSError:
                    pass
                _wifi_connect_state['status'] = 'connected'
                _wifi_connect_state['connection'] = final_status.get('connection', ssid)
                _wifi_connect_state['message'] = f'Connected to {final_status.get("connection", ssid)}'
                print(f'✅ Setup Wi-Fi connected to {final_status.get("connection", ssid)}')
                # Clean up all leftover mempaper-setup profiles
                self._cleanup_legacy_setup_hotspots()
                self._nmcli(['connection', 'delete', 'mempaper-setup'])
                if self.e_ink_enabled:
                    threading.Thread(
                        target=self._display_onboarding_connected_screen,
                        daemon=True,
                    ).start()
            else:
                # nmcli reported success but device status doesn't show connected.
                # The profile IS saved — try activating it by name as a last resort.
                print(f'⚠️ nmcli succeeded but device not connected yet — trying connection up by name...')
                self._nmcli(['connection', 'up', ssid, 'ifname', interface], timeout=30)
                time.sleep(10)
                final_status = current_wifi_status(interface)
                if final_status.get('connected'):
                    try:
                        if os.path.exists(self.setup_mode_flag_path):
                            os.remove(self.setup_mode_flag_path)
                    except OSError:
                        pass
                    _wifi_connect_state['status'] = 'connected'
                    _wifi_connect_state['connection'] = final_status.get('connection', ssid)
                    _wifi_connect_state['message'] = f'Connected to {final_status.get("connection", ssid)}'
                    print(f'✅ Setup Wi-Fi connected via fallback: {final_status.get("connection", ssid)}')
                    self._cleanup_legacy_setup_hotspots()
                    self._nmcli(['connection', 'delete', 'mempaper-setup'])
                    if self.e_ink_enabled:
                        threading.Thread(
                            target=self._display_onboarding_connected_screen,
                            daemon=True,
                        ).start()
                else:
                    _wifi_connect_state['status'] = 'failed'
                    _wifi_connect_state['message'] = 'Connection attempt did not complete — check credentials'
                    self._bring_up_setup_hotspot(interface)
        finally:
            self._manual_wifi_connect_in_progress = False

    @self.app.route('/setup')
    def setup_wifi_page():
        """Public Wi-Fi onboarding page (only available in setup mode)."""
        if not setup_mode_enabled():
            return redirect(url_for('dashboard'))

        setup_data = setup_mode_payload()
        interface  = setup_data.get('interface', 'wlan0')

        url_key = request.args.get('key', '')
        key_valid = bool(url_key) and url_key == self._setup_password_from_mac(interface)

        # Show password gate until the correct key has been submitted.
        if not session.get('portal_authenticated'):
            return render_template(
                'setup_portal_gate.html',
                dark_mode=self.config.get('color_mode_dark', True),
                prefill_key=(url_key if key_valid else ''),
            )

        # Collect setup_* keys from all languages for client-side i18n
        setup_i18n = {}
        for lang_code, lang_dict in translations.items():
            setup_i18n[lang_code] = {k: v for k, v in lang_dict.items()
                                     if k.startswith('setup_') or k == 'onboarding_select_language'}
        return render_template(
            'setup_wifi.html',
            ssid=setup_data.get('ssid', 'mempaper-0000'),
            dark_mode=self.config.get('color_mode_dark', True),
            setup_i18n_json=json.dumps(setup_i18n, ensure_ascii=False),
        )

    # Captive-portal detection endpoints used by Android / iOS / Windows.
    # ── Captive-portal detection ──────────────────────────────
    # When in setup/hotspot mode, ALL captive-portal probe URLs return
    # a 302 redirect to the setup page.  This is what triggers the
    # "Sign in to WiFi network" popup on Android, iOS, and Windows.
    #
    # Combined with the wildcard dnsmasq (all DNS → hotspot IP) and
    # iptables port redirect (80/443 → Flask), this mirrors the proven
    # approach used by Bitaxe AxeOS / ESP-IDF captive portals.
    #
    # Previous approach returned 204/success for Android probes to
    # "keep the connection stable" — but this backfired because Android
    # then expected real internet and disconnected when it failed.

    @self.app.route('/generate_204')
    @self.app.route('/hotspot-detect.html')
    @self.app.route('/ncsi.txt')
    @self.app.route('/connecttest.txt')
    @self.app.route('/library/test/success.html')  # iOS
    @self.app.route('/success.txt')                # macOS Sonoma
    @self.app.route('/canonical.html')             # Windows 11
    def _absolute_setup_url():
        """Build an absolute http://<hotspot-ip>:<port>/setup URL.

        Redirecting with a bare '/setup' (Flask's default relative
        url_for()) leaves the browser on whatever external host it was
        probing (e.g. www.msftconnecttest.com) — the page still loads
        (DNS/iptables route it to us either way), but every relative
        /static/... asset request then also carries that external host,
        gets caught by captive_portal_catch_all() below, and is bounced
        back to /setup instead of actually being served — the page
        renders with no CSS/JS. An absolute URL corrects the browser's
        host immediately so assets load normally afterward.
        """
        interface = detect_wifi_interface()
        hotspot_ip = self._get_hotspot_ip(interface)
        port = self._get_web_port()
        return f'http://{hotspot_ip}:{port}/setup'

    def captive_portal_redirect():
        # No-store: prevents a client that cached this response on a
        # previous captive network from skipping the probe on ours.
        if setup_mode_enabled():
            resp = redirect(_absolute_setup_url(), code=302)
        else:
            resp = self.app.response_class(status=204)
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp

    @self.app.before_request
    def captive_portal_catch_all():
        """Redirect any request to an unknown host while in setup mode."""
        if not setup_mode_enabled():
            return None
        host = request.host.split(':')[0]
        # Pass through requests already destined for the Pi
        local_hosts = {'192.168.12.1', '10.42.0.1', 'localhost', '127.0.0.1'}
        if host in local_hosts:
            return None
        # Let /setup, /api/setup, and /static through even when the Host
        # header is still an external domain (e.g. connectivitycheck.gstatic.com):
        # /setup and /api/setup because captive-portal browsers can still
        # follow our 302 while keeping the external host (blocking them
        # here would create a redirect loop), and /static so CSS/JS/icons
        # referenced by relative URLs actually load instead of being
        # bounced back to /setup on every asset request.
        if request.path == '/setup' or request.path.startswith('/setup/') \
                or request.path.startswith('/api/setup') \
                or request.path.startswith('/static/'):
            return None
        # Everything else (captive-portal probes via external domains) →
        # redirect to setup page. No-store for the same reason as
        # captive_portal_redirect() above.
        resp = redirect(_absolute_setup_url(), code=302)
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp

    @self.app.route('/api/setup/portal-auth', methods=['POST'])
    def setup_portal_auth():
        """Validate the captive-portal password and mark the session as authenticated."""
        if not setup_mode_enabled():
            return jsonify({'success': False, 'message': 'Setup mode not active'}), 403
        data      = request.json or {}
        key       = data.get('key', '')
        setup_data = setup_mode_payload()
        interface  = setup_data.get('interface', 'wlan0')
        if key == self._setup_password_from_mac(interface):
            session['portal_authenticated'] = True
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Incorrect password'}), 401

    @self.app.route('/api/setup/wifi/scan', methods=['GET'])
    def setup_wifi_scan():
        if not setup_mode_enabled():
            return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

        interface = detect_wifi_interface()
        networks = scan_wifi_networks(interface)
        status = current_wifi_status(interface)

        return jsonify({
            'success': True,
            'interface': interface,
            'networks': networks,
            'status': status,
        })

    @self.app.route('/api/setup/wifi/connect', methods=['POST'])
    def setup_wifi_connect():
        if not setup_mode_enabled():
            return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

        data = request.json or {}
        ssid = (data.get('ssid') or '').strip()
        password = data.get('password', '')
        hidden = bool(data.get('hidden', False))
        language = (data.get('language') or '').strip()

        if not ssid:
            return jsonify({'success': False, 'message': 'SSID is required'}), 400
        if password and len(password) < 8:
            return jsonify({'success': False, 'message': 'Wi-Fi password must be at least 8 characters'}), 400

        # Persist selected language to config so the whole app uses it.
        if language and language in ('en', 'de', 'es', 'fr', 'it'):
            self.config_manager.set('language', language)
            self.config_manager.save_config()
            self.config['language'] = language
            self.translations = translations.get(language, translations['en'])
            # Recreate image renderer so dashboard images use the new language
            self.image_renderer = ImageRenderer(self.config, self.translations)

        interface = detect_wifi_interface()

        # Reset state and fire background thread BEFORE touching the radio.
        # This ensures the HTTP response is sent while hotspot is still up.
        _wifi_connect_state['status'] = 'connecting'
        _wifi_connect_state['message'] = f'Connecting to {ssid}...'
        _wifi_connect_state['connection'] = ''
        # Set here, synchronously, rather than as the background thread's
        # first line: otherwise the recovery monitor can see
        # _wifi_connect_pending below before the not-yet-started thread
        # sets this flag, and run its own _release_hotspot_for_probe()
        # concurrently with the one about to start — both threads tearing
        # down/rebuilding the hotspot and connecting at once, corrupting
        # NM's scan cache ("No network with SSID '<ssid>' found").
        self._manual_wifi_connect_in_progress = True
        self._wifi_connect_pending = True  # signal recovery monitor to probe immediately on failure
        threading.Thread(
            target=apply_wifi_credentials_background,
            args=(interface, ssid, password, hidden),
            daemon=True,
        ).start()

        return jsonify({
            'success': True,
            'connecting': True,
            'message': f'Connecting to {ssid}... please wait',
        })

    @self.app.route('/api/setup/wifi/connect_status', methods=['GET'])
    def setup_wifi_connect_status():
        """Poll this after posting to /connect to find out the result."""
        return jsonify({
            'success': True,
            'status': _wifi_connect_state['status'],
            'message': _wifi_connect_state['message'],
            'connection': _wifi_connect_state['connection'],
        })

    @self.app.route('/api/setup/status', methods=['GET'])
    def setup_wifi_status():
        interface = detect_wifi_interface()
        return jsonify({
            'success': True,
            'setup_mode': setup_mode_enabled(),
            'interface': interface,
            'wifi': current_wifi_status(interface),
        })

    @self.app.route('/api/setup/admin_needed', methods=['GET'])
    def setup_admin_needed():
        """Return whether first-time admin creation is still required.
        Safe to call at any time — never exposes credentials."""
        needed = not self.auth_manager.password_manager.is_password_set()
        return jsonify({'success': True, 'admin_needed': needed})

    @self.app.route('/api/setup/create_admin', methods=['POST'])
    def setup_create_admin():
        """Create the first admin user.  Only allowed when no user exists yet,
        so this endpoint cannot be used to hijack an already-configured device."""
        if not setup_mode_enabled():
            return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

        # Hard guard: refuse if any user already exists.
        if self.auth_manager.password_manager.is_password_set():
            return jsonify({
                'success': False,
                'message': 'Admin user already configured — use the settings page to manage users.',
            }), 403

        data = request.json or {}
        username = (data.get('username') or '').strip()
        password = data.get('password', '')
        confirm  = data.get('confirm_password', '')

        if not username:
            return jsonify({'success': False, 'message': 'Username is required'}), 400
        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
        if password != confirm:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        ok = self.auth_manager.password_manager.create_user(username, password)
        if not ok:
            return jsonify({'success': False, 'message': 'Failed to save user — check logs'}), 500

        print(f"✅ Setup: first admin user '{username}' created via onboarding portal")
        return jsonify({'success': True, 'message': f"User '{username}' created successfully"})

    @self.app.route('/api/setup/reset_device', methods=['POST'])
    def setup_reset_device():
        """Reset admin credentials and sensitive user data.

        Only allowed while the device is in setup/hotspot mode so that a
        user who forgot their admin password can recover without SSH access.
        """
        if not setup_mode_enabled():
            return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

        try:
            self._perform_user_data_reset()
            print("✅ Setup: device reset via onboarding portal")
            return jsonify({'success': True, 'message': 'Device reset successful'})
        except Exception as e:
            print(f"❌ Setup reset failed: {e}")
            return jsonify({'success': False, 'message': _safe_error(e)}), 500
