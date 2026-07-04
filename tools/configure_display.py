#!/usr/bin/env python3
"""
Display Device Configuration Helper

Utility script to set up different e-Paper display devices.
Shows available device types and updates configuration accordingly.
For native Waveshare displays, downloads driver files automatically.
"""

import fnmatch
import glob
import json
import os
import sys
import urllib.request
import zipfile
import tempfile

# Path to bundled driver directory (relative to project root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
DRIVERS_DIR = os.path.join(_PROJECT_ROOT, 'display', 'drivers')

# Common device configurations with typical display dimensions
DEVICE_CONFIGS = {
    "epd13in3E": {
        "name": "Waveshare 13.3\" 6-color (Spectra 6)",
        "width": 1200,
        "height": 1600,
        "description": "13.3 inch 6-color e-ink display (recommended for mempaper)",
        "driver_files": ["epd13in3E.py", "epdconfig.py", "DEV_Config_*.so"],
    },
    "epd7in3f": {
        "name": "Waveshare 7.3\" 7-color",
        "width": 800,
        "height": 480,
        "description": "7.3 inch 7-color e-ink display",
        "driver_files": ["epd7in3f.py", "epdconfig.py"],
    },
    # Displays below are not yet supported in this release
    # "waveshare_epd.epd5in83_v2": {
    #     "name": "Waveshare 5.83\" V2 (via omni-epd)",
    #     "width": 648,
    #     "height": 480,
    #     "description": "Medium sized black/white display",
    # },
    # "waveshare_epd.epd4in2": {
    #     "name": "Waveshare 4.2\" (via omni-epd)",
    #     "width": 400,
    #     "height": 300,
    #     "description": "Popular 4.2 inch black/white display",
    # },
    # "waveshare_epd.epd2in7": {
    #     "name": "Waveshare 2.7\" (via omni-epd)",
    #     "width": 264,
    #     "height": 176,
    #     "description": "Compact black/white display",
    # },
    # "inky.impression": {
    #     "name": "Inky Impression 7-color",
    #     "width": 448,
    #     "height": 600,
    #     "description": "Pimoroni 7-color e-ink display",
    # },
    # "inky.auto": {
    #     "name": "Inky Auto-detect",
    #     "width": 400,
    #     "height": 300,
    #     "description": "Auto-detect connected Inky display",
    # },
    # "omni_epd.mock": {
    #     "name": "Mock Display (Testing)",
    #     "width": 800,
    #     "height": 600,
    #     "description": "Virtual display for testing (no hardware)",
    # },
}

# Download sources for native Waveshare drivers.
# Two modes:
#   "url" + "files"  — download a zip and extract named files from it
#   "direct_files"   — download each file individually by URL (faster, no zip overhead)
DRIVER_DOWNLOADS = {
    "epd13in3E": {
        "url": "https://files.waveshare.com/wiki/13.3inch%20e-Paper%20HAT%2B/13.3inch_e-Paper_E.zip",
        "files": {
            "epd13in3E.py": None,   # searched by name inside zip
            "epdconfig.py": None,
            "DEV_Config_*.so": None, # native SPI library (glob pattern)
        },
    },
    "epd7in3f": {
        # Downloading the full e-Paper repo zip (~80 MB) for two small files is wasteful.
        # Fetch each file directly from raw.githubusercontent.com instead.
        "direct_files": {
            "epd7in3f.py": (
                "https://raw.githubusercontent.com/waveshare/e-Paper/master"
                "/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd7in3f.py"
            ),
            "epdconfig.py": (
                "https://raw.githubusercontent.com/waveshare/e-Paper/master"
                "/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py"
            ),
        },
    },
}


def load_config():
    config_path = os.path.join(_PROJECT_ROOT, "config", "config.json")
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ config/config.json not found")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config/config.json: {e}")
        return None


def save_config(config):
    config_path = os.path.join(_PROJECT_ROOT, "config", "config.json")
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False


def show_current_device(config):
    if not config:
        return
    device_name = config.get("omni_device_name", "epd13in3E")
    display_enabled = config.get("e-ink-display-connected", True)
    width = config.get("display_width", 800)
    height = config.get("display_height", 480)

    print(f"\nCurrent Display Configuration:")
    print(f"  Device: {device_name}")
    if device_name in DEVICE_CONFIGS:
        info = DEVICE_CONFIGS[device_name]
        print(f"  Name: {info['name']}")
        print(f"  Description: {info['description']}")
    print(f"  Status: {'ENABLED' if display_enabled else 'DISABLED'}")
    print(f"  Dimensions: {width}x{height}")


