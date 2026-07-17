#!/usr/bin/env bash
# install_wifi_permissions.sh
# Installs the polkit rule that allows mempaper's service user to manage
# NetworkManager connections (required for setup hotspot onboarding).
#
# Run once on the Raspberry Pi:
#   sudo bash ~/btc-mempaper/tools/install_wifi_permissions.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_SRC="${SCRIPT_DIR}/90-mempaper-wifi.rules"
RULES_DEST="/etc/polkit-1/rules.d/90-mempaper-wifi.rules"
SERVICE_USER="${1:-pi}"   # pass different user as first argument if needed

if [ "$(id -u)" != "0" ]; then
    echo "❌  This script must be run with sudo."
    echo "    sudo bash $0"
    exit 1
fi

echo "📋 Installing polkit rule for mempaper Wi-Fi onboarding…"
cp "${RULES_SRC}" "${RULES_DEST}"
chmod 644 "${RULES_DEST}"
echo "✅  Rule installed: ${RULES_DEST}"

# --- sudoers: scoped passwordless sudo for all mempaper operations ----------
# settings.modify.system cannot be granted via polkit rules/pkla on
# Raspberry Pi OS Bookworm without polkit-pkla-compat.  A narrow sudoers
# entry is the most reliable approach on embedded Pi OS.
# All rules are restricted to the exact commands mempaper actually runs.
# See docs/SECURITY_GUIDE.md for threat model and rationale.
SUDOERS_FILE="/etc/sudoers.d/mempaper-wifi"
APT_INSTALL_WRAPPER="/usr/local/bin/mempaper-apt-install"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
NMCLI_BIN="$(which nmcli    2>/dev/null || echo /usr/bin/nmcli)"
IW_BIN="$(which iw          2>/dev/null || echo /usr/sbin/iw)"
IPTABLES_BIN="$(which iptables 2>/dev/null || echo /usr/sbin/iptables)"
SYSTEMCTL_BIN="$(which systemctl 2>/dev/null || echo /usr/bin/systemctl)"
IP_BIN="$(which ip          2>/dev/null || echo /usr/sbin/ip)"
RFKILL_BIN="$(which rfkill  2>/dev/null || echo /usr/sbin/rfkill)"
NFT_BIN="$(which nft       2>/dev/null || echo /usr/sbin/nft)"
KILL_BIN="$(which kill      2>/dev/null || echo /bin/kill)"
MOUNT_BIN="$(which mount    2>/dev/null || echo /bin/mount)"
APT_GET_BIN="$(which apt-get 2>/dev/null || echo /usr/bin/apt-get)"
APT_BIN="$(which apt       2>/dev/null || echo /usr/bin/apt)"
TEE_BIN="$(which tee        2>/dev/null || echo /usr/bin/tee)"
CAT_BIN="$(which cat        2>/dev/null || echo /bin/cat)"
CHMOD_BIN="$(which chmod    2>/dev/null || echo /bin/chmod)"
MKDIR_BIN="$(which mkdir    2>/dev/null || echo /bin/mkdir)"
RM_BIN="$(which rm         2>/dev/null || echo /bin/rm)"

# Install apt wrapper script — installs only packages from apt-requirements.txt,
# accepts no arguments so the sudoers rule cannot be exploited to install arbitrary packages.
cat > "${APT_INSTALL_WRAPPER}" <<WRAPPER
#!/bin/bash
APT_REQ="${PROJECT_DIR}/apt-requirements.txt"
if [ ! -f "\$APT_REQ" ]; then
    echo "❌ apt-requirements.txt not found: \$APT_REQ" >&2
    exit 1
fi
PKGS=\$(grep -v '^\s*#' "\$APT_REQ" | grep -v '^\s*\$' | tr '\n' ' ')
if [ -z "\$PKGS" ]; then
    echo "No packages listed in apt-requirements.txt — nothing to install."
    exit 0
fi
exec apt-get install -y --no-upgrade \$PKGS
WRAPPER
chown root:root "${APT_INSTALL_WRAPPER}"
chmod 755 "${APT_INSTALL_WRAPPER}"
echo "✅  apt install wrapper installed: ${APT_INSTALL_WRAPPER}"

