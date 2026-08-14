"""Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit.
"""

import math

from babel.dates import format_date
from datetime import datetime


# ── Absolute scale (mode A) ───────────────────────────────────────────────
# The original fixed table, kept as the default for anyone who wants the old
# behaviour and as the fallback whenever no baseline is available yet. Its
# weakness is the reason the relative modes exist: the first three stops cover
# 0-5 sat/vB in a single green, so a year of low fees renders as one colour.
# fmt: off
ABSOLUTE_STOPS = [
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

# ── Relative scales (modes B and C) ───────────────────────────────────────
# Positions are log2 of (fee / baseline), so each whole step is a doubling.
# Fees move multiplicatively - the gap between 1 and 2 sat/vB matters as much
# as the gap between 20 and 40 - and a linear ratio axis would squash the
# entire cheap half of the range into the first tenth of the scale.
#
#   -2.0 = a quarter of normal      0.0 = exactly normal      +2.0 = 4x normal

RELATIVE_RAINBOW_STOPS = [
    (-2.0, (  0,  90, 255)),   # blue       - exceptionally cheap
    (-1.0, (  0, 170, 200)),   # teal
    (-0.4, (  0, 200,  70)),   # green      - comfortably below normal
    ( 0.0, (235, 215,   0)),   # yellow     - normal
    ( 0.38,(255, 180,   0)),   # amber      - ~1.3x normal
    ( 0.72,(255, 130,   0)),   # orange     - ~1.65x
    ( 1.10,(245,  75,  10)),   # orange-red - ~2.1x
    ( 1.55,(215,  25,  25)),   # red        - ~2.9x
    ( 2.00,(150,  10,  30)),   # deep red   - 4x and beyond
]

# Mode C splits the scale around a neutral centre instead of running one ramp
# through it: cool colours mean cheaper than usual, warm colours mean dearer,
# and the neutral band in the middle is handled separately (see NEUTRAL_*).
RELATIVE_NEUTRAL_COOL = [
    (-2.0, (  0,  90, 255)),   # blue    - exceptionally cheap
    (-1.0, (  0, 160, 210)),   # teal
    (-0.5, (  0, 200,  70)),   # green
    (-0.07,(  0, 200,  70)),   # green, right up to the neutral band
]
RELATIVE_NEUTRAL_WARM = [
    ( 0.07,(235, 215,   0)),   # yellow, straight out of the neutral band
    ( 0.38,(255, 180,   0)),   # amber      - ~1.3x normal
    ( 0.72,(255, 130,   0)),   # orange     - ~1.65x
    ( 1.10,(245,  75,  10)),   # orange-red - ~2.1x
    ( 1.55,(215,  25,  25)),   # red        - ~2.9x
    ( 2.00,(150,  10,  30)),   # deep red   - 4x and beyond
]
# fmt: on

# What "normal" looks like. Black on a light background, near-white on a dark
# one - the neutral reading has to be the colour that says "nothing to see
# here" for the theme in use, and black text on a dark panel says nothing at all.
NEUTRAL_LIGHT = (20, 20, 25)
NEUTRAL_DARK = (235, 235, 240)

# No baseline yet, or no fee at all.
UNKNOWN_COLOR = (120, 120, 130)

# Below the relay minimum there is nothing cheaper to wait for, so 1 sat/vB is
# always the cheapest colour no matter what the baseline says. Without this a
# quiet week drags the baseline down to 1 and then 1 sat/vB reads as "normal",
# which is exactly backwards - it is as good as it ever gets.
ABSOLUTE_CHEAP_FLOOR = 1.0

# Text colours the panel can actually produce. White is deliberately absent:
# it is the background, and snapping a fee colour to it erases the digits.
EINK_SNAP_6 = [(0, 0, 0), (255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255)]
EINK_SNAP_7 = EINK_SNAP_6 + [(255, 128, 0)]

# Panels with an orange ink. Everything else gets the six-colour set, which is
# the safe assumption: emitting orange to a panel without it dithers into a
# red/yellow checkerboard across the glyphs.
ORANGE_CAPABLE_PANELS = {"epd7in3f"}


def _interpolate(stops, position, low_default=None, high_default=None):
    """Linear interpolation across a sorted (position, rgb) table."""
    if position <= stops[0][0]:
        return low_default or stops[0][1]
    if position >= stops[-1][0]:
        return high_default or stops[-1][1]
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= position <= p1:
            span = (p1 - p0) or 1
            t = (position - p0) / span
            return tuple(int(c0[j] + t * (c1[j] - c0[j])) for j in range(3))
    return stops[-1][1]


def _snap_to_palette(rgb, palette):
    """Nearest ink the panel actually has.

    Weighted to approximate perceived brightness rather than raw RGB distance,
    so a mid-yellow does not land on green just because the green channel is
    numerically closer.
    """
    best = None
    best_d = None
    for cand in palette:
        d = (2.0 * (rgb[0] - cand[0]) ** 2
             + 4.0 * (rgb[1] - cand[1]) ** 2
             + 3.0 * (rgb[2] - cand[2]) ** 2)
        if best_d is None or d < best_d:
            best, best_d = cand, d
    return best


class FormattingMixin:
    """Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit."""

    def _fee_color_for(self, fee, baseline, mode, is_dark, neutral_band):
        """One fee to one RGB triple, before any theme or panel treatment."""
        if fee is None:
            return UNKNOWN_COLOR

        # No baseline means no opinion about what normal is. Falling back to the
        # absolute table is better than inventing a ratio from three samples.
        if mode == "absolute" or not baseline or baseline <= 0:
            return _interpolate(self._absolute_stops(), fee)

        if fee <= ABSOLUTE_CHEAP_FLOOR:
            cheapest = (RELATIVE_RAINBOW_STOPS if mode == "relative_rainbow"
                        else RELATIVE_NEUTRAL_COOL)[0][1]
            return cheapest

        ratio = fee / float(baseline)
        if ratio <= 0:
            return UNKNOWN_COLOR
        position = math.log2(ratio)

        if mode == "relative_rainbow":
            return _interpolate(RELATIVE_RAINBOW_STOPS, position)

        # relative_neutral: a flat neutral plateau, then colour outwards.
        # The band is a plateau rather than a single point so "normal" reads as
        # a deliberate state instead of a colour the gradient happens to cross.
        if abs(ratio - 1.0) <= neutral_band:
            return NEUTRAL_DARK if is_dark else NEUTRAL_LIGHT
        if position < 0:
            return _interpolate(RELATIVE_NEUTRAL_COOL, position)
        return _interpolate(RELATIVE_NEUTRAL_WARM, position)

    def _absolute_stops(self):
        """Mode A's table: the user's own thresholds, else the built-in ones.

        Config format is [[fee, "#rrggbb"], ...]. Anything malformed falls back
        whole rather than partially, so a typo cannot produce a table that is
        half custom and half default.
        """
        raw = self.config.get("fee_color_stops")
        if not raw:
            return ABSOLUTE_STOPS
        try:
            parsed = []
            for fee, hex_color in raw:
                h = str(hex_color).lstrip('#')
                if len(h) != 6:
                    return ABSOLUTE_STOPS
                parsed.append((float(fee), (int(h[0:2], 16),
                                            int(h[2:4], 16),
                                            int(h[4:6], 16))))
            if len(parsed) < 2:
                return ABSOLUTE_STOPS
            return sorted(parsed, key=lambda s: s[0])
        except (TypeError, ValueError):
            return ABSOLUTE_STOPS

    def fee_to_colors(self, current_fee, recent_fee, web_quality=False):
        """
        Returns (top_color, bottom_color) for the block-height text gradient.

        The gradient runs from the previous block's fee at the top to the
        current fee at the bottom, so the digits show both where the fee is and
        which way it is moving. When the fee has not changed the two ends agree
        and it renders flat, exactly as before.

        Colour meaning depends on `fee_color_mode`:
          absolute         - fixed sat/vB thresholds (the original behaviour)
          relative_rainbow - blue/green/yellow/orange/red against the baseline
          relative_neutral - neutral at the baseline, cool below, warm above

        On e-ink the result snaps to an ink the panel actually has, because a
        colour it cannot make is dithered into a checkerboard and thin digits
        turn to speckle.
        """
        if web_quality:
            is_dark = self.config.get("color_mode_dark", True)
        else:
            is_dark = self.config.get("eink_dark_mode", False)

        mode = self.config.get("fee_color_mode", "relative_neutral")
        if mode not in ("absolute", "relative_rainbow", "relative_neutral"):
            mode = "relative_neutral"

        try:
            neutral_band = float(self.config.get("fee_neutral_band_pct", 5)) / 100.0
        except (TypeError, ValueError):
            neutral_band = 0.05
        neutral_band = max(0.0, min(0.5, neutral_band))

        baseline = None
        store = getattr(self, "fee_baseline", None)
        if store is not None and mode != "absolute":
            try:
                baseline = store.baseline()
            except Exception:
                baseline = None

        current_color = self._fee_color_for(current_fee, baseline, mode, is_dark, neutral_band)
        recent_color = self._fee_color_for(recent_fee, baseline, mode, is_dark, neutral_band)

        if not web_quality:
            # Snap first, then skip the wash/saturate treatment entirely: those
            # produce intermediate tones that are exactly what the panel cannot
            # render, so applying them after snapping would undo the snapping.
            panel = self.config.get("omni_device_name", "")
            palette = (EINK_SNAP_7 if panel in ORANGE_CAPABLE_PANELS
                       else EINK_SNAP_6)
            top = _snap_to_palette(recent_color, palette)
            bottom = _snap_to_palette(current_color, palette)
            return top, bottom

        def boost_saturation(c, factor=0.85):
            """Boost color saturation"""
            return tuple(min(255, int(v * factor)) for v in c)

        def wash_out(c, amount=0.5):
            """Wash color towards white, keeping its hue readable.

            This used to wash 85% of the way to white, which was fine when both
            ends of the gradient came from the same fee - it was decoration. Now
            the top end carries the previous block's fee, and at 85% every hue
            arrives as the same near-white: a fee that fell from 200 to 1 looked
            identical to one that rose from 1 to 200. Half-way keeps the top
            clearly lighter than the bottom, so the fee label stays the readable
            end, while leaving enough saturation to tell blue from red.
            """
            return tuple(int(v + amount * (255 - v)) for v in c)

        # The fee label sits at the bottom, so the current fee takes the end of
        # the treatment that stays readable against the background, and the
        # previous fee takes the other one. Unchanged fees give two shades of a
        # single hue, which is what this looked like before the direction of
        # travel was encoded at all.
        if is_dark:
            # Dark background: bottom must be the light end.
            return boost_saturation(recent_color), wash_out(current_color)
        # Light background: bottom must be the dark end.
        return wash_out(recent_color), boost_saturation(current_color)



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
