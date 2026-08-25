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

# Whether this run actually changed anything. The updater runs this script on
# every update, which is the point - it is how a system-level step reaches a
# device installed before that step existed. But every check reported itself
# whether or not it did anything, so a device that was already correct printed
# four lines of "nothing to do" into the update log on every single update. The
# marker on the last line lets the updater collapse that to one line, while
# anyone running this over SSH still sees the full account.
CHANGED=0

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
step()    { echo -e "\n${BLUE}▶ $1${NC}"; }
ok()      { echo -e "${GREEN}✅ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; CHANGED=1; }
changed() { CHANGED=1; }

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root: sudo bash $0" >&2
    exit 1
fi

# ── Somewhere to write ────────────────────────────────────────────────────
# Steps below write to /etc, and this script is usually reached from the web
# updater - which runs it as a child of mempaper.service. That unit carries
# ProtectSystem=strict, so the whole hierarchy is read-only inside its mount
# namespace apart from the paths named in ReadWritePaths, and sudo does not
# leave that namespace. The updater remounts / before the permissions refresh
# and before apt, but an update that needs neither reaches this script with
# /etc still read-only, and every write here fails.
#
# Probed by writing rather than by reading /proc/mounts: the restriction is a
# read-only bind inside the namespace, and the underlying mount can be listed
# as rw while nothing here can write to it.
#
# Deliberately not put back afterwards. In the namespace it is undone when the
# service restarts at the end of the update, and the pip install that follows
# this script writes to the same filesystem - handing it back read-only would
# break the install this is meant to prepare for. The updater's own remounts do
# not restore it either, for the same reason.
_root_probe="/etc/.mempaper-write-probe.$$"
if ! ( : > "$_root_probe" ) 2>/dev/null; then
    mount -o remount,rw / 2>/dev/null || true
fi
if ( : > "$_root_probe" ) 2>/dev/null; then
    rm -f "$_root_probe"
else
    echo "⚠️  / is read-only and could not be remounted — steps that write to /etc will be skipped" >&2
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
        changed
        ok "TRIM supported — fstrim.timer enabled (weekly)"
    else
        warn "TRIM works but fstrim.timer could not be enabled — run 'sudo fstrim /' periodically"
    fi
else
    warn "This card does not support TRIM — freed blocks keep their old contents"
    warn "If it ever held wallet data in clear text, only re-flashing erases it"
fi

# ── Swap for building packages ────────────────────────────────────────────
# A device installed before this existed has no disk-backed swap, and its owner
# may never run install.sh again. Source builds there are killed for memory
# rather than failing with anything that names the cause.
SWAP_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/setup_swap.sh"
step "Swap for source builds"
if [ ! -f "$SWAP_SCRIPT" ]; then
    warn "setup_swap.sh not found — skipping"
else
    swap_rc=0
    bash "$SWAP_SCRIPT" || swap_rc=$?
    case "$swap_rc" in
        10) changed; ok "Swap file created for source builds" ;;
        0)  ok "Swap already as it should be" ;;
        *)  warn "Swap file could not be set up — source builds may run out of memory" ;;
    esac
fi

# ── How eagerly the kernel swaps ──────────────────────────────────────────
# The swap file above is a backstop for building a package from source, where
# the peak briefly exceeds what a 512 MB device has. It is not meant to be used
# in ordinary operation, and at the distribution default of 60 it is: the kernel
# moves cold anonymous pages out to grow the page cache long before there is any
# pressure, so a device sitting at 61% of its RAM still accumulates tens of
# megabytes of swap over a day. On a Pi that swap file lives on the SD card, and
# every one of those writes is card wear paid for nothing.
#
# 1, not 0. Zero tells the kernel to avoid swap until an allocation is about to
# fail, which on a small device means reaching for the OOM killer where it could
# have swapped - and a build killed for memory is the failure the swap file was
# added to prevent. 1 keeps the file available under genuine pressure while
# leaving a running service entirely in RAM.
SYSCTL_FILE="/etc/sysctl.d/60-mempaper-swappiness.conf"
step "Swap only under pressure"
if [ "$(cat /proc/sys/vm/swappiness 2>/dev/null)" = "1" ]    && [ -f "$SYSCTL_FILE" ]; then
    ok "Swappiness already 1 — swap is a backstop, not everyday storage"
else
    # Written for the next boot and applied to this one: a device that is not
    # rebooted after an update would otherwise keep the old behaviour
    # indefinitely, which for this setting is the whole of its service life.
    if cat > "$SYSCTL_FILE" << 'SYSCTL'
# Written by mempaper postinstall.sh.
# The swap file exists so a source build is not killed for memory. It is not
# meant to carry a running service, and the default of 60 puts it there.
vm.swappiness = 1
SYSCTL
    then
        chmod 644 "$SYSCTL_FILE"
        if sysctl -q -w vm.swappiness=1 2>/dev/null; then
            changed
            ok "Swappiness set to 1, now and on every boot"
        else
            changed
            warn "Swappiness will apply on the next boot — could not set it live"
        fi
    else
        warn "Could not write ${SYSCTL_FILE} — swappiness stays at the default"
    fi
fi

echo
ok "Post-install system configuration complete"

# Machine-readable, always last, stripped by the updater before display.
if [ "${CHANGED}" -eq 0 ]; then
    echo "POSTINSTALL_RESULT=unchanged"
else
    echo "POSTINSTALL_RESULT=changed"
fi