# Install Python upgrade wrapper — runs tools/upgrade_python.sh --force --no-restart
# Scoped: no arguments, executes a single known script path, cannot be used arbitrarily.
UPGRADE_PYTHON_WRAPPER="/usr/local/bin/mempaper-upgrade-python"
cat > "${UPGRADE_PYTHON_WRAPPER}" <<WRAPPER
#!/bin/bash
exec bash "${PROJECT_DIR}/tools/upgrade_python.sh" --force --no-restart
WRAPPER
chown root:root "${UPGRADE_PYTHON_WRAPPER}"
chmod 755 "${UPGRADE_PYTHON_WRAPPER}"
echo "✅  Python upgrade wrapper installed: ${UPGRADE_PYTHON_WRAPPER}"

# Install WiFi clear wrapper — removes ALL saved client WiFi profiles including
# netplan-managed ones (Pi Imager creates these as netplan-wlan0-SSID).
# nmcli connection delete refuses to remove netplan-managed connections because
# NM marks them as externally managed; direct file deletion + reload is required.
# Accepts optional --no-reload flag: deletes files and strips netplan YAML but
# skips daemon reload and netplan apply so SSH stays connected; changes take
# effect on next reboot. Useful when running over a WiFi SSH session.
CLEAR_WIFI_WRAPPER="/usr/local/bin/mempaper-clear-wifi"
cat > "${CLEAR_WIFI_WRAPPER}" <<'WRAPPER'
#!/bin/bash
# Remove all saved client WiFi profiles, including netplan-managed ones.
# Usage: mempaper-clear-wifi [--no-reload]
#   --no-reload  Delete files and strip netplan YAML but skip daemon reload
#                and netplan apply. SSH stays connected; takes effect on reboot.

NO_RELOAD=0
for arg in "$@"; do
    [ "$arg" = "--no-reload" ] && NO_RELOAD=1
done

DELETED=0

# Step 1: Delete NM connection files directly for wifi-type connections.
# Handles Pi Imager netplan-wlan0-* profiles that nmcli refuses to delete.
for DIR in /etc/NetworkManager/system-connections /run/NetworkManager/system-connections; do
    [ -d "$DIR" ] || continue
    for F in "$DIR"/*.nmconnection; do
        [ -f "$F" ] || continue
        TYPE=$(awk -F= '/^type[[:space:]]*=/{gsub(/[[:space:]]/,"",$2); print $2; exit}' "$F")
        NAME=$(awk -F= '/^id[[:space:]]*=/{sub(/^[[:space:]]*/,"",$2); print $2; exit}' "$F")
        [ "$TYPE" = "wifi" ] || continue
        case "$NAME" in mempaper-setup*) continue ;; esac
        echo "Removing NM connection file: $F ($NAME)"
        rm -f "$F" && DELETED=$((DELETED+1))
    done
done

# Step 2: Reload NM so removed files take effect immediately (skipped with --no-reload).
# Omitting this keeps the active WiFi connection alive so an SSH session survives;
# NM will start clean from disk on next reboot.
if [ "$NO_RELOAD" = "0" ]; then
    nmcli connection reload 2>/dev/null || true
fi

# Step 3: Remove wifis section from netplan configs so they are not recreated at boot.
# This is a plain file edit — no daemon interaction, safe with --no-reload.
for YAML in /etc/netplan/*.yaml; do
    [ -f "$YAML" ] || continue
    grep -q 'wifis:' "$YAML" 2>/dev/null || continue
    python3 - "$YAML" <<'PYEOF'
import sys, yaml
path = sys.argv[1]
with open(path) as f:
    data = yaml.safe_load(f) or {}
net = data.get('network', {})
if 'wifis' not in net:
    sys.exit(0)
del net['wifis']
with open(path, 'w') as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
print('Removed wifis section from ' + path)
PYEOF
done

# Step 4: Apply netplan changes if netplan is present (skipped with --no-reload).
if [ "$NO_RELOAD" = "0" ]; then
    command -v netplan >/dev/null 2>&1 && netplan apply 2>/dev/null || true
fi

if [ "$NO_RELOAD" = "1" ]; then
    echo "WiFi config cleared (deferred) — $DELETED file(s) removed, takes effect after reboot"
else
    echo "WiFi clear complete — removed $DELETED connection file(s)"
fi
WRAPPER
chown root:root "${CLEAR_WIFI_WRAPPER}"
chmod 755 "${CLEAR_WIFI_WRAPPER}"
echo "✅  WiFi clear wrapper installed: ${CLEAR_WIFI_WRAPPER}"

# Saved-WiFi-check wrapper — root-owned since connection files aren't
# readable by the service user. Exit 0 = a saved network exists, 1 = none.
HAS_SAVED_WIFI_WRAPPER="/usr/local/bin/mempaper-has-saved-wifi"
cat > "${HAS_SAVED_WIFI_WRAPPER}" <<'WRAPPER'
#!/bin/bash
for DIR in /etc/NetworkManager/system-connections /run/NetworkManager/system-connections; do
    [ -d "$DIR" ] || continue
    for F in "$DIR"/*.nmconnection; do
        [ -f "$F" ] || continue
        TYPE=$(awk -F= '/^type[[:space:]]*=/{gsub(/[[:space:]]/,"",$2); print $2; exit}' "$F")
        NAME=$(awk -F= '/^id[[:space:]]*=/{sub(/^[[:space:]]*/,"",$2); print $2; exit}' "$F")
        [ "$TYPE" = "wifi" ] || continue
        case "$NAME" in mempaper-setup*) continue ;; esac
        exit 0
    done
