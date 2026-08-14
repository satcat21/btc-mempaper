"""Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit.
"""

import math

from babel.dates import format_date
from datetime import datetime


# ── The three scales ──────────────────────────────────────────────────────
# constant  the configured colour, always. The fee is not consulted.
# relative  cheap or dear against what this same fee tier has cost lately.
# manual    fixed sat/vB thresholds the user sets by hand.
MODES = ("constant", "relative", "manual")

def normalise_mode(raw):
    """The stored scale name, or the default if it is not one we know."""
    raw = str(raw or "").strip()
    return raw if raw in MODES else "relative"


# ── Manual scale (mode C) ─────────────────────────────────────────────────
# Five fixed colours whose thresholds the user sets, in real sat/vB. No
# baseline is involved, so this mode says something on a fresh install and
# never changes its mind about a given fee. The trade is the opposite of the
# relative scale's: a threshold chosen in a quiet month reads the same in a
# busy one, whether or not that is still the advice the user wanted.
# fmt: off
MANUAL_COLORS = (
    ("blue",   (  0,  90, 255)),   # nothing cheaper worth waiting for
    ("green",  (  0, 200,  70)),   # comfortable
    ("yellow", (235, 215,   0)),   # starting to cost
    ("orange", (255, 130,   0)),   # expensive
    ("red",    (215,  25,  25)),   # wait unless it is urgent
)

# Defaults for a market where blocks clear under 1 sat/vB most of the time and
# 5 is already worth sitting out. Every one is editable.
MANUAL_DEFAULTS = {
    "blue": 0.5, "green": 0.8, "yellow": 1.5, "orange": 3.0, "red": 5.0,
}

# ── Relative scale (mode B) ───────────────────────────────────────────────
# Positions are log2 of (fee / baseline), so each whole step is a doubling.
# Fees move multiplicatively - the gap between 1 and 2 sat/vB matters as much
# as the gap between 20 and 40 - and a linear ratio axis would squash the
# entire cheap half of the range into the first tenth of the scale.
#
#   -2.0 = a quarter of normal      0.0 = exactly normal      +2.0 = 4x normal
#
# Split around a neutral centre rather than running one ramp through it: cool
# means cheaper than usual, warm means dearer, and the band in the middle is
# handled separately so "ordinary" gets the user's own colour.
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

# The base colour of the block height: what the digits read as when the fee has
# nothing to say, and the anchor end of the gradient in every other case.
# A neutral grey by default, in the two tones the themes need - dark enough to
# hold up against white, light enough against black. Neutral on purpose: this is
# the "nothing to report" reading, so it must not compete with the fee hues that
# surround it. Both are user-configurable via color_block_height_light /
# color_block_height_dark; these are the defaults.
BASE_LIGHT = (60, 60, 70)      # #3C3C46
BASE_DARK = (200, 200, 210)    # #C8C8D2

# How far a derived tone travels toward white. The gradient needs both ends
# visibly different without the lighter one washing out to the background, and
# this is the same half-way figure the fee ends already use.
LIGHTEN_AMOUNT = 0.45

# No baseline yet, or no fee at all.
UNKNOWN_COLOR = (120, 120, 130)

# A fee at or under the floor reads as the cheapest colour whatever the ratio
# says, because there is nothing cheaper to wait for.
#
# The floor is not a constant. It is whatever the mempool is currently
# accepting, so the caller passes minimumFee from the live fee recommendations.
# Hardcoding 1 sat/vB was wrong in both directions: blocks clear at fractions of
# a sat/vB, so everything from 0.1 to 1.0 collapsed onto one colour - a full
# order of magnitude, and precisely the range a quiet market lives in.
#
# Only while the baseline is above it, either way. At a median of 0.5 a fee of
# 1.0 is twice the going rate and must not render as the best moment in a month.
#
# 0.0 when the network does not say: no floor at all rather than a wrong one.
# That is also the honest reading once the mempool has cleared entirely, where
# minimumFee itself goes to zero and nothing is waiting to be undercut.
FALLBACK_CHEAP_FLOOR = 0.0


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


def _lighten(rgb, amount=LIGHTEN_AMOUNT):
    """Move a colour toward white, keeping its hue."""
    return tuple(int(v + amount * (255 - v)) for v in rgb)


def _deepen(rgb, factor=0.85):
    """Move a colour toward black, keeping its hue."""
    return tuple(max(0, min(255, int(v * factor))) for v in rgb)


