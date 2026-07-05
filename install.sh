#!/usr/bin/env bash
# ============================================================================
# mempaper one-click installer
# ============================================================================
# Sets up a fresh Raspberry Pi (Raspberry Pi OS Lite 32-bit, Bookworm or Trixie) as a mempaper device.
#
# Usage:
#   git clone https://github.com/satcat21/btc-mempaper.git
#   cd btc-mempaper
#   bash install.sh
#
# What it does:
#   1. Installs system packages (apt-requirements.txt)
#   2. Creates Python virtual environment and installs pip packages
#   3. Installs Raspberry Pi GPIO/SPI libraries + rebuilds Pillow (Pi Zero 1 WH)
#   4. Copies example config
#   5. Configures e-ink display (interactive selection + driver download)
#   6. Generates and installs systemd service file
#   7. Installs WiFi/hotspot permissions (polkit + sudoers)
#   8. Disables WiFi power management (prevents BCM43430 beacon misses)
#   9. Enables and starts the mempaper service
#
# After install the Pi enters hotspot onboarding mode — connect to the
# mempaper WiFi network and open http://192.168.4.1:5000 to set up.
# ============================================================================

set -e

SERVICE_USER="mempaper"
# If a prior run already relocated the repo into the service-user home,
# the runner needs traverse permission before we can resolve SCRIPT_DIR.
# g+x is needed because pi (added to the mempaper group) uses group permissions,
# not "other" permissions, when accessing mempaper-owned paths.
sudo chmod g+x,o+x "/home/${SERVICE_USER}" 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
step() { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }

# ── Pre-flight checks ──────────────────────────────────────────────────────
if [ "$(uname -s)" != "Linux" ]; then
    fail "This installer is for Raspberry Pi (Linux) only."
fi

if [ "$(id -u)" = "0" ]; then
    fail "Do not run as root. Run as your normal user (e.g. 'pi'). The script uses sudo where needed."
fi

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install it with: sudo apt install python3"
fi

python3 - <<'PYEOF'
W = '\033[1;97m'       # bold bright white — "mem"
O = '\033[38;5;214m'   # orange            — "paper"
Y = '\033[1;33m'       # bold yellow       — subtitles (matches step headers)
R = '\033[0m'
lines = [
    "  _ __ ___   ___ _ __ ___  _ __   __ _ _ __   ___ _ __",
    " | '_ ` _ \\ / _ \\ '_ ` _ \\| '_ \\ / _` | '_ \\ / _ \\ '__|",
    " | | | | | |  __/ | | | | | |_) | (_| | |_) |  __/ |",
    " |_| |_| |_|\\___|_| |_| |_| .__/ \\__,_| .__/ \\___|_|",
    "                          |_|         |_|",
]
s = 26
for l in lines:
    print(f"{W}{l[:s]}{O}{l[s:]}{R}")
print(f"\n{Y}               Bitcoin Meme Block Clock{R}")
print(f"\n{Y}                      Installer{R}\n")
PYEOF
echo ""
echo "  User:    $SERVICE_USER (service account)"
echo "  Runner:  $(whoami)"
echo "  Path:    $SCRIPT_DIR"
echo ""

_T0=$(date +%s)   # installation start — used for elapsed time at the end

# ══ Quick Setup — all questions upfront ═══════════════════════════════════════
echo ""
echo -e "  ${YELLOW}━━━ Configuration ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  Answer the questions below, then the rest runs without interruption."
echo ""

# [1] Display
echo -e "  ${CYAN}Display${NC}"
echo ""
echo -e "    ${CYAN}1${NC}. Waveshare 13.3\" 6-color (Spectra 6)  ${GREEN}[recommended]${NC}"
echo -e "    ${CYAN}2${NC}. Waveshare 7.3\" 7-color"
echo -e "    ${CYAN}3${NC}. Waveshare 5.83\" V2 (via omni-epd)"
echo -e "    ${CYAN}4${NC}. Waveshare 4.2\" (via omni-epd)"
echo -e "    ${CYAN}5${NC}. Waveshare 2.7\" (via omni-epd)"
echo -e "    ${CYAN}6${NC}. Inky Impression 7-color"
echo -e "    ${CYAN}7${NC}. Inky Auto-detect"
echo -e "    ${CYAN}8${NC}. Mock Display (testing, no hardware)"
echo -e "    ${CYAN}s${NC}. Skip — configure later via web UI"
echo ""
DISPLAY_CHOICE=""
while true; do
    read -rp "  Select display [1-8, s]: " DISPLAY_CHOICE
    case "$DISPLAY_CHOICE" in
        [1-8]|s|S) break ;;
        *) echo "  Invalid choice. Enter 1-8 or s to skip." ;;
    esac
