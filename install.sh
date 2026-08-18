#!/usr/bin/env bash
# ============================================================================
# mempaper one-click installer
# ============================================================================
# Sets up a fresh Raspberry Pi (Raspberry Pi OS Lite 32-bit, Trixie / Debian 13) as a mempaper device.
#
# Bookworm (Debian 12) is not supported or tested. It still installs: the pins in
# apt-requirements.txt are scoped to the suite named in that file, and Step 1
# drops them on any other one rather than failing to resolve them. What you lose
# is the tested combination — see the Installation note in README.md.
#
# Usage:
#   sudo apt install -y git
#   git clone https://github.com/satcat21/btc-mempaper.git
#   cd btc-mempaper && bash install.sh
#
# What it does:
#   1. Installs system packages (apt-requirements.txt)
#   2. Creates Python virtual environment and installs pip packages
#   3. Installs Raspberry Pi GPIO/SPI libraries + rebuilds Pillow (Pi Zero 1 WH)
#   4. Copies example config and applies the chosen mempool source
#   5. Configures e-ink display (interactive selection + driver download)
#   6. Generates and installs systemd service file
#   7. Installs WiFi/hotspot permissions (polkit + sudoers)
#   8. Disables WiFi power management (prevents BCM43430 beacon misses)
#   9. Enables and starts the mempaper service
#
# After install the mempaper service starts and the web UI is available at
# http://<pi-ip>:5000 on your local network.
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
# Check whether admin users already exist.
#
# admin_users is a sensitive field, so save_secure_config writes it to the
# encrypted config/config.sensitive.json and deliberately keeps it out of
# config/config.json. Inspecting the plain file therefore never finds it, and
# this prompt reappeared on every re-run of an already-installed device even
# though the credentials were then discarded.
#
# Ask the application instead, which can decrypt. On a genuine first install
# there is no venv yet - and no users either - so the plain-file check below
# still covers that, along with builds that run without secure config.
_HAS_USERS=false
if [ -x ".venv/bin/python" ] && [ -f "tools/setup_user.py" ]; then
    if .venv/bin/python tools/setup_user.py --list 2>/dev/null | grep -q "user(s) configured"; then
        _HAS_USERS=true
    fi
fi
if [ "$_HAS_USERS" = "false" ] && [ -f "config/config.json" ]; then
    _HAS_USERS=$(python3 -c "
import json, sys
try:
    c = json.load(open('config/config.json'))
    print('true' if c.get('admin_users') or c.get('admin_password_hash') else 'false')
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

# [3] Mempool source
# One question rather than separate host/Tor toggles, because the two are not
# independent: Tor cannot route private addresses, so "own node on the LAN" plus
# Tor is a combination that fails outright. Choosing here writes a coherent set.
echo -e "  ${CYAN}Mempool source${NC}"
echo "  Where mempaper reads blocks, fees, hashrate and prices from."
echo ""
echo -e "    ${CYAN}1${NC}. mempool.space over Tor   ${GREEN}[recommended]${NC} — mempool.space sees your IP"
echo -e "    ${CYAN}2${NC}. mempool.space directly   — slightly faster, your IP is visible to it"
echo -e "    ${CYAN}3${NC}. My own node on the LAN   — nothing leaves your network"
echo ""
MEMPOOL_SOURCE=""
MEMPOOL_LAN_HOST=""
MEMPOOL_LAN_REST=""
MEMPOOL_LAN_WS=""
while true; do
    read -rp "  Select mempool source [1-3, default 1]: " MEMPOOL_SOURCE
    MEMPOOL_SOURCE="${MEMPOOL_SOURCE:-1}"
    case "$MEMPOOL_SOURCE" in
        1|2) break ;;
        3)
            _paste_had_https=""
            while true; do
                read -rp "    Node host, IP or domain:      " MEMPOOL_LAN_HOST
                # Remember a pasted https:// before stripping it — it is a good
                # signal for the scheme default below.
                case "$MEMPOOL_LAN_HOST" in https://*) _paste_had_https="y" ;; esac
                # The app stores a bare host, so drop any scheme and path.
                MEMPOOL_LAN_HOST=$(echo "$MEMPOOL_LAN_HOST" | sed -E 's#^[a-zA-Z]+://##; s#/.*$##' | tr -d '[:space:]')
                [ -n "$MEMPOOL_LAN_HOST" ] && break
                echo "    Host cannot be empty."
            done

            # A bare LAN IP is almost always plain http on mempool's own ports;
            # a domain name usually means a reverse proxy terminating TLS.
            if [ -n "$_paste_had_https" ]; then
                _https_default="Y"
            elif echo "$MEMPOOL_LAN_HOST" | grep -qE '^[0-9]+(\.[0-9]+){3}$'; then
                _https_default="N"
            else
                _https_default="Y"
            fi
            if [ "$_https_default" = "Y" ]; then
                read -rp "    Reached over HTTPS?     [Y/n]: " MEMPOOL_LAN_HTTPS
                MEMPOOL_LAN_HTTPS="${MEMPOOL_LAN_HTTPS:-Y}"
            else
                read -rp "    Reached over HTTPS?     [y/N]: " MEMPOOL_LAN_HTTPS
                MEMPOOL_LAN_HTTPS="${MEMPOOL_LAN_HTTPS:-N}"
            fi

            # Behind a TLS proxy everything arrives on 443; a direct mempool
            # instance splits REST and WebSocket across its own two ports.
            if [[ "$MEMPOOL_LAN_HTTPS" =~ ^[Yy]$ ]]; then
                _rest_default=443; _ws_default=443
            else
                _rest_default=4081; _ws_default=8999
            fi
            while true; do
                read -rp "    REST API port:        [${_rest_default}]: " MEMPOOL_LAN_REST
                MEMPOOL_LAN_REST="${MEMPOOL_LAN_REST:-$_rest_default}"
                echo "$MEMPOOL_LAN_REST" | grep -qE '^[0-9]{1,5}$' && [ "$MEMPOOL_LAN_REST" -le 65535 ] && break
                echo "    Not a valid port."
            done
            while true; do
                read -rp "    WebSocket port:       [${_ws_default}]: " MEMPOOL_LAN_WS
                MEMPOOL_LAN_WS="${MEMPOOL_LAN_WS:-$_ws_default}"
                echo "$MEMPOOL_LAN_WS" | grep -qE '^[0-9]{1,5}$' && [ "$MEMPOOL_LAN_WS" -le 65535 ] && break
                echo "    Not a valid port."
            done
            break ;;
        *) echo "  Invalid choice. Enter 1, 2 or 3." ;;
    esac
