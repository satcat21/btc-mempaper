"""
Image Rendering and Display Module

This module handles all image-related operations including:
- Meme selection and loading
- Holiday information rendering
- Date localization and formatting
- Image composition and layout
- Display integration with e-Paper hardware

DUAL IMAGE GENERATION:
- Web Quality: High-quality images for web browser display (no e-ink processing)
- E-ink Quality: Optimized images with dithering and palette conversion for e-Paper display
- Use render_dual_images() to generate both versions simultaneously

COLOR SYSTEM:
- Uses ColorLUT for web-friendly vs e-ink optimized color mapping
- Named colors automatically map to appropriate RGB values for each display type
"""

import os
import sys
import random
import subprocess
from datetime import datetime
from tracemalloc import start
from PIL import Image, ImageDraw, ImageFont
from babel.dates import format_date

from btc_holidays import btc_holidays
from color_lut import ColorLUT
from btc_price_api import BitcoinPriceAPI
from bitaxe_api import BitaxeAPI
from wallet_balance_api import WalletBalanceAPI

COLOR_SETS = {
    "light": {
        "background": "#ffffff",
        "date_normal": "#222222",
        "date_holiday": "#b22222",
        "holiday_title": "#cd853f",
        "holiday_desc": "#d2691e",
        "btc_price": "#228B22",
        "moscow_time": "#4682B4",
        "hashrate": "#4682B4",
        "found_blocks": "#DAA520",
        "info_header": "#222222",
        "info_value": "#222222",
        "info_unit": "#808080",
        "info_bg": "#ffffff",
        "info_outline": "#eeeeee",
        "hash_start": "#007bff",
        "hash_end": "#6610f2",
        "green": "#28a745",
        "yellow": "#ffc107",
        "orange": "#fd7e14",
        "red": "#dc3545",
        "blue": "#007bff",
        "black": "#343a40",
        "wallet_balance": "#1E88E5",  # blue shade for wallet balance
        "fiat_balance": "#43A047",    # green shade for fiat balance
    },
    "dark": {
        "background": "#2e324e",
        "date_normal": "#BA68C8",
        "date_holiday": "#09a3ba",
        "holiday_title": "#09a3ba",
        "holiday_desc": "#09a3ba",
        "btc_price": "#00c896",
        "moscow_time": "#00c896",
        "hashrate": "#ffe566",
        "found_blocks": "#ffe566",
        "info_header": "#ffffff",
        "info_value": "#ffffff",
        "info_unit": "#777983",
        "info_bg": "#1d1f31",
        "info_outline": "#1d1f31",
        "hash_start": "#4FC3F7",
        "hash_end": "#BA68C8",
        'green':  "#81C784",   # Material Light Green
        'yellow': "#FFF566",   # Soft Lemon Yellow
        'orange': "#FFB347",   # Light Orange
        'red':    "#FF6F6F",   # Light/Salmon Red
        'blue':   "#4FC3F7",   # Light Sky Blue
        'black':  "#CCCCCC",
        "wallet_balance": "#09a3ba",  # lighter blue for wallet balance
        "fiat_balance": "#09a3ba",    # lighter green for fiat balance
    }
}

FEE_COLOR_TONES = {
    # Brightened colors optimized for dark backgrounds and small text readability
    "green":   ("#8AF1DC", "#4CAF50"),   # Light Green to Material Green (high contrast)
    "yellow":  ("#D0E276", "#FFC107"),   # Bright Yellow to Material Amber (very visible)
    "orange":  ("#DBD36B", "#FF9800"),   # Light Orange to Material Orange (warm and bright)
    "red":     ("#D9997B", "#F44336"),   # Light Red to Material Red (attention-grabbing)
    "blue":    ("#AD85E1", "#2196F3"),   # Light Blue to Material Blue (excellent contrast)
    "black":   ("#E0E0E0", "#BDBDBD"),   # Light Grey to Medium Grey (high readability)
}

# --- Layout and Block Constants (single source of truth) ---
INFO_BLOCK_HEIGHT = 60        # Height of info block
ELEMENT_MARGIN = 20           # Margin between elements/blocks
CARD_RADIUS = 15              # Corner radius for cards/blocks
SIDE_PADDING = 20             # Padding from left/right edge
TOP_PADDING = 20              # Padding from top edge
BLOCK_HEIGHT_AREA = 180       # Reserved space at bottom for block info
BLOCK_INNER_MARGIN = 10       # Space inside grey section/block
SECTION_SIDE_PADDING = SIDE_PADDING  # Alias for clarity
BLOCK_RADIUS = CARD_RADIUS            # Alias for clarity

