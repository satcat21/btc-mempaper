#!/usr/bin/env python3
"""
Local Mempool Configuration Manager
Validates local mempool instance connectivity and configuration.
"""

import requests
import socket
from typing import Dict, List, Optional

class LocalMempoolManager:
    """Manages local mempool instance validation and connectivity."""
    
    def __init__(self):
        """Initialize local mempool manager."""
        pass
    
    def is_local_ip(self, ip: str) -> bool:
        """Check if IP address is in private/local ranges."""
        try:
            # Try to resolve hostname to IP
            if not ip.replace('.', '').isdigit():
                ip = socket.gethostbyname(ip)
            
            # Private IP ranges
            private_ranges = [
                ('10.0.0.0', '10.255.255.255'),
                ('172.16.0.0', '172.31.255.255'),
                ('192.168.0.0', '192.168.255.255'),
                ('127.0.0.0', '127.255.255.255'),  # Localhost
                ('169.254.0.0', '169.254.255.255')  # Link-local
            ]
            
            ip_parts = [int(x) for x in ip.split('.')]
            ip_int = (ip_parts[0] << 24) + (ip_parts[1] << 16) + (ip_parts[2] << 8) + ip_parts[3]
            
            for start_ip, end_ip in private_ranges:
                start_parts = [int(x) for x in start_ip.split('.')]
                end_parts = [int(x) for x in end_ip.split('.')]
                
                start_int = (start_parts[0] << 24) + (start_parts[1] << 16) + (start_parts[2] << 8) + start_parts[3]
                end_int = (end_parts[0] << 24) + (end_parts[1] << 16) + (end_parts[2] << 8) + end_parts[3]
                
                if start_int <= ip_int <= end_int:
                    return True
            
            return False
            
        except Exception:
            # If we can't resolve, assume it's external
            return False
    
    def validate_local_mempool(self, mempool_host: str, mempool_port: int) -> Dict:
        """
        Validate connection to local mempool instance.
        
        Args:
            mempool_host: Mempool host (IP address or domain name)
            mempool_port: Mempool port
            
        Returns:
            Validation result dictionary
        """
        # Build API URL
        base_url = f"https://{mempool_host}:{mempool_port}/api"
        
        result = {
            "is_local": self.is_local_ip(mempool_host),
            "is_reachable": False,
            "is_valid_mempool": False,
            "base_url": base_url,
            "error": None,
            "response_time": None
        }
        
        try:
            # Test connection
            import time
            start_time = time.time()
            
            response = requests.get(f"{base_url}/blocks/tip/height", timeout=10, verify=False)
            response_time = time.time() - start_time
            
            result["response_time"] = round(response_time * 1000, 2)  # ms
            result["is_reachable"] = True
            
            if response.status_code == 200:
                # Validate it's actually a mempool API
                try:
                    height = int(response.text)
                    if height > 0:
                        result["is_valid_mempool"] = True
                    else:
                        result["error"] = "Invalid block height response"
                except ValueError:
                    result["error"] = "Non-numeric block height response"
            else:
                result["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
                
        except requests.exceptions.Timeout:
            result["error"] = "Connection timeout (>10s)"
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection refused - service not reachable"
        except Exception as e:
            result["error"] = f"Connection error: {str(e)}"
        
        return result
    
    def get_mempool_status(self, config: Dict) -> Dict:
        """
        Get comprehensive mempool configuration status.
        
        Args:
            config: Current configuration
            
        Returns:
            Dictionary with mempool status and recommendations
        """
        mempool_host = config.get("mempool_host", "127.0.0.1")
        mempool_port = config.get("mempool_rest_port", 4081)
        
        # Validate mempool connection
        validation = self.validate_local_mempool(mempool_host, mempool_port)
        
        # Generate simple status
        if validation["is_reachable"] and validation["is_valid_mempool"]:
            if validation["is_local"]:
                status = "OPTIMAL"
                message = "✅ Local mempool instance working perfectly"
            else:
                status = "WARNING"
                message = "⚠️ Mempool instance is not on local network"
        elif validation["is_reachable"]:
            status = "ERROR"
            message = f"❌ Invalid mempool API: {validation['error']}"
        else:
            status = "ERROR" 
            message = f"❌ Cannot connect to mempool: {validation['error']}"
        
        return {
            "validation": validation,
            "status": status,
            "message": message,
            "response_time_ms": validation.get("response_time"),
            "base_url": validation["base_url"]
        }

# Global instance
mempool_manager = LocalMempoolManager()
