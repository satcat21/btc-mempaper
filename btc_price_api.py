"""
Bitcoin Price API Module

Handles fetching Bitcoin price data and Moscow time calculations.
Based on the reference implementation from image_renderer.py.

"""

import requests
from datetime import datetime
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
        self.base_url = "https://mempool.space/api"
    
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
            response = requests.get(f"{self.base_url}/v1/prices", timeout=10)
            response.raise_for_status()
            price_data = response.json()
            
            # Get configured currency
            selected_currency = self.config.get("btc_price_currency", "USD")

            price_in_selected_currency = price_data.get(selected_currency, 0)
            if not price_in_selected_currency:
                return {"error": f"Unable to fetch {selected_currency} price"}

            usd_price = price_data.get(selected_currency, 0)
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