class ImageRenderer:
    def __init__(self, config, translations):
        self.config = config
        self.t = translations
        self.block_fee_cache = {}  # {block_height: {'fee_data': ..., 'fee_color': ...}}
        self.last_block_height = None
        self.fee_param = config.get('fee_param', 'fastestFee')  # Default fee param
        self.lang = config.get("language", "en")
        self.orientation = config.get("display_orientation", "vertical").lower()
        self.display_width = config.get("display_width", 800)
        self.display_height = config.get("display_height", 480)
        self.e_ink_enabled = config.get("e-ink-display-connected", True)
        self._last_fee = None
        self._last_block_height = None
        if self.orientation == "vertical":
            self.width, self.height = self.display_height, self.display_width  # 480x800
        else:
            self.width, self.height = self.display_width, self.display_height  # 800x480
        self.meme_dir = os.path.join("static", "memes")
        self.font_regular = os.path.join("fonts", "Roboto-Regular.ttf")
        self.font_bold = os.path.join("fonts", "Roboto-Bold.ttf")
        self.font_mono = os.path.join("fonts", "IBMPlexMono-Bold.ttf")
        self.font_block_height = os.path.join("fonts", "RobotoCondensed-ExtraBold.ttf")
        self.block_height_area = config.get("block_height_area", 180)
        
        # Color palette for 7-color e-Paper display
        # Using the same bright, intense colors as omni-epd configuration for consistency
        # This matches the palette_filter in waveshare_epd.epd7in3f.ini
        self.palette = [
            0, 0, 0,        # black
            255, 255, 255,  # white  
            0, 255, 0,      # intense green (same as omni-epd)
            0, 0, 255,      # intense blue (same as omni-epd)
            255, 0, 0,      # intense red (same as omni-epd)
            255, 255, 0,    # intense yellow (same as omni-epd)
            255, 128, 0,    # intense orange (same as omni-epd)
        ] + [0, 0, 0] * (256 - 7)  # fill rest with black

        # Initialize API clients
        self.btc_price_api = BitcoinPriceAPI(config)
        self.bitaxe_api = BitaxeAPI(config)
        self.wallet_api = WalletBalanceAPI(config)
        # Register wallet cache update callback to refresh dashboard
        if hasattr(self.wallet_api, "register_cache_update_callback"):
            self.wallet_api.register_cache_update_callback(self._on_wallet_cache_update)

    def _on_wallet_cache_update(self, *args, **kwargs):
        """
        Callback triggered when wallet cache updates. Refreshes dashboard images.
        """
        print("🔄 Wallet cache updated, refreshing dashboard images...")
        # You may want to trigger a dashboard refresh here, e.g. by calling a method or setting a flag
        # Example:
        if hasattr(self, "refresh_dashboard"):
            self.refresh_dashboard()

    def _block_fee_cache_compat(self):
        """
        Compatibility wrapper for legacy _block_fee_cache structure.
        Returns a dict with 'current' and 'previous' keys for block fee cache.
        """
        block_heights = sorted(self.block_fee_cache.keys())
        cache = {}
        if block_heights:
            cache['current'] = {
                'height': block_heights[-1],
                'fee_data': self.block_fee_cache[block_heights[-1]].get('fee_data', {})
            }
            if len(block_heights) > 1:
                cache['previous'] = {
                    'height': block_heights[-2],
                    'fee_data': self.block_fee_cache[block_heights[-2]].get('fee_data', {})
                }
            else:
                cache['previous'] = cache['current']
        else:
            cache['current'] = {'height': None, 'fee_data': {}}
            cache['previous'] = {'height': None, 'fee_data': {}}
        return cache

    @property
    def _block_fee_cache(self):
        return self._block_fee_cache_compat()
    def _get_fee_for_parameter(self, block_height, fee_param=None):
        """
        Retrieve the fee value for a given block height and fee parameter.
        """
        fee_param = fee_param or self.fee_param
        block_entry = self.block_fee_cache.get(block_height, {})
        fee_data = block_entry.get('fee_data', {})
        return fee_data.get(fee_param, None)

    def _update_block_fee_cache(self, block_height, fee_data, fee_color):
        """
        Update block fee cache when a new block is found.
        Stores fee data and fee color for the current block height.
        Keeps previous block's data for gradient rendering.
        """
        # Ensure block_height is always a string (hashable)
        if isinstance(block_height, dict):
            block_height = str(block_height)
        if block_height != self.last_block_height:
            # New block detected, update cache
            self.block_fee_cache[block_height] = {
                'fee_data': fee_data,
                'fee_color': fee_color
            }
            # Optionally, keep only last two blocks to limit memory
            if len(self.block_fee_cache) > 2:
                # Remove oldest block
                oldest = sorted(self.block_fee_cache.keys())[0]
                del self.block_fee_cache[oldest]
            self.last_block_height = block_height
        # If not a new block, do not update cache

    def get_fee_colors_for_gradient(self, block_height):
        """
        Get previous and current fee colors for gradient rendering.
        Returns (recent_fee_color, current_fee_color).
        """
        block_heights = sorted(self.block_fee_cache.keys())
        if len(block_heights) < 2:
            # Not enough data, fallback to current color twice
            current = self.block_fee_cache.get(block_height, {})
            color = current.get('fee_color', 'gray')
            return color, color
        prev_height = block_heights[-2]
        curr_height = block_heights[-1]
        prev_color = self.block_fee_cache[prev_height]['fee_color']
        curr_color = self.block_fee_cache[curr_height]['fee_color']
        return prev_color, curr_color

    def get_fee_value_for_param(self, block_height, fee_param=None):
        """
        Get the fee value for the given block and fee parameter.
        """
        fee_param = fee_param or self.fee_param
        block_entry = self.block_fee_cache.get(block_height, {})
        fee_data = block_entry.get('fee_data', {})
        return fee_data.get(fee_param, None)
    # ...existing code...
    
    # --- Info Block Data Fetchers ---
    def fetch_btc_price(self):
        """
        Fetch current BTC price and calculate Moscow time using the dedicated API client.
        Returns: dict with price info or None on failure.
        """
        return self.btc_price_api.fetch_btc_price()

    def fetch_bitaxe_stats(self):
        """
        Fetch Bitaxe hashrate and valid blocks using the dedicated API client.
        Returns: dict with hashrate and valid blocks info or None on failure.
        """
        return self.bitaxe_api.fetch_bitaxe_stats()

    def fetch_wallet_balances(self, startup_mode: bool = False):
        """
        Fetch deduped wallet balances using the dedicated API client.
        
        Args:
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            
        Returns: dict with balance info or None on failure.
        """
        return self.wallet_api.fetch_wallet_balances(startup_mode=startup_mode)
        
    # --- Info Block Renderers ---
    def render_btc_price_block(self, draw, info_block_y, font_label, font_value, price_data, web_quality=False):
        """
        Render BTC price and Moscow time info block with two-column table layout.
        """
        if price_data is None or price_data.get("error"):
            return info_block_y

        currency = price_data["currency"]
        price = price_data.get("currency_price", price_data.get("price_in_selected_currency", 0))
        moscow_time = price_data["moscow_time"]

        currency_symbols = {
            "USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$", 
            "CHF": "CHF", "AUD": "A$", "JPY": "¥"
        }
        fiat_currency_symbol = currency_symbols.get(currency, currency)

        moscow_time_unit = self.config.get("moscow_time_unit", "sats")

        header_left_text = self.t.get("btc_price", "BTC price")
        if moscow_time_unit == "hour":
            header_right_text = self.t.get("moscow_time", "Moscow time")
        else:
            header_right_text = f"1 {currency} ="

        col_width = self.width // 2
        left_col_center_x = col_width // 2
        right_col_center_x = col_width + (col_width // 2)

        try:
            font_small_label = ImageFont.truetype(self.font_regular, 14)
        except:
            font_small_label = font_label

        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)

        left_x = left_col_center_x - (bbox_left[2] - bbox_left[0]) // 2
        right_x = right_col_center_x - (bbox_right[2] - bbox_right[0]) // 2

        draw.rounded_rectangle(
            [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, info_block_y),
            (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        text_y = info_block_y + 5
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        info_block_y += (bbox_left[3] - bbox_left[1]) + 8

        try:
            font_large_value = ImageFont.truetype(self.font_bold, 27)
        except:
            font_large_value = font_value

        price_value_text = f"{fiat_currency_symbol} {price:,.0f}"

        if moscow_time_unit == "hour":
            hours = moscow_time // 100
            minutes = moscow_time % 100
            moscow_time_text = f"{hours:02d}:{minutes:02d}"
        else:
            moscow_time_text = f"{moscow_time:,} sats"

        bbox_price = font_large_value.getbbox(price_value_text)
        bbox_moscow = font_large_value.getbbox(moscow_time_text)

        price_x = left_col_center_x - (bbox_price[2] - bbox_price[0]) // 2
        moscow_x = right_col_center_x - (bbox_moscow[2] - bbox_moscow[0]) // 2

        text_y = info_block_y + 5
        draw.text((price_x, text_y), price_value_text, font=font_large_value, fill=self.get_color("btc_price", web_quality))
        draw.text((moscow_x, text_y), moscow_time_text, font=font_large_value, fill=self.get_color("moscow_time", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_bitaxe_block(self, draw, info_block_y, font_label, font_value, bitaxe_data, web_quality=False):
        """
        Render Bitaxe hashrate and valid blocks info block with two-column table layout.
        """
        if bitaxe_data is None or bitaxe_data.get("error"):
            return info_block_y

        total_ths = bitaxe_data.get("total_hashrate_ths", 0)
        online_devices = bitaxe_data.get("miners_online", 0)
        total_devices = bitaxe_data.get("miners_total", 0)
        valid_blocks = bitaxe_data.get("valid_blocks", 0)

        header_left_text = self.t.get("total_hashrate", f"Total hashrate ({online_devices}/{total_devices})")
        header_right_text = self.t.get("valid_blocks", "Valid blocks found")

        col_width = self.width // 2
        left_col_center_x = col_width // 2
        right_col_center_x = col_width + (col_width // 2)

        try:
            font_small_label = ImageFont.truetype(self.font_regular, 14)
        except:
            font_small_label = font_label

        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)

        left_x = left_col_center_x - (bbox_left[2] - bbox_left[0]) // 2
        right_x = right_col_center_x - (bbox_right[2] - bbox_right[0]) // 2

        draw.rounded_rectangle(
            [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, info_block_y),
            (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )
        text_y = info_block_y + 5

        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        info_block_y += (bbox_left[3] - bbox_left[1]) + 8

        try:
            font_large_value = ImageFont.truetype(self.font_bold, 27)
        except:
            font_large_value = font_value

        hashrate_value_text = f"{total_ths:.2f} TH/s"
        blocks_value_text = str(valid_blocks)

        bbox_hashrate = font_large_value.getbbox(hashrate_value_text)
        bbox_blocks = font_large_value.getbbox(blocks_value_text)

        hashrate_x = left_col_center_x - (bbox_hashrate[2] - bbox_hashrate[0]) // 2
        blocks_x = right_col_center_x - (bbox_blocks[2] - bbox_blocks[0]) // 2

        text_y = info_block_y + 5
        draw.text((hashrate_x, text_y), hashrate_value_text, font=font_large_value, fill=self.get_color("hashrate", web_quality))
        draw.text((blocks_x, text_y), blocks_value_text, font=font_large_value, fill=self.get_color("found_blocks", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_wallet_balances_block(self, draw, info_block_y, font_label, font_value, balance_data, web_quality=False, startup_mode=False):
        # Defensive: Ensure balance_data is a dict and not a list
        if balance_data is None or not isinstance(balance_data, dict) or balance_data.get("error"):
            return info_block_y
        """
        Render wallet balances info block with two-column table layout.
        Args:
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
        """
        if balance_data is None or balance_data.get("error"):
            return info_block_y

        total_balance_btc = balance_data.get("total_btc", 0)
        balance_unit = balance_data.get("unit", "BTC")
        show_fiat = balance_data.get("show_fiat", False)
        total_balance_btc = balance_data.get("total_btc", 0)
        balance_unit = balance_data.get("unit", "BTC")
        show_fiat = balance_data.get("show_fiat", False)
        fiat_value = balance_data.get("total_fiat")
        fiat_currency = balance_data.get("fiat_currency", "USD")

        header_left_text = self.t.get("total_balance", "Total balance") + f" ({balance_unit})"
        header_right_text = self.t.get("fiat_value", "Fiat value") if show_fiat else ""

        col_width = self.width // 2 if show_fiat else self.width
        left_col_center_x = col_width // 2
        right_col_center_x = col_width + (col_width // 2) if show_fiat else 0

        try:
            font_small_label = ImageFont.truetype(self.font_regular, 14)
        except Exception:
            font_small_label = font_label

        draw.rounded_rectangle(
            [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, info_block_y),
            (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        bbox_left = font_small_label.getbbox(header_left_text)
        left_x = left_col_center_x - (bbox_left[2] - bbox_left[0]) // 2
        text_y = info_block_y + 5
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        if show_fiat and header_right_text:
            bbox_right = font_small_label.getbbox(header_right_text)
            right_x = right_col_center_x - (bbox_right[2] - bbox_right[0]) // 2
            draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        info_block_y += (bbox_left[3] - bbox_left[1]) + 8

        try:
            font_large_value = ImageFont.truetype(self.font_bold, 27)
        except Exception:
            font_large_value = font_value

        if balance_unit.lower() == "sats":
            total_balance_sats = int(total_balance_btc * 1e8)
            balance_value_text = f"{total_balance_sats:,}"
        else:
            balance_value_text = f"{total_balance_btc:.8f}"

        bbox_balance = font_large_value.getbbox(balance_value_text)
        balance_x = left_col_center_x - (bbox_balance[2] - bbox_balance[0]) // 2
        text_y = info_block_y + 5
        draw.text((balance_x, text_y), balance_value_text, font=font_large_value, fill=self.get_color("wallet_balance", web_quality))

        if show_fiat and fiat_value is not None:
            currency_symbols = {
                "USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$", 
                "CHF": "CHF", "AUD": "A$", "JPY": "¥"
            }
            fiat_currency_symbol = currency_symbols.get(fiat_currency, fiat_currency)

            if fiat_currency == "JPY":
                fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.0f}"
            elif fiat_currency == "EUR":
                fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.2f}"
            else:
                fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.2f}"

            bbox_fiat = font_large_value.getbbox(fiat_value_text)
            fiat_x = right_col_center_x - (bbox_fiat[2] - bbox_fiat[0]) // 2
            text_y = info_block_y + 5
            draw.text((fiat_x, text_y), fiat_value_text, font=font_large_value, fill=self.get_color("fiat_balance", web_quality))
        elif show_fiat:
            currency_symbols = {
                "USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$", 
                "CHF": "CHF", "AUD": "A$", "JPY": "¥"
            }
            fiat_currency_symbol = currency_symbols.get(fiat_currency, fiat_currency)

            if fiat_currency == "EUR":
                fiat_value_text = f"{fiat_currency_symbol} 0.00"
            else:
                fiat_value_text = f"{fiat_currency_symbol} 0.00"

            bbox_fiat = font_large_value.getbbox(fiat_value_text)
            fiat_x = right_col_center_x - (bbox_fiat[2] - bbox_fiat[0]) // 2
            text_y = info_block_y + 5
            draw.text((fiat_x, text_y), fiat_value_text, font=font_large_value, fill=self.get_color("fiat_balance", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN


    def get_color(self, color_name, web_quality=False):
        """
        Get RGB color values for a color key (theme) or named color.
        For web images, uses COLOR_SETS for light/dark mode.
        For e-ink, uses ColorLUT and EPD color mapping.

        Args:
            color_name (str or list): Color key (for theme) or named color or RGB array
            web_quality (bool): True for web display, False for e-ink

        Returns:
            tuple: RGB color tuple
        """
        """
        Get RGB color values for a color key (theme) or named color.
        For web images, uses COLOR_SETS for light/dark mode.
        For e-ink, uses ColorLUT and EPD color mapping.
        """
        # Only use COLOR_SETS for web images
        if web_quality and isinstance(color_name, str) and color_name in COLOR_SETS["light"]:
            mode = "dark" if self.config.get("color_mode_dark", True) else "light"
            hex_color = COLOR_SETS[mode].get(color_name, "#ffffff")
            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return rgb

        # For e-ink images, always use light mode colors or EPD mapping
        if not web_quality and isinstance(color_name, str) and color_name in COLOR_SETS["light"]:
            hex_color = COLOR_SETS["light"].get(color_name, "#ffffff")
            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return rgb
    
        # If it's a direct RGB list
        if isinstance(color_name, list) and len(color_name) == 3:
            return tuple(color_name)

        # For named colors (legacy or e-ink)
        if isinstance(color_name, str):
            if web_quality:
                # Use ColorLUT for web display
                display_type = "web"
                rgb_values = ColorLUT.get_color(color_name, display_type)
                return tuple(rgb_values)
            else:
                # Map named colors directly to EPD colors for e-ink
                from epd_color_fix import WAVESHARE_EPD_COLORS
                color_mapping = {
                    'black': WAVESHARE_EPD_COLORS['BLACK'],
                    'white': WAVESHARE_EPD_COLORS['WHITE'],
                    'red': WAVESHARE_EPD_COLORS['RED'],
                    'fire_brick': WAVESHARE_EPD_COLORS['RED'],
                    'green': WAVESHARE_EPD_COLORS['GREEN'],
                    'forest_green': WAVESHARE_EPD_COLORS['GREEN'],
                    'blue': WAVESHARE_EPD_COLORS['BLUE'],
                    'steel_blue': WAVESHARE_EPD_COLORS['BLUE'],
                    'yellow': WAVESHARE_EPD_COLORS['YELLOW'],
                    'goldenrod': WAVESHARE_EPD_COLORS['YELLOW'],
                    'orange': WAVESHARE_EPD_COLORS['ORANGE'],
                    'peru': WAVESHARE_EPD_COLORS['ORANGE'],
                    'chocolate': WAVESHARE_EPD_COLORS['ORANGE'],
                }
                if color_name.lower() in color_mapping:
                    return color_mapping[color_name.lower()]
                else:
                    # Fallback: try ColorLUT then map to closest EPD color
                    try:
                        rgb_values = ColorLUT.get_color(color_name, "eink")
                        from epd_color_fix import get_closest_epd_color
                        return get_closest_epd_color(tuple(rgb_values))
                    except:
                        return WAVESHARE_EPD_COLORS['BLACK']  # Safe fallback

        # Fallback to black
        if web_quality:
            return (0, 0, 0)
        else:
            from epd_color_fix import WAVESHARE_EPD_COLORS
            return WAVESHARE_EPD_COLORS['BLACK']
    
    def convert_to_7color(self, img, use_meme_optimization=False):
        """
        Convert image to 7-color palette suitable for e-Paper display.
        
        Args:
            img (PIL.Image): Input image
            use_meme_optimization (bool): Apply enhanced processing for meme images
            
        Returns:
            PIL.Image: Converted image with 7-color palette
        """
        palette_img = Image.new("P", (1, 1))
        palette_img.putpalette(self.palette)
        
        if use_meme_optimization:
            # Enhanced processing for memes: better color mixing
            # Apply slight contrast boost for better color definition
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            
            # Use Floyd-Steinberg dithering for better color gradients in memes
            return img.convert("RGB").quantize(palette=palette_img, dither=Image.FLOYDSTEINBERG).convert("RGB")
        else:
            # Clean processing for text areas: no dithering for sharp text
            return img.convert("RGB").quantize(palette=palette_img, dither=Image.NONE).convert("RGB")
    
    def remove_graining_from_pil(self, img, threshold=30):
        """
        Remove graining artifacts from palettized images.
        
        Args:
            img (PIL.Image): Input image in palette mode
            threshold (int): Darkness threshold for pixel cleanup
            
        Returns:
            PIL.Image: Cleaned image
        """
        if img.mode != "P":
            return img
        
        palette = img.getpalette()
        pixels = img.load()
        
        for y in range(img.height):
            for x in range(img.width):
                index = pixels[x, y]
                r, g, b = palette[index * 3 : index * 3 + 3]
                
                if r < threshold and g < threshold and b < threshold:
                    pixels[x, y] = 0  # Set to pure black in palette
        
        return img
    
    def pick_random_meme(self):
        """
        Select a random meme image from the memes directory.
        
        Returns:
            str or None: Path to selected meme or None if no memes found
        """
        try:
            memes = [f for f in os.listdir(self.meme_dir) 
                    if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if not memes:
                print("No meme images found in directory")
                return None
            
            selected = random.choice(memes)
            return os.path.join(self.meme_dir, selected)
        except Exception as e:
            print(f"Error selecting meme: {e}")
            return None
    
    def get_today_btc_holiday(self):
        """
        Get Bitcoin holiday information for today in the configured language.
        
        Returns:
            dict or None: Holiday information or None if no holiday today
        """
        today_key = datetime.now().strftime("%m-%d")
        holiday_list = btc_holidays.get(today_key)
        
        if holiday_list and isinstance(holiday_list, list) and len(holiday_list) > 0:
            # Take the first holiday entry (there could be multiple)
            holiday = holiday_list[0]
            
            if holiday and self.lang in holiday:
                return holiday[self.lang]
            elif holiday and "en" in holiday:
                return holiday["en"]  # fallback to English
        
        return None
    
    def get_fee_and_block_info(self, mempool_api=None):
        """
        Get current transaction fees and block info from mempool API.
        Returns:
            tuple: (configured_fee, block_height) or (None, None) if failed
        """
        if mempool_api is None:
            print("⚠️ No mempool_api instance provided")
            return None, None
        try:
            fee_parameter = self.config.get("fee_parameter", "minimumFee")
            configured_fee = mempool_api.get_configured_fee(fee_parameter)
            block_height = mempool_api.get_tip_height()
            if configured_fee is not None and block_height is not None:
                return configured_fee, int(block_height)
            else:
                print("⚠️ Failed to get complete fee and block info")
                return None, None
        except Exception as e:
            print(f"⚠️ Error getting fee info: {e}")
            return None, None

    def render_mempool_error(self, draw, y, width, language):
        """
        Render a localized error message if mempool connection fails.
        """
        msg = self.t.get("mempool_error", "⚠️ Mempool connection failed. Fee and block info unavailable.")
        font = ImageFont.truetype(self.font_bold, 22)
        bbox = font.getbbox(msg)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), msg, font=font, fill=self.get_color("red", True))
        return y + (bbox[3] - bbox[1]) + 20

    def fee_to_colors(self, current_fee, recent_fee, web_quality=False):
        """
        Returns a tuple of (current_color, recent_color) for gradient coloring.
        Caches the last fee in memory.
        """
        # Helper to map fee to color name
        def fee_to_color_name(fee_value):
            if fee_value is None:
                return "black"
            elif fee_value <= 1:
                return "green"
            elif fee_value <= 3:
                return "yellow"
            elif fee_value <= 10:
                return "orange"
            elif fee_value <= 20:
                return "red"
            elif fee_value <= 40:
                return "blue"
            else:
                return "black"

        # Get color names for current and recent fee
        current_color_name = fee_to_color_name(current_fee)
        recent_color_name = fee_to_color_name(recent_fee)

        # Get color tones: vivid for current, washed out for recent
        current_hex = FEE_COLOR_TONES.get(current_color_name, ("#FF9604", "#0B940B"))[0]
        recent_hex = FEE_COLOR_TONES.get(recent_color_name, ("#A304FF", "#E3D90D"))[1]

        # Convert hex to RGB tuple
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = ''.join([c*2 for c in hex_color])
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        current_rgb = hex_to_rgb(current_hex)
        recent_rgb = hex_to_rgb(recent_hex)

        return current_rgb, recent_rgb
    

    def get_localized_date(self):
        """
        Get current date formatted according to the configured language.
        
        Returns:
            str: Localized date string
        """
        today = datetime.now()
        
        if self.lang == "en":
            # English with ordinal day (e.g., "22nd July 2025")
            def ordinal(n):
                return "%d%s" % (n, "tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
            day_ordinal = ordinal(today.day)
            return f"{day_ordinal} {today.strftime('%B %Y')}"
        
        elif self.lang == "de":
            # German format (e.g., "22. Juli 2025")
            return format_date(today, format="d. MMMM y", locale="de")
        
        elif self.lang == "es":
            # Spanish format (e.g., "22 de julio de 2025")
            return format_date(today, format="d 'de' MMMM 'de' y", locale="es")
        
        elif self.lang == "fr":
            # French format (e.g., "22 juillet 2025")
            return format_date(today, format="d MMMM y", locale="fr")
        
        else:
            # Fallback to ISO format
            return today.strftime("%Y-%m-%d")
    
    def get_optimal_date_font_size(self, date_text, max_width=None, max_font_size=None, min_font_size=None):
        """
        Calculate optimal font size for date text to fit within display width.
        
        Args:
            date_text (str): The date text to measure
            max_width (int, optional): Maximum width in pixels. Defaults to 90% of display width.
            max_font_size (int, optional): Maximum font size to try. Defaults to config value or 48.
            min_font_size (int, optional): Minimum font size allowed. Defaults to config value or 20.
        
        Returns:
            int: Optimal font size that fits the text within the width constraints
        """
        if max_width is None:
            max_width = int(self.width * 0.9)  # Use 90% of display width as default
        
        if max_font_size is None:
            max_font_size = self.config.get("date_font_max_size", 48)
        
        if min_font_size is None:
            min_font_size = self.config.get("date_font_min_size", 32)
        
        # Start with the maximum font size and work down
        for font_size in range(max_font_size, min_font_size - 1, -1):
            try:
                test_font = ImageFont.truetype(self.font_bold, font_size)
                bbox = test_font.getbbox(date_text)
                text_width = bbox[2] - bbox[0]
                
                if text_width <= max_width:
                    return font_size
            except Exception as e:
                # If font loading fails, continue with smaller size
                continue
        
        # If all else fails, return minimum font size
        return min_font_size

    def draw_centered(self, draw, text, y, font, fill="black"):
        """
        Draw text centered horizontally at specified y position.
        
        Args:
            draw (ImageDraw): PIL drawing context
            text (str): Text to draw
            y (int): Y position
            font (ImageFont): Font to use
            fill (str or tuple): Text color (string name or RGB tuple)
            
        Returns:
            int: Y position after text (for next element)
        """
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (self.width - text_width) // 2
        draw.text((x, y), text, font=font, fill=fill)
        return y + text_height + 10
    
    def draw_multiline_centered(self, draw, text, y, font, max_width, fill="black", line_spacing=4):
        """
        Draw multi-line text centered horizontally with word wrapping.
        
        Args:
            draw (ImageDraw): PIL drawing context
            text (str): Text to draw
            y (int): Starting Y position
            font (ImageFont): Font to use
            max_width (int): Maximum width for text wrapping
            fill (str): Text color
            line_spacing (int): Space between lines
            
        Returns:
            int: Y position after last line of text
        """
        words = text.split()
        lines = []
        current_line = ""
        
        # Word wrapping
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            bbox = font.getbbox(test_line)
            test_width = bbox[2] - bbox[0]
            
            if test_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Draw each line centered
        for line in lines:
            bbox = font.getbbox(line)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (self.width - text_width) // 2
            draw.text((x, y), line, font=font, fill=fill)
            y += text_height + line_spacing
        
        return y

    def render_dual_images(self, block_height, block_hash, mempool_api=None,  startup_mode=False):
        """
        Render both web-quality and e-ink optimized images efficiently.
        Optimized to share common elements and reduce API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            
        Returns:
            tuple: (web_image, eink_image, content_path) - Both PIL.Image objects and source content path
        """
        if startup_mode:
            print("🚀 [STARTUP] Generating dual images with minimal processing...")
        else:
            print("🎨 Generating dual images with shared processing...")
        
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        if holiday_info:
            print(f"🎄 Holiday detected: {holiday_info.get('title', 'No title')}")
        
        # Get fee info once
        configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Try Twitter content first, fallback to memes
        content_path = None
        # Fallback to random meme
        if not content_path:
            content_path = self.pick_random_meme()
            print(f"🎭 Selected meme: {os.path.basename(content_path) if content_path else 'None'}")
        
        # Randomly select info blocks ONCE
        info_blocks = []
        bitaxe_data = None
        btc_price_data = None
        wallet_data = None
        config = self.config
        if config.get("show_btc_price_block", True):
            btc_price_data = self.btc_price_api.fetch_btc_price()
            info_blocks.append((self.render_btc_price_block, btc_price_data))
        if config.get("show_bitaxe_block", True):
            bitaxe_data = self.bitaxe_api.fetch_bitaxe_stats()
            info_blocks.append((self.render_bitaxe_block, bitaxe_data))
        if config.get("show_wallet_balances_block", True):
            print("🔍 [IMG] Loading cached wallet data...")
            wallet_data = self.wallet_api.get_cached_wallet_balances()
            # Import privacy utils if available
            try:
                from privacy_utils import mask_bitcoin_data
                masked_wallet_data = mask_bitcoin_data(wallet_data)
                print(f"📋 [IMG] Cached wallet data result: {masked_wallet_data}")
            except ImportError:
                print(f"📋 [IMG] Cached wallet data result: {wallet_data}")
            if wallet_data is None or wallet_data.get("error"):
                print("⚠️ [IMG] No cached wallet data available or error occurred, using default values")
                wallet_data = {
                    "total_btc": 0,
                    "total_fiat": 0,
                    "fiat_currency": "USD",
                    "addresses": [],
                    "xpubs": [],
                }
            else:
                print(f"✅ [IMG] Using cached wallet data: {wallet_data.get('total_btc', 0)} BTC")
            
            # Only try to convert to fiat if we have valid wallet data
            if wallet_data.get("total_btc") is not None and not wallet_data.get("error"):
                if btc_price_data:
                    wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data["fiat_currency"])
                else:
                    btc_price_data = self.btc_price_api.fetch_btc_price()
                    if btc_price_data:
                        wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data["fiat_currency"])
                    else:
                        print("⚠️ Failed to fetch BTC price data for wallet balance updates. Use cache as it is.")

            info_blocks.append((self.render_wallet_balances_block, wallet_data))
        
        # Pass all shared data to both renders
        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "api_block_height": api_block_height,
            "meme_path": content_path,
            "btc_price_data": btc_price_data,
            "bitaxe_data": bitaxe_data,
            "wallet_data": wallet_data,
            "info_blocks": info_blocks,
            # ...add any other shared data...
        }

        # === GENERATE WEB IMAGE ===
        if startup_mode:
            print("🚀 [STARTUP] Generating web-quality image with cached data...")
        else:
            print("🌐 Generating web-quality image...")
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True, startup_mode=startup_mode
        )
        
        # === GENERATE E-INK IMAGE ===
        if startup_mode:
            print("🚀 [STARTUP] Generating e-ink optimized image with cached data...")
        else:
            print("🖥️ Generating e-ink optimized image...")
        eink_img = None
        if self.e_ink_enabled:
            eink_img = self._render_image_with_shared_data(
                block_height, block_hash, mempool_api,
                shared_data, web_quality=False, startup_mode=startup_mode
            )
        
        print("✅ Dual image generation completed efficiently")
        return web_img, eink_img, content_path  # Return selected content path for caching
    
    def render_dual_images_with_cached_meme(self, block_height, block_hash, cached_meme_path, mempool_api=None):
        """
        Render both web-quality and e-ink optimized images using a specific cached meme.
        Used when configuration changes require image refresh but meme should stay the same.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            cached_meme_path (str): Path to the cached meme to use
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            
        Returns:
            tuple: (web_image, eink_image, meme_path) - Both PIL.Image objects and used meme path
        """
        print(f"🎨 Regenerating images with cached meme: {os.path.basename(cached_meme_path) if cached_meme_path else 'None'}")
        
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        if holiday_info:
            print(f"🎄 Holiday detected: {holiday_info.get('title', 'No title')}")
        
        # Get fee info once
        configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Use the provided cached meme path
        meme_path = cached_meme_path
        print(f"📦 Using cached meme: {os.path.basename(meme_path) if meme_path else 'None'}")
        
        # Fetch info block data ONCE
        btc_price_data = None
        bitaxe_data = None
        wallet_data = None

        # Randomly select info blocks ONCE
        info_blocks = []
        config = self.config
        if config.get("show_btc_price_block", True):
            btc_price_data = self.btc_price_api.fetch_btc_price()
            info_blocks.append((self.render_btc_price_block, btc_price_data))
        if config.get("show_bitaxe_block", True):
            bitaxe_data = self.bitaxe_api.fetch_bitaxe_stats()
            info_blocks.append((self.render_bitaxe_block, bitaxe_data))
        if config.get("show_wallet_balances_block", True):
            print("🔍 [CACHE_IMG] Loading cached wallet data...")
            wallet_data = self.wallet_api.get_cached_wallet_balances()
            # Import privacy utils if available
            try:
                from privacy_utils import mask_bitcoin_data
                masked_wallet_data = mask_bitcoin_data(wallet_data)
                print(f"📋 [CACHE_IMG] Cached wallet data result: {masked_wallet_data}")
            except ImportError:
                print(f"📋 [CACHE_IMG] Cached wallet data result: {wallet_data}")
            if wallet_data is None or wallet_data.get("error"):
                print("⚠️ [CACHE_IMG] No cached wallet data available or error occurred, using default values")
                wallet_data = {
                    "total_btc": 0,
                    "total_fiat": 0,
                    "fiat_currency": "USD",
                    "addresses": [],
                    "xpubs": [],
                }
            else:
                print(f"✅ [CACHE_IMG] Using cached wallet data: {wallet_data.get('total_btc', 0)} BTC")
            
            # Only try to convert to fiat if we have valid wallet data
            if wallet_data.get("total_btc") is not None and not wallet_data.get("error"):
                if btc_price_data:
                    wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data["fiat_currency"])
                else:
                    btc_price_data = self.btc_price_api.fetch_btc_price()
                    if btc_price_data:
                        wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data["fiat_currency"])
                    else:
                        print("⚠️ Failed to fetch BTC price data for wallet balance updates. Use cache as it is.")

            info_blocks.append((self.render_wallet_balances_block, wallet_data))
        # Random selection logic here if needed

        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "api_block_height": api_block_height,
            "meme_path": meme_path,
            "btc_price_data": btc_price_data,
            "bitaxe_data": bitaxe_data,
            "wallet_data": wallet_data,
            "info_blocks": info_blocks,
            # ...add any other shared data...
        }

        # === GENERATE WEB IMAGE ===
        print("🌐 Regenerating web-quality image...")
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True
        )
        
        # === GENERATE E-INK IMAGE ===
        print("🖥️ Regenerating e-ink optimized image...")
        eink_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=False
        )
        
        print("✅ Image regeneration with cached meme completed")
        return web_img, eink_img, meme_path
    
    def _render_image_with_shared_data(self, block_height, block_hash, mempool_api,
                                      shared_data, web_quality=False, startup_mode=False):
        """
        Render image using pre-collected shared data to avoid duplicate API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            holiday_info (dict): Pre-collected holiday information
            configured_fee (int): Pre-collected fee information
            api_block_height (int): Pre-collected API block height
            meme_path (str): Pre-selected meme path
            web_quality (bool): True for web display, False for e-ink
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            
        Returns:
            PIL.Image: Rendered dashboard image
        """
        # Get the date text first to calculate optimal font size
        date_text = self.get_localized_date()
        
        # Calculate optimal font size for the date
        optimal_date_font_size = self.get_optimal_date_font_size(date_text)
        
        # Load fonts with calculated date font size
        font_date = ImageFont.truetype(self.font_bold, optimal_date_font_size)
        font_holiday_title = ImageFont.truetype(self.font_bold, 20)
        font_holiday_desc = ImageFont.truetype(self.font_regular, 16)
        font_block_label = ImageFont.truetype(self.font_regular, 16)
        font_block_value = ImageFont.truetype(self.font_block_height, 124)
        
        holiday_info = shared_data["holiday_info"]
        configured_fee = shared_data["configured_fee"]
        api_block_height = shared_data["api_block_height"]
        meme_path = shared_data["meme_path"]
        # btc_price_data = shared_data["btc_price_data"]
        # bitaxe_data = shared_data["bitaxe_data"]
        # wallet_data = shared_data["wallet_data"]
        info_blocks = shared_data["info_blocks"]

        # Create base image
        img = Image.new('RGB', (self.width, self.height), color=self.get_color("background", web_quality))
        draw = ImageDraw.Draw(img)
        
        # Date
        top_y = 20
        # y = self.draw_centered(draw, self.get_localized_date(), top_y, font_date, fill=self.get_color("date_holiday" if holiday_info else "date_normal", web_quality))
        # Choose gradient colors (can use hash frame colors or any theme keys)
        start_color = self.get_color("hash_start", web_quality)
        end_color = self.get_color("hash_end", web_quality)

        # Use the date_text we already calculated
        bbox = font_date.getbbox(date_text)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = top_y

        # Always set date_bottom_y to the bottom of the date text plus margin
        date_bottom_y = y + (bbox[3] - bbox[1]) + 10

        # Always draw the date at the top, with gradient color
        date_color = self.get_color("date_holiday", web_quality) if holiday_info else self.get_color("date_normal", web_quality)
        for i, char in enumerate(date_text):
            t = i / max(len(date_text) - 1, 1)
            color = self.interpolate_color(start_color, end_color, t)
            char_bbox = font_date.getbbox(char)
            char_width = char_bbox[2] - char_bbox[0]
            draw.text((x, y), char, font=font_date, fill=color)
            x += char_width

        # Draw info block background after date rendering if holiday_info
        if holiday_info:
            draw.rounded_rectangle(
                [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, y + 60),
                 (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, y + 60 + INFO_BLOCK_HEIGHT)],
                radius=BLOCK_RADIUS,
                fill=self.get_color("info_bg", web_quality),
                outline=self.get_color("info_outline", web_quality),
                width=4
            )

        meme_bottom_y = self.height - self.block_height_area
        content_top_y = date_bottom_y
        available_content_height = meme_bottom_y - content_top_y

        prioritize_large_meme = self.config.get("prioritize_large_scaled_meme", False)

        # Info blocks setup
        # info_blocks = []
        # config = self.config
        # if config.get("show_btc_price_block", True):
        #     info_blocks.append((self.render_btc_price_block, btc_price_data))
        # if config.get("show_bitaxe_block", True):
        #     info_blocks.append((self.render_bitaxe_block, bitaxe_data))
        # if config.get("show_wallet_balances_block", True):
        #     info_blocks.append((self.render_wallet_balances_block, wallet_data))

        #INFO_BLOCK_HEIGHT = 60
        HOLIDAY_HEIGHT = 70 if holiday_info else 0
        BLOCK_MARGIN = 15

        if prioritize_large_meme:
            # --- Step 1: Determine meme scaling ---
            meme_img = None
            meme_height = 0
            meme_width = 0
            if meme_path:
                try:
                    meme_img = Image.open(meme_path)
                    aspect_ratio = meme_img.width / meme_img.height
                    max_width = self.width - 40
                    max_height = available_content_height - 20
                    # Scale meme to fit max width and max height
                    scaled_width = min(max_width, int(max_height * aspect_ratio))
                    scaled_height = int(scaled_width / aspect_ratio)
                    if scaled_height > max_height:
                        scaled_height = max_height
                        scaled_width = int(scaled_height * aspect_ratio)
                    meme_img = meme_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                    meme_height = scaled_height
                    meme_width = scaled_width
                except Exception as e:
                    print(f"⚠️ Error loading meme for scaling: {e}")

            # --- Step 2: Calculate remaining height for info blocks ---
            remaining_height = available_content_height - meme_height - 20
            blocks_y = content_top_y

            # --- Step 3: Assign space for holiday ---
            holiday_space = HOLIDAY_HEIGHT if (holiday_info and remaining_height >= HOLIDAY_HEIGHT) else 0
            remaining_height_for_info = remaining_height - holiday_space

            # --- Step 4: Assign space for info blocks ---
            max_blocks = (remaining_height_for_info - BLOCK_MARGIN) // (INFO_BLOCK_HEIGHT + BLOCK_MARGIN)
            info_blocks_to_render = []
            if max_blocks > 0 and info_blocks:
                if len(info_blocks) > max_blocks:
                    info_blocks_to_render = random.sample(info_blocks, int(max_blocks))
                else:
                    info_blocks_to_render = info_blocks
            # --- Step 5: Calculate vertical layout ---
            # Total assigned height for all elements
            total_assigned_height = meme_height + holiday_space + len(info_blocks_to_render) * INFO_BLOCK_HEIGHT + (len(info_blocks_to_render) + 1) * BLOCK_MARGIN
            vertical_offset = content_top_y + (available_content_height - total_assigned_height) // 2
            current_y = vertical_offset
                    
            # Render holiday (centered in assigned space)
            if holiday_space:
                holiday_vertical_offset = content_top_y + 10 #(holiday_space - HOLIDAY_HEIGHT) // 2
                self._render_holiday_info(draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        holiday_vertical_offset, HOLIDAY_HEIGHT, web_quality)
                current_y += holiday_space

            # Render meme (centered horizontally)
            if meme_img:
                current_y += 10
                meme_x = (self.width - meme_width) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)  
                img.paste(meme_img, (meme_x, current_y), meme_img)
                current_y += meme_height
            else:
                self._render_fallback_content(img, draw, current_y, meme_height,
                                            font_holiday_title, web_quality)
                current_y += meme_height
            if len(info_blocks_to_render):
                # Render info blocks (each centered in assigned space)
                section_left = BLOCK_MARGIN
                section_right = self.width - BLOCK_MARGIN
                section_top = current_y #+ BLOCK_MARGIN # slightly above first block
                section_bottom = current_y + len(info_blocks_to_render) * INFO_BLOCK_HEIGHT + (len(info_blocks_to_render) + 1) * BLOCK_MARGIN

                bg_color = (255, 250, 200)  # pale yellow
                # bg_color = (200, 200, 200)  # light grey
                radius = 15  # rounded corners
                # draw.rounded_rectangle(
                #     [(section_left, section_top), (section_right, section_bottom)],
                #     radius=radius,
                #     fill=bg_color
                # )
                blocks_y += BLOCK_MARGIN

            for block_fn, block_data in info_blocks_to_render:
                info_vertical_offset = current_y + (INFO_BLOCK_HEIGHT + BLOCK_MARGIN - INFO_BLOCK_HEIGHT) // 2 + 10
                try:
                    if block_fn == self.render_wallet_balances_block:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                    else:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality)
                except Exception as e:
                    print(f"⚠️ Error rendering info block {block_fn.__name__}: {e}")
                current_y += INFO_BLOCK_HEIGHT + BLOCK_MARGIN

        else:
            # --- prioritize_large_scaled_meme == False ---
            # Render holiday first
            blocks_y = content_top_y
            if holiday_info:
                self._render_holiday_info(draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        blocks_y, HOLIDAY_HEIGHT, web_quality)
                blocks_y += HOLIDAY_HEIGHT

            # Render meme (centered horizontally)
            meme_img = None
            meme_height = 0
            meme_width = 0
            if meme_path:
                try:
                    meme_img = Image.open(meme_path)
                    aspect_ratio = meme_img.width / meme_img.height
                    max_width = self.width - 40
                    max_height = available_content_height - 20
                    scaled_width = min(max_width, int(max_height * aspect_ratio))
                    scaled_height = int(scaled_width / aspect_ratio)
                    if scaled_height > max_height:
                        scaled_height = max_height
                        scaled_width = int(scaled_height * aspect_ratio)
                    meme_img = meme_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                    meme_height = scaled_height
                    meme_width = scaled_width
                except Exception as e:
                    print(f"⚠️ Error loading meme for scaling: {e}")
            if meme_img:
                blocks_y += 10
                meme_x = (self.width - meme_width) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)
                img.paste(meme_img, (meme_x, blocks_y), meme_img)
                blocks_y += meme_height
            else:
                self._render_fallback_content(img, draw, blocks_y, meme_height,
                                            font_holiday_title, web_quality)
                blocks_y += meme_height

            # Render info blocks below meme, with dark style
            if len(info_blocks):
                section_left = BLOCK_MARGIN
                section_right = self.width - BLOCK_MARGIN
                section_top = blocks_y
                section_bottom = blocks_y + len(info_blocks) * INFO_BLOCK_HEIGHT + (len(info_blocks) + 1) * BLOCK_MARGIN
                # Use theme background color for info block area
                bg_color = self.get_color("info_bg", web_quality)
                radius = 15
                draw.rounded_rectangle(
                    [(section_left, section_top), (section_right, section_bottom)],
                    radius=radius,
                    fill=bg_color
                )
                blocks_y += BLOCK_MARGIN
                for block_fn, block_data in info_blocks:
                    try:
                        if block_fn == self.render_wallet_balances_block:
                            blocks_y = block_fn(draw, blocks_y, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                        else:
                            blocks_y = block_fn(draw, blocks_y, font_block_label, font_block_value, block_data, web_quality)
                    except Exception as e:
                        print(f"⚠️ Error rendering info block {block_fn.__name__}: {e}")
                    blocks_y += BLOCK_MARGIN

            # Calculate remaining space for meme (not needed, meme is already rendered above info blocks)
            # meme_top_y = blocks_y + BLOCK_MARGIN
            # meme_area_height = meme_bottom_y - meme_top_y
            # self._render_content_with_meme(img, draw, meme_top_y, meme_area_height,
            #                             font_holiday_title, font_holiday_desc, meme_path, web_quality)

        # Block info at bottom
        self._render_block_info_with_data(img, draw, block_height, block_hash, font_block_label,
                                        font_block_value, mempool_api, configured_fee,
                                        api_block_height, web_quality)

        return img
    
    def _render_content_with_meme(self, img, draw, meme_top_y, available_height,
                                font_holiday_title, font_holiday_desc, meme_path, web_quality):
        """
        Render content using pre-selected meme data to avoid redundant selection.
        """
        # Render meme content if path is provided
        if meme_path:
            try:
                # Use the pre-selected meme path directly
                print(f"🎨 Using pre-selected meme: {meme_path}")
                
                # Open and process the meme image
                meme_img = Image.open(meme_path)
                
                # Calculate optimal size and position
                aspect_ratio = meme_img.width / meme_img.height
                target_width = min(self.width - 40, available_height * aspect_ratio)
                target_height = target_width / aspect_ratio
                
                # Resize if needed
                if target_width != meme_img.width or target_height != meme_img.height:
                    meme_img = meme_img.resize((int(target_width), int(target_height)), Image.Resampling.LANCZOS)
                
                # Center the meme
                x = (self.width - meme_img.width) // 2
                y = meme_top_y + (available_height - meme_img.height) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)  
                # Paste the meme onto the main image
                img.paste(meme_img, (x, y), meme_img)

            except Exception as e:
                print(f"⚠️ Error rendering pre-selected meme {meme_path}: {e}")
                # Fallback to rendering text if meme fails
                self._render_fallback_content(img, draw, meme_top_y, available_height, 
                                            font_holiday_title, web_quality)
        else:
            # No meme available, render alternative content
            self._render_fallback_content(img, draw, meme_top_y, available_height, 
                                        font_holiday_title, web_quality)

    def add_rounded_corners(self, img, radius):
        # Create mask
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
        # Apply mask
        img_rounded = img.copy()
        img_rounded.putalpha(mask)
        return img_rounded

    def interpolate_color(self, start, end, t):
        return tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))

    def draw_hash_frame(self, draw, x_init, y_init, block_hash, rect_width=760, rect_height=80, max_width=None, web_quality=True):
        """
        Draws a block hash as a rectangular frame starting at (x, y).
        """
        padding = 40
        extra_space = 8
        start_color = self.get_color("hash_start", web_quality)  # #4FC3F7
        end_color   = self.get_color("hash_end", web_quality)    # #BA68C8

        total_chars = len(block_hash)
        block_hash_colors = [self.interpolate_color(start_color, end_color, i / max(total_chars - 1, 1)) for i in range(total_chars)]
        # --- Optional scaling if max_width is given ---
        if max_width is not None:
            original_width = rect_width + 2 * padding
            if original_width > max_width:
                scale_factor = max_width / original_width
                rect_width = int(rect_width * scale_factor)
                rect_height = int(rect_height * scale_factor)
                padding = int(padding * scale_factor)

        font = ImageFont.truetype(self.font_mono, 11)
    
        # Character size
        #char_w, char_h = font.getbbox("0")[2:4]
        bbox = font.getbbox("0")
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]

        # Split the hash
        left_chars = block_hash[:16]           # left vertical
        right_chars = block_hash[46:64]        # right vertical
        top_chars = block_hash[0:46]          # top horizontal (22 chars)
        bottom_chars = block_hash[18:62]       # bottom horizontal (22 chars)

        left_chars_colors = block_hash_colors[:16]
        right_chars_colors = block_hash_colors[46:64]
        top_chars_colors = block_hash_colors[0:46]
        bottom_chars_colors = block_hash_colors[18:62]

        # --- TOP EDGE with grouped pairs ---
        #x = padding
        #y = padding
        top_positions = []
        x = x_init
        y = y_init
        for i, c in enumerate(top_chars):
            draw.text((x, y), c, fill=top_chars_colors[i], font=font)
            top_positions.append(x)
            x +=  int(char_w)
            if (i + 1) % 2 == 0:
                x += 6#int(char_w) # extra space after every 2 chars

        # --- LEFT VERTICAL SIDE with horizontal pairs ---
        x = top_positions[0]  # align under first char of top edge
        y = y_init + int(char_h) + extra_space # y_init +padding +  int(char_h) + extra_space
        i = 0
        while i < len(left_chars):
            pair = left_chars[i:i+2]
            draw.text((x, y), pair, fill=left_chars_colors[i], font=font)  # draw both chars on the same line
            y +=  int(char_h) + extra_space # move down for next pair
            i += 2

        # --- RIGHT VERTICAL SIDE with horizontal pairs ---
        x = top_positions[-2] + 1 # align under last char of top edge
        y = y_init + int(char_h) + extra_space #padding +  int(char_h) + extra_space
        i = 0
        while i < len(right_chars):
            pair = right_chars[i:i+2]
            draw.text((x, y), pair, fill=right_chars_colors[i], font=font)
            y +=  int(char_h) + extra_space
            i += 2

        # --- BOTTOM EDGE with grouped pairs ---
        x = x_init
        y = y_init + padding + rect_height + extra_space + int(char_h) + extra_space
        for i, c in enumerate(bottom_chars):
            draw.text((x, y), c, fill=bottom_chars_colors[i], font=font)
            x += int(char_w)
            if (i + 1) % 2 == 0:
                x +=  6#int(char_w)  # extra space after every 2 chars

    def _render_block_info_with_data(self, img, draw, block_height, block_hash, font_block_label,
                                    font_block_value, mempool_api, configured_fee,
                                    api_block_height, web_quality):
        """
        Render block information using pre-collected fee and block data.
        """
        # Use pre-collected data instead of making new API calls
        if api_block_height is not None:
            display_block_height = str(api_block_height)
        else:
            display_block_height = str(block_height)
        
        # Update fee cache only if block height changed
        if self._block_fee_cache["current"]["height"] != display_block_height:
            fee_data = mempool_api.get_fee_recommendations() if mempool_api else None
            # Compute fee_color or use a default
            fee_color = self.get_color("fee", web_quality) if hasattr(self, 'get_color') else "gray"
            self._update_block_fee_cache(display_block_height, fee_data, fee_color)
        fee_parameter = self.config.get("fee_parameter", "minimumFee")
        prev_fee = self._get_fee_for_parameter(self._block_fee_cache["previous"]["height"], fee_parameter)
        curr_fee = self._get_fee_for_parameter(self._block_fee_cache["current"]["height"], fee_parameter)
        block_height_start_color, block_height_end_color = self.fee_to_colors(curr_fee, prev_fee, web_quality)
        # Position block info based on orientation (same as existing _render_block_info)
        if self.orientation == "vertical":
            y = self.height - (self.block_height_area - 10)  # Move up by 10px from original position
        else:
            y = self.height - (self.block_height_area - 70)  # Adjust for horizontal layout
        
        # Draw "Block Height" label
        # y = self.draw_centered(draw, self.t.get("block_height", "Block Height"), 
        #                      y, font_block_label)
        # Draw at (x, y), black text, max width 760px
        self.draw_hash_frame(draw, 12, y+3, block_hash, web_quality=web_quality)
        y = y + 24
        # Format and draw block height with fee-based color
        if mempool_api:
            formatted_height = mempool_api.format_block_height(display_block_height)
        else:
            try:
                height_int = int(display_block_height)
                formatted_height = f"{height_int:,}".replace(",", ".")
            except (ValueError, TypeError):
                formatted_height = str(display_block_height)
        
        # Draw block height with color based on current fees (move up by 10px)
        value_y = y - 25
        bbox = font_block_value.getbbox(formatted_height)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y + 10, font_block_value, block_height_start_color, block_height_end_color)
        # self.draw_centered(draw, formatted_height, value_y + 10, font_block_value, fill=self.get_color(block_height_color, web_quality))

        # Add fee information as small text if available
        if configured_fee is not None:
            # Get the configured fee parameter to display the fee type
            fee_parameter = self.config.get("fee_parameter", "minimumFee")
            
            # Map technical fee parameter names to user-friendly display names
            fee_type_names = {
                "fastestFee": "Fastest",
                "halfHourFee": "Half Hour", 
                "hourFee": "Hour",
                "economyFee": "Economy",
                "minimumFee": "Minimum"
            }
            
            fee_type_display = fee_type_names.get(fee_parameter, "Unknown")
            fee_text = f"{fee_type_display} fee: {configured_fee} sat/vB"
            
            try:
                font_small = ImageFont.truetype(self.font_regular, 12)
            except:
                font_small = font_block_label
            
            # Draw fee info in smaller text below block height (use adjusted position)
            bbox = font_block_value.getbbox(formatted_height)
            fee_y = value_y + bbox[3] - bbox[1] + 42
            # Use darker tone for e-ink, use brighter tone for web (TODO: use darker for light mode as well?)
            if web_quality:
                self.draw_centered(draw, fee_text, fee_y, font_small, block_height_start_color)
            else:
                self.draw_centered(draw, fee_text, fee_y, font_small, block_height_end_color)

        # Draw shortened hash
        # if mempool_api:
        #     short_hash = mempool_api.shorten_hash(block_hash)
        # else:
        #     short_hash = f"{block_hash[:12]}...{block_hash[-12:]}"
        
        y += 105  # Moved up by 5px (was 110)
        # self.draw_centered(draw, short_hash, y, font_block_label)
    
    def draw_vertical_gradient_text(self, img, draw, text, x, y, font, start_color, end_color):
        ascent, descent = font.getmetrics()
        text_width = font.getbbox(text)[2] - font.getbbox(text)[0]
        text_height = ascent + descent + 8  # Add a few pixels for safety
        size = (text_width, text_height)

        # Create a transparent image for the text
        text_img = Image.new("L", size, 0)
        text_draw = ImageDraw.Draw(text_img)
        # Draw text at (0, ascent) for proper vertical alignment
        text_draw.text((0, 0), text, font=font, fill=255)

        # Create a vertical gradient image
        gradient = Image.new("RGBA", size)
        for yy in range(size[1]):
            t = yy / max(size[1] - 1, 1)
            color = tuple(int(start_color[i] + ((end_color[i] - start_color[i]) * t)) for i in range(3)) + (255,)
            ImageDraw.Draw(gradient).line([(0, yy), (size[0], yy)], fill=color)

        # Use the text image as an alpha mask
        gradient.putalpha(text_img)

        # Paste onto the main image using alpha channel
        img.paste(gradient, (int(x), int(y)), gradient)

    def _render_fallback_content(self, img, draw, meme_top_y, available_height, 
                               font_holiday_title, web_quality):
        """
        Render fallback content (Twitter or meme) when pre-selected meme fails.
        """
        
        # Fallback to random meme selection
        print("🎲 Falling back to random meme selection")
        meme_path = self.pick_random_meme()
        if meme_path:
            try:
                # Render the fallback meme
                meme_img = Image.open(meme_path)
                
                # Calculate optimal size
                aspect_ratio = meme_img.width / meme_img.height
                target_width = min(self.width - 40, available_height * aspect_ratio)
                target_height = target_width / aspect_ratio
                
                if target_width != meme_img.width or target_height != meme_img.height:
                    meme_img = meme_img.resize((int(target_width), int(target_height)), Image.Resampling.LANCZOS)
                
                # Apply e-ink optimization if needed
                if not web_quality:
                    meme_img = self.convert_to_7color(meme_img, use_meme_optimization=True)
                    self.remove_graining_from_pil(meme_img)
                
                # Center and paste the meme
                x = (self.width - meme_img.width) // 2
                y = meme_top_y + (available_height - meme_img.height) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)  
                img.paste(meme_img, (x, y), meme_img)
                
                print(f"🎨 Rendered fallback meme: {meme_path}")
                
            except Exception as e:
                               print(f"⚠️ Error rendering fallback meme {meme_path}: {e}")
        else:
            print("⚠️ No fallback meme available")
    

    def _render_holiday_info(self, draw, holiday_info, font_title, font_desc, 
                           date_bottom_y, holiday_height, web_quality=False):
        """
        Render Bitcoin holiday information dynamically centered in available space.
        
        Args:
            draw (ImageDraw): Drawing context
            holiday_info (dict): Holiday information
            font_title (ImageFont): Font for holiday title
            font_desc (ImageFont): Font for holiday description
            date_bottom_y (int): Bottom Y position of date text
            holiday_height (int): Reserved height for holiday content
            web_quality (bool): True for web display, False for e-ink
        """
        # Check if holiday should be displayed (this method only called when not prioritizing large meme)
        #prioritize_large_meme = self.config.get("prioritize_large_scaled_meme", False)
        
        #if not prioritize_large_meme:
        # Get configurable colors using color LUT
        title_color = self.get_color("holiday_title", web_quality)
        desc_color = self.get_color("holiday_desc", web_quality)

        print(f"🎄 Rendering holiday: {holiday_info.get('title', 'No title')}")
            
        # Calculate text dimensions for dynamic centering
        title_text = holiday_info.get("title", "Bitcoin Holiday")
        desc_text = holiday_info.get("description", "")
            
        # Calculate title height
        title_bbox = font_title.getbbox(title_text)
        title_height = title_bbox[3] - title_bbox[1]
            
        # Calculate description height (with text wrapping)
        max_text_width = int(self.width * 0.9)
        words = desc_text.split()
        desc_lines = []
        current_line = ""
            
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            bbox = font_desc.getbbox(test_line)
            test_width = bbox[2] - bbox[0]
                
            if test_width <= max_text_width:
                current_line = test_line
            else:
                if current_line:
                    desc_lines.append(current_line)
                    current_line = word
                else:
                    desc_lines.append(word)
            
        if current_line:
            desc_lines.append(current_line)
            
        # Calculate total description height
        desc_bbox = font_desc.getbbox("Ay")  # Sample text for line height
        line_height = desc_bbox[3] - desc_bbox[1]
        desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * 4  # 4px line spacing
            
        # Calculate total holiday content height
        total_holiday_height = title_height + 10 + desc_total_height  # 10px gap between title and desc
            
        # Calculate available space for holiday (between date and meme area)
        holiday_start = date_bottom_y + 10  # Reduced gap from 30px to 20px
        meme_area_start = date_bottom_y + 20 + holiday_height
        available_space = holiday_height
            
        # Center the holiday content vertically in available space
        vertical_center = holiday_start + (available_space - total_holiday_height) // 2
        # Move holiday title 10px higher
        y = max(holiday_start, vertical_center - 10)  # Ensure we don't go above minimum position
            
        # Render the holiday title
        y = self.draw_centered(draw, title_text, y, font_title, fill=title_color)
            
        # Render the holiday description with text wrapping
        y = self.draw_multiline_centered(draw, desc_text, y + 5, font_desc, 
                                           max_text_width, fill=desc_color)
        #else:
        #    print(f"🚫 Holiday hidden due to prioritize_large_scaled_meme=True")
    

    def display_on_epaper(self, image_path="current.png", message=None):
        """
        Display image on e-Paper - now returns immediately since main app uses subprocess.
        
        Args:
            image_path (str): Path to image file to display
            message (str, optional): Optional message overlay
            
        Returns:
            bool: Always returns True since subprocess handles the actual display
        """
        # Check if e-Paper display is enabled in configuration
        if not self.e_ink_enabled:
            print("ⓘ e-Paper display disabled in configuration - skipping hardware display")
            return True
        
        # When called from main app, the subprocess method handles the display
        # This method just returns success to avoid blocking the threading
        print("ⓘ E-paper display handled by subprocess - returning immediately")
        return True
    
    def _fallback_display(self, image_path, message=None):
        """
        Fallback to the original show_image.py script method.
        
        Args:
            image_path (str): Path to image file to display
            message (str, optional): Optional message overlay
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Prepare command to call show_image.py script
            script_path = os.path.join("display", "show_image.py")
            python_executable = sys.executable
            
            cmd = [python_executable, script_path]
            
            if message:
                cmd.extend(["--message", message])
            
            # Convert to absolute path
            if not os.path.isabs(image_path):
                image_path = os.path.abspath(image_path)
            cmd.append(image_path)
            
            print(f"🔄 Running fallback display command: {' '.join(cmd)}")
            
            # Run the display script with timeout
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            if result.returncode == 0:
                print("✓ Image displayed on e-Paper via show_image.py (fallback)")
                if result.stdout:
                    print(f"Output: {result.stdout}")
                return True
            else:
                print(f"✗ Error displaying on e-Paper (exit code {result.returncode}): {result.stderr}")
                if result.stdout:
                    print(f"Output: {result.stdout}")
                return False
                    
        except subprocess.TimeoutExpired:
            print("✗ Timeout while displaying image on e-Paper")
            return False
        except Exception as e:
            print(f"✗ Error displaying on e-Paper: {e}")
            return False