done
exit 1
WRAPPER
chown root:root "${HAS_SAVED_WIFI_WRAPPER}"
chmod 755 "${HAS_SAVED_WIFI_WRAPPER}"
echo "✅  Saved-WiFi-check wrapper installed: ${HAS_SAVED_WIFI_WRAPPER}"

cat > "${SUDOERS_FILE}" <<EOF
# mempaper sudoers rules — generated by tools/install_wifi_permissions.sh
# Rules are scoped to the exact commands mempaper runs. See docs/SECURITY_GUIDE.md.

# WiFi management via NetworkManager.
# nmcli uses many subcommands so kept broad; it does not execute arbitrary code.
${SERVICE_USER} ALL=(root) NOPASSWD: ${NMCLI_BIN}

# Passive WiFi scan during AP mode (read-only — no network changes possible)
${SERVICE_USER} ALL=(root) NOPASSWD: ${IW_BIN} dev * scan passive

# Captive-portal NAT rules: redirect HTTP/HTTPS ports to Flask
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t nat -A PREROUTING *
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t nat -D PREROUTING *
# Captive-portal filter rules: block DNS-over-TLS leakage from clients
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t filter -I FORWARD *
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t filter -D FORWARD *
# Captive-portal INPUT rules: allow hotspot clients through to Flask port (Trixie nftables firewall)
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t filter -I INPUT *
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN} -t filter -D INPUT *

# Hotspot DHCP: stop/start system dnsmasq at runtime so NM can bind port 53/67.
# Without these, the sudo call fails silently and dnsmasq keeps port 53, preventing
# NM from starting its own dnsmasq instance for ipv4.method=shared DHCP.
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop dnsmasq
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start dnsmasq
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop dnsmasq.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start dnsmasq.service

# Hotspot firewall: add/remove an accept rule for the AP interface in the
# native nftables 'inet filter input' chain (Debian Trixie default policy drop).
# iptables-nft rules go into a separate 'ip filter' namespace and do NOT protect
# against the inet filter DROP — only direct nft commands do.
${SERVICE_USER} ALL=(root) NOPASSWD: ${NFT_BIN} insert rule inet filter input iifname * accept
${SERVICE_USER} ALL=(root) NOPASSWD: ${NFT_BIN} delete rule inet filter input handle *
${SERVICE_USER} ALL=(root) NOPASSWD: ${NFT_BIN} -a list chain inet filter input

# DHCP option 114 (RFC 8910): write captive portal URL into NM's dnsmasq-shared.d
# so Android 11+ detects the portal immediately via DHCP instead of HTTP probing.
${SERVICE_USER} ALL=(root) NOPASSWD: ${MKDIR_BIN} -p /etc/NetworkManager/dnsmasq-shared.d
${SERVICE_USER} ALL=(root) NOPASSWD: ${TEE_BIN} /etc/NetworkManager/dnsmasq-shared.d/mempaper-captive.conf
${SERVICE_USER} ALL=(root) NOPASSWD: ${RM_BIN} -f /etc/NetworkManager/dnsmasq-shared.d/mempaper-captive.conf

