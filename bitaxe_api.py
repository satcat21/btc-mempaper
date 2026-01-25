"""
Bitaxe Miner API Module

Handles fetching hashrate data from Bitaxe miners and integrating with 
block reward monitoring for valid blocks count.
Based on fetch_bitaxe_hashrate.py reference implementation.

"""

import requests
from typing import Dict, List, Optional, Union


class BitaxeAPI:
    """API client for Bitaxe miner monitoring and hashrate aggregation."""
    
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
    
    def get_miner_hashrate(self, ip: str, timeout: int = 5) -> float:
        """
        Get hashrate from a single Bitaxe miner.
        
        Args:
            ip: IP address of the miner
            timeout: Request timeout in seconds
            
        Returns:
            Hashrate in GH/s, 0 if error
        """
        try:
            response = requests.get(f"http://{ip}/api/system/info", timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("hashRate", 0)
        except Exception as e:
            print(f"⚠️ Error fetching hashrate from {ip}: {e}")
            return 0
    
    def get_miner_info(self, ip: str, timeout: int = 5) -> Dict:
        """
        Get detailed info from a single Bitaxe miner.
        
        Args:
            ip: IP address of the miner
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary with miner information
        """
        try:
            response = requests.get(f"http://{ip}/api/system/info", timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            return {
                "ip": ip,
                "hashrate_ghs": data.get("hashRate", 0),
                "power": data.get("power", 0),
                "temp": data.get("temp", 0),
                "fan_speed": data.get("fanSpeed", 0),
                "frequency": data.get("frequency", 0),
                "voltage": data.get("voltage", 0),
                "best_diff": data.get("bestDiff", 0),
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
                "best_diff": 0,
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
            from block_monitor import get_block_monitor
            monitor = get_block_monitor()
            if monitor:
                return monitor.get_valid_blocks_count()
        except Exception as e:
            print(f"⚠️ Could not get valid blocks count: {e}")
        return 0
    
    def get_formatted_hashrate(self, stats: Dict) -> str:
        """
        Format hashrate for display.
        
        Args:
            stats: Stats data from fetch_bitaxe_stats()
            
        Returns:
            Formatted hashrate string
        """
        if stats.get("error"):
            return "Hashrate unavailable"
        
        ths = stats.get("total_hashrate_ths", 0)
        return f"{ths:.2f} TH/s"
    
    def get_formatted_miners_status(self, stats: Dict) -> str:
        """
        Format miners status for display.
        
        Args:
            stats: Stats data from fetch_bitaxe_stats()
            
        Returns:
            Formatted miners status string
        """
        if stats.get("error"):
            return "Status unavailable"
        
        online = stats.get("miners_online", 0)
        total = stats.get("miners_total", 0)
        return f"{online}/{total} online"
    
    def get_formatted_valid_blocks(self, stats: Dict) -> str:
        """
        Format valid blocks count for display.
        
        Args:
            stats: Stats data from fetch_bitaxe_stats()
            
        Returns:
            Formatted valid blocks string
        """
        if stats.get("error"):
            return "N/A"
        
        blocks = stats.get("valid_blocks", 0)
        return f"{blocks} blocks"
