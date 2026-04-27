#!/usr/bin/env python3
"""
Delivery State Script — Auslieferungszustand
=============================================
Renders a clean "factory default" dashboard image using static/memes/0.jpg as
the meme and zeroed-out placeholder values, then pushes it to the e-ink display.

Run this before shipping a device to a customer:

    python scripts/delivery_state.py

The script stops the mempaper service first (so the display isn't locked),
renders and shows the image, then exits.  You can then shut down the Pi safely.
"""

import os
import sys
import time
import subprocess

# ── Path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)

# ── Re-exec with venv Python if running under system Python ─────────────────
# Needed when script is called as "sudo python3 ..." instead of using the venv.
_VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "bin", "python3")
if os.path.exists(_VENV_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PYTHON):
    print(f"🔄 Re-launching with venv Python: {_VENV_PYTHON}")
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

MEME_PATH        = os.path.join(ROOT_DIR, "static", "memes", "0.jpg")
OUTPUT_WEB_PATH  = os.path.join(ROOT_DIR, "cache", "delivery_web.png")
OUTPUT_EINK_PATH = os.path.join(ROOT_DIR, "cache", "delivery_eink.png")

# ── Stop the running service so we can access the display ───────────────────
def stop_service():
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", "mempaper"],
        capture_output=True
    )
    if result.returncode == 0:
        print("⏹  Stopping mempaper service…")
        subprocess.run(["sudo", "systemctl", "stop", "mempaper"], check=False)
        time.sleep(2)
        print("✅ Service stopped")
    else:
        print("ℹ️  mempaper service is not running — proceeding")

# ── Load config ──────────────────────────────────────────────────────────────
def load_config():
    from managers.config_manager import ConfigManager
    return ConfigManager().get_current_config()

# ── Render the delivery image ────────────────────────────────────────────────
def render_delivery_image(config):
    from utils.translations import translations
    from lib.image_renderer import ImageRenderer

    lang         = config.get("language", "en")
    translations_dict = translations.get(lang, translations["en"])

    renderer = ImageRenderer(config, translations_dict)

    # Zero-out all data so no stale API values appear
    renderer._donation_data = None

    # Fake block data: height 0, a neutral placeholder hash
    BLOCK_HEIGHT = "0"
    BLOCK_HASH   = "0000000000000000000000000000000000000000000000000000000000000000"

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
    display = WaveshareDisplay()
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
    print("=" * 55)
    print("  mempaper — Auslieferungszustand / Delivery State")
    print("=" * 55)

    if not os.path.exists(MEME_PATH):
        print(f"❌ Meme image not found: {MEME_PATH}")
        sys.exit(1)

    stop_service()
    config     = load_config()
    image_path = render_delivery_image(config)
    show_on_eink(image_path)

    print()
    print("✅ Delivery state applied.")
    print("   You can now safely shut down the Raspberry Pi.")
    print("   sudo shutdown -h now")

if __name__ == "__main__":
    main()
