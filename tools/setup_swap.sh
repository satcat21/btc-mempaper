#!/bin/bash
# setup_swap.sh — a disk-backed swap file on devices that cannot build without one.
#
# Raspberry Pi OS backs swap with zram: compressed pages held in RAM. That is the
# right default for a running dashboard, but it adds no capacity — on a 512 MB Pi
# Zero the compressed pages compete for the same memory a build needs. A source
# build of numpy or cryptography then thrashes or is killed, and on this hardware
# that costs hours before anything says so.
#
# A file on disk is the only tier that adds capacity. Priority 10 keeps it below
# zram's 100, so pages still reach the fast tier first and the file absorbs only
# the overflow. It is SD-card wear, so it is sized once and skipped entirely on a
# device with memory to spare.
#
# Run from install.sh before the first pip build, and from postinstall.sh so it
# also reaches a device that was installed before this existed and only ever
# updates through the web UI.
#
# Exit codes, so callers can report what happened:
#   0   nothing to do — already covered, or not needed here
#   10  a swap file was created and enabled
#   1   needed but could not be set up

set -u

SWAPFILE="${SWAPFILE:-/swapfile}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-2048}"

# Above this there is enough RAM to build without help, and the SD-card wear
# would buy nothing.
MEM_CEILING_MB=1536

# Room for the file plus a working margin, so a nearly full card is not finished
# off by a 2 GB allocation.
DISK_MARGIN_MB=1024

if [ "$(id -u)" -ne 0 ]; then
    echo "setup_swap.sh must run as root" >&2
    exit 1
fi

MEM_TOTAL_MB=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
DISK_FREE_MB=$(df -Pm / 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)

if [ "${MEM_TOTAL_MB:-0}" -eq 0 ]; then
    echo "Could not read total memory — skipping swap file setup" >&2
    exit 0
fi

if [ "$MEM_TOTAL_MB" -gt "$MEM_CEILING_MB" ]; then
    echo "Swap file not needed (${MEM_TOTAL_MB} MB RAM)"
    exit 0
fi

# Anything not on zram is already the tier this would add.
if swapon --show=NAME --noheadings 2>/dev/null | grep -qv '^/dev/zram'; then
    echo "Disk-backed swap already active — leaving it as it is"
    exit 0
fi

if [ -f "$SWAPFILE" ]; then
    # Present but not swapped on: an earlier run got this far, or a reboot has
    # not applied the fstab entry yet. Either way it is not ours to resize.
    swapon --priority 10 "$SWAPFILE" 2>/dev/null || true
    echo "Swap file already present: $SWAPFILE"
    exit 0
fi

if [ "${DISK_FREE_MB:-0}" -lt $((SWAP_SIZE_MB + DISK_MARGIN_MB)) ]; then
    echo "Only ${DISK_FREE_MB} MB free on / — skipping the ${SWAP_SIZE_MB} MB swap file" >&2
    exit 0
fi

# fallocate leaves an extent-mapped file that swapon rejects on some
# filesystems; dd writes the blocks out instead.
created=1
fallocate -l "${SWAP_SIZE_MB}M" "$SWAPFILE" 2>/dev/null \
    || dd if=/dev/zero of="$SWAPFILE" bs=1M count="$SWAP_SIZE_MB" status=none 2>/dev/null \
    || created=0

if [ "$created" -eq 1 ] \
    && chmod 600 "$SWAPFILE" \
    && mkswap "$SWAPFILE" >/dev/null 2>&1 \
    && swapon --priority 10 "$SWAPFILE" 2>/dev/null; then
    grep -q "^${SWAPFILE}[[:space:]]" /etc/fstab \
        || echo "${SWAPFILE} none swap sw,pri=10 0 0" >> /etc/fstab
    echo "Swap file active: ${SWAP_SIZE_MB} MB at priority 10, below zram"
    exit 10
fi

rm -f "$SWAPFILE"
echo "Could not enable $SWAPFILE — continuing without extra swap" >&2
exit 1
