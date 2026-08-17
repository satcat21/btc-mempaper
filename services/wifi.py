"""Wi-Fi and the setup hotspot: interface detection, nmcli wrappers, hostapd
and captive-portal DNS, the onboarding e-ink screens, and the recovery
monitor that brings the radio back after a dropout.
"""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time


class WifiHotspotMixin:
    """Wi-Fi and the setup hotspot: interface detection, nmcli wrappers, hostapd"""

    def _has_saved_wifi_connections(self):
        """Return True if NetworkManager has at least one saved client Wi-Fi connection.

        Excludes the mempaper-setup AP profile — it is not a client network.
        Caches the last successful result so a transient nmcli timeout or error
        while NM is busy reconnecting does not falsely appear as 'no saved
        networks' and trigger an immediate hotspot switch.
        """
        result = self._nmcli_read(['-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if result is None or result.returncode != 0:
            # nmcli can time out while NM is busy with a rescan/reconnect.
            # Use the cached value rather than defaulting to False.
            if self._saved_wifi_known is not None:
                print('⚠️ nmcli connection query failed — using cached saved-networks result: '
                      + str(self._saved_wifi_known))
                return self._saved_wifi_known
            return False
        has = False
        client_wifi = []
        for line in result.stdout.splitlines():
            parts = line.strip().rsplit(':', 1)  # rsplit: TYPE is always the last field
            if len(parts) < 2:
                continue
            name, conn_type = parts[0], parts[1]
            if conn_type not in ('wifi', '802-11-wireless'):
                continue
            if self._is_setup_hotspot_connection(name):
                continue  # don't count our own AP profile as a saved client network
            client_wifi.append(name)
            has = True
        if client_wifi:
            print(f'📶 Saved client WiFi profiles in NM: {", ".join(client_wifi)}')
        else:
            print('📶 No saved client WiFi profiles in NM')
        self._saved_wifi_known = has
        return has

    def _has_saved_wifi_connections_on_disk(self):
        """Check for saved WiFi profiles via a root-owned wrapper, without nmcli.

        Returns True/False, or None if the wrapper isn't installed (caller
        should fall back to the nmcli-based check in that case).
        """
        wrapper = '/usr/local/bin/mempaper-has-saved-wifi'
        if not os.path.exists(wrapper):
            return None
        try:
            result = subprocess.run(['sudo', wrapper], capture_output=True, timeout=10)
        except Exception:
            return None
        return result.returncode == 0

    def _wait_for_nm_ready(self, max_attempts=12):
        """Poll until NetworkManager's D-Bus service actually responds, with back-off.

        Returns the detected WiFi interface name once ready, or None if NM
        never responded within the attempt budget.
        """
        interface = None
        for wait in range(max_attempts):
            interface = self._detect_wifi_interface()
            if interface:
                probe = self._nmcli_read(['-t', '-f', 'RUNNING', 'general', 'status'])
                if probe is not None and probe.returncode == 0:
                    return interface
            delay = min(wait + 1, 5)
            print(f'⏳ Waiting for NetworkManager to be ready (attempt {wait + 1}/{max_attempts}, retry in {delay}s)...')
            time.sleep(delay)
        return None

    def _startup_wifi_check(self):
        """Called once at startup.
                - If already connected: nothing to do.
                - If disconnected and no saved networks: start hotspot immediately.
                - If disconnected and saved networks exist: give NetworkManager a short
                    startup grace window to connect, then start hotspot if still offline.

        Includes retries with back-off because NetworkManager may not be fully
        ready right after boot on the Pi Zero W.
        """
        if os.name == 'nt':
            return
        if shutil.which('nmcli') is None:
            return

        # Lift a persisted software rfkill block before anything else.  This
        # can survive a reboot (e.g. NetworkManager.state's WirelessEnabled
        # saved as false) independent of the WiFi country code, and blocks
        # both station-mode WiFi and the hostapd setup AP identically.
        # Under heavy boot-time system load this call can itself time out;
        # an uncaught TimeoutExpired here would crash this whole thread
        # before ever reaching the saved-networks check or hotspot bring-up
        # below, silently leaving the device with no way to onboard.
        if shutil.which('rfkill'):
            try:
                subprocess.run(['sudo', 'rfkill', 'unblock', 'wifi'], capture_output=True, timeout=5)
            except subprocess.TimeoutExpired:
                print('⚠️ rfkill unblock timed out — continuing anyway')

        # With nothing saved to reconnect to, we only need to tell NM to
        # release the interface — no need to wait for it to be ready first.
        fs_interface = self._detect_wifi_interface_fs_only()
        if fs_interface and self._has_saved_wifi_connections_on_disk() is False:
            # The saved-network profile file is written by netplan/NetworkManager's
            # own startup (netplan generate -> /run/NetworkManager/system-connections/),
            # which can still be mid-reload right when this runs.
            no_saved_confirmed = True
            for _ in range(8):
                time.sleep(3)
                if self._has_saved_wifi_connections_on_disk() is not False:
                    no_saved_confirmed = False
                    break
            if no_saved_confirmed:
                print('📶 No saved Wi-Fi networks on disk — starting setup hotspot without waiting for NetworkManager')
                if not self._bring_up_setup_hotspot_with_retry(fs_interface):
                    self._write_setup_mode_flag(True, ssid=self._setup_ssid_from_mac(fs_interface), interface=fs_interface)
                    print('⚠️ Hotspot failed at startup — recovery monitor will retry')
                return

        # Wait for NetworkManager to become operational.  On the Pi Zero W it
        # can take 10-30s after systemd starts the service before nmcli
        # commands actually succeed.
        interface = self._wait_for_nm_ready()
        if interface is None:
            print('⚠️ NetworkManager not ready after retries — will rely on recovery monitor')
            return

        # Remove any stale setup-hotspot profiles before checking connectivity —
        # an old autoconnect profile could mask a real outage or broadcast the
        # wrong SSID before the app had a chance to recreate it.
        self._cleanup_legacy_setup_hotspots()

        status = self._current_wifi_status(interface)
        if status.get('connected'):
            print('📡 Wi-Fi connected at startup — skipping setup hotspot')
            return

        has_saved = self._has_saved_wifi_connections()
        if not has_saved:
            # No saved Wi-Fi at all: factory / freshly-flashed device.
            print('📶 No saved Wi-Fi networks — starting setup hotspot for first-time provisioning')
            if not self._bring_up_setup_hotspot_with_retry(interface):
                self._write_setup_mode_flag(True, ssid=self._setup_ssid_from_mac(interface), interface=interface)
                print('⚠️ Hotspot failed at startup — recovery monitor will retry')
            return

        # Saved Wi-Fi exists but we are currently offline.
        startup_wait = int(self.config.get('wifi_startup_connect_wait_seconds', 45))
        startup_wait = max(0, startup_wait)
        poll_seconds = 5
        print(
            '📡 Saved Wi-Fi networks exist but not connected at startup — '
            f'waiting up to {startup_wait}s before enabling setup hotspot'
        )

        deadline = time.time() + startup_wait
        last_connect_try = 0.0
        while time.time() < deadline:
            now = time.time()
            if now - last_connect_try >= 10:
                last_connect_try = now
                self._nmcli(['device', 'connect', interface], timeout=20)

            probe = self._current_wifi_status(interface)
            if probe.get('connected'):
                print('✅ Wi-Fi connected during startup grace window')
                return
            time.sleep(poll_seconds)

        print('📶 Startup grace expired without Wi-Fi — enabling setup hotspot')
        if not self._bring_up_setup_hotspot_with_retry(interface):
            self._write_setup_mode_flag(True, ssid=self._setup_ssid_from_mac(interface), interface=interface)
            print('⚠️ Hotspot failed at startup — recovery monitor will retry')

    def _bring_up_setup_hotspot_with_retry(self, interface, max_attempts=4):
        """Try to bring up the setup hotspot with retries and back-off.

        NetworkManager can reject AP-mode activation right after boot if the
        Wi-Fi radio or driver isn't fully initialised yet.  Retrying after a
        short delay makes the first-boot experience much more reliable.
        """
        for attempt in range(1, max_attempts + 1):
            if self._bring_up_setup_hotspot(interface):
                return True
            if attempt < max_attempts:
                delay = attempt * 5  # 5s, 10s, 15s
                print(f'⚠️ Hotspot attempt {attempt}/{max_attempts} failed — retrying in {delay}s')
                time.sleep(delay)
        return False

    def _is_setup_mode_enabled(self):
        if not os.path.exists(self.setup_mode_flag_path):
            return False
        try:
            with open(self.setup_mode_flag_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return bool(data.get('enabled', False))
        except Exception:
            return False

    def _setup_mode_payload(self):
        payload = {
            'enabled': False,
            'ssid': 'mempaper-0000',
            'interface': 'wlan0',
        }
        if not os.path.exists(self.setup_mode_flag_path):
            return payload
        try:
            with open(self.setup_mode_flag_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                payload.update(data)
        except Exception:
            pass
        return payload

    def _perform_user_data_reset(self):
        """Clear admin credentials and all sensitive user data.

        Called from the setup-page reset button and from the multi-power-cycle
        factory reset path.  Reuses the same logic as delivery_state.py but
        runs inside the live app process.
        """
        # 1. Clear admin users (same keys as delivery_state.clear_admin_users)
        keys_to_remove = [
            'admin_users', 'admin_password_hash', 'admin_username',
            # Wallet / monitoring
            'wallet_balance_addresses_with_comments',
            'block_reward_addresses_table',
            # Bitaxe
            'bitaxe_miner_table',
            # Donation webhook
            'webhook_relay_ws_url',
            # Mempool auth
            'mempool_username',
            'mempool_password',
        ]

        full_cfg = self.config_manager.get_current_config()
        removed = [k for k in keys_to_remove if k in full_cfg]

        # Reset list/table fields to empty instead of deleting (keeps schema intact)
        list_fields = {
            'wallet_balance_addresses_with_comments': [],
            'block_reward_addresses_table': [],
            'bitaxe_miner_table': [],
        }
        for k in keys_to_remove:
            if k in list_fields:
                full_cfg[k] = list_fields[k]
            else:
                full_cfg.pop(k, None)

        # Also reset the show-* toggles so cleared blocks don't show empty
        full_cfg['show_wallet_balances_block'] = False
        full_cfg['show_bitaxe_block'] = False
        full_cfg['show_donation_block'] = False

        # Persist via secure config manager (handles encrypted fields)
        if self.config_manager.secure_manager:
            if not self.config_manager.secure_manager.save_secure_config(full_cfg):
                print('❌ Failed to persist cleared admin credentials to disk — '
                      'device will still show as configured after reboot!')
        else:
            cfg_path = os.path.join('config', 'config.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(full_cfg, f, indent=2)

        # Update in-memory config
        for k in keys_to_remove:
            if k in list_fields:
                self.config[k] = list_fields[k]
                self.config_manager.config[k] = list_fields[k]
            else:
                self.config.pop(k, None)
                self.config_manager.config.pop(k, None)
        self.config['show_wallet_balances_block'] = False
        self.config['show_bitaxe_block'] = False
        self.config['show_donation_block'] = False

        # 2. Clear donation cache files
        for path in [self._donations_file,
                     os.path.join('cache', 'donations.json')]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._latest_donation = None
        self._highest_donation = None
        self._donation_history = []

        # 3. Clear wallet / observer / secure caches
        for cache_file in ['cache/wallet_balances.json',
                           'cache/observer_cache.json',
                           'cache/bitaxe_cache.json',
                           'cache/async_wallet_address_cache.sensitive.json',
                           'cache/cache.sensitive.json',
                           'cache/mobile_tokens.sensitive.json',
                           'cache/mobile_tokens.secure.json',
                           'cache/mobile_tokens.json']:
            try:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            except OSError:
                pass

        # Deleting the file above doesn't touch UnifiedSecureCache's in-memory
        # copy — this reset runs inside the already-running process (not a
        # fresh restart), and get_cached_wallet_balances() etc. read straight
        # from that in-memory dict, not from disk. Without this, the old
        # balance/hashrate keeps being served from memory even though the
        # config now has no addresses/miners and the file is gone.
        try:
            from managers.unified_secure_cache import get_unified_cache
            _uc = get_unified_cache()
            for _cache_type in ('wallet_balance_cache', 'block_reward_cache', 'optimized_balance_cache'):
                _uc.clear_cache(_cache_type)
        except Exception as e:
            print(f'⚠️ Could not clear in-memory unified cache: {e}')

        # Also drop the wallet API's own last-fetched-result attribute, if any.
        try:
            wallet_api = getattr(self.image_renderer, 'wallet_api', None)
            if wallet_api is not None and hasattr(wallet_api, '_wallet_cache'):
                wallet_api._wallet_cache = None
        except Exception:
            pass

        # 4. Strip mempaper-managed SSH keys — a reset that leaves old SSH
        # access in place while wiping the admin password would be a real
        # security gap for the "locked out, need a clean device" use case.
        self._clear_managed_ssh_keys()

        if removed:
            print(f"🧹 Cleared sensitive data: {', '.join(removed)}")
        else:
            print("ℹ️ No sensitive data found to clear")

    def _clear_managed_ssh_keys(self):
        """Strip the mempaper-managed SSH key block from both authorized_keys
        files (the service user's own, and the pi user's — see the
        /api/system/ssh-keys routes for the canonical splice format this
        mirrors). Lines outside the BEGIN/END markers are left untouched, same
        as the routes: this only removes keys mempaper itself provisioned.
        """
        ssh_start = '# BEGIN mempaper-managed'
        ssh_end = '# END mempaper-managed'

        def _without_block(content):
            if ssh_start not in content:
                return None  # nothing to do
            kept = []
            in_block = False
            for line in content.splitlines(keepends=True):
                s = line.strip()
                if s == ssh_start:
                    in_block = True
                    continue
                if s == ssh_end:
                    in_block = False
                    continue
                if not in_block:
                    kept.append(line)
            result = ''.join(kept).rstrip('\n')
            return result + '\n' if result else ''

        own_path = os.path.join(os.path.expanduser('~'), '.ssh', 'authorized_keys')
        try:
            if os.path.exists(own_path):
                with open(own_path, encoding='utf-8') as f:
                    new_content = _without_block(f.read())
                if new_content is not None:
                    with open(own_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f'🧹 Cleared mempaper-managed SSH keys from {own_path}')
        except OSError as e:
            print(f'⚠️ Could not clear SSH keys from {own_path}: {e}')

        pi_path = '/home/pi/.ssh/authorized_keys'
        if own_path == pi_path:
            return  # service user IS pi — already handled above
        try:
            cat_result = subprocess.run(
                ['sudo', 'cat', pi_path], capture_output=True, text=True, timeout=10
            )
            if cat_result.returncode != 0:
                return  # file doesn't exist / not readable — nothing to clear
            new_content = _without_block(cat_result.stdout)
            if new_content is not None:
                subprocess.run(
                    ['sudo', 'tee', pi_path], input=new_content,
                    capture_output=True, text=True, timeout=10
                )
                print(f'🧹 Cleared mempaper-managed SSH keys from {pi_path}')
        except Exception as e:
            print(f'⚠️ Could not clear SSH keys from {pi_path}: {e}')

    def _write_setup_mode_flag(self, enabled, ssid=None, interface=None):
        try:
            os.makedirs(os.path.dirname(self.setup_mode_flag_path), exist_ok=True)
        except Exception:
            pass

        if not enabled:
            try:
                if os.path.exists(self.setup_mode_flag_path):
                    os.remove(self.setup_mode_flag_path)
            except OSError:
                pass
            return

        payload = {
            'enabled': True,
            'ssid': ssid,
            'interface': interface,
            'timestamp': int(time.time()),
        }
        try:
            with open(self.setup_mode_flag_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            print(f"⚠️ Could not write setup mode flag: {e}")

    def _detect_wifi_interface(self):
        result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status'])
        if result is not None and result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split(':')
                if len(parts) < 2:
                    continue
                device, dev_type = parts[0], parts[1]
                if device and dev_type == 'wifi':
                    return device

        preferred = '/sys/class/net/wlan0'
        if os.path.exists(preferred):
            return 'wlan0'

        net_root = '/sys/class/net'
        if not os.path.isdir(net_root):
            return 'wlan0'

        for iface in sorted(os.listdir(net_root)):
            if os.path.isdir(os.path.join(net_root, iface, 'wireless')):
                return iface
        return 'wlan0'

    def _detect_wifi_interface_fs_only(self):
        """Find the WiFi interface via /sys/class/net, without nmcli.

        Returns None (rather than guessing 'wlan0') when nothing is found.
        """
        preferred = '/sys/class/net/wlan0'
        if os.path.exists(preferred):
            return 'wlan0'

        net_root = '/sys/class/net'
        if not os.path.isdir(net_root):
            return None

        for iface in sorted(os.listdir(net_root)):
            if os.path.isdir(os.path.join(net_root, iface, 'wireless')):
                return iface
        return None

    def _has_ap_station(self, interface):
        """Return True if at least one client device is associated with our AP.

        Uses 'iw dev <iface> station dump' which lists connected stations.
        Falls back to False (allow probe) if iw is unavailable.
        """
        if shutil.which('iw') is None:
            return False
        try:
            result = subprocess.run(
                ['iw', 'dev', interface, 'station', 'dump'],
                capture_output=True, text=True, timeout=5,
            )
            # Any output means at least one station is associated
            return bool(result.returncode == 0 and result.stdout.strip())
        except Exception:
            return False

    def _scan_wifi_via_iw(self, interface, own_ssid=None):
        """Scan for nearby WiFi networks by parsing 'iw scan' output directly.

        Do NOT rely on 'nmcli device wifi list' to report the results: nmcli
        only reports scan results for devices NetworkManager currently
        manages, and while the setup hotspot is active this interface has
        been explicitly unmanaged ('nmcli device set <iface> managed no') so
        hostapd can bind it — nmcli silently returns zero networks in that
        state even though the kernel-level scan itself succeeds. Parsing
        'iw scan' output ourselves works regardless of NM's managed state.

        Returns [] on any failure so callers can fall back to nmcli.
        """
        if shutil.which('iw') is None:
            return []
        try:
            result = subprocess.run(
                ['sudo', 'iw', 'dev', interface, 'scan', 'passive'],
                capture_output=True, text=True, timeout=15,
            )
        except Exception:
            return []
        if result.returncode != 0 or not result.stdout:
            return []

        networks = []
        seen = set()
        current = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if line.startswith('BSS '):
                if current and current.get('ssid') and current['ssid'] not in seen:
                    seen.add(current['ssid'])
                    networks.append(current)
                current = {'ssid': '', 'signal': 0, 'security': ''}
                continue
            if current is None:
                continue
            if stripped.startswith('signal:'):
                try:
                    dbm = float(stripped.split(':', 1)[1].strip().split()[0])
                    # Rough dBm→percent mapping matching typical WiFi-manager
                    # conventions (-100 dBm = 0%, -50 dBm and better = 100%).
                    current['signal'] = max(0, min(100, int(2 * (dbm + 100))))
                except (ValueError, IndexError):
                    pass
            elif stripped.startswith('SSID:'):
                ssid = stripped.split(':', 1)[1].strip()
                if ssid:
                    current['ssid'] = ssid
            elif stripped.startswith('RSN:'):
                current['security'] = 'WPA2'
            elif stripped.startswith('WPA:') and not current['security']:
                current['security'] = 'WPA'
        if current and current.get('ssid') and current['ssid'] not in seen:
            seen.add(current['ssid'])
            networks.append(current)

        if own_ssid:
            networks = [n for n in networks if n['ssid'] != own_ssid]

        for n in networks:
            n['open'] = not n['security']
            n['in_use'] = False
        networks.sort(key=lambda n: n.get('signal', 0), reverse=True)
        return networks

    def _nmcli(self, args, timeout=25):
        """Run nmcli with sudo for write operations (connection add/delete/up/down, radio)."""
        if shutil.which('nmcli') is None:
            return None
        # Use 'sudo nmcli' on Linux so the service user (non-root) can manage
        # NM connections.  The passwordless sudoers rule is installed by
        # tools/install_permissions.sh.
        cmd = (['sudo', 'nmcli'] if os.name != 'nt' else ['nmcli']) + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

    def _nmcli_read(self, args, timeout=10):
        """Run nmcli without sudo for read-only queries (device status, connection list).

        Avoids PAM session logging that occurs with every sudo invocation.
        Plain nmcli is sufficient for status reads — no elevated privileges needed.
        """
        if shutil.which('nmcli') is None:
            return None
        try:
            return subprocess.run(
                ['nmcli'] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

    def _is_setup_hotspot_connection(self, connection_name):
        """Return True when the active connection is a setup hotspot profile."""
        conn = (connection_name or '').strip()
        if not conn:
            return False
        return conn == 'mempaper-setup' or conn.startswith('mempaper-setup_')

    def _cleanup_legacy_setup_hotspots(self, ssid=None):
        """Remove any setup-hotspot NM profiles (current or legacy naming, or matching SSID)."""
        result = self._nmcli_read(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'])
        if result is None or result.returncode != 0:
            return

        to_delete = []  # list of (name, uuid) tuples
        for line in result.stdout.splitlines():
            # Format: NAME:UUID:TYPE  — split on first 2 colons only so a
            # connection name containing ':' doesn't break the parse.
            parts = line.split(':', 2)
            if len(parts) < 3:
                continue
            name      = parts[0].strip()
            uuid      = parts[1].strip()
            conn_type = parts[2].strip()
            if conn_type not in ('wifi', '802-11-wireless'):
                continue

            is_setup = (
                name == 'mempaper-setup'
                or name.startswith('mempaper-setup_')
                or name.startswith('mempaper-setup-')
                or name.startswith('mempaper-setup ')   # NM duplicate suffix "mempaper-setup 2" etc.
            )

            # Also match by SSID for profiles with unexpected names
            if not is_setup and ssid:
                detail = self._nmcli_read(['connection', 'show', uuid])
                if detail and detail.returncode == 0:
                    for prop in detail.stdout.splitlines():
                        if '802-11-wireless.ssid' in prop and ':' in prop:
                            if prop.split(':', 1)[1].strip() == ssid:
                                is_setup = True
                            break

            if is_setup:
                to_delete.append((name, uuid))

        for name, uuid in to_delete:
            # Delete by UUID — unambiguous even when multiple profiles share a name.
            self._nmcli(['connection', 'down', uuid])
            self._nmcli(['connection', 'delete', uuid])

    def _current_wifi_status(self, interface):
        result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
        if result is None or result.returncode != 0:
            # nmcli can time out while NM is busy reconnecting.  Return
            # status_known=False so the caller doesn't treat this as a
            # confirmed disconnect and start the outage timer prematurely.
            return {'connected': False, 'connection': '', 'status_known': False}

        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) < 4:
                continue
            dev, dev_type, state, connection = parts[0], parts[1], parts[2], parts[3]
            if dev == interface and dev_type == 'wifi':
                connected = state.startswith('connected') and not self._is_setup_hotspot_connection(connection)
                return {'connected': connected, 'connection': connection, 'status_known': True}

        return {'connected': False, 'connection': '', 'status_known': True}

    def _mac_digest(self, interface):
        """Return the hex SHA-256 digest of the interface permanent MAC address.

        Uses perm_address (the hardware-burned-in MAC) so the derived SSID and
        password are stable regardless of NM MAC randomization on the client
        connection that was active when install.sh ran.
        """
        mac_address = '00:00:00:00:00:00'
        for candidate in (f'/sys/class/net/{interface}/perm_address',
                          f'/sys/class/net/{interface}/address'):
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    val = f.read().strip().lower()
                if val and val != '00:00:00:00:00:00':
                    mac_address = val
                    break
            except OSError:
                continue
        return hashlib.sha256(mac_address.replace(':', '').encode('utf-8')).hexdigest()

    def _setup_ssid_from_mac(self, interface):
        digest = self._mac_digest(interface)
        suffix = f"{int(digest[:8], 16) % 10000:04d}"
        return f"mempaper-{suffix}"

    def _setup_password_from_mac(self, interface):
        """Derive a deterministic 8-char hex WPA2 password from the MAC address.

        Uses bytes 8-16 of the SHA-256 digest so the password is independent
        of the SSID suffix (bytes 0-8) and not guessable from the visible SSID.
        """
        digest = self._mac_digest(interface)
        return digest[8:16]   # 8 lowercase hex chars, always valid WPA2

    # Fixed static address for the setup hotspot — assigned directly via 'ip addr
    # add' (not NM), so it's always known up front rather than detected after
    # the fact.
    _HOTSPOT_IP   = '10.42.0.1'
    _HOTSPOT_CIDR = '10.42.0.1/24'

    # NetworkManager conf.d override marking wlan0 unmanaged; written on
    # reset, removed once WiFi credentials are applied (see below).
    _WLAN0_UNMANAGED_CONF = '/etc/NetworkManager/conf.d/99-mempaper-wlan0-unmanaged.conf'

    def _bring_up_setup_hotspot(self, interface):
        ssid     = self._setup_ssid_from_mac(interface)
        password = self._setup_password_from_mac(interface)
        print(f'📶 Setup hotspot: open AP "{ssid}" — portal password required for setup access')

        # Remove any stale NM AP-mode profile for this SSID before hostapd binds it.
        self._cleanup_legacy_setup_hotspots(ssid=ssid)

        # Track the interface immediately so a failure partway through this
        # method still lets _bring_down_setup_hotspot() restore NM management.
        self._active_hotspot_interface = interface

        # Release the interface from NetworkManager so hostapd can bind it —
        # NM and hostapd cannot both manage the same interface at once.
        self._nmcli(['device', 'set', interface, 'managed', 'no'])
        subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'],
                       capture_output=True, timeout=10)
        subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', interface],
                       capture_output=True, timeout=10)
        addr = subprocess.run(
            ['sudo', 'ip', 'addr', 'add', self._HOTSPOT_CIDR, 'dev', interface],
            capture_output=True, text=True, timeout=10,
        )
        if addr.returncode != 0:
            err = (addr.stderr or addr.stdout or '').strip()
            print(f'❌ Setup hotspot: failed to assign {self._HOTSPOT_CIDR} to {interface} — {err}')
            self._nmcli(['device', 'set', interface, 'managed', 'yes'])
            return False

        # Open AP — no WPA2. A derived password gates access to the /setup page
        # instead. hostapd (not NM's own AP-mode) creates the AP for reliability
        # across driver/kernel combinations.
        if not self._start_hostapd(interface, ssid):
            self._nmcli(['device', 'set', interface, 'managed', 'yes'])
            return False

        # Redirect port 80/443 → Flask port so captive-portal probes
        # (which hit port 80) actually reach our /generate_204 handler.
        self._add_captive_portal_redirect(interface)

        self._start_captive_dns(interface, self._HOTSPOT_IP)

        self._write_setup_mode_flag(True, ssid=ssid, interface=interface)
        print(f"📶 Wi-Fi recovery: setup hotspot enabled ({ssid})")
        if self.e_ink_enabled and not self._onboarding_hotspot_screen_shown:
            self._onboarding_hotspot_screen_shown = True
            threading.Thread(
                target=self._display_onboarding_hotspot_screen,
                args=(ssid, password, interface),
                daemon=True,
            ).start()
        return True

    def _bring_down_setup_hotspot(self):
        self._onboarding_hotspot_screen_shown = False
        self._stop_captive_dns()
        self._remove_captive_portal_redirect()
        self._stop_hostapd()
        interface = self._active_hotspot_interface
        if interface:
            subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', interface],
                           capture_output=True, timeout=10)
            self._nmcli(['device', 'set', interface, 'managed', 'yes'])
        self._cleanup_legacy_setup_hotspots()
        self._write_setup_mode_flag(False)

    def _release_hotspot_for_probe(self, interface):
        """Stop hostapd/dnsmasq and hand the interface back to NM so it can
        scan/connect, without clearing the setup-mode flag.

        Used when probing for a saved network while still in setup mode; the
        caller re-arms the hotspot via _bring_up_setup_hotspot() if the probe
        fails, or fully tears down via _bring_down_setup_hotspot() if it succeeds.
        """
        self._stop_captive_dns()
        self._remove_captive_portal_redirect()
        self._stop_hostapd()
        subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', interface],
                       capture_output=True, timeout=10)
        self._nmcli(['device', 'set', interface, 'managed', 'yes'])

    def _add_captive_portal_redirect(self, interface):
        """Add iptables rules for the captive portal:
          - PREROUTING REDIRECT: port 80/443 → Flask port (captive-portal probes)
          - INPUT ACCEPT: DHCP (UDP 67), DNS (UDP 53), Flask port (TCP)
            (belt+suspenders when nftables service is active with policy drop)
        """
        self._active_hotspot_interface = interface
        if not shutil.which('iptables'):
            print('⚠️ iptables not installed — captive-portal port redirect unavailable (install: sudo apt install iptables)')
            return
        port = self._get_web_port()
        # Allow DHCP broadcasts from hotspot clients through any active firewall.
        for proto, dport in [('udp', 67), ('udp', 53), ('tcp', port)]:
            try:
                result = subprocess.run(
                    ['sudo', 'iptables', '-t', 'filter', '-I', 'INPUT',
                     '-i', interface, '-p', proto, '--dport', str(dport),
                     '-j', 'ACCEPT'],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    print(f'⚠️ iptables INPUT accept {proto}/{dport} failed: {(result.stderr or result.stdout).strip()}')
            except Exception as e:
                print(f'⚠️ iptables INPUT accept {proto}/{dport} error: {e}')
        for src_port in (80, 443):
            try:
                result = subprocess.run(
                    ['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING',
                     '-i', interface, '-p', 'tcp', '--dport', str(src_port),
                     '-j', 'REDIRECT', '--to-port', str(port)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    print(f'⚠️ iptables redirect {src_port}→{port} failed: {(result.stderr or result.stdout).strip()}')
            except Exception as e:
                print(f'⚠️ iptables redirect {src_port}→{port} error: {e}')
        print(f"🔀 Captive-portal redirect: ports 80/443 → {port}, INPUT accept {port}")

        # On Debian Trixie, the default nftables ruleset uses an 'inet filter input'
        # chain (NOT the iptables-nft 'ip filter' chain) with policy drop.  The two
        # namespaces are independent, so our iptables rule above doesn't protect
        # traffic in the native nftables chain.  Insert a rule there directly.
        self._nft_hotspot_handle = None
        if shutil.which('nft'):
            import re as _re
            try:
                r = subprocess.run(
                    ['sudo', 'nft', 'insert', 'rule', 'inet', 'filter', 'input',
                     'iifname', interface, 'accept'],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0:
                    lr = subprocess.run(
                        ['sudo', 'nft', '-a', 'list', 'chain', 'inet', 'filter', 'input'],
                        capture_output=True, text=True, timeout=10,
                    )
                    for line in (lr.stdout or '').splitlines():
                        if f'iifname "{interface}" accept' in line or f'iifname {interface} accept' in line:
                            m = _re.search(r'#\s*handle\s+(\d+)', line)
                            if m:
                                self._nft_hotspot_handle = m.group(1)
                                print(f'🔒 nft inet filter input: accept {interface} (handle {self._nft_hotspot_handle})')
                                break
                else:
                    print(f'⚠️ nft INPUT accept failed (rc={r.returncode}): {(r.stderr or r.stdout or "").strip()}'
                          f' — run install_permissions.sh to add sudoers entry for nft')
            except Exception as e:
                print(f'⚠️ nft accept rule error: {e}')

    def _teardown_interface(self):
        """The interface to build rule-deletion specs against.

        Normally the one the hotspot was raised on, but that attribute is lost
        if the process restarts while the hotspot is up - and the rules outlive
        the process. Fall back to detecting the interface from the filesystem,
        which needs neither nmcli nor sudo and so is safe on a teardown path.
        """
        return self._active_hotspot_interface or self._detect_wifi_interface_fs_only()

    def _remove_captive_portal_redirect(self):
        """Remove all mempaper captive-portal iptables rules (PREROUTING + INPUT)."""
        port = self._get_web_port()
        interface = self._teardown_interface()
        # 'iptables -D' matches on the complete rule spec, so every deletion has
        # to repeat the '-i <interface>' its rule was added with. The PREROUTING
        # deletion below used to omit it: nothing matched, the loop broke on the
        # first failure, and each hotspot cycle appended another redirect pair
        # that outlived the hotspot. The INPUT deletion always passed it, which
        # is why only these accumulated.
        if interface:
            # Remove INPUT accept rules added for DHCP, DNS, and Flask port
            for proto, dport in [('udp', 67), ('udp', 53), ('tcp', port)]:
                for _ in range(5):
                    try:
                        result = subprocess.run(
                            ['sudo', 'iptables', '-t', 'filter', '-D', 'INPUT',
                             '-i', interface, '-p', proto, '--dport', str(dport),
                             '-j', 'ACCEPT'],
                            capture_output=True, timeout=10,
                        )
                        if result.returncode != 0:
                            break
                    except Exception:
                        break
            for src_port in (80, 443):
                # Delete until no matching rule remains (handles duplicates)
                for _ in range(5):
                    try:
                        result = subprocess.run(
                            ['sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING',
                             '-i', interface, '-p', 'tcp', '--dport', str(src_port),
                             '-j', 'REDIRECT', '--to-port', str(port)],
                            capture_output=True, timeout=10,
                        )
                        if result.returncode != 0:
                            break
                    except Exception:
                        break
        else:
            print('⚠️ Captive-portal redirect cleanup skipped — no WiFi interface found')

        # Remove the nft inet filter input rule if we inserted one.
        handle = getattr(self, '_nft_hotspot_handle', None)
        if shutil.which('nft'):
            import re as _re
            if handle:
                try:
                    subprocess.run(
                        ['sudo', 'nft', 'delete', 'rule', 'inet', 'filter', 'input',
                         'handle', handle],
                        capture_output=True, timeout=10,
                    )
                except Exception:
                    pass
                self._nft_hotspot_handle = None
            elif interface:
                # Fallback scan (handles app restart while hotspot was active)
                try:
                    lr = subprocess.run(
                        ['sudo', 'nft', '-a', 'list', 'chain', 'inet', 'filter', 'input'],
                        capture_output=True, text=True, timeout=10,
                    )
                    for line in (lr.stdout or '').splitlines():
                        if f'iifname "{interface}" accept' in line or f'iifname {interface} accept' in line:
                            m = _re.search(r'#\s*handle\s+(\d+)', line)
                            if m:
                                subprocess.run(
                                    ['sudo', 'nft', 'delete', 'rule', 'inet', 'filter', 'input',
                                     'handle', m.group(1)],
                                    capture_output=True, timeout=10,
                                )
                except Exception:
                    pass

    # ── Setup hotspot AP (hostapd) + captive-portal DNS/DHCP (dnsmasq) ───────
    #
    # Both run as on-demand systemd units (mempaper-hostapd.service,
    # mempaper-dnsmasq.service — installed by install_permissions.sh),
    # started/stopped/restarted here via 'sudo systemctl'. systemd supervises
    # the actual processes: crash-restart, journald logging, and clean shutdown.
    #
    #   AP:   hostapd on the interface handed to it by _bring_up_setup_hotspot
    #         (NM releases the interface first via 'nmcli device set managed no').
    #   DNS:  dnsmasq, port 53 (system dnsmasq is masked at install time so
    #         there's no conflict), wildcard address=/#/<ip> resolves all
    #         domains to the Pi.
    #   DHCP: dnsmasq, port 67, range <ip>.10-200, option 114 for Android 11+
    #         captive-portal popup, router/DNS pointing at the hotspot IP.
    #   DoT:  TCP 853 FORWARD REJECT forces Android 9+ to fall back to plain
    #         UDP DNS instead of timing out on a TLS handshake.

    # Under the project's own cache/ dir, not /tmp: mempaper.service's
    # ProtectSystem=strict makes /tmp read-only unless PrivateTmp=true is also
    # set, and PrivateTmp gives this service a /tmp namespace-private to
    # itself — invisible to the independent mempaper-hostapd.service /
    # mempaper-dnsmasq.service units that need to read these files. cache/ is
    # already in this service's ReadWritePaths and has no such isolation.
    _HOSTAPD_CONF     = os.path.join('cache', 'mempaper-hostapd.conf')
    _CAPTIVE_DNS_CONF = os.path.join('cache', 'mempaper-captive-dns.conf')

    def _hostapd_active(self):
        """Return True if mempaper-hostapd.service is currently running."""
        result = subprocess.run(
            ['systemctl', 'is-active', '--quiet', 'mempaper-hostapd.service'], timeout=5,
        )
        return result.returncode == 0

    def _captive_dnsmasq_active(self):
        """Return True if mempaper-dnsmasq.service is currently running."""
        result = subprocess.run(
            ['systemctl', 'is-active', '--quiet', 'mempaper-dnsmasq.service'], timeout=5,
        )
        return result.returncode == 0

    def _wifi_country_code(self):
        """Return the OS-configured WiFi regulatory country code (e.g. 'DE').

        Read via 'iw reg get' (no root needed) rather than raspi-config, since
        the service user may not have permission to invoke raspi-config.
        Falls back to 'US' — the most channel/power-restrictive common
        default — if no regulatory domain is set, rather than leaving hostapd
        without a country_code (which can prevent it from selecting a channel
        at all on some regulatory-domain-unaware installs).
        """
        if shutil.which('iw'):
            try:
                result = subprocess.run(['iw', 'reg', 'get'], capture_output=True, text=True, timeout=5)
                for line in (result.stdout or '').splitlines():
                    line = line.strip()
                    if line.startswith('country '):
                        code = line.split()[1].rstrip(':')
                        if len(code) == 2 and code.isalpha():
                            return code.upper()
            except Exception:
                pass
        return 'US'

    def _start_hostapd(self, interface, ssid):
        """Write the hostapd config and (re)start mempaper-hostapd.service."""
        if not shutil.which('hostapd'):
            print('⚠️ hostapd not installed — setup hotspot unavailable')
            return False

        conf = (
            f'interface={interface}\n'
            f'driver=nl80211\n'
            f'ssid={ssid}\n'
            f'hw_mode=g\n'
            f'channel=6\n'  # explicit channel avoids brcmfmac auto-select failure on kernel 6.6+
            f'country_code={self._wifi_country_code()}\n'
            f'ieee80211d=1\n'  # advertise the country IE so clients honor the regulatory limits
            f'ieee80211n=1\n'
            f'wmm_enabled=1\n'
            f'auth_algs=1\n'
            f'wpa=0\n'  # open AP — captive-portal password gates /setup instead
            f'ignore_broadcast_ssid=0\n'
        )
        try:
            with open(self._HOSTAPD_CONF, 'w', encoding='utf-8') as f:
                f.write(conf)
        except OSError as e:
            print(f'❌ Setup hotspot: could not write hostapd config — {e}')
            return False

        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'mempaper-hostapd.service'],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or '').strip()
            print(f'❌ Setup hotspot: failed to start hostapd — {err}')
            return False

        time.sleep(1)
        active = subprocess.run(
            ['systemctl', 'is-active', '--quiet', 'mempaper-hostapd.service'], timeout=5,
        )
        if active.returncode != 0:
            log = subprocess.run(
                ['journalctl', '-u', 'mempaper-hostapd.service', '-n', '20', '--no-pager'],
                capture_output=True, text=True, timeout=5,
            )
            print(f'❌ Setup hotspot: hostapd exited immediately — {(log.stdout or "").strip()[-400:]}')
            return False

        print(f'✅ Setup hotspot AP started ("{ssid}" on {interface})')
        return True

    def _stop_hostapd(self):
        subprocess.run(['sudo', 'systemctl', 'stop', 'mempaper-hostapd.service'],
                       capture_output=True, timeout=15)
        try:
            os.remove(self._HOSTAPD_CONF)
        except OSError:
            pass

    def _start_captive_dns(self, interface, hotspot_ip):
        """Write the dnsmasq config and (re)start mempaper-dnsmasq.service."""
        if not shutil.which('dnsmasq'):
            print('⚠️ dnsmasq not installed — captive-portal DNS/DHCP unavailable')
        else:
            port   = self._get_web_port()
            prefix = hotspot_ip.rsplit('.', 1)[0]
            conf = (
                f'interface={interface}\n'
                f'bind-dynamic\n'
                f'address=/#/{hotspot_ip}\n'
                f'no-resolv\n'
                f'dhcp-range={prefix}.10,{prefix}.200,255.255.255.0,12h\n'
                f'dhcp-option=option:router,{hotspot_ip}\n'
                f'dhcp-option=option:dns-server,{hotspot_ip}\n'
                f'dhcp-option=114,http://{hotspot_ip}:{port}/\n'
            )
            try:
                with open(self._CAPTIVE_DNS_CONF, 'w', encoding='utf-8') as f:
                    f.write(conf)
            except OSError as e:
                print(f'⚠️ Could not write dnsmasq config: {e}')
                return

            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'mempaper-dnsmasq.service'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or '').strip()
                print(f'⚠️ dnsmasq failed to start: {err}')
                return

            time.sleep(1)
            active = subprocess.run(
                ['systemctl', 'is-active', '--quiet', 'mempaper-dnsmasq.service'], timeout=5,
            )
            if active.returncode != 0:
                print('⚠️ dnsmasq exited immediately — DHCP unavailable '
                      '(check: journalctl -u mempaper-dnsmasq.service)')
                return

            print(f'✅ Captive-portal DNS+DHCP started (all domains → {hotspot_ip}, DHCP {prefix}.10-200)')

        # Block DNS-over-TLS (TCP 853 FORWARD) so Android 9+ falls back to plain
        # UDP DNS quickly instead of timing out on a TLS handshake.
        if shutil.which('iptables'):
            try:
                subprocess.run(
                    ['sudo', 'iptables', '-t', 'filter', '-I', 'FORWARD',
                     '-i', interface, '-p', 'tcp', '--dport', '853',
                     '-j', 'REJECT'],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass

    def _stop_captive_dns(self):
        """Stop the captive-portal dnsmasq and remove all iptables rules it added."""
        # Remove DNS-over-TLS FORWARD block. Same exact-spec rule as the
        # PREROUTING deletions: '-i <interface>' has to repeat what _start_captive_dns
        # added, or the delete matches nothing and the REJECT rule accumulates.
        interface = self._teardown_interface()
        if interface:
            for _ in range(5):
                try:
                    result = subprocess.run(
                        ['sudo', 'iptables', '-t', 'filter', '-D', 'FORWARD',
                         '-i', interface, '-p', 'tcp', '--dport', '853',
                         '-j', 'REJECT'],
                        capture_output=True, timeout=10,
                    )
                    if result.returncode != 0:
                        break
                except Exception:
                    break

        subprocess.run(['sudo', 'systemctl', 'stop', 'mempaper-dnsmasq.service'],
                       capture_output=True, timeout=15)
        try:
            os.remove(self._CAPTIVE_DNS_CONF)
        except OSError:
            pass

    def _get_web_port(self):
        """Return the configured HTTP port (default 5000)."""
        return int(self.config.get('web_port', 5000))

    def _get_hotspot_ip(self, interface):
        """Return the hotspot AP's IP address.

        We assign _HOTSPOT_IP ourselves via 'ip addr add' when bringing up the
        hotspot, so it's always known up front. The kernel-parse fallback below
        is only a defensive check in case the interface somehow ended up with a
        different address.
        """
        import re
        try:
            res = subprocess.run(
                ['ip', '-4', 'addr', 'show', interface],
                capture_output=True, text=True, timeout=5,
            )
            if res.returncode == 0:
                m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', res.stdout)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return self._HOTSPOT_IP

    def _display_onboarding_hotspot_screen(self, ssid, password, interface):
        """Render the two-QR hotspot screen and push it to the e-ink display.

        Tries to stamp QR codes onto the existing delivery-state image so the
        onboarding screen shows the same meme/date as the delivery image.
        Falls back to the standalone onboarding screen if the delivery image
        is not available.
        """
        # Give NM a couple of seconds to finish assigning the AP address.
        time.sleep(2)
        port       = self._get_web_port()
        hotspot_ip = self._get_hotspot_ip(interface)
        # Include the portal password as a URL key so scanning QR2 grants immediate
        # access without manual password entry.  The password is still shown in text so
        # users without a QR scanner can type it in the captive portal page.
        portal_url = f'http://{hotspot_ip}:{port}/setup?key={password}'
        try:
            delivery_eink = os.path.join('cache', 'delivery_eink.png')
            if os.path.exists(delivery_eink):
                from PIL import Image as _Image
                from lib.onboarding_renderer import stamp_qr_codes_on_image
                base_img = _Image.open(delivery_eink).convert('RGB')
                _, path = stamp_qr_codes_on_image(
                    base_img, ssid, password, portal_url, self.config,
                    eink=True)
            else:
                from lib.onboarding_renderer import render_hotspot_screen
                _, path = render_hotspot_screen(ssid, password, portal_url, self.config)
            if path:
                # The portal URL is shown on the panel itself; keeping it out of
                # the log avoids writing setup-session details to the journal.
                print('📺 Displaying hotspot onboarding screen on e-ink')
                self._display_on_epaper_async(path, None, None)
        except Exception as e:
            print(f'⚠️ Could not render hotspot onboarding screen: {e}')

    def _display_onboarding_connected_screen(self):
        """Render the post-connection QR screen, display it, then restore normal
        operation after 60 seconds."""
        import socket as _socket

        # Suppress other e-ink updates while the connected screen is showing
        self._onboarding_connected_active = True

        # Give the OS a moment to assign an IP after the connection settles.
        time.sleep(3)

        ip = None
        for _ in range(5):
            try:
                s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                s.settimeout(2)
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
                s.close()
                break
            except Exception:
                time.sleep(2)

        port       = self._get_web_port()
        access_url = f'http://{ip}:{port}' if ip else f'http://<pi-ip>:{port}'

        try:
            from lib.onboarding_renderer import render_connected_screen
            # Render e-ink version for the display
            eink_img, path = render_connected_screen(access_url, self.config, timeout_seconds=60,
                                                     translations=self.translations)
            if path:
                print(f'📺 Displaying connected onboarding screen on e-ink ({access_url})')
                self._display_on_epaper_async(path, None, None)
                render_start = time.time()

            # Render web version (same screen) and serve it as the dashboard image
            # so the browser shows the connected screen instead of a stale/broken template.
            try:
                web_img, _ = render_connected_screen(access_url, self.config, timeout_seconds=60,
                                                     eink=False, translations=self.translations)
                if web_img:
                    self._save_images_to_disk(web_img, None)
                    self._cache_web_image(web_img)
                    print('📺 Connected screen also set as web dashboard image')
            except Exception:
                pass  # non-fatal — web image is cosmetic
        except Exception as e:
            print(f'⚠️ Could not render connected onboarding screen: {e}')
            return

        # The e-ink display worker takes ~40s to render.  Start the 60s
        # countdown from when the image was submitted to the display, so the
        # total on-screen time is ~60s, not render_time + 60s.
        #
        # Bounded wait, not an unconditional 'with': the vendor Waveshare
        # driver's busy-pin polling loop has no timeout of its own, and a
        # hardware-level hang there would otherwise block every other e-ink
        # update indefinitely.
        acquired = self._display_worker_lock.acquire(timeout=90)
        if acquired:
            self._display_worker_lock.release()
        else:
            print('⚠️ Display worker lock timeout after 90s — e-ink hardware may be stuck; continuing anyway')
        elapsed = time.time() - render_start
        remaining = max(0, 60 - elapsed)
        print(f'📺 Connected screen on e-ink (render took {elapsed:.0f}s, waiting {remaining:.0f}s more)')
        if remaining > 0:
            time.sleep(remaining)
        # After onboarding, always force a fresh image generation.
        # The cached image is likely stale (old block height, old language)
        # because it was rendered before the WiFi setup / language change.
        self._onboarding_connected_active = False
        try:
            print('⚙️ Onboarding complete — forcing fresh dashboard image generation')
            self.image_is_current = False
            self.last_eink_block_height = None
            self.last_eink_block_hash = None
            self._background_image_generation(force_eink=True)
        except Exception as e:
            print(f'⚠️ Could not generate fresh image after onboarding: {e}')

    def _start_wifi_recovery_monitor(self):
        if self._wifi_recovery_thread_started:
            return

        if os.name == 'nt':
            return

        enabled = bool(self.config.get('wifi_recovery_enabled', True))
        if not enabled:
            print('⚙️ Wi-Fi recovery monitor disabled in config')
            return

        if shutil.which('nmcli') is None:
            print('⚙️ Wi-Fi recovery monitor disabled (nmcli not available)')
            return

        self._wifi_recovery_thread_started = True

        def _loop():
            interface = self._detect_wifi_interface()
            poll_seconds = int(self.config.get('wifi_recovery_poll_seconds', 30))
            reconnect_interval_seconds = int(self.config.get('wifi_reconnect_interval_seconds', 60))
            setup_probe_interval_seconds = int(self.config.get('wifi_setup_probe_interval_seconds', 180))
            min_attempts = int(self.config.get('wifi_recovery_min_attempts', 10))
            outage_seconds = int(self.config.get('wifi_recovery_outage_seconds', 1800))
            startup_grace_seconds = int(self.config.get('wifi_recovery_startup_grace_seconds', 90))

            print(
                f"📡 Wi-Fi recovery monitor started on {interface} "
                f"(threshold: {outage_seconds}s + {min_attempts} attempts)"
            )

            # Wait for _startup_wifi_check to finish before the first poll —
            # without this grace, the recovery monitor races with startup and
            # both call _bring_up_setup_hotspot simultaneously, causing a
            # dnsmasq port-67 conflict that silently kills DHCP. Waiting on the
            # event rather than sleeping the full fixed duration lets the
            # common case (hotspot already up in a few seconds) start
            # monitoring immediately; startup_grace_seconds is now just the
            # worst-case fallback if the event is never set for some reason.
            self._startup_wifi_check_done.wait(timeout=startup_grace_seconds)

            while True:
                try:
                    now = time.time()
                    status = self._current_wifi_status(interface)
                    connected = bool(status.get('connected'))
                    status_known = status.get('status_known', True)
                    active_connection = status.get('connection', '')

                    # nmcli timed out (NM busy reconnecting) — skip this tick
                    # rather than treating the unknown state as a disconnect.
                    if not status_known:
                        time.sleep(max(5, poll_seconds))
                        continue

                    if connected:
                        self._wifi_disconnect_since = None
                        self._wifi_reconnect_attempts = 0
                        self._wifi_last_setup_probe_try = 0
                        self._wifi_setup_probe_failures = 0

                        if self._is_setup_mode_enabled():
                            print(f"✅ Wi-Fi recovered on {active_connection}; disabling setup hotspot")
                            self._bring_down_setup_hotspot()
                            # Wait for DHCP/DNS to settle before normal network operations resume.
                            print('⏳ Waiting 15s for DHCP/DNS to settle…')
                            time.sleep(15)

                        # When connected, poll slowly — no action needed until a drop occurs.
                        time.sleep(max(60, poll_seconds * 4))
                        continue

                    # Disconnected from normal Wi-Fi.
                    if self._wifi_disconnect_since is None:
                        self._wifi_disconnect_since = now
                        self._wifi_reconnect_attempts = 0
                        self._wifi_last_reconnect_try = 0
                        self._wifi_last_setup_probe_try = 0
                        print('⚠️ Wi-Fi disconnected, starting recovery attempts')

                    disconnected_for = now - self._wifi_disconnect_since

                    # A manual connect attempt from the setup page (apply_wifi_credentials_background)
                    # is actively tearing down/rebuilding the hotspot and negotiating a client
                    # connection right now — stand down completely rather than racing it. Without
                    # this, both threads independently manage wlan0/hostapd/dnsmasq and can empty
                    # NM's scan cache moments before the other's 'nmcli device wifi connect' runs.
                    if self._manual_wifi_connect_in_progress:
                        time.sleep(max(2, min(5, poll_seconds)))
                        continue

                    if self._is_setup_mode_enabled():
                        # If the setup flag is set but hostapd is not actually running
                        # (e.g. it crashed or was never started), bring it up
                        # unconditionally. If hostapd is up but dnsmasq died, only
                        # dnsmasq is restarted below — see the comment there for why.
                        hotspot_actually_up = self._hostapd_active()
                        captive_portal_up = self._captive_dnsmasq_active()
                        if not hotspot_actually_up:
                            print('📶 Setup mode flagged but hotspot not active — bringing up')
                            self._bring_up_setup_hotspot(interface)
                            self._captive_reinit_failures = 0
                            time.sleep(max(5, poll_seconds))
                            continue
                        if not captive_portal_up:
                            # dnsmasq died but hostapd (the AP itself) is still up —
                            # restart only dnsmasq, without touching the Wi-Fi interface,
                            # so an already-attached client isn't dropped. Backoff avoids
                            # hammering a persistent failure.
                            reinit_backoff = min(30 * (2 ** self._captive_reinit_failures), 300)
                            if now - self._last_captive_reinit_try >= reinit_backoff:
                                self._last_captive_reinit_try = now
                                self._captive_reinit_failures += 1
                                print('📶 Hotspot active but captive portal not running — restarting dnsmasq only')
                                hotspot_ip = self._get_hotspot_ip(interface)
                                self._start_captive_dns(interface, hotspot_ip)
                            time.sleep(max(5, poll_seconds))
                            continue
                        self._captive_reinit_failures = 0

                        # Immediate probe if user just submitted credentials via setup page.
                        pending = self._wifi_connect_pending
                        if pending:
                            self._wifi_connect_pending = False
                            self._wifi_last_setup_probe_try = 0  # force probe now

                        # Only do timed probes when no client is connected to the AP.
                        # Tearing down the hotspot while a phone is using it causes the
                        # phone to detect "no internet" and drop the connection.
                        has_ap_client = self._has_ap_station(interface)
                        if has_ap_client:
                            self._last_ap_station_seen_ts = now

                        # Grace window: treat the AP as occupied for N seconds after the
                        # phone was last seen — phones disassociate briefly when the screen
                        # goes off, which would otherwise trigger an immediate probe.
                        ap_client_grace = int(self.config.get('wifi_ap_client_grace_seconds', 120))
                        recently_had_client = (now - self._last_ap_station_seen_ts) < ap_client_grace

                        # Skip timed probes entirely when no saved client networks exist.
                        # There is nothing to connect to, so probing only disrupts the hotspot.
                        has_saved_networks = self._has_saved_wifi_connections()

                        # Progressive backoff: probe quickly at first (WiFi blip),
                        # then slow down (device moved, user needs stable hotspot).
                        # 0-2 failures: 90s, 3-5: 180s, 6+: 300s
                        # Capped at 300s so recovery after a router reboot is always
                        # detected within 5 minutes of the network coming back.
                        failures = self._wifi_setup_probe_failures
                        if failures <= 2:
                            probe_interval = 90
                        elif failures <= 5:
                            probe_interval = 180
                        else:
                            probe_interval = 300

                        if pending or (
                            has_saved_networks
                            and not has_ap_client
                            and not recently_had_client
                            and now - self._wifi_last_setup_probe_try >= probe_interval
                        ):
                            self._wifi_last_setup_probe_try = now
                            self._release_hotspot_for_probe(interface)
                            # After switching from AP back to station mode the radio
                            # needs a fresh scan to discover available networks.
                            time.sleep(3)
                            self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface], timeout=10)
                            time.sleep(8)
                            # Generous timeout: Pi Zero + slow post-reboot DHCP can take 60s+.
                            reconnect = self._nmcli(['device', 'connect', interface], timeout=90)
                            # On modern NM, returncode=0 means fully connected (DHCP done).
                            # If we hit our Python timeout (None) NM may still be finishing
                            # up in the background — poll for up to 30s before giving up.
                            poll_attempts = 1 if (reconnect is not None and reconnect.returncode == 0) else 10
                            recovered = False
                            for _ in range(poll_attempts):
                                time.sleep(3)
                                probe_status = self._current_wifi_status(interface)
                                if probe_status.get('connected'):
                                    recovered = True
                                    break
                            if recovered:
                                print('✅ Wi-Fi recovered during setup mode probe; disabling setup hotspot')
                                self._bring_down_setup_hotspot()
                                print('⏳ Waiting 15s for DHCP/DNS to settle…')
                                time.sleep(15)
                                time.sleep(max(5, poll_seconds))
                            else:
                                self._wifi_setup_probe_failures += 1
                                self._bring_up_setup_hotspot(interface)
                            continue

                        time.sleep(max(5, poll_seconds))
                        continue

                    # Keep trying normal reconnection before entering setup mode.
                    if now - self._wifi_last_reconnect_try >= reconnect_interval_seconds:
                        self._wifi_last_reconnect_try = now
                        self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface], timeout=10)
                        time.sleep(8)
                        reconnect = self._nmcli(['device', 'connect', interface], timeout=20)
                        self._wifi_reconnect_attempts += 1
                        if reconnect is not None and reconnect.returncode == 0:
                            pass  # NM accepted reconnect; wait for next poll to confirm

                    # If there are no saved client networks there is nothing to reconnect to
                    # — start the setup hotspot as soon as the startup grace window has
                    # passed (no need to wait for the full outage threshold).
                    no_saved = not self._has_saved_wifi_connections()

                    # Conservative trigger: only after startup grace + sustained outage + repeated attempts.
                    if (
                        (now - self._startup_timestamp) >= startup_grace_seconds
                        and (
                            no_saved
                            or (
                                disconnected_for >= outage_seconds
                                and self._wifi_reconnect_attempts >= min_attempts
                            )
                        )
                    ):
                        # Final re-check: NM may have just reconnected between our
                        # reconnect attempt above and this trigger (race condition).
                        # Bringing up the hotspot releases the interface from NM
                        # ('nmcli device set managed no'), which would rip out a
                        # freshly-recovered connection.
                        recheck = self._current_wifi_status(interface)
                        if recheck.get('connected'):
                            print('📡 Wi-Fi recovered before hotspot trigger — aborting hotspot switch')
                            self._wifi_disconnect_since = None
                            self._wifi_reconnect_attempts = 0
                            time.sleep(max(5, poll_seconds))
                            continue
                        reason = 'no saved networks' if no_saved else f'offline {int(disconnected_for)}s, attempts {self._wifi_reconnect_attempts}'
                        print(f'📶 Wi-Fi recovery threshold reached; switching to setup hotspot ({reason})')
                        self._bring_up_setup_hotspot(interface)

                    time.sleep(max(5, poll_seconds))
                except Exception as e:
                    print(f"⚠️ Wi-Fi recovery monitor error: {e}")
                    time.sleep(30)

        threading.Thread(target=_loop, name='wifi-recovery-monitor', daemon=True).start()