# Setup hotspot: interface handoff between NetworkManager (station mode) and
# hostapd (AP mode). mempaper releases the interface before starting hostapd
# and hands it back to NM when the hotspot tears down.
${SERVICE_USER} ALL=(root) NOPASSWD: ${IP_BIN} link set * up
${SERVICE_USER} ALL=(root) NOPASSWD: ${IP_BIN} addr add * dev *
${SERVICE_USER} ALL=(root) NOPASSWD: ${IP_BIN} addr flush dev *

# WiFi radio unblock: lifts a persisted software rfkill soft-block at startup
# (e.g. NetworkManager.state's WirelessEnabled saved as false across a
# reboot) so the radio doesn't come up disabled independent of the
# one-time country-code fix applied at install time.
${SERVICE_USER} ALL=(root) NOPASSWD: ${RFKILL_BIN} unblock wifi

# Setup hotspot: start/stop/restart the hostapd (AP) and dnsmasq (DHCP/DNS)
# systemd units. systemd supervises the actual processes (crash-restart,
# journald logging) — mempaper only ever asks it to start/stop/restart.
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start mempaper-hostapd.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop mempaper-hostapd.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} restart mempaper-hostapd.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start mempaper-dnsmasq.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop mempaper-dnsmasq.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} restart mempaper-dnsmasq.service

# Remount root filesystem rw/ro around apt operations (read-only Pi OS root partition)
${SERVICE_USER} ALL=(root) NOPASSWD: ${MOUNT_BIN} -o remount\,rw /
${SERVICE_USER} ALL=(root) NOPASSWD: ${MOUNT_BIN} -o remount\,ro /

# Remount /boot/firmware rw/ro around apt operations — it's a separate mount
# point from / on Raspberry Pi OS, and apt upgrades that touch initramfs-tools
# write there directly (not covered by remounting / above).
${SERVICE_USER} ALL=(root) NOPASSWD: ${MOUNT_BIN} -o remount\,rw /boot/firmware
${SERVICE_USER} ALL=(root) NOPASSWD: ${MOUNT_BIN} -o remount\,ro /boot/firmware

# System package updates (for SSH admin maintenance via 'ssh mempaper@<ip>')
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_BIN} update
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_BIN} upgrade -y
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_BIN} autoremove -y
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_GET_BIN} update
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_GET_BIN} upgrade -y
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_GET_BIN} autoremove -y

# Scoped apt install wrapper — only installs packages from apt-requirements.txt,
# accepts no arguments (no wildcard, cannot be used to install arbitrary packages).
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_INSTALL_WRAPPER}

# Python minor-version upgrade wrapper — unholds, upgrades, rebuilds venv.
# Scoped to a single fixed script path; cannot install arbitrary packages.
${SERVICE_USER} ALL=(root) NOPASSWD: ${UPGRADE_PYTHON_WRAPPER}

# WiFi profile clear wrapper — deletes all saved client WiFi profiles including
# Pi Imager netplan-managed connections that nmcli refuses to remove directly.
# --no-reload variant keeps SSH alive; changes take effect on next reboot.
${SERVICE_USER} ALL=(root) NOPASSWD: ${CLEAR_WIFI_WRAPPER}
${SERVICE_USER} ALL=(root) NOPASSWD: ${CLEAR_WIFI_WRAPPER} --no-reload

# Filesystem-only saved-WiFi check — lets startup skip waiting on
# NetworkManager entirely when there's nothing saved to reconnect to.
${SERVICE_USER} ALL=(root) NOPASSWD: ${HAS_SAVED_WIFI_WRAPPER}

# Pre-declare / undo wlan0 as NetworkManager-unmanaged around a factory
# reset, so hotspot bring-up doesn't need to wait for NM's D-Bus readiness.
${SERVICE_USER} ALL=(root) NOPASSWD: ${MKDIR_BIN} -p /etc/NetworkManager/conf.d
${SERVICE_USER} ALL=(root) NOPASSWD: ${TEE_BIN} /etc/NetworkManager/conf.d/99-mempaper-wlan0-unmanaged.conf
${SERVICE_USER} ALL=(root) NOPASSWD: ${RM_BIN} -f /etc/NetworkManager/conf.d/99-mempaper-wlan0-unmanaged.conf

