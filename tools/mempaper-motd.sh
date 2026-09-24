#!/usr/bin/env bash
# tools/mempaper-motd.sh — SSH login system overview for mempaper
#
# Installed by install.sh as a symlink:
#   /etc/profile.d/mempaper-motd.sh        (sourced on SSH login)
#   /usr/local/bin/mempaper                (direct CLI invocation)
#
# This file is sourced by bash for interactive login shells.
# Do NOT use 'set -e' — an error would exit the user's login shell.

# When run directly (not sourced from profile.d), skip the SSH guard.
# Use -ef (same inode) rather than string equality — symlinks give different
# path strings for $0 vs BASH_SOURCE[0] even when pointing to the same file.
if [[ ! "${BASH_SOURCE[0]}" -ef "${0}" ]]; then
    # Being sourced — only proceed for interactive SSH sessions.
    case "$-" in *i*) ;; *) return 0 2>/dev/null; exit 0 ;; esac
    [ -n "${SSH_CONNECTION:-}${SSH_TTY:-}" ] || return 0
fi

PROJECT_DIR="/home/mempaper/btc-mempaper"
CONFIG_FILE="${PROJECT_DIR}/config/config.json"
MEMES_DIR="${PROJECT_DIR}/static/memes"

# ── Latest release, fetched in the background ────────────────────────────────
# The two network requests - this one and the block-height probe below - were
# most of the time the login sat waiting, and they ran one after the other.
# Each now starts as early as its inputs allow and is read only where it is
# printed, so the banner takes as long as the slower of them rather than their
# sum plus everything else. Process substitution rather than '&': this file is
# sourced into an interactive shell, where a background job prints '[1] 1234'.
#
# Ask this checkout's own origin for the latest release, not a hardcoded
# upstream repo — a fork or a self-hosted GitLab mirror was otherwise told
# about upstream's releases and prompted to "update" to a tag it does not have.
# Mirrors the host-based GitHub/GitLab split used by the in-app update check.
_REMOTE=$(git -C "${PROJECT_DIR}" -c safe.directory="${PROJECT_DIR}" remote get-url origin 2>/dev/null || echo "")
_REMOTE="${_REMOTE%.git}"
_REMOTE="${_REMOTE%/}"
# host and owner/repo, handling https://host/path and git@host:path alike
_RHOST=$(printf '%s' "${_REMOTE}" | sed -E 's#^(https?|ssh|git)://##; s#^[^@/]+@##; s#[:/].*$##' | tr 'A-Z' 'a-z')
_RPATH=$(printf '%s' "${_REMOTE}" | sed -E 's#^(https?|ssh|git)://##; s#^[^@/]+@##; s#^[^:/]+[:/]##')

_fetch_latest() {
    [ -n "${_RHOST}" ] && [ -n "${_RPATH}" ] || return 0
    if [ "${_RHOST}" = "github.com" ] || [ "${_RHOST}" = "www.github.com" ]; then
        curl -sf --max-time 2 \
            "https://api.github.com/repos/${_RPATH}/releases/latest" 2>/dev/null \
            | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null
    else
        # GitLab returns a list, newest first; %2F-encode the project path
        curl -sf --max-time 2 \
            "https://${_RHOST}/api/v4/projects/$(printf '%s' "${_RPATH}" | sed 's#/#%2F#g')/releases" 2>/dev/null \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['tag_name'] if d else '')" 2>/dev/null
    fi
}
exec {_FD_LATEST}< <(_fetch_latest)
unset -f _fetch_latest

# Group a whole number the way the app's number_format setting groups it, so the
# banner and the display do not punctuate the same block height differently.
# Falls back to the raw digits if anything about the input is not a number.
_group() {
    case "$1" in
        ''|*[!0-9]*) printf '%s' "$1"; return ;;
    esac
    _g=$(printf '%s' "$1" | sed -E ':a;s/([0-9])([0-9]{3})($|[^0-9])/\1,\2\3/;ta')
    [ "${NUMBER_FORMAT:-eu}" = "us" ] || _g=$(printf '%s' "$_g" | tr ',' '.')
    printf '%s' "$_g"
}

