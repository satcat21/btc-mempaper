"""How numbers read: which mark groups thousands, which marks the decimal.

Every figure the device draws goes through here, so a block height, a hashrate
and a fee all punctuate the same way. Before this existed each site decided for
itself: block heights were hardcoded to 62.923 while the hashrate followed the
display language, so an English device drew 62.923 next to 0.51 TH/s - one
number European, the next American, on the same screen.

The choice is a config setting rather than a consequence of the language,
because the two are genuinely independent: plenty of people read an English
interface and still expect 62.923 and 0,51.
"""

# 62.923  ·  0,51        the default, and what most of Europe reads
EU = "eu"
# 62,923  ·  0.51
US = "us"

STYLES = (EU, US)

_PLACEHOLDER = "\x00"


def normalize_style(style):
    """Anything unrecognised reads as the default rather than raising."""
    return style if style in STYLES else EU


def decimal_mark(style=EU):
    """The character this style puts before the decimals."""
    return "." if normalize_style(style) == US else ","


def group_mark(style=EU):
    """The character this style puts between thousands."""
    return "," if normalize_style(style) == US else "."


def format_number(value, decimals=0, style=EU):
    """One number, grouped and pointed the way the setting asks.

    Python's own format produces the US arrangement, so EU is reached by
    swapping the two marks through a placeholder - going straight from "," to
    "." and then "." to "," would turn every separator into the same character.
    """
    try:
        text = f"{float(value):,.{int(decimals)}f}"
    except (TypeError, ValueError):
        return str(value)
    if normalize_style(style) == US:
        return text
    return text.replace(",", _PLACEHOLDER).replace(".", ",").replace(_PLACEHOLDER, ".")


def format_decimal_string(text, style=EU):
    """Repoint an already-formatted plain decimal such as f"{x:.8f}".

    For figures whose precision is decided elsewhere - a BTC balance at eight
    places - where only the mark is in question and there is no grouping.
    """
    return text if normalize_style(style) == US else str(text).replace(".", ",")
