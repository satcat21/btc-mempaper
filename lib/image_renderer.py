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
from PIL import Image, ImageDraw, ImageFont, ImageOps
from babel.dates import format_date

from utils.webp_probe_cache import cached_probe

# Probe whether PIL can decode WebP without SIGILL.
# On ARMv6 with a NEON-compiled libwebp, both encode and decode cause SIGILL
# (an uncatchable signal). Running the probe in a subprocess isolates the crash.
def _probe_webp_decode() -> bool:
    try:
        r = subprocess.run(
            [sys.executable, '-c',
             'from PIL import Image; import io; '
             'buf=io.BytesIO(); Image.new("RGB",(1,1)).save(buf,"WEBP"); '
             'buf.seek(0); Image.open(buf).load()'],
            capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

_WEBP_PIL_DECODE_SAFE = cached_probe('decode_ok', _probe_webp_decode)

from lib.btc_holidays import btc_holidays
from utils.color_lut import ColorLUT
from utils.translations import translations as _TRANSLATIONS
from lib.btc_price_api import BitcoinPriceAPI
from lib.bitaxe_api import BitaxeAPI
from lib.wallet_balance_api import WalletBalanceAPI

# ---------------------------------------------------------------------------
# Emoji support — optional pilmoji dependency with persistent disk cache.
# ---------------------------------------------------------------------------
# Loaded lazily (on first text render that actually contains emoji), not at
# module import: pilmoji pulls in the 'emoji' package's large Unicode tables,
# ~4s of import cost on a Pi Zero that's wasted on any render that never
# needs it (e.g. the setup/hotspot QR screen).
_PILMOJI_AVAILABLE = None  # None = not yet probed
_Pilmoji = None
_CachedEmojiSource = None


def _ensure_pilmoji_loaded():
    global _PILMOJI_AVAILABLE, _Pilmoji, _CachedEmojiSource
    if _PILMOJI_AVAILABLE is not None:
        return _PILMOJI_AVAILABLE

    try:
        import hashlib as _hashlib
        from pilmoji import Pilmoji as _PilmojiCls
        from pilmoji.source import TwitterEmojiSource as _TwitterEmojiSource

        class _CachedEmojiSourceCls(_TwitterEmojiSource):
            """TwitterEmojiSource with a persistent on-disk cache.

            Emoji images are downloaded once from Twitter's CDN and stored under
            ``cache/emoji_cache/``.  Subsequent renders read from disk, so the
            app works offline after a warm-up pass.
            """
            _CACHE_DIR = os.path.join("cache", "emoji_cache")

            def request(self, url: str) -> bytes:
                os.makedirs(self._CACHE_DIR, exist_ok=True)
                key = _hashlib.md5(url.encode()).hexdigest() + ".png"
                cache_file = os.path.join(self._CACHE_DIR, key)
                if os.path.exists(cache_file):
                    with open(cache_file, "rb") as fh:
                        return fh.read()
                data = super().request(url)
                try:
                    with open(cache_file, "wb") as fh:
                        fh.write(data)
                except OSError:
                    pass
                return data

        _Pilmoji = _PilmojiCls
        _CachedEmojiSource = _CachedEmojiSourceCls
        _PILMOJI_AVAILABLE = True
    except ImportError:
        _PILMOJI_AVAILABLE = False

    return _PILMOJI_AVAILABLE

COLOR_SETS = {
    "light": {
        "background": "#ffffff",
        "date_normal": "#222222",
        "date_holiday": "#b22222",
        "holiday_start": "#F7931A",
        "holiday_end": "#C62828",
        "btc_price": "#17805B",      # darker green for BTC price (was #228B22)
        "moscow_time": "#17805B",    # darker blue for Moscow time (was #4682B4)
        "hashrate": "#B89C1D",       # darker gold for Bitaxe (was #DAA520)
        "found_blocks": "#B89C1D",   # same as hashrate
        "info_header": "#222222",
        "info_value": "#222222",
        "info_unit": "#808080",
        "info_bg": "#F8F9FA",
        "info_outline": "#E9ECEF",
        "hash_start": "#1c82c0",     # medium blue (shifted ~35% towards dark mode #4FC3F7)
        "hash_end": "#c040a8",       # pink-magenta (shifted towards pink from purple)
        "green": "#388E3C",          # Material Green (darker)
        "yellow": "#FFA000",         # Material Amber (darker)
        "orange": "#F57C00",         # Material Orange (darker)
        "red": "#C62828",            # Material Red (darker)
        "blue": "#1976D2",           # Material Blue (darker)
        "black": "#343a40",
        "wallet_balance": "#1565C0", # darker blue for wallet balance
        "fiat_balance": "#1565C0",   # darker green for fiat balance
        "donation": "#F7931A",       # Bitcoin orange for donation block
        "countdown": "#C55A00",      # dark amber-orange for supply countdown
        "halving": "#1565C0",        # deep blue for halving countdown
        "network_hashrate": "#6A1B9A",  # deep purple for network hashrate
        "network_difficulty": "#6A1B9A",  # same purple for difficulty
    },
    "dark": {
        "background": "#1a1a1f",
        "date_normal": "#BA68C8",
        "date_holiday": "#09a3ba",
        "holiday_start": "#F7931A",
        "holiday_end": "#FF6F6F",
        "btc_price": "#00c896",
        "moscow_time": "#00c896",
        "hashrate": "#ffe566",
        "found_blocks": "#ffe566",
        "info_header": "#ffffff",
        "info_value": "#ffffff",
        "info_unit": "#6a6a78",
        "info_bg": "#1a1a1f",
        "info_outline": "#2a2a32",
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
        "donation": "#F7931A",        # Bitcoin orange for donation block
        "countdown": "#FF9E40",       # warm orange for supply countdown
        "halving": "#4FC3F7",         # sky blue for halving countdown
        "network_hashrate": "#CE93D8",   # soft purple for network hashrate
        "network_difficulty": "#CE93D8", # same soft purple for difficulty
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

# Device dimensions mapping (width x height in landscape orientation)
# Source: device hardware specifications
DEVICE_DIMENSIONS = {
    # Native Waveshare displays
    "epd13in3E": (1600, 1200),
    "epd13in3k": (1600, 1200),
    "epd7in3f": (800, 480),
    # Waveshare via omni-epd (legacy format)
    "waveshare_epd.epd13in3E": (1600, 1200),
    "waveshare_epd.epd13in3k": (1600, 1200),
    "waveshare_epd.epd7in3f": (800, 480),
    "waveshare_epd.epd5in83_v2": (648, 480),
    "waveshare_epd.epd4in2": (400, 300),
    "waveshare_epd.epd2in7": (264, 176),
    # Inky displays
    "inky.auto": (600, 448),
    "inky.impression": (600, 448),
    "inky.what_red": (400, 300),
    "inky.what_yellow": (400, 300),
    "inky.what_black": (400, 300),
    # Mock display
    "omni_epd.mock": (800, 600),
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

# Baseline canvas sizes used for the original layout design.
BASE_CANVAS_VERTICAL_WIDTH = 480
BASE_CANVAS_VERTICAL_HEIGHT = 800
BASE_CANVAS_HORIZONTAL_WIDTH = 800
BASE_CANVAS_HORIZONTAL_HEIGHT = 480

# Baseline layout constants (immutable references for dynamic scaling).
BASE_INFO_BLOCK_HEIGHT = INFO_BLOCK_HEIGHT
BASE_ELEMENT_MARGIN = ELEMENT_MARGIN
BASE_CARD_RADIUS = CARD_RADIUS
BASE_SIDE_PADDING = SIDE_PADDING
BASE_TOP_PADDING = TOP_PADDING
BASE_BLOCK_HEIGHT_AREA = BLOCK_HEIGHT_AREA
BASE_BLOCK_INNER_MARGIN = BLOCK_INNER_MARGIN
BASE_LABEL_PADDING_TOP = LABEL_PADDING_TOP
BASE_LABEL_TO_VALUE_SPACING = LABEL_TO_VALUE_SPACING
BASE_LINE_SPACING_DEFAULT = LINE_SPACING_DEFAULT
BASE_LINE_SPACING_MULTILINE = LINE_SPACING_MULTILINE
BASE_HOLIDAY_TITLE_DESC_GAP = HOLIDAY_TITLE_DESC_GAP
BASE_HOLIDAY_PADDING = HOLIDAY_PADDING
BASE_FONT_SIZE_SMALL_LABEL = FONT_SIZE_SMALL_LABEL
BASE_FONT_SIZE_LARGE_VALUE = FONT_SIZE_LARGE_VALUE
BASE_FONT_SIZE_BLOCK_VALUE = FONT_SIZE_BLOCK_VALUE
BASE_FONT_SIZE_HOLIDAY_TITLE = FONT_SIZE_HOLIDAY_TITLE
BASE_FONT_SIZE_HOLIDAY_DESC = FONT_SIZE_HOLIDAY_DESC
BASE_STANDARD_SPACING = STANDARD_SPACING
BASE_MEME_RADIUS = MEME_RADIUS
BASE_MEME_MIN_HEIGHT = MEME_MIN_HEIGHT
BASE_MEME_SIDE_MARGIN = MEME_SIDE_MARGIN
BASE_INFO_BLOCK_VERTICAL_ADJUSTMENT = INFO_BLOCK_VERTICAL_ADJUSTMENT


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
    
    def get_column_max_text_width(self, num_columns, inner_padding=2):
        """Max pixel width for value text centered in one column of a num_columns layout.

        Accounts for the outer block border (SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN)
        plus an optional inner_padding cushion so text never touches the block edge.
        """
        col_width = self.width // num_columns
        col_half = col_width // 2
        block_margin = SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN
        return max(0, 2 * (col_half - block_margin - inner_padding))

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
        # Date / hash-frame gradient (start → end)
        if "color_date_start_light" in config:
            self.color_sets["light"]["hash_start"] = config["color_date_start_light"]
        if "color_date_end_light" in config:
            self.color_sets["light"]["hash_end"] = config["color_date_end_light"]
        if "color_date_start_dark" in config:
            self.color_sets["dark"]["hash_start"] = config["color_date_start_dark"]
        if "color_date_end_dark" in config:
            self.color_sets["dark"]["hash_end"] = config["color_date_end_dark"]

        # Holidays (gradient: start → end)
        if "color_holiday_start_light" in config:
            self.color_sets["light"]["holiday_start"] = config["color_holiday_start_light"]
        if "color_holiday_end_light" in config:
            self.color_sets["light"]["holiday_end"] = config["color_holiday_end_light"]
        if "color_holiday_start_dark" in config:
            self.color_sets["dark"]["holiday_start"] = config["color_holiday_start_dark"]
        if "color_holiday_end_dark" in config:
            self.color_sets["dark"]["holiday_end"] = config["color_holiday_end_dark"]

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

        # Donation colors
        if "color_donation_light" in config:
            self.color_sets["light"]["donation"] = config["color_donation_light"]
        if "color_donation_dark" in config:
            self.color_sets["dark"]["donation"] = config["color_donation_dark"]

        # Countdown colors
        if "color_countdown_light" in config:
            self.color_sets["light"]["countdown"] = config["color_countdown_light"]
        if "color_countdown_dark" in config:
            self.color_sets["dark"]["countdown"] = config["color_countdown_dark"]

        # Halving colors
        if "color_halving_light" in config:
            self.color_sets["light"]["halving"] = config["color_halving_light"]
        if "color_halving_dark" in config:
            self.color_sets["dark"]["halving"] = config["color_halving_dark"]

        # Network stats colors
        if "color_network_light" in config:
            self.color_sets["light"]["network_hashrate"] = config["color_network_light"]
            self.color_sets["light"]["network_difficulty"] = config["color_network_light"]
        if "color_network_dark" in config:
            self.color_sets["dark"]["network_hashrate"] = config["color_network_dark"]
            self.color_sets["dark"]["network_difficulty"] = config["color_network_dark"]

        # Latest Lightning donation data (set from app before each render)
        self._donation_data = None

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
        
        # Determine display dimensions from device config
        # Priority: config-provided values > device lookup > smart defaults
        device_name = config.get("omni_device_name", "")
        
        if "display_width" in config and "display_height" in config:
            # Use explicit config values if provided (backwards compatibility)
            self.display_width = config.get("display_width", 800)
            self.display_height = config.get("display_height", 480)
        elif device_name and device_name in DEVICE_DIMENSIONS:
            # Look up dimensions from device specifications
            self.display_width, self.display_height = DEVICE_DIMENSIONS[device_name]
        else:
            # Smart defaults: always store landscape-native dimensions (1600x1200).
            # _apply_orientation_settings swaps them for portrait/vertical rendering.
            self.display_width = 1600
            self.display_height = 1200
        
        self.block_height_area_base = config.get("block_height_area", BASE_BLOCK_HEIGHT_AREA)
        self.e_ink_enabled = config.get("e-ink-display-connected", True)
        self._last_fee = None
        self._last_block_height = None
        
        # Initialize default state (will be overridden during rendering)
        self._apply_orientation_settings(self.orientation)
        
        self.meme_dir = os.path.join("static", "memes")
        self.opsec_dir = os.path.join("static", "opsec")

        # Meme file list + metadata cache (avoids re-scanning 4000+ files on every call)
        self._meme_cache_files = []          # sorted list of image filenames
        self._meme_cache_stems = set()       # filename stems (no extension) for quick lookup
        self._meme_cache_meta = {}           # stem -> list of searchable strings
        self._meme_cache_tags = {}           # stem -> list of tag strings (for display/editing)
        self._meme_cache_api_tags = {}       # stem -> list of API-sourced tags (read-only)
        self._meme_cache_stem_to_file = {}   # stem -> actual filename on disk
        self._meme_cache_ts = 0.0            # last rebuild timestamp
        self._MEME_CACHE_TTL = 86400         # seconds before auto-refresh (24h; mutations invalidate immediately)
        self._recent_memes = []              # last N meme paths to avoid repeats
        self._RECENT_MEMES_MAX = 50          # remember this many recent selections
        self._holiday_rr_index = {}          # round-robin index per date key (MM-DD)
        self._imagemagick_available = None   # cached check; None = not yet tested

        self.font_regular = os.path.join("static", "fonts", "Roboto-Regular.ttf")
        self.font_bold = os.path.join("static", "fonts", "Roboto-Bold.ttf")
        self.font_mono = os.path.join("static", "fonts", "IBMPlexMono-Bold.ttf")
        self.font_block_height = os.path.join("static", "fonts", "RobotoCondensed-ExtraBold.ttf")
        self._font_cache = {}  # Cache loaded font objects by (path, size)
        self.block_height_area = self.block_height_area_base
        
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

    def _open_image_robust(self, path: str) -> 'Image.Image':
        """Open an image file, falling back to ImageMagick when PIL lacks codec support.

        On ARMv6 (Pi Zero 1WH), PIL's WebP decode causes SIGILL (uncatchable signal).
        For .webp files on ARMv6 we skip PIL entirely and go straight to ImageMagick,
        which runs in a subprocess so a SIGILL inside convert cannot kill the main process.

        Raises if all attempts fail.
        """
        ext = os.path.splitext(path)[1].lower()
        pil_err = None
        needs_fallback = ext in ('.webp', '.avif', '.heic', '.heif')

        # Skip PIL for WebP on ARMv6 — SIGILL cannot be caught by try/except.
        if _WEBP_PIL_DECODE_SAFE or not needs_fallback:
            try:
                return Image.open(path)
            except Exception as e:
                if not needs_fallback:
                    raise
                pil_err = e

        # Reach here when: PIL failed for a special format, OR ARMv6 WebP (PIL skipped).
        # ImageMagick runs in a subprocess — safe even if libwebp SIGILLs inside convert.
        if self._imagemagick_available is None:
            try:
                import subprocess as _sp
                r = _sp.run(['convert', '--version'], capture_output=True, timeout=5)
                self._imagemagick_available = (r.returncode == 0)
            except Exception:
                self._imagemagick_available = False

        if not self._imagemagick_available:
            if pil_err:
                raise pil_err
            raise RuntimeError(
                f"PIL skipped for {ext} on ARMv6 and ImageMagick is not available — "
                f"install imagemagick: sudo apt-get install imagemagick"
            )

        import subprocess as _sp, tempfile as _tf
        tmp_fd, tmp_path = _tf.mkstemp(suffix='.png')
        os.close(tmp_fd)
        try:
            result = _sp.run(
                ['convert', path, tmp_path],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ImageMagick convert failed: {result.stderr.decode(errors='replace')}"
                )
            img = Image.open(tmp_path)
            img.load()  # force full decode before temp file is removed
            print(f"⚙️ Loaded {ext} via ImageMagick fallback: {os.path.basename(path)}")
            return img
        except Exception as im_err:
            pil_msg = f"PIL error: {pil_err}; " if pil_err else "PIL skipped (ARMv6); "
            raise RuntimeError(f"{pil_msg}ImageMagick fallback error: {im_err}") from im_err
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _get_font(self, font_path, size):
        """Get a cached font object, loading from disk only on first request."""
        key = (font_path, size)
        font = self._font_cache.get(key)
        if font is None:
            font = ImageFont.truetype(font_path, size)
            self._font_cache[key] = font
        return font

    def _shrink_font_to_fit(self, font_path, texts, max_width, start_size, min_size=10):
        """Return the largest font at or below start_size where every string in *texts*
        fits within max_width pixels.  Falls back to min_size if nothing fits."""
        for size in range(start_size, min_size - 1, -1):
            font = self._get_font(font_path, size)
            if all((font.getbbox(t)[2] - font.getbbox(t)[0]) <= max_width for t in texts):
                return font
        return self._get_font(font_path, min_size)

    # ------------------------------------------------------------------
    # Emoji support helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_emoji(text: str) -> bool:
        """Return True if *text* contains any Unicode emoji or symbol codepoints."""
        for char in text:
            cp = ord(char)
            if (
                0x1F300 <= cp <= 0x1FFFF  # Misc Symbols, Pictographs, Emoticons, Transport, Supplemental
                or 0x2600 <= cp <= 0x27BF  # Misc symbols & Dingbats
                or 0x1F1E0 <= cp <= 0x1F1FF  # Regional indicator symbols (flags)
                or 0xFE0F == cp  # Variation selector-16 (emoji presentation)
                or 0x200D == cp  # Zero-width joiner (compound emoji sequences)
                or 0x1F004 <= cp <= 0x1F0FF  # Mahjong/domino tile symbols
            ):
                return True
        return False

    @staticmethod
    def _emoji_aware_getlength(text: str, font) -> float:
        """Measure text pixel width, approximating emoji characters as *font.size* wide.

        Roboto (and similar Latin fonts) have no emoji glyphs, so calling
        ``font.getlength`` on an emoji codepoint returns the width of the
        .notdef glyph (often ~0 or a tiny box).  This method replaces those
        characters with a size-proportional estimate so that word-wrapping
        and centering work correctly.
        """
        if not ImageRenderer._has_emoji(text):
            return font.getlength(text)

        emoji_size = getattr(font, 'size', 20)
        total = 0.0
        i = 0
        while i < len(text):
            cp = ord(text[i])
            if (
                0x1F300 <= cp <= 0x1FFFF
                or 0x2600 <= cp <= 0x27BF
                or 0x1F1E0 <= cp <= 0x1F1FF
                or 0x1F004 <= cp <= 0x1F0FF
            ):
                total += emoji_size
                # Consume any trailing variation selector / ZWJ / second emoji in sequence
                i += 1
                while i < len(text):
                    nc = ord(text[i])
                    if nc in (0xFE0F, 0x200D):
                        i += 1
                        # ZWJ — the next codepoint is part of this compound emoji
                        if i < len(text) and (
                            0x1F300 <= ord(text[i]) <= 0x1FFFF
                            or 0x1F1E0 <= ord(text[i]) <= 0x1F1FF
                        ):
                            i += 1  # consume the joined character (already counted)
                    else:
                        break
            elif cp in (0xFE0F, 0x200D):
                # Standalone modifiers — skip, no width
                i += 1
            else:
                total += font.getlength(text[i])
                i += 1
        return total

    def _draw_text_with_emoji(self, draw, xy, text, font, fill):
        """Draw *text* at *xy* with full emoji support via pilmoji.

        Emoji images are fetched from Twitter's CDN on first use and cached to
        ``cache/emoji_cache/`` so subsequent renders work offline.
        Falls back to plain ``draw.text()`` when pilmoji is unavailable or the
        text contains no emoji, so existing non-emoji rendering is unaffected.
        """
        if not self._has_emoji(text):
            draw.text(xy, text, font=font, fill=fill)
            return
        if not _ensure_pilmoji_loaded():
            draw.text(xy, text, font=font, fill=fill)
            return
        try:
            image = draw._image  # PIL semi-public attribute, stable across versions
            with _Pilmoji(image, source=_CachedEmojiSource) as pilmoji:
                pilmoji.text(xy, text, fill=fill, font=font)
        except Exception:
            # Graceful fallback: render without emoji (shows .notdef placeholder)
            draw.text(xy, text, font=font, fill=fill)

    def _get_resolution_scale(self, orientation):
        """Return orientation-aware scale factor based on original baseline canvas."""
        if orientation == "vertical":
            base_w, base_h = BASE_CANVAS_VERTICAL_WIDTH, BASE_CANVAS_VERTICAL_HEIGHT
        else:
            base_w, base_h = BASE_CANVAS_HORIZONTAL_WIDTH, BASE_CANVAS_HORIZONTAL_HEIGHT

        sx = self.width / max(base_w, 1)
        sy = self.height / max(base_h, 1)

        # Keep uniform scaling to preserve proportions.
        return max(0.75, min(3.0, min(sx, sy)))

    def _scale_px(self, value, min_value=1):
        """Scale a pixel value using the current UI scale."""
        return max(min_value, int(round(value * self.ui_scale)))

    def _scale_font_size(self, value, min_value=8):
        """Scale font size using the current UI scale."""
        return max(min_value, int(round(value * self.ui_scale)))

    def _apply_scaled_layout_constants(self):
        """Apply resolution-scaled layout constants used throughout rendering."""
        global INFO_BLOCK_HEIGHT, ELEMENT_MARGIN, CARD_RADIUS, SIDE_PADDING, TOP_PADDING
        global BLOCK_HEIGHT_AREA, BLOCK_INNER_MARGIN, SECTION_SIDE_PADDING, BLOCK_RADIUS
        global LABEL_PADDING_TOP, LABEL_TO_VALUE_SPACING, LINE_SPACING_DEFAULT, LINE_SPACING_MULTILINE
        global HOLIDAY_TITLE_DESC_GAP, HOLIDAY_PADDING
        global FONT_SIZE_SMALL_LABEL, FONT_SIZE_LARGE_VALUE, FONT_SIZE_BLOCK_VALUE
        global FONT_SIZE_HOLIDAY_TITLE, FONT_SIZE_HOLIDAY_DESC
        global STANDARD_SPACING, MEME_RADIUS, MEME_MIN_HEIGHT, MEME_SIDE_MARGIN
        global INFO_BLOCK_VERTICAL_ADJUSTMENT

        INFO_BLOCK_HEIGHT = self._scale_px(BASE_INFO_BLOCK_HEIGHT, min_value=32)
        ELEMENT_MARGIN = self._scale_px(BASE_ELEMENT_MARGIN, min_value=8)
        CARD_RADIUS = self._scale_px(BASE_CARD_RADIUS, min_value=6)
        SIDE_PADDING = self._scale_px(BASE_SIDE_PADDING, min_value=8)
        TOP_PADDING = self._scale_px(BASE_TOP_PADDING, min_value=8)
        BLOCK_HEIGHT_AREA = self._scale_px(BASE_BLOCK_HEIGHT_AREA, min_value=100)
        BLOCK_INNER_MARGIN = self._scale_px(BASE_BLOCK_INNER_MARGIN, min_value=4)
        SECTION_SIDE_PADDING = SIDE_PADDING
        BLOCK_RADIUS = CARD_RADIUS

        LABEL_PADDING_TOP = self._scale_px(BASE_LABEL_PADDING_TOP, min_value=2)
        LABEL_TO_VALUE_SPACING = self._scale_px(BASE_LABEL_TO_VALUE_SPACING, min_value=3)
        LINE_SPACING_DEFAULT = self._scale_px(BASE_LINE_SPACING_DEFAULT, min_value=4)
        LINE_SPACING_MULTILINE = self._scale_px(BASE_LINE_SPACING_MULTILINE, min_value=2)
        HOLIDAY_TITLE_DESC_GAP = self._scale_px(BASE_HOLIDAY_TITLE_DESC_GAP, min_value=1)
        HOLIDAY_PADDING = self._scale_px(BASE_HOLIDAY_PADDING, min_value=10)

        FONT_SIZE_SMALL_LABEL = self._scale_font_size(BASE_FONT_SIZE_SMALL_LABEL, min_value=10)
        FONT_SIZE_LARGE_VALUE = self._scale_font_size(BASE_FONT_SIZE_LARGE_VALUE, min_value=16)
        FONT_SIZE_BLOCK_VALUE = self._scale_font_size(BASE_FONT_SIZE_BLOCK_VALUE, min_value=24)
        FONT_SIZE_HOLIDAY_TITLE = self._scale_font_size(BASE_FONT_SIZE_HOLIDAY_TITLE, min_value=14)
        FONT_SIZE_HOLIDAY_DESC = self._scale_font_size(BASE_FONT_SIZE_HOLIDAY_DESC, min_value=12)

        STANDARD_SPACING = self._scale_px(BASE_STANDARD_SPACING, min_value=8)
        MEME_RADIUS = self._scale_px(BASE_MEME_RADIUS, min_value=6)
        MEME_MIN_HEIGHT = self._scale_px(BASE_MEME_MIN_HEIGHT, min_value=24)
        MEME_SIDE_MARGIN = self._scale_px(BASE_MEME_SIDE_MARGIN, min_value=16)
        INFO_BLOCK_VERTICAL_ADJUSTMENT = self._scale_px(BASE_INFO_BLOCK_VERTICAL_ADJUSTMENT, min_value=2)

        # block_height_area may be user-configured; scale from its configured base value.
        self.block_height_area = self._scale_px(self.block_height_area_base, min_value=100)

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

        # Update resolution-aware scale and derived layout constants.
        self.ui_scale = self._get_resolution_scale(self.orientation)
        self._apply_scaled_layout_constants()
        
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

        is_new_block = block_height != self.last_block_height
        has_data = bool(self.block_fee_cache.get(block_height, {}).get('fee_data'))
        if is_new_block or not has_data:
            # New block detected, or retrying a height whose fee fetch previously failed
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
        # Otherwise, we already have usable data for this height — keep it

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

    def fetch_wallet_balances(self, startup_mode: bool = False, current_block: int = None):
        """
        Fetch deduped wallet balances using the dedicated API client.
        
        Args:
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            current_block (int): Current block height - used to prevent scanning same block multiple times
            
        Returns: dict with balance info or None on failure.
        """
        return self.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=current_block)
        
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
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
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

        # Render values — compute strings first so font can be sized to fit
        price_value_text = f"{fiat_currency_symbol} {self._format_number(price, 0)}"
        if moscow_time_unit == "hour":
            hours = moscow_time // 100
            minutes = moscow_time % 100
            moscow_time_text = f"{hours:02d}:{minutes:02d}"
        else:
            moscow_time_text = f"{self._format_number(moscow_time, 0)} sats"

        max_col_w = self.layout.get_column_max_text_width(2)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, [price_value_text, moscow_time_text], max_col_w, FONT_SIZE_LARGE_VALUE
        )

        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

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

        header_left_text = self.t.get("total_hashrate", f"Bitaxe Hashrate ({online_devices}/{total_devices})")
        
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
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
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

        # Render values — compute strings first so font can be sized to fit
        hashrate_value_text = f"{total_ths:.2f} TH/s"

        max_col_w = self.layout.get_column_max_text_width(2)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, [hashrate_value_text, blocks_value_text], max_col_w, FONT_SIZE_LARGE_VALUE
        )

        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        bbox_hashrate = font_large_value.getbbox(hashrate_value_text)
        bbox_blocks = font_large_value.getbbox(blocks_value_text)

        hashrate_x = self.layout.get_text_centered_x(bbox_hashrate, left_col_center)
        blocks_x = self.layout.get_text_centered_x(bbox_blocks, right_col_center)

        draw.text((hashrate_x, value_y), hashrate_value_text, font=font_large_value, fill=self.get_color("hashrate", web_quality))
        draw.text((blocks_x, value_y), blocks_value_text, font=font_large_value, fill=self.get_color("found_blocks", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    # --- Bitcoin Supply / Halving / Network helpers ---

    _MAX_SUPPLY_BTC = 20999999.97690000
    _HALVING_INTERVAL = 210000
    _GENESIS_SUBSIDY_SATS = 5000000000  # 50 BTC in satoshis

    @staticmethod
    def _compute_supply_stats(height):
        """Compute BTC circulating supply, remaining, and % mined from block height."""
        subsidy = ImageRenderer._GENESIS_SUBSIDY_SATS
        total_sats = 0
        h = int(height) if height else 0
        for epoch in range(64):
            start = epoch * ImageRenderer._HALVING_INTERVAL
            end = (epoch + 1) * ImageRenderer._HALVING_INTERVAL
            if h <= start:
                break
            blocks_in_epoch = min(h, end) - start
            total_sats += blocks_in_epoch * subsidy
            subsidy //= 2
            if subsidy == 0:
                break
        circulating_btc = total_sats / 1e8
        remaining_btc = ImageRenderer._MAX_SUPPLY_BTC - circulating_btc
        pct_mined = (circulating_btc / ImageRenderer._MAX_SUPPLY_BTC) * 100
        return {
            "circulating_btc": circulating_btc,
            "remaining_btc": remaining_btc,
            "pct_mined": pct_mined,
        }

    @staticmethod
    def _compute_halving_stats(height, time_avg_ms=600000):
        """Compute next halving block, blocks remaining, estimated date from block height."""
        from datetime import datetime, timedelta
        h = int(height) if height else 0
        current_epoch = h // ImageRenderer._HALVING_INTERVAL
        next_halving_block = (current_epoch + 1) * ImageRenderer._HALVING_INTERVAL
        blocks_remaining = next_halving_block - h
        seconds_remaining = blocks_remaining * (time_avg_ms / 1000.0)
        estimated_date = datetime.now() + timedelta(seconds=seconds_remaining)
        days_remaining = seconds_remaining / 86400.0
        hours_remaining = seconds_remaining / 3600.0
        return {
            "next_halving_block": next_halving_block,
            "blocks_remaining": blocks_remaining,
            "days_remaining": days_remaining,
            "hours_remaining": hours_remaining,
            "estimated_date": estimated_date,
        }

    def _format_number(self, value, decimals=0):
        """Format a number with locale-aware thousand separators and decimal point."""
        formatted = f"{value:,.{decimals}f}"
        if self.lang == "de":
            # German: 1.234.567,89
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        elif self.lang in ("es", "fr", "it"):
            # ES/FR/IT: 1.234.567,89
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted

    def _format_pct_mined(self, pct):
        """Format percentage mined with enough decimals to never show 100% prematurely."""
        for decimals in range(2, 11):
            formatted = f"{pct:.{decimals}f}"
            if formatted != f"{100.0:.{decimals}f}":
                if self.lang in ("de", "es", "fr", "it"):
                    formatted = formatted.replace(".", ",")
                return f"{formatted}%"
        formatted = f"{pct:.10f}"
        if self.lang in ("de", "es", "fr", "it"):
            formatted = formatted.replace(".", ",")
        return f"{formatted}%"

    def _format_hashrate(self, hs):
        """Format hash rate (H/s) as human-readable string (EH/s, PH/s, TH/s)."""
        if hs >= 1e18:
            return f"{self._format_number(hs / 1e18, 2)} EH/s"
        if hs >= 1e15:
            return f"{self._format_number(hs / 1e15, 2)} PH/s"
        if hs >= 1e12:
            return f"{self._format_number(hs / 1e12, 2)} TH/s"
        if hs >= 1e9:
            return f"{self._format_number(hs / 1e9, 2)} GH/s"
        return f"{self._format_number(hs, 0)} H/s"

    def _format_difficulty(self, d):
        """Format mining difficulty as human-readable string (T, G, M)."""
        if d >= 1e12:
            return f"{self._format_number(d / 1e12, 2)} T"
        if d >= 1e9:
            return f"{self._format_number(d / 1e9, 2)} G"
        if d >= 1e6:
            return f"{self._format_number(d / 1e6, 2)} M"
        return f"{self._format_number(d, 0)}"

    def render_countdown_block(self, draw, info_block_y, font_label, font_value, countdown_data, web_quality=False):
        """Render BTC supply countdown block: remaining BTC (left) and % mined (right)."""
        if countdown_data is None or countdown_data.get("error"):
            return info_block_y

        remaining_btc = countdown_data.get("remaining_btc", 0)
        pct_mined = countdown_data.get("pct_mined", 0)

        header_left_text = self.t.get("btc_remaining", "BTC Remaining")
        header_right_text = self.t.get("pct_mined", "% Mined")

        left_col_center = self.layout.get_column_center(2, 0)
        right_col_center = self.layout.get_column_center(2, 1)

        try:
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except Exception:
            font_small_label = font_label

        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
             (block_bounds[2], info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        text_y = self.layout.get_label_y(info_block_y)
        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)
        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center)
        right_x = self.layout.get_text_centered_x(bbox_right, right_col_center)
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        remaining_text = f"{self._format_number(remaining_btc, 2)} BTC"
        pct_text = self._format_pct_mined(pct_mined)

        max_col_w = self.layout.get_column_max_text_width(2)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, [remaining_text, pct_text], max_col_w, FONT_SIZE_LARGE_VALUE
        )

        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        bbox_remaining = font_large_value.getbbox(remaining_text)
        bbox_pct = font_large_value.getbbox(pct_text)
        remaining_x = self.layout.get_text_centered_x(bbox_remaining, left_col_center)
        pct_x = self.layout.get_text_centered_x(bbox_pct, right_col_center)

        draw.text((remaining_x, value_y), remaining_text, font=font_large_value, fill=self.get_color("countdown", web_quality))
        draw.text((pct_x, value_y), pct_text, font=font_large_value, fill=self.get_color("countdown", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_halving_block(self, draw, info_block_y, font_label, font_value, halving_data, web_quality=False):
        """Render next halving block: estimated date (left) and days/hours countdown (right)."""
        if halving_data is None or halving_data.get("error"):
            return info_block_y

        estimated_date = halving_data.get("estimated_date")
        days_remaining = halving_data.get("days_remaining", 0)
        hours_remaining = halving_data.get("hours_remaining", 0)

        header_left_text = self.t.get("halving_date", "Next Halving")
        if hours_remaining < 24:
            header_right_text = self.t.get("halving_hours_left", "Hours Until Halving")
        else:
            header_right_text = self.t.get("halving_days_left", "Days Until Halving")

        left_col_center = self.layout.get_column_center(2, 0)
        right_col_center = self.layout.get_column_center(2, 1)

        try:
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except Exception:
            font_small_label = font_label

        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
             (block_bounds[2], info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        text_y = self.layout.get_label_y(info_block_y)
        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)
        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center)
        right_x = self.layout.get_text_centered_x(bbox_right, right_col_center)
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        # Format date matching the top-of-image date style (locale-aware)
        if estimated_date:
            try:
                lang = self.config.get("language", "en")
                if lang == "en":
                    def ordinal(n):
                        return "%d%s" % (n, "tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
                    date_text = f"{estimated_date.strftime('%B')} {ordinal(estimated_date.day)}, {estimated_date.year}"
                elif lang == "de":
                    date_text = format_date(estimated_date, format="d. MMMM y", locale="de")
                elif lang == "es":
                    date_text = format_date(estimated_date, format="d 'de' MMMM 'de' y", locale="es")
                elif lang == "fr":
                    date_text = format_date(estimated_date, format="d MMMM y", locale="fr")
                elif lang == "it":
                    date_text = format_date(estimated_date, format="d MMMM y", locale="it")
                else:
                    date_text = estimated_date.strftime("%Y-%m-%d")
            except Exception:
                date_text = estimated_date.strftime("%d %b %Y") if estimated_date else "—"
        else:
            date_text = "—"

        if hours_remaining < 24:
            countdown_text = f"{hours_remaining:.1f}h"
        else:
            countdown_text = f"{days_remaining:.0f}d"

        max_col_w = self.layout.get_column_max_text_width(2)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, [date_text, countdown_text], max_col_w, FONT_SIZE_LARGE_VALUE
        )

        bbox_date = font_large_value.getbbox(date_text)
        bbox_countdown = font_large_value.getbbox(countdown_text)
        date_x = self.layout.get_text_centered_x(bbox_date, left_col_center)
        countdown_x = self.layout.get_text_centered_x(bbox_countdown, right_col_center)

        draw.text((date_x, value_y), date_text, font=font_large_value, fill=self.get_color("halving", web_quality))
        draw.text((countdown_x, value_y), countdown_text, font=font_large_value, fill=self.get_color("halving", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def render_network_block(self, draw, info_block_y, font_label, font_value, network_data, web_quality=False):
        """Render global network hashrate (left) and current difficulty (right)."""
        if network_data is None or network_data.get("error"):
            return info_block_y

        hashrate = network_data.get("currentHashrate", 0)
        difficulty = network_data.get("currentDifficulty", 0)

        header_left_text = self.t.get("network_hashrate", "Network Hashrate")
        header_right_text = self.t.get("network_difficulty", "Difficulty")

        left_col_center = self.layout.get_column_center(2, 0)
        right_col_center = self.layout.get_column_center(2, 1)

        try:
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except Exception:
            font_small_label = font_label

        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
             (block_bounds[2], info_block_y + INFO_BLOCK_HEIGHT)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        text_y = self.layout.get_label_y(info_block_y)
        bbox_left = font_small_label.getbbox(header_left_text)
        bbox_right = font_small_label.getbbox(header_right_text)
        left_x = self.layout.get_text_centered_x(bbox_left, left_col_center)
        right_x = self.layout.get_text_centered_x(bbox_right, right_col_center)
        draw.text((left_x, text_y), header_left_text, font=font_small_label, fill=self.get_color("info_header", web_quality))
        draw.text((right_x, text_y), header_right_text, font=font_small_label, fill=self.get_color("info_header", web_quality))

        label_height = bbox_left[3] - bbox_left[1]
        value_y = self.layout.get_value_y(info_block_y, label_height)

        hashrate_text = self._format_hashrate(hashrate)
        difficulty_text = self._format_difficulty(difficulty)

        max_col_w = self.layout.get_column_max_text_width(2)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, [hashrate_text, difficulty_text], max_col_w, FONT_SIZE_LARGE_VALUE
        )

        bbox_hashrate = font_large_value.getbbox(hashrate_text)
        bbox_diff = font_large_value.getbbox(difficulty_text)
        hashrate_x = self.layout.get_text_centered_x(bbox_hashrate, left_col_center)
        diff_x = self.layout.get_text_centered_x(bbox_diff, right_col_center)

        draw.text((hashrate_x, value_y), hashrate_text, font=font_large_value, fill=self.get_color("network_hashrate", web_quality))
        draw.text((diff_x, value_y), difficulty_text, font=font_large_value, fill=self.get_color("network_difficulty", web_quality))

        return info_block_y + INFO_BLOCK_HEIGHT + ELEMENT_MARGIN

    def _build_donation_header_text(self, amount_sats: int, timestamp: str, mode: str = None) -> str:
        """Build localized donation header text used for measure + render passes."""
        display_mode = mode if mode is not None else self.config.get("donation_display_mode", "latest")
        lang = self.config.get("language", "en")
        t = _TRANSLATIONS.get(lang, _TRANSLATIONS["en"])

        if display_mode == "highest":
            header_mode = t.get("donation_mode_highest", "Largest donation")
        elif display_mode == "auto":
            # In auto mode show the actual label (latest or largest) for the donation being displayed
            effective = None
            if self._donation_data and isinstance(self._donation_data, dict):
                effective = self._donation_data.get("_effective_mode")
            if effective == "highest":
                header_mode = t.get("donation_mode_highest", "Largest donation")
            else:
                header_mode = t.get("donation_mode_latest", "Latest donation")
        else:
            header_mode = t.get("donation_mode_latest", "Latest donation")

        if timestamp:
            try:
                from datetime import datetime as _dt2, timezone
                from babel.dates import format_datetime
                dt = _dt2.fromisoformat(timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_local = dt.astimezone()
                if lang == "de":
                    timestamp_text = format_datetime(dt_local, "HH:mm 'Uhr', dd.MM.yyyy", locale="de")
                elif lang == "es":
                    timestamp_text = format_datetime(dt_local, "dd/MM/yyyy HH:mm 'h'", locale="es")
                elif lang == "fr":
                    timestamp_text = format_datetime(dt_local, "dd/MM/yyyy HH:mm 'h'", locale="fr")
                elif lang == "it":
                    timestamp_text = format_datetime(dt_local, "dd/MM/yyyy HH:mm", locale="it")
                elif lang == "en":
                    timestamp_text = format_datetime(dt_local, "MM/dd/yyyy h:mm a", locale="en_US")
                else:
                    timestamp_text = format_datetime(dt_local, "dd.MM.yyyy HH:mm", locale=lang)
            except Exception:
                timestamp_text = timestamp.replace("T", " ")[:16]
        else:
            timestamp_text = "—"

        amount_formatted = self._format_number(amount_sats, 0)
        amount_text = f"{amount_formatted} Sat" if amount_sats == 1 else f"{amount_formatted} Sats"
        return f"{header_mode}: {amount_text} ({timestamp_text})"

    def _measure_donation_block_layout(self, donation_data, font_label, font_value):
        """Measure donation block geometry and choose largest 2-line body font that fits width."""
        amount_sats = donation_data.get("amount_sats", 0)
        message = donation_data.get("message", "") or ""
        timestamp = donation_data.get("timestamp", "")

        _ib_left = SIDE_PADDING + BLOCK_INNER_MARGIN + 2
        _ib_right = self.width - SIDE_PADDING - BLOCK_INNER_MARGIN - 2
        content_width = max(20, _ib_right - _ib_left - self._scale_px(12, min_value=4))
        content_center_x = (_ib_left + _ib_right) // 2

        try:
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
        except Exception:
            font_small_label = font_label

        header_text = self._build_donation_header_text(amount_sats, timestamp)
        min_header_size = self._scale_font_size(8, min_value=8)
        header_font_size = FONT_SIZE_SMALL_LABEL
        header_font = font_small_label
        while header_font_size > min_header_size:
            try:
                trial = self._get_font(self.font_regular, header_font_size)
            except Exception:
                trial = font_small_label
            if trial.getlength(header_text) <= content_width:
                header_font = trial
                break
            header_font_size -= 1

        header_bbox = header_font.getbbox(header_text)
        header_h = header_bbox[3] - header_bbox[1]
        header_top_offset = self.layout.get_label_y(0)

        msg = message.strip() if message.strip() else "—"
        max_lines = 2
        min_size = self._scale_font_size(8, min_value=8)
        two_line_max_size = max(min_size, self._scale_font_size(27, min_value=12))
        # Max body font matches info block large value size so single-line
        # donation blocks have the same height as other info blocks.
        start_size = max(min_size, self._scale_font_size(FONT_SIZE_LARGE_VALUE, min_value=12))
        line_gap = self._scale_px(3, min_value=1)

        content_font = None
        lines = None
        line_h = 0
        chosen_size = None
        for size in range(start_size, min_size - 1, -1):
            try:
                f = self._get_font(self.font_bold, size)
            except Exception:
                f = font_value
            wrapped = ImageRenderer._wrap_text_to_lines(msg, f, content_width, max_lines)
            if wrapped is None:
                continue
            bb_line = f.getbbox("Ag")
            line_h = bb_line[3] - bb_line[1]
            content_font = f
            lines = wrapped
            chosen_size = size
            break

        if content_font is None or not lines:
            try:
                content_font = self._get_font(self.font_bold, min_size)
            except Exception:
                content_font = font_value
            lines = ImageRenderer._wrap_text_truncated(msg, content_font, content_width, max_lines)
            bb_line = content_font.getbbox("Ag")
            line_h = bb_line[3] - bb_line[1]
            chosen_size = min_size

        # If body needs multiple lines, cap max font size to 27 and re-wrap at that size.
        if len(lines) > 1 and chosen_size is not None and chosen_size > two_line_max_size:
            try:
                content_font = self._get_font(self.font_bold, two_line_max_size)
            except Exception:
                content_font = font_value
            lines = ImageRenderer._wrap_text_to_lines(msg, content_font, content_width, max_lines)
            if lines is None:
                lines = ImageRenderer._wrap_text_truncated(msg, content_font, content_width, max_lines)
            bb_line = content_font.getbbox("Ag")
            line_h = bb_line[3] - bb_line[1]

        body_h = len(lines) * line_h + (len(lines) - 1) * line_gap
        body_top_gap = self._scale_px(4, min_value=2)
        bottom_pad = self._scale_px(6, min_value=2)
        block_height = max(INFO_BLOCK_HEIGHT, header_top_offset + header_h + body_top_gap + body_h + bottom_pad)

        return {
            "content_center_x": content_center_x,
            "content_width": content_width,
            "header_text": header_text,
            "header_font": header_font,
            "header_h": header_h,
            "header_top_offset": header_top_offset,
            "line_gap": line_gap,
            "content_font": content_font,
            "lines": lines,
            "line_h": line_h,
            "body_top_gap": body_top_gap,
            "block_height": block_height,
        }

    def _get_info_block_height(self, block_fn, block_data, font_label, font_value):
        """Return dynamic height for variable-size blocks, defaulting to INFO_BLOCK_HEIGHT."""
        if block_fn == self.render_donation_block and block_data:
            layout = self._measure_donation_block_layout(block_data, font_label, font_value)
            return layout["block_height"]
        return INFO_BLOCK_HEIGHT

    def _estimate_max_info_blocks(self, meme_path, block_height=None):
        """
        Estimate how many info blocks can fit below the meme in
        prioritize_large_scaled_meme=True layout.  Only reads the meme header.

        Returns:
            -1  on any error → caller should treat as "all blocks fit"
             0  when the meme fills all available space
            >0  estimated number of blocks that fit
        """
        if not meme_path or not os.path.exists(meme_path):
            return -1
        try:
            with self._open_image_robust(meme_path) as img:
                meme_w, meme_h = img.size
        except Exception:
            return -1

        # Estimate where the date text ends (y=20, bbox[3] ≈ font descent)
        try:
            date_text = self.get_localized_date(block_height)
            opt_size = self.get_optimal_date_font_size(date_text)
            font = self._get_font(self.font_bold, opt_size)
            bbox = font.getbbox(date_text)
            date_bottom_y = 20 + bbox[3] + 5
        except Exception:
            date_bottom_y = 70  # conservative fallback

        hash_frame_y = self.height - self.block_height_area + 3
        available = hash_frame_y - date_bottom_y
        min_gaps = 2 * STANDARD_SPACING  # top + bottom gap around meme
        max_meme_h = max(0, available - min_gaps)

        aspect = meme_w / meme_h
        max_w = self.width - 40
        scaled_w = min(max_w, int(max_meme_h * aspect))
        scaled_h = int(scaled_w / aspect)
        if scaled_h > max_meme_h:
            scaled_h = max_meme_h

        # 3 gaps: above meme, meme→blocks, blocks→hash frame
        space_for_blocks = (available - scaled_h) - 3 * STANDARD_SPACING
        if space_for_blocks <= 0:
            return 0

        # Approximate block unit: INFO_BLOCK_HEIGHT + ~10 px margin between blocks
        block_unit = INFO_BLOCK_HEIGHT + 10
        return max(0, int(space_for_blocks // block_unit))

    def _info_blocks_can_fit(self, meme_path, block_height=None):
        """Return True when at least one info block fits below the meme."""
        return self._estimate_max_info_blocks(meme_path, block_height) != 0

    def _preselect_info_blocks(self, meme_path, block_height=None):
        """
        For prioritize_large_scaled_meme=True layouts: estimate which block
        types will be shown and return them in random display order so the
        caller can fetch only the necessary data.

        Returns:
            None  — default layout (all enabled blocks always shown)
            []    — meme fills screen, no info blocks
            list  — randomly-ordered type strings, e.g. ['network', 'price']
        """
        import random as _random

        if not self.config.get("prioritize_large_scaled_meme", False):
            return None  # default layout always shows all blocks

        config = self.config
        _donation_data_self = getattr(self, '_donation_data', None)
        _donation_guaranteed = (
            isinstance(_donation_data_self, dict)
            and bool(_donation_data_self.get('_guaranteed'))
            and config.get("show_donation_block", False)
        )

        enabled = []
        if config.get("show_btc_price_block", True):       enabled.append('price')
        if config.get("show_countdown_block", True):        enabled.append('countdown')
        if config.get("show_halving_block", True):          enabled.append('halving')
        if config.get("show_network_block", True):          enabled.append('network')
        if config.get("show_bitaxe_block", True):           enabled.append('bitaxe')
        if config.get("show_wallet_balances_block", True):  enabled.append('wallet')
        # Non-guaranteed donation competes in the random pool; guaranteed is handled below
        if not _donation_guaranteed and config.get("show_donation_block", False) and _donation_data_self:
            enabled.append('donation')

        max_n = self._estimate_max_info_blocks(meme_path, block_height)

        if _donation_guaranteed:
            # Always include donation even if the meme fills the screen (renderer reserves space).
            # Other blocks are selected randomly and donation is rendered last.
            if max_n < 0:
                max_n = len(enabled)
            _random.shuffle(enabled)
            enabled_no_donation = [b for b in enabled if b != 'donation']
            selected = enabled_no_donation[:min(max_n, len(enabled_no_donation))] + ['donation']
            if len(selected) > 1 and 'donation' in selected:
                selected = [b for b in selected if b != 'donation'] + ['donation']
            return selected

        if not enabled:
            return []
        if max_n == 0:
            return []
        if max_n < 0:
            max_n = len(enabled)

        _random.shuffle(enabled)
        selected = enabled[:min(max_n, len(enabled))]
        if len(selected) > 1 and 'donation' in selected:
            selected = [b for b in selected if b != 'donation'] + ['donation']
        return selected

    def render_donation_block(self, draw, info_block_y, font_label, font_value, donation_data, web_quality=False):
        """Render a Lightning donation info block with adaptive 2-line body and dynamic height."""
        if not donation_data:
            return info_block_y

        layout = self._measure_donation_block_layout(donation_data, font_label, font_value)
        block_height = layout["block_height"]

        block_bounds = self.layout.get_info_block_bounds()
        draw.rounded_rectangle(
            [(block_bounds[0], info_block_y),
             (block_bounds[2], info_block_y + block_height)],
            radius=BLOCK_RADIUS,
            fill=self.get_color("info_bg", web_quality),
            outline=self.get_color("info_outline", web_quality),
            width=4
        )

        text_y = info_block_y + layout["header_top_offset"]
        header_bbox = layout["header_font"].getbbox(layout["header_text"])
        header_x = self.layout.get_text_centered_x(header_bbox, layout["content_center_x"])
        draw.text((header_x, text_y), layout["header_text"], font=layout["header_font"], fill=self.get_color("info_header", web_quality))

        start_y = text_y + layout["header_h"] + layout["body_top_gap"]
        for i, line in enumerate(layout["lines"]):
            # Use emoji-aware width for correct centering when line contains emoji
            if self._has_emoji(line):
                line_w = self._emoji_aware_getlength(line, layout["content_font"])
                x = layout["content_center_x"] - int(line_w) // 2
            else:
                bb = layout["content_font"].getbbox(line)
                x = self.layout.get_text_centered_x(bb, layout["content_center_x"])
            self._draw_text_with_emoji(
                draw,
                (x, start_y + i * (layout["line_h"] + layout["line_gap"])),
                line,
                font=layout["content_font"],
                fill=self.get_color("donation", web_quality)
            )

        return info_block_y + block_height + ELEMENT_MARGIN

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
            font_small_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
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

        if balance_unit.lower() == "sats":
            total_balance_sats = int(total_balance_btc * 1e8)
            balance_value_text = self._format_number(total_balance_sats, 0)
        else:
            balance_value_text = f"{total_balance_btc:.8f}"
            if self.lang in ("de", "es", "fr", "it"):
                balance_value_text = balance_value_text.replace(".", ",")

        texts_to_fit = [balance_value_text]
        fiat_value_text = None
        if show_fiat:
            currency_symbols = {
                "USD": "$", "EUR": "€", "GBP": "£", "CAD": "C$",
                "CHF": "CHF", "AUD": "A$", "JPY": "¥"
            }
            fiat_currency_symbol = currency_symbols.get(fiat_currency, fiat_currency)
            if fiat_value is not None:
                if fiat_currency == "JPY":
                    fiat_value_text = f"{fiat_currency_symbol} {self._format_number(fiat_value, 0)}"
                else:
                    fiat_value_text = f"{fiat_currency_symbol} {self._format_number(fiat_value, 2)}"
            else:
                fiat_value_text = f"{fiat_currency_symbol} {self._format_number(0, 2)}"
            texts_to_fit.append(fiat_value_text)

        max_col_w = self.layout.get_column_max_text_width(num_columns)
        font_large_value = self._shrink_font_to_fit(
            self.font_bold, texts_to_fit, max_col_w, FONT_SIZE_LARGE_VALUE
        )

        bbox_balance = font_large_value.getbbox(balance_value_text)
        balance_x = self.layout.get_text_centered_x(bbox_balance, left_col_center_x)
        label_height = bbox_left[3] - bbox_left[1]
        text_y = self.layout.get_value_y(info_block_y, label_height)
        draw.text((balance_x, text_y), balance_value_text, font=font_large_value, fill=self.get_color("wallet_balance", web_quality))

        if show_fiat and fiat_value_text is not None:
            bbox_fiat = font_large_value.getbbox(fiat_value_text)
            fiat_x = self.layout.get_text_centered_x(bbox_fiat, right_col_center_x)
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

            # For e-ink dark mode background, use pure black for better readability
            if mode == "dark" and color_name == "background":
                hex_color = "#000000"

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
        Select a random meme image from the local memes directory.
        Avoids repeating recently shown memes.

        Returns:
            str or None: Path to selected meme or None if no memes found
        """
        # Try holiday-themed selection first
        # Extract keywords from English + German titles (memes may be tagged in either)
        # Use the current round-robin entry (same one get_today_btc_holiday will display)
        today_key = datetime.now().strftime("%m-%d")
        holiday_list = btc_holidays.get(today_key)
        if holiday_list and isinstance(holiday_list, list) and len(holiday_list) > 0:
            idx = self._holiday_rr_index.get(today_key, 0) % len(holiday_list)
            holiday_data = holiday_list[idx]
            en_title = holiday_data.get("en", {}).get("title", "")
            de_title = holiday_data.get("de", {}).get("title", "")
            keywords = list(dict.fromkeys(
                self._holiday_keywords(en_title) + self._holiday_keywords(de_title)
            ))
            if keywords:
                result = self._pick_local_meme_by_keywords(keywords)
                if result:
                    self._track_recent_meme(result)
                    return result
        result = self._pick_local_meme()
        if result:
            self._track_recent_meme(result)
        return result

    def _track_recent_meme(self, path: str) -> None:
        """Record a meme path in the recent history ring buffer."""
        self._recent_memes.append(path)
        if len(self._recent_memes) > self._RECENT_MEMES_MAX:
            self._recent_memes = self._recent_memes[-self._RECENT_MEMES_MAX:]

    @staticmethod
    def _holiday_keywords(title: str) -> list:
        """Extract search keywords from a holiday title.

        Strips common stopwords, 'bitcoin'/'btc'/'day', '#N' tokens,
        and words shorter than 3 characters.
        """
        import re
        STOPWORDS = {
            # English
            'bitcoin', 'btc', 'day', 'the', 'of', 'a', 'an', 'is', 'this', 'in', 'on',
            'not', 'for', 'its', 'was', 'has', 'are', 'but', 'all', 'can',
            'first', 'good',
            # German
            'tag', 'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'und',
            'von', 'auf', 'aus', 'mit', 'zum', 'zur', 'als', 'bei', 'vor', 'nach',
            'erster', 'erste', 'ersten', 'erstes', 'guten', 'gute', 'guter',
            'nicht', 'oder', 'auch', 'noch', 'nur', 'wie',
        }
        # Also filter out pure-numeric tokens (e.g. "000" from "$1,000")
        cleaned = re.sub(r"[^a-z0-9 ]", " ", title.lower())
        return [w for w in cleaned.split()
                if w not in STOPWORDS and not w.startswith('#') and len(w) >= 3
                and not w.isdigit()]

    # ------------------------------------------------------------------
    # Meme cache helpers
    # ------------------------------------------------------------------

    def _refresh_meme_cache(self, force: bool = False) -> None:
        """Rebuild the cached meme file list + metadata if stale or forced."""
        import json as _json
        import time as _time

        now = _time.time()
        if not force and (now - self._meme_cache_ts) < self._MEME_CACHE_TTL and self._meme_cache_files:
            return  # cache still fresh

        memes_dir = self.meme_dir
        if not os.path.isdir(memes_dir):
            self._meme_cache_files = []
            self._meme_cache_stems = set()
            self._meme_cache_stem_to_file = {}
            self._meme_cache_meta = {}
            self._meme_cache_tags = {}
            self._meme_cache_api_tags = {}
            self._meme_cache_ts = now
            return

        # 1. Scan directory once
        files = [
            f for f in os.listdir(memes_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
            and not f.startswith('_')
        ]
        files.sort()
        stems = {os.path.splitext(f)[0] for f in files}

        # 2. Load rename map (_renames.json): {current_stem: original_uuid}
        renames: dict[str, str] = {}
        renames_path = os.path.join(memes_dir, '_renames.json')
        if os.path.exists(renames_path):
            try:
                with open(renames_path, encoding='utf-8') as fh:
                    renames = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        # Build reverse map: uuid -> current_stem (for re-keying)
        uuid_to_stem: dict[str, str] = {}
        for cur_stem, orig_uuid in renames.items():
            uuid_to_stem[orig_uuid] = cur_stem

        # 3. Build metadata map from index.jsonl + _state_memes.jsonl
        #    Keys are resolved to current filename stems (accounting for renames).
        meta: dict[str, list[str]] = {}
        tags_map: dict[str, list[str]] = {}
        api_tags_map: dict[str, list[str]] = {}  # tags from API (read-only)
        for jsonl_name in ('index.jsonl', '_state_memes.jsonl'):
            jsonl_path = os.path.join(memes_dir, jsonl_name)
            if not os.path.exists(jsonl_path):
                continue
            try:
                with open(jsonl_path, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        mid = entry.get('id', '')
                        if not mid:
                            continue
                        # Resolve UUID to current filename stem
                        key = uuid_to_stem.get(mid, mid)
                        if key in meta:
                            continue
                        raw_tags = entry.get('tags', []) or []
                        searchable: list[str] = []
                        searchable.extend(t.lower() for t in raw_tags)
                        for fld in ('description_en', 'description_de', 'ocr_text',
                                    'meme_template', 'sentiment', 'humor_type'):
                            val = entry.get(fld, '')
                            if val:
                                searchable.append(val.lower())
                        meta[key] = searchable
                        tags_map[key] = list(raw_tags)
                        api_tags_map[key] = list(raw_tags)
            except OSError:
                continue

        # 4. Load user-defined tag overrides (_user_tags.json)
        user_tags_path = os.path.join(memes_dir, '_user_tags.json')
        if os.path.exists(user_tags_path):
            try:
                with open(user_tags_path, encoding='utf-8') as fh:
                    user_tags = _json.load(fh)
                for stem, utags in user_tags.items():
                    api_tags = api_tags_map.get(stem, [])
                    merged = list(api_tags) + [t for t in utags
                                               if t.lower() not in {a.lower() for a in api_tags}]
                    tags_map[stem] = merged
                    # Update searchable meta
                    existing = meta.get(stem, [])
                    existing_set = set(existing)
                    meta[stem] = existing + [t.lower() for t in utags
                                             if t.lower() not in existing_set]
            except (OSError, _json.JSONDecodeError):
                pass

        # Build stem -> filename lookup for path resolution
        stem_to_file: dict[str, str] = {}
        for f in files:
            stem_to_file[os.path.splitext(f)[0]] = f

        self._meme_cache_files = files
        self._meme_cache_stems = stems
        self._meme_cache_stem_to_file = stem_to_file
        self._meme_cache_meta = meta
        self._meme_cache_tags = tags_map
        self._meme_cache_api_tags = api_tags_map
        self._meme_cache_ts = now

    def invalidate_meme_cache(self) -> None:
        """Force the meme cache to rebuild on next access."""
        self._meme_cache_ts = 0.0

    def get_cached_meme_files(self) -> list[str]:
        """Return the cached sorted list of meme filenames."""
        self._refresh_meme_cache()
        return self._meme_cache_files

    def get_cached_meme_meta(self) -> dict[str, list[str]]:
        """Return the cached metadata map (stem -> searchable strings)."""
        self._refresh_meme_cache()
        return self._meme_cache_meta

    def get_cached_meme_tags(self) -> dict[str, list[str]]:
        """Return the cached tags map (stem -> list of tag strings)."""
        self._refresh_meme_cache()
        return self._meme_cache_tags

    def get_cached_meme_api_tags(self) -> dict[str, list[str]]:
        """Return the cached API-sourced tags (stem -> read-only tag list)."""
        self._refresh_meme_cache()
        return self._meme_cache_api_tags

    def record_rename(self, old_stem: str, new_stem: str) -> None:
        """Track a file rename in _renames.json so metadata stays linked."""
        import json as _json
        renames_path = os.path.join(self.meme_dir, '_renames.json')
        renames: dict[str, str] = {}
        if os.path.exists(renames_path):
            try:
                with open(renames_path, encoding='utf-8') as fh:
                    renames = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        # Resolve chain: if old_stem was itself a rename, follow to the original UUID
        original_uuid = renames.pop(old_stem, old_stem)
        renames[new_stem] = original_uuid
        with open(renames_path, 'w', encoding='utf-8') as fh:
            _json.dump(renames, fh, ensure_ascii=False, indent=2)

    def set_meme_tags(self, stem: str, tags: list[str]) -> None:
        """Save user-defined tags for a meme (persisted in _user_tags.json)."""
        import json as _json
        user_tags_path = os.path.join(self.meme_dir, '_user_tags.json')
        user_tags: dict[str, list[str]] = {}
        if os.path.exists(user_tags_path):
            try:
                with open(user_tags_path, encoding='utf-8') as fh:
                    user_tags = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        user_tags[stem] = tags
        with open(user_tags_path, 'w', encoding='utf-8') as fh:
            _json.dump(user_tags, fh, ensure_ascii=False, indent=2)
        self.invalidate_meme_cache()

    # ------------------------------------------------------------------

    def _pick_local_meme_by_keywords(self, keywords: list) -> str | None:
        """Return a random local meme whose tags contain any of the keywords.

        Uses the cached metadata from index.jsonl and filters to memes whose
        tag list contains at least one keyword as a substring.
        Only returns memes whose file is actually on disk.
        Avoids recently shown memes when possible.
        Falls back to None if no metadata or no matches found.
        """
        self._refresh_meme_cache()
        if not self._meme_cache_meta:
            return None
        try:
            on_disk = self._meme_cache_stems
            matches = []
            for mid, searchable in self._meme_cache_meta.items():
                if mid not in on_disk:
                    continue
                if any(kw in s for kw in keywords for s in searchable):
                    matches.append(mid)

            if not matches:
                print(f"No local memes matched keywords {keywords}, using random")
                return None

            # Prefer memes not recently shown
            recent_set = set(self._recent_memes)
            s2f = self._meme_cache_stem_to_file
            unseen = [m for m in matches
                      if os.path.join(self.meme_dir, s2f.get(m, f"{m}.webp")) not in recent_set]
            pool = unseen if unseen else matches

            chosen = random.choice(pool)
            chosen_file = s2f.get(chosen, f"{chosen}.webp")
            print(f"Holiday meme match (keywords={keywords}, pool={len(pool)}/{len(matches)}): {chosen_file}")
            return os.path.join(self.meme_dir, chosen_file)
        except Exception as e:
            print(f"Error in holiday meme selection: {e}")
            return None

    def _pick_local_meme(self):
        """Select a random meme from the local memes directory."""
        try:
            memes = self.get_cached_meme_files()
            if not memes:
                print("No meme images found in directory")
                return None
            # Prefer memes not recently shown
            recent_set = set(self._recent_memes)
            unseen = [f for f in memes
                      if os.path.join(self.meme_dir, f) not in recent_set]
            pool = unseen if unseen else memes
            selected = random.choice(pool)
            return os.path.join(self.meme_dir, selected)
        except Exception as e:
            print(f"Error selecting meme: {e}")
            return None

    def pick_random_opsec_image(self):
        """
        Select a random OPSec image from the opsec directory.

        Returns:
            str or None: Path to selected OPSec image or None if none found
        """
        try:
            if not os.path.exists(self.opsec_dir):
                return None
            images = [f for f in os.listdir(self.opsec_dir)
                      if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
            if not images:
                print("No OPSec images found in directory")
                return None
            selected = random.choice(images)
            return os.path.join(self.opsec_dir, selected)
        except Exception as e:
            print(f"Error selecting OPSec image: {e}")
            return None

    def get_opsec_image_for_eink(self):
        """
        Get a randomly selected OPSec image for e-ink display.
        A new random image is picked on every block update.

        Returns:
            str or None: Path to a randomly selected OPSec image
        """
        image = self.pick_random_opsec_image()
        return image

    def _cover_crop(self, img, target_width, target_height):
        """
        Scale and center-crop an image to exactly cover the target dimensions
        without changing the original aspect ratio (CSS object-fit: cover behaviour).

        The image is scaled up/down uniformly so that both target dimensions are
        fully covered, then the excess is cropped symmetrically from the edges.

        Args:
            img (PIL.Image): Source image (must already be in RGB mode)
            target_width (int): Desired output width in pixels
            target_height (int): Desired output height in pixels

        Returns:
            PIL.Image: Cropped/scaled image of exactly (target_width × target_height)
        """
        img_w, img_h = img.size
        scale = max(target_width / img_w, target_height / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)
        img = img.resize((scaled_w, scaled_h), Image.LANCZOS)
        left = (scaled_w - target_width) // 2
        top = (scaled_h - target_height) // 2
        return img.crop((left, top, left + target_width, top + target_height))

    def render_opsec_eink_image(self):
        """
        Render OPSec image for e-ink display.

        The image is scaled to *cover* the full display area (maintaining the
        original aspect ratio) and center-cropped so no empty borders remain.
        self.width / self.height already reflect the active e-ink orientation
        (set by _apply_orientation_settings before this method is called), so
        portrait vs. landscape is handled automatically.

        Falls back to a plain white image when no OPSec images are available.

        Returns:
            PIL.Image: E-ink optimized image
        """
        opsec_path = self.get_opsec_image_for_eink()

        if opsec_path and os.path.exists(opsec_path):
            try:
                opsec_img = ImageOps.exif_transpose(Image.open(opsec_path)).convert('RGB')
                opsec_img = self._cover_crop(opsec_img, self.width, self.height)
                print(f"🔒 OPSec: rendering {os.path.basename(opsec_path)} "
                      f"({opsec_img.width}×{opsec_img.height}) on e-ink display")
                return self.convert_to_7color(opsec_img, use_meme_optimization=True)
            except Exception as e:
                print(f"⚠️ OPSec: failed to load image {opsec_path}: {e}")

        # Fallback: plain white background
        print("⚠️ OPSec: no images available, rendering blank fallback")
        return Image.new('RGB', (self.width, self.height), color='white')

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

    def _get_holiday_description_layout(self, text):
        """Pick font size and wrapping so holiday description stays compact and readable.

        Target at most 2 lines on all screen sizes for better aesthetics.
        """
        text = (text or "").strip()
        if not text:
            font_desc = self._get_font(self.font_regular, FONT_SIZE_HOLIDAY_DESC)
            return font_desc, [""]

        max_lines = 2
        inner_pad = max(self._scale_px(12, min_value=6), HOLIDAY_PADDING // 2)
        max_text_width = max(120, self.width - (2 * (SECTION_SIDE_PADDING + BLOCK_INNER_MARGIN + inner_pad)))

        base_size = FONT_SIZE_HOLIDAY_DESC
        min_size = max(10, int(round(base_size * 0.6)))

        for font_size in range(base_size, min_size - 1, -1):
            font_desc = self._get_font(self.font_regular, font_size)
            lines = self._wrap_text_to_lines(text, font_desc, max_text_width, max_lines)
            if lines is not None:
                if len(lines) > 1:
                    lines = self._balance_lines(text, font_desc, max_text_width)
                return font_desc, lines

        # Last resort: keep max line count and truncate with ellipsis.
        fallback_font = self._get_font(self.font_regular, min_size)
        fallback_lines = self._wrap_text_truncated(text, fallback_font, max_text_width, max_lines)
        return fallback_font, fallback_lines

    @staticmethod
    def _balance_lines(text, font, max_width):
        """Re-wrap text so that multi-line results have similar pixel widths.

        Tries every possible word-boundary split point and picks the one that
        minimises the difference between the longest and shortest line, while
        still fitting within max_width.
        """
        words = text.split()
        if len(words) <= 1:
            return [text]

        best_lines = None
        best_diff = float('inf')

        for split in range(1, len(words)):
            line1 = " ".join(words[:split])
            line2 = " ".join(words[split:])
            w1 = font.getlength(line1)
            w2 = font.getlength(line2)
            if w1 > max_width or w2 > max_width:
                continue
            diff = abs(w1 - w2)
            if diff < best_diff:
                best_diff = diff
                best_lines = [line1, line2]

        if best_lines is not None:
            return best_lines
        # Fallback: greedy wrap (should not happen since caller already verified fit)
        return [text]

    def get_today_btc_holiday(self):
        """
        Get Bitcoin holiday information for today in the configured language.
        
        Returns:
            dict or None: Holiday information or None if no holiday today
        """
        today_key = datetime.now().strftime("%m-%d")
        holiday_list = btc_holidays.get(today_key)

        if holiday_list and isinstance(holiday_list, list) and len(holiday_list) > 0:
            # Round-robin across multiple entries for the same date
            idx = self._holiday_rr_index.get(today_key, 0)
            holiday = holiday_list[idx % len(holiday_list)]
            self._holiday_rr_index[today_key] = idx + 1

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
        font = self._get_font(self.font_bold, 22)
        bbox = font.getbbox(msg)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), msg, font=font, fill=self.get_color("red", True))
        return y + (bbox[3] - bbox[1]) + 20

    def fee_to_colors(self, current_fee, recent_fee, web_quality=False):
        """
        Returns (top_color, bottom_color) for the block-height text gradient.

        Light mode: gradient from bottom (darker) to top (lighter)
          - Fee label at bottom uses darker color for better readability
        Dark mode: gradient from top (darker) to bottom (lighter)
          - Fee label at bottom uses lighter color for better contrast

        The gradient shifts hue when fees change between blocks.
        """
        # fmt: off
        STOPS = [
            (0,    (  0, 210,  80)),   # green
            (1,    (  0, 210,  80)),   # green
            (5,    ( 20, 205,  50)),   # green (still clearly green)
            (10,   (130, 210,  10)),   # yellow-green
            (18,   (225, 205,   0)),   # yellow
            (30,   (255, 160,   0)),   # amber
            (50,   (255, 110,   0)),   # orange
            (80,   (255,  55,   0)),   # orange-red
            (120,  (230,  20,  20)),   # red
            (250,  (195,  15,  90)),   # crimson
            (500,  (140,  30, 200)),   # purple
            (900,  ( 50,  90, 225)),   # blue
            (1600, ( 25,  50, 150)),   # dark blue
            (2500, ( 70,  70,  80)),   # dark grey
        ]
        # fmt: on

        def interpolate(fee_value):
            if fee_value is None:
                return (120, 120, 130)
            if fee_value <= STOPS[0][0]:
                return STOPS[0][1]
            if fee_value >= STOPS[-1][0]:
                return STOPS[-1][1]
            for i in range(len(STOPS) - 1):
                f0, c0 = STOPS[i]
                f1, c1 = STOPS[i + 1]
                if f0 <= fee_value <= f1:
                    t = (fee_value - f0) / (f1 - f0)
                    return tuple(int(c0[j] + t * (c1[j] - c0[j])) for j in range(3))
            return STOPS[-1][1]

        current_color = interpolate(current_fee)
        recent_color  = interpolate(recent_fee)

        # Create saturated and washed versions
        def boost_saturation(c, factor=0.85):
            """Boost color saturation"""
            return tuple(min(255, int(v * factor)) for v in c)
        
        def wash_out(c, amount=0.85):
            """Wash out color towards white"""
            return tuple(int(v + amount * (255 - v)) for v in c)

        saturated = boost_saturation(current_color)
        washed = wash_out(current_color)
        
        # Check if dark mode - use appropriate mode for web vs e-ink
        if web_quality:
            is_dark = self.config.get("color_mode_dark", True)
        else:
            is_dark = self.config.get("eink_dark_mode", False)
        
        # Light mode: return (washed_top, saturated_bottom) - gradient bottom→top (dark→light)
        # Dark mode: return (saturated_top, washed_bottom) - gradient top→bottom (dark→light)
        if is_dark:
            return saturated, washed  # top=darker, bottom=lighter
        else:
            return washed, saturated  # top=lighter, bottom=darker
    

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
            # English (American) with ordinal day (e.g., "May 22nd, 2025")
            def ordinal(n):
                return "%d%s" % (n, "tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
            day_ordinal = ordinal(today.day)
            return f"{today.strftime('%B')} {day_ordinal}, {today.year}"
        
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
            max_font_size = self._scale_font_size(self.config.get("date_font_max_size", 48), min_value=20)
        
        if min_font_size is None:
            min_font_size = self._scale_font_size(self.config.get("date_font_min_size", 32), min_value=14)
        
        # Start with the maximum font size and work down
        for font_size in range(max_font_size, min_font_size - 1, -1):
            try:
                test_font = self._get_font(self.font_bold, font_size)
                bbox = test_font.getbbox(date_text)
                text_width = bbox[2] - bbox[0]
                
                if text_width <= max_width:
                    return font_size
            except Exception:
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

    def render_dual_images(self, block_height, block_hash, mempool_api=None,  startup_mode=False, override_content_path=None, preserve_info_blocks=None, precached_price=None, precached_bitaxe=None, precached_fee=None, precached_block_height=None, precached_network=None, skip_hash_frame=False):
        """
        Render both web-quality and e-ink optimized images efficiently.
        Optimized to share common elements and reduce API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            override_content_path (str, optional): Force specific meme/image path
            preserve_info_blocks (list, optional): List of block types to preserve ['wallet', 'bitaxe', 'price']
            precached_price (dict, optional): Pre-cached price data to avoid API call
            precached_bitaxe (dict, optional): Pre-cached Bitaxe data to avoid API call
            precached_fee (dict, optional): Pre-cached fee recommendations to avoid API call
            precached_block_height (int, optional): Pre-cached block height to avoid API call
            
        Returns:
            tuple: (web_image, eink_image, content_path, displayed_blocks) - PIL.Image objects, content path, and displayed block types
        """
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info - use pre-cached if available
        if precached_fee and precached_block_height is not None:
            fee_param = self.config.get("fee_parameter", "minimumFee")
            configured_fee = precached_fee.get(fee_param, 1)
            # Always prefer the explicitly passed block_height over stale pre-cached value
            api_block_height = block_height if block_height is not None else precached_block_height
        else:
            configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Try overrides first, then Twitter content, fallback to memes
        content_path = override_content_path
        
        # Fallback to random meme if no override and no content path yet
        if not content_path:
            content_path = self.pick_random_meme()
        
        # Determine which block types to build:
        #   preserve_info_blocks set → keep an existing layout (config change / wallet refresh)
        #   prioritize_large_scaled_meme → pre-select only the types that fit the meme
        #   otherwise (default layout) → all enabled blocks (renderer will randomise)
        #
        # active_types:
        #   None  = build all enabled blocks (renderer randomises)
        #   []    = meme fills screen — nothing to build
        #   list  = pre-selected / preserved types in display order
        info_blocks = []
        bitaxe_data = None
        btc_price_data = None
        wallet_data = None
        network_data = None
        displayed_blocks = []
        config = self.config

        if preserve_info_blocks is not None:
            active_types = preserve_info_blocks
            print(f"🎭 Preserving info block layout: {active_types}")
        else:
            active_types = self._preselect_info_blocks(content_path, block_height)
            if active_types is not None and not active_types:
                print("ℹ️ Meme fills available space — skipping info block data fetch")

        # Fetch shared network data only when at least one of the three network-dependent
        # blocks will actually be shown.
        _network_types = {'countdown', 'halving', 'network'}
        _need_network = (
            (active_types is None and (
                config.get("show_countdown_block", True)
                or config.get("show_halving_block", True)
                or config.get("show_network_block", True)
            )) or
            (active_types and any(t in _network_types for t in active_types))
        )
        if _need_network:
            if precached_network:
                network_data = precached_network
            elif mempool_api:
                _hd = mempool_api.get_hashrate_and_difficulty()
                _da = mempool_api.get_difficulty_adjustment()
                if _hd:
                    network_data = {
                        "currentHashrate": _hd.get("currentHashrate", 0),
                        "currentDifficulty": _hd.get("currentDifficulty", 0),
                        "timeAvg": _da.get("timeAvg", 600000) if _da else 600000,
                    }

        # Unified block builder — handles both "all enabled" and "specific types" paths.
        def _add_block(block_type):
            nonlocal btc_price_data, bitaxe_data
            if block_type == 'price' and config.get("show_btc_price_block", True):
                btc_price_data = precached_price or self.btc_price_api.fetch_btc_price()
                info_blocks.append((self.render_btc_price_block, btc_price_data))
                displayed_blocks.append('price')
            elif block_type == 'countdown' and config.get("show_countdown_block", True):
                _supply = self._compute_supply_stats(block_height)
                info_blocks.append((self.render_countdown_block, _supply))
                displayed_blocks.append('countdown')
            elif block_type == 'halving' and config.get("show_halving_block", True):
                _time_avg = (network_data or {}).get("timeAvg", 600000)
                _halving = self._compute_halving_stats(block_height, _time_avg)
                info_blocks.append((self.render_halving_block, _halving))
                displayed_blocks.append('halving')
            elif block_type == 'network' and config.get("show_network_block", True):
                info_blocks.append((self.render_network_block, network_data or {}))
                displayed_blocks.append('network')
            elif block_type == 'bitaxe' and config.get("show_bitaxe_block", True):
                bitaxe_data = precached_bitaxe or self.bitaxe_api.fetch_bitaxe_stats()
                info_blocks.append((self.render_bitaxe_block, bitaxe_data))
                displayed_blocks.append('bitaxe')
            elif block_type == 'donation' and config.get("show_donation_block", False):
                _donation_data = getattr(self, '_donation_data', None)
                if _donation_data:
                    info_blocks.append((self.render_donation_block, _donation_data))
                    displayed_blocks.append('donation')
            # 'wallet' is intentionally excluded — handled separately below

        if active_types is None:
            # Default layout: add all enabled blocks; renderer will randomise order.
            for bt in ('price', 'countdown', 'halving', 'network', 'bitaxe'):
                _add_block(bt)
            # Donation included like any other block; renderer handles guarantee vs. random
            _add_block('donation')
        else:
            for bt in active_types:
                _add_block(bt)

        # Wallet block — always positioned last (or at its preserved index) and needs
        # fiat conversion, so it is handled outside the unified loop.
        _want_wallet = config.get("show_wallet_balances_block", True) and (
            active_types is None or 'wallet' in (active_types or [])
        )
        if _want_wallet:
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

            # Add wallet block at its correct position
            if active_types is not None and 'wallet' in active_types:
                wallet_index = active_types.index('wallet')
                info_blocks.insert(wallet_index, (self.render_wallet_balances_block, wallet_data))
            else:
                info_blocks.append((self.render_wallet_balances_block, wallet_data))
            displayed_blocks.append('wallet')

        # When blocks were pre-selected (active_types is a list), pass them directly to
        # the renderer as 'selected_info_blocks' so it skips the random re-shuffle.
        _pre_selected_layout = active_types is not None and bool(active_types)

        # Pass all shared data to both renders
        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "precached_fee": precached_fee,
            "api_block_height": api_block_height,
            "meme_path": content_path,
            "btc_price_data": btc_price_data,
            "bitaxe_data": bitaxe_data,
            "wallet_data": wallet_data,
            "info_blocks": info_blocks,
            "displayed_blocks": displayed_blocks,
            "preserve_layout": preserve_info_blocks is not None,
            # Pre-populate selected_info_blocks to skip renderer re-shuffle when the
            # block order was already decided here (pre-selection or preservation).
            "selected_info_blocks": info_blocks if _pre_selected_layout else None,
        }

        # === GENERATE WEB IMAGE ===
        # Apply web orientation settings
        self._apply_orientation_settings(self.web_orientation)
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True, startup_mode=startup_mode,
            skip_hash_frame=skip_hash_frame
        )
        
        # === GENERATE E-INK IMAGE ===
        eink_img = None
        if self.e_ink_enabled:
            # Apply e-ink orientation settings
            self._apply_orientation_settings(self.eink_orientation)
            if self.config.get("opsec_mode_enabled", False):
                # OPSec mode: show a random family/cover photo instead of BTC data
                eink_img = self.render_opsec_eink_image()
            else:
                eink_img = self._render_image_with_shared_data(
                    block_height, block_hash, mempool_api,
                    shared_data, web_quality=False, startup_mode=startup_mode,
                    skip_hash_frame=skip_hash_frame
                )

        # Restore default/web orientation state (optional, but good practice)
        self._apply_orientation_settings(self.web_orientation)

        print(f"✅ Image generated for block {block_height}")
        return web_img, eink_img, content_path, displayed_blocks  # Return images, content path, and displayed block types
    
    def render_dual_images_with_cached_meme(self, block_height, block_hash, cached_meme_path, mempool_api=None,
                                             precached_price=None, precached_bitaxe=None, precached_fee=None,
                                             precached_network=None):
        """
        Render both web-quality and e-ink optimized images using a specific cached meme.
        Used when configuration changes require image refresh but meme should stay the same.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            cached_meme_path (str): Path to the cached meme to use
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            precached_price (dict, optional): Pre-cached price data as fallback
            precached_bitaxe (dict, optional): Pre-cached Bitaxe data as fallback
            precached_fee (dict, optional): Pre-cached fee data as fallback
            
        Returns:
            tuple: (web_image, eink_image, meme_path) - Both PIL.Image objects and used meme path
        """
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info - use pre-cached as fallback if API fails
        if precached_fee is not None:
            fee_param = self.config.get("fee_parameter", "minimumFee")
            configured_fee = precached_fee.get(fee_param, 1)
            api_block_height = block_height
        else:
            configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        # Always prefer the explicitly passed block_height over API-fetched value
        if block_height is not None:
            api_block_height = block_height
        
        # Use the provided cached meme path
        meme_path = cached_meme_path
        
        # Fetch info block data ONCE
        btc_price_data = None
        bitaxe_data = None
        wallet_data = None
        network_data = precached_network

        config = self.config

        # When the meme-first layout is active, check upfront whether any info block
        # could actually fit below the cached meme.  If not, skip all data fetching —
        # unless donation is guaranteed (renderer will pre-reserve space for it).
        _donation_data_pre = getattr(self, '_donation_data', None)
        _donation_guaranteed_pre = (
            isinstance(_donation_data_pre, dict)
            and bool(_donation_data_pre.get('_guaranteed'))
            and config.get("show_donation_block", False)
        )
        _skip_info_blocks = (
            config.get("prioritize_large_scaled_meme", False)
            and meme_path is not None
            and not self._info_blocks_can_fit(meme_path, block_height)
            and not _donation_guaranteed_pre
        )
        if _skip_info_blocks:
            print("ℹ️ Meme fills available space — skipping info block data fetch")

        # Fetch live network stats if not precached and any of the new blocks are enabled
        _need_network = (
            config.get("show_countdown_block", True)
            or config.get("show_halving_block", True)
            or config.get("show_network_block", True)
        )
        if _need_network and not _skip_info_blocks and network_data is None and mempool_api:
            _hd = mempool_api.get_hashrate_and_difficulty()
            _da = mempool_api.get_difficulty_adjustment()
            if _hd:
                network_data = {
                    "currentHashrate": _hd.get("currentHashrate", 0),
                    "currentDifficulty": _hd.get("currentDifficulty", 0),
                    "timeAvg": _da.get("timeAvg", 600000) if _da else 600000,
                }

        # Build info blocks ONCE
        info_blocks = []
        if not _skip_info_blocks:
            if config.get("show_btc_price_block", True):
                btc_price_data = precached_price or self.btc_price_api.fetch_btc_price()
                info_blocks.append((self.render_btc_price_block, btc_price_data))
            if config.get("show_countdown_block", True):
                _supply = self._compute_supply_stats(block_height)
                info_blocks.append((self.render_countdown_block, _supply))
            if config.get("show_halving_block", True):
                _time_avg = network_data.get("timeAvg", 600000) if network_data else 600000
                _halving = self._compute_halving_stats(block_height, _time_avg)
                info_blocks.append((self.render_halving_block, _halving))
            if config.get("show_network_block", True):
                info_blocks.append((self.render_network_block, network_data or {}))
            if config.get("show_bitaxe_block", True):
                bitaxe_data = precached_bitaxe or self.bitaxe_api.fetch_bitaxe_stats()
                info_blocks.append((self.render_bitaxe_block, bitaxe_data))
            if config.get("show_wallet_balances_block", True):
                wallet_data = self.wallet_api.get_cached_wallet_balances()
                if wallet_data is None or wallet_data.get("error"):
                    wallet_data = {
                        "total_btc": 0,
                        "total_fiat": 0,
                        "fiat_currency": "USD",
                        "addresses": [],
                        "xpubs": [],
                    }

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
        # Add donation when info blocks are not skipped, OR when donation is guaranteed
        # (even if the meme fills the screen, the renderer will pre-reserve space).
        if not _skip_info_blocks or _donation_guaranteed_pre:
            _donation_data = getattr(self, '_donation_data', None)
            if _donation_data and config.get("show_donation_block", False):
                info_blocks.append((self.render_donation_block, _donation_data))

        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "precached_fee": precached_fee,
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
        if self.config.get("opsec_mode_enabled", False):
            # OPSec mode: show a random family/cover photo instead of BTC data
            eink_img = self.render_opsec_eink_image()
        else:
            eink_img = self._render_image_with_shared_data(
                block_height, block_hash, mempool_api,
                shared_data, web_quality=False
            )

        # Restore default
        self._apply_orientation_settings(self.web_orientation)

        return web_img, eink_img, meme_path
    
    def _render_image_with_shared_data(self, block_height, block_hash, mempool_api,
                                      shared_data, web_quality=False, startup_mode=False,
                                      skip_hash_frame=False):
        """
        Render image using pre-collected shared data to avoid duplicate API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            shared_data (dict): Pre-collected data (holiday, fee, meme, etc.)
            web_quality (bool): True for web display, False for e-ink
            startup_mode (bool): If True, use cached data only
            skip_hash_frame (bool): If True, skip drawing the decorative hash border
            
        Returns:
            PIL.Image: Rendered dashboard image
        """
        # Get the date text first to calculate optimal font size
        date_text = self.get_localized_date(block_height)
        
        # Calculate optimal font size for the date
        optimal_date_font_size = self.get_optimal_date_font_size(date_text)
        
        # Load fonts with calculated date font size
        font_date = self._get_font(self.font_bold, optimal_date_font_size)
        font_holiday_title = self._get_font(self.font_bold, FONT_SIZE_HOLIDAY_TITLE)
        font_holiday_desc = self._get_font(self.font_regular, FONT_SIZE_HOLIDAY_DESC)
        font_block_label = self._get_font(self.font_regular, FONT_SIZE_SMALL_LABEL)
        font_block_value = self._get_font(self.font_block_height, self._scale_font_size(124, min_value=52))
        
        holiday_info = shared_data["holiday_info"]
        configured_fee = shared_data["configured_fee"]
        precached_fee = shared_data.get("precached_fee")
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
            
            # Description layout (adaptive font and wrapping)
            holiday_desc_font, desc_lines = self._get_holiday_description_layout(desc_text)

            desc_bbox = holiday_desc_font.getbbox("Ay")
            line_height = desc_bbox[3] - desc_bbox[1]
            desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * LINE_SPACING_MULTILINE

            HOLIDAY_HEIGHT = title_height + HOLIDAY_TITLE_DESC_GAP + desc_total_height + HOLIDAY_PADDING

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
                                            api_block_height, web_quality, y_override=10,
                                            skip_hash_frame=skip_hash_frame, precached_fee=precached_fee)
            
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
                    # If preserving layout, keep first N blocks in order, otherwise apply
                    # random selection with donation ordering/guarantee rules.
                    if shared_data.get('preserve_layout', False):
                        print(f"ℹ️ Landscape Mode: Preserving first {int(max_blocks)} of {len(info_blocks)} blocks")
                        info_blocks_to_render = _truncate_blocks_with_rules(info_blocks, int(max_blocks))
                    elif shared_data.get('selected_info_blocks') is not None:
                        # Reuse selection from first render to keep both screens consistent
                        preselected = shared_data['selected_info_blocks']
                        info_blocks_to_render = _truncate_blocks_with_rules(preselected, int(max_blocks))
                    else:
                        print(f"⚠️ Landscape Mode: Not enough space for all blocks. Showing {int(max_blocks)} of {len(info_blocks)}")
                        info_blocks_to_render = _sample_blocks_with_rules(info_blocks, int(max_blocks))
                        shared_data['selected_info_blocks'] = info_blocks_to_render
                else:
                    info_blocks_to_render = _move_donation_to_bottom(info_blocks)
                    if shared_data.get('selected_info_blocks') is None:
                        shared_data['selected_info_blocks'] = info_blocks_to_render
            
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
                self._render_holiday_info(info_img, info_draw, holiday_info, font_holiday_title, font_holiday_desc,
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
                    meme_img = self._open_image_robust(meme_path)
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

        # Date (merged with holiday title when a holiday is active)
        start_color = self.get_color("hash_start", web_quality)
        end_color = self.get_color("hash_end", web_quality)

        y = 20
        if holiday_info:
            # Merge date + holiday title into a single line with holiday gradient
            holiday_title = holiday_info.get("title", "")
            combined_text = f"{date_text}  {holiday_title}" if holiday_title else date_text
            # Find a font size that fits the combined text in one line.
            # Allow a lower minimum than the plain date so long holiday titles
            # (e.g. "3. Januar 2009  Bitcoins Geburtstag") don't get clipped.
            combined_font_size = self.get_optimal_date_font_size(
                combined_text, min_font_size=16)
            font_date_combined = self._get_font(self.font_bold, combined_font_size)
            bbox = font_date_combined.getbbox(combined_text)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            date_bottom_y = y + bbox[3] + 5
            # Horizontal gradient mapped to absolute x positions across all lines.
            # The longest line (date+title or any desc line) defines the full
            # gradient range; shorter centered lines use the inner portion.
            hol_start = self.get_color("holiday_start", web_quality)
            hol_end = self.get_color("holiday_end", web_quality)

            # Find global x extents across all lines (this line + description)
            desc_text_tmp = holiday_info.get("description", "")
            holiday_desc_font_tmp, desc_lines_tmp = self._get_holiday_description_layout(desc_text_tmp)
            global_x_min = x
            global_x_max = x + text_width
            for dl in desc_lines_tmp:
                dl_bbox = holiday_desc_font_tmp.getbbox(dl)
                dl_w = dl_bbox[2] - dl_bbox[0]
                dl_x = (self.width - dl_w) // 2
                global_x_min = min(global_x_min, dl_x)
                global_x_max = max(global_x_max, dl_x + dl_w)
            global_span = max(global_x_max - global_x_min, 1)

            # Render date+title via mask + horizontal gradient
            title_h = bbox[3] - bbox[1]
            text_mask = Image.new("L", (text_width, title_h), 0)
            ImageDraw.Draw(text_mask).text((-bbox[0], -bbox[1]), combined_text,
                                           font=font_date_combined, fill=255)
            title_grad = Image.new("RGBA", (text_width, title_h))
            title_grad_draw = ImageDraw.Draw(title_grad)
            for px in range(text_width):
                t = (x + px - global_x_min) / global_span
                c = tuple(int(hol_start[i] + (hol_end[i] - hol_start[i]) * t) for i in range(3)) + (255,)
                title_grad_draw.line([(px, 0), (px, title_h)], fill=c)
            title_grad.putalpha(text_mask)
            img.paste(title_grad, (x, y), title_grad)
            # Store for _render_holiday_info to use the same gradient mapping
            holiday_x_range = (global_x_min, global_span)
        else:
            bbox = font_date.getbbox(date_text)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            date_bottom_y = y + bbox[3] + 5
            for i, char in enumerate(date_text):
                t = i / max(len(date_text) - 1, 1)
                color = self.interpolate_color(start_color, end_color, t)
                char_bbox = font_date.getbbox(char)
                char_width = char_bbox[2] - char_bbox[0]
                draw.text((x, y), char, font=font_date, fill=color)
                x += char_width

        # Define constants needed for calculations
        BLOCK_MARGIN = 8
        HOLIDAY_HEIGHT = 0
        if holiday_info:
            # Title is merged into the date line — only description needs its own block
            desc_text = holiday_info.get("description", "")

            # Description layout (adaptive font and wrapping)
            holiday_desc_font, desc_lines = self._get_holiday_description_layout(desc_text)

            desc_bbox = holiday_desc_font.getbbox("Ay")
            line_height = desc_bbox[3] - desc_bbox[1]
            desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * LINE_SPACING_MULTILINE

            HOLIDAY_HEIGHT = desc_total_height + HOLIDAY_PADDING
        # Reserve space for hash frame — must stay in sync with y formula in _render_block_info_with_data.
        # y = self.height - self.block_height_area, hash frame drawn at y+3
        hash_frame_y_position = self.height - self.block_height_area + 3
        meme_bottom_y = hash_frame_y_position  # Content can go up to where hash frame visibly starts
        # Content starts after the date. Holiday is part of the content flow.
        content_top_y = date_bottom_y
        min_content_start_y = date_bottom_y + 5  # Keep at least 5px separation below date text.
        available_content_height = meme_bottom_y - content_top_y

        prioritize_large_meme = self.config.get("prioritize_large_scaled_meme", False)

        # Define standard spacing unit for balanced layout
        # Increase spacing when holiday is present to ensure visual separation
        STANDARD_SPACING = 12 if holiday_info else 10  # Reduced by ~50% to maximize meme area

        # Calculate space required for info blocks
        def calculate_info_blocks_space(config_ref):
            """Calculate the total height needed for info blocks including margins."""
            block_count = 0
            if config_ref.get("show_btc_price_block", True):
                block_count += 1
            if config_ref.get("show_countdown_block", True):
                block_count += 1
            if config_ref.get("show_halving_block", True):
                block_count += 1
            if config_ref.get("show_network_block", True):
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

        def _block_height(entry):
            block_fn, block_data = entry
            return self._get_info_block_height(block_fn, block_data, font_block_label, font_block_value)

        def _blocks_total_height(entries):
            if not entries:
                return 0
            total = 0
            for idx, entry in enumerate(entries):
                total += _block_height(entry)
                if idx < len(entries) - 1:
                    total += BLOCK_MARGIN
            return total

        def _fit_blocks_to_height(candidates, limit_height):
            fitted = []
            used = 0
            for entry in candidates:
                candidate_h = _block_height(entry)
                add_h = candidate_h if not fitted else BLOCK_MARGIN + candidate_h
                if used + add_h <= limit_height:
                    fitted.append(entry)
                    used += add_h
            return fitted

        def _is_donation_entry(entry):
            return bool(entry and entry[0].__name__ == 'render_donation_block')

        def _is_guaranteed_donation_entry(entry):
            if not _is_donation_entry(entry):
                return False
            _d = entry[1]
            return isinstance(_d, dict) and bool(_d.get('_guaranteed'))

        def _move_donation_to_bottom(entries):
            if not entries or len(entries) <= 1:
                return list(entries)
            donation_entry = next((e for e in entries if _is_donation_entry(e)), None)
            if not donation_entry:
                return list(entries)
            return [e for e in entries if e is not donation_entry] + [donation_entry]

        def _fit_blocks_with_donation_priority(candidates, limit_height):
            if not candidates or limit_height <= 0:
                return []

            candidates = list(candidates)
            guaranteed_donation = next((e for e in candidates if _is_guaranteed_donation_entry(e)), None)

            if guaranteed_donation is None:
                fitted = _fit_blocks_to_height(candidates, limit_height)
                return _move_donation_to_bottom(fitted)

            # Ensure guaranteed donation is always rendered and pinned to the bottom.
            donation_h = _block_height(guaranteed_donation)
            if donation_h >= limit_height:
                return [guaranteed_donation]

            others = [e for e in candidates if e is not guaranteed_donation]
            reserve_gap = BLOCK_MARGIN if others else 0
            others_limit = max(0, limit_height - donation_h - reserve_gap)
            fitted_others = _fit_blocks_to_height(others, others_limit)
            return fitted_others + [guaranteed_donation]

        def _sample_blocks_with_rules(candidates, max_blocks):
            if not candidates or max_blocks <= 0:
                return []

            candidates = list(candidates)
            guaranteed_donation = next((e for e in candidates if _is_guaranteed_donation_entry(e)), None)

            if guaranteed_donation is None:
                pick_n = min(len(candidates), int(max_blocks))
                picked = random.sample(candidates, pick_n)
                return _move_donation_to_bottom(picked)

            if int(max_blocks) <= 1:
                return [guaranteed_donation]

            others = [e for e in candidates if e is not guaranteed_donation]
            pick_others = min(len(others), int(max_blocks) - 1)
            picked_others = random.sample(others, pick_others) if pick_others > 0 else []
            return picked_others + [guaranteed_donation]

        def _truncate_blocks_with_rules(candidates, max_blocks):
            if not candidates or max_blocks <= 0:
                return []

            candidates = list(candidates)
            guaranteed_donation = next((e for e in candidates if _is_guaranteed_donation_entry(e)), None)

            if guaranteed_donation is None:
                trimmed = candidates[:int(max_blocks)]
                return _move_donation_to_bottom(trimmed)

            if int(max_blocks) <= 1:
                return [guaranteed_donation]

            others = [e for e in candidates if e is not guaranteed_donation]
            return others[:int(max_blocks) - 1] + [guaranteed_donation]

        if prioritize_large_meme:
            # --- PRIORITY ORDER: Holiday (always) + Donation (if guaranteed) > Meme (max remaining) > Other Info Blocks ---
            # Step 0a: Always reserve space for holiday description block
            holiday_reserved = 0
            if holiday_info:
                holiday_reserved = HOLIDAY_HEIGHT + 2 * STANDARD_SPACING

            # Step 0b: If donation is guaranteed (within 144 blocks), pre-reserve its space so
            #         the meme is sized into what is left — guaranteeing the block is shown.
            _donation_entry = next(
                (b for b in info_blocks if b[0].__name__ == 'render_donation_block'), None
            )
            _donation_guaranteed_render = False
            if _donation_entry:
                _d = _donation_entry[1]
                _donation_guaranteed_render = isinstance(_d, dict) and bool(_d.get('_guaranteed'))

            donation_reserved = 0
            if _donation_entry and _donation_guaranteed_render:
                donation_reserved = _block_height(_donation_entry) + 2 * STANDARD_SPACING

            # Step 1: Size meme to MAXIMUM possible size (minus reserved space)
            meme_img = None
            meme_height = 0
            meme_width = 0

            # Pre-calculate max meme height (needed by fallback even if image load fails)
            min_gaps = 2 * STANDARD_SPACING  # Top gap + Bottom gap
            max_meme_height = available_content_height - min_gaps - donation_reserved - holiday_reserved
            max_meme_height = max(max_meme_height, 0)

            if meme_path:
                try:
                    meme_img = self._open_image_robust(meme_path)
                    aspect_ratio = meme_img.width / meme_img.height
                    max_width = self.width - 40

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

            # --- Step 3: Holiday is always shown (space was pre-reserved) ---
            holiday_space = HOLIDAY_HEIGHT if holiday_info else 0
            
            # --- Step 4: Try to fit Info Blocks in remaining space ---
            remaining_after_holiday = space_after_meme - holiday_space
            # If we have holiday: need gaps: top, holiday-meme, meme-blocks, blocks-hash = 4 gaps
            # If no holiday: need gaps: top, meme-blocks, blocks-hash = 3 gaps
            base_gaps = (4 * STANDARD_SPACING) if holiday_space else (3 * STANDARD_SPACING)
            space_for_blocks = remaining_after_holiday - base_gaps

            info_blocks_to_render = []
            if space_for_blocks > 0 and info_blocks:
                if shared_data.get('selected_info_blocks') is not None:
                    candidate_order = _move_donation_to_bottom(shared_data['selected_info_blocks'])
                else:
                    if shared_data.get('preserve_layout', False):
                        candidate_order = _move_donation_to_bottom(info_blocks)
                    else:
                        # Non-preserved layouts compete randomly.
                        candidate_order = random.sample(info_blocks, len(info_blocks))
                        candidate_order = _move_donation_to_bottom(candidate_order)

                info_blocks_to_render = _fit_blocks_with_donation_priority(candidate_order, space_for_blocks)
                if shared_data.get('selected_info_blocks') is None:
                    shared_data['selected_info_blocks'] = info_blocks_to_render
            
            # --- Step 5: Render holiday description tight against the date, then distribute remaining space ---
            # Holiday description is pinned right below the date with a small fixed gap
            HOLIDAY_DATE_GAP = 5  # Small fixed gap between date line and holiday description
            current_y = content_top_y
            current_y = max(current_y, min_content_start_y)

            if holiday_space:
                current_y += HOLIDAY_DATE_GAP
                self._render_holiday_info(img, draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        current_y, HOLIDAY_HEIGHT, web_quality, skip_title=True,
                                        global_x_range=holiday_x_range)
                # Advance by actual visual height (description is rendered 5px higher)
                current_y += holiday_space - 5

            # Calculate even gaps for remaining elements (meme + info blocks)
            remaining_content_top = current_y
            remaining_available = meme_bottom_y - remaining_content_top
            remaining_content_height = meme_height
            if len(info_blocks_to_render):
                remaining_content_height += _blocks_total_height(info_blocks_to_render)

            if len(info_blocks_to_render) == 0 and not holiday_space:
                # No holiday, no info blocks — center the meme vertically
                center_point = content_top_y + (available_content_height // 2)
                current_y = center_point - (meme_height // 2) if meme_height > 0 else center_point
                current_y = max(current_y, min_content_start_y)
            else:
                num_gaps = 2  # top + bottom
                if len(info_blocks_to_render): num_gaps += 1  # gap between meme and info blocks
                gap_size = max(STANDARD_SPACING, (remaining_available - remaining_content_height) // num_gaps) if num_gaps > 0 else STANDARD_SPACING
                current_y = remaining_content_top + gap_size

            # Render meme (centered horizontally)
            if meme_img:
                meme_x = (self.width - meme_width) // 2
                meme_img = meme_img.convert("RGBA")
                meme_img = self.add_rounded_corners(meme_img, radius=20)  
                img.paste(meme_img, (meme_x, current_y), meme_img)
                current_y += meme_height
            else:
                fallback_h = max(50, max_meme_height) if meme_height == 0 else meme_height
                self._render_fallback_content(img, draw, current_y, fallback_h,
                                            font_holiday_title, web_quality)
                current_y += fallback_h
            
            # Add gap before info blocks for even distribution
            if len(info_blocks_to_render):
                current_y += gap_size
                
            if len(info_blocks_to_render):
                # Render info blocks without the extra BLOCK_MARGIN wrapper
                # The first block starts at current_y (already includes gap_size)
                pass

            for i, (block_fn, block_data) in enumerate(info_blocks_to_render):
                # Render each info block at current_y position
                info_vertical_offset = current_y
                try:
                    if block_fn == self.render_wallet_balances_block:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality, startup_mode=startup_mode)
                    else:
                        info_vertical_offset = block_fn(draw, info_vertical_offset, font_block_label, font_block_value, block_data, web_quality)
                except Exception as e:
                    print(f"⚠️ Error rendering info block {block_fn.__name__}: {e}")

                # Move to next block position (dynamic height + margin between blocks)
                current_y += _block_height((block_fn, block_data))
                if i < len(info_blocks_to_render) - 1:  # Add margin between blocks, but not after the last one
                    current_y += BLOCK_MARGIN

        else:
            # --- prioritize_large_scaled_meme == False ---
            # Treat all elements (Holiday, Meme, Info Block 1, Info Block 2, ...) as separate items
            # and distribute vertical space evenly between them, as well as top and bottom.
            
            # 1. Count elements and gaps (holiday is pinned to date, not part of even distribution)
            num_elements = 1  # Meme is always present (or fallback)

            # Add count of info blocks
            num_info_blocks = len(info_blocks)
            num_elements += num_info_blocks

            # Gaps = Elements + 1 (Top, between each, Bottom)
            num_gaps = num_elements + 1

            # 2. Calculate fixed content height (Info Blocks raw height)
            # Holiday is rendered tight against the date, not part of the gap distribution
            fixed_content_height = _blocks_total_height(info_blocks)

            # Account for holiday space consumed above the gap-distributed area
            # The -5 matches the upward shift applied in _render_holiday_info
            HOLIDAY_DATE_GAP = 5
            holiday_pinned_space = (HOLIDAY_HEIGHT + HOLIDAY_DATE_GAP - 5) if holiday_info else 0

            # 3. Calculate Gaps estimate to find available Meme Height
            # We use STANDARD_SPACING as a minimum/target estimate
            estimated_total_gaps = num_gaps * STANDARD_SPACING

            # 4. Calculate Max Meme Height
            max_meme_height = available_content_height - fixed_content_height - estimated_total_gaps - holiday_pinned_space
            if max_meme_height < 50: 
                max_meme_height = 50  # Minimum height constraint

            # 5. Determine actual Meme Height
            meme_img = None
            meme_height = 0
            meme_width = 0
            if meme_path:
                try:
                    meme_img = self._open_image_robust(meme_path)
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
            
            # 6. Calculate Actual Total Content Height (excluding pinned holiday)
            total_content_height = fixed_content_height + meme_height

            # 7. Calculate Real Remaining Space and Gap Size
            remaining_space = available_content_height - total_content_height - holiday_pinned_space
            
            # Distribute spacing evenly, ensuring at least STANDARD_SPACING if possible, 
            # but allow shrinking if space is tight (which shouldn't happen with our meme calc)
            # If remaining space is large (small meme), this gap will grow to center/distribute everything.
            gap_size = max(5, remaining_space // num_gaps) if num_gaps > 0 else STANDARD_SPACING
            
            # 8. Render Elements Loop
            # Pin holiday description tight against the date first
            current_y = content_top_y
            current_y = max(current_y, min_content_start_y)

            if holiday_info:
                current_y += HOLIDAY_DATE_GAP
                self._render_holiday_info(img, draw, holiday_info, font_holiday_title, font_holiday_desc,
                                        current_y, HOLIDAY_HEIGHT, web_quality, skip_title=True,
                                        global_x_range=holiday_x_range)
                current_y += HOLIDAY_HEIGHT - 5

            # Start even distribution after holiday
            current_y += gap_size

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
                    
                    # Move to next position: add dynamic block height only
                    current_y += _block_height((block_fn, block_data))
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
                                        api_block_height, web_quality,
                                        skip_hash_frame=skip_hash_frame, precached_fee=precached_fee)

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
                meme_img = self._open_image_robust(meme_path)
                
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

    def draw_hash_frame(self, draw, x_init, y_init, block_hash, rect_width=760, rect_height=80, max_width=None, web_quality=True, center=False):
        """
        Draws a block hash as a rectangular frame starting at (x, y).
        """
        padding = self._scale_px(40, min_value=16)
        # On wide screens increase interior breathing room so fee text stays inside the frame.
        extra_space = self._scale_px(11, min_value=3) if self.width >= 1000 else self._scale_px(8, min_value=3)
        # On holidays use the holiday gradient so hashframe matches the holiday date text
        if self.get_today_btc_holiday():
            start_color = self.get_color("holiday_start", web_quality)
            end_color   = self.get_color("holiday_end",   web_quality)
        else:
            start_color = self.get_color("hash_start", web_quality)
            end_color   = self.get_color("hash_end",   web_quality)

        total_chars = len(block_hash)
        block_hash_colors = [self.interpolate_color(start_color, end_color, i / max(total_chars - 1, 1)) for i in range(total_chars)]
        
        is_wide_screen = self.width >= 1000

        # Resolution-aware spacing between 2-char groups in the hash frame.
        # Keep 480x800 baseline unchanged while opening spacing on larger canvases.
        def _pair_gap_px(vertical_mode: bool) -> int:
            base_gap = 6 if vertical_mode else 3
            min_gap = 2 if vertical_mode else 1
            gap_px = self._scale_px(base_gap, min_value=min_gap)
            if self.ui_scale > 1.0:
                gap_px += int(round((self.ui_scale - 1.0) * 2))
            if is_wide_screen and not vertical_mode:
                gap_px += self._scale_px(5, min_value=1)
            return gap_px

        font_size = self._scale_font_size(11, min_value=8)
        # --- Optional scaling if max_width is given ---
        if max_width is not None:
            # Calculate required width for standard font 11
            # 23 pairs in top row. Each pair (2 chars) takes roughly:
            # bbox("0") width * 2 + extra_space.
            # Plus gaps between pairs (6px).
            # This is an approximation since we don't know the font metrics perfectly without loading.
            
            # Load font to measure
            temp_font = self._get_font(self.font_mono, self._scale_font_size(11, min_value=8))
            bbox = temp_font.getbbox("0")
            cw = bbox[2] - bbox[0]
            # Top row logic: 2 chars then gap.
            # Total width = 46 chars + 23 gaps.
            # Horizontal gap is 3px (smaller than vertical's 6px) to fit the larger font
            
            _est_horizontal_pairs = 24 if is_wide_screen else 23
            _est_horizontal_chars = _est_horizontal_pairs * 2
            _est_gaps = max(0, _est_horizontal_pairs - 1)
            estimated_full_width = (_est_horizontal_chars * cw) + (_est_gaps * _pair_gap_px(vertical_mode=False)) + self._scale_px(20, min_value=8)
            
            if estimated_full_width > max_width:
                 scale_factor = max_width / estimated_full_width
                 font_size = int(self._scale_font_size(11, min_value=8) * scale_factor)
                 if font_size < 1: font_size = 1
                 
                 # Adjust spacing by scale too
                 extra_space = int(max(1, extra_space * scale_factor))

        font = self._get_font(self.font_mono, font_size)
    
        # Character size
        bbox = font.getbbox("0")
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]

        # Hash frame geometry profile.
        # Wide screens: 24 pairs wide x 9 pairs high.
        # Default profile: 23 pairs wide x 10 pairs high.
        # The sequence length follows the overlap model: N = W + H - 1.
        horizontal_pairs = 24 if is_wide_screen else 23
        vertical_pairs_total = 9 if is_wide_screen else 10
        side_pairs_middle = max(0, vertical_pairs_total - 2)
        sequence_pair_count = horizontal_pairs + vertical_pairs_total - 1

        # Build two-character pairs from the block hash, wrapping if needed.
        hash_text = (block_hash or "").strip()
        if len(hash_text) < 2:
            hash_text = "00" * max(32, sequence_pair_count)

        pair_chars = []
        pair_colors = []
        for i in range(sequence_pair_count):
            c0 = hash_text[(2 * i) % len(hash_text)]
            c1 = hash_text[(2 * i + 1) % len(hash_text)]
            pair_chars.append(c0 + c1)
            pair_colors.append(block_hash_colors[(2 * i) % total_chars])

        # Two-pass edge construction:
        # pass 1: top starts at upper-left and uses first W pairs, then right uses remaining pairs.
        # pass 2: left starts at upper-left and uses first H pairs, then bottom uses remaining pairs.
        top_pairs_chars = pair_chars[:horizontal_pairs]
        top_pairs_colors = pair_colors[:horizontal_pairs]

        # Side columns are only the middle rows, excluding both corners.
        left_pairs_chars = pair_chars[1:1 + side_pairs_middle]
        left_pairs_colors = pair_colors[1:1 + side_pairs_middle]
        right_pairs_chars = pair_chars[horizontal_pairs:horizontal_pairs + side_pairs_middle]
        right_pairs_colors = pair_colors[horizontal_pairs:horizontal_pairs + side_pairs_middle]

        # Bottom keeps full width and starts at the lower-left corner value.
        bottom_start = vertical_pairs_total - 1
        bottom_pairs_chars = pair_chars[bottom_start:bottom_start + horizontal_pairs]
        bottom_pairs_colors = pair_colors[bottom_start:bottom_start + horizontal_pairs]

        # Use the same effective gap value as the draw loop below.
        # Vertical mode uses 6 px, horizontal uses 3 px.
        gap = _pair_gap_px(vertical_mode=(self.orientation == "vertical"))

        # Optional deterministic centering based on the actual frame geometry.
        top_pair_count = len(top_pairs_chars)
        top_effective_gaps = max(0, top_pair_count - 1)
        frame_width = (top_pair_count * 2 * int(char_w)) + (top_effective_gaps * gap)
        if center:
            x_init = max(0, (self.width - frame_width) // 2)

        # --- TOP EDGE ---
        x = x_init
        y = y_init
        for i, pair in enumerate(top_pairs_chars):
            draw.text((x, y), pair, fill=top_pairs_colors[i], font=font)
            x += (2 * int(char_w))
            if i < len(top_pairs_chars) - 1:
                x += gap

        # --- LEFT VERTICAL SIDE with horizontal pairs ---
        x_left = x_init
        x = x_left
        y = y_init + int(char_h) + extra_space
        base_side_pairs = 10
        base_side_step = int(char_h) + extra_space
        if vertical_pairs_total > 1:
            # Wide profile: moderate spacing to fit fee text inside without excess vertical room.
            if is_wide_screen:
                target_span = (vertical_pairs_total - 1) * base_side_step
            else:
                target_span = (base_side_pairs - 1) * base_side_step
            side_step = max(1, int(round(target_span / (vertical_pairs_total - 1))))
        else:
            side_step = base_side_step
        for i, pair in enumerate(left_pairs_chars):
            draw.text((x, y), pair, fill=left_pairs_colors[i], font=font)
            y += side_step

        # --- RIGHT VERTICAL SIDE ---
        x_right = x_init + frame_width - (2 * int(char_w))
        x = x_right
        y = y_init + int(char_h) + extra_space
        # Keep both sides on the same vertical cadence to avoid asymmetric heights.
        right_step = side_step
        for i, pair in enumerate(right_pairs_chars):
            draw.text((x, y), pair, fill=right_pairs_colors[i], font=font)
            y += right_step

        # --- BOTTOM EDGE ---
        # Place bottom edge from deterministic frame geometry.
        # Keep a small vertical breathing room below side pairs and scale by resolution.
        left_pair_count = max(1, len(left_pairs_chars))
        right_pair_count = max(1, len(right_pairs_chars))
        last_left_y = y_init + int(char_h) + extra_space + (left_pair_count - 1) * side_step
        last_right_y = y_init + int(char_h) + extra_space + (right_pair_count - 1) * right_step
        last_side_y = max(last_left_y, last_right_y)
        bottom_edge_nudge = self._scale_px(4, min_value=1)
        y = last_side_y + int(char_h) + max(1, extra_space // 2) + bottom_edge_nudge

        x = x_init
        for i, pair in enumerate(bottom_pairs_chars):
            draw.text((x, y), pair, fill=bottom_pairs_colors[i], font=font)
            x += (2 * int(char_w))
            if i < len(bottom_pairs_chars) - 1:
                x += gap

    def _render_block_info_with_data(self, img, draw, block_height, block_hash, font_block_label,
                                    font_block_value, mempool_api, configured_fee,
                                    api_block_height, web_quality, y_override=None,
                                    skip_hash_frame=False, precached_fee=None):
        """
        Render block information using pre-collected fee and block data.

        Args:
            skip_hash_frame: If True, skip drawing the decorative hash border.
                            Used for pre-rendering where hash is not yet known.
            precached_fee: Already-fetched fee recommendations dict, reused instead
                            of an extra API call when refreshing the gradient cache.
        """
        # Use pre-collected data instead of making new API calls
        if api_block_height is not None:
            display_block_height = str(api_block_height)
        else:
            display_block_height = str(block_height)

        # Refresh the fee cache if the block height changed, or if the entry for
        # this height has no usable fee data (e.g. a prior fetch for this same
        # height failed/timed out) — otherwise a single transient API failure
        # permanently locks the gradient to grey until the next block.
        _cached_fee_data = self.block_fee_cache.get(display_block_height, {}).get('fee_data')
        if self._block_fee_cache["current"]["height"] != display_block_height or not _cached_fee_data:
            fee_data = precached_fee or (mempool_api.get_fee_recommendations() if mempool_api else None)
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
            # Use the full block_height_area so the hash frame bottom row stays within the image.
            y = self.height - self.block_height_area
        else:
            y = self.height - (self.block_height_area - self._scale_px(70, min_value=20))
        
        # Calculate Max Width for Responsive Layout
        max_available_width = self.width - self._scale_px(24, min_value=8)

        # Compute the inner width of the hash frame so we can target exactly
        # 8 px of margin between the block-height number and the frame chars.
        # The frame uses IBMPlexMono-Bold 11 pt; char advance = getbbox("0") width.
        # top row: 46 chars, gap of 6 px (vertical) or 3 px (horizontal) after every 2.
        # Inner left  = x_init + 2*cw   (left side draws pairs of 2 chars)
        # Inner right = x_init + 44*cw + 22*gap  (= top_positions[-2])
        # Inner width = 42*cw + 22*gap
        _MARGIN = self._scale_px(8, min_value=3)  # desired px gap on each side
        try:
            _mono_font = self._get_font(self.font_mono, self._scale_font_size(11, min_value=8))
            _cw = _mono_font.getbbox("0")[2] - _mono_font.getbbox("0")[0]
            _gap_frame = self._scale_px(6, min_value=2) if self.orientation == "vertical" else self._scale_px(3, min_value=1)
            if self.ui_scale > 1.0:
                _gap_frame += int(round((self.ui_scale - 1.0) * 2))
            if self.width >= 1000 and self.orientation != "vertical":
                _gap_frame += self._scale_px(2, min_value=1)
            _horizontal_pairs = 24 if self.width >= 1000 else 23
            _horizontal_chars = _horizontal_pairs * 2
            _horizontal_gaps = max(0, _horizontal_pairs - 1)
            _inner_frame_width = (_horizontal_chars - 4) * _cw + _horizontal_gaps * _gap_frame
            frame_target_width = max(self._scale_px(200, min_value=80), _inner_frame_width - 2 * _MARGIN)
        except Exception:
            frame_target_width = max_available_width - self._scale_px(20, min_value=8)

        # Format block height string
        if mempool_api:
            formatted_height = mempool_api.format_block_height(display_block_height)
        else:
            try:
                height_int = int(display_block_height)
                formatted_height = f"{height_int:,}".replace(",", ".")
            except (ValueError, TypeError):
                formatted_height = str(display_block_height)

        # Dot-advance compression: tighter dots narrow the number so it fits
        # comfortably inside the hash frame with the desired margin.
        # 0.35 means each '.' uses 35 % of its natural advance width.
        _DOT_FRACTION = 0.35

        # Scale block-height font so the squeezed text fits inside frame_target_width
        used_font_block_value = font_block_value
        text_width = ImageRenderer._squeezed_text_width(formatted_height, used_font_block_value, _DOT_FRACTION)

        if text_width > frame_target_width:
            ratio = frame_target_width / text_width
            new_size = max(self._scale_font_size(20, min_value=12), int(self._scale_font_size(124, min_value=52) * ratio))
            try:
                used_font_block_value = self._get_font(self.font_block_height, new_size)
                # Re-measure after font size change
                text_width = ImageRenderer._squeezed_text_width(formatted_height, used_font_block_value, _DOT_FRACTION)
            except Exception as e:
                print(f"Error scaling font: {e}")

        # Draw "Block Height" label
        # None
        
        if self.orientation == "vertical":
            # --- VERTICAL MODE (fixed geometry, not auto-scaled like landscape below) ---
            # Draw hash frame centered using measured geometry
            if not skip_hash_frame:
                self.draw_hash_frame(draw, 12, y+3, block_hash, web_quality=web_quality, center=True)
            y = y + self._scale_px(24, min_value=8)

            # When the font is scaled down (7-digit number), shift the text down by
            # half the height reduction so it stays vertically centred in the frame.
            base_ascent = font_block_value.getmetrics()[0]
            used_ascent = used_font_block_value.getmetrics()[0]
            vertical_centering_offset = max(0, (base_ascent - used_ascent) // 2)

            # Draw block height with color based on current fees (move up by 10px)
            value_y = y - self._scale_px(25, min_value=8) + vertical_centering_offset
            x = (self.width - text_width) // 2  # text_width already squeezed+scaled above
            self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y + self._scale_px(10, min_value=3),
                                             used_font_block_value,
                                             block_height_start_color, block_height_end_color,
                                             dot_fraction=_DOT_FRACTION)
            
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
                    font_small = self._get_font(self.font_regular, self._scale_font_size(12, min_value=8))
                except:
                    font_small = font_block_label
                    
                bbox = used_font_block_value.getbbox(formatted_height)
                fee_y = value_y + bbox[3] - bbox[1] + self._scale_px(42, min_value=14)
                
                # Fee label always uses bottom color of gradient
                fee_color = block_height_end_color
                self.draw_centered(draw, fee_text, fee_y, font_small, fee_color)

            return # Exit early for vertical

        # --- LANDSCAPE/RESPONSIVE MODE ---
        # Draw hash frame centered using measured geometry.
        # width auto-scaled by draw_hash_frame if max_width passed
        if not skip_hash_frame:
            self.draw_hash_frame(draw, 32, y, block_hash, web_quality=web_quality, max_width=max_available_width, center=True)
        
        # Center Block Height Text inside the frame (approx y+15)
        value_y = y + self._scale_px(15, min_value=5)
        
        x = (self.width - text_width) // 2  # text_width already squeezed+scaled above
        self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y,
                                         used_font_block_value,
                                         block_height_start_color, block_height_end_color,
                                         dot_fraction=_DOT_FRACTION)
        
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
                font_small = self._get_font(self.font_regular, self._scale_font_size(12, min_value=8))
            except:
                font_small = font_block_label
            
            # Draw fee info in smaller text below block height
            bbox = used_font_block_value.getbbox(formatted_height)
            text_height = bbox[3] - bbox[1]
            # Extra gap avoids overlapping the block height text above
            fee_y = value_y + text_height + self._scale_px(25, min_value=8)

            # Fee label always uses bottom color of gradient
            fee_color = block_height_end_color
            self.draw_centered(draw, fee_text, fee_y, font_small, fee_color)

        # Draw shortened hash
        # (covered by frame)
        
        y += self._scale_px(105, min_value=35)
        # self.draw_centered(draw, short_hash, y, font_block_label)
    
    def patch_hash_frame_on_image(self, img, block_hash, web_quality, y_override=None):
        """
        Draw only the hash frame border onto an existing pre-rendered image.
        
        Used to stamp the actual block hash onto a pre-rendered image that was
        generated with skip_hash_frame=True. This avoids a full re-render when
        only the decorative hash border needs updating.
        
        Args:
            img: PIL Image to draw on (modified in-place)
            block_hash: The actual block hash string
            web_quality: True for web image, False for e-ink
            y_override: Override y position (for split-screen block_info_img)
        """
        draw = ImageDraw.Draw(img)
        
        # Replicate the y calculation from _render_block_info_with_data
        if y_override is not None:
            y = y_override
        elif self.orientation == "vertical":
            y = self.height - self.block_height_area
        else:
            y = self.height - (self.block_height_area - self._scale_px(70, min_value=20))
        
        max_available_width = self.width - self._scale_px(24, min_value=8)
        
        if self.orientation == "vertical":
            self.draw_hash_frame(draw, 12, y + 3, block_hash, web_quality=web_quality, center=True)
        else:
            self.draw_hash_frame(draw, 32, y, block_hash, web_quality=web_quality,
                                max_width=max_available_width, center=True)

    @staticmethod
    def _wrap_text_to_lines(text: str, font, max_width: float, max_lines: int):
        """Word-wrap *text* into at most *max_lines* pixel-width-limited lines.

        Returns a list of lines where ALL words fit cleanly, or None if the text
        cannot be arranged without truncation (signalling the caller to reduce
        font size and retry).
        """
        _getlength = ImageRenderer._emoji_aware_getlength
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if _getlength(word, font) > max_width:
                return None  # single word too wide — reduce font size
            candidate = (current + " " + word).strip()
            if _getlength(candidate, font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    return None  # would need more lines than allowed — reduce font size
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines

    @staticmethod
    def _wrap_text_truncated(text: str, font, max_width: float, max_lines: int) -> list:
        """Fill up to *max_lines* with word-wrapped text, adding '…' at the last word
        boundary if not all words fit.  Used as a last-resort fallback at minimum
        font size when _wrap_text_to_lines cannot find a clean fit.
        """
        _getlength = ImageRenderer._emoji_aware_getlength
        words = text.split()
        lines = []
        current = ""
        for word in words:
            # If a single word is too wide, squeeze it in alone (edge case at tiny sizes)
            candidate = (current + " " + word).strip()
            if _getlength(candidate, font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        # Add ellipsis at word boundary if words were cut off
        if lines and len(" ".join(lines).split()) < len(words):
            last = lines[-1]
            parts = last.split()
            while parts:
                candidate = " ".join(parts) + "…"
                if _getlength(candidate, font) <= max_width:
                    lines[-1] = candidate
                    break
                parts.pop()
            else:
                lines[-1] = "…"
        return lines or ["…"]

    @staticmethod
    def _squeezed_text_width(text: str, font, dot_fraction: float = 1.0) -> int:
        """Measure rendered pixel width of *text* with optional dot-advance compression.

        When dot_fraction < 1.0 each '.' is rendered with a symmetric fixed gap on
        each side scaled from the font's natural side bearing.  This matches the
        rendering done by draw_vertical_gradient_text exactly.
        """
        if dot_fraction >= 1.0:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0]
        cx = 0.0
        for ch in text:
            if ch == '.' :
                bb = font.getbbox(ch)
                glyph_w = bb[2] - bb[0]
                natural_gap = max(0.5, (font.getlength(ch) - glyph_w) / 2)
                gap = max(1.0, natural_gap * dot_fraction)
                cx += glyph_w + 2 * gap
            else:
                cx += font.getlength(ch)
        return int(cx)

    def draw_vertical_gradient_text(self, img, draw, text, x, y, font, start_color, end_color,
                                    dot_fraction: float = 1.0):
        """Draw *text* at (x, y) with a top-to-bottom colour gradient.

        dot_fraction — when < 1.0 each '.' is rendered with that fraction of its
        natural advance width, tightening the gap around thousand-separator dots.
        Pass the same value to _squeezed_text_width() when calculating the x
        position so centering stays accurate.
        """
        ascent, descent = font.getmetrics()
        text_height = ascent + descent + 8  # extra pixels for safety

        if dot_fraction >= 1.0:
            # Fast path: single draw.text() call, natural spacing
            text_width = font.getbbox(text)[2] - font.getbbox(text)[0]
            text_img = Image.new("L", (text_width, text_height), 0)
            ImageDraw.Draw(text_img).text((0, 0), text, font=font, fill=255)
        else:
            # Char-by-char path: centre each dot glyph in its compressed slot so
            # the gap on both sides of '.' is equal.
            # gap = natural_side_bearing * dot_fraction  (min 1 px)
            # advance = glyph_width + 2 * gap
            # draw_x  = cx + gap - bb[0]  (left pixel of glyph lands at cx+gap)
            text_width = ImageRenderer._squeezed_text_width(text, font, dot_fraction)
            text_img = Image.new("L", (text_width, text_height), 0)
            text_draw = ImageDraw.Draw(text_img)
            cx = 0.0
            for ch in text:
                if ch == '.':
                    adv = font.getlength(ch)
                    bb = font.getbbox(ch)
                    glyph_w = bb[2] - bb[0]
                    natural_gap = max(0.5, (adv - glyph_w) / 2)
                    gap = max(1.0, natural_gap * dot_fraction)
                    text_draw.text((int(cx + gap - bb[0]), 0), ch, font=font, fill=255)
                    cx += glyph_w + 2 * gap
                else:
                    text_draw.text((int(cx), 0), ch, font=font, fill=255)
                    cx += font.getlength(ch)

        size = (text_width, text_height)

        # Vertical gradient mask
        gradient = Image.new("RGBA", size)
        for yy in range(size[1]):
            t = yy / max(size[1] - 1, 1)
            color = tuple(int(start_color[i] + ((end_color[i] - start_color[i]) * t)) for i in range(3)) + (255,)
            ImageDraw.Draw(gradient).line([(0, yy), (size[0], yy)], fill=color)

        gradient.putalpha(text_img)
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
                meme_img = self._open_image_robust(meme_path)
                
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
    

    def _render_holiday_info(self, img, draw, holiday_info, font_title, font_desc,
                           holiday_box_top_y, holiday_height, web_quality=False,
                           skip_title=False, global_x_range=None):
        """Render Bitcoin holiday information with a horizontal gradient.

        The gradient flows left-to-right (holiday_start → holiday_end) mapped
        to absolute x positions.  The longest line spans the full colour range;
        shorter centered lines use the inner portion so equal x positions
        always show the same colour tone.

        Args:
            img (Image): Target image to composite onto
            draw (ImageDraw): Drawing context (used only for layout calculations)
            holiday_info (dict): Holiday information
            font_title (ImageFont): Font for holiday title
            font_desc (ImageFont): Font for holiday description
            holiday_box_top_y (int): Top Y position of the holiday box
            holiday_height (int): Reserved height for holiday content
            web_quality (bool): True for web display, False for e-ink
            skip_title (bool): If True, only render description (title merged with date)
            global_x_range (tuple|None): (x_min, span) from the caller so the
                date+title line and description share the same gradient mapping.
        """
        # Get configurable holiday gradient colors
        hol_start = self.get_color("holiday_start", web_quality)
        hol_end = self.get_color("holiday_end", web_quality)

        print(f"🎄 Rendering holiday: {holiday_info.get('title', 'No title')}")

        title_text = holiday_info.get("title", "Bitcoin Holiday")
        desc_text = holiday_info.get("description", "")

        # Calculate description lines with adaptive font and wrapping
        holiday_desc_font, desc_lines = self._get_holiday_description_layout(desc_text)
        print(f"   📝 Holiday description wrapped into {len(desc_lines)} line(s)")

        # Calculate total description height
        desc_bbox = holiday_desc_font.getbbox("Ay")  # Sample text for line height
        line_height = desc_bbox[3] - desc_bbox[1]
        desc_total_height = len(desc_lines) * line_height + (len(desc_lines) - 1) * LINE_SPACING_MULTILINE

        if skip_title:
            # Title already merged with date line — pin description to top of block
            content_y = holiday_box_top_y - 5
        else:
            # Full render: title + description (landscape mode)
            title_bbox_val = font_title.getbbox(title_text)
            title_height_val = title_bbox_val[3] - title_bbox_val[1]
            total_holiday_height = title_height_val + HOLIDAY_TITLE_DESC_GAP + desc_total_height
            vertical_padding = (holiday_height - total_holiday_height) // 2
            content_y = holiday_box_top_y + vertical_padding - 5

        # --- Horizontal gradient mapped to absolute x positions ---
        # The longest line (title or any description line) defines the full
        # gradient range (x_min → x_max = start_color → end_color).
        # Shorter centered lines use the inner portion of the gradient,
        # so equal x positions always have the same colour tone.

        img_width = img.size[0]

        # Use caller-provided global x range, or compute from local lines
        if global_x_range:
            global_x_min, global_span = global_x_range
        else:
            # Collect x extents of all lines to find global min/max
            # Use visual width and simple centering to match the date+title code
            line_extents = []  # (x_start, width) for each line
            for line in desc_lines:
                lb = holiday_desc_font.getbbox(line)
                lw = lb[2] - lb[0]
                lx = (img_width - lw) // 2
                line_extents.append((lx, lw))

            if not skip_title:
                title_bbox_full = font_title.getbbox(title_text)
                title_w = title_bbox_full[2] - title_bbox_full[0]
                title_h = title_bbox_full[3] - title_bbox_full[1]
                tx = (img_width - title_w) // 2
                line_extents.append((tx, title_w))

            global_x_min = min(lx for lx, _ in line_extents) if line_extents else 0
            global_x_max = max(lx + lw for lx, lw in line_extents) if line_extents else img_width
            global_span = max(global_x_max - global_x_min, 1)

        # Render title (landscape mode only) using mask + horizontal gradient
        if not skip_title:
            if global_x_range:
                # Ensure title dimensions are available even when extents were not computed
                title_bbox_full = font_title.getbbox(title_text)
                title_w = title_bbox_full[2] - title_bbox_full[0]
                title_h = title_bbox_full[3] - title_bbox_full[1]
                tx = (img_width - title_w) // 2
            title_mask = Image.new("L", (title_w, title_h), 0)
            ImageDraw.Draw(title_mask).text((-title_bbox_full[0], -title_bbox_full[1]),
                                            title_text, font=font_title, fill=255)
            title_grad = Image.new("RGBA", (title_w, title_h))
            tg_draw = ImageDraw.Draw(title_grad)
            for px in range(title_w):
                t = (tx + px - global_x_min) / global_span
                c = tuple(int(hol_start[i] + (hol_end[i] - hol_start[i]) * t) for i in range(3)) + (255,)
                tg_draw.line([(px, 0), (px, title_h)], fill=c)
            title_grad.putalpha(title_mask)
            img.paste(title_grad, (tx, content_y), title_grad)

            content_y += title_height_val + HOLIDAY_TITLE_DESC_GAP

        # Render description lines using mask + horizontal gradient
        # Use ascent+descent for line height to avoid clipping descenders (g, p, q, y)
        ascent, descent = holiday_desc_font.getmetrics()
        full_line_height = ascent + descent
        desc_canvas_w = img_width
        desc_canvas_h = max(len(desc_lines) * full_line_height + (len(desc_lines) - 1) * LINE_SPACING_MULTILINE, 1)

        desc_mask = Image.new("L", (desc_canvas_w, desc_canvas_h), 0)
        desc_mask_draw = ImageDraw.Draw(desc_mask)

        local_y = 0
        for line in desc_lines:
            bbox = holiday_desc_font.getbbox(line)
            text_w = bbox[2] - bbox[0]
            # Centre using visual width, then offset by -bbox[0] so the visual
            # left edge lands exactly at the centred x — matching the date+title
            # gradient coordinate system.
            lx = (img_width - text_w) // 2
            desc_mask_draw.text((lx - bbox[0], local_y), line, font=holiday_desc_font, fill=255)
            local_y += full_line_height + LINE_SPACING_MULTILINE

        # Horizontal gradient across the full canvas width
        desc_grad = Image.new("RGBA", (desc_canvas_w, desc_canvas_h))
        dg_draw = ImageDraw.Draw(desc_grad)
        for px in range(desc_canvas_w):
            t = (px - global_x_min) / global_span
            t = max(0.0, min(1.0, t))
            c = tuple(int(hol_start[i] + (hol_end[i] - hol_start[i]) * t) for i in range(3)) + (255,)
            dg_draw.line([(px, 0), (px, desc_canvas_h)], fill=c)
        desc_grad.putalpha(desc_mask)
        img.paste(desc_grad, (0, content_y), desc_grad)
    

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
