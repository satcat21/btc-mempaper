#!/usr/bin/env bash
# install_permissions.sh
# Installs everything mempaper needs to act on the system as its own service
# user, without ever being root itself:
#
#   - the polkit rule + pkla granting NetworkManager control (setup hotspot)
#   - the scoped /etc/sudoers.d/mempaper grant set
#   - the /usr/local/bin/mempaper-* wrappers those grants point at
#     (apt install, Python upgrade, post-install, permissions refresh,
#      Wi-Fi clear, saved-Wi-Fi check)
#
# Named install_wifi_permissions.sh until the apt and update wrappers arrived
# and made that a third of what it does. tools/install_wifi_permissions.sh is
# kept as a shim so wrappers already on devices keep resolving.
#
# Run once on the Raspberry Pi:
#   sudo bash ~/btc-mempaper/tools/install_permissions.sh mempaper
#
# After that a release changing this file re-applies itself through the web
# updater, via the refresh wrapper installed below.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_SRC="${SCRIPT_DIR}/90-mempaper-wifi.rules"
RULES_DEST="/etc/polkit-1/rules.d/90-mempaper-wifi.rules"
# Whose grants these are. Not a preference: it is whichever account systemd
# actually starts mempaper as, so read it out of the unit file rather than
# guess. The default used to be 'pi', from when this script only handled Wi-Fi
# and was run by hand on a fresh Pi. That became a quiet trap once the app ran
# as its own user — `sudo bash tools/install_permissions.sh` with no argument
# wrote a complete, valid, correctly-validated grant set for the wrong account,
# printed every tick, and left the service unable to do a single privileged
# thing. Every message in the app that names this command omits the argument,
# so that was the common case, not the exotic one.
_detect_service_user() {
    local u
    u=$(sed -n 's/^[[:space:]]*User=//p' /etc/systemd/system/mempaper.service 2>/dev/null \
        | head -1 | tr -d '[:space:]')
    if [ -n "$u" ]; then
        echo "$u"
    else
        echo mempaper
    fi
}
SERVICE_USER="${1:-$(_detect_service_user)}"   # pass a different user as the first argument if needed

if [ "$(id -u)" != "0" ]; then
    echo "❌  This script must be run with sudo."
    echo "    sudo bash $0"
    exit 1
fi

# A sudoers file naming an account that does not exist is still syntactically
# valid — visudo accepts it and this script would report success — so a typo in
# the argument produced a device with a perfect grant set that granted nothing.
# Check the account before writing anything that depends on it.
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "❌  No such user: '${SERVICE_USER}'"
    echo "    Nothing has been changed. Pass the account mempaper runs as, e.g."
    echo "    sudo bash $0 mempaper"
    exit 1