# ── color codes ──────────────────────────────────────────────────────────────
_B='\033[1m'   _R='\033[0m'   _D='\033[2m'
_O='\033[38;5;214m'   _G='\033[32m'   _RE='\033[31m'   _Y='\033[33m'
_W='\033[1;97m'
_GY='\033[90m'

# ── Config (one Python call for all fields) ───────────────────────────────────
MEMPOOL_HOST="mempool.space"
MEMPOOL_PORT="443"
MEMPOOL_HTTPS="true"
DISP_ON="false"
DEVICE_NAME="none"
MEMPOOL_TOR="false"
TOR_SOCKS_HOST="127.0.0.1"
TOR_SOCKS_PORT="9050"
NUMBER_FORMAT="eu"

if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    _raw=$(python3 - <<PYEOF 2>/dev/null
import json, sys
try:
    with open('${CONFIG_FILE}') as f:
        c = json.load(f)
    print(c.get('mempool_host', 'mempool.space'))
    print(c.get('mempool_rest_port', '443'))
    print(str(c.get('e-ink-display-connected', False)).lower())
    print(c.get('omni_device_name', 'none'))
    print(str(c.get('mempool_use_https', True)).lower())
    print(str(c.get('mempool_use_tor', False)).lower())
    print(c.get('tor_socks_host', '127.0.0.1') or '127.0.0.1')
    print(c.get('tor_socks_port', 9050) or 9050)
    print(c.get('number_format', 'eu') or 'eu')
    # Set when three consecutive refresh failures switched the panel off. It is
    # what separates a display the operator disabled from one that broke.
    print(str(c.get('eink_auto_disabled', False)).lower())
except Exception:
    print('mempool.space'); print('443'); print('false'); print('none'); print('true')
    print('false'); print('127.0.0.1'); print('9050'); print('eu')
    print('false')
PYEOF
)
    MEMPOOL_HOST=$(printf '%s' "$_raw"  | sed -n '1p')
    MEMPOOL_PORT=$(printf '%s' "$_raw"  | sed -n '2p')
    DISP_ON=$(printf '%s' "$_raw"       | sed -n '3p')
    DEVICE_NAME=$(printf '%s' "$_raw"   | sed -n '4p')
    MEMPOOL_HTTPS=$(printf '%s' "$_raw" | sed -n '5p')
    MEMPOOL_TOR=$(printf '%s' "$_raw"   | sed -n '6p')
    TOR_SOCKS_HOST=$(printf '%s' "$_raw" | sed -n '7p')
    TOR_SOCKS_PORT=$(printf '%s' "$_raw" | sed -n '8p')
    NUMBER_FORMAT=$(printf '%s' "$_raw"  | sed -n '9p')
    DISP_AUTO_OFF=$(printf '%s' "$_raw" | sed -n '10p')
    [ "$NUMBER_FORMAT" = "us" ] || NUMBER_FORMAT="eu"
    : "${TOR_SOCKS_HOST:=127.0.0.1}" "${TOR_SOCKS_PORT:=9050}"
fi

# ── Block height, fetched in the background ───────────────────────────────────
# Needs the mempool host from the config, so it starts here rather than at the
# top; read back just before the mempaper rows are printed.

# Mempool URL
if [ "$MEMPOOL_HTTPS" = "true" ]; then
    [ "$MEMPOOL_PORT" = "443" ] \
        && _MURL="https://${MEMPOOL_HOST}" \
        || _MURL="https://${MEMPOOL_HOST}:${MEMPOOL_PORT}"
else
    [ "$MEMPOOL_PORT" = "80" ] \
        && _MURL="http://${MEMPOOL_HOST}" \
        || _MURL="http://${MEMPOOL_HOST}:${MEMPOOL_PORT}"
fi

