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
from PIL import Image, ImageDraw, ImageFont
from babel.dates import format_date

from lib.btc_holidays import btc_holidays
from utils.color_lut import ColorLUT
from lib.btc_price_api import BitcoinPriceAPI
from lib.bitaxe_api import BitaxeAPI
from lib.wallet_balance_api import WalletBalanceAPI

COLOR_SETS = {
    "light": {
        "background": "#ffffff",
        "date_normal": "#222222",
        "date_holiday": "#b22222",
        "holiday_title": "#cd853f",
        "holiday_desc": "#d2691e",
        "btc_price": "#17805B",      # darker green for BTC price (was #228B22)
        "moscow_time": "#17805B",    # darker blue for Moscow time (was #4682B4)
        "hashrate": "#B89C1D",       # darker gold for Bitaxe (was #DAA520)
        "found_blocks": "#B89C1D",   # same as hashrate
        "info_header": "#222222",
        "info_value": "#222222",
        "info_unit": "#808080",
        "info_bg": "#F8F9FA",
        "info_outline": "#E9ECEF",
        "hash_start": "#005fa3",     # darker blue
        "hash_end": "#4b0f8f",       # darker purple
        "green": "#388E3C",          # Material Green (darker)
        "yellow": "#FFA000",         # Material Amber (darker)
        "orange": "#F57C00",         # Material Orange (darker)
        "red": "#C62828",            # Material Red (darker)
        "blue": "#1976D2",           # Material Blue (darker)
        "black": "#343a40",
        "wallet_balance": "#1565C0", # darker blue for wallet balance
        "fiat_balance": "#1565C0",   # darker green for fiat balance
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
    # (light_mode, dark_mode)
    "green":   ("#4CAF50", "#8AF1DC"),   # Light Green to Material Green (high contrast)
    "yellow":  ("#FFC107", "#D0E276"),   # Bright Yellow to Material Amber (very visible)
    "orange":  ("#FF9800", "#DBD36B"),   # Light Orange to Material Orange (warm and bright)
    "red":     ("#F44336", "#D9997B"),   # Light Red to Material Red (attention-grabbing)
    "blue":    ("#2196F3", "#AD85E1"),   # Light Blue to Material Blue (excellent contrast)
    "black":   ("#BDBDBD", "#E0E0E0"),   # Light Grey to Medium Grey (high readability)
}

# For dark mode, reverse the tuple order for each color
FEE_COLOR_TONES_DARK = {
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

# --- Text and Label Constants ---
LABEL_PADDING_TOP = 5         # Vertical padding above labels
LABEL_TO_VALUE_SPACING = 8    # Space between label and value
LINE_SPACING_DEFAULT = 10     # Default line spacing for wrapped text
LINE_SPACING_MULTILINE = 4    # Spacing between lines in multiline text
HOLIDAY_TITLE_DESC_GAP = 3    # Gap between holiday title and description
HOLIDAY_PADDING = 24          # Padding around holiday content

# --- Font Sizes ---
FONT_SIZE_SMALL_LABEL = 14    # Small labels
FONT_SIZE_LARGE_VALUE = 27    # Large values in info blocks
FONT_SIZE_BLOCK_VALUE = 48    # Block height value
FONT_SIZE_HOLIDAY_TITLE = 22  # Holiday title
FONT_SIZE_HOLIDAY_DESC = 18   # Holiday description

# --- Content Layout ---
STANDARD_SPACING = 20         # Standard gap between elements
MEME_RADIUS = 20              # Border radius for meme images
MEME_MIN_HEIGHT = 50          # Minimum height for meme
MEME_SIDE_MARGIN = 40         # Total horizontal margin for meme (20 per side)

# --- Info Block Offsets ---
INFO_BLOCK_VERTICAL_ADJUSTMENT = 10  # Vertical offset adjustment for info block content


class LayoutCalculator:
    """Helper class for efficient layout calculations with consistent spacing."""
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.content_width = width - (SECTION_SIDE_PADDING * 2)
        self.inner_content_width = self.content_width - (BLOCK_INNER_MARGIN * 2)
    
    def get_centered_x(self, element_width):
        """Calculate X position to center an element."""
        return (self.width - element_width) // 2
    
    def get_column_center(self, num_columns, column_index):
        """Calculate center X position for a column in multi-column layout."""
        col_width = self.width // num_columns
        return col_width * column_index + (col_width // 2)
    
    def get_text_centered_x(self, bbox, column_center=None):
        """Calculate X position to center text based on bounding box."""
        text_width = bbox[2] - bbox[0]
        if column_center is not None:
            return column_center - (text_width // 2)
        return self.get_centered_x(text_width)
    
    def get_info_block_bounds(self):
        """Get standardized bounding box for info blocks."""
        return (
            SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN,
            SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN,
            self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN
        )
    
    def calculate_distributed_spacing(self, available_height, content_height, num_gaps):
        """Calculate evenly distributed spacing between elements."""
        if num_gaps <= 0:
            return STANDARD_SPACING
        remaining_space = available_height - content_height
        return max(STANDARD_SPACING, remaining_space // num_gaps)
    
    def get_label_y(self, block_y):
        """Get Y position for labels in info blocks."""
        return block_y + LABEL_PADDING_TOP
    
    def get_value_y(self, block_y, label_height):
        """Get Y position for values in info blocks."""
        return block_y + label_height + LABEL_TO_VALUE_SPACING + LABEL_PADDING_TOP


class ImageRenderer:
    def __init__(self, config, translations):
        self.config = config
        self.t = translations
        
        # Initialize color sets with defaults and overrides
        self.color_sets = {k: v.copy() for k, v in COLOR_SETS.items()}
        
        # Override with configured colors
        # Holidays
        if "color_holiday_light" in config:
            self.color_sets["light"]["holiday_title"] = config["color_holiday_light"]
            self.color_sets["light"]["holiday_desc"] = config["color_holiday_light"]
        if "color_holiday_dark" in config:
            self.color_sets["dark"]["holiday_title"] = config["color_holiday_dark"]
            self.color_sets["dark"]["holiday_desc"] = config["color_holiday_dark"]

        # BTC Price
        if "color_btc_price_light" in config:
            self.color_sets["light"]["btc_price"] = config["color_btc_price_light"]
            self.color_sets["light"]["moscow_time"] = config["color_btc_price_light"]
        if "color_btc_price_dark" in config:
            self.color_sets["dark"]["btc_price"] = config["color_btc_price_dark"]
            self.color_sets["dark"]["moscow_time"] = config["color_btc_price_dark"]

        # Bitaxe
        if "color_bitaxe_stats_light" in config:
            self.color_sets["light"]["hashrate"] = config["color_bitaxe_stats_light"]
            self.color_sets["light"]["found_blocks"] = config["color_bitaxe_stats_light"]
        if "color_bitaxe_stats_dark" in config:
            self.color_sets["dark"]["hashrate"] = config["color_bitaxe_stats_dark"]
            self.color_sets["dark"]["found_blocks"] = config["color_bitaxe_stats_dark"]

        # Wallets
        if "color_wallets_light" in config:
            self.color_sets["light"]["wallet_balance"] = config["color_wallets_light"]
            self.color_sets["light"]["fiat_balance"] = config["color_wallets_light"]
        if "color_wallets_dark" in config:
            self.color_sets["dark"]["wallet_balance"] = config["color_wallets_dark"]
            self.color_sets["dark"]["fiat_balance"] = config["color_wallets_dark"]

        self.block_fee_cache = {}  # {block_height: {'fee_data': ..., 'fee_color': ...}}
        self.last_block_height = None
        self.fee_param = config.get('fee_param', 'fastestFee')  # Default fee param
        self.lang = config.get("language", "en")
        
        # Orientation settings
        # Specific orientation settings (defaults to vertical if not set)
        self.web_orientation = config.get("web_orientation", "vertical").lower()
        self.eink_orientation = config.get("eink_orientation", "vertical").lower()
        
        # Initialize default orientation for rendering context (defaults to web settings)
        self.orientation = self.web_orientation
        
        self.display_width = config.get("display_width", 800)
        self.display_height = config.get("display_height", 480)
        self.e_ink_enabled = config.get("e-ink-display-connected", True)
        self._last_fee = None
        self._last_block_height = None
        
        # Initialize default state (will be overridden during rendering)
        self._apply_orientation_settings(self.orientation)
        
        self.meme_dir = os.path.join("static", "memes")
        self.font_regular = os.path.join("static", "fonts", "Roboto-Regular.ttf")
        self.font_bold = os.path.join("static", "fonts", "Roboto-Bold.ttf")
        self.font_mono = os.path.join("static", "fonts", "IBMPlexMono-Bold.ttf")
        self.font_block_height = os.path.join("static", "fonts", "RobotoCondensed-ExtraBold.ttf")
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
        print("⚙️ Wallet cache updated, refreshing dashboard images...")
        # You may want to trigger a dashboard refresh here, e.g. by calling a method or setting a flag
        # Example:
        if hasattr(self, "refresh_dashboard"):
            self.refresh_dashboard()

    def _apply_orientation_settings(self, orientation):
        """
        Apply width/height/layout settings based on requested orientation.
        Updates self.width, self.height, self.orientation, and self.layout.
        """
        self.orientation = orientation
        if self.orientation == "vertical":
            self.width, self.height = self.display_height, self.display_width  # 480x800
        else:
            self.width, self.height = self.display_width, self.display_height  # 800x480
        
        # Re-initialize layout calculator for the new dimensions
        self.layout = LayoutCalculator(self.width, self.height)

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
        if block_entry is None:
            block_entry = {}
            
        fee_data = block_entry.get('fee_data', {})
        if fee_data is None:
            fee_data = {}
            
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
            
        # Ensure fee_data is a dict
        if fee_data is None:
            fee_data = {}
            
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
        """Render BTC price and Moscow time info block with two-column table layout."""
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

        # Determine header text
        header_left_text = self.t.get("btc_price", "BTC price")
        if moscow_time_unit == "hour":
            header_right_text = self.t.get("moscow_time", "Moscow time")
        else:
            header_right_text = f"1 {currency} ="

        # Calculate column centers
        left_col_center = self.layout.get_column_center(2, 0)
        right_col_center = self.layout.get_column_center(2, 1)

        # Create fonts
        try:
            font_small_label = ImageFont.truetype(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except:
            font_small_label = font_label

        # Draw block background
        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
            (block_bounds[2], info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        # Render labels
        text_y = self.layout.get_label_y(info_block_y)
        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)
        
        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center)
        right_x = self.layout.get_text_centered_x(bbox_right, right_col_center)
        
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        # Render values
        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        try:
            font_large_value = ImageFont.truetype(self.font_bold, FONT_SIZE_LARGE_VALUE)
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

        price_x = self.layout.get_text_centered_x(bbox_price, left_col_center)
        moscow_x = self.layout.get_text_centered_x(bbox_moscow, right_col_center)

        draw.text((price_x, value_y), price_value_text, font=font_large_value, fill=self.get_color("btc_price", web_quality))
        draw.text((moscow_x, value_y), moscow_time_text, font=font_large_value, fill=self.get_color("moscow_time", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_bitaxe_block(self, draw, info_block_y, font_label, font_value, bitaxe_data, web_quality=False):
        """Render Bitaxe hashrate and valid blocks info block with two-column table layout."""
        if bitaxe_data is None or bitaxe_data.get("error"):
            return info_block_y

        total_ths = bitaxe_data.get("total_hashrate_ths", 0)
        online_devices = bitaxe_data.get("miners_online", 0)
        total_devices = bitaxe_data.get("miners_total", 0)
        valid_blocks = bitaxe_data.get("valid_blocks", 0)
        best_difficulty = bitaxe_data.get("best_difficulty", 0)

        header_left_text = self.t.get("total_hashrate", f"Total hashrate ({online_devices}/{total_devices})")
        
        # Determine what to show on the right side based on config
        display_mode = self.config.get("bitaxe_display_mode", "blocks")
        
        if display_mode == "difficulty":
            header_right_text = self.t.get("best_difficulty", "Best Difficulty")
            # Format difficulty
            if best_difficulty >= 1e12:
                blocks_value_text = f"{best_difficulty / 1e12:.2f}T"
            elif best_difficulty >= 1e9:
                blocks_value_text = f"{best_difficulty / 1e9:.2f}G"
            elif best_difficulty >= 1e6:
                blocks_value_text = f"{best_difficulty / 1e6:.2f}M"
            elif best_difficulty >= 1e3:
                blocks_value_text = f"{best_difficulty / 1e3:.2f}k"
            else:
                blocks_value_text = f"{best_difficulty:.0f}"
        else:
            header_right_text = self.t.get("valid_blocks", "Valid blocks found")
            blocks_value_text = str(valid_blocks)

        # Calculate column centers
        left_col_center = self.layout.get_column_center(2, 0)
        right_col_center = self.layout.get_column_center(2, 1)

        try:
            font_small_label = ImageFont.truetype(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except:
            font_small_label = font_label

        # Draw block background
        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
            (block_bounds[2], info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )
        
        # Render labels
        text_y = self.layout.get_label_y(info_block_y)
        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)

        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center)
        right_x = self.layout.get_text_centered_x(bbox_right, right_col_center)

        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        # Render values
        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        try:
            font_large_value = ImageFont.truetype(self.font_bold, FONT_SIZE_LARGE_VALUE)
        except:
            font_large_value = font_value

        hashrate_value_text = f"{total_ths:.2f} TH/s"
        bbox_hashrate = font_large_value.getbbox(hashrate_value_text)
        bbox_blocks = font_large_value.getbbox(blocks_value_text)

        hashrate_x = self.layout.get_text_centered_x(bbox_hashrate, left_col_center)
        blocks_x = self.layout.get_text_centered_x(bbox_blocks, right_col_center)

        draw.text((hashrate_x, value_y), hashrate_value_text, font=font_large_value, fill=self.get_color("hashrate", web_quality))
        draw.text((blocks_x, value_y), blocks_value_text, font=font_large_value, fill=self.get_color("found_blocks", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_wallet_balances_block(self, draw, info_block_y, font_label, font_value, balance_data, web_quality=False, startup_mode=False):
        """Render wallet balances info block with two-column table layout.
        
        Args:
            draw: PIL drawing context
            info_block_y: Y position for info block
            font_label: Font for labels
            font_value: Font for values
            balance_data: Dictionary with balance information
            web_quality: True for web display, False for e-ink
            startup_mode: If True, use cached data only and skip expensive gap limit detection
            
        Returns:
            int: Y position after the info block
        """
        # Defensive: Ensure balance_data is a dict and not a list
        if balance_data is None or not isinstance(balance_data, dict) or balance_data.get("error"):
            return info_block_y

        total_balance_btc = balance_data.get("total_btc", 0)
        balance_unit = balance_data.get("unit", "BTC")
        show_fiat = balance_data.get("show_fiat", False)
        fiat_value = balance_data.get("total_fiat")
        fiat_currency = balance_data.get("fiat_currency", "USD")

        header_left_text = self.t.get("total_balance", "Total balance") + f" ({balance_unit})"
        header_right_text = self.t.get("fiat_value", "Fiat value") if show_fiat else ""

        # Use LayoutCalculator for column positioning
        num_columns = 2 if show_fiat else 1
        left_col_center_x = self.layout.get_column_center(num_columns, 0)
        right_col_center_x = self.layout.get_column_center(num_columns, 1) if show_fiat else 0

        try:
            font_small_label = ImageFont.truetype(self.font_regular, FONT_SIZE_SMALL_LABEL)
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
        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center_x)
        text_y = self.layout.get_label_y(info_block_y)
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        if show_fiat and header_right_text:
            bbox_right = font_small_label.getbbox(header_right_text)
            right_x = self.layout.get_text_centered_x(bbox_right, right_col_center_x)
            draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        try:
            font_large_value = ImageFont.truetype(self.font_bold, FONT_SIZE_LARGE_VALUE)
        except Exception:
            font_large_value = font_value

        if balance_unit.lower() == "sats":
            total_balance_sats = int(total_balance_btc * 1e8)
            balance_value_text = f"{total_balance_sats:,}"
        else:
            balance_value_text = f"{total_balance_btc:.8f}"

        bbox_balance = font_large_value.getbbox(balance_value_text)
        balance_x = self.layout.get_text_centered_x(bbox_balance, left_col_center_x)
        label_height = bbox_left[3] - bbox_left[1]
        text_y = self.layout.get_value_y(info_block_y, label_height)
        draw.text((balance_x, text_y), balance_value_text, font=font_large_value, fill=self.get_color("wallet_balance", web_quality))

        if show_fiat:
            currency_symbols = {
                "USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$", 
                "CHF": "CHF", "AUD": "A$", "JPY": "¥"
            }
            fiat_currency_symbol = currency_symbols.get(fiat_currency, fiat_currency)

            if fiat_value is not None:
                if fiat_currency == "JPY":
                    fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.0f}"
                elif fiat_currency == "EUR":
                    fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.2f}"
                else:
                    fiat_value_text = f"{fiat_currency_symbol} {fiat_value:,.2f}"
            else:
                # Show 0.00 for EUR/others when no value
                fiat_value_text = f"{fiat_currency_symbol} 0.00"

            bbox_fiat = font_large_value.getbbox(fiat_value_text)
            fiat_x = self.layout.get_text_centered_x(bbox_fiat, right_col_center_x)
            label_height = bbox_left[3] - bbox_left[1]
            text_y = self.layout.get_value_y(info_block_y, label_height)
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
        # Use self.color_sets for web images
        if web_quality and isinstance(color_name, str) and color_name in self.color_sets["light"]:
            mode = "dark" if self.config.get("color_mode_dark", True) else "light"
            hex_color = self.color_sets[mode].get(color_name, "#ffffff")
            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return rgb

        # For e-ink images, use dark mode if enabled
        if not web_quality and isinstance(color_name, str) and color_name in self.color_sets["light"]:
            mode = "dark" if self.config.get("eink_dark_mode", False) else "light"
            hex_color = self.color_sets[mode].get(color_name, "#ffffff")
            
            # For e-ink dark mode, override most text to white for readability
            # Exceptions: date colors and fee-based colors (green/yellow/orange/red/blue/black)
            if mode == "dark" and color_name not in ["date_normal", "date_holiday", "background", 
                                                       "info_bg", "info_outline", "hash_start", "hash_end",
                                                       "green", "yellow", "orange", "red", "blue", "black"]:
                hex_color = "#ffffff"
            
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
                from utils.epd_color_fix import WAVESHARE_EPD_COLORS
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
                        from utils.epd_color_fix import get_closest_epd_color
                        return get_closest_epd_color(tuple(rgb_values))
                    except:
                        return WAVESHARE_EPD_COLORS['BLACK']  # Safe fallback

        # Fallback to black
        if web_quality:
            return (0, 0, 0)
        else:
            from utils.epd_color_fix import WAVESHARE_EPD_COLORS
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
    
    def _wrap_text_at_chars(self, text, max_chars=50):
        """Wrap text to multiple lines, breaking at word boundaries.
        
        Args:
            text (str): Text to wrap
            max_chars (int): Maximum characters per line
            
        Returns:
            list: List of text lines
        """
        if len(text) <= max_chars:
            return [text]
        
        lines = []
        current_line = ""
        words = text.split()
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            
            if len(test_line) <= max_chars:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
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
        Uses FEE_COLOR_TONES for light mode and FEE_COLOR_TONES_DARK for dark mode.
        """
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

        # Determine mode
        mode = "dark" if self.config.get("color_mode_dark", True) else "light"
        color_tones = FEE_COLOR_TONES_DARK if mode == "dark" else FEE_COLOR_TONES

        current_color_name = fee_to_color_name(current_fee)
        recent_color_name = fee_to_color_name(recent_fee)

        current_hex = color_tones.get(current_color_name, ("#FF9604", "#0B940B"))[0]
        recent_hex = color_tones.get(recent_color_name, ("#A304FF", "#E3D90D"))[1]

        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = ''.join([c*2 for c in hex_color])
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        current_rgb = hex_to_rgb(current_hex)
        recent_rgb = hex_to_rgb(recent_hex)

        return current_rgb, recent_rgb
    

    def get_localized_date(self, block_height=None):
        """
        Get current date formatted according to the configured language.
        For genesis block (height 0), returns the actual genesis block date.
        
        Args:
            block_height (int or str, optional): Block height to determine date.
                                                  If 0, uses genesis block date.
        
        Returns:
            str: Localized date string
        """
        # Genesis block timestamp: 1231006505 (January 3, 2009, 18:15:05 UTC)
        # Use the actual genesis block date for block 0
        if block_height is not None and str(block_height) == "0":
            today = datetime(2009, 1, 3)
        else:
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
        
        elif self.lang == "it":
            # Italian format (e.g., "22 luglio 2025")
            return format_date(today, format="d MMMM y", locale="it")
        
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
        """Draw text centered horizontally at specified y position.
        
        Args:
            draw (ImageDraw): PIL drawing context
            text (str): Text to draw
            y (int): Y position
            font (ImageFont): Font to use
            fill (str or tuple): Text color
            
        Returns:
            int: Y position after text (for next element)
        """
        bbox = font.getbbox(text)
        text_height = bbox[3] - bbox[1]
        x = self.layout.get_text_centered_x(bbox)
        draw.text((x, y), text, font=font, fill=fill)
        return y + text_height + LINE_SPACING_DEFAULT
    
    def draw_multiline_centered(self, draw, text, y, font, max_width, fill="black", line_spacing=LINE_SPACING_MULTILINE):
        """Draw multi-line text centered horizontally with word wrapping.
        
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
            text_height = bbox[3] - bbox[1]
            x = self.layout.get_text_centered_x(bbox)
            draw.text((x, y), line, font=font, fill=fill)
            y += text_height + line_spacing
        
        return y

    def render_dual_images(self, block_height, block_hash, mempool_api=None,  startup_mode=False, override_content_path=None):
        """
        Render both web-quality and e-ink optimized images efficiently.
        Optimized to share common elements and reduce API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            override_content_path (str, optional): Force specific meme/image path
            
        Returns:
            tuple: (web_image, eink_image, content_path) - Both PIL.Image objects and source content path
        """
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info once
        configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Try overrides first, then Twitter content, fallback to memes
        content_path = override_content_path
        
        # Fallback to random meme if no override and no content path yet
        if not content_path:
            content_path = self.pick_random_meme()
        
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
            if startup_mode:
                wallet_data = self.wallet_api.get_cached_wallet_balances()
                if wallet_data is None or wallet_data.get("error"):
                    print("⚠️ [STARTUP-IMG] No cached wallet data available, using default values for immediate display")
                    wallet_data = {
                        "total_btc": 0,
                        "total_fiat": 0,
                        "fiat_currency": config.get("fiat_currency", "USD"),
                        "unit": config.get("btc_unit", "BTC"),
                        "show_fiat": config.get("show_fiat_balance", False),
                        "addresses": [],
                        "xpubs": [],
                    }
                else:
                    print(f"✅ [STARTUP-IMG] Using cached wallet data: {wallet_data.get('total_btc', 0):.8f} BTC")
            else:
                wallet_data = self.wallet_api.get_cached_wallet_balances()
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
                    pass
            
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
        # Apply web orientation settings
        self._apply_orientation_settings(self.web_orientation)
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True, startup_mode=startup_mode
        )
        
        # === GENERATE E-INK IMAGE ===
        eink_img = None
        if self.e_ink_enabled:
            # Apply e-ink orientation settings
            self._apply_orientation_settings(self.eink_orientation)
            eink_img = self._render_image_with_shared_data(
                block_height, block_hash, mempool_api,
                shared_data, web_quality=False, startup_mode=startup_mode
            )
        
        # Restore default/web orientation state (optional, but good practice)
        self._apply_orientation_settings(self.web_orientation)
        
        print(f"✅ Image generated for block {block_height}")
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
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info once
        configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Use the provided cached meme path
        meme_path = cached_meme_path
        
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
            wallet_data = self.wallet_api.get_cached_wallet_balances()
            # Import privacy utils if available
            # try:
                # from privacy_utils import mask_bitcoin_data
                # masked_wallet_data = mask_bitcoin_data(wallet_data)
                # print(f"📋 [CACHE_IMG] Cached wallet data result: {masked_wallet_data}")
            # except ImportError:
                # print(f"📋 [CACHE_IMG] Cached wallet data result: {wallet_data}")
            if wallet_data is None or wallet_data.get("error"):
                wallet_data = {
                    "total_btc": 0,
                    "total_fiat": 0,
                    "fiat_currency": "USD",
                    "addresses": [],
                    "xpubs": [],
                }
            else:
                pass
            
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
        # Apply web orientation settings
        self._apply_orientation_settings(self.web_orientation)
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True
        )
        
        # === GENERATE E-INK IMAGE ===
        self._apply_orientation_settings(self.eink_orientation)
        eink_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=False
        )
        
        # Restore default
        self._apply_orientation_settings(self.web_orientation)
        
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
        date_text = self.get_localized_date(block_height)
        
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

        # --- Calculate HOLIDAY_HEIGHT (Used in both Landscape and Vertical layouts) ---
        BLOCK_MARGIN = 15
        HOLIDAY_HEIGHT = 0
        if holiday_info:
            # Calculate exact height needed based on text content
            title_text = holiday_info.get("title", "Bitcoin Holiday")
            desc_text = holiday_info.get("description", "")
            
            # Title height
            title_bbox = font_holiday_title.getbbox(title_text)
            title_height = title_bbox[3] - title_bbox[1]
            
            # Description height (with word wrapping at 50 characters)
            desc_lines = self._wrap_text_at_chars(desc_text, max_chars=50)
            
            desc_bbox = font_holiday_desc.getbbox("Ay")
            line_height = desc_bbox[3] - desc_bbox[1]
            desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * 4
            
            # Total height: Title + Gap(3) + Description + Padding(24)
            # 12px top + 12px bottom = 24px total padding for balanced spacing
            HOLIDAY_HEIGHT = title_height + 3 + desc_total_height + 24

        # === Landscape Mode Layout (Split Screen) ===
        if self.orientation == "horizontal":
            # 1. Calculate Date and Layout Widths
            # Use reduced font size if needed, but horizontal usually allows full width
            # Standard font date is bold, calculated earlier: font_date
            
            # Left pane items: Date, Holiday, Info Blocks, Block Height/Hash
            # Right pane: Meme
            
            date_bbox = font_date.getbbox(date_text)
            date_width = date_bbox[2] - date_bbox[0]
            date_height = date_bbox[3] - date_bbox[1]
            
            # Define Left Column Width
            # User wants "width of the date to center all other elements"
            # We enforce a minimum width to ensure info blocks fit reasonably well (e.g. 300px)
            # Info blocks standard layout is usually robust
            left_pane_width = max(date_width + 40, 320)
            
            # Ensure we don't take too much space (max 60% of width)
            left_pane_width = min(left_pane_width, int(self.width * 0.6))
            
            left_margin = 20  # "linksbündig" implies left aligned with margin
            content_center_x = left_margin + (date_width // 2) # Center point based on Date Width as requested
            # Alternatively, center in the pane width:
            content_center_x = left_margin + ((left_pane_width - left_margin * 2) // 2)
            
            # BUT user said: "using the width of the date to center all other elements"
            # This implies the center axis is Date's center.
            # If Date is Left Aligned at `left_margin`.
            date_center_x = left_margin + (date_width // 2)
            left_col_center = date_center_x 
            
            # We must ensure this center allows elements to fit defined `left_pane_width`
            # If date is very short (e.g. "May 1"), the center is very left. Info blocks will clip left.
            # So let's enforce a minimum visual center or just align elements to the date's center
            # effectively creating a "column" around the date.
            
            # 2. Render Date (Left Aligned at specific margin)
            # Use gradient as before
            start_color = self.get_color("hash_start", web_quality)
            end_color = self.get_color("hash_end", web_quality)
            
            current_y = 10
            x = left_margin
            
            # Draw Date
            for i, char in enumerate(date_text):
                t = i / max(len(date_text) - 1, 1)
                color = self.interpolate_color(start_color, end_color, t)
                char_bbox = font_date.getbbox(char)
                char_width = char_bbox[2] - char_bbox[0]
                draw.text((x, current_y), char, font=font_date, fill=color)
                x += char_width
                
            current_y += date_height + 10 # Gap after date
            
            # 3. Render Holiday and Info Blocks in the Left Column
            # We need to temporarily hack self.layout/self.width for render functions that depend on it
            # OR we pass a custom `draw_centered` logic?
            # Most render functions use `self.layout.get_info_block_bounds()` which uses `self.width`
            # We will patch `self.layout` temporarily layout calculator
            
            original_layout_width = self.layout.width
            # We want the render functions to think the screen width is `left_pane_width` 
            # AND we want them to render at `left_margin` offset?
            # Actually, `get_info_block_bounds` returns (padding, padding, width-padding)
            # If we set layout width to `left_pane_width`, it renders from 0 to `left_pane_width`.
            # We can create a separate image/layer for the left pane and paste it?
            # Or we can just calculate offsets.
            # Simpler: Temporary Layout Override.
            
            # Create a temporary layout for the left column
            # We set width such that center aligns with `left_col_center` relative to 0?
            # No, render functions typically assume full screen width and center content.
            # If we set layout width to `left_pane_width`, content is centered at `left_pane_width / 2`.
            # If we render to a specific X offset, we need to adjust `draw`.
            # We can't easily offset `draw` operations without a transform.
            
            # Strategy: Render Left Column content assuming a "narrow screen" of `left_pane_width`
            # BUT we need to position it at `left_margin`?
            # If `left_pane_width` includes margins, and we position it at `left_margin`...
            # The User wants alignment to Date Center.
            # Let's define the "Left Column Context" as a virtual screen of width `left_pane_width`
            # position at `left_margin` might be tricky if we don't offset.
            # The Date is drawing at `left_margin`.
            # Its center is `left_col_center`.
            # If we define the Virtual Width such that its center is `left_col_center`.
            # virtual_width = left_col_center * 2. 
            # If left_col_center = 160 (e.g.), virtual_width = 320.
            # Then content centered in 320 will align with 160.
            
            virtual_col_width = int(left_col_center * 2)
            # Ensure it's wide enough for info blocks (at least 320px typically needed)
            # If date is short, `virtual_col_width` is small -> Info blocks will shrink/fail.
            # We might need to decouple "Date Alignment" from "Info Block Alignment" if Date is too short.
            # User requirement: "using the width of the date to center all other elements".
            # If Date is small, this request creates a bad UI.
            # I will assume "Date is typically wide enough" or strictly follow orders.
            # If explicitly requested, I will try to respect it, but clamp minimum width.
            
            min_col_width = 310 # Info blocks need space
            if virtual_col_width < min_col_width:
                 # If date is narrower, we center relative to the DATE, but extend width outwards
                 # Center X is fixed at `left_col_center`.
                 # We need virtual width `min_col_width` centered at `left_col_center`.
                 # This means drawing from `left_col_center - min_col_width/2` to `left_col_center + min_col_width/2`.
                 pass
            else:
                 min_col_width = virtual_col_width
            # Create a localized layout calculator
            original_layout = self.layout
            self.layout = LayoutCalculator(min_col_width, self.height)
            
            # Offsets for drawing
            # We need to shift drawing operations by `x_offset`.
            # Since we can't shift `draw`, we can't easily reuse `render_btc_price_block` etc IF they use `draw.text((absolute_x...))`.
            # They use `self.layout.get_centered_x()` which returns value 0..width.
            # So `x` returned is local to `min_col_width`.
            # We need to add `offset_x` to every drawing call? No, that requires rewriting all renderers.
            
            # Alternative: Render Info Blocks to a temporary image and paste it.
            # This is cleaner.
            
            # We will perform the rendering in Step 3 and 4 below to allow proper vertical centering.
            # (Deleted duplicate rendering logic here)

            # Update Y cursor for Hash Frame (which comes below info blocks)
            # Hash Frame / Block Info is rendered via `_render_block_info_with_data`
            # This function uses `self.layout` again effectively or `self.width`.
            # We want it in the Left Pane also.
            # Logic: `_render_block_info_with_data` is typically pinned to bottom.
            # In split screen, we want it pinned to bottom of Left Pane? Or Screen Bottom?
            # User: "hash frame is too low ... date and block height are centered over the entire screen, that is not correct"
            # So Hash Frame should be in the Left Column.
            
            # We can use the same "Render to separate image" trick for Block Info?
            # `_render_block_info_with_data` usually draws at `self.height - area`.
            # We can override `self.width` and `self.height` temporarily?
            # Let's try to just call it with a separate image context if possible?
            # No, `_render_block_info_with_data` takes `img` and `draw` of the main image.
            
            # We must override `self.width`.
            # And `self.layout`.
            
            # Override for Block Info
            orig_width = self.width
            self.width = min_col_width
            self.layout = LayoutCalculator(self.width, self.height)
            
            # --- 4. Render Block Info (Bottom of Left Column) ---
            # Calculate the space needed. 
            # We use the config block_height_area which is typically ~180px.
            block_info_height = self.block_height_area # Default 180
            
            # Create temp image for block info
            block_info_img = Image.new('RGBA', (min_col_width, block_info_height), (0,0,0,0))
            block_info_draw = ImageDraw.Draw(block_info_img)
            
            # We want it "glued to bottom", meaning the content layout inside `block_info_img` 
            # should appear at the bottom of `block_info_img`?
            # Or we simply paste `block_info_img` at the absolute bottom of main screen.
            
            # Render internal content. 
            # _render_block_info_with_data uses "self.height" to calculate positions if y_override is None.
            # If we pass y_override, it sets the `y` base.
            # We want the content to be at the bottom of `block_info_img`.
            # Content height is roughly `block_height_area` (180).
            # So if we render at y=0 of `block_info_img` (height=180), it fills it.
            # But the original vertical logic uses `y = self.height - (self.block_height_area - 10)`.
            # If `self.height` was 180, `y` = 180 - (180 - 10) = 10.
            # So passing `y_override=10` should work well for a 180px high image.
            
            # Also user wanted hash frame "slightly larger". 
            # We can force `max_width` to be `min_col_width` (full width of column).
            
            self._render_block_info_with_data(block_info_img, block_info_draw, block_height, block_hash, font_block_label,
                                            font_block_value, mempool_api, configured_fee,
                                            api_block_height, web_quality, y_override=10)
            
            # --- 3. Render Center Content (Holiday + Info Blocks) ---
            # Calculate available vertical space
            # Top: current_y (after date)
            # Bottom: self.height - block_info_height
            available_middle_top = current_y
            available_middle_bottom = self.height - block_info_height
            available_middle_height = available_middle_bottom - available_middle_top
            
            if available_middle_height < 0: available_middle_height = 0
            
            # --- Check how many info blocks fit ---
            remaining_height_for_info = available_middle_height
            if holiday_info:
                remaining_height_for_info -= (HOLIDAY_HEIGHT + 10)
                
            # If negative after holiday, maybe don't show info blocks at all?
            if remaining_height_for_info < 0: remaining_height_for_info = 0
            
            # Use same logic as vertical mode: calculate max blocks that fit
            # Each block takes INFO_BLOCK_HEIGHT + 10 margin
            max_blocks = remaining_height_for_info // (INFO_BLOCK_HEIGHT + 10)
            
            info_blocks_to_render = []
            if max_blocks > 0 and info_blocks:
                if len(info_blocks) > max_blocks:
                    print(f"⚠️ Landscape Mode: Not enough space for all blocks. Showing {int(max_blocks)} of {len(info_blocks)}")
                    info_blocks_to_render = random.sample(info_blocks, int(max_blocks))
                else:
                    info_blocks_to_render = info_blocks
            
            # Create a localized layout calculator for rendering
            # We need to measure content height first.
            
            # Temp image to capture content
            # Make it tall enough to hold everything initially
            content_canvas_height = max(self.height, 1000) 
            info_img = Image.new('RGBA', (min_col_width, content_canvas_height), (0,0,0,0))
            info_draw = ImageDraw.Draw(info_img)
            
            info_y = 0
            # Render Holiday
            if holiday_info:
                info_draw.rounded_rectangle(
                    [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, info_y),
                     (min_col_width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, info_y + HOLIDAY_HEIGHT)],
                    radius=BLOCK_RADIUS,
                    fill=self.get_color("info_bg", web_quality),
                    outline=self.get_color("info_outline", web_quality),
                    width=4
                )
                self._render_holiday_info(info_draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        info_y, HOLIDAY_HEIGHT, web_quality)
                info_y += HOLIDAY_HEIGHT + 10

            # Render Info Blocks
            for i, (block_fn, block_data) in enumerate(info_blocks_to_render):
                 try:
                    if block_fn == self.render_wallet_balances_block:
                        block_fn(info_draw, info_y, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                    else:
                        block_fn(info_draw, info_y, font_block_label, font_block_value, block_data, web_quality)
                    
                    info_y += INFO_BLOCK_HEIGHT + 10
                 except Exception as e:
                    print(f"Error render info block landscape: {e}")
            
            # Total content height used
            total_content_height = info_y
            if total_content_height > 0:
                total_content_height -= 10 # Remove last margin
            
            # Crop the info image to actual content
            info_img = info_img.crop((0, 0, min_col_width, total_content_height + 1)) # +1 to avoid 0 height error
            
            # Determine Y position to Center vertically in available space
            if total_content_height < available_middle_height:
                info_paste_y = available_middle_top + (available_middle_height - total_content_height) // 2
            else:
                # Content exceeds space, start at top (or clip?) 
                # Let's start at top to show most important info
                info_paste_y = available_middle_top
            
            # Restore State
            self.width = orig_width
            self.layout = original_layout
            
            # Paste Info Column
            paste_x = int(left_col_center - min_col_width // 2)
            img.paste(info_img, (paste_x, info_paste_y), info_img)
            
            # Paste Block Info at exact bottom
            block_info_paste_y = self.height - block_info_height
            img.paste(block_info_img, (paste_x, block_info_paste_y), block_info_img)
            
            # 4. Render Meme (Right Pane)
            # Left pane occupies up to `paste_x + min_col_width`.
            # Or just `left_margin + date_width + margin`.
            # Let's define the start of Right Pane.
            right_pane_start_x = paste_x + min_col_width + 5
            # Ensure it doesn't overlap excessively 
            # (min_col_width centered at date center might extend left of date start? No, date center is width/2)
            
            if right_pane_start_x < left_margin + date_width + 10:
                 right_pane_start_x = int(left_margin + date_width + 10)
                 
            available_meme_width = self.width - right_pane_start_x - 5
            available_meme_height = self.height - 10 # Padding (5 top + 5 bottom)
            
            if available_meme_width > 50 and meme_path:
                try:
                    meme_img = Image.open(meme_path)
                    # Scale to fit
                    aspect = meme_img.width / meme_img.height
                    
                    # Fit to box
                    target_w = min(available_meme_width, int(available_meme_height * aspect))
                    target_h = int(target_w / aspect)
                    
                    if target_h > available_meme_height:
                         target_h = available_meme_height
                         target_w = int(target_h * aspect)
                         
                    meme_img = meme_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    
                    # Center in Right Pane
                    meme_x = right_pane_start_x + (available_meme_width - target_w) // 2
                    meme_y = (self.height - target_h) // 2
                    
                    meme_img = meme_img.convert("RGBA")
                    meme_img = self.add_rounded_corners(meme_img, radius=20)
                    img.paste(meme_img, (meme_x, meme_y), meme_img)
                    
                except Exception as e:
                    print(f"Error landscape meme: {e}")

            return img

        # Date
        # y = self.draw_centered(draw, self.get_localized_date(), top_y, font_date, fill=self.get_color("date_holiday" if holiday_info else "date_normal", web_quality))
        # Choose gradient colors (can use hash frame colors or any theme keys)
        start_color = self.get_color("hash_start", web_quality)
        end_color = self.get_color("hash_end", web_quality)

        # Use the date_text we already calculated
        bbox = font_date.getbbox(date_text)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = 20
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

        # Define constants needed for calculations
        BLOCK_MARGIN = 15
        HOLIDAY_HEIGHT = 0
        if holiday_info:
            # Calculate exact height needed based on text content
            title_text = holiday_info.get("title", "Bitcoin Holiday")
            desc_text = holiday_info.get("description", "")
            
            # Title height
            title_bbox = font_holiday_title.getbbox(title_text)
            title_height = title_bbox[3] - title_bbox[1]
            
            # Description height (with word wrapping at 50 characters)
            desc_lines = self._wrap_text_at_chars(desc_text, max_chars=50)
            
            desc_bbox = font_holiday_desc.getbbox("Ay")
            line_height = desc_bbox[3] - desc_bbox[1]
            desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * 4
            
            # Total height: Title + Gap(3) + Description + Padding(24)
            # 12px top + 12px bottom = 24px total padding for balanced spacing
            HOLIDAY_HEIGHT = title_height + 3 + desc_total_height + 24
        # Reserve space for hash frame - calculate where it actually renders
        # The hash frame rendering in vertical mode uses: y = self.height - (self.block_height_area - 10)
        hash_frame_y_position = self.height - (self.block_height_area - 10) + 6
        meme_bottom_y = hash_frame_y_position  # Content can go up to where hash frame visibly starts
        # Content starts after the date. Holiday is part of the content flow.
        content_top_y = date_bottom_y
        available_content_height = meme_bottom_y - content_top_y

        prioritize_large_meme = self.config.get("prioritize_large_scaled_meme", False)

        # Define standard spacing unit for balanced layout
        # Increase spacing when holiday is present to ensure visual separation
        STANDARD_SPACING = 25 if holiday_info else 20  # Base spacing between major elements

        # Info blocks setup - moved after data initialization
        # info_blocks = []
        # config = self.config
        # if config.get("show_btc_price_block", True):
        #     info_blocks.append((self.render_btc_price_block, btc_price_data))
        # if config.get("show_bitaxe_block", True):
        #     info_blocks.append((self.render_bitaxe_block, bitaxe_data))
        # if config.get("show_wallet_balances_block", True):
        #     info_blocks.append((self.render_wallet_balances_block, wallet_data))

        # Calculate space required for info blocks
        def calculate_info_blocks_space(config_ref):
            """Calculate the total height needed for info blocks including margins."""
            block_count = 0
            if config_ref.get("show_btc_price_block", True):
                block_count += 1
            if config_ref.get("show_bitaxe_block", True):
                block_count += 1
            if config_ref.get("show_wallet_balances_block", True):
                block_count += 1
            
            if block_count == 0:
                return 0
            # Each block: INFO_BLOCK_HEIGHT + BLOCK_MARGIN, plus one extra BLOCK_MARGIN at top
            return block_count * (INFO_BLOCK_HEIGHT + BLOCK_MARGIN) + BLOCK_MARGIN

        info_blocks_space = calculate_info_blocks_space(self.config)

        if prioritize_large_meme:
            # --- PRIORITY ORDER: Meme (max size) > Holiday > Info Blocks ---
            # Step 1: Size meme to MAXIMUM possible size
            meme_img = None
            meme_height = 0
            meme_width = 0
            
            if meme_path:
                try:
                    meme_img = Image.open(meme_path)
                    aspect_ratio = meme_img.width / meme_img.height
                    max_width = self.width - 40
                    
                    # Calculate maximum meme height with only mandatory gaps (top + bottom)
                    min_gaps = 2 * STANDARD_SPACING  # Top gap + Bottom gap
                    max_meme_height = available_content_height - min_gaps
                    
                    # Scale meme to fit max width and max height
                    scaled_width = min(max_width, int(max_meme_height * aspect_ratio))
                    scaled_height = int(scaled_width / aspect_ratio)
                    if scaled_height > max_meme_height:
                        scaled_height = max_meme_height
                        scaled_width = int(scaled_height * aspect_ratio)
                    
                    meme_img = meme_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                    meme_height = scaled_height
                    meme_width = scaled_width
                except Exception as e:
                    print(f"⚠️ Error loading meme for scaling: {e}")
            
            # --- Step 2: Calculate remaining space after meme ---
            space_after_meme = available_content_height - meme_height
            
            # --- Step 3: Try to fit Holiday (higher priority than info blocks) ---
            holiday_space = 0
            if holiday_info:
                # Space needed: gap after meme + holiday + gap before hash = 3 gaps total + holiday
                space_needed_for_holiday = (3 * STANDARD_SPACING) + HOLIDAY_HEIGHT
                if space_after_meme >= space_needed_for_holiday:
                    holiday_space = HOLIDAY_HEIGHT
                else:
                    print(f"⚠️ Not enough space for holiday. Need {space_needed_for_holiday}px, have {space_after_meme}px")
            
            # --- Step 4: Try to fit Info Blocks in remaining space ---
            remaining_after_holiday = space_after_meme - holiday_space
            
            # Calculate how many info blocks fit
            # If we have holiday: need gaps: top, holiday-meme, meme-blocks, blocks-hash = 4 gaps
            # If no holiday: need gaps: top, meme-blocks, blocks-hash = 3 gaps
            base_gaps = (4 * STANDARD_SPACING) if holiday_space else (3 * STANDARD_SPACING)
            space_for_blocks = remaining_after_holiday - base_gaps
            
            info_blocks_to_render = []
            if space_for_blocks > 0 and info_blocks:
                # Calculate how many blocks fit
                # First block: INFO_BLOCK_HEIGHT
                # Each additional block: BLOCK_MARGIN + INFO_BLOCK_HEIGHT
                max_blocks = 0
                if space_for_blocks >= INFO_BLOCK_HEIGHT:
                    max_blocks = 1
                    remaining = space_for_blocks - INFO_BLOCK_HEIGHT
                    additional = remaining // (BLOCK_MARGIN + INFO_BLOCK_HEIGHT)
                    max_blocks += int(additional)
                
                if max_blocks > 0:
                    if len(info_blocks) > max_blocks:
                        info_blocks_to_render = random.sample(info_blocks, int(max_blocks))
                        print(f"ℹ️ Showing {max_blocks} of {len(info_blocks)} info blocks (meme prioritized)")
                    else:
                        info_blocks_to_render = info_blocks
                else:
                    print(f"ℹ️ No space for info blocks (meme takes {meme_height}px of {available_content_height}px)")
            
            # --- Step 5: Calculate balanced vertical spacing with actual content ---
            # When no holiday and no info blocks, center the meme vertically
            if not holiday_space and len(info_blocks_to_render) == 0:
                # Center meme between date and hash frame
                center_point = content_top_y + (available_content_height // 2)
                current_y = center_point - (meme_height // 2) if meme_height > 0 else center_point
            else:
                # Calculate total content height (actual heights, no gaps included)
                total_content_height = 0
                if holiday_space:
                    total_content_height += holiday_space
                total_content_height += meme_height
                if len(info_blocks_to_render):
                    # Include margins between info blocks (not before first or after last)
                    total_content_height += len(info_blocks_to_render) * INFO_BLOCK_HEIGHT + (len(info_blocks_to_render) - 1) * BLOCK_MARGIN
                
                # Calculate remaining space to distribute evenly across gaps
                remaining_space = available_content_height - total_content_height
                
                # Calculate number of gaps for even distribution
                # Gaps: Top (after date) + Between elements + Bottom (before hash)
                num_gaps = 2  # Top and bottom gaps are mandatory
                if holiday_space: num_gaps += 1  # gap between holiday and meme
                if len(info_blocks_to_render): num_gaps += 1  # gap between meme and info blocks
                
                # Distribute spacing evenly across all gaps, ensuring minimum spacing
                gap_size = max(STANDARD_SPACING, remaining_space // num_gaps) if num_gaps > 0 else STANDARD_SPACING
                
                # Start positioning elements with balanced spacing
                current_y = content_top_y + gap_size
                    
            # Render holiday (centered in assigned space)
            if holiday_space:
                # Draw background
                draw.rounded_rectangle(
                    [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, current_y),
                     (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, current_y + HOLIDAY_HEIGHT)],
                    radius=BLOCK_RADIUS,
                    fill=self.get_color("info_bg", web_quality),
                    outline=self.get_color("info_outline", web_quality),
                    width=4
                )
                
                self._render_holiday_info(draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        current_y, HOLIDAY_HEIGHT, web_quality)
                current_y += holiday_space + gap_size  # Add gap after holiday

            # Render meme (centered horizontally)
            if meme_img:
                meme_x = (self.width - meme_width) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)  
                img.paste(meme_img, (meme_x, current_y), meme_img)
                current_y += meme_height
            else:
                self._render_fallback_content(img, draw, current_y, meme_height,
                                            font_holiday_title, web_quality)
                current_y += meme_height
            
            # Add gap before info blocks for even distribution
            if len(info_blocks_to_render):
                current_y += gap_size
                
            if len(info_blocks_to_render):
                # Render info blocks without the extra BLOCK_MARGIN wrapper
                # The first block starts at current_y (already includes gap_size)
                pass

            for i, (block_fn, block_data) in enumerate(info_blocks_to_render):
                # Render each info block at current_y position
                info_vertical_offset = current_y + 10  # Small adjustment for visual centering
                try:
                    if block_fn == self.render_wallet_balances_block:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                    else:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality)
                except Exception as e:
                    print(f"⚠️ Error rendering info block {block_fn.__name__}: {e}")
                
                # Move to next block position (height + margin between blocks)
                current_y += INFO_BLOCK_HEIGHT
                if i < len(info_blocks_to_render) - 1:  # Add margin between blocks, but not after the last one
                    current_y += BLOCK_MARGIN

        else:
            # --- prioritize_large_scaled_meme == False ---
            # Treat all elements (Holiday, Meme, Info Block 1, Info Block 2, ...) as separate items
            # and distribute vertical space evenly between them, as well as top and bottom.
            
            # 1. Count elements and gaps
            num_elements = 1  # Meme is always present (or fallback)
            if holiday_info:
                num_elements += 1
            
            # Add count of info blocks
            num_info_blocks = len(info_blocks)
            num_elements += num_info_blocks
            
            # Gaps = Elements + 1 (Top, between each, Bottom)
            num_gaps = num_elements + 1
            
            # 2. Calculate fixed content height (Holiday + Info Blocks raw height)
            # Note: We don't include fixed margins here, as we'll use dynamic gaps
            fixed_content_height = 0
            if holiday_info:
                fixed_content_height += HOLIDAY_HEIGHT
            
            fixed_content_height += num_info_blocks * INFO_BLOCK_HEIGHT
            
            # 3. Calculate Gaps estimate to find available Meme Height
            # We use STANDARD_SPACING as a minimum/target estimate
            estimated_total_gaps = num_gaps * STANDARD_SPACING
            
            # 4. Calculate Max Meme Height
            max_meme_height = available_content_height - fixed_content_height - estimated_total_gaps
            if max_meme_height < 50: 
                max_meme_height = 50  # Minimum height constraint

            # 5. Determine actual Meme Height
            meme_img = None
            meme_height = 0
            meme_width = 0
            if meme_path:
                try:
                    meme_img = Image.open(meme_path)
                    aspect_ratio = meme_img.width / meme_img.height
                    max_width = self.width - 40
                    
                    scaled_width = min(max_width, int(max_meme_height * aspect_ratio))
                    scaled_height = int(scaled_width / aspect_ratio)
                    if scaled_height > max_meme_height:
                        scaled_height = max_meme_height
                        scaled_width = int(scaled_height * aspect_ratio)
                    meme_img = meme_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                    meme_height = scaled_height
                    meme_width = scaled_width
                except Exception as e:
                    print(f"⚠️ Error loading meme for scaling: {e}")
            
            if not meme_img:
                # Fallback height if no meme
                meme_height = max(50, max_meme_height)
            
            # 6. Calculate Actual Total Content Height
            total_content_height = fixed_content_height + meme_height
            
            # 7. Calculate Real Remaining Space and Gap Size
            remaining_space = available_content_height - total_content_height
            
            # Distribute spacing evenly, ensuring at least STANDARD_SPACING if possible, 
            # but allow shrinking if space is tight (which shouldn't happen with our meme calc)
            # If remaining space is large (small meme), this gap will grow to center/distribute everything.
            gap_size = max(5, remaining_space // num_gaps) if num_gaps > 0 else STANDARD_SPACING
            
            # 8. Render Elements Loop
            current_y = content_top_y + gap_size
            
            # Render Holiday
            if holiday_info:
                # Draw background
                draw.rounded_rectangle(
                    [(SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN, current_y),
                     (self.width - SECTION_SIDE_PADDING - BLOCK_INNER_MARGIN, current_y + HOLIDAY_HEIGHT)],
                    radius=BLOCK_RADIUS,
                    fill=self.get_color("info_bg", web_quality),
                    outline=self.get_color("info_outline", web_quality),
                    width=4
                )

                self._render_holiday_info(draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        current_y, HOLIDAY_HEIGHT, web_quality)
                current_y += HOLIDAY_HEIGHT + gap_size

            # Render Meme
            if meme_img:
                meme_x = (self.width - meme_width) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)
                img.paste(meme_img, (meme_x, current_y), meme_img)
                current_y += meme_height
            else:
                self._render_fallback_content(img, draw, current_y, meme_height,
                                            font_holiday_title, web_quality)
                current_y += meme_height
            
            # Render Info Blocks
            # No wrapper background for the group is drawn in this mode, as they are distributed elements
            for i, (block_fn, block_data) in enumerate(info_blocks):
                # Add gap before each info block (creates uniform spacing with meme and between blocks)
                current_y += gap_size
                
                try:
                    if block_fn == self.render_wallet_balances_block:
                        block_fn(draw, current_y, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                    else:
                        block_fn(draw, current_y, font_block_label, font_block_value, block_data, web_quality)
                    
                    # Move to next position: add block height only (gap is added at start of next iteration or remains as bottom gap)
                    current_y += INFO_BLOCK_HEIGHT
                except Exception as e:
                    print(f"⚠️ Error rendering info block {block_fn.__name__}: {e}")
                    # If error, skip this block and continue

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
                print(f"⚙️ Using pre-selected meme: {meme_path}")
                
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
        
        # --- VERTICAL MODE (Legacy Logic) ---
        if self.orientation == "vertical":
             padding = 40
             extra_space = 8
             font = ImageFont.truetype(self.font_mono, 11)
             
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
                     
             return

        font_size = 11
        # --- Optional scaling if max_width is given ---
        if max_width is not None:
            # Calculate required width for standard font 11
            # 23 pairs in top row. Each pair (2 chars) takes roughly:
            # bbox("0") width * 2 + extra_space.
            # Plus gaps between pairs (6px).
            # This is an approximation since we don't know the font metrics perfectly without loading.
            
            # Load font to measure
            temp_font = ImageFont.truetype(self.font_mono, 11)
            bbox = temp_font.getbbox("0")
            cw = bbox[2] - bbox[0]
            # Top row logic: 2 chars then gap. 
            # Total width = 46 chars + 23 gaps.
            # We use gap = 3 (reduced from 6 to fit larger font)
            
            estimated_full_width = (46 * cw) + (23 * 3) + 20 # +20 safety
            
            if estimated_full_width > max_width:
                 scale_factor = max_width / estimated_full_width
                 font_size = int(11 * scale_factor)
                 if font_size < 1: font_size = 1
                 
                 # Adjust padding/spacing by scale too
                 padding = int(padding * scale_factor)
                 extra_space = int(max(1, 8 * scale_factor)) # Keep at least 1px

        font = ImageFont.truetype(self.font_mono, font_size)
    
        # Character size
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
        top_positions = []
        x = x_init
        y = y_init
        for i, c in enumerate(top_chars):
            draw.text((x, y), c, fill=top_chars_colors[i], font=font)
            top_positions.append(x)
            x +=  int(char_w)
            if (i + 1) % 2 == 0:
               x += 3 # Reduced spacing

        # --- LEFT VERTICAL SIDE with horizontal pairs ---
        x = top_positions[0]  # align under first char of top edge
        y = y_init + int(char_h) + extra_space 
        i = 0
        while i < len(left_chars):
            pair = left_chars[i:i+2]
            draw.text((x, y), pair, fill=left_chars_colors[i], font=font)  # draw both chars on the same line
            y +=  int(char_h) + extra_space # move down for next pair
            i += 2

        # --- RIGHT VERTICAL SIDE with horizontal pairs ---
        x = top_positions[-2] + 1 # align under last char of top edge
        y = y_init + int(char_h) + extra_space 
        i = 0
        while i < len(right_chars):
            pair = right_chars[i:i+2]
            draw.text((x, y), pair, fill=right_chars_colors[i], font=font)
            y +=  int(char_h) + extra_space
            i += 2

        # --- BOTTOM EDGE with grouped pairs ---
        # Auto-calculate Y to connect with vertical sides
        bottom_y_start = y 
        
        # User requested "bottom line needs to be higher". 
        # Move up further to close the gap (2x char height)
        y = bottom_y_start - int(2 * char_h)

        x = x_init
        for i, c in enumerate(bottom_chars):
            draw.text((x, y), c, fill=bottom_chars_colors[i], font=font)
            x += int(char_w)
            if (i + 1) % 2 == 0:
                x +=  3 # Reduced spacing

    def _render_block_info_with_data(self, img, draw, block_height, block_hash, font_block_label,
                                    font_block_value, mempool_api, configured_fee,
                                    api_block_height, web_quality, y_override=None):
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
        
        if y_override is not None:
            y = y_override
        elif self.orientation == "vertical":
            y = self.height - (self.block_height_area - 10)  # Move up by 10px from original position
        else:
            y = self.height - (self.block_height_area - 70)  # Adjust for horizontal layout
        
        # Calculate Max Width for Responsive Layout
        # Only constrain width in landscape mode. For vertical, we rely on standard sizes (legacy behavior).
        if self.orientation == "horizontal":
            max_available_width = self.width - 24 
        else:
            max_available_width = None
        
        # Format block height string
        if mempool_api:
            formatted_height = mempool_api.format_block_height(display_block_height)
        else:
            try:
                height_int = int(display_block_height)
                formatted_height = f"{height_int:,}".replace(",", ".")
            except (ValueError, TypeError):
                formatted_height = str(display_block_height)

        # Scale Block Height Font if needed
        used_font_block_value = font_block_value
        bbox = used_font_block_value.getbbox(formatted_height)
        text_width = bbox[2] - bbox[0]
        
        if max_available_width and text_width > max_available_width - 80: # More padding for frame
             # Calculate scale ratio (add some margin)
             ratio = (max_available_width - 80) / (text_width + 10)
             # Extract size from font object? No standard way.
             # Standard size is 124.
             new_size = int(124 * ratio)
             if new_size < 20: new_size = 20 # Minimum safeguard
             try:
                 used_font_block_value = ImageFont.truetype(self.font_block_height, new_size)
             except Exception as e:
                 print(f"Error scaling font: {e}")

        # Draw "Block Height" label
        # None
        
        if self.orientation == "vertical":
            # --- VERTICAL MODE (Legacy Logic) ---
            # Draw at (x, y), black text, max width 760px
            self.draw_hash_frame(draw, 12, y+3, block_hash, web_quality=web_quality)
            y = y + 24
            
            # Draw block height with color based on current fees (move up by 10px)
            value_y = y - 25
            bbox = font_block_value.getbbox(formatted_height)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y + 10, font_block_value, block_height_start_color, block_height_end_color)
            
            # Add fee information as small text if available
            if configured_fee is not None:
                # Fee parameter translation logic replicated locally or reused if possible?
                # The surrounding code already sets up fee variables but let's reuse the structure at the end of the function if possible?
                # The current structure has fee logic embedded at the end.
                # I will define `fee_y` here and let the common block handle text generation if possible, but the positioning is specific.
                
                # Get fee text (duplicate logic for safety or refactor later)
                fee_parameter = self.config.get("fee_parameter", "minimumFee")
                fee_type_keys = {
                    "fastestFee": "fastest", "halfHourFee": "half_hour", "hourFee": "hour", "economyFee": "economy", "minimumFee": "minimum"
                }
                fee_key = fee_type_keys.get(fee_parameter, "minimum")
                fee_type_display = self.t.get(fee_key, "Unknown")
                fee_text = f"{fee_type_display}: {configured_fee} sat/vB"
                
                try:
                    font_small = ImageFont.truetype(self.font_regular, 12)
                except:
                    font_small = font_block_label
                    
                bbox = font_block_value.getbbox(formatted_height)
                fee_y = value_y + bbox[3] - bbox[1] + 42
                
                color = block_height_start_color if web_quality else block_height_end_color
                self.draw_centered(draw, fee_text, fee_y, font_small, color)
                
            return # Exit early for vertical

        # --- LANDSCAPE/RESPONSIVE MODE ---
        # Hash frame 
        # width auto-scaled by draw_hash_frame if max_width passed
        # User requested: "slightly moved to the right". Old x=24. Adjusted to 32 (halfway).
        self.draw_hash_frame(draw, 32, y, block_hash, web_quality=web_quality, max_width=max_available_width)
        
        # Center Block Height Text inside the frame (approx y+15)
        # User requested: "Can you even further move up the block height?". Old value_y=y+25. New = y+15.
        value_y = y + 15
        
        bbox = used_font_block_value.getbbox(formatted_height)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y, used_font_block_value, block_height_start_color, block_height_end_color)
        
        # Add fee information as small text if available
        if configured_fee is not None:
            # Get the configured fee parameter to display the fee type
            fee_parameter = self.config.get("fee_parameter", "minimumFee")
            
            # Map technical fee parameter names to translation keys
            fee_type_keys = {
                "fastestFee": "fastest",
                "halfHourFee": "half_hour", 
                "hourFee": "hour",
                "economyFee": "economy",
                "minimumFee": "minimum"
            }
            
            # Get the translated fee type name
            fee_key = fee_type_keys.get(fee_parameter, "minimum")
            fee_type_display = self.t.get(fee_key, "Unknown")
            fee_text = f"{fee_type_display}: {configured_fee} sat/vB"
            
            try:
                font_small = ImageFont.truetype(self.font_regular, 12)
            except:
                font_small = font_block_label
            
            # Draw fee info in smaller text below block height
            bbox = used_font_block_value.getbbox(formatted_height)
            text_height = bbox[3] - bbox[1]
            # User requested to fix overlap: Increased gap from 15 to 25
            fee_y = value_y + text_height + 25

            # Use darker tone for e-ink, use brighter tone for web (TODO: use darker for light mode as well?)
            if web_quality:
                self.draw_centered(draw, fee_text, fee_y, font_small, block_height_start_color)
            else:
                self.draw_centered(draw, fee_text, fee_y, font_small, block_height_end_color)

        # Draw shortened hash
        # (covered by frame)
        
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
                
                print(f"⚙️ Rendered fallback meme: {meme_path}")
                
            except Exception as e:
                               print(f"⚠️ Error rendering fallback meme {meme_path}: {e}")
        else:
            print("⚠️ No fallback meme available")
    

    def _render_holiday_info(self, draw, holiday_info, font_title, font_desc, 
                           holiday_box_top_y, holiday_height, web_quality=False):
        """Render Bitcoin holiday information dynamically centered in available space.
        
        Args:
            draw (ImageDraw): Drawing context
            holiday_info (dict): Holiday information
            font_title (ImageFont): Font for holiday title
            font_desc (ImageFont): Font for holiday description
            holiday_box_top_y (int): Top Y position of the holiday box
            holiday_height (int): Reserved height for holiday content
            web_quality (bool): True for web display, False for e-ink
        """
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
            
        # Calculate description lines with word wrapping at 50 characters
        desc_lines = self._wrap_text_at_chars(desc_text, max_chars=50)
        print(f"   📝 Holiday description wrapped into {len(desc_lines)} line(s)")
            
        # Calculate total description height
        desc_bbox = font_desc.getbbox("Ay")  # Sample text for line height
        line_height = desc_bbox[3] - desc_bbox[1]
        desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * LINE_SPACING_MULTILINE
            
        # Calculate total holiday content height
        total_holiday_height = title_height + HOLIDAY_TITLE_DESC_GAP + desc_total_height
            
        # Calculate equal top and bottom padding
        vertical_padding = (holiday_height - total_holiday_height) // 2
        
        y = holiday_box_top_y + vertical_padding - 5
            
        # Render the holiday title
        y = self.draw_centered(draw, title_text, y, font_title, fill=title_color)
            
        # Render the holiday description lines
        y += HOLIDAY_TITLE_DESC_GAP
        for line in desc_lines:
            bbox = font_desc.getbbox(line)
            text_height = bbox[3] - bbox[1]
            x = self.layout.get_text_centered_x(bbox)
            draw.text((x, y), line, font=font_desc, fill=desc_color)
            y += text_height + LINE_SPACING_MULTILINE
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
            print("⚙️ e-Paper display disabled in configuration - skipping hardware display")
            return True
        
        # When called from main app, the subprocess method handles the display
        # This method just returns success to avoid blocking the threading
        print("⚙️ E-paper display handled by subprocess - returning immediately")
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
            
            print(f"⚙️ Running fallback display command: {' '.join(cmd)}")
            
            # Run the display script with timeout
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            if result.returncode == 0:
                print("✅ Image displayed on e-Paper via show_image.py (fallback)")
                if result.stdout:
                    print(f"Output: {result.stdout}")
                return True
            else:
                print(f"❌ Error displaying on e-Paper (exit code {result.returncode}): {result.stderr}")
                if result.stdout:
                    print(f"Output: {result.stdout}")
                return False
                    
        except subprocess.TimeoutExpired:
            print("❌ Timeout while displaying image on e-Paper")
            return False
        except Exception as e:
            print(f"❌ Error displaying on e-Paper: {e}")
            return False