def list_available_devices():
    print("\nAvailable Display Devices:")
    print("=" * 55)
    for i, (device_id, info) in enumerate(DEVICE_CONFIGS.items(), 1):
        driver_note = " [auto-install drivers]" if device_id in DRIVER_DOWNLOADS else ""
        print(f"{i:2}. {info['name']}{driver_note}")
        print(f"    ID: {device_id}")
        print(f"    Size: {info['width']}x{info['height']}")
        print(f"    {info['description']}")
        print()


def _drivers_missing(device_id):
    """Return list of driver files that are not yet installed.
    
    Supports glob patterns (e.g. 'DEV_Config_*.so') in driver_files.
    A glob pattern is considered missing if no files match it.
    """
    info = DEVICE_CONFIGS.get(device_id, {})
    missing = []
    device_driver_dir = os.path.join(DRIVERS_DIR, device_id)
    for fname in info.get("driver_files", []):
        if '*' in fname or '?' in fname:
            # Glob pattern: check if any files match
            if not glob.glob(os.path.join(device_driver_dir, fname)):
                missing.append(fname)
        else:
            if not os.path.exists(os.path.join(device_driver_dir, fname)):
                missing.append(fname)
    return missing


def _extract_files_from_zip(zip_path, target_files, dest_dir):
    """Extract named files from a zip, searching all paths inside.
    
    Supports glob patterns in target_files (e.g. 'DEV_Config_*.so').
    Exact names are matched by basename; glob patterns use fnmatch.
    """
    installed = []
    with zipfile.ZipFile(zip_path) as zf:
        all_members = zf.namelist()
        # Build a map: basename -> full zip path (last one wins if duplicates)
        name_map = {}
        for member in all_members:
            basename = os.path.basename(member)
            if basename:
                name_map[basename] = member

        for fname in target_files:
            if '*' in fname or '?' in fname:
                # Glob pattern: find all matching basenames
                matched = [bn for bn in name_map if fnmatch.fnmatch(bn, fname)]
                if matched:
                    for bn in matched:
                        member = name_map[bn]
                        dest = os.path.join(dest_dir, bn)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(member) as src, open(dest, 'wb') as dst:
                            dst.write(src.read())
                        installed.append(bn)
                else:
                    print(f"   WARNING: no files matching '{fname}' found in zip")
            else:
                if fname in name_map:
                    member = name_map[fname]
                    dest = os.path.join(dest_dir, fname)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                    installed.append(fname)
                else:
                    print(f"   WARNING: {fname} not found in zip")
    return installed