done
echo ""

# [2] Admin account
echo -e "  ${CYAN}Admin account${NC}"
ADMIN_USERNAME=""
ADMIN_PASSWORD=""
# Check if config already has users (system python3, before venv exists)
_HAS_USERS=false
if [ -f "config/config.json" ]; then
    _HAS_USERS=$(python3 -c "
import json, sys
try:
    c = json.load(open('config/config.json'))
    print('true' if c.get('admin_users') else 'false')
except Exception:
    print('false')
" 2>/dev/null || echo "false")
fi
if [ "$_HAS_USERS" = "true" ]; then
    ok "Admin users already configured — skipping"
else
    echo "  Set credentials for the mempaper web interface."
    echo ""
    while true; do
        read -rp "  Admin username: " ADMIN_USERNAME
        [ -n "$ADMIN_USERNAME" ] && break
        echo "  Username cannot be empty."
    done
    _pw_ok=false
    while [ "$_pw_ok" = "false" ]; do
        read -rsp "  Admin password (≥16 chars, upper+lower+digit+special): " ADMIN_PASSWORD
        echo ""
        # Validate via python3 using env var to avoid quoting/injection issues
        _ERR=$(_PW="$ADMIN_PASSWORD" python3 - <<'PYEOF' 2>&1
import re, sys, os
pw = os.environ.get('_PW', '')
issues = []
if len(pw) < 16:                         issues.append('at least 16 characters')
if not re.search(r'[A-Z]', pw):          issues.append('an uppercase letter')
if not re.search(r'[a-z]', pw):          issues.append('a lowercase letter')
if not re.search(r'[0-9]', pw):          issues.append('a number')
if not re.search(r'[^A-Za-z0-9]', pw):  issues.append('a special character')
if issues:
    print('  Password needs: ' + ', '.join(issues) + '.')
    sys.exit(1)
PYEOF
)
        if [ -n "$_ERR" ]; then
            echo "$_ERR"
            continue
        fi
        read -rsp "  Confirm password: " _ADMIN_PW2
        echo ""
        if [ "$ADMIN_PASSWORD" != "$_ADMIN_PW2" ]; then
            echo "  Passwords do not match."
            continue
        fi
        _pw_ok=true
    done
fi
echo ""

# [3] Options — press Enter to accept defaults
echo -e "  ${CYAN}Options${NC} — press Enter to accept defaults"
echo ""
read -rp "  Minify JavaScript (better performance)?   [Y/n]: " MINIFY_CHOICE
MINIFY_CHOICE="${MINIFY_CHOICE:-Y}"
read -rp "  UFW firewall (restrict to LAN only)?       [Y/n]: " UFW_CHOICE
UFW_CHOICE="${UFW_CHOICE:-Y}"
read -rp "  fail2ban (SSH brute-force protection)?     [Y/n]: " F2B_CHOICE
F2B_CHOICE="${F2B_CHOICE:-Y}"
read -rp "  Unattended security updates?               [Y/n]: " UU_CHOICE
UU_CHOICE="${UU_CHOICE:-Y}"
UU_REBOOT_CHOICE="Y"
UU_REBOOT_TIME="04:00"
if [[ "$UU_CHOICE" =~ ^[Yy]$ ]]; then
    read -rp "  Auto-reboot after updates?                 [Y/n]: " UU_REBOOT_CHOICE
    UU_REBOOT_CHOICE="${UU_REBOOT_CHOICE:-Y}"
    if [[ "$UU_REBOOT_CHOICE" =~ ^[Yy]$ ]]; then
        read -rp "  Auto-reboot time (24h)?                    [04:00]: " UU_REBOOT_TIME
        UU_REBOOT_TIME="${UU_REBOOT_TIME:-04:00}"
        if ! echo "$UU_REBOOT_TIME" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; then
            warn "Invalid time '${UU_REBOOT_TIME}' — using 04:00"
            UU_REBOOT_TIME="04:00"
        fi
    fi
fi
echo ""
echo -e "  ${CYAN}SSH hardening${NC} — disable password login, require SSH key"
echo "  Add your public key via Settings > SSH in the web UI after install."
echo "  Without a key, physical access is needed to SSH in."
echo ""
read -rp "  Disable SSH password authentication?       [Y/n]: " SSH_HARDENING
SSH_HARDENING="${SSH_HARDENING:-Y}"
echo ""

echo -e "  ${YELLOW}━━━ All set — starting installation now ━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Step 0: Create mempaper service user ──────────────────────────────────
step "Step 0 — Creating mempaper service user"

if id "$SERVICE_USER" >/dev/null 2>&1; then
    ok "User '$SERVICE_USER' already exists"
else
    sudo useradd -r -m -s /bin/bash "$SERVICE_USER"
    ok "Created service user '$SERVICE_USER'"
fi

# Ensure required group memberships
REQUIRED_GROUPS="netdev gpio spi i2c"
for grp in $REQUIRED_GROUPS; do
    if getent group "$grp" >/dev/null 2>&1; then
        if id -nG "$SERVICE_USER" | grep -qw "$grp"; then
            ok "User '$SERVICE_USER' is already in the '$grp' group"
        else
            sudo usermod -aG "$grp" "$SERVICE_USER"
            ok "Added '$SERVICE_USER' to the '$grp' group"
        fi
    else
        warn "Group '$grp' does not exist — skipping (OK on non-Pi systems)"
    fi
done

# ── Relocate repo into the service user's home directory ──────────────────
# The pi user clones to /home/pi/btc-mempaper; the app should live at
# /home/mempaper/btc-mempaper so all app files are owned and contained by the
# service account rather than scattered under the pi home.
APP_DIR="/home/${SERVICE_USER}/$(basename "$SCRIPT_DIR")"
if [ "$SCRIPT_DIR" != "$APP_DIR" ]; then
    if [ -d "$APP_DIR" ]; then
        warn "Destination $APP_DIR already exists — skipping relocation, continuing from there"
    else
        sudo mv "$SCRIPT_DIR" "$APP_DIR"
        ok "Repo relocated to '$APP_DIR'"
    fi
    SCRIPT_DIR="$APP_DIR"
    VENV_DIR="$SCRIPT_DIR/.venv"
    sudo chmod g+x,o+x "/home/${SERVICE_USER}"
    cd "$SCRIPT_DIR"
fi

# Grant ownership of the repo directory to the service user so it can
# write config/cache files and create the venv
sudo chown -R "$SERVICE_USER":"$SERVICE_USER" "$SCRIPT_DIR"
ok "Repo ownership set to '$SERVICE_USER'"

# Allow the pi user (and any other admin) to SCP files into static/memes/.
# pi is added to the mempaper group, which uses GROUP permissions on these paths —
# so both the repo root and static/ need g+rx, not just o+x.
sudo chmod g+rx "$SCRIPT_DIR"
sudo mkdir -p "$SCRIPT_DIR/static/memes"
sudo chown "$SERVICE_USER":"$SERVICE_USER" "$SCRIPT_DIR/static"
sudo chmod g+rx "$SCRIPT_DIR/static"
sudo chown "$SERVICE_USER":"$SERVICE_USER" "$SCRIPT_DIR/static/memes"
sudo chmod 2775 "$SCRIPT_DIR/static/memes"  # setgid + group write; new files inherit mempaper group
if id pi >/dev/null 2>&1; then
    if ! groups pi | grep -qw "$SERVICE_USER"; then
        sudo usermod -aG "$SERVICE_USER" pi
        ok "Added 'pi' user to '$SERVICE_USER' group (SCP access to static/memes)"
    else
        ok "'pi' user already in '$SERVICE_USER' group"
    fi
fi

# Pre-create .ssh dirs so ReadWritePaths in the service unit takes effect.
# ProtectSystem=strict silently ignores ReadWritePaths entries that don't exist
# at service start, which would prevent SSH key writes from the web GUI.
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
sudo -u "$SERVICE_USER" mkdir -p "$SERVICE_HOME/.ssh"
sudo chmod 700 "$SERVICE_HOME/.ssh"
# Pre-create authorized_keys so the web GUI can write to it immediately.
# The file must exist before the service starts — ReadWritePaths only bind-mounts
# paths that already exist; a missing file stays unwritable inside the sandbox.
[ -f "$SERVICE_HOME/.ssh/authorized_keys" ] || sudo -u "$SERVICE_USER" touch "$SERVICE_HOME/.ssh/authorized_keys"
sudo chmod 600 "$SERVICE_HOME/.ssh/authorized_keys"
sudo mkdir -p /home/pi/.ssh
sudo chmod 700 /home/pi/.ssh
[ -f /home/pi/.ssh/authorized_keys ] || sudo touch /home/pi/.ssh/authorized_keys
sudo chmod 600 /home/pi/.ssh/authorized_keys
# chown /home/pi/.ssh only if pi user exists
if id pi >/dev/null 2>&1; then
    sudo chown pi:pi /home/pi/.ssh /home/pi/.ssh/authorized_keys
fi
ok ".ssh directories and authorized_keys files created for SSH key management"

# ── Step 1: System packages ────────────────────────────────────────────────
step "Step 1/9 — Installing system packages"

sudo apt-get update -qq

if [ -f apt-requirements.txt ]; then
    # Filter out comments and blank lines
    APT_PKGS=$(grep -v '^\s*#' apt-requirements.txt | grep -v '^\s*$' | tr '\n' ' ')
    sudo apt-get install -y $APT_PKGS
    ok "System packages installed"
else
    warn "apt-requirements.txt not found — skipping"
fi

# Ensure python3-venv is available
sudo apt-get install -y python3-venv
ok "python3-venv available"

# ── Step 2: Python virtual environment ─────────────────────────────────────
step "Step 2/9 — Setting up Python virtual environment"

if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
else
    ok "Virtual environment already exists"
fi

sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel -q
ok "pip/setuptools upgraded"

# Lock the Python minor version so 'apt upgrade' can never switch the default
# Python (e.g. 3.13 → 3.14) and orphan the virtual environment.
# Security patches within the same minor (python3.13 updates) still flow —
# only the metapackage that controls which minor is the default is held.
# To intentionally upgrade: use tools/upgrade_python.sh after testing.
_PYMINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "?")
sudo apt-mark hold python3 python3-dev python3-venv >/dev/null 2>&1 \
    && ok "Python 3.${_PYMINOR} version locked — run tools/upgrade_python.sh to move to a new minor" \
    || warn "Could not lock Python version (non-fatal)"