# An .onion host resolves only through the SOCKS proxy, so without this the
# banner reports a perfectly healthy instance as offline. --socks5-hostname
# (not --socks5) leaves resolution to Tor. The longer budget covers circuit
# setup and the hidden-service descriptor lookup, which routinely exceed the
# clearnet timeout — kept modest because the login still waits for the answer.
_CURL_PROXY=()
_CURL_TIME=4
if [ "$MEMPOOL_TOR" = "true" ]; then
    _CURL_PROXY=(--socks5-hostname "${TOR_SOCKS_HOST}:${TOR_SOCKS_PORT}")
    _CURL_TIME=10
fi

_probe_tip() {
    curl -sf "${_CURL_PROXY[@]}" --max-time "$1" \
        "${_MURL}/api/blocks/tip/height" 2>/dev/null || true
}

# One failed request is not evidence of an offline host. A Tor circuit
# routinely fails to build on the first attempt and succeeds a moment later, so
# a single probe reported healthy onion instances as down. Two attempts, the
# second on a smaller budget: a host that really is unreachable should not hold
# the login open for twice as long as one that is merely slow.
_fetch_tip() {
    local tip
    tip=$(_probe_tip "${_CURL_TIME}")
    if ! printf '%s' "${tip}" | grep -qE '^[0-9]+$' 2>/dev/null; then
        tip=$(_probe_tip "$(( _CURL_TIME / 2 + 1 ))")
    fi
    printf '%s' "${tip}"
}
exec {_FD_TIP}< <(_fetch_tip)
# Sourced from profile.d, so anything defined here stays in the user's shell.
unset -f _probe_tip _fetch_tip

# ── Banner ────────────────────────────────────────────────────────────────────
_sp=26
_bl=(
    $'  _ __ ___   ___ _ __ ___  _ __   __ _ _ __   ___ _ __'
    $' | \'_ ` _ \\ / _ \\ \'_ ` _ \\| \'_ \\ / _` | \'_ \\ / _ \\ \'__|'
    $' | | | | | |  __/ | | | | | |_) | (_| | |_) |  __/ |'
    $' |_| |_| |_|\\___|_| |_| |_| .__/ \\__,_| .__/ \\___|_|'
    $'                          |_|         |_|'
)
printf '\n'
for _l in "${_bl[@]}"; do
    printf '%b%s%b%s%b\n' "${_W}" "${_l:0:$_sp}" "${_O}" "${_l:$_sp}" "${_R}"
done
printf '\n'
_ORIGIN=$(printf '%s' "${_REMOTE}" | sed -E 's#^(https?|ssh|git)://##; s#^[^@/]+@##; s#:#/#')
[ -n "${_ORIGIN}" ] || _ORIGIN="github.com/satcat21/btc-mempaper"
printf '%b\n' "  ${_B}${_Y}Bitcoin Meme Block Clock  ·  ${_ORIGIN}${_R}"

# ── Version info ──────────────────────────────────────────────────────────────
_OS_PRETTY=$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-}")
_PY_VER=$(python3 --version 2>/dev/null | awk '{print $2}')
_MVER=$(git -C "${PROJECT_DIR}" -c safe.directory="${PROJECT_DIR}" describe --tags --abbrev=0 2>/dev/null || echo "unknown")

# Started at the top; this waits only for whatever of it is still running.
_LATEST=$(cat <&"${_FD_LATEST}" 2>/dev/null)
exec {_FD_LATEST}<&-

printf '\n'
printf "  %b%s%b\n" "${_D}" "${_OS_PRETTY}" "${_R}"
printf "  Python %-10s mempaper %s" "${_PY_VER}" "${_MVER}"
if [ -n "$_LATEST" ] && [ "$_LATEST" != "$_MVER" ]; then
    printf "   %b${_B}→ %s available${_R}" "${_Y}" "${_LATEST}"
