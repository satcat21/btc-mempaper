"""Health, saved Wi-Fi management, power control and SSH key management.
"""

from flask import jsonify
from flask import request
from managers.auth_manager import require_auth
import os
import subprocess
import threading
import time

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the system routes."""
    from mempaper_app import _safe_error

    # ── Software Update Endpoints ────────────────────────────────

    @self.app.route('/api/health', methods=['GET'])
    def health_check():
        """Health check endpoint for update polling."""
        return jsonify({
            'status': 'ok',
            'started': self._startup_timestamp,
            'boot_id': getattr(self, '_current_boot_id', None),
        })

    # ── WiFi Management API ───────────────────────────────────────────
    @self.app.route('/api/wifi/saved', methods=['GET'])
    @require_auth(self.auth_manager)
    def wifi_saved_list():
        """List saved WiFi connections with priority and active status."""
        try:
            # Use sudo to see system-owned connections
            result = self._nmcli(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'])
            if result is None or result.returncode != 0:
                return jsonify({'success': False, 'error': 'nmcli not available'}), 500

            # Get current active connection
            iface = self._detect_wifi_interface()
            status_result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
            active_connection = ''
            if status_result and status_result.returncode == 0:
                for line in status_result.stdout.splitlines():
                    parts = line.split(':')
                    if len(parts) >= 4 and parts[0] == iface and parts[1] == 'wifi':
                        if parts[2].startswith('connected'):
                            active_connection = parts[3]

            connections = []
            for line in result.stdout.splitlines():
                parts = line.split(':', 2)
                if len(parts) < 3:
                    continue
                name, uuid, conn_type = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if conn_type not in ('wifi', '802-11-wireless'):
                    continue
                # Skip setup hotspot profiles
                if self._is_setup_hotspot_connection(name):
                    continue

                # Get connection details (SSID, autoconnect-priority, security)
                detail = self._nmcli_read(['connection', 'show', uuid])
                ssid = name
                priority = 0
                autoconnect = True
                key_mgmt = ''
                if detail and detail.returncode == 0:
                    for prop in detail.stdout.splitlines():
                        if '802-11-wireless.ssid:' in prop:
                            ssid = prop.split(':', 1)[1].strip()
                        elif 'connection.autoconnect-priority:' in prop:
                            try:
                                priority = int(prop.split(':', 1)[1].strip())
                            except ValueError:
                                pass
                        elif 'connection.autoconnect:' in prop:
                            autoconnect = prop.split(':', 1)[1].strip().lower() == 'yes'
                        elif '802-11-wireless-security.key-mgmt:' in prop:
                            key_mgmt = prop.split(':', 1)[1].strip()

                connections.append({
                    'name': name,
                    'uuid': uuid,
                    'ssid': ssid,
                    'priority': priority,
                    'autoconnect': autoconnect,
                    'active': name == active_connection,
                    'open': key_mgmt in ('', '--'),
                })

            # Sort by priority (highest first), then by name
            connections.sort(key=lambda c: (-c['priority'], c['name'].lower()))
            return jsonify({'success': True, 'connections': connections})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/saved/<uuid>', methods=['DELETE'])
    @require_auth(self.auth_manager)
    def wifi_delete_connection(uuid):
        """Delete a saved WiFi connection (cannot delete active connection)."""
        try:
            # Check if this is the active connection
            iface = self._detect_wifi_interface()
            status_result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
            if status_result and status_result.returncode == 0:
                for line in status_result.stdout.splitlines():
                    parts = line.split(':')
                    if len(parts) >= 4 and parts[0] == iface and parts[1] == 'wifi':
                        if parts[2].startswith('connected'):
                            # Get UUID of active connection
                            active_result = self._nmcli_read(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show', '--active'])
                            if active_result and active_result.returncode == 0:
                                for aline in active_result.stdout.splitlines():
                                    aparts = aline.split(':', 2)
                                    if len(aparts) >= 2 and aparts[1].strip() == uuid:
                                        return jsonify({'success': False, 'error': 'Cannot delete the currently connected WiFi'}), 400

            result = self._nmcli(['connection', 'delete', uuid])
            if result is None or result.returncode != 0:
                err = (result.stderr or result.stdout or '').strip() if result else 'nmcli failed'
                return jsonify({'success': False, 'error': err}), 500

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/add', methods=['POST'])
    @require_auth(self.auth_manager)
    def wifi_add_connection():
        """Add a new WiFi connection."""
        try:
            data = request.get_json()
            ssid = (data.get('ssid') or '').strip()
            password = (data.get('password') or '').strip()
            hidden = data.get('hidden', False)

            if not ssid:
                return jsonify({'success': False, 'error': 'SSID is required'}), 400
            if password and len(password) < 8:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

            iface = self._detect_wifi_interface()

            # Build nmcli command to add the connection (don't activate it)
            cmd = ['connection', 'add', 'type', 'wifi', 'ifname', iface,
                   'con-name', ssid, 'ssid', ssid,
                   'connection.autoconnect', 'yes']
            if hidden:
                cmd += ['802-11-wireless.hidden', 'yes']

            result = self._nmcli(cmd, timeout=15)
            if result is None or result.returncode != 0:
                err = (result.stderr or result.stdout or '').strip() if result else 'nmcli failed'
                return jsonify({'success': False, 'error': err}), 500

            # Set password if provided (WPA-PSK)
            if password:
                self._nmcli(['connection', 'modify', ssid,
                             'wifi-sec.key-mgmt', 'wpa-psk',
                             'wifi-sec.psk', password])

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/priority', methods=['POST'])
    @require_auth(self.auth_manager)
    def wifi_set_priority():
        """Set preferred WiFi by adjusting autoconnect-priority."""
        try:
            data = request.get_json()
            uuid = (data.get('uuid') or '').strip()
            priority = data.get('priority', 100)

            if not uuid:
                return jsonify({'success': False, 'error': 'UUID is required'}), 400

            result = self._nmcli(['connection', 'modify', uuid,
                                  'connection.autoconnect-priority', str(int(priority))])
            if result is None or result.returncode != 0:
                err = (result.stderr or result.stdout or '').strip() if result else 'nmcli failed'
                return jsonify({'success': False, 'error': err}), 500

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/scan', methods=['GET'])
    @require_auth(self.auth_manager)
    def wifi_scan_networks():
        """Scan for nearby WiFi networks."""
        try:
            import time as _time

            iface = self._detect_wifi_interface()

            # Get saved connection profiles, resolved to their *actual* SSID.
            # A profile's name can differ from its SSID (NM appends a
            # disambiguation suffix like "-1" on name conflicts, or a profile
            # can simply be renamed) — comparing against the name directly
            # missed those cases, including the currently-connected network
            # whenever its profile name didn't happen to match its SSID.
            saved_result = self._nmcli(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'])
            profile_ssids = {}  # profile name -> real SSID
            if saved_result and saved_result.returncode == 0:
                for line in saved_result.stdout.splitlines():
                    parts = line.strip().split(':', 2)
                    if len(parts) < 3:
                        continue
                    name, uuid, conn_type = parts[0], parts[1], parts[2]
                    if conn_type not in ('wifi', '802-11-wireless'):
                        continue
                    if self._is_setup_hotspot_connection(name):
                        continue
                    ssid = name
                    detail = self._nmcli_read(['-t', '-f', '802-11-wireless.ssid', 'connection', 'show', uuid])
                    if detail and detail.returncode == 0:
                        for dline in detail.stdout.splitlines():
                            if dline.startswith('802-11-wireless.ssid:'):
                                ssid = dline.split(':', 1)[1].strip() or name
                                break
                    profile_ssids[name] = ssid
            saved_ssids = set(profile_ssids.values())

            own_ssid = self._setup_ssid_from_mac(iface) if hasattr(self, '_setup_ssid_from_mac') else None

            # Parse 'iw scan' output directly rather than reading results
            # back via nmcli: nmcli reports zero networks for devices it
            # doesn't currently manage (e.g. if the setup hotspot happens
            # to be active), even though the kernel-level scan succeeds.
            iw_networks = self._scan_wifi_via_iw(iface, own_ssid=own_ssid)
            if iw_networks:
                # A raw 'iw scan' has no concept of NetworkManager's connection
                # state, so _scan_wifi_via_iw() can't know which network (if any)
                # is currently active — cross-reference against nmcli separately,
                # resolving the active profile's name to its real SSID too.
                current_status = self._current_wifi_status(iface)
                current_ssid = None
                if current_status.get('connected'):
                    active_name = current_status.get('connection')
                    current_ssid = profile_ssids.get(active_name, active_name)
                for n in iw_networks:
                    n['saved'] = n['ssid'] in saved_ssids
                    n['in_use'] = bool(current_ssid) and n['ssid'] == current_ssid
                return jsonify({'success': True, 'networks': iw_networks})

            # Fallback: nmcli (works when the interface is NM-managed)
            self._nmcli(['device', 'wifi', 'rescan', 'ifname', iface])
            _time.sleep(2)

            result = self._nmcli_read([
                '-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY',
                'device', 'wifi', 'list', 'ifname', iface,
            ])
            if result is None or result.returncode != 0:
                return jsonify({'success': False, 'error': 'Scan failed'}), 500

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
                # Skip our own hotspot
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
                    'saved': ssid in saved_ssids,
                })

            networks.sort(key=lambda n: n.get('signal', 0), reverse=True)
            return jsonify({'success': True, 'networks': networks})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/connect', methods=['POST'])
    @require_auth(self.auth_manager)
    def wifi_connect():
        """Connect to a saved WiFi network by UUID."""
        try:
            data = request.get_json()
            uuid = (data.get('uuid') or '').strip()
            if not uuid:
                return jsonify({'success': False, 'error': 'UUID is required'}), 400

            result = self._nmcli(['connection', 'up', uuid], timeout=30)
            if result is None or result.returncode != 0:
                err = (result.stderr or result.stdout or '').strip() if result else 'Connection failed'
                return jsonify({'success': False, 'error': err}), 500

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/wifi/modify', methods=['POST'])
    @require_auth(self.auth_manager)
    def wifi_modify_connection():
        """Modify password of a saved WiFi connection."""
        try:
            data = request.get_json()
            uuid = (data.get('uuid') or '').strip()
            password = (data.get('password') or '').strip()

            if not uuid:
                return jsonify({'success': False, 'error': 'UUID is required'}), 400
            if password and len(password) < 8:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

            if password:
                result = self._nmcli(['connection', 'modify', uuid,
                                      'wifi-sec.key-mgmt', 'wpa-psk',
                                      'wifi-sec.psk', password])
                if result is None or result.returncode != 0:
                    err = (result.stderr or result.stdout or '').strip() if result else 'Modify failed'
                    return jsonify({'success': False, 'error': err}), 500

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    # ── Device Power Management API ────────────────────────────────────

    def _wait_for_display_idle(action, timeout=120):
        """Block until no e-ink refresh is in flight, or the wait runs out.

        Cutting power part-way through a refresh leaves the waveform unfinished
        and DC bias sitting on the pixels, which is the one thing an e-ink panel
        must not be subjected to. A 13.3" panel takes over half a minute, and
        these routes previously powered off two seconds after the click.

        Bounded rather than an unconditional wait: the vendor driver's busy-pin
        polling has no timeout of its own, so a panel that has stopped answering
        would otherwise make the device impossible to turn off from the web UI.
        """
        lock = getattr(self, '_display_worker_lock', None)
        if lock is None:
            return
        if lock.acquire(timeout=timeout):
            lock.release()
            print(f"✅ Display idle — safe to {action}")
        else:
            print(f"⚠️ Display lock timeout after {timeout}s — {action} anyway; "
                  f"the panel may be left mid-refresh")
    @self.app.route('/api/system/restart-service', methods=['POST'])
    @require_auth(self.auth_manager)
    def restart_service():
        """Restart the mempaper service."""
        try:
            def _do_restart():
                time.sleep(1)
                _wait_for_display_idle('restart')
                subprocess.run(
                    ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                    timeout=30
                )
            threading.Thread(target=_do_restart, daemon=True).start()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/system/reboot', methods=['POST'])
    @require_auth(self.auth_manager)
    def reboot_device():
        """Reboot the entire device."""
        try:
            def _do_reboot():
                # Mark this as an authenticated, intentional reboot so
                # _check_power_cycle_reset() on the next boot doesn't count it
                # toward the panic-recovery threshold (see GRACEFUL_REBOOT_MARKER_PATH).
                try:
                    os.makedirs('cache', exist_ok=True)
                    with open(self.GRACEFUL_REBOOT_MARKER_PATH, 'w', encoding='utf-8') as f:
                        f.write('')
                except OSError as e:
                    print(f'⚠️ Could not write graceful-reboot marker: {e}')
                time.sleep(2)
                _wait_for_display_idle('reboot')
                subprocess.run(
                    ['sudo', 'systemctl', 'reboot'],
                    timeout=30
                )
            threading.Thread(target=_do_reboot, daemon=True).start()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/system/shutdown', methods=['POST'])
    @require_auth(self.auth_manager)
    def shutdown_device():
        """Shut down (power off) the device."""
        try:
            def _do_shutdown():
                time.sleep(2)
                _wait_for_display_idle('power off')
                subprocess.run(
                    ['sudo', 'systemctl', 'poweroff'],
                    timeout=30
                )
            threading.Thread(target=_do_shutdown, daemon=True).start()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    # ── SSH Key Management API ─────────────────────────────────────────────
    # Marker lines that delimit the mempaper-managed section inside authorized_keys.
    # All lines outside this block are never touched by the app.
    _SSH_BLOCK_START = '# BEGIN mempaper-managed'
    _SSH_BLOCK_END = '# END mempaper-managed'

    def _ssh_block_keys(content: str) -> tuple[list, bool]:
        """Return (keys_in_block, block_found).

        If no block exists yet (first use / legacy file) block_found is False
        and we return all non-comment keys so the UI shows existing keys.
        """
        has_block = _SSH_BLOCK_START in content
        in_block = False
        all_keys: list = []
        block_keys: list = []
        for line in content.splitlines():
            s = line.strip()
            if s == _SSH_BLOCK_START:
                in_block = True
                continue
            if s == _SSH_BLOCK_END:
                in_block = False
                continue
            if s and not s.startswith('#'):
                all_keys.append(s)
                if in_block:
                    block_keys.append(s)
        return (block_keys if has_block else all_keys), has_block

    def _update_ssh_block(existing_content: str, valid_keys: list) -> str:
        """Splice the mempaper block into authorized_keys content.

        Lines outside the block are preserved verbatim. Only the block
        itself is replaced, so pre-existing manually-added keys are safe.
        """
        lines = existing_content.splitlines(keepends=True)
        kept: list = []
        in_block = False
        for line in lines:
            s = line.strip()
            if s == _SSH_BLOCK_START:
                in_block = True
                continue
            if s == _SSH_BLOCK_END:
                in_block = False
                continue
            if not in_block:
                kept.append(line)

        result = ''.join(kept).rstrip('\n')
        if result:
            result += '\n'
        if valid_keys:
            if result:
                result += '\n'
            result += _SSH_BLOCK_START + '\n'
            result += ''.join(k + '\n' for k in valid_keys)
            result += _SSH_BLOCK_END + '\n'
        return result

    @self.app.route('/api/system/ssh-keys', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_ssh_keys():
        """Return mempaper-managed SSH public keys from the service user's authorized_keys."""
        try:
            home_dir = os.path.expanduser('~')
            auth_keys_path = os.path.join(home_dir, '.ssh', 'authorized_keys')
            keys: list = []
            if os.path.exists(auth_keys_path):
                with open(auth_keys_path, encoding='utf-8') as f:
                    content = f.read()
                keys, _ = _ssh_block_keys(content)
            return jsonify({'success': True, 'keys': keys})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/system/ssh-keys', methods=['POST'])
    @require_auth(self.auth_manager)
    def save_ssh_keys():
        """Update only the mempaper-managed block in both authorized_keys files."""
        import re as _re
        SSH_KEY_RE = _re.compile(
            r'^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(?:256|384|521)'
            r'|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)'
            r'\s+[A-Za-z0-9+/]+=*(\s+\S.*)?$'
        )
        try:
            data = request.json or {}
            raw_keys = data.get('keys', [])

            valid_keys = []
            for key in raw_keys:
                key = key.strip()
                if not key or key.startswith('#'):
                    continue
                if not SSH_KEY_RE.match(key):
                    return jsonify({
                        'success': False,
                        'error': f'Invalid SSH public key: {key[:50]}...'
                    }), 400
                valid_keys.append(key)

            # ── Service user's own authorized_keys (no sudo needed) ───────
            # Wrapped non-fatally: ProtectSystem=strict in the service unit
            # makes the service user's home dir read-only when running under
            # systemd.  The pi-user sudo block below is what actually grants
            # SSH access; this write is best-effort.
            auth_keys_path = None
            wrote_service_user = False
            try:
                home_dir = os.path.expanduser('~')
                ssh_dir = os.path.join(home_dir, '.ssh')
                os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
                auth_keys_path = os.path.join(ssh_dir, 'authorized_keys')
                existing = ''
                if os.path.exists(auth_keys_path):
                    with open(auth_keys_path, encoding='utf-8') as f:
                        existing = f.read()
                new_content = _update_ssh_block(existing, valid_keys)
                with open(auth_keys_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                os.chmod(auth_keys_path, 0o600)
                wrote_service_user = True
            except OSError as own_err:
                print(f'⚠️ SSH: could not update service-user authorized_keys: {own_err}')

            # ── pi user's authorized_keys (via sudo, preserve non-mempaper keys) ──
            pi_auth_keys = '/home/pi/.ssh/authorized_keys'
            wrote_pi = False
            if auth_keys_path != pi_auth_keys:
                try:
                    subprocess.run(
                        ['sudo', 'mkdir', '-p', '/home/pi/.ssh'],
                        check=True, capture_output=True, timeout=10
                    )
                    # Read current content first so non-mempaper keys are preserved
                    cat_result = subprocess.run(
                        ['sudo', 'cat', pi_auth_keys],
                        capture_output=True, text=True, timeout=10
                    )
                    pi_existing = cat_result.stdout if cat_result.returncode == 0 else ''
                    pi_new = _update_ssh_block(pi_existing, valid_keys)
                    result = subprocess.run(
                        ['sudo', 'tee', pi_auth_keys],
                        input=pi_new, text=True, capture_output=True, timeout=10
                    )
                    if result.returncode == 0:
                        subprocess.run(['sudo', 'chmod', '700', '/home/pi/.ssh'],
                                       capture_output=True, timeout=10)
                        subprocess.run(['sudo', 'chmod', '600', pi_auth_keys],
                                       capture_output=True, timeout=10)
                        wrote_pi = True
                    else:
                        print('⚠️ SSH: failed to write /home/pi/.ssh/authorized_keys')
                except Exception as pi_err:
                    print(f'⚠️ SSH: could not update pi authorized_keys: {pi_err}')
            else:
                # Service user IS pi — the service-user write already covered this path
                wrote_pi = wrote_service_user

            if not wrote_service_user and not wrote_pi:
                return jsonify({
                    'success': False,
                    'error': 'Could not write authorized_keys — check service logs: sudo journalctl -u mempaper.service'
                }), 500

            return jsonify({'success': True, 'key_count': len(valid_keys)})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500

    @self.app.route('/api/system/lan-ip', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_lan_ip():
        """Return the device's LAN IP address."""
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return jsonify({'success': True, 'ip': ip})
        except Exception as e:
            return jsonify({'success': False, 'error': _safe_error(e)}), 500