# Validate that this OS has an entry in the Python version spec file.
# tools/python_version is a git-managed spec (codename=minor pairs) — not written here.
_OS_CODENAME=$(. /etc/os-release 2>/dev/null && echo "${VERSION_CODENAME:-}" | tr '[:upper:]' '[:lower:]')
_VERSION_FILE="${SCRIPT_DIR}/tools/python_version"
if [ -n "$_OS_CODENAME" ] && ! grep -qE "^${_OS_CODENAME}=" "$_VERSION_FILE" 2>/dev/null; then
    warn "No Python version entry for OS '${_OS_CODENAME}' in tools/python_version — web update auto-upgrade will not trigger for this OS"
fi

# Always include piwheels so ARMv6-compatible wheels are found on any OS.
# Trixie (Debian 13) does not ship with piwheels in pip.conf unlike Bookworm.
PIP_PIWHEELS="--extra-index-url https://www.piwheels.org/simple"

# ── Step 3: Python dependencies ────────────────────────────────────────────
step "Step 3/9 — Installing Python dependencies"

if [ -f requirements.txt ]; then
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install $PIP_PIWHEELS -r requirements.txt
    ok "Python packages installed"
else
    fail "requirements.txt not found"
fi

# Raspberry Pi specific packages (GPIO/SPI)
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install $PIP_PIWHEELS spidev gpiozero lgpio 2>/dev/null \
    && ok "GPIO/SPI libraries installed" \
    || warn "GPIO/SPI libraries not available (OK if not running on a Pi)"