fi
printf '\n'
# The settings page is the reason most people log into this device at all,
# and the address is the one thing an SSH session cannot tell them. First
# global IPv4 rather than the hostname: .local depends on mDNS resolving
# from whatever machine they are sitting at, and it often does not.
_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | head -1)
[ -n "${_IP}" ] || _IP="$(hostname 2>/dev/null).local"
printf "  %bhttp://%s:5000%b\n" "${_O}" "${_IP}" "${_R}"
if [ -n "$_LATEST" ] && [ "$_LATEST" != "$_MVER" ]; then
    _CU=$(id -un 2>/dev/null || echo "${USER:-unknown}")
    if [ "$_CU" = "mempaper" ]; then
        printf "  %bUpdate: git -C ~/btc-mempaper fetch --tags%b\n" "${_D}" "${_R}"
        printf "  %b        git -C ~/btc-mempaper checkout %s%b\n" "${_D}" "${_LATEST}" "${_R}"
    else
        printf "  %bUpdate: sudo -u mempaper git -C %s fetch --tags%b\n" "${_D}" "${PROJECT_DIR}" "${_R}"
        printf "  %b        sudo -u mempaper git -C %s checkout %s%b\n" "${_D}" "${PROJECT_DIR}" "${_LATEST}" "${_R}"
    fi
    printf "  %b        sudo systemctl restart mempaper.service%b\n" "${_D}" "${_R}"
fi
printf '\n'

