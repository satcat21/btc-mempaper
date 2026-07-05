#!/usr/bin/env python3
"""
Delivery State Script — Auslieferungszustand
=============================================
Renders a clean "factory default" dashboard image using static/memes/0.jpg as
the meme and zeroed-out placeholder values, then pushes it to the e-ink display.

Run this before shipping a device to a customer:

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

HOTSPOT_CONNECTION_NAME = "mempaper-setup"
SETUP_MODE_FLAG_PATH = os.path.join(ROOT_DIR, "cache", "setup_mode.json")
MEMPAPER_SERVICE = "mempaper.service"

REQUIRED_PYTHON_MODULES = [
    "babel",
    "PIL",
]


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


def run_cmd(cmd, check=False):
    return subprocess.run(cmd, check=check, capture_output=True, text=True)

# ---------------------------------------------------------------------------
# nmcli wrapper — uses 'sudo nmcli' when not already root so that
# hotspot creation (settings.modify.system) works for normal service users.
# The install_wifi_permissions.sh script drops a matching passwordless
# sudoers rule at /etc/sudoers.d/mempaper-wifi.
# ---------------------------------------------------------------------------
_USE_SUDO_NMCLI = (not is_root_user())

def nmcli_cmd(*args):
    base = ["sudo", "nmcli"] if _USE_SUDO_NMCLI else ["nmcli"]
    return subprocess.run(base + list(args), capture_output=True, text=True)

def _print_cmd_error(prefix, result):
    if result is None:
        print(f"⚠️  {prefix}: command did not execute")
        return
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    if stderr:
        print(f"⚠️  {prefix}: {stderr}")
    elif stdout:
        print(f"⚠️  {prefix}: {stdout}")
    else:
        print(f"⚠️  {prefix}: failed with exit code {result.returncode}")


def write_setup_mode_flag(enabled, ssid=None, interface=None):
    os.makedirs(os.path.dirname(SETUP_MODE_FLAG_PATH), exist_ok=True)

    if not enabled:
        try:
            if os.path.exists(SETUP_MODE_FLAG_PATH):
                os.remove(SETUP_MODE_FLAG_PATH)
        except OSError:
            pass
        return

    payload = {
        "enabled": True,
        "ssid": ssid,
        "interface": interface,
        "timestamp": int(time.time()),
    }
    try:
        with open(SETUP_MODE_FLAG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError as e:
        print(f"⚠️  Could not write setup mode flag: {e}")

def detect_wifi_interface():
    if shutil.which("nmcli") is not None:
        result = nmcli_cmd("-t", "-f", "DEVICE,TYPE,STATE", "device", "status")
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.strip().split(":")
                if len(parts) < 2:
                    continue
                device, dev_type = parts[0], parts[1]
                if device and dev_type == "wifi":
                    return device

    preferred = "/sys/class/net/wlan0"
    if os.path.exists(preferred):
        return "wlan0"

    net_root = "/sys/class/net"
    if not os.path.isdir(net_root):
        return None

    for iface in sorted(os.listdir(net_root)):
        if os.path.isdir(os.path.join(net_root, iface, "wireless")):
            return iface

    return None


def wait_for_wifi_interface(timeout_seconds=30, poll_seconds=2):
    deadline = time.time() + max(0, timeout_seconds)
    while time.time() <= deadline:
        interface = detect_wifi_interface()
        if interface:
            return interface
        time.sleep(max(1, poll_seconds))
    return None

def get_mac_address(interface):
    mac_path = f"/sys/class/net/{interface}/address"
    try:
        with open(mac_path, "r", encoding="utf-8") as f:
            return f.read().strip().lower()
    except OSError:
        return "00:00:00:00:00:00"

def hotspot_suffix_from_mac(mac_address):
    raw = mac_address.replace(":", "")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 10000:04d}"

def build_hotspot_ssid(interface, prefix="mempaper"):
    mac = get_mac_address(interface)
    suffix = hotspot_suffix_from_mac(mac)
    return f"{prefix}-{suffix}"

def build_hotspot_password(interface):
    """Derive deterministic 8-char WPA2 password from MAC address (matches mempaper_app.py)."""
    mac = get_mac_address(interface)
    raw = mac.replace(":", "")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[8:16]  # 8 lowercase hex chars

def is_wifi_connected(interface):
    status = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    if status.returncode != 0:
        return False

    for line in status.stdout.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 3:
            continue
        device, dev_type, state = parts[0], parts[1], parts[2]
        if device == interface and dev_type == "wifi" and state.startswith("connected"):
            return True

    return False

DNSMASQ_CONF_PATH = "/tmp/mempaper-captive-dns.conf"
DNSMASQ_PID_PATH  = "/tmp/mempaper-captive-dns.pid"
CAPTIVE_IP        = "192.168.12.1"


def start_captive_dns(interface):
    """Start a dnsmasq instance that resolves all domains to the hotspot IP,
    triggering the OS captive-portal popup on connecting devices."""
    stop_captive_dns()  # clean up any stale instance
    if shutil.which("dnsmasq") is None:
        print("⚠️  dnsmasq not found — captive-portal DNS unavailable")
        print("   Install with: sudo apt install -y dnsmasq")
        return

    conf = (
        f"interface={interface}\n"
        f"bind-interfaces\n"
        f"dhcp-range={interface},192.168.12.100,192.168.12.200,12h\n"
        f"address=/#/{CAPTIVE_IP}\n"  # resolve everything to Pi IP
        f"no-resolv\n"
        f"no-poll\n"
        f"log-queries\n"
    )
    try:
        with open(DNSMASQ_CONF_PATH, "w", encoding="utf-8") as f:
            f.write(conf)
    except OSError as e:
        print(f"⚠️  Could not write dnsmasq config: {e}")
        return

    result = run_cmd([
        "sudo", "dnsmasq",
        "--conf-file=" + DNSMASQ_CONF_PATH,
        "--pid-file=" + DNSMASQ_PID_PATH,
    ])
    if result.returncode == 0:
        print("✅  Captive-portal dnsmasq started")
    else:
        print(f"⚠️  dnsmasq failed to start: {result.stderr.strip() or result.stdout.strip()}")


def stop_captive_dns():
    """Stop the captive-portal dnsmasq instance."""
    pid_file = DNSMASQ_PID_PATH
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = f.read().strip()
            if pid:
                run_cmd(["sudo", "kill", pid])
        except OSError:
            pass
        try:
            os.remove(pid_file)
        except OSError:
            pass
    # Also kill any stale instance by config file reference
    run_cmd(["sudo", "pkill", "-f", DNSMASQ_CONF_PATH])
    if os.path.exists(DNSMASQ_CONF_PATH):
        try:
            os.remove(DNSMASQ_CONF_PATH)
        except OSError:
            pass


def bring_up_hotspot(interface, ssid, password):
    nmcli_cmd("radio", "wifi", "on")
    nmcli_cmd("connection", "down", HOTSPOT_CONNECTION_NAME)
    nmcli_cmd("connection", "delete", HOTSPOT_CONNECTION_NAME)

    print(f'\U0001f4f6 Setup hotspot: WPA2 AP "{ssid}" (password derived from device MAC)')
    nmcli_cmd("connection", "add", "type", "wifi", "ifname", interface,
              "con-name", HOTSPOT_CONNECTION_NAME, "autoconnect", "yes", "ssid", ssid)
    nmcli_cmd("connection", "modify", HOTSPOT_CONNECTION_NAME,
              "802-11-wireless.mode", "ap",
              "802-11-wireless.band", "bg",
              "ipv4.method", "shared",
              "ipv6.method", "ignore",
              "connection.autoconnect-priority", "-999")
    nmcli_cmd("connection", "modify", HOTSPOT_CONNECTION_NAME,
              "wifi-sec.key-mgmt", "wpa-psk",
              "wifi-sec.psk",      password,
              "wifi-sec.proto",    "rsn",   # WPA2 only
              "wifi-sec.pairwise", "ccmp",  # AES
              "wifi-sec.group",    "ccmp")  # AES
    up = nmcli_cmd("connection", "up", HOTSPOT_CONNECTION_NAME)
    if up.returncode != 0:
        _print_cmd_error("Failed to activate WPA2 hotspot", up)
    else:
        start_captive_dns(interface)
        add_captive_portal_redirect(interface)
    return up.returncode == 0

def add_captive_portal_redirect(interface, flask_port=5000):
    """Add iptables rules to redirect port 80/443 → Flask port on the hotspot interface.

    Android captive-portal probes hit port 80; without this redirect they get
    connection-refused and the OS drops the Wi-Fi network.
    """
    for src_port in (80, 443):
        _sudo("iptables", "-t", "nat", "-A", "PREROUTING",
              "-i", interface, "-p", "tcp", "--dport", str(src_port),
              "-j", "REDIRECT", "--to-port", str(flask_port))
    print(f"🔀 Captive-portal redirect: ports 80/443 → {flask_port}")

def remove_captive_portal_redirect(flask_port=5000):
    """Remove captive-portal iptables PREROUTING rules."""
    for src_port in (80, 443):
        for _ in range(5):
            r = _sudo("iptables", "-t", "nat", "-D", "PREROUTING",
                      "-p", "tcp", "--dport", str(src_port),
                      "-j", "REDIRECT", "--to-port", str(flask_port))
            if r.returncode != 0:
                break

def bring_down_hotspot():
    stop_captive_dns()
    remove_captive_portal_redirect()
    nmcli_cmd("connection", "down", HOTSPOT_CONNECTION_NAME)
    nmcli_cmd("connection", "delete", HOTSPOT_CONNECTION_NAME)


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
        cm.secure_manager.save_secure_config(full_cfg)
    else:
        # No encryption — plain JSON fallback
        cfg_path = os.path.join(ROOT_DIR, "config", "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(full_cfg, f, indent=2)

    # Also update in-memory state so subsequent code sees the change
    for k in removed:
        cm.config.pop(k, None)

    print(f"✅ Cleared admin credentials: {', '.join(removed)}")


def clear_saved_wifi_connections():
    """Delete all saved client-mode WiFi profiles from NetworkManager.

    This gives the customer device a factory-fresh NM state so that on first boot
    ``_has_saved_wifi_connections()`` returns False and the setup hotspot starts
    immediately instead of waiting out the 45-second startup grace window.
    """
    if shutil.which("nmcli") is None:
        print("⚠️  nmcli not found — skipping WiFi profile cleanup")
        return

    result = nmcli_cmd("-t", "-f", "NAME,TYPE", "connection", "show")
    if result.returncode != 0:
        print("⚠️  Could not list NM connections — skipping WiFi profile cleanup")
        return

    deleted = []
    errors = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(":", 1)
        if len(parts) < 2:
            continue
        name, conn_type = parts[0], parts[1]
        if conn_type != "wifi":
            continue
        # Leave our own setup profile alone (the app manages it at runtime)
        if name == HOTSPOT_CONNECTION_NAME or name.startswith("mempaper-setup"):
            continue
        r = nmcli_cmd("connection", "delete", name)
        if r.returncode == 0:
            deleted.append(name)
        else:
            errors.append(f"'{name}': {(r.stderr or r.stdout or '').strip()}")

    if deleted:
        print(f"🧹 Cleared {len(deleted)} saved WiFi profile(s): {', '.join(deleted)}")
    else:
        print("ℹ️  No saved client WiFi profiles to clear")
    for e in errors:
        print(f"⚠️  Could not delete WiFi profile {e}")


def connect_saved_wifi(interface):
    nmcli_cmd("connection", "down", HOTSPOT_CONNECTION_NAME)
    nmcli_cmd("device", "connect", interface)
    time.sleep(6)
    return is_wifi_connected(interface)

def run_wifi_onboarding(password, prefix, timeout_seconds):
    # Password parameter is kept for backward compatibility but ignored.

    if shutil.which("nmcli") is None:
        print("❌ nmcli not found. Install/enable NetworkManager first.")
        print("   sudo apt install network-manager")
        return False

    if _USE_SUDO_NMCLI:
        print("ℹ️  Running as non-root — using 'sudo nmcli' for hotspot management")

    interface = detect_wifi_interface()
    if not interface:
        print("❌ No Wi-Fi interface found (expected wlan0)")
        return False

    if is_wifi_connected(interface):
        print("✅ Wi-Fi already connected — no setup hotspot needed")
        start_service()
        return True

    ssid = build_hotspot_ssid(interface, prefix=prefix)
    password = build_hotspot_password(interface)

    if not bring_up_hotspot(interface, ssid, password):
        print("\u274c Could not start setup hotspot")
        return False

    write_setup_mode_flag(True, ssid=ssid, interface=interface)

    start_service()

    print()
    print("\U0001f4f6 Setup hotspot active")
    print(f"   SSID:     {ssid}")
    print(f"   Password: {password}")
    print(f"   Security: WPA2")
    print("   Open the dashboard via: http://192.168.12.1:5000")
    print("   Script will automatically switch to normal mode once Wi-Fi connects.")
    print()

    start_ts = time.time()
    last_reconnect_try = 0.0

    while True:
        now = time.time()

        if timeout_seconds > 0 and (now - start_ts) >= timeout_seconds:
            print("⏱️  Onboarding timeout reached; leaving setup hotspot active")
            return False

        if is_wifi_connected(interface):
            print("✅ Wi-Fi connected successfully")
            break

        # Periodically pause AP and let NetworkManager try known client networks.
        if now - last_reconnect_try >= 45:
            last_reconnect_try = now
            print("🔎 Checking whether saved Wi-Fi credentials can connect…")
            if connect_saved_wifi(interface):
                print("✅ Switched from setup hotspot to client Wi-Fi")
                break
            bring_up_hotspot(interface, ssid, password)
            write_setup_mode_flag(True, ssid=ssid, interface=interface)

        time.sleep(10)

    bring_down_hotspot()
    write_setup_mode_flag(False)
    start_service()
    print("✅ Setup hotspot disabled, normal operation mode active")
    return True

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

    # Remove saved client WiFi profiles so the customer device has a clean NM
    # state: on first boot _has_saved_wifi_connections() returns False and the
    # setup hotspot starts immediately (no 45s grace-window delay).
    print()
    print("🧹 Clearing saved WiFi profiles…")
    clear_saved_wifi_connections()

    # Ensure mempaper.service is enabled for automatic hotspot on next boot
    print()
    print("🔧 Ensuring mempaper.service is enabled…")
    result = subprocess.run(
        ["systemctl", "is-enabled", "--quiet", MEMPAPER_SERVICE],
        capture_output=True
    )
    if result.returncode != 0:
        _sudo("systemctl", "enable", MEMPAPER_SERVICE)
        print("✅  mempaper.service enabled")
    else:
        print("✅  mempaper.service already enabled")

    print()
    print("✅ Delivery state applied. Device is ready to ship.")
    print()
    print("   When the customer powers it on:")
    print("     • If no Wi-Fi is saved → app automatically starts setup hotspot")
    print( "       - SSID:     mempaper-XXXX  (4-digit suffix derived from device MAC)")
    print( "       - Security: WPA2  (password = 8 hex chars derived from device MAC)")
    print( "       - Scan the QR code on the e-ink display to join & open the setup page")
    print("     • Device connects to home Wi-Fi → hotspot disappears")
    print("     • Dashboard starts automatically and updates on new blocks")
    print()
    print("   Useful WiFi commands:")
    print("     • Show saved WiFi networks:")
    print("         nmcli -f NAME,TYPE connection show | grep wifi")
    print("     • Delete a specific WiFi:")
    print("         sudo nmcli connection delete \"<SSID>\"")
    print("     • Delete ALL saved WiFi networks:")
    print("         nmcli -t -f UUID,TYPE connection show | grep wifi | cut -d: -f1 | xargs -I{} sudo nmcli connection delete uuid {}")
    print()
    print("   To shut down: sudo shutdown -h now")

if __name__ == "__main__":
    main()