# On Pi Zero 1 WH (armv6l) with Python 3.13, piwheels does not yet provide
# armv6l wheels for Python 3.13. PyPI wheels target armv7+ and cause SIGILL or
# Python 3.13 ssl incompatibility. We rebuild gevent and Pillow from source.
# Raspbian Trixie's system libwebp is compiled for ARMv7+ NEON and causes SIGILL
# on ARMv6 during both encode and decode. We build libwebp from source with NEON
# disabled and install it as a shared library so Pillow links against it at runtime.
ARCH=$(uname -m)
if [ "$ARCH" = "armv6l" ]; then
    # gevent: test ssl C extension (SIGILL on armv7+ wheel, TypeError on Python 3.13 with ssl=False)
    if sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" -c "import gevent.ssl; print('ok')" >/dev/null 2>&1; then
        ok "gevent ssl works on armv6l — skipping source rebuild"
    else
        step "Rebuilding gevent from source (Pi Zero 1 WH — takes 10-20 minutes)"
        GEVENT_VER=$(sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" show gevent 2>/dev/null \
            | grep '^Version:' | awk '{print $2}' | tr -d '[:space:]')
        GEVENT_REQ="${GEVENT_VER:+gevent==$GEVENT_VER}"
        GEVENT_REQ="${GEVENT_REQ:-gevent}"
        sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --force-reinstall --no-cache-dir --no-binary :all: "$GEVENT_REQ"
        ok "gevent rebuilt from source (${GEVENT_REQ})"
    fi

    # libwebp: Raspbian Trixie's package is compiled for ARMv7+ NEON — causes SIGILL on ARMv6.
    # Build from source with NEON disabled, install as shared lib to override the system one.
    # Test by probing WebP encode in a subprocess (SIGILL kills the child, not the app).
    if sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" -c \
        'from PIL import Image; import io; buf=io.BytesIO(); Image.new("RGB",(1,1)).save(buf,"WEBP")' \
        >/dev/null 2>&1; then
        ok "Pillow WebP works on armv6l — skipping libwebp source build"
    else
        LIBWEBP_VER="1.5.0"
        LIBWEBP_URL="https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-${LIBWEBP_VER}.tar.gz"
        step "Building libwebp ${LIBWEBP_VER} from source with NEON disabled (Pi Zero 1 WH — takes ~10 minutes)"
        sudo apt-get install -y cmake
        LIBWEBP_BUILD_DIR=$(mktemp -d)
        wget -qO "${LIBWEBP_BUILD_DIR}/libwebp.tar.gz" "$LIBWEBP_URL"
        tar xf "${LIBWEBP_BUILD_DIR}/libwebp.tar.gz" -C "$LIBWEBP_BUILD_DIR"
        LIBWEBP_SRC=$(find "$LIBWEBP_BUILD_DIR" -maxdepth 1 -name 'libwebp-*' -type d | head -1)
        mkdir -p "${LIBWEBP_SRC}/build"
        cmake -S "$LIBWEBP_SRC" -B "${LIBWEBP_SRC}/build" \
            -DWEBP_ENABLE_SIMD=OFF -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
            >/dev/null 2>&1
        make -j1 -C "${LIBWEBP_SRC}/build" >/dev/null 2>&1
        sudo make -C "${LIBWEBP_SRC}/build" install >/dev/null 2>&1
        # Overwrite the system libwebp shared library so runtime picks up our NEON-free build.
        LIBWEBP_SO=$(find /usr/local/lib -name 'libwebp.so.*.*.*' | head -1)
        LIBWEBP_SYSTEM=$(find /lib/arm-linux-gnueabihf -name 'libwebp.so.*.*.*' 2>/dev/null | head -1)
        if [ -n "$LIBWEBP_SO" ] && [ -n "$LIBWEBP_SYSTEM" ]; then
            sudo cp "$LIBWEBP_SO" "$LIBWEBP_SYSTEM"
        fi
        sudo ldconfig
        rm -rf "$LIBWEBP_BUILD_DIR"
        ok "libwebp ${LIBWEBP_VER} built without NEON and installed"

        # Rebuild Pillow from source so it links against the new NEON-free libwebp.
        step "Rebuilding Pillow from source (Pi Zero 1 WH — takes a few minutes)"
        PILLOW_VER=$(sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" show Pillow 2>/dev/null \
            | grep '^Version:' | awk '{print $2}' | tr -d '[:space:]')
        PILLOW_REQ="${PILLOW_VER:+Pillow==$PILLOW_VER}"
        PILLOW_REQ="${PILLOW_REQ:-Pillow}"
        sudo apt-get install -y libjpeg-dev libpng-dev zlib1g-dev libfreetype6-dev libwebp-dev
        sudo -u "$SERVICE_USER" TMPDIR="$SERVICE_HOME" "$VENV_DIR/bin/pip" install \
            --force-reinstall --no-cache-dir --no-binary :all: "$PILLOW_REQ"
        ok "Pillow rebuilt from source with ARMv6-safe WebP (${PILLOW_REQ})"
    fi
fi

# ── Optional: Minify JavaScript ───────────────────────────────────────────
if [[ "$MINIFY_CHOICE" =~ ^[Yy]$ ]]; then
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" tools/minify.py
    ok "JavaScript minified — served from static/js/dist/"
else
    ok "Skipping JS minification (app will use unminified source files)"
fi

# ── Step 4: Configuration ─────────────────────────────────────────────────
step "Step 4/9 — Setting up configuration"

sudo -u "$SERVICE_USER" mkdir -p config cache

if [ ! -f config/config.json ]; then
    if [ -f config/config.json.example ]; then
        sudo -u "$SERVICE_USER" cp config/config.json.example config/config.json
        ok "Config created from example"
    else
        warn "No config.json.example found — service will create defaults on first start"
    fi
else
    ok "config.json already exists"
fi

# Secure config directory and file (contains password hashes and API keys).
# Group-readable (750/640) so the mempaper group (pi user) can read the config
# for tools like the 'mempaper' CLI command, without exposing it to other users.
sudo chmod 750 config/
[ -f config/config.json ] && sudo chmod 640 config/config.json
ok "Config permissions secured (dir 750, file 640 — readable by mempaper group)"

# ── Admin account (non-interactive, credentials collected upfront) ────────────
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
    printf '%s\n%s\n' "$ADMIN_USERNAME" "$ADMIN_PASSWORD" | \
        sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" tools/setup_user.py --stdin
    ok "Admin account created"
else
    ok "Skipping admin account — create later via web UI or: python tools/setup_user.py"
fi

# ── Step 5: E-Ink display configuration ───────────────────────────────────
step "Step 5/9 — Configuring e-ink display"

if [ "$DISPLAY_CHOICE" != "s" ] && [ "$DISPLAY_CHOICE" != "S" ]; then
    echo ""
    # Pass --offline flag when no internet is reachable so driver download is
    # skipped silently rather than retried repeatedly — drivers can be fetched
    # later via the web GUI.
    if curl -fsS --max-time 5 https://github.com >/dev/null 2>&1; then
        CONFIGURE_ARGS="$DISPLAY_CHOICE"
    else
        warn "No internet connection — driver download skipped. Select the display again in the web GUI once online to fetch drivers automatically."
        CONFIGURE_ARGS="$DISPLAY_CHOICE --offline"
    fi
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" tools/configure_display.py $CONFIGURE_ARGS
    ok "Display configured"

else
    warn "Display configuration skipped — configure later in Settings > Display"
fi

# Enable SPI interface for all real display choices (including skip — user may
# connect a display later via web UI, and SPI is harmless when unused).
# Only skip for option 8 (Mock/virtual display — no hardware, no SPI needed).
if [ "$DISPLAY_CHOICE" != "8" ]; then
    echo ""
    echo "  Enabling SPI interface..."
    if command -v raspi-config >/dev/null 2>&1; then
        sudo raspi-config nonint do_spi 0
        ok "SPI interface enabled"
        if [ ! -e /dev/spidev0.0 ]; then
            warn "SPI device not yet available — a reboot is required after install"
        fi
    else
        warn "raspi-config not found — enable SPI manually: sudo raspi-config > Interface Options > SPI"
    fi
fi

# ── Step 6: Systemd service ───────────────────────────────────────────────
step "Step 6/9 — Installing systemd service"

sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" tools/generate_service_file.py --quiet
sudo cp mempaper.service /etc/systemd/system/mempaper.service
sudo systemctl daemon-reload
sudo systemctl enable mempaper.service
ok "mempaper.service installed and enabled"

# ── Step 7: WiFi/hotspot permissions ───────────────────────────────────────
step "Step 7/9 — Installing WiFi hotspot permissions"

sudo bash tools/install_wifi_permissions.sh "$SERVICE_USER"
ok "WiFi permissions installed"

# ── Step 8: Disable WiFi power management ────────────────────────────────
step "Step 8/9 — Disabling WiFi power management"

NM_CONF_DIR="/etc/NetworkManager/conf.d"
NM_POWERSAVE_CONF="$NM_CONF_DIR/99-disable-powersave.conf"

if [ -d "$NM_CONF_DIR" ]; then
    if [ ! -f "$NM_POWERSAVE_CONF" ]; then
        sudo tee "$NM_POWERSAVE_CONF" > /dev/null << 'EOF'
[connection]
wifi.powersave = 2
EOF
        sudo systemctl restart NetworkManager 2>/dev/null || true
        ok "WiFi power management disabled (prevents BCM43430 beacon misses)"
    else
        ok "WiFi power management already disabled"
    fi
else
    warn "NetworkManager conf.d not found — skipping powersave configuration"
fi

# ── SSH login overview (MOTD) ─────────────────────────────────────────────────
MOTD_SCRIPT="${SCRIPT_DIR}/tools/mempaper-motd.sh"
MOTD_LINK="/etc/profile.d/mempaper-motd.sh"
sudo chmod +x "$MOTD_SCRIPT"
if sudo ln -sf "$MOTD_SCRIPT" "$MOTD_LINK" 2>/dev/null; then
    ok "SSH login overview installed (${MOTD_LINK})"
else
    warn "Could not install SSH login overview — symlink $MOTD_LINK failed"
fi

# Install 'mempaper' CLI command — runs the same overview on demand
MEMPAPER_CMD="/usr/local/bin/mempaper"
if sudo ln -sf "$MOTD_SCRIPT" "$MEMPAPER_CMD" 2>/dev/null; then
    ok "CLI command installed — run 'mempaper' anywhere to show the overview"
else
    warn "Could not install 'mempaper' CLI command — symlink $MEMPAPER_CMD failed"
fi

# ── Optional: UFW firewall ────────────────────────────────────────────────
if [[ "$UFW_CHOICE" =~ ^[Yy]$ ]]; then
    sudo apt-get install -y ufw -q
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    # Remove any pre-existing broad rules that would override the LAN-only rules below
    for port in 22 5000; do
        sudo ufw delete allow "${port}/tcp" 2>/dev/null || true
        sudo ufw delete allow "${port}"     2>/dev/null || true
    done
    for subnet in 192.168.0.0/16 10.0.0.0/8 172.16.0.0/12; do
        sudo ufw allow from "$subnet" to any port 22
        sudo ufw allow from "$subnet" to any port 5000
    done
    # Allow WireGuard if installed
    if command -v wg >/dev/null 2>&1; then
        sudo ufw allow 51820/udp
        ok "WireGuard detected — UDP 51820 allowed"
    fi
    sudo ufw --force enable
    ok "UFW firewall configured (SSH + port 5000 restricted to LAN only)"
else
    ok "Skipping UFW — configure later with: sudo ufw enable"
fi

# ── Optional: fail2ban ────────────────────────────────────────────────────
if [[ "$F2B_CHOICE" =~ ^[Yy]$ ]]; then
    sudo apt-get install -y fail2ban -q
    ok "fail2ban installed"
else
    ok "Skipping fail2ban"
fi

# ── Optional: unattended-upgrades ─────────────────────────────────────────
if [[ "$UU_CHOICE" =~ ^[Yy]$ ]]; then
    sudo apt-get install -y unattended-upgrades -q
    sudo DEBIAN_FRONTEND=noninteractive dpkg-reconfigure --priority=low unattended-upgrades

    if [[ "$UU_REBOOT_CHOICE" =~ ^[Yy]$ ]]; then
        sudo tee /etc/apt/apt.conf.d/52mempaper-reboot > /dev/null <<EOF
// Written by mempaper install.sh
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";
Unattended-Upgrade::Automatic-Reboot-Time "${UU_REBOOT_TIME}";
EOF
        ok "Auto-reboot enabled at ${UU_REBOOT_TIME} (skipped if SSH session active)"
    else
        ok "Auto-reboot disabled — reboot manually after updates if needed"
    fi

    ok "unattended-upgrades enabled"
else
    ok "Skipping unattended-upgrades"
fi

# ── Optional: disable SSH password authentication ─────────────────────────
if [[ "$SSH_HARDENING" =~ ^[Yy]$ ]]; then
    sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sudo systemctl reload sshd
    ok "SSH hardened: password auth disabled, root login disabled (key-only)"
    echo ""
    echo -e "  ${YELLOW}⚠  SSH password login is now disabled.${NC}"
    echo "  Add your SSH public key via Settings > SSH in the web UI."
    echo "  Until then, SSH access requires physical access to the Pi."
else
    ok "SSH hardening skipped — enable later via:"
    echo "    sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config"
    echo "    sudo systemctl reload sshd"
fi

# ── Done ──────────────────────────────────────────────────────────────────
NEEDS_REBOOT=false
if [ "$DISPLAY_CHOICE" != "8" ] && [ ! -e /dev/spidev0.0 ]; then
    NEEDS_REBOOT=true
fi

# Derive hotspot credentials from MAC address (same algorithm as mempaper_app.py)
WIFI_IFACE=$(ip -o link show | awk -F': ' '/wlan/{print $2; exit}')
if [ -n "$WIFI_IFACE" ]; then
    MAC=$(cat "/sys/class/net/$WIFI_IFACE/address" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$MAC" ]; then
        DIGEST=$(echo -n "$MAC" | sha256sum | awk '{print $1}')
        SUFFIX=$(printf "%04d" $(( 16#${DIGEST:0:8} % 10000 )))
        HOTSPOT_SSID="mempaper-$SUFFIX"
        HOTSPOT_PASS="${DIGEST:8:8}"
    fi
fi

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │     Setup complete — ready to start!  │"
echo "  └──────────────────────────────────────┘"
echo ""
if [ -n "$HOTSPOT_SSID" ]; then
    echo -e "  ${YELLOW}╔══════════════════════════════════════╗${NC}"
    echo -e "  ${YELLOW}║  SAVE THESE CREDENTIALS NOW!         ║${NC}"
    echo -e "  ${YELLOW}║  SSH will disconnect when the         ║${NC}"
    echo -e "  ${YELLOW}║  service starts hotspot mode.         ║${NC}"
    echo -e "  ${YELLOW}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}WiFi Hotspot Credentials:${NC}"
    echo -e "    SSID:     ${GREEN}$HOTSPOT_SSID${NC}"
    echo -e "    Password: ${GREEN}$HOTSPOT_PASS${NC}"
    echo -e "    Web UI:   ${GREEN}http://10.42.0.1:5000${NC}"
    echo ""
    echo "  After the service starts, connect to this"
    echo "  WiFi from your phone or laptop to set up."
    echo "  If the URL doesn't work, try the captive"
    echo "  portal popup or check the e-ink display."
else
    echo "  After the service starts it will enter"
    echo "  hotspot onboarding mode. Check the logs"
    echo "  for the SSID and password:"
    echo "    sudo journalctl -u mempaper.service | grep hotspot"
fi
echo ""
echo "  Useful commands (after connecting to hotspot):"
echo "    sudo journalctl -u mempaper.service -f   # live logs"
echo "    sudo systemctl restart mempaper.service   # restart"
echo "    sudo systemctl status mempaper.service    # status"
echo ""
echo "  To reconfigure the display later:"
echo "    python tools/configure_display.py"
echo ""
echo "  To prepare for delivery (factory reset):"
echo "    python tools/delivery_state.py"
echo ""

# ── Step 9: Start service (last — drops SSH when hotspot activates) ───────
step "Step 9/9 — Starting mempaper service"
if [ "$NEEDS_REBOOT" = true ]; then
    echo ""
    echo -e "  ${YELLOW}SPI not yet active — a reboot is required to start the display.${NC}"
    echo "  After reboot the Pi enters hotspot mode and your SSH session ends."
    echo ""
    echo "  Rebooting in 5 seconds (Ctrl+C to cancel)..."
    sleep 5
    sudo reboot
else
    echo ""
    echo -e "  ${YELLOW}Starting the service will activate hotspot mode."
    echo -e "  Your SSH session may disconnect.${NC}"
    echo ""
    sudo systemctl restart mempaper.service
    ok "mempaper service started"
fi

_T1=$(date +%s)
_ELAPSED=$(( _T1 - _T0 ))
_MIN=$(( _ELAPSED / 60 ))
_SEC=$(( _ELAPSED % 60 ))
echo ""
echo -e "  ${GREEN}Total install time: ${_MIN}m ${_SEC}s${NC}"