done
echo ""

# [4] Options — press Enter to accept defaults
echo -e "  ${CYAN}Options${NC} — press Enter to accept defaults"
echo ""
read -rp "  Minify JavaScript (better performance)?   [Y/n]: " MINIFY_CHOICE
MINIFY_CHOICE="${MINIFY_CHOICE:-Y}"
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
echo -e "  ${CYAN}Persistent logging${NC}"
echo "  Raspberry Pi OS keeps journal logs in RAM only (lost on every reboot),"
echo "  to reduce SD card wear. Enabling this writes logs to the SD card"
echo "  instead (capped at 200M) so 'journalctl -b -1' works after a reboot —"
echo "  useful for debugging, at the cost of a little extra SD card wear."
echo ""
read -rp "  Enable persistent logging?                 [y/N]: " PERSISTENT_LOG_CHOICE
PERSISTENT_LOG_CHOICE="${PERSISTENT_LOG_CHOICE:-N}"
echo ""
echo -e "  ${CYAN}WiFi regulatory domain${NC}"
echo "  Unlocks WiFi channels/transmit power and lifts the software rfkill"
echo "  block that otherwise keeps the radio disabled until a country is set —"
echo "  required for both normal WiFi and the setup hotspot to come up reliably."
echo ""
read -rp "  WiFi country code (ISO 3166-1 alpha-2)?    [DE]: " WIFI_COUNTRY
WIFI_COUNTRY="${WIFI_COUNTRY:-DE}"
WIFI_COUNTRY=$(echo "$WIFI_COUNTRY" | tr '[:lower:]' '[:upper:]')
if ! echo "$WIFI_COUNTRY" | grep -qE '^[A-Z]{2}$'; then
    warn "Invalid country code '${WIFI_COUNTRY}' — using DE"
    WIFI_COUNTRY="DE"
fi
echo ""
echo -e "  ${CYAN}Network-bound encryption (Tang)${NC} — optional, protects a stolen device"
echo "  Wallet addresses, balance caches and the rendered images are otherwise"
echo "  readable by anyone holding the SD card: the key is derived from the Pi"
echo "  itself. A Tang server on your LAN keeps that key off the device, so a"
echo "  device carried off your network cannot decrypt them at all."
echo ""
echo "  The clevis client is installed either way, so you can turn this on later"
echo "  from Settings > General > Advanced without touching the command line."
echo "  Skip this unless you already run a Tang server — see docs/SELF_HOSTING_GUIDE.md."
echo ""
read -rp "  Connect to a Tang server now?              [y/N]: " TANG_CHOICE
TANG_CHOICE="${TANG_CHOICE:-N}"
TANG_URL=""
TANG_THUMBPRINT=""
if echo "$TANG_CHOICE" | grep -qi '^y'; then
    read -rp "    Tang server URL (http://host:7500):      " TANG_URL
    TANG_URL="${TANG_URL%/}"
    if [ -z "$TANG_URL" ]; then
        warn "No URL given — skipping Tang setup, configure it later in the web UI"
    else
        read -rp "    Signing-key thumbprint (blank to fetch):  " TANG_THUMBPRINT
    fi
