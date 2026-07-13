#!/usr/bin/env python3
"""
Delivery State Script — Auslieferungszustand
=============================================
Renders a clean "factory default" dashboard image using static/memes/0.jpg as
the meme and zeroed-out placeholder values, then pushes it to the e-ink display.

Run this before shipping a device to a user:

    python tools/delivery_state.py

The script stops the mempaper service first (so the display isn't locked),
renders and shows the image, then exits.  You can then shut down the Pi safely.
"""

import os
import sys
import time
import argparse
import hashlib
import shutil
import json
import importlib.util
import subprocess
import signal
import glob
import datetime

# ── Path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)

# Many managers use relative paths like "config/...".
# Force project root as cwd so the script behaves the same no matter where it is launched from.
os.chdir(ROOT_DIR)

# ── Re-exec with venv Python if running under system Python ─────────────────
# Needed when script is called as "sudo python3 ..." instead of using the venv.
_VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "bin", "python3")
if os.path.exists(_VENV_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PYTHON):
    print(f"🔄 Re-launching with venv Python: {_VENV_PYTHON}")
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

MEME_PATH        = os.path.join(ROOT_DIR, "static", "memes", "0.jpg")
OUTPUT_WEB_PATH  = os.path.join(ROOT_DIR, "cache", "delivery_web.png")
OUTPUT_EINK_PATH = os.path.join(ROOT_DIR, "cache", "delivery_eink.png")

SETUP_MODE_FLAG_PATH = os.path.join(ROOT_DIR, "cache", "setup_mode.json")
MEMPAPER_SERVICE = "mempaper.service"

REQUIRED_PYTHON_MODULES = [
    "babel",
    "PIL",
]

LOG_PATH = "/tmp/delivery_state.log"


class _Tee:
    """Mirror writes to multiple streams — used to tee stdout/stderr to a log file
    so the full run is readable after SSH disconnects during WiFi clearing."""
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
    def fileno(self):
        return self._streams[0].fileno()


def _verify_wifi_state():
    """Dump NM connections, connection files, and netplan YAML state.

    Called after clear_saved_wifi_connections() so we can confirm the clear
    actually worked.  Output goes to LOG_PATH (readable after SSH recovery).
    """
    print("📋 WiFi state verification:")

    # 1. Live NM connection list
    r = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        wifi_lines = []
        for line in r.stdout.splitlines():
            parts = line.strip().rsplit(":", 2)
            if len(parts) == 3 and parts[2] in ("wifi", "802-11-wireless"):
                wifi_lines.append(line.strip())
        if wifi_lines:
            print(f"   ⚠️  NM still has {len(wifi_lines)} WiFi profile(s):")
            for ln in wifi_lines:
                print(f"      {ln}")
        else:
            print("   ✅ NM: no WiFi connections remaining")
    else:
        print(f"   ⚠️  nmcli query failed: {r.stderr.strip()}")

    # 2. .nmconnection files still on disk
    wifi_files = []
    for d in ("/etc/NetworkManager/system-connections",
              "/run/NetworkManager/system-connections"):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".nmconnection"):
                continue
            fp = os.path.join(d, fn)
            try:
                with open(fp) as fh:
                    content = fh.read()
                if "type=wifi" in content or "type = wifi" in content:
                    wifi_files.append(fp)
            except OSError:
                pass
    if wifi_files:
        print(f"   ⚠️  .nmconnection files still on disk:")
        for f in wifi_files:
            print(f"      {f}")
    else:
        print("   ✅ NM connection files: none")

    # 3. Netplan YAMLs still containing a wifis: section
    wifis_in_yaml = []
    for path in glob.glob("/etc/netplan/*.yaml"):
        try:
            with open(path) as fh:
                if "wifis:" in fh.read():
                    wifis_in_yaml.append(path)
        except OSError:
            pass
    if wifis_in_yaml:
        print(f"   ⚠️  Netplan YAML still has 'wifis:' section:")
        for p in wifis_in_yaml:
            print(f"      {p}")
    else:
        print("   ✅ Netplan: no 'wifis:' section")


def is_root_user():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _sudo(*cmd):
    base = [] if is_root_user() else ["sudo"]
    return subprocess.run(base + list(cmd), check=False, capture_output=True, text=True)


# ── Stop/start the mempaper service ─────────────────────────────────────────
def stop_service():
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", MEMPAPER_SERVICE],
        capture_output=True
    )
    if result.returncode == 0:
        print("⏹  Stopping mempaper service…")
        _sudo("systemctl", "stop", MEMPAPER_SERVICE)
        time.sleep(2)
        print("✅ Service stopped")
    else:
        print("ℹ️  mempaper service is not running — proceeding")