fi
echo "👤  Installing permissions for service user: ${SERVICE_USER}"

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
SUDOERS_FILE="/etc/sudoers.d/mempaper"
# What this file was called when it only carried Wi-Fi grants. Removed once the
# new one has been written *and* validated — never before, because a sudoers
# file that fails validation is deleted below, and doing the removal first would
# turn a syntax error into a device with no grants at all.
LEGACY_SUDOERS_FILE="/etc/sudoers.d/mempaper-wifi"
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
#
# Only the APT_REQ path is interpolated from here; the body goes through a quoted
# heredoc so its own $variables survive into the generated script unescaped.
{
    echo '#!/bin/bash'
    echo "APT_REQ=\"${PROJECT_DIR}/apt-requirements.txt\""
    cat <<'WRAPPER'
# No terminal here whether this was reached from the web updater or from cron,
# and debconf announces all three frontends it cannot use before giving up on
# its own. Set explicitly so it does not have to: sudo passes the variable in
# via env_keep when the caller sets it, but this wrapper is also run directly as
# root, and a device whose sudoers predates that grant would otherwise still get
# the cascade.
export DEBIAN_FRONTEND=noninteractive

if [ ! -f "$APT_REQ" ]; then
    echo "❌ apt-requirements.txt not found: $APT_REQ" >&2
    exit 1
fi

# Pins are scoped to the suite they were resolved against, named by a
# '# pins-for: <codename>' line in the file. A version from one suite's archive
# does not exist in another's, and apt matches a pinned version exactly, so on a
# different release every pin fails to install - and _apply_holds below would
# then hold each package at whatever it already had, freezing it off Debian's
# security updates while reporting the pins applied. Drop the versions instead:
# same packages, floating and unheld.
#
# The pins stand when the file names no suite (it predates this, or its author
# wants them unconditional) or when the codename cannot be read - releasing every
# hold on a healthy device over an unreadable /etc/os-release would be worse than
# doing nothing. Sourced in a subshell so os-release cannot clobber anything here.
PINS_TARGET="$(sed -n 's/^[[:space:]]*#[[:space:]]*[Pp]ins-for:[[:space:]]*\([A-Za-z0-9_.-][A-Za-z0-9_.-]*\).*/\1/p' \
    "$APT_REQ" | head -n1 | tr '[:upper:]' '[:lower:]')"
OS_CODENAME="$( . /etc/os-release 2>/dev/null && printf '%s' "${VERSION_CODENAME:-}" | tr '[:upper:]' '[:lower:]' )"
APPLY_PINS=1
if [ -n "$PINS_TARGET" ] && [ -n "$OS_CODENAME" ] && [ "$PINS_TARGET" != "$OS_CODENAME" ]; then
    APPLY_PINS=0
fi

# A declaration is 'name' or 'name=version'. The name is what dpkg-query and
# apt-mark take; the full spec is what apt-get install takes. Keeping the two
# apart is the whole reason this parsing is no longer one grep: handing
# 'tor=0.4.8.12-1' to dpkg-query reports an unknown package, so a pinned
# package would read as permanently missing.
declare -a PKGS=()          # names, declaration order
declare -A WANT_VERSION=()  # name -> pinned version, only for pinned entries
# '|| [ -n "$line" ]' is what makes the last line count. `read` returns non-zero
# when it reaches EOF without finding a delimiter, so a file whose final line
# carries no trailing newline had that line read into $line and then thrown away
# by the loop condition - the last package in apt-requirements.txt was silently
# invisible to this wrapper. It was never installed and never held, while every
# Python reader of the same file saw it and reported it missing. Editors that
# strip the final newline are common enough that guarding the read is the fix;
# depending on the file to always end in one is not.
while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    name="${line%%=*}"
    if [ "$name" != "$line" ] && [ "$APPLY_PINS" -eq 1 ]; then
        WANT_VERSION["$name"]="${line#*=}"
    fi
    PKGS+=("$name")
done < "$APT_REQ"

if [ ${#PKGS[@]} -eq 0 ]; then
    echo "No packages listed in apt-requirements.txt — nothing to install."
    exit 0
fi

if [ "$APPLY_PINS" -eq 0 ]; then
    echo "ℹ️  Version pins are declared for ${PINS_TARGET}; this device runs ${OS_CODENAME}."
    echo "    Installing the same ${#PKGS[@]} packages unpinned — those versions do not"
    echo "    exist in this archive. Re-pin apt-requirements.txt for ${OS_CODENAME} to change that."
fi

# '${Status}' is "want error state". Only the state says whether the files are
# on disk; matching the whole of 'install ok installed' also keyed on the want
# flag, which 'apt-mark hold' sets to 'hold' - so every held package read as
# missing and was then reported as blocked below. Match the state alone.
_missing() {
    local p
    for p in "$@"; do
        dpkg-query -W -f='${Status}' "$p" 2>/dev/null \
            | grep -q ' ok installed$' || echo "$p"
    done
}

_installed_version() {
    dpkg-query -W -f='${Version}' "$1" 2>/dev/null || true
}

# The spec apt-get install should receive for a package: pinned entries carry
# their version so apt puts that exact one on, everything else stays bare and
# floats to whatever the archive offers.
_spec() {
    if [ -n "${WANT_VERSION[$1]+x}" ]; then
        echo "$1=${WANT_VERSION[$1]}"
    else
        echo "$1"
    fi
}

# Packages whose hold belongs to tools/upgrade_python.sh rather than to this
# file. python3-dev is declared in apt-requirements.txt *and* held there to pin
# the Python minor version, so the release sweep below has to step around it:
# unholding it would let the next apt upgrade move the interpreter the venv is
# built against, which is exactly the failure the hold exists to prevent.
PYTHON_HOLDS=(python3 python3-dev python3-venv)

# ── Holds, reconciled against the declarations ───────────────────────────────
# A pin is only a pin if apt is told about it. Installing the right version is
# half the job; without a hold the next `apt upgrade` moves it again and the
# declaration silently stops meaning anything. The reverse matters just as much:
# dropping the '=version' from a line has to release the hold, or the package
# stays frozen forever at a version nothing declares any more.
_apply_holds() {
    local p want held to_hold=() to_release=() unsatisfied=()
    local -A have=()
    held="$(apt-mark showhold 2>/dev/null || true)"
    for p in "${PKGS[@]}"; do
        if [ -n "${WANT_VERSION[$p]+x}" ]; then
            want="${WANT_VERSION[$p]}"
            have["$p"]="$(_installed_version "$p")"
            # Only hold what is actually on the device. apt-mark hold on an
            # uninstalled package pins it as "never install" - silently, with no
            # error - which is how a declared package becomes permanently
            # uninstallable. The block at the top of this script exists because
            # that has happened.
            [ -z "${have[$p]}" ] && continue
            if [ "${have[$p]}" = "$want" ]; then
                printf '%s\n' "$held" | grep -qxF "$p" || to_hold+=("$p")
            else
                # The pin was asked for and did not take - the version is not in
                # the archive, or the install failed. Holding here would freeze
                # the package at a version *nothing declares*, silently cutting
                # it off from Debian's security updates while this function
                # printed "📌 Pinned (held)" and looked like it had worked. It is
                # the reason a device could sit for months on a version no
                # release ever asked for. Leave it floating and say so instead:
                # an unreachable pin is a declaration to fix, not a state to
                # freeze. Release a hold left behind by an earlier run for the
                # same reason - that hold is the frozen state, and this is the
                # only place that can undo it.
                unsatisfied+=("$p")
                printf '%s\n' "${PYTHON_HOLDS[@]}" | grep -qxF "$p" && continue
                printf '%s\n' "$held" | grep -qxF "$p" && to_release+=("$p")
            fi
        else
            printf '%s\n' "${PYTHON_HOLDS[@]}" | grep -qxF "$p" && continue
            printf '%s\n' "$held" | grep -qxF "$p" && to_release+=("$p")
        fi
    done
    if [ ${#to_hold[@]} -gt 0 ]; then
        apt-mark hold "${to_hold[@]}" >/dev/null 2>&1 \
            && echo "📌 Pinned (held): ${to_hold[*]}" \
            || echo "⚠️  Could not hold: ${to_hold[*]}" >&2
    fi
    if [ ${#to_release[@]} -gt 0 ]; then
        apt-mark unhold "${to_release[@]}" >/dev/null 2>&1 \
            && echo "🔓 Pin removed, now floating: ${to_release[*]}" \
            || echo "⚠️  Could not unhold: ${to_release[*]}" >&2
    fi
    if [ ${#unsatisfied[@]} -gt 0 ]; then
        echo "⚠️  Declared version not installed — left floating, NOT held:" >&2
        for p in "${unsatisfied[@]}"; do
            echo "      $p wants ${WANT_VERSION[$p]}, has ${have[$p]}" >&2
        done
        echo "    Check the version exists in this suite: apt-cache madison <package>" >&2
    fi
    return 0
}

# ── Pins that have drifted ───────────────────────────────────────────────────
# A pinned package that is installed at the wrong version is not "missing", so
# the presence check below would leave it alone forever. It gets there by an
# ordinary route: the pin was added or changed in a release, and the device
# already had some other version on it. Reconcile these first, before the
# missing-package pass, so a single run converges the device either way.
DRIFTED=()
for p in "${PKGS[@]}"; do
    [ -n "${WANT_VERSION[$p]+x}" ] || continue
    have="$(_installed_version "$p")"
    [ -z "$have" ] && continue                       # not installed - the missing pass owns it
    [ "$have" = "${WANT_VERSION[$p]}" ] && continue  # already exactly right
    DRIFTED+=("$p")
done

if [ ${#DRIFTED[@]} -gt 0 ]; then
    echo "Pinned but at another version: ${DRIFTED[*]}"
    # Unhold first: a held package cannot be changed at all, and these are
    # precisely the packages this script holds itself on the way out.
    apt-mark unhold "${DRIFTED[@]}" >/dev/null 2>&1 || true
    apt-get update || echo "⚠️  apt-get update failed — continuing with the cached index" >&2
    for p in "${DRIFTED[@]}"; do
        # --allow-downgrades because a pin may point backwards: that is the
        # entire purpose of pinning a version that a later upgrade moved past.
        apt-get install -y --allow-downgrades "$(_spec "$p")" \
            || echo "❌ could not pin $p to ${WANT_VERSION[$p]} (is that version in the archive?)" >&2
    done
fi

mapfile -t MISSING < <(_missing "${PKGS[@]}")
if [ ${#MISSING[@]} -eq 0 ]; then
    if [ ${#DRIFTED[@]} -eq 0 ]; then
        echo "All ${#PKGS[@]} declared packages already installed — nothing to do."
    fi
    _apply_holds
    exit $?
fi
echo "Missing: ${MISSING[*]}"

# A package on hold cannot be installed. apt-mark hold pins a package in its
# current state, and when that state is "not installed" apt refuses to change it
# - silently, reporting 0 newly installed with no error at all.
# tools/upgrade_python.sh holds python3/python3-dev/python3-venv to pin the
# Python minor version, so this is reachable in normal operation. Separate those
# out rather than attempting them: the attempt cannot succeed, and retrying it
# on every startup costs a package-index refresh on a Pi Zero for nothing.
HELD=$(apt-mark showhold 2>/dev/null || true)
BLOCKED=()
INSTALLABLE=()
for p in "${MISSING[@]}"; do
    if printf '%s\n' "$HELD" | grep -qxF "$p"; then
        BLOCKED+=("$p")
    else
        INSTALLABLE+=("$p")
    fi
done

if [ ${#BLOCKED[@]} -gt 0 ]; then
    echo "⚠️  On hold and not installed, so apt cannot install: ${BLOCKED[*]}" >&2
    echo "    Release and install with:" >&2
    echo "      sudo apt-mark unhold ${BLOCKED[*]}" >&2
    echo "      sudo apt-get install -y ${BLOCKED[*]}" >&2
    echo "    Re-hold afterwards only if the package is a Python metapackage" >&2
    echo "    whose minor version you are pinning." >&2
fi

if [ ${#INSTALLABLE[@]} -eq 0 ]; then
    echo "Nothing installable — every missing package is on hold." >&2
    exit 1
fi
MISSING=("${INSTALLABLE[@]}")

# Refresh the index before installing. A package that is new in this release does
# not exist in an index that predates it, and 'Unable to locate package' would
# otherwise abort the entire batch below - which is exactly how a device ends up
# running a release whose declared dependencies were never installed.
apt-get update || echo "⚠️  apt-get update failed — continuing with the cached index" >&2

# Batch first: it resolves shared dependencies in one pass and is far faster on a
# Pi Zero. But apt-get install is all-or-nothing, so a single unavailable package
# silently takes every other package down with it. On failure, retry one at a time
# so the damage is limited to the package that actually cannot be installed.
#
# --no-upgrade keeps an already-installed package where it is; it is harmless
# alongside a version spec, which names the target explicitly rather than asking
# for "newer".
SPECS=()
for p in "${MISSING[@]}"; do SPECS+=("$(_spec "$p")"); done
if ! apt-get install -y --no-upgrade "${SPECS[@]}"; then
    echo "⚠️  Batch install failed — retrying each package individually" >&2
    for p in "${MISSING[@]}"; do
        apt-get install -y --no-upgrade "$(_spec "$p")" || echo "❌ failed: $p" >&2
    done
fi

# Exit on what is actually on the device now, not on what apt-get returned. The
# app and the web updater use this status to decide whether to warn the user, so
# it must not report success for a package that is still missing.
mapfile -t STILL_MISSING < <(_missing "${MISSING[@]}")
# Holds are applied either way: a package that installed correctly should be
# pinned now, and a partial failure must not leave the packages that did land
# unpinned until the next run.
_apply_holds
if [ ${#STILL_MISSING[@]} -gt 0 ] || [ ${#BLOCKED[@]} -gt 0 ]; then
    [ ${#STILL_MISSING[@]} -gt 0 ] \
        && echo "❌ Still missing after install: ${STILL_MISSING[*]}" >&2
    [ ${#BLOCKED[@]} -gt 0 ] \
        && echo "❌ Not attempted (on hold): ${BLOCKED[*]}" >&2
    exit 1
fi
echo "✅ Installed: ${MISSING[*]}"
WRAPPER
} > "${APT_INSTALL_WRAPPER}"
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

# Install post-install wrapper — applies system configuration (periodic TRIM and
# anything else added later) that the web updater cannot apply on its own.
# Scoped the same way: no arguments, one fixed script path inside the repo, so
# its contents travel with the release while the grant stays narrow.
POSTINSTALL_WRAPPER="/usr/local/bin/mempaper-postinstall"
cat > "${POSTINSTALL_WRAPPER}" <<WRAPPER
#!/bin/bash
exec bash "${PROJECT_DIR}/tools/postinstall.sh"
WRAPPER
chown root:root "${POSTINSTALL_WRAPPER}"
chmod 755 "${POSTINSTALL_WRAPPER}"
echo "✅  Post-install wrapper installed: ${POSTINSTALL_WRAPPER}"

# Install permissions-refresh wrapper — re-runs *this* script for the service
# user it was originally installed for.
#
# Without it, every change to this file needs an SSH session as a sudo-capable
# user, and until someone does that the device keeps running the old wrappers
# and the old sudoers set. That is how a release ships a new grant to every
# device and the grant to none of them: the web updater checks out code that
# expects a wrapper which was never regenerated. The apt-install wrapper below
# is written by this script, so a change to how packages are declared - version
# pins, say - lands as new file content that nothing on the device reads.
#
# The service user is baked in at generation time rather than passed as an
# argument, so the sudoers rule below needs no wildcard and the grant cannot be
# redirected at another account.
#
# On privilege: this grants no reach that is not already granted. The
# post-install and Python-upgrade wrappers directly above both exec a script
# inside PROJECT_DIR as root, and PROJECT_DIR is writable by the service user -
# so anything able to write there already had root by way of those two. This
# adds a third door to a room that is already open, and in exchange the
# permission set stops silently drifting out of date on every device.
REFRESH_PERMS_WRAPPER="/usr/local/bin/mempaper-refresh-permissions"
cat > "${REFRESH_PERMS_WRAPPER}" <<WRAPPER
#!/bin/bash
exec bash "${PROJECT_DIR}/tools/install_permissions.sh" "${SERVICE_USER}"
WRAPPER
chown root:root "${REFRESH_PERMS_WRAPPER}"
chmod 755 "${REFRESH_PERMS_WRAPPER}"
echo "✅  Permissions refresh wrapper installed: ${REFRESH_PERMS_WRAPPER}"

# Record which revision of this script produced the wrappers currently on disk.
# The app compares this against the hash of the file in the repo, so it can say
# "the helper scripts are out of date" instead of failing obscurely later, and
# the web updater uses the same comparison to decide whether a refresh is due.
PERMS_STAMP="/usr/local/bin/.mempaper-permissions-stamp"
sha256sum "${SCRIPT_DIR}/install_permissions.sh" 2>/dev/null | awk '{print $1}' \
    > "${PERMS_STAMP}" || true
chmod 644 "${PERMS_STAMP}" 2>/dev/null || true

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
# mempaper sudoers rules — generated by tools/install_permissions.sh
# Rules are scoped to the exact commands mempaper runs. See docs/SECURITY_GUIDE.md.

# Quieten the journal. mempaper calls sudo on a timer (nmcli polling, rfkill,
# nft checks), and each call otherwise writes three lines to the unit journal:
# sudo's own COMMAND= entry plus a pam_unix session opened/closed pair. That
# buries the application's own output.
#
# !syslog      drops sudo's log entry for this user
# !pam_session skips PAM session setup, which is what emits the pam_unix pair.
#              These are short non-interactive helpers, so there is no session
#              to account for; it also saves a little work per call.
#
# Scoped to ${SERVICE_USER} only — sudo used by anyone else still logs normally,
# so this does not reduce the audit trail for administrators.
Defaults:${SERVICE_USER} !syslog, !pam_session

# Let DEBIAN_FRONTEND through to the apt commands below. There is no terminal
# behind a web request, so debconf tried Dialog, then Readline, then Teletype,
# reporting each failure into the update log before falling back to
# Noninteractive on its own.
#
# env_keep rather than a 'sudo DEBIAN_FRONTEND=noninteractive apt-get ...'
# command line, because every apt grant below is an exact command match: the
# prefixed form is a different command and sudo would refuse it, so the variable
# has to arrive as environment instead. Nothing is granted by this that was not
# already granted — it selects a debconf frontend for commands the service user
# may already run, and cannot name a program or a package.
Defaults:${SERVICE_USER} env_keep += "DEBIAN_FRONTEND"

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

# Dependency health check: validates a self-contained ruleset (own throwaway
# table/chain, read from stdin) via -c -f - — never touches the live 'inet
# filter input' chain, which doesn't exist outside of active hotspot mode.
${SERVICE_USER} ALL=(root) NOPASSWD: ${NFT_BIN} -c -f -

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

# Full upgrade. Unlike 'upgrade', this one is allowed to install new packages and
# to REMOVE existing ones in order to resolve a dependency change - which is both
# why it is needed (an ordinary upgrade silently holds back anything requiring a
# new dependency, and that residue never clears) and why it is the most dangerous
# grant in this file. The web route never calls it blind: it first runs
# 'apt-get -s dist-upgrade', which needs no privileges at all, and refuses to
# proceed if the simulation wants to remove a package that apt-requirements.txt
# declares or that the Python pin depends on.
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_GET_BIN} dist-upgrade -y
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_BIN} full-upgrade -y

# Scoped apt install wrapper — only installs packages from apt-requirements.txt,
# accepts no arguments (no wildcard, cannot be used to install arbitrary packages).
${SERVICE_USER} ALL=(root) NOPASSWD: ${APT_INSTALL_WRAPPER}

# Python minor-version upgrade wrapper — unholds, upgrades, rebuilds venv.
# Scoped to a single fixed script path; cannot install arbitrary packages.
${SERVICE_USER} ALL=(root) NOPASSWD: ${UPGRADE_PYTHON_WRAPPER}

# Post-install system configuration (periodic TRIM, and whatever a later release
# adds). Lets the web updater apply system state it otherwise could not touch.
# Scoped to a single fixed script path; takes no arguments.
${SERVICE_USER} ALL=(root) NOPASSWD: ${POSTINSTALL_WRAPPER}

# Permissions refresh — re-runs install_permissions.sh for this same user,
# so a release that changes a wrapper or adds a sudoers grant reaches the device
# through the web updater instead of waiting for someone to SSH in as pi.
# The service user is compiled into the wrapper, so there is no argument to
# abuse. See the note beside the wrapper for why this adds no new reach.
${SERVICE_USER} ALL=(root) NOPASSWD: ${REFRESH_PERMS_WRAPPER}

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
    # Only now is the old file safe to drop. Two sudoers files in
    # /etc/sudoers.d are both live, so leaving the legacy one behind would keep
    # granting whatever it listed - including grants deliberately removed from
    # the new set, which is the kind of leftover a security review is meant to
    # catch and a rename is a silly way to introduce.
    if [ -f "${LEGACY_SUDOERS_FILE}" ]; then
        rm -f "${LEGACY_SUDOERS_FILE}"
        echo "🧹  Removed superseded ${LEGACY_SUDOERS_FILE}"
    fi
else
    echo "❌  Sudoers rule invalid — removing to avoid lockout"
    rm -f "${SUDOERS_FILE}"
    # The legacy file is deliberately left where it is. It is stale, but it is
    # valid and it is what the running device is currently relying on; removing
    # it here would leave no grants at all and take the hotspot, the updater and
    # the recovery paths down with it.
    [ -f "${LEGACY_SUDOERS_FILE}" ] \
        && echo "⚠️  Keeping ${LEGACY_SUDOERS_FILE} — it is out of date, but removing it would leave no sudo grants at all"
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