fi
echo ""
echo -e "  ${CYAN}SSH hardening${NC} — disable password login, require SSH key"
echo "  Add your public key via Settings > General > Advanced > SSH Access after install."
echo "  Without a key, physical access is needed to SSH in."
echo ""
read -rp "  Disable SSH password authentication?       [Y/n]: " SSH_HARDENING
SSH_HARDENING="${SSH_HARDENING:-Y}"
echo ""

echo -e "  ${YELLOW}━━━ All set — starting installation now ━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── System update ─────────────────────────────────────────────────────────
# Run before any other step so installed packages are current.
step "System update"
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -q
sudo apt-get install -y locales-all -q
ok "System updated"

# ── Persistent logging ─────────────────────────────────────────────────────
# Raspberry Pi OS ships /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf
# (Storage=volatile) to reduce SD card wear, so journalctl logs vanish on every
# reboot by default. Override it with our own /etc/ drop-in (later-sorting
# filenames win for duplicate systemd conf.d keys, unlike sshd's Include=
# first-wins behavior) so 'journalctl -u mempaper.service -b -1' etc. work for
# debugging a previous boot. Capped to avoid unbounded SD card growth.
step "Persistent logging"
if [[ "$PERSISTENT_LOG_CHOICE" =~ ^[Yy]$ ]]; then
    sudo mkdir -p /var/log/journal
    sudo systemd-tmpfiles --create --prefix /var/log/journal
    sudo mkdir -p /etc/systemd/journald.conf.d
    sudo tee /etc/systemd/journald.conf.d/persistent.conf > /dev/null << 'EOF'
[Journal]
Storage=persistent
SystemMaxUse=200M
EOF
    sudo systemctl restart systemd-journald
    ok "Persistent logging enabled (capped at 200M, survives reboots)"
else
    ok "Persistent logging skipped (default — logs stay RAM-only, reset on reboot)"
fi

# ── Netplan permissions ──────────────────────────────────────────────────
step "Netplan permissions"
sudo mkdir -p /etc/tmpfiles.d
sudo tee /etc/tmpfiles.d/mempaper-netplan-perms.conf > /dev/null << 'EOF'
z /lib/netplan/00-network-manager-all.yaml 0600 root root - -
EOF
sudo systemd-tmpfiles --create /etc/tmpfiles.d/mempaper-netplan-perms.conf
ok "Netplan config permissions fixed"

# ── Cloud-init network reconfiguration ─────────────────────────────────
step "Cloud-init network reconfiguration"
sudo mkdir -p /etc/cloud/cloud.cfg.d
sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg > /dev/null << 'EOF'
network: {config: disabled}
EOF
ok "Cloud-init per-boot network reconfiguration disabled"

# NetworkManager calls "netplan generate" internally on startup; if the
# render differs from disk it triggers a systemd daemon-reload, which can
# cascade into further reloads and delay NM's own readiness. Rendering here,
# ordered before NetworkManager.service, keeps NM's internal render a no-op.
step "Netplan pre-generate (avoids NetworkManager startup reload storm)"
sudo tee /etc/systemd/system/mempaper-netplan-pregenerate.service > /dev/null << 'EOF'
[Unit]
Description=Pre-render netplan config before NetworkManager starts
DefaultDependencies=no
After=systemd-udevd.service local-fs.target
Before=NetworkManager.service
Wants=systemd-udevd.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/netplan generate
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable mempaper-netplan-pregenerate.service
ok "Netplan pre-generate service installed"

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

# ── Checkout latest release tag ───────────────────────────────────────────
# The repo is cloned from main (to get the latest install.sh), but the installed
# version should be the latest tagged release so the update-available banner
# does not appear immediately after a fresh install.
_LATEST_TAG=$(sudo -u "$SERVICE_USER" git -C "$SCRIPT_DIR" \
    describe --tags --abbrev=0 2>/dev/null || true)
if [ -n "$_LATEST_TAG" ]; then
    sudo -u "$SERVICE_USER" git -C "$SCRIPT_DIR" checkout "$_LATEST_TAG" --quiet 2>/dev/null \
        && ok "Checked out latest release: $_LATEST_TAG" \
        || warn "Could not check out tag '$_LATEST_TAG' — continuing from current branch"
else
    warn "No release tags found — continuing from current branch"
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