def start_service():
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", MEMPAPER_SERVICE],
        capture_output=True
    )
    if result.returncode != 0:
        print("▶️  Starting mempaper service…")
        _sudo("systemctl", "start", MEMPAPER_SERVICE)
        time.sleep(2)
        print("✅ Service started")
    else:
        print("ℹ️  mempaper service already running")


def clear_admin_users():
    """Remove all admin users from config (including encrypted config.secure.json).

    Uses ConfigManager + SecureConfigManager so the encrypted blob is properly
    rewritten without the credential keys.  After this, ``is_password_set()``
    returns False and the onboarding setup page shows the admin account creation
    form.
    """
    keys_to_remove = ["admin_users", "admin_password_hash", "admin_username"]

    try:
        from managers.config_manager import ConfigManager
        cm = ConfigManager()
    except Exception as e:
        print(f"⚠️  Could not load ConfigManager: {e}")
        return

    # get_current_config() merges plain + encrypted files → full picture
    full_cfg = cm.get_current_config()
    removed = [k for k in keys_to_remove if k in full_cfg]
    if not removed:
        print("ℹ️  No admin users found to clear")
        return

    for k in removed:
        del full_cfg[k]

    # Write directly through the secure config manager so both config.json
    # (public fields) and config.secure.json (encrypted fields) are updated.
    if cm.secure_manager:
        if not cm.secure_manager.save_secure_config(full_cfg):
            print("❌ Failed to persist cleared admin credentials to disk — "
                  "device will still show as configured after reboot!")
    else:
        # No encryption — plain JSON fallback
        cfg_path = os.path.join(ROOT_DIR, "config", "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(full_cfg, f, indent=2)

    # Also update in-memory state so subsequent code sees the change
    for k in removed:
        cm.config.pop(k, None)

    print(f"✅ Cleared admin credentials: {', '.join(removed)}")


def clear_authorized_keys():
    """Remove only the mempaper-managed SSH key block from authorized_keys.

    Lines outside the '# BEGIN mempaper-managed' / '# END mempaper-managed'
    block are preserved verbatim — manually-added keys survive the reset.
    SSH reads authorized_keys fresh on every connection so no daemon reload
    is needed.  The service user's file is owned by that user; the pi user's
    file is written via 'sudo tee' (already in NOPASSWD sudoers).
    """
    import pwd

    _BLOCK_START = "# BEGIN mempaper-managed"
    _BLOCK_END   = "# END mempaper-managed"

    def _strip_block(content):
        """Return content with the mempaper block removed; None if no change needed."""
        if _BLOCK_START not in content:
            return None  # nothing to remove
        lines = content.splitlines(keepends=True)
        out, in_block = [], False
        for line in lines:
            s = line.strip()
            if s == _BLOCK_START:
                in_block = True
                continue
            if s == _BLOCK_END:
                in_block = False
                continue
            if not in_block:
                out.append(line)
        return "".join(out)

    cleared = []
    skipped = []
    failed  = []

    # ── Service user's own authorized_keys ───────────────────────────────
    try:
        service_home = pwd.getpwnam(os.environ.get("USER", "mempaper")).pw_dir
    except KeyError:
        service_home = os.path.expanduser("~")
    own_keys = os.path.join(service_home, ".ssh", "authorized_keys")
    if os.path.exists(own_keys):
        try:
            content = open(own_keys, "r", encoding="utf-8").read()
            cleaned = _strip_block(content)
            if cleaned is None:
                skipped.append(own_keys)
            else:
                open(own_keys, "w", encoding="utf-8").write(cleaned)
                cleared.append(own_keys)
        except OSError as e:
            failed.append(f"{own_keys} ({e})")
    else:
        skipped.append(f"{own_keys} (absent)")

    # ── pi user's authorized_keys (via sudo tee) ──────────────────────────
    pi_keys = "/home/pi/.ssh/authorized_keys"
    if os.path.exists(pi_keys):
        try:
            r = subprocess.run(
                ([] if is_root_user() else ["sudo"]) + ["cat", pi_keys],
                capture_output=True, text=True
            )
            if r.returncode == 0:
                cleaned = _strip_block(r.stdout)
                if cleaned is None:
                    skipped.append(pi_keys)
                else:
                    w = subprocess.run(
                        ([] if is_root_user() else ["sudo"]) + ["tee", pi_keys],
                        input=cleaned, capture_output=True, text=True
                    )
                    if w.returncode == 0:
                        cleared.append(pi_keys)
                    else:
                        failed.append(f"{pi_keys} ({(w.stderr or w.stdout).strip()})")
            else:
                failed.append(f"{pi_keys} (read failed: {(r.stderr or r.stdout).strip()})")
        except OSError as e:
            failed.append(f"{pi_keys} ({e})")
    else:
        skipped.append(f"{pi_keys} (absent)")

    if cleared:
        print(f"✅ Cleared mempaper SSH keys from: {', '.join(cleared)}")
    if skipped:
        print(f"ℹ️  No mempaper SSH keys found in: {', '.join(skipped)}")
    if failed:
        for f in failed:
            print(f"⚠️  Could not clear authorized_keys: {f}")


def clear_saved_wifi_connections():
    """Delete all saved client-mode WiFi profile files from disk.

    Uses the mempaper-clear-wifi wrapper with --no-reload so NM's in-memory
    state (and the active WiFi connection) is untouched — SSH stays connected.
    The .nmconnection files and any netplan wifis: section are removed from
    disk; changes take effect on next reboot.  The delivery_mode flag (written
    later in main()) ensures the app starts its hotspot immediately on that
    reboot regardless of any residual NM state.
    """
    wrapper = "/usr/local/bin/mempaper-clear-wifi"
    if not (shutil.which(wrapper) or os.path.exists(wrapper)):
        print("❌ WiFi clear wrapper not installed — run:")
        print("   sudo bash tools/install_wifi_permissions.sh mempaper")
        return

    _cmd = ([] if is_root_user() else ["sudo"]) + [wrapper, "--no-reload"]
    r = subprocess.run(_cmd, capture_output=True, text=True)
    if r.returncode == 0:
        out = (r.stdout or "").strip()
        print(f"🧹 {out}" if out else "🧹 WiFi config cleared (deferred — takes effect after reboot)")
    else:
        err = (r.stderr or r.stdout or "").strip()
        print(f"❌ WiFi clear wrapper failed: {err}")
        print("   Re-run: sudo bash tools/install_wifi_permissions.sh mempaper")


def disable_cloudinit_network_config():
    """Stop cloud-init from re-applying network config (incl. saved WiFi) on every boot.

    Raspberry Pi Imager preconfigures WiFi via a cloud-init NoCloud datasource
    seeded from /boot/firmware/, and Raspberry Pi OS deliberately re-applies
    that datasource's network config on EVERY boot (not cloud-init's usual
    one-shot behavior), so the same SD image works if moved to different
    hardware. Without this, clear_saved_wifi_connections() above is silently
    undone by cloud-init the next time the device boots, before the app's own
    "no saved networks" check ever runs.
    """
    conf_dir  = "/etc/cloud/cloud.cfg.d"
    conf_path = f"{conf_dir}/99-disable-network-config.cfg"
    _sudo("mkdir", "-p", conf_dir)
    r = subprocess.run(
        ([] if is_root_user() else ["sudo"]) + ["tee", conf_path],
        input="network: {config: disabled}\n",
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print("🧹 Disabled cloud-init network re-application (WiFi clear survives reboot now)")
    else:
        err = (r.stderr or r.stdout or "").strip()
        print(f"⚠️ Could not disable cloud-init network config: {err}")


def _is_root_readonly():
    """Check if / is mounted read-only."""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == "/":
                    return "ro" in parts[3].split(",")
    except Exception:
        pass
    return False


def write_wlan0_unmanaged_override():
    """Mark wlan0 unmanaged for NetworkManager, effective next reboot.

    Removed again by mempaper_app.py once WiFi credentials are applied.
    """
    conf_dir  = "/etc/NetworkManager/conf.d"
    conf_path = f"{conf_dir}/99-mempaper-wlan0-unmanaged.conf"
    was_readonly = _is_root_readonly()
    if was_readonly:
        _sudo("mount", "-o", "remount,rw", "/")
    _sudo("mkdir", "-p", conf_dir)
    r = subprocess.run(
        ([] if is_root_user() else ["sudo"]) + ["tee", conf_path],
        input="[keyfile]\nunmanaged-devices=interface-name:wlan0\n",
        capture_output=True, text=True,
    )
    if was_readonly:
        _sudo("mount", "-o", "remount,ro", "/")
    if r.returncode == 0:
        print("🧹 wlan0 pre-declared unmanaged for next boot (hotspot won't wait on NetworkManager)")
    else:
        err = (r.stderr or r.stdout or "").strip()
        print(f"⚠️ Could not write wlan0 unmanaged override: {err}")


# ── Load config ──────────────────────────────────────────────────────────────
def load_config():
    from managers.config_manager import ConfigManager
    return ConfigManager().get_current_config()

def check_runtime_dependencies():
    missing = []
    for module_name in REQUIRED_PYTHON_MODULES:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)

    if not missing:
        return True

    print("❌ Missing Python dependencies:")
    for module_name in missing:
        print(f"   - {module_name}")

    print()
    print("Install requirements in your venv and retry:")
    print(f"   {os.path.join(ROOT_DIR, '.venv', 'bin', 'pip')} install -r {os.path.join(ROOT_DIR, 'requirements.txt')}")
    print("   (or: source .venv/bin/activate && pip install -r requirements.txt)")
    return False

# ── Render the delivery image ────────────────────────────────────────────────
def render_delivery_image(config):
    try:
        from utils.translations import translations
        from lib.image_renderer import ImageRenderer
    except ModuleNotFoundError as e:
        print(f"❌ Required module not found while loading renderer: {e}")
        print("   Install dependencies: pip install -r requirements.txt")
        sys.exit(1)

    lang         = config.get("language", "en")
    translations_dict = translations.get(lang, translations["en"])

    renderer = ImageRenderer(config, translations_dict)

    # Zero-out all data so no stale API values appear
    renderer._donation_data = None

    # No holiday info on delivery image — keep it clean, just the date
    renderer.get_today_btc_holiday = lambda: None

    # Genesis block data: block 0 with actual Genesis block hash
    BLOCK_HEIGHT = "0"
    BLOCK_HASH   = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"

    print(f"🎨 Rendering delivery image with {os.path.basename(MEME_PATH)}…")
    web_img, eink_img, _, _ = renderer.render_dual_images(
        block_height=BLOCK_HEIGHT,
        block_hash=BLOCK_HASH,
        mempool_api=None,
        startup_mode=True,           # use cached / no API calls
        override_content_path=MEME_PATH,
    )

    os.makedirs(os.path.dirname(OUTPUT_WEB_PATH), exist_ok=True)

    if web_img:
        web_img.save(OUTPUT_WEB_PATH)
        print(f"💾 Web preview saved → {OUTPUT_WEB_PATH}")

    if eink_img:
        eink_img.save(OUTPUT_EINK_PATH)
        print(f"💾 E-ink image saved  → {OUTPUT_EINK_PATH}")
    else:
        print("❌ E-ink image not generated — aborting display step")
        sys.exit(1)

    return OUTPUT_EINK_PATH

# ── Push to e-ink display ────────────────────────────────────────────────────
def show_on_eink(image_path):
    try:
        from display.waveshare_display import WaveshareDisplay, WAVESHARE_AVAILABLE
    except ImportError:
        print("⚠️  Waveshare library not importable — skipping hardware display")
        return

    if not WAVESHARE_AVAILABLE:
        print("⚠️  Waveshare hardware not available — skipping display step")
        return

    print("🖥️  Sending image to e-ink display (this takes ~40 s)…")
    start = time.time()
    
    # Load config for display dimensions and device name
    try:
        from managers.config_manager import ConfigManager
        config_manager = ConfigManager()
        config = config_manager.config
    except Exception as e:
        print(f"⚠️  Could not load config, using defaults: {e}")
        config = {}
    
    display = WaveshareDisplay(config=config)
    success = display.display_image(image_path)
    elapsed = time.time() - start

    if success:
        print(f"✅ E-ink display updated in {elapsed:.1f} s")
    else:
        print("❌ E-ink display update failed")
        sys.exit(1)

    display.cleanup()

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Render delivery image and prepare device for shipment")
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Skip e-ink display step (render image only)",
    )
    args = parser.parse_args()

    # Ignore SIGHUP so the script survives SSH disconnect when WiFi is cleared.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    # Mirror all output to a log file so the full run is readable after SSH
    # disconnects (which happens when WiFi is cleared mid-script).
    try:
        _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
        _log_fh.write(f"# delivery_state.py  {datetime.datetime.now().isoformat()}\n")
        sys.stdout = _Tee(sys.__stdout__, _log_fh)
        sys.stderr = _Tee(sys.__stderr__, _log_fh)
    except Exception as e:
        print(f"⚠️  Could not open log file {LOG_PATH}: {e}")

    print("=" * 55)
    print("  mempaper — Auslieferungszustand / Delivery State")
    print("=" * 55)

    if not os.path.exists(MEME_PATH):
        print(f"❌ Meme image not found: {MEME_PATH}")
        sys.exit(1)

    if not check_runtime_dependencies():
        sys.exit(1)

    stop_service()
    config     = load_config()
    image_path = render_delivery_image(config)

    if not args.no_display:
        show_on_eink(image_path)

    # Disable UFW so DHCP works on the setup hotspot.
    # UFW's ufw-after-input chain drops UDP/67 broadcasts before user allow-rules
    # can accept them, making it impossible for dnsmasq to reply to DHCP DISCOVERs.
    print()
    print("🔒 Disabling UFW (prevents DHCP on setup hotspot)…")
    if shutil.which("ufw"):
        r = _sudo("ufw", "disable")
        if r.returncode == 0:
            print("✅ UFW disabled")
        else:
            print(f"⚠️  ufw disable failed (non-fatal): {(r.stderr or r.stdout or '').strip()}")
    else:
        print("ℹ️  UFW not installed — nothing to do")

    # Clear any leftover setup-mode flag so the app starts fresh
    try:
        if os.path.exists(SETUP_MODE_FLAG_PATH):
            os.remove(SETUP_MODE_FLAG_PATH)
    except OSError:
        pass

    # Clear admin users so the onboarding page shows the account creation form.
    # Admin credentials live in the encrypted config.secure.json, not config.json.
    print()
    print("🧹 Clearing admin users…")
    clear_admin_users()

    print()
    print("🧹 Clearing SSH authorized keys…")
    clear_authorized_keys()

    # Remove saved client WiFi profiles so the user device has a clean NM
    # state: on first boot _has_saved_wifi_connections() returns False and the
    # setup hotspot starts immediately (no 45s grace-window delay).
    print()
    print("🧹 Clearing saved WiFi profiles…")
    clear_saved_wifi_connections()
    disable_cloudinit_network_config()
    write_wlan0_unmanaged_override()
    _verify_wifi_state()

    # Pre-write setup_mode.json so the Wi-Fi recovery monitor treats setup
    # mode as already enabled from the very first boot tick.  Without this,
    # if _startup_wifi_check exits early (e.g. NM timeout), the recovery
    # monitor falls back to the 90s startup grace window before starting the
    # hotspot.  Cleared by _bring_down_setup_hotspot() after user setup.
    cache_dir = os.path.join(ROOT_DIR, "cache")
    setup_mode_flag = os.path.join(cache_dir, "setup_mode.json")
    try:
        # Detect WiFi interface for the flag (informational only — the app
        # re-derives the SSID from the MAC address when it brings up the hotspot).
        wifi_iface = "wlan0"
        net_root = "/sys/class/net"
        if os.path.isdir(net_root):
            for iface in sorted(os.listdir(net_root)):
                if os.path.isdir(os.path.join(net_root, iface, "wireless")):
                    wifi_iface = iface
                    break
        # Derive SSID using the same MAC digest logic as the app.
        try:
            mac = ""
            for _mac_path in (f"/sys/class/net/{wifi_iface}/perm_address",
                               f"/sys/class/net/{wifi_iface}/address"):
                try:
                    _v = open(_mac_path).read().strip().lower()
                    if _v and _v != "00:00:00:00:00:00":
                        mac = _v
                        break
                except OSError:
                    continue
            digest = hashlib.sha256(mac.replace(":", "").encode()).hexdigest()
            ssid = f"mempaper-{int(digest[:8], 16) % 10000:04d}"
        except Exception:
            ssid = "mempaper-0000"
        with open(setup_mode_flag, "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "ssid": ssid, "interface": wifi_iface}, f)
        print(f"✅ Setup mode flag pre-written → recovery monitor starts hotspot immediately on boot ({ssid} on {wifi_iface})")
    except OSError as e:
        print(f"⚠️  Could not write setup mode flag: {e}")

    # Ensure mempaper.service is enabled for automatic hotspot on next boot
    result = subprocess.run(
        ["systemctl", "is-enabled", "--quiet", MEMPAPER_SERVICE],
        capture_output=True
    )
    if result.returncode != 0:
        _sudo("systemctl", "enable", MEMPAPER_SERVICE)
        print("✅ mempaper.service enabled")

    # Flush all pending writes to the SD card before the user powers off.
    # setup_mode.json and the removed .nmconnection files live in page cache
    # until sync; a hard power cut before this flush leaves the device in an
    # inconsistent state (flag missing, old WiFi profile still on disk).
    print()
    print("💾 Syncing filesystem to SD card…")
    subprocess.run(["sync"], check=False)
    print("✅ Filesystem synced — safe to power off")

    print()
    print("✅ Delivery state applied. Device is ready to ship.")
    print()
    print("   Power on → hotspot starts → e-ink shows SSID, password, and QR code.")
    print("   User scans QR, opens http://10.42.0.1:5000, enters password to set up WiFi.")
    print()
    print(f"   To shut down: sudo shutdown -h now")
    print(f"   Full run log: sudo cat {LOG_PATH}")

if __name__ == "__main__":
    main()
