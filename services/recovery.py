"""Factory reset: power-cycle detection, clearing Wi-Fi profiles and user
data, and the NetworkManager overrides that reset depends on.
"""

from utils.atomic_io import atomic_write_json
import json
import os
import subprocess
import time


class RecoveryMixin:
    """Factory reset: power-cycle detection, clearing Wi-Fi profiles and user"""

    def _check_power_cycle_reset(self):
        """Detect rapid power-cycling (3 reboots in 15 min) and trigger factory reset.

        Each unique system boot (identified by /proc/sys/kernel/random/boot_id)
        is recorded. Service restarts on the same boot are deduplicated and do
        NOT count.  Using boot_id instead of (now - uptime) avoids false
        positives caused by NTP clock corrections after boot.
        If 3+ distinct reboots occur within the window, a full factory reset is
        triggered: admin + sensitive data cleared, saved WiFi profiles deleted,
        and the delivery-state e-ink image rendered.

        Returns True if a reset was triggered (caller should skip normal startup).
        """
        now = time.time()

        # Distinguish real reboots from service restarts using the kernel
        # boot_id — a UUID that changes on every reboot but stays constant
        # across service restarts.  Unlike (now - uptime), this is immune to
        # NTP clock corrections that shift the computed boot epoch.
        boot_id = None
        try:
            with open('/proc/sys/kernel/random/boot_id', 'r') as f:
                boot_id = f.read().strip()
            print(f'⏱️ Kernel boot_id: {boot_id}')
        except (OSError, ValueError):
            pass  # Not on Linux (dev machine)
        # Exposed via /api/health so the frontend can tell an actual reboot
        # (new boot_id) apart from a same-boot service restart.
        self._current_boot_id = boot_id

        # Consume the one-shot "this reboot was triggered from the authenticated
        # web UI" marker. Still want the usual boot-confirmation e-ink refresh
        # below — just skip counting this boot toward the panic-recovery
        # threshold, since the user already has full access (they just used it).
        graceful_reboot = os.path.exists(self.GRACEFUL_REBOOT_MARKER_PATH)
        if graceful_reboot:
            try:
                os.remove(self.GRACEFUL_REBOOT_MARKER_PATH)
            except OSError:
                pass
            print('🔄 Power-cycle reset check: skipped (reboot was triggered from the web UI)')
            self._pending_boot_refresh = True
            return False

        # Load existing boot records — stored as {boot_id: timestamp} pairs
        # to deduplicate multiple service restarts within the same boot.
        boot_records = {}  # {boot_id_str: first_seen_timestamp}
        try:
            if os.path.exists(self.BOOT_TIMESTAMPS_PATH):
                with open(self.BOOT_TIMESTAMPS_PATH, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                # Migrate from old list/dict format that used numeric keys
                if isinstance(raw, list):
                    boot_records = {}
                    print('🔄 Migrating boot_timestamps from old list format')
                elif isinstance(raw, dict):
                    # Detect old numeric-key format and discard it
                    if raw and all(k.replace('-', '').isdigit() or len(k) < 30 for k in raw):
                        boot_records = {}
                        print('🔄 Migrating boot_timestamps from old numeric format')
                    else:
                        boot_records = raw
        except (json.JSONDecodeError, OSError):
            pass

        # Prune records outside the detection window
        boot_records = {k: v for k, v in boot_records.items()
                        if (now - v) < self.POWER_CYCLE_RESET_WINDOW}

        if boot_id is not None:
            if boot_id in boot_records:
                print(f'🔄 Power-cycle reset check: skipped (service restart on same boot)')
                return False
            # New boot — record it, and remember to push a fast refresh once
            # startup finishes, so power-cycling the device is visibly
            # confirmed instead of leaving the user unsure it's alive.
            boot_records[boot_id] = now
            self._pending_boot_refresh = True
        else:
            # Fallback (non-Linux): use timestamp as key (old behavior)
            boot_records[str(int(now))] = now
            self._pending_boot_refresh = True

        # Persist updated boot records atomically (temp file + os.replace, both
        # fsync'd) so a power loss mid-write never leaves a truncated/corrupt file.
        try:
            atomic_write_json(self.BOOT_TIMESTAMPS_PATH, boot_records)
        except OSError:
            pass

        boot_count = len(boot_records)
        print(f'🔄 Power-cycle reset check: {boot_count}/{self.POWER_CYCLE_RESET_THRESHOLD} '
              f'unique boots in {self.POWER_CYCLE_RESET_WINDOW}s window')

        if boot_count >= self.POWER_CYCLE_RESET_THRESHOLD:
            print(f'🔄 Power-cycle reset detected! ({boot_count} boots in {self.POWER_CYCLE_RESET_WINDOW}s window)')
            print('🔄 Triggering factory reset...')

            # Clear the timestamps file so the next boot is clean
            try:
                os.remove(self.BOOT_TIMESTAMPS_PATH)
            except OSError:
                pass

            # Caller runs _execute_factory_reset() synchronously so WiFi
            # profiles are deleted before the WiFi check thread starts.
            return True

        return False

    BOOT_REFRESH_MARKER_PATH = os.path.join('cache', 'boot_refresh_pending')

    def _check_boot_refresh_marker(self):
        """Consume the one-shot marker install.sh drops before its final
        service restart, pushing a fast e-ink refresh so a completed install
        is visibly confirmed even when no reboot happened."""
        if os.path.exists(self.BOOT_REFRESH_MARKER_PATH):
            try:
                os.remove(self.BOOT_REFRESH_MARKER_PATH)
            except OSError:
                pass
            self._pending_boot_refresh = True
            print('🔄 Boot-refresh marker found — will push a fast e-ink refresh after startup')

    def _execute_factory_reset(self):
        """Full factory reset: clear data, delete WiFi, render delivery image.

        Runs in a background thread because the delivery-state image render
        and e-ink display update take ~40-60 seconds.
        """
        try:
            # 1. Clear admin + sensitive user data
            print('🧹 Factory reset: clearing user data...')
            self._perform_user_data_reset()

            # 2. Clear saved WiFi profiles using the app's own nmcli wrapper
            #    (delivery_state's nmcli_cmd has different sudo handling that
            #    may silently fail inside the running service)
            print('🧹 Factory reset: clearing saved WiFi profiles...')
            self._factory_reset_clear_wifi()

            # 3. Render the delivery-state image and push via the app's display worker
            print('🎨 Factory reset: rendering delivery state image...')
            try:
                import tools.delivery_state as ds
                config = self.config_manager.get_current_config()
                image_path = ds.render_delivery_image(config)
                # Use the app's own display worker (not ds.show_on_eink) to avoid
                # GPIO conflicts with the already-running display subprocess.
                if self.e_ink_enabled:
                    print('🖥️ Factory reset: pushing delivery image to e-ink...')
                    self._display_on_epaper_async(image_path, None, None)
            except Exception as e:
                print(f'⚠️ Could not render delivery image: {e}')

            print('✅ Factory reset complete. Device is in delivery state.')

        except Exception as e:
            print(f'❌ Factory reset failed: {e}')
            import traceback
            traceback.print_exc()

    def _factory_reset_clear_wifi(self):
        """Delete all saved client WiFi profiles.

        Uses 'sudo nmcli' for both listing and deleting because system-owned
        WiFi connections (created via 'sudo nmcli device wifi connect') are
        not visible to unprivileged nmcli queries.
        """
        try:
            # Must use sudo to see system-owned connections
            result = self._nmcli(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'])
            if result is None:
                print('⚠️ WiFi cleanup: nmcli command failed to execute')
                return
            if result.returncode != 0:
                print(f'⚠️ WiFi cleanup: nmcli list failed: {(result.stderr or result.stdout or "").strip()}')
                return

            print(f'🔍 WiFi cleanup: nmcli output: {result.stdout.strip()!r}')

            deleted = []
            failed = []
            for line in result.stdout.splitlines():
                # Format: NAME:UUID:TYPE — rsplit from right so SSIDs with colons are handled
                parts = line.strip().rsplit(':', 2)
                if len(parts) < 3:
                    continue
                name, uuid, conn_type = parts[0], parts[1], parts[2]
                if conn_type not in ('wifi', '802-11-wireless'):
                    continue
                if name.startswith('mempaper-setup'):
                    continue
                print(f'🧹 Deleting WiFi profile: {name}')
                # Try by name first; fall back to UUID for Pi Imager "immutable" profiles
                r = self._nmcli(['connection', 'delete', name])
                if r is None or r.returncode != 0:
                    r = self._nmcli(['connection', 'delete', 'uuid', uuid])
                if r is not None and r.returncode == 0:
                    deleted.append(name)
                else:
                    err = (r.stderr or r.stdout or '').strip() if r else 'no result'
                    failed.append(f'{name}: {err}')
                    print(f'⚠️ Failed to delete WiFi profile {name} ({uuid}): {err}')

            if deleted:
                print(f'🧹 Deleted {len(deleted)} WiFi profile(s): {", ".join(deleted)}')
            elif not failed:
                print('ℹ️ No saved WiFi profiles to delete')
            if failed:
                print(f'⚠️ nmcli delete failed for {len(failed)} profile(s)')

            # Always run the wrapper too, even when every nmcli delete reported
            # success. For Pi-Imager/netplan-managed profiles, 'nmcli connection
            # delete' can return 0 after removing the live NM connection object
            # while leaving the underlying /etc/netplan/*.yaml 'wifis:' section
            # completely untouched — the deletion "succeeds" but NetworkManager's
            # own internal 'netplan generate' (or mempaper-netplan-pregenerate)
            # silently recreates the identical profile from that YAML on the very
            # next boot. Only stripping the netplan source when nmcli explicitly
            # failed missed exactly this case. The wrapper's netplan edit is
            # idempotent (checks for a 'wifis:' section first), so re-running it
            # here is a no-op when there's nothing left to strip.
            wrapper = '/usr/local/bin/mempaper-clear-wifi'
            if os.path.exists(wrapper):
                r = subprocess.run(['sudo', wrapper], capture_output=True, text=True)
                if r.returncode == 0:
                    print('🧹 Netplan-sourced WiFi config cleared via wrapper')
                else:
                    print(f'❌ Wrapper failed: {(r.stderr or r.stdout or "").strip()}')
            else:
                print('❌ WiFi clear wrapper not installed — re-run install_permissions.sh')
        except Exception as e:
            print(f'⚠️ WiFi cleanup failed: {e}')
            import traceback
            traceback.print_exc()

        self._disable_cloudinit_network_config()
        self._write_wlan0_unmanaged_override()

    def _disable_cloudinit_network_config(self):
        """Stop cloud-init from re-applying network config (incl. saved WiFi) on every boot.

        Raspberry Pi Imager preconfigures WiFi via a cloud-init NoCloud
        datasource seeded from /boot/firmware/, and Raspberry Pi OS
        deliberately re-applies that datasource's network config on EVERY
        boot (not cloud-init's usual one-shot behavior) so the same SD image
        works if moved to different hardware. Without this, the WiFi clearing
        above is silently undone by cloud-init on the very next boot, before
        _has_saved_wifi_connections() ever gets a chance to see "no networks".
        """
        conf_dir  = '/etc/cloud/cloud.cfg.d'
        conf_path = f'{conf_dir}/99-disable-network-config.cfg'
        subprocess.run(['sudo', 'mkdir', '-p', conf_dir], capture_output=True, timeout=10)
        r = subprocess.run(
            ['sudo', 'tee', conf_path],
            input='network: {config: disabled}\n',
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            print('🧹 Disabled cloud-init network re-application (WiFi clear survives reboot now)')
        else:
            err = (r.stderr or r.stdout or '').strip()
            print(f'⚠️ Could not disable cloud-init network config: {err}')

    def _is_root_readonly(self):
        """Check if / is mounted read-only."""
        try:
            with open('/proc/mounts') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[1] == '/':
                        return 'ro' in parts[3].split(',')
        except Exception:
            pass
        return False

    def _write_wlan0_unmanaged_override(self):
        """Mark wlan0 unmanaged for NetworkManager, effective next reboot."""
        conf_dir = os.path.dirname(self._WLAN0_UNMANAGED_CONF)
        was_readonly = self._is_root_readonly()
        if was_readonly:
            subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], capture_output=True, timeout=10)
        subprocess.run(['sudo', 'mkdir', '-p', conf_dir], capture_output=True, timeout=10)
        r = subprocess.run(
            ['sudo', 'tee', self._WLAN0_UNMANAGED_CONF],
            input='[keyfile]\nunmanaged-devices=interface-name:wlan0\n',
            capture_output=True, text=True, timeout=10,
        )
        if was_readonly:
            subprocess.run(['sudo', 'mount', '-o', 'remount,ro', '/'], capture_output=True, timeout=10)
        if r.returncode == 0:
            print('🧹 wlan0 pre-declared unmanaged for next boot (hotspot won\'t wait on NetworkManager)')
        else:
            err = (r.stderr or r.stdout or '').strip()
            print(f'⚠️ Could not write wlan0 unmanaged override: {err}')

    def _remove_wlan0_unmanaged_override(self):
        """Undo _write_wlan0_unmanaged_override() and reload NM immediately."""
        if not os.path.exists(self._WLAN0_UNMANAGED_CONF):
            return
        was_readonly = self._is_root_readonly()
        if was_readonly:
            subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], capture_output=True, timeout=10)
        r = subprocess.run(['sudo', 'rm', '-f', self._WLAN0_UNMANAGED_CONF],
                            capture_output=True, text=True, timeout=10)
        if was_readonly:
            subprocess.run(['sudo', 'mount', '-o', 'remount,ro', '/'], capture_output=True, timeout=10)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '').strip()
            print(f'⚠️ Could not remove wlan0 unmanaged override: {err}')
            return
        reload_result = subprocess.run(['sudo', 'nmcli', 'general', 'reload', 'conf'],
                                        capture_output=True, text=True, timeout=15)
        if reload_result.returncode == 0:
            print('🧹 Removed wlan0 unmanaged override and reloaded NetworkManager config')
        else:
            err = (reload_result.stderr or reload_result.stdout or '').strip()
            print(f'⚠️ Removed wlan0 unmanaged override but NM reload failed: {err}')