if [ -f apt-requirements.txt ]; then
    # Pins are scoped to the suite named by '# pins-for: <codename>' in the file.
    # Those version strings only exist in that suite's archive, and apt matches a
    # pinned version exactly, so on any other release every spec below fails to
    # locate a candidate and takes the whole batch down with it. Strip the
    # versions there and install the same packages floating.
    #
    # The pins stand when the file names no suite, or when the codename cannot be
    # read. An empty sed expression is a valid no-op, which is what keeps the two
    # cases a single pipeline.
    PINS_TARGET=$(sed -n 's/^[[:space:]]*#[[:space:]]*[Pp]ins-for:[[:space:]]*\([A-Za-z0-9_.-][A-Za-z0-9_.-]*\).*/\1/p' \
        apt-requirements.txt | head -n1 | tr '[:upper:]' '[:lower:]')
    OS_CODENAME=$( . /etc/os-release 2>/dev/null && printf '%s' "${VERSION_CODENAME:-}" | tr '[:upper:]' '[:lower:]' )
    STRIP_PINS=''
    if [ -n "$PINS_TARGET" ] && [ -n "$OS_CODENAME" ] && [ "$PINS_TARGET" != "$OS_CODENAME" ]; then
        STRIP_PINS='s/=.*//'
        warn "apt-requirements.txt pins versions for ${PINS_TARGET}, but this is ${OS_CODENAME}."
        warn "Installing those packages unpinned — see the Installation note in README.md."
    fi

    # Comments (whole-line and trailing), blanks and CR stripped. What survives
    # is either 'name' or 'name=version', both of which apt-get install takes
    # verbatim — the pin is applied here and held later, once Step 7 has
    # installed the wrapper that manages holds.
    APT_PKGS=$(sed -e 's/#.*//' -e 's/\r//g' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
        -e "$STRIP_PINS" apt-requirements.txt | grep -v '^$' | tr '\n' ' ')
    sudo apt-get install -y $APT_PKGS
    ok "System packages installed"
else
    warn "apt-requirements.txt not found — skipping"
fi

# Mask system dnsmasq so it never holds port 53/67.
# NM's shared-mode dnsmasq starts its own dnsmasq process for DHCP; if the system
# dnsmasq service is running it grabs port 53 on all interfaces and prevents NM's
# instance from starting.  Mask survives future apt-get reinstalls.
sudo systemctl stop dnsmasq    2>/dev/null || true
sudo systemctl disable dnsmasq 2>/dev/null || true
sudo systemctl mask dnsmasq    2>/dev/null || true
ok "System dnsmasq masked (NM starts its own dnsmasq for shared-mode DHCP)"

# Disable and flush nftables so its inet-filter DROP policy never blocks DHCP.
# Trixie ships /etc/nftables.conf with 'inet filter input { policy drop }' which
# silently drops DHCP DISCOVER broadcasts (UDP 67) from hotspot clients even after
# the service is disabled (the ruleset loaded at boot stays in memory until flushed).
sudo systemctl stop nftables    2>/dev/null || true
sudo systemctl disable nftables 2>/dev/null || true
sudo nft flush ruleset          2>/dev/null || true
ok "nftables service disabled and ruleset flushed (prevents DHCP drop on Trixie)"

# Disable UFW if active.  UFW's ufw-after-input chain unconditionally drops
# UDP dport 67 (DHCP broadcasts) before any user allow-rules can accept them,
# so the setup hotspot's DHCP server can never reply to clients while UFW runs.
# mempaper manages its own iptables rules for the hotspot; UFW is redundant here.
if command -v ufw >/dev/null 2>&1; then
    sudo ufw disable 2>/dev/null || true
    ok "UFW disabled (its ufw-after-input chain drops UDP/67 DHCP broadcasts)"
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

# pip is pinned in requirements.txt so every device resolves wheels the same
# way; install that exact version here too, otherwise a fresh install starts on
# whatever pip is newest today and immediately diverges from the pin.
_PIP_PIN=$(grep -oE '^pip==[0-9][0-9.]*' requirements.txt | head -1)
if [ -n "$_PIP_PIN" ]; then
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade "$_PIP_PIN" setuptools wheel -q
    ok "pip pinned to ${_PIP_PIN#pip==}, setuptools/wheel upgraded"
else
    # No pin found (requirements.txt edited?) — fall back rather than fail the install.
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel -q
    warn "No pip pin found in requirements.txt — upgraded to latest instead"
fi

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

# ── Mempool source ────────────────────────────────────────────────────────────
# Writes host, scheme, ports, Tor and the private flag as one coherent set, so
# the combinations that silently fail cannot be produced by hand (Tor refuses to
# route private addresses, so LAN host + Tor breaks mempool access entirely).
# Only applied while the host is still the shipped default, so re-running
# install.sh never redirects an instance already pointed somewhere else.
# Values travel via env rather than string interpolation so a host containing
# shell metacharacters cannot break out of the heredoc.
if [ -f config/config.json ]; then
    sudo -u "$SERVICE_USER" env \
        MP_SOURCE="$MEMPOOL_SOURCE" \
        MP_HOST="$MEMPOOL_LAN_HOST" \
        MP_REST="$MEMPOOL_LAN_REST" \
        MP_WS="$MEMPOOL_LAN_WS" \
        MP_HTTPS="$MEMPOOL_LAN_HTTPS" \
        python3 - <<'PYEOF' && ok "Mempool source configured (change any time in Settings)" || warn "Could not set mempool source (non-fatal)"