# Disable cloud-init's per-boot network re-application after a WiFi clear —
# Raspberry Pi Imager's NoCloud datasource re-injects the original WiFi
# network from /boot/firmware/ on every boot otherwise, silently undoing the
# clear above before the app's own "no saved networks" check ever runs.
${SERVICE_USER} ALL=(root) NOPASSWD: ${MKDIR_BIN} -p /etc/cloud/cloud.cfg.d
${SERVICE_USER} ALL=(root) NOPASSWD: ${TEE_BIN} /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg

# Service control
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start mempaper.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop mempaper.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} restart mempaper.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} enable mempaper.service
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} daemon-reload
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} reboot
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} poweroff

# Service file self-update: mempaper can regenerate and install its own unit file.
# tee is scoped to the exact service file path only.
${SERVICE_USER} ALL=(root) NOPASSWD: ${TEE_BIN} /etc/systemd/system/mempaper.service

# SSH key management for pi user (web GUI provisioning of admin SSH access)
${SERVICE_USER} ALL=(root) NOPASSWD: ${MKDIR_BIN} -p /home/pi/.ssh
${SERVICE_USER} ALL=(root) NOPASSWD: ${TEE_BIN} /home/pi/.ssh/authorized_keys
${SERVICE_USER} ALL=(root) NOPASSWD: ${CHMOD_BIN} 700 /home/pi/.ssh
${SERVICE_USER} ALL=(root) NOPASSWD: ${CHMOD_BIN} 600 /home/pi/.ssh/authorized_keys
${SERVICE_USER} ALL=(root) NOPASSWD: ${CAT_BIN} /home/pi/.ssh/authorized_keys
EOF
chmod 440 "${SUDOERS_FILE}"
# Validate the file (visudo -c exits non-zero if syntax is wrong)
if visudo -c -f "${SUDOERS_FILE}" >/dev/null 2>&1; then
    echo "✅  Sudoers rule installed: ${SUDOERS_FILE}"
else
    echo "❌  Sudoers rule invalid — removing to avoid lockout"
    rm -f "${SUDOERS_FILE}"
fi

# Ensure the service user is in the 'netdev' group
if id -nG "${SERVICE_USER}" | grep -qw netdev; then
    echo "✅  User '${SERVICE_USER}' is already in the 'netdev' group"
else
    echo "➕  Adding '${SERVICE_USER}' to the 'netdev' group…"
    usermod -aG netdev "${SERVICE_USER}"
    echo "✅  Done — group change takes effect on next login / reboot"
fi

# Also install a .pkla (legacy localauthority) file for settings.modify.system
# On Raspberry Pi OS the JavaScript rule alone cannot grant this action.
PKLA_DIR="/etc/polkit-1/localauthority/50-local.d"
PKLA_FILE="${PKLA_DIR}/90-mempaper-wifi.pkla"
mkdir -p "${PKLA_DIR}"
cat > "${PKLA_FILE}" <<'EOF'
[mempaper-wifi-modify-system]
Identity=unix-group:netdev
Action=org.freedesktop.NetworkManager.settings.modify.system
ResultAny=yes
ResultInactive=yes
ResultActive=yes

[mempaper-wifi-network-control]
Identity=unix-group:netdev
Action=org.freedesktop.NetworkManager.network-control
ResultAny=yes
ResultInactive=yes
ResultActive=yes

[mempaper-wifi-enable-disable]
Identity=unix-group:netdev
Action=org.freedesktop.NetworkManager.enable-disable-wifi
ResultAny=yes
ResultInactive=yes
ResultActive=yes
EOF
chmod 644 "${PKLA_FILE}"
echo "✅  Legacy pkla rule installed: ${PKLA_FILE}"

# Restart polkit so the new rule is picked up immediately
echo "🔄  Restarting polkit…"
if systemctl restart polkit 2>/dev/null; then
    echo "✅  polkit restarted"
else
    # Some older Pi OS images use a different unit name
    systemctl restart polkitd 2>/dev/null && echo "✅  polkitd restarted" \
        || echo "⚠️  Could not restart polkit — reboot the Pi to apply the rule"
fi

echo ""
if command -v nmcli >/dev/null 2>&1; then
    _PERMS=$(sudo -u "$SERVICE_USER" nmcli general permissions 2>/dev/null || true)
    _MODIFY=$(echo "$_PERMS" | grep -c 'settings\.modify\.system.*\(yes\|ja\)' || true)
    _SHARE=$(echo  "$_PERMS" | grep -c 'wifi\.share\.protected.*\(yes\|ja\)'   || true)
    if [ "$_MODIFY" -ge 1 ] && [ "$_SHARE" -ge 1 ]; then
        echo "✅  Wi-Fi permissions installed and verified."
    else
        echo "✅  Wi-Fi permissions installed."
        echo "⚠️  Permissions not yet active — a reboot may be required for polkit rules to take effect."
    fi
