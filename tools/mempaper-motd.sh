#!/usr/bin/env bash
# tools/mempaper-motd.sh — SSH login system overview for mempaper
#
# Installed by install.sh as a symlink:
#   /etc/profile.d/mempaper-motd.sh
#
# This file is sourced by bash for interactive login shells.
# Do NOT use 'set -e' — an error would exit the user's login shell.

# Only run for interactive SSH sessions; skip scripts and non-login shells.
case "$-" in *i*) ;; *) return 0 2>/dev/null; exit 0 ;; esac
[ -n "${SSH_CONNECTION:-}${SSH_TTY:-}" ] || return 0

PROJECT_DIR="/home/mempaper/btc-mempaper"
CONFIG_FILE="${PROJECT_DIR}/config/config.json"
MEMES_DIR="${PROJECT_DIR}/static/memes"

# ── Colour codes ──────────────────────────────────────────────────────────────
_B='\033[1m'   _R='\033[0m'   _D='\033[2m'
_O='\033[38;5;214m'   _G='\033[32m'   _RE='\033[31m'   _Y='\033[33m'
_W='\033[1;97m'

# ── Config (one Python call for all fields) ───────────────────────────────────
MEMPOOL_HOST="mempool.space"
MEMPOOL_PORT="443"
DISP_ON="false"
DEVICE_NAME="none"

if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    _raw=$(python3 - <<PYEOF 2>/dev/null
import json, sys
try:
    with open('${CONFIG_FILE}') as f:
        c = json.load(f)
    print(c.get('mempool_api_host', 'mempool.space'))
    print(c.get('mempool_api_port', 443))
    print(str(c.get('e-ink-display-connected', False)).lower())
    print(c.get('omni_device_name', 'none'))
except Exception:
    print('mempool.space'); print('443'); print('false'); print('none')
PYEOF
)
    MEMPOOL_HOST=$(printf '%s' "$_raw" | sed -n '1p')
    MEMPOOL_PORT=$(printf '%s' "$_raw" | sed -n '2p')
    DISP_ON=$(printf '%s' "$_raw"       | sed -n '3p')
    DEVICE_NAME=$(printf '%s' "$_raw"   | sed -n '4p')
fi

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
printf '%b\n\n' "  ${_D}Bitcoin Block Clock  ·  github.com/satcat21/btc-mempaper${_R}"

_SEP="────────────────────────────────────────────────────────────────"
printf ' %b\n' "${_B}${_SEP}${_R}"

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

# Memory
_MU=$(free -m 2>/dev/null | awk '/^Mem:/{print $3}')
_MT=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
: "${_MU:=0}" "${_MT:=1}"
_MP=$(( _MU * 100 / _MT ))

# Disk (root filesystem)
_DU=$(df -h / 2>/dev/null | awk 'NR==2{print $3}')
_DT=$(df -h / 2>/dev/null | awk 'NR==2{print $2}')
_DP=$(df    / 2>/dev/null | awk 'NR==2{gsub(/%/,"");print $5}')
if   [ "${_DP:-0}" -ge 85 ]; then _DC="${_RE}"
elif [ "${_DP:-0}" -ge 70 ]; then _DC="${_Y}"
else                              _DC="${_G}"
fi

# Load averages
_LD=$(uptime 2>/dev/null | awk -F'load average:' '{print $2}' | xargs)

# Print system rows (no colour in value strings — printf width works correctly)
printf "  %-9s ${_TC}%-27s${_R} %-9s %s\n" \
    "temp"   "${_T}°C"                         "uptime"  "${_UP}"
printf "  %-9s ${_DC}%-27s${_R} %-9s %s\n" \
    "disk"   "${_DU:-?}/${_DT:-?} (${_DP:-?}%)" "memory"  "${_MU}/${_MT} MB (${_MP}%)"
printf "  %-9s %s\n" \
    "load"   "${_LD}"

printf ' %b\n' "${_B}${_SEP}${_R}"

# ── mempaper stats ────────────────────────────────────────────────────────────

# Service status
_SVC=$(systemctl is-active mempaper.service 2>/dev/null || echo unknown)
if [ "$_SVC" = "active" ]; then _SD="${_G}"; _SL="running"
else                            _SD="${_RE}"; _SL="${_SVC}"
fi

# Meme count
_MC=0
if [ -d "$MEMES_DIR" ]; then
    _MC=$(find "$MEMES_DIR" -maxdepth 1 -type f \
        \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
           -o -iname '*.gif' -o -iname '*.webp' \) 2>/dev/null | wc -l | tr -d ' ')
fi

# Mempool URL
if [ "${MEMPOOL_PORT}" = "443" ]; then
    _MURL="https://${MEMPOOL_HOST}"
else
    _MURL="http://${MEMPOOL_HOST}:${MEMPOOL_PORT}"
fi

# Block height — query mempool (4 s timeout)
_BH="—"
_MD="${_RE}"
_TIP=$(curl -sf --max-time 4 "${_MURL}/api/blocks/tip/height" 2>/dev/null || true)
if printf '%s' "${_TIP}" | grep -qE '^[0-9]+$' 2>/dev/null; then
    _BH=$(python3 -c "print(f'{int(${_TIP}):,}')" 2>/dev/null || echo "${_TIP}")
    _MD="${_G}"
    _ML="${MEMPOOL_HOST}"
else
    _ML="${MEMPOOL_HOST} (offline)"
fi

# Display label
if [ "$DISP_ON" = "true" ] || [ "$DISP_ON" = "True" ]; then
    _DL="${DEVICE_NAME} (enabled)"
else
    _DL="disabled"
fi

# ── Print mempaper rows ───────────────────────────────────────────────────────
# Coloured-dot rows: label(9) + dot(1 vis.) + space + value(26) + label(9) + value
# The %-26s is applied to the plain-text value *after* the dot — alignment holds.
_COL=26

printf "  %-9s %b● %b%-${_COL}s %b%-9s %s\n" \
    "service"  "${_SD}" "${_R}" "${_SL}"  "${_R}" "block"  "${_BH}"

printf "  %-9s %b● %b%-${_COL}s %b%-9s %s files\n" \
    "mempool"  "${_MD}" "${_R}" "${_ML}"  "${_R}" "memes"  "${_MC}"

printf "  %-9s   %-${_COL}s\n" \
    "display"  "${_DL}"

printf ' %b\n\n' "${_B}${_SEP}${_R}"