import json, os, sys
from pathlib import Path

sys.path.insert(0, ".")
p = Path("config/config.json")
try:
    cfg = json.loads(p.read_text())
except Exception as e:
    print(f"   could not read config.json: {e}")
    sys.exit(1)

host = str(cfg.get("mempool_host", "")).strip()
if host and host != "mempool.space":
    print(f"   mempool_host already set to '{host}' — leaving it alone")
    sys.exit(0)

source = os.environ.get("MP_SOURCE", "1")

if source == "1":
    try:
        # single source of truth — also carries the scheme/port the service
        # expects, so a changed onion address ships with a software update
        from utils.technical_config import MEMPOOL_ONION_PRESETS
        preset = MEMPOOL_ONION_PRESETS[0]
    except Exception as e:
        print(f"   could not read onion preset: {e}")
        sys.exit(1)
    cfg.update({
        "mempool_use_tor":    True,
        "mempool_host":       preset["host"],
        "mempool_use_https":  preset["use_https"],   # the circuit already encrypts
        "mempool_rest_port":  preset["port"],
        "mempool_ws_port":    preset["port"],
        "mempool_is_private": False,
    })
    summary = f"{preset['label']} via Tor on port {preset['port']}"

elif source == "2":
    cfg.update({
        "mempool_use_tor":    False,
        "mempool_host":       "mempool.space",
        "mempool_use_https":  True,
        "mempool_rest_port":  443,
        "mempool_ws_port":    443,
        "mempool_is_private": False,
    })
    summary = "mempool.space directly over HTTPS — the instance sees your IP"

else:
    # Own node, either a bare LAN address or a domain behind a TLS proxy.
    # Tor stays off deliberately: it cannot reach a private address, so
    # enabling it here would break every request — and for a public domain it
    # would add a circuit to reach a host you already control. is_private
    # suppresses the public-instance privacy warnings on wallet monitoring,
    # which do not apply when you run the instance yourself.
    _https = os.environ.get("MP_HTTPS", "").lower() in ("y", "yes", "true", "1")
    cfg.update({
        "mempool_use_tor":    False,
        "mempool_host":       os.environ["MP_HOST"],
        "mempool_use_https":  _https,
        "mempool_rest_port":  int(os.environ["MP_REST"]),
        "mempool_ws_port":    int(os.environ["MP_WS"]),
        "mempool_is_private": True,
    })
    summary = (f"self-hosted mempool at {'https' if _https else 'http'}://"
               f"{cfg['mempool_host']}:{cfg['mempool_rest_port']} (Tor off)")

tmp = p.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cfg, indent=2))
tmp.replace(p)
print(f"   {summary}")
PYEOF
fi

# ── Randomise the weekly meme-sync schedule ───────────────────────────────────
# Every install otherwise inherits the same default (Thu 13:00), so every
# mempaper in the world would hit einundzwanzig-memes.space in the same hour.
# Picking a per-device day and hour at install time spreads that load out.
# Only ever set on a device that has not chosen a schedule yet, so re-running
# install.sh never overwrites what a user picked in the web UI.
if [ -f config/config.json ]; then
    sudo -u "$SERVICE_USER" python3 - <<'PYEOF' && ok "Meme-sync schedule randomised for this device" || warn "Could not set meme-sync schedule (non-fatal)"
import json, random, sys
from pathlib import Path

p = Path("config/config.json")
try:
    cfg = json.loads(p.read_text())
except Exception as e:
    print(f"   could not read config.json: {e}")
    sys.exit(1)

# Treat the shipped default (Thu 13:00) as "never chosen".
already = cfg.get("meme_sync_schedule_randomised", False)
names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

if already and "meme_sync_minute" in cfg:
    print("   schedule already randomised — leaving it alone")
    sys.exit(0)

if already:
    # Upgrade path: this device picked a day and hour before the minute was
    # spread too, so it currently fires on the stroke of the hour along with
    # every other device that drew the same hour. Give it a minute without
    # touching the day and hour the user may since have chosen themselves.
    day  = int(cfg.get("meme_sync_day", 4))
    hour = int(cfg.get("meme_sync_hour", 13))
else:
    day  = random.randint(0, 6)    # cron: 0=Sun … 6=Sat
    hour = random.randint(0, 23)
    cfg["meme_sync_day"] = str(day)
    cfg["meme_sync_hour"] = str(hour)
    cfg["meme_sync_schedule_randomised"] = True

