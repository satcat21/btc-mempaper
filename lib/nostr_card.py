"""A Nostr post drawn as a Primal-style card: avatar, name and age on top,
the text below, the image under that.

The card is what the panel shows in place of a meme, so it is drawn large and
plain - it is scaled down into the meme area, and on the 7-colour panel thin
lines and pale greys dissolve into dither.
"""

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageOps
import os
import re
import time

WIDTH = 1000
_PAD = 44
_AVATAR = 104
_GAP = 26
_RADIUS = 28
_MAX_TEXT_LINES = 4
# Taller images are scaled down to this height, never cropped: a meme's
# caption is usually at its top or bottom edge, and cutting the image to a
# square cut it off. Without a limit a portrait photo would make the card a
# strip too narrow to read once it is fitted into the meme area.
_MAX_IMAGE_ASPECT = 1.0  # height / width

THEMES = {
    'light': {'bg': (255, 255, 255), 'text': (17, 17, 17), 'meta': (110, 110, 110),
              'placeholder': (225, 225, 225)},
    'dark': {'bg': (0, 0, 0), 'text': (245, 245, 245), 'meta': (150, 150, 150),
             'placeholder': (45, 45, 45)},
}

_FONT_BOLD = os.path.join('static', 'fonts', 'Roboto-Bold.ttf')
_FONT_REGULAR = os.path.join('static', 'fonts', 'Roboto-Regular.ttf')
_fonts = {}

_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
_MENTION_RE = re.compile(r'nostr:(npub|nprofile|note|nevent|naddr)1[02-9ac-hj-np-z]+', re.IGNORECASE)


def _font(path, size):
    key = (path, size)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype(path, size)
        except OSError:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def relative_age(created_at, now=None):
    """'now', '12m', '3h', '2d' - the way Primal labels a post."""
    seconds = max(0, int((now or time.time()) - created_at))
    if seconds < 60:
        return 'now'
    if seconds < 3600:
        return f'{seconds // 60}m'
    if seconds < 86400:
        return f'{seconds // 3600}h'
    return f'{seconds // 86400}d'


