#!/usr/bin/env bash
# ============================================================================
# mempaper one-click installer
# ============================================================================
# Sets up a fresh Raspberry Pi (Raspbian OS 32-bit) as a mempaper device.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
SERVICE_USER="$(whoami)"
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

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │     mempaper installer                │"
echo "  │     Bitcoin Meme Block Clock          │"
echo "  └──────────────────────────────────────┘"
echo ""
echo "  User:    $SERVICE_USER"
echo "  Path:    $SCRIPT_DIR"
echo ""

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
    python3 -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
else
    ok "Virtual environment already exists"
fi

source "$VENV_DIR/bin/activate"

pip install --upgrade pip setuptools wheel -q
ok "pip/setuptools upgraded"

# ── Step 3: Python dependencies ────────────────────────────────────────────
step "Step 3/9 — Installing Python dependencies"

if [ -f requirements.txt ]; then
    pip install -r requirements.txt
    ok "Python packages installed"
else
    fail "requirements.txt not found"
fi

# Raspberry Pi specific packages (GPIO/SPI)
pip install spidev gpiozero lgpio 2>/dev/null && ok "GPIO/SPI libraries installed" \
    || warn "GPIO/SPI libraries not available (OK if not running on a Pi)"

# Pillow source rebuild for Pi Zero 1 WH (armv6l)
ARCH=$(uname -m)
if [ "$ARCH" = "armv6l" ]; then
    step "Rebuilding Pillow from source (Pi Zero 1 WH — this takes a few minutes)"
    pip install --force-reinstall --no-cache-dir --no-binary :all: Pillow
    ok "Pillow rebuilt from source"
fi

# ── Optional: Minify JavaScript ───────────────────────────────────────────
echo ""
echo -e "  ${CYAN}Minify JavaScript for better performance?${NC}"
echo "  Strips comments & whitespace from JS files into static/js/dist/"
echo "  The app serves minified files when they exist, originals otherwise."
echo ""
read -rp "  Minify JavaScript? [Y/n]: " MINIFY_CHOICE
MINIFY_CHOICE="${MINIFY_CHOICE:-Y}"
if [[ "$MINIFY_CHOICE" =~ ^[Yy]$ ]]; then
    "$VENV_DIR/bin/python" tools/minify.py
    ok "JavaScript minified — served from static/js/dist/"
else
    ok "Skipping JS minification (app will use unminified source files)"
fi

# ── Step 4: Configuration ─────────────────────────────────────────────────
step "Step 4/9 — Setting up configuration"

mkdir -p config cache

if [ ! -f config/config.json ]; then
    if [ -f config/config.json.example ]; then
        cp config/config.json.example config/config.json
        ok "Config created from example"
    else
        warn "No config.json.example found — service will create defaults on first start"
    fi
else
    ok "config.json already exists"
fi

# ── Step 5: E-Ink display configuration ───────────────────────────────────
step "Step 5/9 — Configuring e-ink display"

echo ""
echo "  Which e-ink display is connected to your Pi?"
echo ""
echo -e "  ${CYAN}1${NC}. Waveshare 13.3\" 6-color (Spectra 6)  ${GREEN}[recommended]${NC}"
echo -e "  ${CYAN}2${NC}. Waveshare 7.3\" 7-color"
echo -e "  ${CYAN}3${NC}. Waveshare 5.83\" V2 (via omni-epd)"
echo -e "  ${CYAN}4${NC}. Waveshare 4.2\" (via omni-epd)"
echo -e "  ${CYAN}5${NC}. Waveshare 2.7\" (via omni-epd)"
echo -e "  ${CYAN}6${NC}. Inky Impression 7-color"
echo -e "  ${CYAN}7${NC}. Inky Auto-detect"
echo -e "  ${CYAN}8${NC}. Mock Display (testing, no hardware)"
echo -e "  ${CYAN}s${NC}. Skip — configure later via web UI"
echo ""

DISPLAY_CHOICE=""
while true; do
    read -rp "  Select display [1-8, s]: " DISPLAY_CHOICE
    case "$DISPLAY_CHOICE" in
        [1-8]|s|S) break ;;
        *) echo "  Invalid choice. Enter 1-8 or s to skip." ;;
    esac
done

if [ "$DISPLAY_CHOICE" != "s" ] && [ "$DISPLAY_CHOICE" != "S" ]; then
    echo ""
    "$VENV_DIR/bin/python" tools/configure_display.py "$DISPLAY_CHOICE"
    ok "Display configured"

    # Enable SPI interface (required for e-ink displays)
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
else
    warn "Display configuration skipped — configure later in Settings > Display"
fi

# ── Step 6: Systemd service ───────────────────────────────────────────────
step "Step 6/9 — Installing systemd service"

python tools/generate_service_file.py
sudo cp mempaper.service /etc/systemd/system/mempaper.service
sudo systemctl daemon-reload
sudo systemctl enable mempaper.service
ok "mempaper.service installed and enabled"

# ── Step 7: WiFi/hotspot permissions ───────────────────────────────────────
step "Step 7/9 — Installing WiFi hotspot permissions"

sudo bash tools/install_wifi_permissions.sh "$SERVICE_USER"
ok "WiFi permissions installed"

# ── Done ──────────────────────────────────────────────────────────────────
NEEDS_REBOOT=false
if [ "$DISPLAY_CHOICE" != "s" ] && [ "$DISPLAY_CHOICE" != "S" ] && [ "$DISPLAY_CHOICE" != "8" ]; then
    if [ ! -e /dev/spidev0.0 ]; then
        NEEDS_REBOOT=true
    fi
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
echo "  │     Installation complete!            │"
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
        # Restart NM to pick up the new config; ignore errors (service may
        # restart itself later, and the setting takes effect on next connect).
        sudo systemctl restart NetworkManager 2>/dev/null || true
        ok "WiFi power management disabled (prevents BCM43430 beacon misses)"
    else
        ok "WiFi power management already disabled"
    fi
else
    warn "NetworkManager conf.d not found — skipping powersave configuration"
fi

# ── Step 9: Start service (last — drops SSH when hotspot activates) ───────
if [ "$NEEDS_REBOOT" = true ]; then
    echo -e "  ${YELLOW}A reboot is required to activate the SPI interface"
    echo -e "  and start the mempaper service.${NC}"
    echo ""
    echo "  After reboot, the Pi enters hotspot mode."
    echo -e "  ${YELLOW}Your SSH session will end.${NC}"
    echo ""
    read -rp "  Reboot now? [Y/n]: " REBOOT_CHOICE
    case "$REBOOT_CHOICE" in
        n|N)
            echo "  Reboot skipped — run 'sudo reboot' when ready."
            echo "  The service will not start until after reboot."
            ;;
        *)
            echo "  Rebooting..."
            sudo reboot
            ;;
    esac
else
    step "Step 9/9 — Starting mempaper service"
    echo ""
    echo -e "  ${YELLOW}Starting the service will activate hotspot mode"
    echo -e "  and your SSH session will disconnect.${NC}"
    echo ""
    read -rp "  Start service now? [Y/n]: " START_CHOICE
    case "$START_CHOICE" in
        n|N)
            echo ""
            echo "  Service not started. Start it manually with:"
            echo "    sudo systemctl start mempaper.service"
            ;;
        *)
            echo ""
            ok "Starting mempaper service..."
            sudo systemctl start mempaper.service
            ;;
    esac
fi
