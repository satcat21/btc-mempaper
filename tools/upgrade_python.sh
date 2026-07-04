#!/usr/bin/env bash
# tools/upgrade_python.sh — safely upgrade the system Python minor version
#
# Run this ONLY after you have tested the new Python minor version end-to-end
# on Pi Zero 1 WH hardware (gevent, Pillow/WebP, all dependencies).
#
# What this script does:
#   1. Reads the required minor from tools/python_version (written by install.sh
#      or updated manually by the developer before pushing a release)
#   2. Unholds python3/python3-dev/python3-venv
#   3. apt upgrade installs the new Python minor
#   4. Rebuilds the virtual environment (old minor binaries are gone after upgrade)
#   5. Reinstalls all Python dependencies (including ARMv6 source builds if needed)
#   6. Re-holds python3 at the new minor
#   7. Records the new minor to tools/python_version
#   8. Restarts the mempaper service
#
# Usage:
#   sudo bash tools/upgrade_python.sh              # interactive
#   sudo bash tools/upgrade_python.sh --force      # no prompts
#
# Called automatically by mempaper_app.py during software updates when
# tools/python_version specifies a different minor than the running interpreter.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_USER="${MEMPAPER_SERVICE_USER:-mempaper}"
VENV_DIR="${PROJECT_DIR}/.venv"
VERSION_FILE="${SCRIPT_DIR}/python_version"
FORCE=false
NO_RESTART=false
for _arg in "$@"; do
    case "$_arg" in
        --force)      FORCE=true ;;
        --no-restart) NO_RESTART=true ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
ok()   { echo -e "  \033[32m✅\033[0m  $*"; }
warn() { echo -e "  \033[33m⚠️ \033[0m  $*"; }
fail() { echo -e "  \033[31m❌\033[0m  $*" >&2; exit 1; }
step() { echo -e "\n\033[1;33m━━━ $* ━━━\033[0m"; }

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ "$(id -u)" != "0" ]; then
    fail "Run with sudo: sudo bash $0 $*"
fi

# ── Detect OS and read required version ───────────────────────────────────────
if [ ! -f "$VERSION_FILE" ]; then
    fail "tools/python_version not found — cannot determine required Python minor"
fi
OS_CODENAME=$(. /etc/os-release 2>/dev/null && echo "${VERSION_CODENAME:-}" | tr '[:upper:]' '[:lower:]')
if [ -z "$OS_CODENAME" ]; then
    fail "Cannot detect OS version (VERSION_CODENAME not found in /etc/os-release)"
fi
REQUIRED_MINOR=$(grep -E "^${OS_CODENAME}=" "$VERSION_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
if [ -z "$REQUIRED_MINOR" ]; then
    fail "No Python version entry for OS '${OS_CODENAME}' in tools/python_version — add '${OS_CODENAME}=<minor>' to the file"
fi
if ! echo "$REQUIRED_MINOR" | grep -qE '^[0-9]+$'; then
    fail "Invalid Python minor '${REQUIRED_MINOR}' for '${OS_CODENAME}' in tools/python_version (expected a number)"
fi

# ── Current version ───────────────────────────────────────────────────────────
CURRENT_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "?")
CURRENT_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "3")

echo ""
echo "  Python upgrade check"
echo "  Current : Python ${CURRENT_MAJOR}.${CURRENT_MINOR}"
echo "  Required: Python ${CURRENT_MAJOR}.${REQUIRED_MINOR}"
echo ""

if [ "$CURRENT_MINOR" -ge "$REQUIRED_MINOR" ] 2>/dev/null; then
    ok "Python ${CURRENT_MAJOR}.${CURRENT_MINOR} meets requirement (≥ 3.${REQUIRED_MINOR}) — nothing to do."
    exit 0
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
if ! $FORCE; then
    echo "  This will:"
    echo "    1. Unhold python3, apt upgrade to ${CURRENT_MAJOR}.${REQUIRED_MINOR}"
    echo "    2. Delete and rebuild .venv (the old minor's binaries are gone after upgrade)"
    echo "    3. Reinstall all Python dependencies (~20 min on Pi Zero 1 WH)"
    echo "    4. Restart mempaper.service"
    echo ""
    read -rp "  Proceed? [y/N]: " _CHOICE
    [[ "$_CHOICE" =~ ^[Yy]$ ]] || { echo "  Aborted."; exit 0; }
fi

# ── Step 1: Unhold Python metapackages ───────────────────────────────────────
step "Unholding Python metapackages"
apt-mark unhold python3 python3-dev python3-venv 2>/dev/null || true
ok "Packages unheld"

# ── Step 2: Upgrade Python ────────────────────────────────────────────────────
step "Upgrading Python ${CURRENT_MAJOR}.${REQUIRED_MINOR} via apt"
apt-get update -qq
apt-get install -y "python3.${REQUIRED_MINOR}" "python3.${REQUIRED_MINOR}-dev" \
    "python3.${REQUIRED_MINOR}-venv" python3 python3-dev python3-venv 2>/dev/null \
    || apt-get upgrade -y python3 python3-dev python3-venv
NEW_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "?")
ok "System Python is now ${CURRENT_MAJOR}.${NEW_MINOR}"

# ── Step 3: Rebuild virtual environment ───────────────────────────────────────
step "Rebuilding virtual environment"
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    ok "Old venv removed"
fi
sudo -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
ok "New venv created with Python ${CURRENT_MAJOR}.${NEW_MINOR}"

