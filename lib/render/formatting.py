"""Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit.
"""

from babel.dates import format_date
from datetime import datetime


class FormattingMixin:
    """Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit."""

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
