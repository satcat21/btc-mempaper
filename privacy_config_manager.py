#!/usr/bin/env python3
"""
Privacy Configuration Manager
Ensures privacy by preventing fallbacks to public services and validating local instances.
"""

import requests
import socket
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse

class PrivacyConfigurationManager:
    """Manages privacy-focused configuration validation and enforcement."""
    
    def __init__(self):
        """Initialize privacy configuration manager."""
        # Public mempool instances to block
        self.public_mempool_instances = [
            "mempool.space",
            "blockstream.info",
            "api.blockchair.com"
        ]
        
        # Privacy-sensitive features that require local mempool
        self.privacy_features = {
            "wallet_balances": ["show_wallet_balances_block", "wallet_balance_addresses"],
            "block_rewards": ["block_reward_addresses_table"],
            "bitaxe": ["show_bitaxe_block", "bitaxe_miner_table"]
        }
    
    def is_public_mempool_instance(self, mempool_ip: str, mempool_port: int) -> bool:
        """
        Check if the configured mempool instance is a public one.
        
        Args:
            mempool_ip: Mempool IP address or domain
            mempool_port: Mempool port
            
        Returns:
            True if it's a public instance, False if local/private
        """
        # Check if it's a known public instance
        if mempool_ip in self.public_mempool_instances:
            return True
        
        # Check if it's using standard HTTPS port (likely public)
        if mempool_port == 443 and not self._is_local_ip(mempool_ip):
            return True
        
        return False
    
    def _is_local_ip(self, ip: str) -> bool:
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
    
    def validate_mempool_connection(self, mempool_ip: str, mempool_port: int) -> Dict:
        """
        Validate connection to mempool instance.
        
        Args:
            mempool_ip: Mempool IP address or domain
            mempool_port: Mempool port
            
        Returns:
            Validation result dictionary
        """
        is_public = self.is_public_mempool_instance(mempool_ip, mempool_port)
        
        # Build API URL
        base_url = f"https://{mempool_ip}:{mempool_port}/api"
        
        result = {
            "is_public": is_public,
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
            
            response = requests.get(f"{base_url}/blocks/tip/height", timeout=5)
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
            result["error"] = "Connection timeout (>5s)"
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection refused - service not reachable"
        except Exception as e:
            result["error"] = f"Connection error: {str(e)}"
        
        return result
    
    def get_privacy_violations(self, config: Dict) -> List[Dict]:
        """
        Get list of privacy violations in current configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            List of privacy violation dictionaries
        """
        violations = []
        
        mempool_ip = config.get("mempool_ip", "")
        mempool_port = config.get("mempool_rest_port", 443)
        
        is_public = self.is_public_mempool_instance(mempool_ip, mempool_port)
        
        if is_public:
            # Check which privacy-sensitive features are enabled
            for feature_category, feature_keys in self.privacy_features.items():
                enabled_features = []
                
                for key in feature_keys:
                    if key.startswith("show_") and config.get(key, False):
                        enabled_features.append(key)
                    elif not key.startswith("show_") and config.get(key):
                        # Non-boolean settings (like addresses, IPs)
                        value = config.get(key)
                        if isinstance(value, list) and value:
                            enabled_features.append(key)
                        elif isinstance(value, str) and value.strip():
                            enabled_features.append(key)
                        elif isinstance(value, (int, float)) and value > 0:
                            enabled_features.append(key)
                
                if enabled_features:
                    violations.append({
                        "category": feature_category,
                        "severity": "HIGH",
                        "message": f"Privacy risk: {feature_category} enabled with public mempool",
                        "enabled_features": enabled_features,
                        "recommendation": f"Disable {feature_category} features or use local mempool instance"
                    })
        
        return violations
    
    def get_disabled_features_for_block(self, block_type: str, config: Dict) -> List[str]:
        """
        Get list of features that should be disabled when a block is disabled.
        
        Args:
            block_type: Type of block (btc_price, bitaxe, wallet_balances, display)
            config: Current configuration
            
        Returns:
            List of feature keys that should be disabled
        """
        disabled_features = []
        
        if block_type == "btc_price" and not config.get("show_btc_price_block", True):
            disabled_features.extend([
                "btc_price_currency",
                "moscow_time_unit", 
                "btc_price_color",
                "moscow_time_color"
            ])
        
        elif block_type == "bitaxe" and not config.get("show_bitaxe_block", True):
            disabled_features.extend([
                "bitaxe_miner_table",
                "hashrate_color",
                "found_blocks_color"
            ])
        
        elif block_type == "wallet_balances" and not config.get("show_wallet_balances_block", True):
            disabled_features.extend([
                "wallet_balance_addresses",
                "wallet_balance_unit",
                "wallet_balance_currency",
                "xpub_derivation_count",
                "info_block_balance_color",
                "info_block_fiat_value_color"
            ])
        
        elif block_type == "display" and not config.get("e-ink-display-connected", True):
            disabled_features.extend([
                "omni_device_name",
                "display_width",
                "display_height",
                "display_orientation"
            ])
        
        return disabled_features
    
    def get_configuration_recommendations(self, config: Dict) -> Dict:
        """
        Get comprehensive configuration recommendations for privacy and functionality.
        
        Args:
            config: Current configuration
            
        Returns:
            Dictionary with recommendations and status
        """
        mempool_ip = config.get("mempool_ip", "")
        mempool_port = config.get("mempool_rest_port", 443)
        
        # Validate mempool connection
        mempool_validation = self.validate_mempool_connection(mempool_ip, mempool_port)
        
        # Get privacy violations
        privacy_violations = self.get_privacy_violations(config)
        
        # Get disabled features for each block type
        disabled_features = {}
        for block_type in ["btc_price", "bitaxe", "wallet_balances", "display"]:
            disabled_features[block_type] = self.get_disabled_features_for_block(block_type, config)
        
        # Calculate privacy score
        privacy_score = 100
        if mempool_validation["is_public"]:
            privacy_score -= 30
        if privacy_violations:
            privacy_score -= len(privacy_violations) * 20
        privacy_score = max(0, privacy_score)
        
        return {
            "mempool_validation": mempool_validation,
            "privacy_violations": privacy_violations,
            "disabled_features": disabled_features,
            "privacy_score": privacy_score,
            "recommendations": self._generate_recommendations(mempool_validation, privacy_violations),
            "status": self._get_overall_status(mempool_validation, privacy_violations)
        }
    
    def _generate_recommendations(self, mempool_validation: Dict, privacy_violations: List[Dict]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        if mempool_validation["is_public"]:
            recommendations.append("🔒 Use a local mempool instance for better privacy")
            recommendations.append("💡 Configure a local Bitcoin node with mempool backend")
        
        if not mempool_validation["is_reachable"]:
            recommendations.append("🔧 Fix mempool connection issues")
            recommendations.append(f"❌ Error: {mempool_validation['error']}")
        
        if privacy_violations:
            recommendations.append("⚠️ Disable privacy-sensitive features or use local mempool")
            for violation in privacy_violations:
                recommendations.append(f"   • {violation['recommendation']}")
        
        if not privacy_violations and mempool_validation["is_reachable"] and not mempool_validation["is_public"]:
            recommendations.append("✅ Configuration is privacy-optimal")
        
        return recommendations
    
    def _get_overall_status(self, mempool_validation: Dict, privacy_violations: List[Dict]) -> str:
        """Get overall configuration status."""
        if not mempool_validation["is_reachable"]:
            return "ERROR"
        elif privacy_violations:
            return "PRIVACY_RISK"
        elif mempool_validation["is_public"]:
            return "PUBLIC_MEMPOOL"
        else:
            return "OPTIMAL"

# Global instance
privacy_manager = PrivacyConfigurationManager()
