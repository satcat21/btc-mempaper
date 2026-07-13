"""
Onboarding screen renderer for the e-ink display.

Three screen variants:
  - hotspot        : 2 QR codes — ① join Wi-Fi, ② open the setup portal (standalone)
  - hotspot overlay: same 2 QR codes stamped onto the delivery-state image,
                     replacing the hash frame / block height area
  - connected      : 1 QR code  — dashboard URL, visible for 3 minutes
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import qrcode as _qrcode
    _QR_OK = True
except ImportError:
    _QR_OK = False

_FONT_DIR  = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
)
_IMAGE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'static', 'images')
)
_CACHE_DIR = 'cache'


# ── Font helpers ──────────────────────────────────────────────────────────────

def _font(name, size):
    path = os.path.join(_FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()


# ── Canvas helpers ─────────────────────────────────────────────────────────────

def _display_wh(config):
    """Return (width, height) for the e-ink canvas, applying orientation."""
    w = int(config.get('display_width',  800))
    h = int(config.get('display_height', 480))
    if config.get('eink_orientation', 'horizontal') == 'vertical':
        return h, w
    return w, h


def _qr_image(data, size, dark, error_correction=None):
    """Return a PIL RGB Image of a QR code scaled to `size`×`size`."""
    fill = (255, 255, 255) if dark else (20,  20,  20)
    back = (0,   0,   0)   if dark else (255, 255, 255)
    if not _QR_OK:
        img = Image.new('RGB', (size, size), back)
        return img
    if error_correction is None:
        error_correction = _qrcode.constants.ERROR_CORRECT_M
    qr = _qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    pil = qr.make_image(fill_color=fill, back_color=back).convert('RGB')
    return pil.resize((size, size), Image.NEAREST)


def _card(draw, x0, y0, x1, y1, radius, fill):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _centered(draw, cx, y, text, font, fill):
    """Draw `text` horizontally centred at `cx`, return rendered line height."""
    bb = font.getbbox(text)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    draw.text((cx - tw // 2, y), text, font=font, fill=fill)
    return th


def _wrap_text(text, font, max_width):
    """Word-wrap `text` into lines that fit within `max_width` pixels."""
    words = text.split()
    if not words:
        return [text]
    lines = []
    current = words[0]
    for word in words[1:]:
        test = current + ' ' + word
        bb = font.getbbox(test)
        if (bb[2] - bb[0]) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _brand_title(draw, cx, y, f_title, sz_title, fg, accent):
    """Draw the 'mem[accent]paper' brand word centred at `cx`."""
    mem_bb   = f_title.getbbox('mem')
    paper_bb = f_title.getbbox('paper')
    mem_w    = mem_bb[2]   - mem_bb[0]
    paper_w  = paper_bb[2] - paper_bb[0]
    tx = cx - (mem_w + paper_w) // 2
    draw.text((tx,          y), 'mem',   font=f_title, fill=fg)
    draw.text((tx + mem_w,  y), 'paper', font=f_title, fill=accent)
    return sz_title


# ── Public render functions ───────────────────────────────────────────────────

def render_hotspot_screen(ssid, password, portal_url, config):
    """
    Build and save the hotspot onboarding image with two QR codes stacked vertically.

    Top    QR: Wi-Fi join URI (WPA2 — phone scans to join, no typing needed)
    Bottom QR: setup portal URL (phone scans to open the browser)

    Returns (PIL Image, path) or (None, None) if PIL is unavailable.
    """
    if not _PIL_OK:
        return None, None

    dark   = bool(config.get('color_mode_dark', True))
    W, H   = _display_wh(config)
    cx     = W // 2

    BG     = (0,   0,   0)   if dark else (255, 255, 255)
    FG     = (255, 255, 255) if dark else (30,  30,  30)
    ORANGE = (247, 147, 26)
    CARD   = (0,   0,   0)   if dark else (240, 240, 248)
    MUTED  = (255, 255, 255) if dark else (100, 100, 100)

    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Scale all sizes with the shorter display edge so layout works on any resolution
    base = min(W, H)
    PAD  = max(10, base // 40)

    SZ_TITLE = max(40, base * 48 // 480)
    SZ_SUB   = max(17, base * 20 // 480)
    SZ_STEP  = max(16, base * 20 // 480)   # slightly larger for readability
    SZ_DATA  = max(15, base * 18 // 480)   # larger → QRs shrink to accommodate
    SZ_MONO  = max(13, base * 16 // 480)   # larger → easier to read on small screens

    f_title = _font('RobotoCondensed-Bold.ttf', SZ_TITLE)
    f_sub   = _font('Roboto-Regular.ttf',       SZ_SUB)
    f_step  = _font('Roboto-Bold.ttf',          SZ_STEP)
    f_data  = _font('Roboto-Regular.ttf',       SZ_DATA)
    f_mono  = _font('IBMPlexMono-Medium.ttf',   SZ_MONO)

    # ── Header ────────────────────────────────────────────────────────────
    y = PAD
    _brand_title(draw, cx, y, f_title, SZ_TITLE, FG, ORANGE)
    y += SZ_TITLE + 4
    _centered(draw, cx, y, 'WiFi Setup', f_sub, MUTED)
    y += SZ_SUB + PAD

    # ── Two vertically-stacked QR sections ────────────────────────────────
    # Hotspot is open (no WPA2).  QR1 connects; QR2 opens setup with portal
    # Password pre-filled so no manual entry is needed when scanning.  The password is
    # shown as text for users who cannot scan QR2.
    clean_url = portal_url.split('?')[0]   # e.g. http://10.42.0.1:5000/setup
    sections = [
        {
            'qr_data': f'WIFI:T:nopass;S:{ssid};;',
            'step':    '[1] Join WiFi',
            'lines':   [(ssid, f_data, FG)],
        },
        {
            'qr_data': portal_url,
            'step':    '[2] Open setup page',
            'lines':   [(clean_url, f_mono, FG), (f'Password: {password}', f_data, FG)],
        },
    ]

    available_h = H - y - PAD
    section_h   = available_h // 2

    for section in sections:
        # Measure label block height for this section
        label_h = SZ_STEP + 4
        for _, fnt, _ in section['lines']:
            bb = fnt.getbbox('Ag')
            label_h += (bb[3] - bb[1]) + 4

        qr_size = max(80, section_h - label_h - PAD * 2)
        # Lower error correction for small QRs → larger cells → easier to scan
        ec = (_qrcode.constants.ERROR_CORRECT_L if _QR_OK and qr_size < 200
              else _qrcode.constants.ERROR_CORRECT_M if _QR_OK else None)

        qr_x = cx - qr_size // 2
        qr_y = y + PAD // 2

        _card(draw, qr_x - 4, qr_y - 4, qr_x + qr_size + 4, qr_y + qr_size + 4, 8, CARD)
        img.paste(_qr_image(section['qr_data'], qr_size, dark, ec), (qr_x, qr_y))

        ly = qr_y + qr_size + PAD // 2
        _centered(draw, cx, ly, section['step'], f_step, FG)
        ly += SZ_STEP + 4
        for txt, fnt, color in section['lines']:
            _centered(draw, cx, ly, txt, fnt, color)
            bb = fnt.getbbox(txt)
            ly += (bb[3] - bb[1]) + 4

        y += section_h

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, 'onboarding_hotspot.png')
    img.save(path, compress_level=1)
    return img, path


def stamp_qr_codes_on_image(base_img, ssid, password, portal_url, config,
                            eink=False):
    """
    Replace the bottom block-height area of an already-rendered image with
    two side-by-side QR codes (WiFi + setup page).

    Args:
        eink: If True, use e-ink color settings (eink_dark_mode, default light).
              If False, use web color settings (color_mode_dark, default dark).

    The base image (e.g. delivery-state) is modified in-place and also saved
    to cache/onboarding_hotspot.png.

    Returns (PIL Image, path) or (None, None) on failure.
    """
    if not _PIL_OK or base_img is None:
        return None, None

    img  = base_img.copy()
    W, H = img.size
    draw = ImageDraw.Draw(img)

    if eink:
        dark = bool(config.get('eink_dark_mode', False))
    else:
        dark = bool(config.get('color_mode_dark', True))
    block_height_area = int(config.get('block_height_area', 180))

    BG     = (0, 0, 0) if dark else (255, 255, 255)
    FG     = (255, 255, 255) if dark else (30, 30, 30)
    MUTED  = (180, 180, 180) if dark else (100, 100, 100)
    ORANGE = (247, 147, 26)

    # Scale font sizes relative to display — slightly larger so text below QRs is readable
    base = min(W, H)
    SZ_LABEL = max(13, base * 16 // 480)
    SZ_MONO  = max(12, base * 14 // 480)

    f_label = _font('Roboto-Bold.ttf', SZ_LABEL)
    f_mono  = _font('IBMPlexMono-Medium.ttf', SZ_MONO)

    # Replicate the renderer's ui_scale logic so we blank exactly the
    # area that _render_block_info_with_data occupies.
    # ui_scale = min(W/base_w, H/base_h), clamped to [0.75, 3.0]
    if H > W:  # vertical / portrait
        base_w, base_h = 480, 800
    else:       # horizontal / landscape
        base_w, base_h = 800, 480
    ui_scale = max(0.75, min(3.0, min(W / base_w, H / base_h)))
    scaled_area = max(100, int(round(block_height_area * ui_scale)))
    qr_area_top = H - scaled_area
    draw.rectangle([0, qr_area_top, W, H], fill=BG)

    pad = max(8, base // 60)
    label_h     = f_label.getbbox('Ag')[3] - f_label.getbbox('Ag')[1]
    info_line_h = f_mono.getbbox('Ag')[3] - f_mono.getbbox('Ag')[1]
    text_overhead = pad + label_h + 4 + 4 + info_line_h * 2 + 8 + pad
    qr_size = min(scaled_area - text_overhead, (W - pad * 3) // 2)
    qr_size = max(60, qr_size)

    # Always black-on-white QR codes for reliable scanning on any background
    ec = _qrcode.constants.ERROR_CORRECT_L if _QR_OK and qr_size < 200 \
        else _qrcode.constants.ERROR_CORRECT_M if _QR_OK else None

    left_cx  = W // 4
    right_cx = 3 * W // 4

    label_y = qr_area_top + pad
    qr_y    = label_y + label_h + 4
    info_y  = qr_y + qr_size + 4

    clean_url = portal_url.split('?')[0]   # e.g. http://10.42.0.1:5000/setup

    # ── Left: WiFi QR (open network — no WPA2 password) ──
    _centered(draw, left_cx, label_y, '1. Connect to WiFi', f_label, FG)
    wifi_uri = f'WIFI:T:nopass;S:{ssid};;'
    img.paste(_qr_image(wifi_uri, qr_size, False, ec), (left_cx - qr_size // 2, qr_y))
    _centered(draw, left_cx, info_y, f'WiFi: {ssid}', f_mono, FG)

    # ── Right: Setup page QR (URL includes portal key for direct access) ──
    _centered(draw, right_cx, label_y, '2. Open setup page', f_label, FG)
    img.paste(_qr_image(portal_url, qr_size, False, ec), (right_cx - qr_size // 2, qr_y))
    _centered(draw, right_cx, info_y, clean_url, f_mono, FG)
    _centered(draw, right_cx, info_y + info_line_h + 2, f'Password: {password}', f_mono, FG)

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, 'onboarding_hotspot.png')
    img.save(path, compress_level=1)
    return img, path


def render_connected_screen(access_url, config, timeout_seconds=180, eink=True,
                            translations=None):
    """
    Build and save the post-connection dashboard-access image (1 QR code).

    Args:
        eink: If True, use e-ink color settings (eink_dark_mode, default light).
              If False, use web color settings (color_mode_dark, default dark).
        translations: Optional dict of translation strings for the current language.

    Returns (PIL Image, path) or (None, None) if PIL is unavailable.
    """
    if not _PIL_OK:
        return None, None

    if eink:
        dark = bool(config.get('eink_dark_mode', False))
    else:
        dark = bool(config.get('color_mode_dark', True))
    W, H  = _display_wh(config)
    cx    = W // 2

    BG     = (0,   0,   0)   if dark else (255, 255, 255)
    FG     = (255, 255, 255) if dark else (30,  30,  30)
    ORANGE = (247, 147, 26)
    GREEN  = (56,  161, 105)
    CARD   = (0,   0,   0)   if dark else (240, 240, 248)

    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Identical scaling to hotspot screen
    base = min(W, H)
    PAD  = max(10, base // 40)

    SZ_TITLE   = max(40, base * 48 // 480)
    SZ_WELCOME = max(18, base * 22 // 480)
    SZ_SUB     = max(17, base * 20 // 480)
    SZ_STEP    = max(15, base * 18 // 480)
    SZ_MONO    = max(12, base * 14 // 480)
    SZ_NOTE    = max(14, base * 16 // 480)

    f_title   = _font('RobotoCondensed-Bold.ttf', SZ_TITLE)
    f_welcome = _font('Roboto-Regular.ttf',        SZ_WELCOME)
    f_sub     = _font('Roboto-Bold.ttf',           SZ_SUB)
    f_step    = _font('Roboto-Bold.ttf',           SZ_STEP)
    f_mono    = _font('IBMPlexMono-Medium.ttf',    SZ_MONO)
    f_note    = _font('Roboto-Regular.ttf',        SZ_NOTE)

    t = translations or {}
    countdown_text = t.get('onboarding_disappears', 'This page disappears in {seconds} seconds.').format(seconds=timeout_seconds)
    connected_text = t.get('onboarding_connected', 'Successfully connected to your network')
    portal_text = t.get('onboarding_open_portal', 'Connect to the web portal:')
    thanks_text = t.get('onboarding_thank_you', 'Thank you for supporting this project!')

    # QR size: half the shorter edge
    qr_size = min(W, H) // 2
    card_pad = 8

    ec = (_qrcode.constants.ERROR_CORRECT_L if _QR_OK and qr_size < 200
          else _qrcode.constants.ERROR_CORRECT_M if _QR_OK else None)

    # ── Load mascot image for bottom section ─────────────────────────────
    mascot_path = os.path.join(_IMAGE_DIR, 'pepe_clown.png')
    mascot_img = None
    try:
        mascot_img = Image.open(mascot_path).convert('RGBA')
    except Exception:
        pass

    # Reserve bottom strip height for mascot + thank-you row
    mascot_h = max(60, base * 100 // 480) if mascot_img else 0
    bottom_strip = mascot_h + SZ_NOTE + PAD  # mascot row + countdown + padding

    # Fixed content heights
    title_h   = SZ_TITLE
    status_h  = SZ_SUB
    label_h   = SZ_STEP       # "Connect to the web portal:"
    qr_block  = qr_size + card_pad * 2
    url_h     = SZ_MONO

    # Distribute remaining space evenly between the content groups
    fixed_h = title_h + status_h + label_h + qr_block + url_h + bottom_strip
    n_gaps  = 4  # gaps: title-status, status-label, label+qr+url block, url-bottom
    margin  = max(PAD, (H - fixed_h - PAD * 2) // n_gaps)

    # ── Title (pinned near top) ───────────────────────────────────────────
    y = PAD
    _brand_title(draw, cx, y, f_title, SZ_TITLE, FG, ORANGE)
    y += title_h + margin

    # ── Status ────────────────────────────────────────────────────────────
    _centered(draw, cx, y, connected_text, f_sub, GREEN)
    y += status_h + margin

    # ── "Connect to..." label ─────────────────────────────────────────────
    _centered(draw, cx, y, portal_text, f_step, FG)
    y += label_h + PAD

    # ── QR code ───────────────────────────────────────────────────────────
    qr_x = cx - qr_size // 2
    qr_y = y + card_pad
    _card(draw, qr_x - card_pad, y, qr_x + qr_size + card_pad,
          qr_y + qr_size + card_pad, 8, CARD)
    img.paste(_qr_image(access_url, qr_size, False, ec), (qr_x, qr_y))
    y += qr_block + PAD

    # ── URL ───────────────────────────────────────────────────────────────
    _centered(draw, cx, y, access_url, f_mono, FG)
    url_bottom_y = y + url_h

    # ── Countdown (vertically centred in free space between URL and bottom row)
    mascot_row_top = H - mascot_h if mascot_img else H - PAD - SZ_WELCOME
    note_y = url_bottom_y + (mascot_row_top - url_bottom_y - SZ_NOTE) // 2
    _centered(draw, cx, note_y, countdown_text, f_note, FG)

    # ── Bottom: mascot image (left) + thank-you text (right) ──────────────
    if mascot_img:
        # Scale mascot to fit the reserved height, keeping aspect ratio
        m_w, m_h = mascot_img.size
        scale = mascot_h / m_h
        new_w = int(m_w * scale)
        new_h = mascot_h
        mascot_resized = mascot_img.resize((new_w, new_h), Image.LANCZOS)

        mascot_x = PAD
        mascot_y = H - new_h - 5

        # Paste with alpha for transparency support
        if mascot_resized.mode == 'RGBA':
            img.paste(mascot_resized, (mascot_x, mascot_y), mascot_resized)
        else:
            img.paste(mascot_resized, (mascot_x, mascot_y))

        # Thank-you text to the right of the mascot, vertically centred
        text_x = mascot_x + new_w + PAD
        text_area_w = W - text_x - PAD
        text_cx = text_x + text_area_w // 2

        # Word-wrap thanks_text to fit available width
        thanks_lines = _wrap_text(thanks_text, f_welcome, text_area_w)
        total_text_h = len(thanks_lines) * (SZ_WELCOME + 4)
        text_y = mascot_y + (new_h - total_text_h) // 2
        for line in thanks_lines:
            _centered(draw, text_cx, text_y, line, f_welcome, FG)
            text_y += SZ_WELCOME + 4
    else:
        # Fallback: centred thank-you without mascot
        thanks_y = H - PAD - SZ_WELCOME
        _centered(draw, cx, thanks_y, thanks_text, f_welcome, FG)

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, 'onboarding_connected.png')
    img.save(path, compress_level=1)
    return img, path