minute = random.randint(0, 59)
cfg["meme_sync_minute"] = str(minute)

tmp = p.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cfg, indent=2))
tmp.replace(p)
print(f"   weekly meme sync scheduled for {names[day]} at {hour:02d}:{minute:02d}")
PYEOF
fi

# ── Write the meme-sync crontab entry ─────────────────────────────────────────
# Written here so the schedule exists on the device from the moment it is
# installed, rather than only once the service has started with the toggle on.
# `crontab -l` is where anyone looks to answer "is this scheduled?", so an
# entry that appears later reads as the feature not existing.
#
# The block is written commented out while the feature is off, so the randomised
# schedule is visible where anyone would look for it. The web UI toggle rewrites
# it live through the same code, so there is no need to uncomment it by hand.
if [ -f config/config.json ]; then
    sudo -u "$SERVICE_USER" python3 -m utils.meme_sync_cron --apply \
        && ok "Meme-sync crontab entry written" \
        || warn "Could not write the meme-sync crontab entry (non-fatal)"
fi

# ── Network-bound encryption (Tang) ───────────────────────────────────────────
# Only reached when a URL was given upfront. Everything is verified before it is
# written: a config pointing at a Tang server that cannot actually unseal would
# leave the device booting into degraded mode with no obvious cause.
if [ -n "$TANG_URL" ]; then
    step "Configuring network-bound encryption (Tang)"

    if ! command -v clevis >/dev/null 2>&1; then
        warn "clevis is not installed — skipping. Enable Tang later from the web UI"
    elif ! curl -sSf --max-time 10 "${TANG_URL}/adv" -o /tmp/tang_adv.json 2>/dev/null; then
        warn "No advertisement from ${TANG_URL} — is it running and reachable?"
        warn "Skipping. Configure it later in Settings > General > Advanced"
    else
        # Pin the signing key, which is the one clevis compares against. The
        # exchange key has a different thumbprint and would always fail.
        if [ -z "$TANG_THUMBPRINT" ]; then
            TANG_THUMBPRINT=$(jose fmt --json /tmp/tang_adv.json -g payload -y -o- 2>/dev/null \
                | jose jwk use -i- -r -u verify -o- 2>/dev/null \
                | jose jwk thp -i- 2>/dev/null || true)
            [ -n "$TANG_THUMBPRINT" ] && echo "   fetched thumbprint: ${TANG_THUMBPRINT}"
        fi

        if [ -z "$TANG_THUMBPRINT" ]; then
            warn "Could not determine the thumbprint — skipping Tang setup"
        elif ! echo mempaper-tang-check \
                | clevis encrypt tang "{\"url\":\"${TANG_URL}\",\"thp\":\"${TANG_THUMBPRINT}\"}" \
                  > /tmp/tang_test.jwe 2>/dev/null; then
            warn "Sealing failed — thumbprint may not match this server. Skipping"
        elif [ "$(clevis decrypt < /tmp/tang_test.jwe 2>/dev/null)" != "mempaper-tang-check" ]; then
            warn "Unsealing failed — Tang answered but could not recover the key. Skipping"
        else
            # Provision the data key here, in the same step that proved the
            # server answers. Writing tang_enabled without a key would leave the
            # admin account step below unable to store anything: the sealed store
            # refuses a sensitive write it cannot seal rather than putting the
            # password hash on disk in clear text. Provisioning now is also what
            # makes that hash sealed from its very first write, with no window
            # where it exists unsealed on the card.
            # Needs the venv python — this imports cryptography, unlike the
            # stdlib-only config edit it used to be.
            sudo -u "$SERVICE_USER" env \
                MP_TANG_URL="$TANG_URL" MP_TANG_THP="$TANG_THUMBPRINT" \
                "$VENV_DIR/bin/python" - <<'PYEOF' && ok "Tang configured — credentials and wallet data sealed to ${TANG_URL}" || warn "Could not configure Tang (non-fatal) — enable it later in the web UI"
import json, os, sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

p = Path("config/config.json")
try:
    cfg = json.loads(p.read_text())
except Exception as e:
    print(f"   could not read config.json: {e}")
    sys.exit(1)

original = dict(cfg)


def write(obj):
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(p)


cfg["tang_enabled"] = True
cfg["tang_url"] = os.environ["MP_TANG_URL"]
cfg["tang_thumbprint"] = os.environ["MP_TANG_THP"]
write(cfg)

# enable() provisions the key and seals whatever already exists. On a fresh
# install that is usually nothing; on a re-run it converts the files in place.
try:
    from managers.tang_store import get_shared_store
    outcome = get_shared_store().enable()
except Exception as e:
    # Nothing was provisioned - enable() only raises before it starts sealing,
    # and per-file errors are collected rather than thrown. Putting the original
    # settings back leaves an unsealed but working install instead of one that
    # claims to be sealed and cannot write.
    write(original)
    print(f"   could not provision the sealed key: {e}")
    sys.exit(1)

