"""
Bitaxe Miner API Module

Handles fetching hashrate data from Bitaxe miners and integrating with 
block reward monitoring for valid blocks count.
Based on fetch_bitaxe_hashrate.py reference implementation.

"""

import ipaddress
import requests
from typing import Dict, List, Optional, Union


def parse_miner_address(raw) -> Optional[str]:
    """Validate a Bitaxe address and return a safe "host" / "host:port", else None.

    A miner address is interpolated straight into a request URL, and it reaches
    that URL from two directions: the miner table in config, and the request path
    of /api/bitaxe/<ip>/best-diff. Neither validated it, so any string - another
    host, a port on localhost, a full URL with its own path and query - became
    the request target (SSRF).

    Only a literal IPv4/IPv6 address with an optional port is accepted, so a
    scheme, path, query, credentials or hostname can never reach the URL.
    Loopback, link-local (169.254.169.254 is the cloud metadata address),
    multicast, reserved and unspecified addresses are rejected as well: they are
    the usual SSRF pivots and are never a real miner. Private ranges stay allowed
    because that is exactly where a Bitaxe lives.
    """
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None

    host, port = value, None
    if value.startswith('['):
        # Bracketed IPv6, optionally [addr]:port
        end = value.find(']')
        if end == -1:
            return None
        host, rest = value[1:end], value[end + 1:]
        if rest:
            if not rest.startswith(':'):
                return None
            port = rest[1:]
    elif value.count(':') == 1:
        # Exactly one colon means host:port; a bare IPv6 literal has several
        host, port = value.split(':', 1)

    if port is not None and not (port.isdigit() and 1 <= int(port) <= 65535):
        return None

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None

    if (addr.is_loopback or addr.is_link_local or addr.is_multicast
            or addr.is_unspecified or addr.is_reserved):
        return None

    netloc = f'[{addr.compressed}]' if addr.version == 6 else addr.compressed
    return f'{netloc}:{port}' if port else netloc


