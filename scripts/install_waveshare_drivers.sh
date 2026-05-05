#!/usr/bin/env bash
# Install Waveshare EPD driver files into display/drivers/
# Supports: 13.3inch e-Paper E (6-color) and 7.3inch e-Paper F (7-color)
#
# Each display gets its own subdirectory because their epdconfig.py files
# are incompatible (13.3E uses ctypes/CDLL, 7.3F uses spidev/RPi.GPIO).
#
# Driver files are MIT licensed by Waveshare Electronics.
# See: https://www.waveshare.com

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DRIVERS_DIR="$PROJECT_ROOT/display/drivers"
TMP_DIR="$(mktemp -d)"

echo "Installing Waveshare EPD drivers into $DRIVERS_DIR"
echo ""

# --- 13.3inch e-Paper E (6-color, epd13in3E) ---
DEST_13E="$DRIVERS_DIR/epd13in3E"
mkdir -p "$DEST_13E"

echo "[1/2] Downloading 13.3inch e-Paper E drivers..."
wget -q --show-progress \
    "https://files.waveshare.com/wiki/13.3inch%20e-Paper%20HAT%2B/13.3inch_e-Paper_E.zip" \
    -O "$TMP_DIR/13.3inch_e-Paper_E.zip"

echo "      Extracting..."
unzip -q "$TMP_DIR/13.3inch_e-Paper_E.zip" -d "$TMP_DIR/13.3E"

EPD13_PY=$(find "$TMP_DIR/13.3E" -name "epd13in3E.py" | head -1)
EPDCFG_13E=$(find "$TMP_DIR/13.3E" -name "epdconfig.py" | head -1)

if [ -z "$EPD13_PY" ]; then
    echo "      WARNING: epd13in3E.py not found in zip"
else
    cp "$EPD13_PY" "$DEST_13E/epd13in3E.py"
    echo "      Installed: epd13in3E/epd13in3E.py"
fi

if [ -z "$EPDCFG_13E" ]; then
    echo "      WARNING: epdconfig.py not found in zip"
else
    cp "$EPDCFG_13E" "$DEST_13E/epdconfig.py"
    echo "      Installed: epd13in3E/epdconfig.py"
fi

# Copy required compiled C libraries (.so) - epdconfig.py loads these via ctypes
if [ -n "$EPDCFG_13E" ]; then
    EPD13_LIB_DIR=$(dirname "$EPDCFG_13E")
    SO_COUNT=0
    for so_file in "$EPD13_LIB_DIR"/DEV_Config_*.so; do
        [ -f "$so_file" ] || continue
        cp "$so_file" "$DEST_13E/"
        echo "      Installed: epd13in3E/$(basename "$so_file")"
        SO_COUNT=$((SO_COUNT + 1))
    done
    if [ "$SO_COUNT" -eq 0 ]; then
        echo "      WARNING: No DEV_Config_*.so files found - display hardware will not work"
    fi
fi

# --- 7.3inch e-Paper F (7-color, epd7in3f) ---
DEST_7F="$DRIVERS_DIR/epd7in3f"
mkdir -p "$DEST_7F"

echo ""
echo "[2/2] Downloading 7.3inch e-Paper F drivers..."
wget -q --show-progress \
    "https://github.com/waveshare/e-Paper/archive/refs/heads/master.zip" \
    -O "$TMP_DIR/e-Paper-master.zip"

echo "      Extracting..."
unzip -q "$TMP_DIR/e-Paper-master.zip" \
    "e-Paper-master/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd7in3f.py" \
    "e-Paper-master/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py" \
    -d "$TMP_DIR/7.3F" 2>/dev/null || true

EPD7_PY=$(find "$TMP_DIR/7.3F" -name "epd7in3f.py" | head -1)
EPDCFG_7F=$(find "$TMP_DIR/7.3F" -name "epdconfig.py" | head -1)

if [ -z "$EPD7_PY" ]; then
    echo "      WARNING: epd7in3f.py not found — trying git clone fallback..."
    if command -v git &>/dev/null; then
        git clone --depth=1 --filter=blob:none --sparse \
            https://github.com/waveshare/e-Paper.git "$TMP_DIR/e-Paper-git" 2>/dev/null
        (cd "$TMP_DIR/e-Paper-git" && git sparse-checkout set \
            RaspberryPi_JetsonNano/python/lib/waveshare_epd 2>/dev/null)
        EPD7_PY=$(find "$TMP_DIR/e-Paper-git" -name "epd7in3f.py" | head -1)
        EPDCFG_7F=$(find "$TMP_DIR/e-Paper-git" -name "epdconfig.py" | head -1)
    fi
fi

if [ -z "$EPD7_PY" ]; then
    echo "      WARNING: epd7in3f.py not found"
else
    cp "$EPD7_PY" "$DEST_7F/epd7in3f.py"
    echo "      Installed: epd7in3f/epd7in3f.py"
fi

if [ -z "$EPDCFG_7F" ]; then
    echo "      WARNING: epdconfig.py for epd7in3f not found"
else
    cp "$EPDCFG_7F" "$DEST_7F/epdconfig.py"
    echo "      Installed: epd7in3f/epdconfig.py"
fi

# Cleanup
rm -rf "$TMP_DIR"

echo ""
echo "Done. Installed files:"
find "$DRIVERS_DIR" -type f | sort | sed "s|$DRIVERS_DIR/||"

echo ""
echo "Note: These driver files are MIT licensed by Waveshare Electronics."
echo "      See display/drivers/README.md for details."
