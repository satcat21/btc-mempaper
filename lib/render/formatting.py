"""Presentation helpers with no layout dependency: fee-to-color mapping, localised date strings and the font size that makes a date fit.
"""

import math

from babel.dates import format_date
from datetime import datetime


# ── The three scales ──────────────────────────────────────────────────────
# constant  the configured color, always. The fee is not consulted.
# relative  cheap or dear against what this same fee tier has cost lately.
# manual    fixed sat/vB thresholds the user sets by hand.
MODES = ("constant", "relative", "manual")

def normalise_mode(raw):
    """The stored scale name, or the default if it is not one we know."""
    raw = str(raw or "").strip()
    return raw if raw in MODES else "relative"


# ── Manual scale (mode C) ─────────────────────────────────────────────────
# Five fixed colors whose thresholds the user sets, in real sat/vB. No
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
# handled separately so "ordinary" gets the user's own color.
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
    ( 1.55,(225,  35,  35)),   # red        - ~2.9x
    ( 2.00,(200,  25,  60)),   # deep red   - 4x and beyond
]
# fmt: on

# The base color of the block height: what the digits read as when the fee has
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

# And toward black, for the end that has to stay readable on a light panel. Much
# less travel than the lightening: the fee hues are already dark enough to read
# against white, and a heavier hand turns the cool end of the scale to mud.
DEEPEN_AMOUNT = 0.85

# No baseline yet, or no fee at all.
UNKNOWN_COLOR = (120, 120, 130)

# A fee at or under the floor reads as the cheapest color whatever the ratio
# says, because there is nothing cheaper to wait for.
#
# The floor is not a constant. It is whatever the mempool is currently
# accepting, so the caller passes minimumFee from the live fee recommendations.
# Hardcoding 1 sat/vB was wrong in both directions: blocks clear at fractions of
# a sat/vB, so everything from 0.1 to 1.0 collapsed onto one color - a full
# order of magnitude, and precisely the range a quiet market lives in.
#
# Only while the baseline is above it, either way. At a median of 0.5 a fee of
# 1.0 is twice the going rate and must not render as the best moment in a month.
#
# 0.0 when the network does not say: no floor at all rather than a wrong one.
# That is also the honest reading once the mempool has cleared entirely, where
# minimumFee itself goes to zero and nothing is waiting to be undercut.
FALLBACK_CHEAP_FLOOR = 0.0

# How close to the baseline still reads as an ordinary fee, and so renders in
# the configured base color rather than a cool or warm one.
#
# Not a setting. Its effect only becomes visible once a month of history has
# accumulated, and nothing about the rendered image tells you whether the number
# wants raising or lowering - so it was a box that could be typed into but not
# judged. It was also actively harmful as a setting: the form posted 0 for any
# number field missing from config.json, 0 is inside the range this accepted,
# and the band silently switched off, leaving every fee reading cheap or dear
# and none ordinary.
NEUTRAL_BAND = 0.05


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
    """Move a color toward white, keeping its hue."""
    return tuple(int(v + amount * (255 - v)) for v in rgb)


def _deepen(rgb, factor=DEEPEN_AMOUNT):
    """Move a color toward black, keeping its hue."""
    return tuple(max(0, min(255, int(v * factor))) for v in rgb)


def _hex(rgb):
    """An (r, g, b) triple as the "#rrggbb" the config page draws with."""
    return "#%02X%02X%02X" % tuple(int(max(0, min(255, v))) for v in rgb)


# The fee slider's far right, as a multiple of the value it centres on. Four
# times the median is log2 = 2.0, exactly the last stop of the warm ramp: the
# whole scale is reachable and the track ends where it runs out of colors.
#
# It used to run to 10x, on the reasoning that a stretch which no longer changes
# is itself a reading - past 4x normal, dearer stops being a distinction worth
# drawing. In practice that spent the last third of the travel on one flat
# color, and against a low median the numbers up there stopped being fees anyone
# recognised: at a median of 2 the track ran to 20 sat/vB.
SLIDER_HEADROOM = 4.0

# Where the constant scale centres its slider. It has no baseline to sit on and
# no thresholds to frame, so 0-1000 sat/vB is the honest span - but linear it
# would bury every fee anyone has ever paid in the first percent of the track,
# so the midpoint anchors somewhere fees actually live and the two halves are
# scaled independently either side of it.
SLIDER_FIXED_ANCHOR = 10.0
SLIDER_FIXED_MAX = 1000.0

