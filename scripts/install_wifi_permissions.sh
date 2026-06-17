#!/usr/bin/env bash
# install_wifi_permissions.sh
# Installs the polkit rule that allows mempaper's service user to manage
# NetworkManager connections (required for setup hotspot onboarding).
#
# Run once on the Raspberry Pi:
#   sudo bash ~/btc-mempaper/scripts/install_wifi_permissions.sh

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

# --- sudoers entry: passwordless 'sudo nmcli' for the service user ----------
# settings.modify.system cannot be granted via polkit rules/pkla on
# Raspberry Pi OS Bookworm without polkit-pkla-compat.  A narrow sudoers
# entry is the most reliable approach on embedded Pi OS.
SUDOERS_FILE="/etc/sudoers.d/mempaper-wifi"
NMCLI_BIN="$(which nmcli 2>/dev/null || echo /usr/bin/nmcli)"
IW_BIN="$(which iw 2>/dev/null || echo /usr/sbin/iw)"
IPTABLES_BIN="$(which iptables 2>/dev/null || echo /usr/sbin/iptables)"
SYSTEMCTL_BIN="$(which systemctl 2>/dev/null || echo /usr/bin/systemctl)"
cat > "${SUDOERS_FILE}" <<EOF
# mempaper: allow service user to manage NetworkManager connections (hotspot onboarding)
${SERVICE_USER} ALL=(root) NOPASSWD: ${NMCLI_BIN}
# mempaper: allow passive WiFi scan while in AP mode
${SERVICE_USER} ALL=(root) NOPASSWD: ${IW_BIN}
# mempaper: allow captive-portal port redirect (80/443 → Flask) during setup hotspot
${SERVICE_USER} ALL=(root) NOPASSWD: ${IPTABLES_BIN}
# mempaper: allow self-update to restart the service from the web UI
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} restart mempaper.service
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
echo "✅  Wi-Fi permissions installed."
echo "   Verify with:  nmcli general permissions | grep -E 'modify.system|share.protected'"
echo "   Expected:     org.freedesktop.NetworkManager.settings.modify.system  ja"
echo "                 org.freedesktop.NetworkManager.wifi.share.protected     ja"
echo ""

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
