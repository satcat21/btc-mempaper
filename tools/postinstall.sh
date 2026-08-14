#!/bin/bash
# postinstall.sh — system state that a mempaper release depends on but that
# does not live in the repository.
#
# Usage:
#   sudo bash ~/btc-mempaper/tools/postinstall.sh
#
# Why this exists as its own script: the web updater checks out code, installs
# apt and pip packages, and restarts the service. It does not — and without a
# root shell cannot — apply system configuration. So when a release added
# periodic TRIM, every fresh install got it and every updated device silently
# did not, because that step lived inline in install.sh and install.sh never
# runs again after the first install.
#
# Everything here must be idempotent: it runs on every install and on every
# update, and re-running it must be a no-op on a device that is already correct.

set -u

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
step() { echo -e "\n${BLUE}▶ $1${NC}"; }
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root: sudo bash $0" >&2
    exit 1
fi

# ── Periodic TRIM ─────────────────────────────────────────────────────────
# Deleting a file on flash does not erase it. The controller marks the old
# cells free and writes the update elsewhere, so the previous contents stay
# physically present until those cells happen to be reused - recoverable from
# the raw NAND long after the file is gone. That matters here because wallet
# addresses are written in clear text unless Tang is enabled, so switching Tang
# on later does not remove what was already committed to the card.
#
# TRIM is the only lever that asks the controller to actually erase freed
# blocks. Best effort by design: plenty of SD cards do not implement discard,
# and that is not a reason to fail an install.
step "Periodic TRIM"
if fstrim / >/dev/null 2>&1; then
    if systemctl is-enabled fstrim.timer >/dev/null 2>&1; then
        ok "TRIM supported — fstrim.timer already enabled (weekly)"
    elif systemctl enable --now fstrim.timer >/dev/null 2>&1; then
        ok "TRIM supported — fstrim.timer enabled (weekly)"
    else
        warn "TRIM works but fstrim.timer could not be enabled — run 'sudo fstrim /' periodically"
    fi
else
    warn "This card does not support TRIM — freed blocks keep their old contents"
    warn "If it ever held wallet data in clear text, only re-flashing erases it"
fi

echo
ok "Post-install system configuration complete"