# How far past the top manual threshold that scale's slider runs. The manual
# table says nothing above its last threshold - everything from `red` upward is
# the same color - so a track that continued to 1000 would be nine hundred and
# ninety-five sat/vB of nothing happening. A tenth past it is enough to show that
# the top band has been entered and does not end, without spending the travel on
# a stretch that cannot change.
MANUAL_HEADROOM = 1.1


class FormattingMixin:
    """Presentation helpers with no layout dependency: fee-to-color mapping, localised date strings and the font size that makes a date fit."""

    def _format_fee(self, fee):
        """A fee as the label shows it, with decimals only where they say something.

        Below 10 sat/vB the tenth is the reading: 0,8 and 1,4 are a different
        market, and both used to print as "1". Above 10 a tenth is noise, and a
        whole number stays whole rather than gaining a hollow "2,0". The
        separator follows the display language, as every other number does.
        """
        try:
            v = float(fee)
        except (TypeError, ValueError):
            return str(fee)
        if v >= 10 or v.is_integer():
            return self._format_number(int(round(v)), 0)
        if v >= 0.1:
            return self._format_number(v, 1)
        # A relay minimum below a tenth: show it rather than round it away, but
        # drop the zeros three decimals leave behind on 0,05 and friends.
        return self._format_number(v, 3).rstrip("0")

    def _fee_color_for(self, fee, baseline, mode, neutral_band,
                       cheap_floor=FALLBACK_CHEAP_FLOOR):
        """One fee to one RGB triple, before any theme or panel treatment.

        Returns None when the fee carries no signal - inside the neutral band,
        where the whole point is that nothing stands out. The caller substitutes
        the configured base color, which is what "nothing to see here" looks
        like for the theme in use.

        `cheap_floor` is the network's current minimum, below which one fee is
        not meaningfully cheaper than another. Zero disables the floor entirely.
        """
        # Constant: the fee has no say. None *is* the answer here - it means
        # "the configured color", which is the whole of this mode.
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

        # A flat neutral plateau, then color outwards.
        # The band is a plateau rather than a single point so "normal" reads as
        # a deliberate state instead of a color the gradient happens to cross.
        if abs(ratio - 1.0) <= neutral_band:
            return None
        if position < 0:
            return _interpolate(RELATIVE_NEUTRAL_COOL, position)
        return _interpolate(RELATIVE_NEUTRAL_WARM, position)

    def _base_color(self, is_dark):
        """The configured block-height color for the theme in use.

        Format is "#rrggbb", the same as every other color setting. Anything
        unparseable falls back to the built-in default rather than raising:
        a bad color must not take the whole render down with it.
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
        """The sat/vB level each of the five colors starts at.

        One number per color, read individually: a typo in one field falls
        back to that color's default rather than discarding the other four,
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

    def block_height_preview_scale(self):
        """The scale itself, so the config page can color any fee the user picks.

        The preview used to be four fixed scenarios colored here and shipped as
        finished swatches - the page held no scale tables, so it could not
        disagree with the renderer. A fee slider ends that arrangement: the
        reader chooses the fee now, continuously, and no enumeration of samples
        answers for a value the server was never asked about.

        So what travels is the scale rather than its output - the same stop
        tables, neutral band, baseline and floor `_fee_color_for` maps with. The
        page walks the identical curve instead of approximating it, and these
        tables stay the only definition: retuning a stop is still an edit to this
        file alone.

        Manual thresholds are deliberately *not* included. They are being typed
        into the form while the slider moves, so the page pairs its own live
        values with the color order below; sending the saved ones would color
        the slider against numbers the reader had already replaced.

        The slider ranges travel too, for the same reason the stops do - where
        "normal" sits on the track is a property of the scale, not a layout
        choice. Each is (min, anchor, max) with the anchor at the midpoint of the
        travel, and each scale is framed by whatever it is measured against:

          relative  0 to ten times the median, median under the middle
          manual    0 to a tenth past the top threshold, so the track is exactly
                    the table the user typed and no wider
          constant  0-1000 sat/vB around a workable centre, the fee having no
                    say - the span is arbitrary because nothing constrains it

        Shape: {"lighten", "deepen", "neutral_band", "baseline", "cheap_floor",
                "current_fee", "block_height", "unknown", "baseline_stats",
                "relative": {"cool": [[pos, hex], ...], "warm": [...]},
                "manual_order": [[name, hex, default_threshold], ...],
                "slider": {mode: {"min", "anchor", "max"}}}
        """
        baseline = None
        stats = None
        store = getattr(self, "fee_baseline", None)
        if store is not None:
            try:
                tier = self.config.get("fee_parameter", "minimumFee")
                baseline = store.baseline(tier)
                stats = store.stats(tier)
            except Exception:
                baseline, stats = None, None

        # The floor and the fee the renderer is working with right now, so the
        # slider opens on the state the panel is actually in rather than on an
        # idealisation of it.
        cheap_floor = FALLBACK_CHEAP_FLOOR
        current_fee = None
        block_height = None
        try:
            height = self._block_fee_cache["current"]["height"]
            cheap_floor = self._get_fee_for_parameter(
                height, "minimumFee") or FALLBACK_CHEAP_FLOOR
            current_fee = self._get_fee_for_parameter(
                height, self.config.get("fee_parameter", "minimumFee"))
            # The tip the panel is currently showing. The preview drew a
            # hardcoded 914427 before, which is a plausible-looking number and
            # nothing more: the reader cannot tell a preview of their own device
            # from a mock-up, and the digit count is the whole geometry of the
            # thing being previewed.
            block_height = int(height)
        except Exception:
            pass

        fixed_slider = {"min": 0.0, "anchor": SLIDER_FIXED_ANCHOR,
                        "max": SLIDER_FIXED_MAX}

        # The manual scale is framed by the numbers it is made of: a tenth past
        # the top threshold, with the midpoint halfway - which makes that track
        # plain linear, and it can afford to be, spanning a handful of sat/vB
        # rather than a thousand. `red` is normally the top, but the thresholds
        # are only sorted when they are used, so take whichever is highest and a
        # transposed pair still frames the whole table.
        levels = self.manual_thresholds()
        top = max([levels.get("red", 0.0)] + list(levels.values()))
        if top > 0:
            span = round(top * MANUAL_HEADROOM, 3)
            manual_slider = {"min": 0.0, "anchor": round(span / 2, 3), "max": span}
        else:
            manual_slider = dict(fixed_slider)

        if baseline and baseline > 0:
            relative_slider = {"min": 0.0,
                               "anchor": round(float(baseline), 3),
                               "max": round(float(baseline) * SLIDER_HEADROOM, 3)}
        else:
            # No window yet, so `relative` is coloring from the manual table -
            # give it that table's range rather than a span around a median that
            # does not exist.
            relative_slider = dict(manual_slider)

        return {
            "lighten": LIGHTEN_AMOUNT,
            "deepen": DEEPEN_AMOUNT,
            "neutral_band": NEUTRAL_BAND,
            "baseline": baseline,
            "cheap_floor": cheap_floor,
            "current_fee": current_fee,
            "block_height": block_height,
            "unknown": _hex(UNKNOWN_COLOR),
            "baseline_stats": stats,
            "relative": {
                "cool": [[pos, _hex(rgb)] for pos, rgb in RELATIVE_NEUTRAL_COOL],
                "warm": [[pos, _hex(rgb)] for pos, rgb in RELATIVE_NEUTRAL_WARM],
            },
            "manual_order": [[name, _hex(rgb), MANUAL_DEFAULTS[name]]
                             for name, rgb in MANUAL_COLORS],
            # Travels so the page can re-frame the manual track from the numbers
            # being typed, rather than waiting for a save to find out where it
            # now ends.
            "manual_headroom": MANUAL_HEADROOM,
            "slider": {"constant": fixed_slider,
                       "relative": relative_slider,
                       "manual": manual_slider},
        }

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
        baseline yet - carries the configured block-height color instead, so
        "nothing to report" looks like a deliberate state rather than a hue that
        happens to mean nothing. Two normal blocks therefore render the digits as
        two tones of the configured color, exactly as a flat gradient should.

        Tone follows the theme, because the end that has to recede differs:

          dark theme   top at full value,      bottom lightened
          light theme  top lightened,          bottom deepened

        so the bottom - where the fee label sits - is always the readable end.

        color meaning depends on `fee_color_mode`:
          constant - the configured color, whatever the fee is doing
          relative - cool below the rolling median, warm above it
          manual   - five fixed colors at thresholds the user sets, in sat/vB

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

        neutral_band = NEUTRAL_BAND
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
        # configured color speaks for that end. Tracked per end, because a
        # neutral end renders the configured color at its own tone rather than
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
        # lightened - including when it is the configured color, or two normal
        # blocks would collapse the gradient to a single flat fill. The bottom is
        # the anchor end here, so a neutral one renders the configured color
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
