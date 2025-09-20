"""
Mempool API Integration Module

This module handles all interactions with the Bitcoin mempool API including:
- Block height and hash retrieval
- REST API communication
- Error handling and fallbacks
"""

import requests


class MempoolAPI:
    """Handles communication with Bitcoin mempool API."""
    
    def __init__(self, ip="127.0.0.1", rest_port="4081"):
        """
        Initialize Mempool API client.
        
        Args:
            ip (str): IP address of the mempool instance
            rest_port (str): REST API port
        """
        self.ip = ip
        self.rest_port = rest_port
        self.base_url = f"https://{ip}:{rest_port}/api"
        
        # Fallback values for when API is unavailable
        self.fallback_data = {
            "block_height": "0",
            "block_hash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
        }
    
    def get_tip_height(self):
        """
        Get the current blockchain tip height.
        
        Returns:
            str: Block height as string
        """
        try:
            url = f"{self.base_url}/blocks/tip/height"
            response = requests.get(url, timeout=5, verify=False)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            print(f"Error fetching block height: {e}")
            return self.fallback_data["block_height"]
    
    def get_tip_hash(self):
        """
        Get the current blockchain tip hash.
        
        Returns:
            str: Block hash as string
        """
        try:
            url = f"{self.base_url}/blocks/tip/hash"
            response = requests.get(url, timeout=5, verify=False)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            print(f"Error fetching block hash: {e}")
            return self.fallback_data["block_hash"]
    
    def get_current_block_info(self):
        """
        Get both current block height and hash.
        
        Returns:
            dict: Dictionary containing 'block_height' and 'block_hash'
        """
        try:
            height = self.get_tip_height()
            block_hash = self.get_tip_hash()
            
            # Format hash for display: first 6 + last 6 characters with grouping
            hash_first = block_hash[:6]
            hash_last = block_hash[-6:]
            # Group characters in pairs
            hash_first_grouped = ' '.join([hash_first[i:i+2] for i in range(0, len(hash_first), 2)])
            hash_last_grouped = ' '.join([hash_last[i:i+2] for i in range(0, len(hash_last), 2)])
            hash_display = f"{hash_first_grouped} ... {hash_last_grouped}"
            
            print(f"Current block - Height: {height}, Hash: {hash_display}")
            
            return {
                "block_height": height,
                "block_hash": block_hash
            }
        except Exception as e:
            print(f"Error getting block info, using fallback: {e}")
            return self.fallback_data.copy()
    
    def format_block_height(self, raw_height):
        """
        Format block height for display (add thousand separators).
        
        Args:
            raw_height (str): Raw block height string
            
        Returns:
            str: Formatted block height
        """
        try:
            height_int = int(raw_height)
            return f"{height_int:,}".replace(",", ".")
        except (ValueError, TypeError):
            return str(raw_height)
    
    def shorten_hash(self, full_hash):
        """
        Create a shortened, formatted version of a block hash for display.
        
        Args:
            full_hash (str): Full block hash
            
        Returns:
            str: Shortened and formatted hash with byte grouping
        """
        start_part = full_hash[:24]
        end_part = full_hash[-6:]
        
        def group_bytes(s):
            """Group string into byte pairs separated by spaces."""
            return " ".join(s[i:i+2] for i in range(0, len(s), 2))
        
        return f"{group_bytes(start_part)} ... {group_bytes(end_part)}"
    
    def get_fee_recommendations(self):
        """
        Get current fee recommendations from mempool API.
        
        Returns:
            dict: Fee recommendations or None if failed
        """
        try:
            url = f"{self.base_url}/v1/fees/recommended"
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching fee recommendations: {e}")
            return None
    
    def get_minimum_fee(self):
        """
        Get the current minimum fee from fee recommendations.
        
        Returns:
            int: Minimum fee in sat/vB or None if failed
        """
        fees = self.get_fee_recommendations()
        if fees:
            return fees.get("minimumFee", 1)
        return None
    
    def get_configured_fee(self, fee_parameter="minimumFee"):
        """
        Get the fee value for the specified parameter.
        
        Args:
            fee_parameter (str): Which fee parameter to use (fastestFee, halfHourFee, hourFee, economyFee, minimumFee)
        
        Returns:
            int: Fee in sat/vB or None if failed
        """
        fees = self.get_fee_recommendations()
        if fees:
            fee_value = fees.get(fee_parameter, 1)
            print(f"📊 Fee info: {fee_value} sat/vB ({fee_parameter})")
            return fee_value
        return None