for failure in outcome["failed"]:
    print(f"   warning: could not seal {failure['label']}: {failure['error']}")

print(f"   sealed key provisioned"
      + (f"; {len(outcome['sealed'])} existing file(s) sealed" if outcome["sealed"] else ""))
PYEOF
        fi
        rm -f /tmp/tang_adv.json /tmp/tang_test.jwe
    fi
fi

# Secure config directory and file (contains password hashes and API keys).
# Group-readable (750/640) so the mempaper group (pi user) can read the config
# for tools like the 'mempaper' CLI command, without exposing it to other users.
sudo chmod 750 config/
[ -f config/config.json ] && sudo chmod 640 config/config.json
ok "Config permissions secured (dir 750, file 640 — readable by mempaper group)"

# ── Admin account (non-interactive, credentials collected upfront) ────────────
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
    _admin_rc=0
    printf '%s\n%s\n' "$ADMIN_USERNAME" "$ADMIN_PASSWORD" | \
        sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" tools/setup_user.py --stdin \
        || _admin_rc=$?
    if   [ "$_admin_rc" -eq 0 ]; then ok "Admin account created"
    elif [ "$_admin_rc" -eq 2 ]; then ok "Admin account already exists — skipping"
    else err "Failed to create admin account (exit $_admin_rc)"; exit 1
    fi
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

# Keep tor's bootstrap from competing with mempaper's startup on a single core.
#
# Priority only, deliberately no After=mempaper.service. Ordering was tried and
# is wrong: with mempool traffic over Tor, mempaper cannot fetch anything until
# tor is up, so starting tor last bought a failed first request and a 20 s
# connect timeout on every boot. Worse, the transport is switchable in the web
# UI while this file is only ever written at install time — so a device set up
# on clearnet and later moved to Tor would have been stuck with the bad
# ordering and no way to correct it.
#
# Nice gives mempaper the CPU it needs during startup without creating that
# dependency inversion, and is correct either way.
if systemctl list-unit-files 'tor@*.service' >/dev/null 2>&1 && command -v tor >/dev/null 2>&1; then
    sudo mkdir -p /etc/systemd/system/tor@default.service.d
    sudo tee /etc/systemd/system/tor@default.service.d/defer-startup.conf > /dev/null << 'EOF'
[Service]
# Written by mempaper install.sh. Priority only — see install.sh for why there
# is deliberately no After= ordering here, and why this value is mild.
# IOSchedulingClass is deliberately not set: circuit crypto is CPU-bound.
Nice=5
EOF
    sudo systemctl daemon-reload
    ok "tor slightly deprioritized (Nice=5) without delaying its startup"
fi

# ── Step 7: WiFi/hotspot permissions ───────────────────────────────────────
step "Step 7/9 — Installing WiFi hotspot permissions"

sudo bash tools/install_permissions.sh "$SERVICE_USER"
ok "WiFi permissions installed"

# Apply any version pins declared in apt-requirements.txt. Step 1 installed the
# packages — 'name=version' is a spec apt-get install already understands — but
# nothing has held them yet, and an unheld pin is not a pin: the first
# `apt upgrade` moves it and the declaration quietly stops meaning anything.
# The wrapper is the one thing that knows how to reconcile holds, and it only
# exists once the script above has run, which is why this sits here rather than
# in Step 1. Idempotent, and a no-op when nothing is pinned.
if [ -x /usr/local/bin/mempaper-apt-install ]; then
    sudo /usr/local/bin/mempaper-apt-install || warn "Could not apply package version pins"
fi

# WiFi regulatory domain: without a country set, the radio can stay
# soft-blocked by rfkill (or hostapd can fail to select a channel) — on a
# fresh flash this can prevent both station-mode WiFi and the setup hotspot
# from ever coming up. raspi-config's do_wifi_country is the officially
# supported way to set this reliably on both Bookworm and Trixie.
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_wifi_country "$WIFI_COUNTRY"
    ok "WiFi country set to ${WIFI_COUNTRY}"
else
    warn "raspi-config not found — set WiFi country manually: sudo raspi-config > Localisation Options > WLAN Country"
fi
sudo rfkill unblock wifi 2>/dev/null || true
sudo nmcli radio wifi on 2>/dev/null || true
ok "WiFi radio unblocked"

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

# ── Optional: fail2ban ────────────────────────────────────────────────────
if [[ "$F2B_CHOICE" =~ ^[Yy]$ ]]; then
    sudo apt-get install -y fail2ban -q
    ok "fail2ban installed"
else
    ok "Skipping fail2ban"
fi