def post_text(content, image_urls):
    """The text a reader sees: the content without the image links it carries,
    references to other notes, or the blank lines left behind."""
    text = content or ''
    for url in image_urls:
        text = text.replace(url, '')
    text = _MENTION_RE.sub(lambda m: '' if m.group(1).lower() in ('note', 'nevent', 'naddr') else '@…', text)
    # Any other link is kept, shortened to its host, as Primal does.
    text = _URL_RE.sub(lambda m: re.sub(r'^https?://(www\.)?', '', m.group(0)).split('/')[0], text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class _TextDraw:
    """Measuring and drawing with the emoji support the dashboard already has."""

    def __init__(self, draw, image):
        from lib.render.text import TextMixin
        self.draw = draw
        self.image = image
        self.has_emoji = TextMixin._has_emoji
        self._estimate = TextMixin._emoji_aware_getlength

    def measure(self, text, font):
        """Width as drawn. pilmoji draws an emoji somewhat wider than the
        shared estimate, which was enough to push a wrapped line past the
        margin, so each one gets a little extra here."""
        width = self._estimate(text, font)
        if self.has_emoji(text):
            emoji = sum(1 for c in text if ord(c) >= 0x1F000 or 0x2600 <= ord(c) <= 0x27BF)
            width += emoji * font.size * 0.3
        return width

    def text(self, xy, text, font, fill):
        if self.has_emoji(text):
            import lib.image_renderer as ir
            if ir._ensure_pilmoji_loaded():
                try:
                    with ir._Pilmoji(self.image, source=ir._CachedEmojiSource) as pm:
                        pm.text(xy, text, fill=fill, font=font)
                    return
                except Exception:
                    pass
        self.draw.text(xy, text, font=font, fill=fill)

    def fit(self, text, font, width):
        """text, cut with an ellipsis to fit width."""
        if self.measure(text, font) <= width:
            return text
        while text and self.measure(text + '…', font) > width:
            text = text[:-1]
        return text.rstrip() + '…'

    def wrap(self, text, font, width, max_lines):
        """Lines of at most width, at most max_lines, the last one ellipsised
        when text remains."""
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split(' ')
            line = ''
            for word in words:
                candidate = f'{line} {word}' if line else word
                if self.measure(candidate, font) <= width:
                    line = candidate
                    continue
                if line:
                    lines.append(line)
                # A single word wider than the line - a long link, mostly.
                line = self.fit(word, font, width) if self.measure(word, font) > width else word
            lines.append(line)
            if len(lines) > max_lines:
                break
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.fit(lines[-1] + ' …', font, width)
        return lines


def _circle(img, size):
    img = ImageOps.fit(img.convert('RGB'), (size, size), Image.LANCZOS)
    mask = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    return img, mask.resize((size, size), Image.LANCZOS)


def _rounded(img, radius):
    mask = Image.new('L', (img.width * 2, img.height * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width * 2 - 1, img.height * 2 - 1),
                                           radius=radius * 2, fill=255)
    return mask.resize(img.size, Image.LANCZOS)


def render_card(image, name, text, created_at, avatar_path=None, theme='light', now=None):
    """The post as one RGB image, WIDTH wide and as tall as it needs.

    image: PIL image of the post's picture. text: already cleaned with
    post_text(). Name and age share the line next to the avatar.
    """
    colors = THEMES.get(theme, THEMES['light'])
    inner = WIDTH - 2 * _PAD
    name_font = _font(_FONT_BOLD, 42)
    meta_font = _font(_FONT_REGULAR, 38)
    body_font = _font(_FONT_REGULAR, 40)
    line_height = int(body_font.size * 1.3)

    probe = _TextDraw(ImageDraw.Draw(Image.new('RGB', (1, 1))), None)
    lines = probe.wrap(text, body_font, inner, _MAX_TEXT_LINES) if text else []

    # Image: full width, or - when taller than _MAX_IMAGE_ASPECT allows -
    # scaled down to that height and centred, the whole picture kept.
    if image.mode in ('RGBA', 'LA', 'P'):
        flat = Image.new('RGB', image.size, colors['bg'])
        rgba = image.convert('RGBA')
        flat.paste(rgba, mask=rgba.split()[-1])
        image = flat
    else:
        image = image.convert('RGB')
    img_h = round(inner * image.height / image.width)
    img_w = inner
    if img_h > inner * _MAX_IMAGE_ASPECT:
        img_h = round(inner * _MAX_IMAGE_ASPECT)
        img_w = max(1, round(img_h * image.width / image.height))
    picture = image.resize((img_w, img_h), Image.LANCZOS)

    text_h = len(lines) * line_height
    height = (_PAD + _AVATAR + _GAP + (text_h + _GAP if lines else 0) + img_h + _PAD)
    card = Image.new('RGB', (WIDTH, height), colors['bg'])
    draw = ImageDraw.Draw(card)
    td = _TextDraw(draw, card)

    # Avatar, or the first letter of the name on a grey disc.
    avatar = None
    if avatar_path and os.path.exists(avatar_path):
        try:
            avatar = Image.open(avatar_path)
        except OSError:
            avatar = None
    if avatar is not None:
        disc, mask = _circle(avatar, _AVATAR)
        card.paste(disc, (_PAD, _PAD), mask)
    else:
        draw.ellipse((_PAD, _PAD, _PAD + _AVATAR, _PAD + _AVATAR), fill=colors['placeholder'])
        initial = (name or '?').strip()[:1].upper() or '?'
        f = _font(_FONT_BOLD, 52)
        w = draw.textlength(initial, font=f)
        draw.text((_PAD + (_AVATAR - w) / 2, _PAD + _AVATAR / 2 - 30), initial, font=f, fill=colors['meta'])

    # Name · age, vertically centred on the avatar.
    x = _PAD + _AVATAR + 24
    age = ' · ' + relative_age(created_at, now)
    age_w = td.measure(age, meta_font)
    name = td.fit(name or 'nostr', name_font, WIDTH - _PAD - x - age_w)
    y = _PAD + (_AVATAR - name_font.size) // 2 - 4
    td.text((x, y), name, name_font, colors['text'])
    draw.text((x + td.measure(name, name_font), y + 4), age, font=meta_font, fill=colors['meta'])

    y = _PAD + _AVATAR + _GAP
    for line in lines:
        td.text((_PAD, y), line, body_font, colors['text'])
        y += line_height
    if lines:
        y += _GAP

    card.paste(picture, (_PAD + (inner - img_w) // 2, y), _rounded(picture, _RADIUS))
    return card