def _parse_diff_value(raw) -> float:
    """Parse a difficulty value that may be numeric or a suffixed string (e.g. '156M')."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 0.0
        suffixes = {'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12, 'P': 1e15}
        if raw[-1] in suffixes:
            try:
                return float(raw[:-1]) * suffixes[raw[-1]]
            except ValueError:
                return 0.0
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return 0.0


class BitaxeAPI:
    """API client for Bitaxe miner monitoring and hashrate aggregation."""

    # Class-level cache: persists across ImageRenderer re-instantiations.
    # Keyed by miner IP; stores last known best_diff when the device was online.
    _best_diff_cache: Dict[str, float] = {}

    def __init__(self, config: Dict = None):
        """
        Initialize Bitaxe API client.

        Args:
            config: Application configuration dictionary
        """
        self.config = config or {}

        # Load miner configuration from table format
        bitaxe_table = self.config.get("bitaxe_miner_table", [])
        self.miner_ips = [entry.get("address", "").strip() for entry in bitaxe_table
                        if isinstance(entry, dict) and entry.get("address", "").strip()]
        self.miner_comments = {entry.get("address", "").strip(): entry.get("comment", "Bitaxe Miner")
                             for entry in bitaxe_table
                             if isinstance(entry, dict) and entry.get("address", "").strip()}

        # Remove cached entries for IPs no longer in the miner table
        active = set(self.miner_ips)
        for ip in list(BitaxeAPI._best_diff_cache.keys()):
            if ip not in active:
                del BitaxeAPI._best_diff_cache[ip]
    
    def get_miner_info(self, ip: str, timeout: int = 5) -> Dict:
        """
        Get detailed info from a single Bitaxe miner.
        
        Args:
            ip: IP address of the miner
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary with miner information
        """
        target = parse_miner_address(ip)
        if target is None:
            print(f"⚠️ Rejected invalid Bitaxe address: {ip!r}")
            return {
                "ip": ip, "hashrate_ghs": 0, "power": 0, "temp": 0,
                "fan_speed": 0, "frequency": 0, "voltage": 0, "best_diff": 0,
                "online": False, "error": "invalid miner address",
            }

        try:
            # allow_redirects=False: a redirect would let the miner point the
            # request back at a host this validation just excluded.
            response = requests.get(f"http://{target}/api/system/info",
                                    timeout=timeout, allow_redirects=False)
            response.raise_for_status()
            data = response.json()

            best_diff = _parse_diff_value(data.get("bestDiff") or data.get("bestSessionDiff", 0))
            if best_diff > 0:
                BitaxeAPI._best_diff_cache[ip] = best_diff

            # Prefer a time-averaged hashrate over the instantaneous value.
            # AxOS exposes different field names depending on firmware version.
            hashrate_avg_ghs = None
            hashrate_avg_label = None
            for field, label in (
                ("hashRate_5min", "5m avg"), ("hashRate_5m", "5m avg"),
                ("hashRate_10min", "10m avg"), ("hashRate_10m", "10m avg"),
                ("hashRate_15min", "15m avg"), ("hashRate_15m", "15m avg"),
                ("avgHashRate", "avg"),
            ):
                val = data.get(field)
                if val is not None and float(val) > 0:
                    hashrate_avg_ghs = float(val)
                    hashrate_avg_label = label
                    break
            if hashrate_avg_ghs is None:
                hashrate_avg_ghs = float(data.get("hashRate", 0))
                hashrate_avg_label = "current"

            return {
                "ip": ip,
                "hashrate_ghs": data.get("hashRate", 0),
                "hashrate_avg_ghs": hashrate_avg_ghs,
                "hashrate_avg_label": hashrate_avg_label,
                "power": data.get("power", 0),
                "temp": data.get("temp", 0),
                "fan_speed": data.get("fanSpeed", 0),
                "frequency": data.get("frequency", 0),
                "voltage": data.get("voltage", 0),
                "best_diff": best_diff,
                "online": True
            }
        except Exception as e:
            print(f"⚠️ Error fetching info from {ip}: {e}")
            return {
                "ip": ip,
                "hashrate_ghs": 0,
                "power": 0,
                "temp": 0,
                "fan_speed": 0,
                "frequency": 0,
                "voltage": 0,
                "best_diff": BitaxeAPI._best_diff_cache.get(ip, 0),
                "online": False,
                "error": str(e)
            }
    
    def fetch_bitaxe_stats(self) -> Optional[Dict[str, Union[str, float, int, List]]]:
        """
        Fetch comprehensive statistics from all configured Bitaxe miners.
        
        Returns:
            Dict containing:
            - total_hashrate_ghs: Total hashrate in GH/s
            - total_hashrate_ths: Total hashrate in TH/s
            - miners_online: Number of online miners
            - miners_total: Total number of configured miners
            - miners: List of individual miner stats
            - valid_blocks: Count of valid blocks found (from block monitor)
            - error: Error message if fetch failed
        """
        if not self.miner_ips:
            return {"error": "No Bitaxe miner IPs configured"}
        
        try:
            miners = []
            total_hashrate_ghs = 0
            miners_online = 0
            max_best_difficulty = 0.0
            
            # Fetch stats from each miner
            for ip in self.miner_ips:
                miner_info = self.get_miner_info(ip)
                miners.append(miner_info)
                
                if miner_info["online"]:
                    miners_online += 1
                    total_hashrate_ghs += miner_info["hashrate_ghs"]
                    current_diff = float(miner_info.get("best_diff", 0))
                    if current_diff > max_best_difficulty:
                        max_best_difficulty = current_diff
            
            # Convert to TH/s
            total_hashrate_ths = total_hashrate_ghs / 1000
            
            # Get valid blocks count from block monitor
            valid_blocks = self._get_valid_blocks_count()
            
            return {
                "total_hashrate_ghs": total_hashrate_ghs,
                "total_hashrate_ths": total_hashrate_ths,
                "miners_online": miners_online,
                "miners_total": len(self.miner_ips),
                "miners": miners,
                "valid_blocks": valid_blocks,
                "best_difficulty": max_best_difficulty
            }
            
        except Exception as e:
            return {"error": f"Failed to fetch Bitaxe stats: {e}"}
    
    def _get_valid_blocks_count(self) -> int:
        """
        Get valid blocks count from the block monitor.
        
        Returns:
            Number of valid blocks found, 0 if not available
        """
        try:
            from lib.block_monitor import get_block_monitor
            monitor = get_block_monitor()
            if monitor:
                return monitor.get_valid_blocks_count()
        except Exception as e:
            print(f"⚠️ Could not get valid blocks count: {e}")
        return 0