# ── Post-install system configuration ─────────────────────────────────────
# Periodic TRIM and anything else that is system state rather than repository
# content. Kept in its own idempotent script so the web updater can re-apply it
# on an existing device — inline here, these steps only ever ran on a fresh
# install, and a release that added one silently skipped every updated device.
sudo bash tools/postinstall.sh

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
    # Some Raspberry Pi OS images (Imager-preconfigured accounts) provision an
    # /etc/ssh/sshd_config.d/*.conf drop-in — e.g. cloud-init's 50-cloud-init.conf —
    # that re-enables password auth for the first-boot account. sshd's Include
    # directive (near the top of sshd_config) uses first-match-wins semantics,
    # so a drop-in loaded before our edit above silently overrides it. Write our
    # own drop-in named to sort first (Include expands *.conf in lexical order)
    # so it wins the precedence race instead.
    sudo mkdir -p /etc/ssh/sshd_config.d
    sudo tee /etc/ssh/sshd_config.d/00-mempaper-hardening.conf > /dev/null << 'EOF'
# Written by mempaper install.sh. Named to sort first among sshd_config.d
# drop-ins (e.g. before cloud-init's 50-cloud-init.conf) since sshd applies
# the first value it encounters for each keyword.
PasswordAuthentication no
PermitRootLogin no
EOF
    sudo chmod 644 /etc/ssh/sshd_config.d/00-mempaper-hardening.conf
    sudo systemctl reload sshd
    # Verify against the actual effective config rather than assuming the
    # edits above won — catches any other higher-precedence override too.
    if sudo sshd -T 2>/dev/null | grep -qi '^passwordauthentication no'; then
        ok "SSH hardened: password auth disabled, root login disabled (key-only)"
        echo ""
        echo -e "  ${YELLOW}⚠  SSH password login is now disabled.${NC}"
        echo "  Add your SSH public key via Settings > General > Advanced > SSH Access."
        echo "  Until then, SSH access requires physical access to the Pi."
    else
        warn "SSH hardening written, but password auth is still effectively enabled"
        echo "  Another /etc/ssh/sshd_config.d/*.conf drop-in is likely overriding it."
        echo "  Check: sudo sshd -T | grep -i passwordauthentication"
        echo "         ls /etc/ssh/sshd_config.d/"
    fi
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

# Detect the Pi's current IP on the WiFi interface for the dashboard URL.
_WIFI_IFACE=$(ip -o link show | awk -F': ' '/wlan/{print $2; exit}')
_DEVICE_IP=""
if [ -n "$_WIFI_IFACE" ]; then
    _DEVICE_IP=$(ip -4 addr show "$_WIFI_IFACE" 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)
fi

echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │     Setup complete — ready to start!     │"
echo "  └──────────────────────────────────────────┘"
echo ""
if [ -n "$_DEVICE_IP" ]; then
    echo -e "  ${CYAN}Dashboard:${NC}"
    echo -e "    ${GREEN}http://$_DEVICE_IP:5000${NC}"
    echo ""
fi
echo "  Useful commands:"
echo "    sudo journalctl -u mempaper.service -f    # live logs"
echo "    sudo systemctl restart mempaper.service   # restart"
echo "    sudo systemctl status mempaper.service    # status"
echo ""
echo "  To reconfigure the display later (not possible from the web UI):"
echo "    cd $SCRIPT_DIR"
echo "    sudo -u $SERVICE_USER $VENV_DIR/bin/python tools/configure_display.py"
echo ""
echo "  To prepare for delivery (factory reset):"
echo "    sudo -u $SERVICE_USER $VENV_DIR/bin/python tools/delivery_state.py"
echo ""

# ── Step 9: Start service ─────────────────────────────────────────────────
step "Step 9/9 — Starting mempaper service"

# Drop a one-shot marker so the app pushes a fast e-ink refresh on this
# start, confirming the install went through even when a reboot isn't
# needed (a plain "systemctl restart" alone wouldn't otherwise trigger one).
sudo -u "$SERVICE_USER" mkdir -p "$SCRIPT_DIR/cache"
sudo -u "$SERVICE_USER" touch "$SCRIPT_DIR/cache/boot_refresh_pending"

if [ "$NEEDS_REBOOT" = true ]; then
    echo ""
    echo -e "  ${YELLOW}SPI not yet active — rebooting to enable it.${NC}"
    echo ""
    echo "  Rebooting in 5 seconds (Ctrl+C to cancel)..."
    sleep 5
    sudo reboot
else
    sudo systemctl restart mempaper.service
    ok "mempaper service started"
fi

_T1=$(date +%s)
_ELAPSED=$(( _T1 - _T0 ))
_MIN=$(( _ELAPSED / 60 ))
_SEC=$(( _ELAPSED % 60 ))
echo ""
echo -e "  ${GREEN}Total install time: ${_MIN}m ${_SEC}s${NC}"