def _preview_fee(v):
    """A preview figure at a sensible precision, and never zero.

    Two decimals under 1 sat/vB, one above. Blocks clear at fractions of a
    sat/vB in a quiet month, and rounding those to whole numbers collapsed
    every scenario onto the same figure. Never zero, because a fee of 0 has no
    ratio and would preview as the grey "unknown" swatch - which reads as a
    broken preview rather than a cheap one.
    """
    try:
        v = max(0.01, float(v))
    except (TypeError, ValueError):
        return None
    return round(v, 2) if v < 1 else round(v, 1)


class FormattingMixin:
    """Presentation helpers with no layout dependency: fee-to-colour mapping, localised date strings and the font size that makes a date fit."""

    def _fee_color_for(self, fee, baseline, mode, neutral_band,
                       cheap_floor=FALLBACK_CHEAP_FLOOR):
        """One fee to one RGB triple, before any theme or panel treatment.

        Returns None when the fee carries no signal - inside the neutral band,
        where the whole point is that nothing stands out. The caller substitutes
        the configured base colour, which is what "nothing to see here" looks
        like for the theme in use.

        `cheap_floor` is the network's current minimum, below which one fee is
        not meaningfully cheaper than another. Zero disables the floor entirely.
        """
        # Constant: the fee has no say. None *is* the answer here - it means
        # "the configured colour", which is the whole of this mode.
        if mode == "constant":
            return None

        if fee is None:
            return UNKNOWN_COLOR

        if mode == "manual":
            return _interpolate(self._manual_stops(), fee)

        # Relative, but nothing to be relative to yet. The manual table is a
        # better answer than a ratio invented from a handful of minutes.
        if not baseline or baseline <= 0:
            return _interpolate(self._manual_stops(), fee)

        if cheap_floor and fee <= cheap_floor < baseline:
            return RELATIVE_NEUTRAL_COOL[0][1]

        ratio = fee / float(baseline)
        if ratio <= 0:
            return UNKNOWN_COLOR
        position = math.log2(ratio)

        # A flat neutral plateau, then colour outwards.
        # The band is a plateau rather than a single point so "normal" reads as
        # a deliberate state instead of a colour the gradient happens to cross.
        if abs(ratio - 1.0) <= neutral_band:
            return None
        if position < 0:
            return _interpolate(RELATIVE_NEUTRAL_COOL, position)
        return _interpolate(RELATIVE_NEUTRAL_WARM, position)

    def _base_color(self, is_dark):
        """The configured block-height colour for the theme in use.

        Format is "#rrggbb", the same as every other colour setting. Anything
        unparseable falls back to the built-in default rather than raising:
        a bad colour must not take the whole render down with it.
        """
        key = "color_block_height_dark" if is_dark else "color_block_height_light"
        fallback = BASE_DARK if is_dark else BASE_LIGHT
        raw = self.config.get(key)
        if not raw:
            return fallback
        h = str(raw).lstrip('#')
        if len(h) != 6:
            return fallback
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return fallback

    def manual_thresholds(self):
        """The sat/vB level each of the five colours starts at.

        One number per colour, read individually: a typo in one field falls
        back to that colour's default rather than discarding the other four,
        which is what the user would expect from five separate inputs.

        Sorted on the way out. Thresholds that cross over - red below orange,
        say - would otherwise invert a section of the ramp, and refusing the
        whole table for it would be a harsh answer to a transposed digit.
        """
        out = {}
        for name, _rgb in MANUAL_COLORS:
            try:
                value = float(self.config.get(f"fee_manual_{name}"))
            except (TypeError, ValueError):
                value = MANUAL_DEFAULTS[name]
            out[name] = max(0.0, value)
        return out

    def _manual_stops(self):
        """The manual thresholds as an interpolation table."""
        levels = self.manual_thresholds()
        stops = [(levels[name], rgb) for name, rgb in MANUAL_COLORS]
        return sorted(stops, key=lambda s: s[0])

    def block_height_preview_samples(self):
        """Both gradient ends for a few representative block-to-block moves.

        The config page draws its block-height preview from this rather than
        reimplementing the scale in JavaScript, so the swatches cannot drift from
        what the renderer actually produces. All three modes are returned at once
        so switching the dropdown updates instantly instead of costing a request.

        Scenarios rather than single fees, because the gradient now reads as a
        move: the previous block at the top, the current one at the bottom. A
        steady cheap network is blue over blue, a spike is blue over red.

        A null end means that fee reads as normal, so the page substitutes the
        colour currently in the picker - which the browser knows and the server
        does not. Tone for that substitution is the caller's job and follows the
        same rule as here: on dark the top is raw and the bottom lightened, on
        light the top is lightened and the bottom raw.

        Each mode brings its own scenarios, because a useful example depends on
        the scale: the relative one wants multiples of the median, the manual
        one wants figures either side of the thresholds the user just typed,
        and the constant one wants a single swatch, the fee having no say.

        Shape: {"lighten": 0.45,
                "modes": {mode: {
                    "scenarios": [{"key":..., "prev":..., "curr":...}, ...],
                    "light"|"dark": {key: {"top": hex|None,
                                           "bottom": hex|None}}}}}

        `lighten` travels with it because the page needs the same figure to
        derive a substituted end, and a second copy of the constant in
        JavaScript is a second thing to keep in step.
        """
        try:
            neutral_band = float(self.config.get("fee_neutral_band_pct", 5)) / 100.0
        except (TypeError, ValueError):
            neutral_band = 0.05
        neutral_band = max(0.0, min(0.5, neutral_band))

        baseline = None
        store = getattr(self, "fee_baseline", None)
        if store is not None:
            try:
                baseline = store.baseline(
                    self.config.get("fee_parameter", "minimumFee"))
            except Exception:
                baseline = None

        # The floor the renderer will actually apply, so the picker shows what
        # gets drawn rather than an unfloored idealisation of it.
        cheap_floor = FALLBACK_CHEAP_FLOOR
        try:
            cheap_floor = self._get_fee_for_parameter(
                self._block_fee_cache["current"]["height"],
                "minimumFee") or FALLBACK_CHEAP_FLOOR
        except Exception:
            pass

        modes = {}
        for mode in MODES:
            scenarios = self._preview_scenarios(mode, baseline)
            entry = {"scenarios": scenarios}
            for theme, is_dark in (("light", False), ("dark", True)):
                per_key = {}
                for sc in scenarios:
                    ends = {}
                    for end, fee in (("top", sc["prev"]), ("bottom", sc["curr"])):
                        rgb = self._fee_color_for(fee, baseline, mode,
                                                  neutral_band, cheap_floor)
                        if rgb is None:
                            ends[end] = None          # the configured colour
                            continue
                        if is_dark:
                            toned = rgb if end == "top" else _lighten(rgb)
                        else:
                            toned = _lighten(rgb) if end == "top" else _deepen(rgb)
                        ends[end] = "#%02X%02X%02X" % tuple(toned)
                    per_key[sc["key"]] = ends
                entry[theme] = per_key
            modes[mode] = entry
        return {"lighten": LIGHTEN_AMOUNT, "modes": modes}

    def _preview_scenarios(self, mode, baseline):
        """Four representative block-to-block moves, chosen to suit the scale.

        Pairs rather than single fees, and genuine moves rather than two equal
        ends: flat pairs make a swatch one colour, which is the one thing the
        gradient is not, and they leave the middle of the scale unvisited.
        """
        if mode == "constant":
            # The fee is never consulted, so a second swatch would only repeat
            # the first. One sample is the honest preview of this mode.
            return [{"key": "steady", "prev": None, "curr": None}]

        if mode == "manual":
            # Anchored on the thresholds the user just typed, so the examples
            # move with them: set orange 3 and red 5 and the dear case shows
            # 3 -> 4.8, which is exactly the band those two numbers describe.
            t = self.manual_thresholds()
            return [
                {"key": "cheap",  "prev": _preview_fee(t["blue"] * 0.6),
                                  "curr": _preview_fee(t["green"])},
                {"key": "steady", "prev": _preview_fee(t["yellow"]),
                                  "curr": _preview_fee(t["yellow"])},
                {"key": "spike",  "prev": _preview_fee(t["green"]),
                                  "curr": _preview_fee(t["orange"])},
                {"key": "dear",   "prev": _preview_fee(t["orange"]),
                                  "curr": _preview_fee(t["red"] * 0.96)},
            ]

        # Relative: multiples of the baseline, so the figures shown are always
        # plausible fees for the market the device is actually in. At a median
        # of 1 the cheap case reads 0.1 -> 0.7, at a median of 20, 2 -> 14.
        normal = float(baseline) if baseline and baseline > 0 else 20.0
        return [
            {"key": key, "prev": _preview_fee(normal * lo),
                         "curr": _preview_fee(normal * hi)}
            for key, lo, hi in (
                ("steady", 1.0, 1.0),   # inside the neutral band: base colour
                ("cheap",  0.1, 0.7),   # floor-cheap, easing back to normal
                ("spike",  1.1, 2.0),   # ordinary into clearly dear
                ("dear",   3.0, 1.8),   # dear, but coming back down
            )
        ]

    def fee_to_colors(self, current_fee, recent_fee=None, web_quality=False,
                      cheap_floor=None):
        """
        Returns (top_color, bottom_color) for the block-height text gradient.

        Both ends are fee readings, taken independently: the previous block's fee
        at the top, the current one at the bottom. That makes the direction of
        travel legible at a glance rather than only the level -

          both ends cool    it was cheap and it still is
          both ends warm    it spiked and has stayed there
          cool over warm    the fee has just jumped
          warm over cool    the fee has just crashed

        An end whose fee reads as normal - inside the neutral band, or with no
        baseline yet - carries the configured block-height colour instead, so
        "nothing to report" looks like a deliberate state rather than a hue that
        happens to mean nothing. Two normal blocks therefore render the digits as
        two tones of the configured colour, exactly as a flat gradient should.

        Tone follows the theme, because the end that has to recede differs:

          dark theme   top at full value,      bottom lightened
          light theme  top lightened,          bottom deepened

        so the bottom - where the fee label sits - is always the readable end.

        Colour meaning depends on `fee_color_mode`:
          constant - the configured colour, whatever the fee is doing
          relative - cool below the rolling median, warm above it
          manual   - five fixed colours at thresholds the user sets, in sat/vB

        `recent_fee` defaults to the current fee, which renders flat - correct for
        any caller that has no previous block to compare against.

        `cheap_floor` is the network's current minimum - minimumFee from the live
        recommendations - below which nothing is meaningfully cheaper. Omitted
        means no floor, which is what a cleared mempool deserves.

        e-ink gets the same treatment as the web image. It used to snap both ends
        to inks the panel could print outright, to keep the driver from dithering
        thin digits into speckle. That cost more than it saved: with five or six
        inks two fees an hour apart land on the same one, so the gradient printed
        flat and said nothing, and a cheap fee could take the panel's blue, which
        is 2.4:1 against a black background - the fee sitting under the number was
        barely readable. Letting the driver dither an intermediate tone gives back
        the gradient and the lighter end, at the cost of some texture in the
        glyphs, which at this size reads as shading rather than noise.
        """
        if web_quality:
            is_dark = self.config.get("color_mode_dark", True)
        else:
            is_dark = self.config.get("eink_dark_mode", False)

        mode = normalise_mode(self.config.get("fee_color_mode"))

        try:
            neutral_band = float(self.config.get("fee_neutral_band_pct", 5)) / 100.0
        except (TypeError, ValueError):
            neutral_band = 0.05
        neutral_band = max(0.0, min(0.5, neutral_band))

        baseline = None
        store = getattr(self, "fee_baseline", None)
        if store is not None and mode == "relative":
            # Against the same tier's own history, so the ratio carries no
            # constant offset from whichever priority level is configured.
            try:
                baseline = store.baseline(
                    self.config.get("fee_parameter", "minimumFee"))
            except Exception:
                baseline = None

        # The network's own minimum, passed in by the caller that has the live
        # fee recommendations. Unusable or absent means no floor rather than a
        # guessed one - see FALLBACK_CHEAP_FLOOR.
        try:
            cheap_floor = max(0.0, float(cheap_floor))
        except (TypeError, ValueError):
            cheap_floor = FALLBACK_CHEAP_FLOOR

        base = self._base_color(is_dark)
        if recent_fee is None:
            recent_fee = current_fee

        # None from _fee_color_for means the fee reads as normal, so the
        # configured colour speaks for that end. Tracked per end, because a
        # neutral end renders the configured colour at its own tone rather than
        # the fee treatment - otherwise the picker never shows what is drawn.
        top_color = self._fee_color_for(recent_fee, baseline, mode, neutral_band,
                                        cheap_floor)
        bottom_color = self._fee_color_for(current_fee, baseline, mode, neutral_band,
                                           cheap_floor)
        top_is_base = top_color is None
        bottom_is_base = bottom_color is None
        if top_is_base:
            top_color = base
        if bottom_is_base:
            bottom_color = base

        if is_dark:
            # Dark background: the top carries the previous fee at full value and
            # the bottom the current one lightened, so the readable end is the
            # one the fee label sits against.
            return top_color, _lighten(bottom_color)
        # Light background: the bottom is the dark, readable end and the top is
        # lightened - including when it is the configured colour, or two normal
        # blocks would collapse the gradient to a single flat fill. The bottom is
        # the anchor end here, so a neutral one renders the configured colour
        # exactly rather than a deepened approximation of it.
        return (_lighten(top_color),
                bottom_color if bottom_is_base else _deepen(bottom_color))



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