# ── Step 4: Reinstall Python dependencies ────────────────────────────────────
step "Reinstalling Python dependencies"

PIP_PIWHEELS="--extra-index-url https://www.piwheels.org/simple"
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel -q

if [ -f "${PROJECT_DIR}/requirements.txt" ]; then
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install $PIP_PIWHEELS -r "${PROJECT_DIR}/requirements.txt"
    ok "Python packages installed"
else
    fail "requirements.txt not found"
fi

# GPIO/SPI (non-fatal on non-Pi hardware)
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install $PIP_PIWHEELS spidev gpiozero lgpio 2>/dev/null \
    && ok "GPIO/SPI libraries installed" \
    || warn "GPIO/SPI not available (OK if not on a Pi)"

# ARMv6 source rebuilds (Pi Zero 1 WH) — same logic as install.sh
ARCH=$(uname -m)
if [ "$ARCH" = "armv6l" ]; then
    # gevent
    if ! sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" -c "import gevent.ssl; print('ok')" >/dev/null 2>&1; then
        step "Rebuilding gevent from source (Pi Zero 1 WH — takes 10-20 minutes)"
        GEVENT_VER=$(sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" show gevent 2>/dev/null \
            | grep '^Version:' | awk '{print $2}' | tr -d '[:space:]')
        sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --force-reinstall --no-cache-dir --no-binary :all: \
            "${GEVENT_VER:+gevent==$GEVENT_VER}" "${GEVENT_VER:-gevent}"
        ok "gevent rebuilt from source"
    else
        ok "gevent ssl works — no rebuild needed"
    fi

    # Pillow + libwebp
    if ! sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" -c \
        'from PIL import Image; import io; buf=io.BytesIO(); Image.new("RGB",(1,1)).save(buf,"WEBP")' \
        >/dev/null 2>&1; then
        LIBWEBP_VER="1.5.0"
        LIBWEBP_URL="https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-${LIBWEBP_VER}.tar.gz"
        step "Building libwebp ${LIBWEBP_VER} from source (NEON disabled, Pi Zero 1 WH — ~10 min)"
        apt-get install -y cmake libjpeg-dev libpng-dev zlib1g-dev libfreetype6-dev libwebp-dev -q
        LIBWEBP_BUILD=$(mktemp -d)
        wget -qO "${LIBWEBP_BUILD}/libwebp.tar.gz" "$LIBWEBP_URL"
        tar xf "${LIBWEBP_BUILD}/libwebp.tar.gz" -C "$LIBWEBP_BUILD"
        LIBWEBP_SRC=$(find "$LIBWEBP_BUILD" -maxdepth 1 -name 'libwebp-*' -type d | head -1)
        mkdir -p "${LIBWEBP_SRC}/build"
        cmake -S "$LIBWEBP_SRC" -B "${LIBWEBP_SRC}/build" \
            -DWEBP_ENABLE_SIMD=OFF -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1
        make -j1 -C "${LIBWEBP_SRC}/build" >/dev/null 2>&1
        make -C "${LIBWEBP_SRC}/build" install >/dev/null 2>&1
        LIBWEBP_SO=$(find /usr/local/lib -name 'libwebp.so.*.*.*' | head -1)
        LIBWEBP_SYS=$(find /lib/arm-linux-gnueabihf -name 'libwebp.so.*.*.*' 2>/dev/null | head -1)
        [ -n "$LIBWEBP_SO" ] && [ -n "$LIBWEBP_SYS" ] && cp "$LIBWEBP_SO" "$LIBWEBP_SYS"
        ldconfig
        rm -rf "$LIBWEBP_BUILD"
        ok "libwebp ${LIBWEBP_VER} built without NEON"

        step "Rebuilding Pillow from source"
        PILLOW_VER=$(sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" show Pillow 2>/dev/null \
            | grep '^Version:' | awk '{print $2}' | tr -d '[:space:]')
        sudo -u "$SERVICE_USER" TMPDIR="$(getent passwd "$SERVICE_USER" | cut -d: -f6)" \
            "$VENV_DIR/bin/pip" install --force-reinstall --no-cache-dir --no-binary :all: \
            "${PILLOW_VER:+Pillow==$PILLOW_VER}" "${PILLOW_VER:-Pillow}"
        ok "Pillow rebuilt from source"
    else
        ok "Pillow WebP works — no rebuild needed"
    fi
fi

# ── Step 5: Re-hold Python metapackages ───────────────────────────────────────
step "Re-locking Python ${CURRENT_MAJOR}.${NEW_MINOR}"
apt-mark hold python3 python3-dev python3-venv >/dev/null 2>&1 \
    && ok "Python ${CURRENT_MAJOR}.${NEW_MINOR} locked (apt-mark hold)"

# ── Step 6: Restart service ───────────────────────────────────────────────────
if $NO_RESTART; then
    ok "Skipping service restart (--no-restart; caller will restart)"
else
    step "Restarting mempaper service"
    systemctl restart mempaper.service 2>/dev/null \
        && ok "mempaper.service restarted" \
        || warn "Could not restart mempaper.service (start it manually)"
fi

echo ""
ok "Python ${CURRENT_MAJOR}.${NEW_MINOR} upgrade complete."
echo ""
