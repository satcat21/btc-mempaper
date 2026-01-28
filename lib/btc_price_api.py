"""
Bitcoin Price API Module

Handles fetching Bitcoin price data and Moscow time calculations.
Based on the reference implementation from image_renderer.py.

"""

import requests
from typing import Dict, Optional, Union


class BitcoinPriceAPI:
    """API client for Bitcoin price data and Moscow time calculations."""
    
    def __init__(self, config: Dict = None):
        """
        Initialize Bitcoin Price API client.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config or {}
        self.base_url = self._build_base_url()
        self.mempool_verify_ssl = self.config.get("mempool_verify_ssl", True)
    
    def _build_base_url(self) -> str:
        """Build the base URL for price API from configuration with unified host field and HTTPS support."""
        mempool_host = self.config.get("mempool_host", "127.0.0.1")
        mempool_rest_port = self.config.get("mempool_rest_port", "8080")
        mempool_use_https = self.config.get("mempool_use_https", False)
        
        # Build URL with proper protocol
        protocol = "https" if mempool_use_https else "http"
        
        # Don't include port in URL if using standard ports with domain/hostname
        if (mempool_use_https and mempool_rest_port in ["443", "80"]) or \
           (not mempool_use_https and mempool_rest_port in ["80", "443"]):
            return f"{protocol}://{mempool_host}/api"
        else:
            return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
    
    def fetch_btc_price(self) -> Optional[Dict[str, Union[str, float, int]]]:
        """
        Fetch Bitcoin price data with Moscow time calculation.
        
        Returns:
            Dict containing:
            - usd_price: Current USD price
            - moscow_time: 1 USD in sats (moscow time)
            - currency: Selected currency
            - currency_price: Price in selected currency (if not USD)
            - error: Error message if fetch failed
        """
        try:
            # Get Bitcoin price in USD
            # print(f"🌐 Fetching price data from: {self.base_url}/v1/prices")
            response = requests.get(f"{self.base_url}/v1/prices", timeout=10, verify=self.mempool_verify_ssl)
            response.raise_for_status()
            price_data = response.json()
            # print(f"✅ Successfully fetched price data from configured mempool instance")
            
            # Get configured currency
            selected_currency = self.config.get("btc_price_currency", "USD")

            price_in_selected_currency = price_data.get(selected_currency, 0)
            if not price_in_selected_currency:
                return {"error": f"Unable to fetch {selected_currency} price"}

            usd_price = price_data.get("USD", 0)
            if not usd_price:
                return {"error": "Unable to fetch USD price"}
            
            # Calculate Moscow time (1 USD in sats)
            moscow_time = int(100_000_000 / price_in_selected_currency) if price_in_selected_currency > 0 else 0
            
            result = {
                "usd_price": usd_price,
                "price_in_selected_currency": price_in_selected_currency,
                "moscow_time": moscow_time,
                "currency": selected_currency
            }
            
            return result
            
        except requests.RequestException as e:
            return {"error": f"Network error: {e}"}
        except Exception as e:
            return {"error": f"Failed to fetch Bitcoin price: {e}"}
    
    def get_formatted_price(self, price_data: Dict, precision: int = 0) -> str:
        """
        Format price data for display.
        
        Args:
            price_data: Price data from fetch_btc_price()
            precision: Decimal places for price display
            
        Returns:
            Formatted price string
        """
        if price_data.get("error"):
            return "Price unavailable"
        
        currency = price_data.get("currency", "USD")
        price = price_data.get("price_in_selected_currency", 0)
        
        if currency == "USD":
            symbol = "$"
        elif currency == "EUR":
            symbol = "€"
        elif currency == "GBP":
            symbol = "£"
        else:
            symbol = currency + " "
        
        return f"{symbol}{price:,.{precision}f}"
    
    def get_formatted_moscow_time(self, price_data: Dict) -> str:
        """
        Format Moscow time for display.
        
        Args:
            price_data: Price data from fetch_btc_price()
            
        Returns:
            Formatted Moscow time string
        """
        if price_data.get("error"):
            return "N/A"
        
        moscow_time = price_data.get("moscow_time", 0)
        return f"{moscow_time:,} sats"
