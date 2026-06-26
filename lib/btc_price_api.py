"""
Bitcoin Price API Module

Handles fetching Bitcoin price data and Moscow time calculations.
Based on the reference implementation from image_renderer.py.

"""

import requests
import time
from typing import Dict, Optional, Union
from utils.technical_config import build_mempool_api_url


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
        
        # Price caching to prevent duplicate API calls
        self._price_cache = None
        self._price_cache_timestamp = 0
        self._price_cache_ttl = 300  # 5-minute cache TTL
        # Raw multi-currency cache — stores the full /v1/prices response
        self._raw_prices: dict = {}
        self._raw_prices_timestamp: float = 0
    
    def _build_base_url(self) -> str:
        """Build the base URL for price API from configuration."""
        return build_mempool_api_url(
            self.config.get("mempool_host", "127.0.0.1"),
            self.config.get("mempool_rest_port", "8080"),
            self.config.get("mempool_use_https", False)
        )
    
    def _build_result(self, raw_prices: dict, currency: str) -> Dict:
        """Build a price result dict from the raw /v1/prices response for a given currency."""
        price = raw_prices.get(currency, 0)
        if not price:
            return {"error": f"Currency {currency} not available in price data"}
        usd_price = raw_prices.get("USD", 0)
        moscow_time = int(100_000_000 / price) if price > 0 else 0
        return {
            "usd_price": usd_price,
            "price_in_selected_currency": price,
            "moscow_time": moscow_time,
            "currency": currency,
            "all_prices": raw_prices,
        }

    def fetch_btc_price(self, override_currency: str = None) -> Optional[Dict[str, Union[str, float, int]]]:
        """
        Fetch Bitcoin price data with Moscow time calculation.
        Uses 5-minute cache. The /v1/prices endpoint returns all currencies at
        once, so override_currency costs no extra network round-trip.

        Returns dict with: usd_price, price_in_selected_currency, moscow_time,
        currency, all_prices (raw dict of all currencies), or error.
        """
        current_time = time.time()
        selected_currency = override_currency or self.config.get("btc_price_currency", "USD")

        # Serve from raw cache if still fresh — zero extra API calls for alt currencies
        if self._raw_prices and (current_time - self._raw_prices_timestamp) < self._price_cache_ttl:
            return self._build_result(self._raw_prices, selected_currency)

        try:
            response = requests.get(f"{self.base_url}/v1/prices", timeout=10, verify=self.mempool_verify_ssl)
            response.raise_for_status()
            raw_prices = response.json()

            if not raw_prices.get("USD"):
                return {"error": "Unable to fetch USD price"}

            # Cache the full raw response once — all currency lookups reuse it
            self._raw_prices = raw_prices
            self._raw_prices_timestamp = current_time

            result = self._build_result(raw_prices, selected_currency)

            # Keep single-currency cache in sync for callers that relied on it
            self._price_cache = result
            self._price_cache_timestamp = current_time

            return result

        except requests.RequestException as e:
            return {"error": f"Network error: {e}"}
        except Exception as e:
            return {"error": f"Failed to fetch Bitcoin price: {e}"}

    def get_all_prices(self) -> dict:
        """Return the cached raw multi-currency price dict, or {} if not yet fetched."""
        return self._raw_prices or {}
    
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
