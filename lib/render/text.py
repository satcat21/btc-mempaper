"""Text measurement and drawing: wrapping, truncation, squeezing to width
and the vertical-gradient draw used for headings.
"""

from PIL import Image
from PIL import ImageDraw


class TextMixin:
    """Text measurement and drawing: wrapping, truncation, squeezing to width"""

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
        if not TextMixin._has_emoji(text):
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

    @staticmethod
    def _wrap_text_to_lines(text: str, font, max_width: float, max_lines: int):
        """Word-wrap *text* into at most *max_lines* pixel-width-limited lines.

        Returns a list of lines where ALL words fit cleanly, or None if the text
        cannot be arranged without truncation (signalling the caller to reduce
        font size and retry).
        """
        _getlength = TextMixin._emoji_aware_getlength
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
        _getlength = TextMixin._emoji_aware_getlength
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
    def _squeezed_text_width(text: str, font, dot_fraction: float = 1.0,
                             squeeze_char: str = '.') -> int:
        """Measure rendered pixel width of *text* with optional dot-advance compression.

        When dot_fraction < 1.0 each separator is rendered with a symmetric fixed
        gap on each side scaled from the font's natural side bearing.  This
        matches the rendering done by draw_vertical_gradient_text exactly.

        squeeze_char is the thousands separator actually in use, which follows
        the number_format setting - compressing a literal '.' would quietly stop
        working the moment the setting made it a comma, and the block height
        would grow wide enough to burst the hash frame it is measured against.
        """
        if dot_fraction >= 1.0:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0]
        cx = 0.0
        for ch in text:
            if ch == squeeze_char:
                bb = font.getbbox(ch)
                glyph_w = bb[2] - bb[0]
                natural_gap = max(0.5, (font.getlength(ch) - glyph_w) / 2)
                gap = max(1.0, natural_gap * dot_fraction)
                cx += glyph_w + 2 * gap
            else:
                cx += font.getlength(ch)
        return int(cx)

    @staticmethod
    def _squeezed_char_spans(text: str, font, dot_fraction: float = 1.0,
                             squeeze_char: str = '.'):
        """Where each separator glyph actually lands, as (left, right) offsets.

        Mirrors the advance arithmetic of _squeezed_text_width, because the
        squeeze moves every glyph after the first separator - measuring the
        separator's position with unsqueezed advances would put it several
        pixels off, which is enough to matter when laying text out around it.
        """
        spans = []
        cx = 0.0
        for ch in text:
            adv = font.getlength(ch)
            if ch == squeeze_char:
                bb = font.getbbox(ch)
                glyph_w = bb[2] - bb[0]
                if dot_fraction < 1.0:
                    natural_gap = max(0.5, (adv - glyph_w) / 2)
                    gap = max(1.0, natural_gap * dot_fraction)
                    spans.append((cx + gap, cx + gap + glyph_w))
                    cx += glyph_w + 2 * gap
                    continue
                side = max(0.0, (adv - glyph_w) / 2)
                spans.append((cx + side, cx + side + glyph_w))
            cx += adv
        return spans

    def draw_vertical_gradient_text(self, img, draw, text, x, y, font, start_color, end_color,
                                    dot_fraction: float = 1.0,
                                    squeeze_char: str = '.'):
        """Draw *text* at (x, y) with a top-to-bottom color gradient.

        dot_fraction — when < 1.0 each separator is rendered with that fraction
        of its natural advance width, tightening the gap around thousand
        separators. Pass the same value and squeeze_char to
        _squeezed_text_width() when calculating the x position so centering
        stays accurate.
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
            text_width = self._squeezed_text_width(text, font, dot_fraction)
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

        # Vertical gradient mask, spanning the glyphs rather than the layout box.
        #
        # text_height is ascent + descent + 8, but digits ink only from the cap
        # top down to the baseline - about 58% of it. Interpolating across the
        # box therefore started the visible text 17% into the ramp and stopped it
        # at 74%, so neither end color was ever actually drawn: a violet-to-
        # light-orange gradient arrived as violet over muddy salmon, and the
        # configured base color was never the color anyone saw. Mapping the
        # ramp onto the ink box makes both ends exact and puts the 50/50 blend
        # at the middle of the digits, where it looks like it should be.
        ink = text_img.getbbox()
        ink_top, ink_bottom = (ink[1], ink[3] - 1) if ink else (0, size[1] - 1)
        ink_span = max(ink_bottom - ink_top, 1)

        gradient = Image.new("RGBA", size)
        for yy in range(size[1]):
            t = min(1.0, max(0.0, (yy - ink_top) / ink_span))
            color = tuple(int(start_color[i] + ((end_color[i] - start_color[i]) * t)) for i in range(3)) + (255,)
            ImageDraw.Draw(gradient).line([(0, yy), (size[0], yy)], fill=color)

        gradient.putalpha(text_img)
        img.paste(gradient, (int(x), int(y)), gradient)