# ── Minification notice ────────────────────────────────────────────────────────
_DIST_EXISTS=false
_MINIFY_STALE=false
_JS_DIST="${PROJECT_DIR}/static/js/dist"
_CSS_DIST="${PROJECT_DIR}/static/css/dist"
if { [ -d "$_JS_DIST" ]  && ls "$_JS_DIST"/*.js  >/dev/null 2>&1; } || \
   { [ -d "$_CSS_DIST" ] && ls "$_CSS_DIST"/*.css >/dev/null 2>&1; }; then
    _DIST_EXISTS=true
    # Newest dist file is the staleness reference (-printf requires GNU find, fine on Pi OS)
    _DIST_REF=$(find "$_JS_DIST" "$_CSS_DIST" -maxdepth 1 \( -name '*.js' -o -name '*.css' \) \
                -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    # Stale when at least one source file is newer than the newest dist file
    if [ -n "$_DIST_REF" ] && \
       find "${PROJECT_DIR}/static/js" "${PROJECT_DIR}/static/css" \
            -maxdepth 1 \( -name '*.js' -o -name '*.css' \) -newer "$_DIST_REF" \
            2>/dev/null | grep -q .; then
        _MINIFY_STALE=true
    fi
fi
# Show when stale, or when an update is available (minify must be re-run after checkout)
if [ "$_MINIFY_STALE" = "true" ] || \
   { [ "$_DIST_EXISTS" = "true" ] && [ -n "$_LATEST" ] && [ "$_LATEST" != "$_MVER" ]; }; then
    _MCU=$(id -un 2>/dev/null || echo "${USER:-unknown}")
    if [ "$_MINIFY_STALE" = "true" ]; then
        printf "  %b${_B}⚡ Minified JS/CSS is stale${_R}%b — re-run minify.py:\n" "${_Y}" "${_R}"
    else
        printf "  %b${_B}⚡ Re-run minify.py after updating${_R}%b:\n" "${_Y}" "${_R}"
    fi
    if [ "$_MCU" = "mempaper" ]; then
        printf "  %bcd ~/btc-mempaper && .venv/bin/python tools/minify.py%b\n" "${_D}" "${_R}"
    else
        printf "  %bsudo -u mempaper sh -c 'cd %s && .venv/bin/python tools/minify.py'%b\n" "${_D}" "${PROJECT_DIR}" "${_R}"
    fi
    printf '\n'
fi

# ── System stats ──────────────────────────────────────────────────────────────

# Temperature
_TR=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
_T=$(( _TR / 1000 ))
if   [ "$_T" -ge 70 ]; then _TC="${_RE}"
elif [ "$_T" -ge 55 ]; then _TC="${_Y}"
else                        _TC="${_G}"
fi

# Uptime (e.g. "3 days, 4h 22m")
_UP=$(uptime -p 2>/dev/null | sed 's/^up //' \
    | sed 's/ hours\?/h/g; s/ minutes\?/m/g; s/ days\?/d/g' || echo '?')

# Memory — read /proc/meminfo directly (no locale dependency; free translates headers)
_MT=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo 2>/dev/null)
_MA=$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo 2>/dev/null)
: "${_MT:=1}" "${_MA:=0}"
_MU=$(( _MT - _MA ))
_MP=$(( _MU * 100 / _MT ))
if   [ "${_MP}" -ge 85 ]; then _MMC="${_RE}"
elif [ "${_MP}" -ge 70 ]; then _MMC="${_Y}"
else                           _MMC="${_G}"
fi

# Disk (root filesystem)
_DU=$(df -h / 2>/dev/null | awk 'NR==2{print $3}')
_DT=$(df -h / 2>/dev/null | awk 'NR==2{print $2}')
_DP=$(df    / 2>/dev/null | awk 'NR==2{gsub(/%/,"");print $5}')
if   [ "${_DP:-0}" -ge 85 ]; then _DC="${_RE}"
elif [ "${_DP:-0}" -ge 70 ]; then _DC="${_Y}"
else                              _DC="${_G}"
fi

# Load averages, each coloured by load per core: a load of 1.0 is one core
# fully busy, so a Pi Zero is saturated at 1.0 and a Pi 4 only at 4.0. Read from
# /proc/loadavg rather than uptime, whose decimal mark follows the locale; the
# banner formats it the way the app's number_format setting does instead.
_NCPU=$(nproc 2>/dev/null || echo 1)
[ "${_NCPU:-0}" -ge 1 ] 2>/dev/null || _NCPU=1
_LDA=($(awk -v n="${_NCPU}" '{
    for (i = 1; i <= 3; i++) {
        r = $i / n
        printf "%s %s ", $i, (r > 1) ? "r" : (r >= 0.95) ? "y" : "g"
    }
}' /proc/loadavg 2>/dev/null))
_LDP=""   # plain, for measuring the column
_LDC=""   # coloured, for printing
for _i in 0 2 4; do
    _v="${_LDA[_i]:-}"
    [ -n "${_v}" ] || continue
    [ "${NUMBER_FORMAT}" = "us" ] || _v="${_v/./,}"
    case "${_LDA[_i+1]}" in
        r) _c="${_RE}" ;; y) _c="${_Y}" ;; *) _c="${_G}" ;;
    esac
    [ -n "${_LDP}" ] && { _LDP="${_LDP}, "; _LDC="${_LDC}, "; }
    _LDP="${_LDP}${_v}"
    _LDC="${_LDC}${_c}${_v}${_R}"
done
[ -n "${_LDP}" ] || { _LDP="?"; _LDC="?"; }
_LDPAD=$(( 22 - ${#_LDP} ))
[ "${_LDPAD}" -ge 0 ] || _LDPAD=0

# Swap. Worth a row on a 512 MB device: a source build that outgrows RAM is
# killed rather than slowed, and swap in use is the warning before that happens.
#
# zram and the swap file are shown apart because they mean different things.
# zram is compressed RAM that Raspberry Pi OS sets up itself: always on, no SD
# card writes, and some use of it is normal. The swap file is on the card and
# mempaper-swap keeps it off except during builds and apt runs - so a single
# total made a healthy zram device read as a swap file that failed to switch off.
_SWAPFILE="/swapfile"
read -r _ZT _ZU _FT _FU <<EOF
$(awk 'NR > 1 {
    if ($1 ~ /^\/dev\/zram/) { zt += $3; zu += $4 } else { ft += $3; fu += $4 }
} END { printf "%d %d %d %d\n", zt / 1024, zu / 1024, ft / 1024, fu / 1024 }' /proc/swaps 2>/dev/null)
EOF
: "${_ZT:=0}" "${_ZU:=0}" "${_FT:=0}" "${_FU:=0}"

# label used total red% yellow% -> "label used/total MB (p%)", numbers coloured
_swap_part() {
    local p=$(( $2 * 100 / $3 )) c="${_G}"
    if   [ "$p" -ge "$4" ]; then c="${_RE}"
    elif [ "$p" -ge "$5" ]; then c="${_Y}"
    fi
    printf '%s %s%s/%s MB (%s%%)%s' "$1" "$c" "$(_group "$2")" "$(_group "$3")" "$p" "${_R}"
}

# zram filling up is the warning; up to half of it in use is routine.
_SWZ=""
[ "${_ZT}" -gt 0 ] && _SWZ="$(_swap_part zram "${_ZU}" "${_ZT}" 80 50)"
if [ "${_FT}" -gt 0 ]; then
    _SWF="$(_swap_part file "${_FU}" "${_FT}" 50 20)"
elif [ -e "${_SWAPFILE}" ]; then
    _SWF="file ${_GY}off${_R}"
else
    _SWF=""
fi
unset -f _swap_part

# One swap kind per line: the first sits beside the swap label, a second goes on
# the row below under an empty label, so neither line runs past the terminal.
if [ -n "${_SWZ}" ]; then
    _SW1="${_SWZ}"; _SW2="${_SWF}"
elif [ -n "${_SWF}" ]; then
    _SW1="${_SWF}"; _SW2=""
else
    _SW1="${_Y}none${_R}"; _SW2=""
fi

_MEMV="${_MMC}$(_group "${_MU}")/$(_group "${_MT}") MB (${_MP}%)${_R}"

# ── mempaper stats ────────────────────────────────────────────────────────────

# Service status
_SVC=$(systemctl is-active mempaper.service 2>/dev/null || true)
: "${_SVC:=unknown}"
if [ "$_SVC" = "active" ]; then _SD="${_G}"; _SL="running"
else                            _SD="${_RE}"; _SL="${_SVC}"
fi

# Meme count
_MC=0
if [ -d "$MEMES_DIR" ]; then
    _MC=$(find "$MEMES_DIR" -maxdepth 1 -type f \
        \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
           -o -iname '*.gif' -o -iname '*.webp' \) 2>/dev/null | wc -l | tr -d ' ')
    _MC=$(_group "${_MC}")
fi

# The mempool host shares its row with the memes count, so it has the same
# 20-character column as the service and display values. A host that fits is
# shown whole; a longer one - a v3 onion is 62 - keeps its head and its tail.
# ASCII dots rather than a single ellipsis character: printf pads by byte count,
# and a multi-byte glyph would throw the width calculation off.
_shorten_host() {
    local h="$1"
    [ "${#h}" -le 20 ] && { printf '%s' "$h"; return; }
    printf '%s...%s' "${h:0:8}" "${h: -9}"
}

# Block height — started in the background after the config was read; this
# waits only for whatever of it is still running.
_BH="—"
_MD="${_RE}"
_TIP=$(cat <&"${_FD_TIP}" 2>/dev/null)
exec {_FD_TIP}<&-

# The dot already says whether it answered - red for no, green for yes - so the
# label is the host and nothing else. "(offline)" beside a red dot said the same
# thing twice, and said it in English on an otherwise symbol-only line.
if printf '%s' "${_TIP}" | grep -qE '^[0-9]+$' 2>/dev/null; then
    _BH=$(_group "${_TIP}")
    _MD="${_G}"
fi
_ML="$(_shorten_host "${MEMPOOL_HOST}")"

unset -f _shorten_host

# Display state, as a dot rather than a word in brackets: the two rows above
# already carry their state that way, and "(enabled)" beside a device name says
# nothing the colour cannot. Three states, because "off" has two very different
# meanings - green is on, red is a panel the app switched off after three failed
# refreshes, grey is one the operator turned off.
_DL="${DEVICE_NAME}"
if [ "$DISP_ON" = "true" ] || [ "$DISP_ON" = "True" ]; then
    _DD="${_G}"
elif [ "$DISP_AUTO_OFF" = "true" ]; then
    _DD="${_RE}"
else
    _DD="${_GY}"
    [ "${DEVICE_NAME}" = "none" ] && _DL="not configured"
fi

# ── Separator ─────────────────────────────────────────────────────────────────
# As long as the widest row, so the lines frame the text rather than stopping
# short of it. Right-hand values start at column 49 and the separator at column
# 1, so it needs 48 characters plus the longest of them. Never shorter than the
# 64 it always was, never wider than the terminal.
_vlen() {
    local s
    s=$(printf '%b' "$1" | sed 's/\x1b\[[0-9;]*m//g')
    printf '%s' "${#s}"
}
_SEPN=64
for _v in "${_MEMV}" "${_SW1}" "${_SW2}" "${_UP}" "${_BH}" "${_MC} files"; do
    _n=$(( 48 + $(_vlen "${_v}") ))
    [ "${_n}" -gt "${_SEPN}" ] && _SEPN="${_n}"
done
_TCOLS=$(tput cols 2>/dev/null || echo 80)
[ "${_TCOLS:-0}" -gt 1 ] 2>/dev/null || _TCOLS=80
[ "${_SEPN}" -lt "${_TCOLS}" ] || _SEPN=$(( _TCOLS - 1 ))
_SEP=$(printf '%*s' "${_SEPN}" '' | sed 's/ /─/g')
unset -f _vlen

# ── Print ─────────────────────────────────────────────────────────────────────
printf ' %b\n' "${_B}${_SEP}${_R}"

# System rows. The left value column is padded by printf, so colour goes
# around the padded field rather than inside it; the right column is last on the
# line and needs no padding, so its value carries its own colour codes (%b).
# Left value column is 23 display chars; temp uses 24 to compensate for the
# 2-byte UTF-8 degree sign (° = 0xC2 0xB0) which printf counts as 2 chars.
printf "  %-9s ${_TC}%-23s${_R} %-13s %b\n" \
    "temp"   "${_T}°C"                         "memory"  "${_MEMV}"
printf "  %-9s ${_DC}%-22s${_R} %-13s %b\n" \
    "disk"   "${_DU:-?}/${_DT:-?} (${_DP:-?}%)" "swap"    "${_SW1}"
# load holds three colours in one field, so it is padded by hand.
if [ -n "${_SW2}" ]; then
    printf "  %-9s %b%*s %-13s %b\n" \
        "load"   "${_LDC}" "${_LDPAD}" ""     ""        "${_SW2}"
else
    printf "  %-9s %b\n" "load" "${_LDC}"
fi

printf ' %b\n' "${_B}${_SEP}${_R}"

# mempaper rows: label(9) + " ● "(3 vis.) + value(20) + label(13) + value
# _COL=20 empirically aligns with system rows — ● is ambiguous-width in some
# terminals, causing a 1-column offset vs. the byte-count calculation.
_COL=20

printf "  %-9s %b● %b%-${_COL}s %b%-13s %s\n" \
    "service"  "${_SD}" "${_R}" "${_SL}"  "${_R}" "uptime"        "${_UP}"

printf "  %-9s %b● %b%-${_COL}s %b%-13s %s\n" \
    "display"  "${_DD}" "${_R}" "${_DL}"  "${_R}" "block height"  "${_BH}"

printf "  %-9s %b● %b%-${_COL}s %b%-13s %s files\n" \
    "mempool"  "${_MD}" "${_R}" "${_ML}"  "${_R}" "memes count"   "${_MC}"

printf ' %b\n\n' "${_B}${_SEP}${_R}"

# Sourced from profile.d: leave no helper behind in the user's shell.
unset -f _group