def install_drivers(device_id, max_retries=5, retry_delay=10):
    """Download and install driver files for a native Waveshare display."""
    if device_id not in DRIVER_DOWNLOADS:
        return True  # Nothing to install for non-native devices

    missing = _drivers_missing(device_id)
    if not missing:
        print(f"   Drivers already installed.")
        return True

    dl = DRIVER_DOWNLOADS[device_id]
    device_driver_dir = os.path.join(DRIVERS_DIR, device_id)
    os.makedirs(device_driver_dir, exist_ok=True)

    # ── Direct file download mode ──────────────────────────────────────────────
    if "direct_files" in dl:
        installed = []
        for fname, url in dl["direct_files"].items():
            if fname not in missing:
                continue
            dest = os.path.join(device_driver_dir, fname)
            host = url.split('/')[2]
            for attempt in range(1, max_retries + 1):
                try:
                    if attempt > 1:
                        import time
                        print(f"   Retrying {fname} in {retry_delay}s (attempt {attempt}/{max_retries})...")
                        time.sleep(retry_delay)
                    print(f"   Downloading {fname} from {host}...")
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        with open(dest, 'wb') as f:
                            f.write(resp.read())
                    print(f"   Installed: {os.path.join(device_id, fname)}")
                    installed.append(fname)
                    break
                except Exception as e:
                    print(f"   ❌ Failed to download {fname} (attempt {attempt}/{max_retries}): {e}")
                    if attempt == max_retries:
                        print("   Try again: python tools/configure_display.py")
                        return False
        return len(installed) > 0

    # ── Zip download mode ──────────────────────────────────────────────────────
    url = dl["url"]
    target_files = list(dl["files"].keys())

    # Remove any leftover temp zips from interrupted previous attempts
    for _stale in glob.glob(os.path.join(device_driver_dir, 'tmp*.zip')):
        try:
            os.unlink(_stale)
        except Exception:
            pass

    def _report(count, block_size, total):
        if total > 0:
            pct = min(100, count * block_size * 100 // total)
            print(f"\r   Downloading... {pct}%", end="", flush=True)

    for attempt in range(1, max_retries + 1):
        tmp_path = None
        try:
            if attempt > 1:
                import time
                print(f"   Retrying in {retry_delay}s (attempt {attempt}/{max_retries})...")
                time.sleep(retry_delay)

            print(f"   Downloading drivers from {url.split('/')[2]}...")
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False, dir=device_driver_dir) as tmp:
                tmp_path = tmp.name

            with urllib.request.urlopen(url, timeout=60) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                with open(tmp_path, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        _report(downloaded, 1, total)
            print()  # newline after progress

            installed = _extract_files_from_zip(tmp_path, target_files, device_driver_dir)
            for fname in installed:
                print(f"   Installed: {os.path.join(device_id, fname)}")

            os.unlink(tmp_path)
            return len(installed) > 0

        except Exception as e:
            print(f"\n   ❌ Driver download failed (attempt {attempt}/{max_retries}): {e}")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            if attempt == max_retries:
                print("   Try again: python tools/configure_display.py")

    return False


def set_device(config, device_id, offline=False):
    if device_id not in DEVICE_CONFIGS:
        print(f"❌ Unknown device: {device_id}")
        return False

    info = DEVICE_CONFIGS[device_id]

    # Install drivers if needed (skip silently when offline)
    if device_id in DRIVER_DOWNLOADS:
        missing = _drivers_missing(device_id)
        if missing:
            if offline:
                print(f"   Skipping driver download (offline mode) — fetch via web GUI when online.")
            else:
                print(f"\nInstalling drivers for {info['name']}...")
                if not install_drivers(device_id):
                    print(f"   Continuing with config update anyway.")
        else:
            print(f"   Drivers already present.")

    config["omni_device_name"] = device_id
    config["display_width"] = info["width"]
    config["display_height"] = info["height"]

    if device_id != "omni_epd.mock":
        config["e-ink-display-connected"] = True

    if save_config(config):
        print(f"✅ Display device updated to: {info['name']}")
        print(f"   Device ID: {device_id}")
        print(f"   Dimensions: {info['width']}x{info['height']}")
        return True

    return False


def main():
    print("mempaper Display Device Configurator")
    print("=" * 45)

    config = load_config()
    if not config:
        sys.exit(1)

    show_current_device(config)

    if len(sys.argv) > 1:
        args = sys.argv[1:]
        offline = "--offline" in args
        args = [a for a in args if a != "--offline"]
        device_arg = args[0] if args else ""

        if device_arg.isdigit():
            device_num = int(device_arg)
            device_list = list(DEVICE_CONFIGS.keys())
            if 1 <= device_num <= len(device_list):
                set_device(config, device_list[device_num - 1], offline=offline)
            else:
                print(f"❌ Invalid device number: {device_num}")
                list_available_devices()
        elif device_arg in DEVICE_CONFIGS:
            set_device(config, device_arg, offline=offline)
        elif device_arg in ["list", "show", "devices"]:
            list_available_devices()
        else:
            print(f"❌ Unknown device or command: {device_arg}")
            list_available_devices()

        sys.exit(0)

    # Interactive mode
    while True:
        list_available_devices()
        print("Options:")
        print("  Enter device number or device ID")
        print("  'q' to quit")

        try:
            choice = input("\nSelect device: ").strip()

            if choice.lower() in ['q', 'quit', 'exit']:
                print("Goodbye!")
                break

            if choice.isdigit():
                device_num = int(choice)
                device_list = list(DEVICE_CONFIGS.keys())
                if 1 <= device_num <= len(device_list):
                    device_id = device_list[device_num - 1]
                    if set_device(config, device_id):
                        print("\nRestart the application for changes to take effect:")
                        print("   python serve.py")
                        break
                else:
                    print(f"❌ Invalid selection: {device_num}")
            elif choice in DEVICE_CONFIGS:
                if set_device(config, choice):
                    print("\nRestart the application for changes to take effect:")
                    print("   python serve.py")
                    break
            else:
                print(f"❌ Invalid selection: {choice}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