else
    echo "✅  Wi-Fi permissions installed."
fi
echo ""

# --- Captive-portal DNS (dnsmasq) ---------------------------------------------
# Ensure dnsmasq is installed for wildcard DNS during setup hotspot.
if ! command -v dnsmasq >/dev/null 2>&1; then
    echo "📦  Installing dnsmasq for captive-portal DNS..."
    apt-get install -y dnsmasq >/dev/null 2>&1 || true
fi
# Stop, disable, and MASK the system dnsmasq service so it can never auto-start
# (masking survives 'apt-get install dnsmasq' re-runs, unlike plain disable).
# mempaper runs its own dnsmasq under mempaper-dnsmasq.service (installed below).
systemctl stop dnsmasq 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true
systemctl mask dnsmasq 2>/dev/null || true
echo "✅  System dnsmasq masked (mempaper-dnsmasq.service owns DHCP/DNS for the setup hotspot)"

# --- Setup hotspot AP (hostapd) ------------------------------------------------
# hostapd creates the setup-hotspot access point directly
if ! command -v hostapd >/dev/null 2>&1; then
    echo "📦  Installing hostapd for the setup hotspot..."
    apt-get install -y hostapd >/dev/null 2>&1 || true
fi
# Stop, disable, and MASK the system hostapd service so it never auto-starts
# or conflicts with mempaper-hostapd.service (which takes over wlan0 only
# while the setup hotspot is active).
systemctl stop hostapd 2>/dev/null || true
systemctl disable hostapd 2>/dev/null || true
systemctl mask hostapd 2>/dev/null || true
echo "✅  System hostapd masked (mempaper-hostapd.service owns the setup hotspot AP)"

# Install the two on-demand systemd units mempaper starts/stops for the setup
# hotspot. Neither is enabled — mempaper_app.py controls them directly via
# 'systemctl start|stop|restart' (see sudoers rules above).
#
# __PROJECT_DIR__ is substituted here rather than hardcoded in the template:
# these units read their hostapd/dnsmasq config from <project>/cache/, the
# same path mempaper_app.py writes it to (not /tmp — mempaper.service's
# ProtectSystem=strict+PrivateTmp would put a /tmp write in a namespace
# private to that service, invisible to these independent units).
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${SCRIPT_DIR}/mempaper-hostapd.service" > /etc/systemd/system/mempaper-hostapd.service
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${SCRIPT_DIR}/mempaper-dnsmasq.service" > /etc/systemd/system/mempaper-dnsmasq.service
systemctl daemon-reload
echo "✅  mempaper-hostapd.service and mempaper-dnsmasq.service installed"

# Disable nftables systemd service so its inet-filter DROP policy never loads.
# Trixie's default /etc/nftables.conf creates an 'inet filter input' chain with
# policy drop, which silently kills DHCP DISCOVER broadcasts (UDP 67) from
# hotspot clients. NM's iptables-nft NAT and DHCP rules use separate 'ip nat'
# and 'ip filter' tables (policy accept) — they work correctly without this service.
systemctl stop nftables    2>/dev/null || true
systemctl disable nftables 2>/dev/null || true
echo "✅  nftables service disabled (prevents DHCP broadcast drop on Trixie)"

# --- Integrated mode cleanup -------------------------------------------------
echo "🔧 Enforcing integrated service mode (no separate onboarding service)…"
systemctl stop mempaper-onboarding.service 2>/dev/null || true
systemctl disable mempaper-onboarding.service 2>/dev/null || true
systemctl mask mempaper-onboarding.service 2>/dev/null || true
rm -f /etc/systemd/system/mempaper-onboarding.service
systemctl daemon-reload

if systemctl enable mempaper.service 2>/dev/null; then
    echo "✅  mempaper.service enabled"
else
    echo "⚠️  Could not enable mempaper.service (generate/install it first if missing)"
fi

echo ""
echo "✅  All done. Reboot to verify integrated hotspot onboarding in mempaper.service."
echo "   Monitor:  sudo journalctl -u mempaper.service -f"
