"""Live posts from Nostr accounts the operator follows: fetching, the pool of
the last hour's posts, and picking the next one for the panel.

Nothing a post brings is written to the SD card. Images are held in memory,
downscaled; the card the panel shows is rendered to a RAM disk when there is
one. Only profile names and avatars are kept on disk, in cache/nostr/, and
written only when a profile changes.

Only signed events are trusted. A relay can hand back anything, and what it
hands back ends up on a wall display, so every event an image is taken from
has its id and its BIP-340 signature checked against the author's key.
"""

from PIL import Image
from PIL import ImageOps
from concurrent.futures import ThreadPoolExecutor
from utils.atomic_io import atomic_write_json
import hashlib
import io
import ipaddress
import json
import os
import re
import shutil
import threading
import time
import uuid
from urllib.parse import urlparse


NOSTR_DIR = os.path.join('cache', 'nostr')
AVATAR_DIR = os.path.join(NOSTR_DIR, 'avatars')
_STATE_PATH = os.path.join(NOSTR_DIR, 'profiles.json')
# Where the rendered card goes: RAM on a Pi, so a card a block does not wear
# the SD card. A desktop without /dev/shm falls back to cache/.
CARD_DIR = (os.path.join('/dev/shm', 'mempaper-nostr') if os.path.isdir('/dev/shm')
            else os.path.join('cache', 'nostr_cards'))
# How long a rendered card stays. Counting files instead removed cards still
# in use: the next block's image is chosen ahead of time and may wait through
# a long block, while other picks write newer cards. Posts leave the pool
# after an hour, so three is ample, and the cards are in RAM, a few MB at most.
_CARD_MAX_AGE = 3 * 3600
# Where an earlier version kept every image on disk. Removed once.
_LEGACY_DIR = os.path.join('static', 'nostr')
_LEGACY_SHOWN = os.path.join('cache', 'nostr_shown.json')

DEFAULT_RELAYS = [
    'wss://relay.damus.io',
    'wss://nos.lol',
    'wss://relay.primal.net',
    'wss://relay.snort.social',
]

# Relays that collect profiles, follow lists and relay lists from everywhere.
# Asked for those only, never for posts: an account that publishes to its own
# relays alone is still found by name, and its relay list says where its
# posts are.
INDEXER_RELAYS = [
    'wss://purplepag.es',
    'wss://user.kindpag.es',
    'wss://indexer.coracle.social',
]
# Relays added for posts beyond the configured ones: those most of the
# followed accounts write to (NIP-65), so a post published only there is
# still seen. Capped, because a list of hundreds names hundreds of relays.
_MAX_OUTBOX_RELAYS = 8
# An account with no profile found is asked about again after this long.
_NO_PROFILE_RETRY = 3600

# Often enough that a post reaches the panel while it is still news; a relay
# query asking only for what is new since the last one is cheap.
FETCH_INTERVAL_SECONDS = 5 * 60
_PROFILE_REFRESH_SECONDS = 30 * 60

# Text notes and NIP-68 picture posts.
_IMAGE_KINDS = [1, 20]

DAY = 24 * 3600
# A post is in the pool for this long after it was published.
POOL_WINDOW = 3600
# A post comes back only after this many other images have been shown.
_MIN_GAP = 2
_MAX_POOL = 40
_EVENT_LIMIT = 200
# Authors per relay filter. A followed list imported from a contact list can
# run to hundreds, and relays cap how many keys one filter may carry.
_AUTHORS_PER_FILTER = 100
# Avatars fetched per run beyond the ones a card needs right now, so an
# imported list of hundreds fills in over a few runs instead of in one burst.
_AVATARS_PER_RUN = 10
# When nobody posted within the window, the newest post of the last day is
# kept - not to show, only so the settings page has something to preview.
_SAMPLE_WINDOW = DAY

_MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
# Smaller than this is an emoji, an avatar or a badge, not a picture.
_MIN_SIDE = 200
# Held in memory at this size: enough for the card, which is 1000 px wide.
_MAX_HELD_SIDE = 1200

# Perceptual match: 256-bit difference hash. Nostr clients and media hosts
# re-encode on upload, so a repost is rarely byte-identical. 256 bits rather
# than the usual 64 because memes share templates: at 9x8 two captions on the
# same picture hash alike, at 17x16 the lettering still shows.
_DHASH_SIZE = 16
_DHASH_MAX_DISTANCE = 12
_ASPECT_TOLERANCE = 0.05
# Repost check reaches back this far.
_DUPLICATE_MEMORY = DAY

_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
_URL_RE = re.compile(r'https?://[^\s<>"\'\]\)]+', re.IGNORECASE)


# ----------------------------------------------------------------------
# Keys: bech32 (NIP-19)
# ----------------------------------------------------------------------

_BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'


def _bech32_polymod(values):
    gen = (0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data, frombits, tobits, pad=True):
    acc = bits = 0
    out = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or value >> frombits:
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & maxv)
    if pad:
        if bits:
            out.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return out


def bech32_decode(text):
    """(hrp, bytes) for a bech32 string, or (None, None) when it is not one."""
    text = text.strip()
    if text.lower() != text and text.upper() != text:
        return None, None
    text = text.lower()
    pos = text.rfind('1')
    if pos < 1 or pos + 7 > len(text):
        return None, None
    hrp = text[:pos]
    try:
        data = [_BECH32_CHARSET.index(c) for c in text[pos + 1:]]
    except ValueError:
        return None, None
    if _bech32_polymod(_bech32_hrp_expand(hrp) + data) != 1:
        return None, None
    decoded = _convertbits(data[:-6], 5, 8, pad=False)
    if decoded is None:
        return None, None
    return hrp, bytes(decoded)


def bech32_encode(hrp, payload):
    data = _convertbits(payload, 8, 5)
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0] * 6) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + '1' + ''.join(_BECH32_CHARSET[d] for d in data + checksum)


def parse_pubkey(text):
    """Hex public key for an npub, an nprofile or 64 hex characters; else None."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if text.startswith('nostr:'):
        text = text[6:]
    if re.fullmatch(r'[0-9a-fA-F]{64}', text):
        return text.lower()
    hrp, payload = bech32_decode(text)
    if hrp == 'npub' and payload and len(payload) == 32:
        return payload.hex()
    if hrp == 'nprofile' and payload:
        # TLV: type 0 is the key itself.
        i = 0
        while i + 2 <= len(payload):
            t, length = payload[i], payload[i + 1]
            value = payload[i + 2:i + 2 + length]
            if t == 0 and len(value) == 32:
                return value.hex()
            i += 2 + length
    return None


def npub(pubkey_hex):
    return bech32_encode('npub', bytes.fromhex(pubkey_hex))


def note_id(event_id_hex):
    return bech32_encode('note', bytes.fromhex(event_id_hex))


def configured_accounts(config):
    """[(pubkey_hex, label)] from the config, invalid and repeated keys dropped."""
    out = []
    seen = set()
    for entry in config.get('nostr_accounts', []) or []:
        if not isinstance(entry, dict):
            continue
        pk = parse_pubkey(entry.get('npub', ''))
        if pk and pk not in seen:
            seen.add(pk)
            out.append((pk, str(entry.get('comment', '')).strip()))
    return out


def configured_relays(config):
    relays = [r.strip() for r in (config.get('nostr_relays') or [])
              if isinstance(r, str) and r.strip().lower().startswith(('wss://', 'ws://'))]
    return relays or list(DEFAULT_RELAYS)


# ----------------------------------------------------------------------
# Event verification: NIP-01 id, BIP-340 Schnorr signature
# ----------------------------------------------------------------------

_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8, 1)


# Jacobian coordinates: one inversion per scalar multiplication instead of one
# per step. A Pi Zero verifies a signature in well under a second this way.
def _jac_double(pt):
    if pt is None:
        return None
    x, y, z = pt
    if y == 0:
        return None
    ysq = y * y % _P
    s = 4 * x * ysq % _P
    m = 3 * x * x % _P
    nx = (m * m - 2 * s) % _P
    ny = (m * (s - nx) - 8 * ysq * ysq) % _P
    nz = 2 * y * z % _P
    return nx, ny, nz


def _jac_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    z1sq, z2sq = z1 * z1 % _P, z2 * z2 % _P
    u1, u2 = x1 * z2sq % _P, x2 * z1sq % _P
    s1, s2 = y1 * z2sq * z2 % _P, y2 * z1sq * z1 % _P
    if u1 == u2:
        return _jac_double(p1) if s1 == s2 else None
    h, r = (u2 - u1) % _P, (s2 - s1) % _P
    h2 = h * h % _P
    h3 = h * h2 % _P
    u1h2 = u1 * h2 % _P
    nx = (r * r - h3 - 2 * u1h2) % _P
    ny = (r * (u1h2 - nx) - s1 * h3) % _P
    nz = h * z1 * z2 % _P
    return nx, ny, nz


def _jac_mul(pt, k):
    result = None
    addend = pt
    while k:
        if k & 1:
            result = _jac_add(result, addend)
        addend = _jac_double(addend)
        k >>= 1
    return result


def _lift_x(x):
    if x >= _P:
        return None
    c = (pow(x, 3, _P) + 7) % _P
    y = pow(c, (_P + 1) // 4, _P)
    if y * y % _P != c:
        return None
    return x, (y if y % 2 == 0 else _P - y), 1


def _tagged_hash(tag, msg):
    th = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(th + th + msg).digest()


def schnorr_verify(msg, pubkey, sig):
    """BIP-340 verification. All three arguments are bytes."""
    if len(msg) != 32 or len(pubkey) != 32 or len(sig) != 64:
        return False
    pt = _lift_x(int.from_bytes(pubkey, 'big'))
    r = int.from_bytes(sig[:32], 'big')
    s = int.from_bytes(sig[32:], 'big')
    if pt is None or r >= _P or s >= _N:
        return False
    e = int.from_bytes(_tagged_hash('BIP0340/challenge', sig[:32] + pubkey + msg), 'big') % _N
    big_r = _jac_add(_jac_mul(_G, s), _jac_mul(pt, _N - e))
    if big_r is None:
        return False
    x, y, z = big_r
    zinv = pow(z, -1, _P)
    zinv2 = zinv * zinv % _P
    ax, ay = x * zinv2 % _P, y * zinv2 * zinv % _P
    return ay % 2 == 0 and ax == r


def verify_event(event):
    """True when the event's id matches its content and its signature is valid."""
    try:
        serialized = json.dumps(
            [0, event['pubkey'], event['created_at'], event['kind'],
             event['tags'], event['content']],
            separators=(',', ':'), ensure_ascii=False)
        digest = hashlib.sha256(serialized.encode('utf-8')).digest()
        if digest.hex() != event['id']:
            return False
        return schnorr_verify(digest, bytes.fromhex(event['pubkey']),
                              bytes.fromhex(event['sig']))
    except (KeyError, TypeError, ValueError):
        return False


# ----------------------------------------------------------------------
# Relays
# ----------------------------------------------------------------------

def _ws_proxy_kwargs(config, circuit='nostr'):
    """websocket-client proxy settings for Tor, or {} when Tor is off.

    The SOCKS credentials are not authentication - Tor's SOCKS port has none.
    They pick a circuit: IsolateSOCKSAuth puts each distinct username on its
    own. 'nostr' keeps relay traffic off the circuit the mempool requests use;
    a retry passes a fresh name to leave through a different exit.
    """
    if not config.get('nostr_use_tor', True):
        return {}
    from utils.technical_config import TOR_CONNECT_TIMEOUT
    return {
        'proxy_type': 'socks5h',
        'http_proxy_host': config.get('tor_socks_host', '127.0.0.1') or '127.0.0.1',
        'http_proxy_port': int(config.get('tor_socks_port', 9050) or 9050),
        'http_proxy_timeout': TOR_CONNECT_TIMEOUT,
        'http_proxy_auth': (f'mempaper-{circuit}', 'x'),
    }


def _query_relay(url, filters, config, deadline_s, circuit='nostr'):
    """Every event one relay returns for the filters, until EOSE or the deadline.

    Returns (events, error text or None, whether a retry on another circuit
    could help).
    """
    import websocket
    sub = uuid.uuid4().hex[:16]
    events = []
    deadline = time.monotonic() + deadline_s
    ws = None
    try:
        ws = websocket.create_connection(url, timeout=min(deadline_s, 30),
                                         **_ws_proxy_kwargs(config, circuit))
        ws.send(json.dumps(['REQ', sub] + filters))
        while time.monotonic() < deadline:
            ws.settimeout(max(1.0, deadline - time.monotonic()))
            raw = ws.recv()
            if not raw:
                break
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, list) or len(msg) < 2:
                continue
            if msg[0] == 'EVENT' and msg[1] == sub and len(msg) >= 3 and isinstance(msg[2], dict):
                events.append(msg[2])
            elif msg[0] in ('EOSE', 'CLOSED') and msg[1] == sub:
                break
        try:
            ws.send(json.dumps(['CLOSE', sub]))
        except Exception:
            pass
        return events, None, False
    except Exception as e:
        return events, f'{url}: {_describe_relay_error(e)}', _exit_may_matter(e)
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _exit_may_matter(e):
    """True for failures another Tor exit might not get.

    Relays behind Cloudflare drop or refuse some exits: the TLS handshake is
    cut off (SSLEOFError), the connection reset, or a 403/429/503 returned.
    A timeout or a bad address is the same from every exit.
    """
    import ssl
    status = getattr(e, 'status_code', None)
    if status:
        return status in (403, 429, 503)
    return isinstance(e, (ssl.SSLError, ConnectionResetError, ConnectionAbortedError,
                          BrokenPipeError)) or 'connection closed' in str(e).lower()


def _describe_relay_error(e):
    """One line a person can act on. A refused handshake otherwise carries
    every response header, a TLS failure an OpenSSL source location."""
    import ssl
    status = getattr(e, 'status_code', None)
    if status:
        return f'HTTP {status} during handshake (relay down or refusing)'
    if isinstance(e, ssl.SSLEOFError) or 'UNEXPECTED_EOF' in str(e):
        return 'connection closed during TLS handshake (relay overloaded, or it refuses this Tor exit)'
    if isinstance(e, ssl.SSLCertVerificationError):
        return 'TLS certificate not valid'
    if isinstance(e, (ConnectionResetError, ConnectionAbortedError)):
        return 'connection reset by the relay'
    if isinstance(e, TimeoutError) or 'timed out' in str(e).lower():
        return 'timed out'
    if 'getaddrinfo' in str(e) or 'name or service not known' in str(e).lower():
        return 'relay address not found'
    first = (str(e).splitlines() or [''])[0]
    return f'{type(e).__name__}: {first}'[:160]


def _author_filters(pubkeys, kinds, limit=None, since=None):
    """Relay filters covering pubkeys in groups of _AUTHORS_PER_FILTER.

    since: None, or a function of the group returning its since value.
    """
    filters = []
    for i in range(0, len(pubkeys), _AUTHORS_PER_FILTER):
        group = pubkeys[i:i + _AUTHORS_PER_FILTER]
        f = {'authors': group, 'kinds': kinds}
        if limit:
            f['limit'] = limit
        if since:
            f['since'] = since(group)
        filters.append(f)
    return filters


def _profile_filters(pubkeys):
    """Profile and relay-list filters for pubkeys.

    One kind per filter, each with a limit as large as its group: a relay
    otherwise applies its own default limit to the filter, and with both kinds
    for a hundred authors in one, part of the profiles never came back.
    """
    filters = []
    for kind in (0, 10002):
        for f in _author_filters(pubkeys, kinds=[kind]):
            f['limit'] = len(f['authors'])
            filters.append(f)
    return filters


def _profile_relays(config):
    return list(dict.fromkeys(configured_relays(config) + INDEXER_RELAYS))


def _write_relays(event):
    """The relays a NIP-65 relay list (kind 10002) says the author writes to."""
    out = []
    for tag in event.get('tags', []):
        if not (isinstance(tag, list) and len(tag) >= 2 and tag[0] == 'r' and isinstance(tag[1], str)):
            continue
        marker = tag[2] if len(tag) > 2 else None
        url = tag[1].strip().rstrip('/')
        if marker in (None, '', 'write') and url.lower().startswith('wss://') \
                and not _is_private_host(url) and len(url) <= 200 and url not in out:
            out.append(url)
    return out[:5]


def _name_of(meta):
    """Display name from a kind-0 profile. Clients disagree on the field."""
    for key in ('display_name', 'displayName', 'name', 'username'):
        value = str(meta.get(key) or '').strip()
        if value:
            return value[:64]
    return ''


def query_relays(relays, filters, config, extra=None):
    """Union of what every relay returns, deduplicated by event id.

    extra: {relay: filters} asked as well, each with its own filters. Their
    failures are logged but not returned: they are a bonus on top of the
    configured relays, and nothing the operator set up.

    Returns (events, errors). Relays are asked in parallel; a slow one costs
    its own deadline, not everyone's.
    """
    tor = config.get('nostr_use_tor', True)
    deadline = 90 if tor else 30

    def ask(task):
        relay, relay_filters = task
        events, err, exit_matters = _query_relay(relay, relay_filters, config, deadline)
        if err and tor and exit_matters and not events:
            # Once more on a circuit of its own: a relay refusing one exit
            # usually accepts the next.
            print(f'🧅 Nostr relay: {err} - retrying through another Tor exit')
            events, err, _ = _query_relay(relay, relay_filters, config, deadline,
                                          circuit=f'nostr-{uuid.uuid4().hex[:8]}')
        return events, err

    tasks = [(r, filters) for r in relays]
    tasks += [(r, f) for r, f in (extra or {}).items() if r not in relays and f]
    by_id = {}
    errors = []
    with ThreadPoolExecutor(max_workers=max(1, min(len(tasks), 8))) as pool:
        for i, (events, err) in enumerate(pool.map(ask, tasks)):
            if err:
                print(f'⚠️ Nostr relay: {err}')
                if i < len(relays):
                    errors.append(err)
            for ev in events:
                if isinstance(ev.get('id'), str):
                    by_id.setdefault(ev['id'], ev)
    return list(by_id.values()), errors


# ----------------------------------------------------------------------
# Images
# ----------------------------------------------------------------------

def image_urls(event):
    """Image URLs in an event, in the order they appear."""
    urls = []
    # imeta (NIP-92) and NIP-68 picture events: the media type is stated, so a
    # URL without a file extension still counts.
    for tag in event.get('tags', []):
        if isinstance(tag, list) and tag and tag[0] == 'imeta':
            fields = {}
            for item in tag[1:]:
                if isinstance(item, str) and ' ' in item:
                    k, v = item.split(' ', 1)
                    fields.setdefault(k, v)
            u, mime = fields.get('url', ''), fields.get('m', '')
            if u and (mime.startswith('image/') or _looks_like_image(u)):
                urls.append(u)
    content = event.get('content', '')
    if isinstance(content, str):
        for u in _URL_RE.findall(content):
            u = u.rstrip('.,;:!?')
            if _looks_like_image(u):
                urls.append(u)
    return list(dict.fromkeys(u for u in urls if u.lower().startswith(('http://', 'https://'))))


def _looks_like_image(url):
    return urlparse(url).path.lower().endswith(_IMAGE_EXTENSIONS)


def _is_private_host(url):
    """True for a URL naming this device or the LAN by address.

    A note is a link anyone can write. Without this a signed note could make
    the device fetch from its own network. Names are not resolved: over Tor
    they cannot reach the LAN anyway, and that is the default.
    """
    host = (urlparse(url).hostname or '').lower()
    if not host or host == 'localhost' or host.endswith(('.local', '.lan', '.home', '.internal')):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _http_proxies(config):
    if not config.get('nostr_use_tor', True):
        return None
    host = config.get('tor_socks_host', '127.0.0.1') or '127.0.0.1'
    port = config.get('tor_socks_port', 9050) or 9050
    endpoint = f'socks5h://{host}:{port}'
    return {'http': endpoint, 'https': endpoint}


def _download(url, config):
    """The image bytes, or raise. Capped at _MAX_DOWNLOAD_BYTES."""
    import requests
    tor = config.get('nostr_use_tor', True)
    with requests.get(url, stream=True, proxies=_http_proxies(config),
                      timeout=(60, 120) if tor else (10, 60),
                      headers={'User-Agent': 'Mozilla/5.0'}) as resp:
        resp.raise_for_status()
        if int(resp.headers.get('Content-Length') or 0) > _MAX_DOWNLOAD_BYTES:
            raise ValueError('image too large')
        buf = io.BytesIO()
        for chunk in resp.iter_content(64 * 1024):
            buf.write(chunk)
            if buf.tell() > _MAX_DOWNLOAD_BYTES:
                raise ValueError('image too large')
        return buf.getvalue()


def dhash(img):
    """256-bit difference hash of a PIL image, as an int."""
    small = img.convert('L').resize((_DHASH_SIZE + 1, _DHASH_SIZE), Image.LANCZOS)
    px = list(small.getdata())
    value = 0
    w = _DHASH_SIZE + 1
    for row in range(_DHASH_SIZE):
        for col in range(_DHASH_SIZE):
            value = (value << 1) | (px[row * w + col] < px[row * w + col + 1])
    return value


def _near_duplicate(dh, aspect, known):
    """What the image looks like, or None.

    known: iterable of (dhash int, aspect ratio, label). Returns the label of
    the first match and the bit distance, so a skip can be checked by hand.
    """
    for other, other_aspect, label in known:
        if other_aspect and abs(aspect - other_aspect) / other_aspect > _ASPECT_TOLERANCE:
            continue
        distance = (dh ^ other).bit_count()
        if distance <= _DHASH_MAX_DISTANCE:
            return label, distance
    return None


def _short_url(url):
    """host/…/last-segment: enough to find the image again, short enough to read."""
    parts = urlparse(url)
    tail = parts.path.rsplit('/', 1)[-1]
    if len(tail) > 24:
        tail = tail[:10] + '…' + tail[-10:]
    return f'{parts.hostname}/…/{tail}' if tail else (parts.hostname or url)


def _describe_error(e):
    """A reason a person can act on, rather than an exception class name."""
    import requests
    from PIL import UnidentifiedImageError
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f'HTTP {e.response.status_code} {e.response.reason or ""}'.strip()
    if isinstance(e, requests.Timeout):
        return 'timed out'
    if isinstance(e, requests.ConnectionError):
        text = str(e).lower()
        if 'socks' in text or 'proxy' in text:
            return 'connection via Tor failed (host may block Tor)'
        if 'name or service' in text or 'resolve' in text or 'getaddrinfo' in text:
            return 'host not found'
        if 'ssl' in text or 'certificate' in text:
            return 'TLS/certificate error'
        return 'connection failed'
    if isinstance(e, UnidentifiedImageError):
        return 'not an image the server can read'
    if isinstance(e, ValueError) and 'too large' in str(e):
        return f'larger than {_MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB'
    return f'{type(e).__name__}: {e}'[:160]


# ----------------------------------------------------------------------
# The store
# ----------------------------------------------------------------------

def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def card_theme(config):
    theme = config.get('nostr_card_theme', 'light')
    return theme if theme in ('light', 'dark') else 'light'


class NostrPostStore:
    """One per process: the pool must outlive ImageRenderer, which is rebuilt
    on every settings save.

    A post is a dict: key, event_id, pubkey, created_at, text, image (encoded
    bytes), shown (count) and last_tick (pick counter when last shown).
    """

    def __init__(self):
        self.lock = threading.RLock()
        self._fetch_lock = threading.Lock()
        self._pool = {}
        self._sample = None
        self._dismissed = set()
        self._seen_events = {}      # event_id -> created_at, handled for good
        self._failures = {}         # event_id -> failed download attempts
        self._recent_hashes = []    # (added_at, sha256, dhash, aspect, label)
        self._cursors = {}          # pubkey -> newest created_at seen
        self._profiles_fetched = 0.0
        self._preview_cache = {}    # (key, theme, width) -> (rendered_at, bytes)
        self._tick = 0
        self._migrated = False
        self.status = {'running': False, 'last_run': None, 'message': '',
                       'added': 0, 'duplicates': 0, 'errors': []}

    # -- picking --------------------------------------------------------

    def tick(self):
        """Count one image shown, whatever its source. The gap a post has to
        wait out is counted in these, so a meme in between counts too."""
        with self.lock:
            self._tick += 1

    def _eligible(self, post, tick):
        return post['last_tick'] is None or tick - post['last_tick'] > _MIN_GAP

    def _expire(self, now):
        for key, post in list(self._pool.items()):
            if now - post['created_at'] > POOL_WINDOW:
                del self._pool[key]
                if self._sample is None or post['created_at'] > self._sample['created_at']:
                    self._sample = post

    def _ranked(self, tick, now):
        """Pool posts in the order they would be picked at this tick, each with
        whether it may be picked at all.

        Never shown first, newest first. Then the ones shown longest ago - a
        round robin through the hour. Posts still waiting out their gap last.
        """
        self._expire(now)
        posts = list(self._pool.values())
        fresh = sorted((p for p in posts if p['last_tick'] is None), key=lambda p: -p['created_at'])
        again = sorted((p for p in posts if p['last_tick'] is not None and self._eligible(p, tick)),
                       key=lambda p: (p['last_tick'], -p['created_at']))
        waiting = sorted((p for p in posts if not self._eligible(p, tick)),
                         key=lambda p: p['last_tick'])
        return [(p, True) for p in fresh + again] + [(p, False) for p in waiting]

    def pick(self, config, now=None, relaxed=False):
        """Path of the card to show now, or None to fall back to a meme.

        relaxed: there is nothing else to show (memes are off or empty), so
        the gap is not waited out - the post shown longest ago comes back -
        and with the pool empty, the newest older post is shown rather than
        an empty panel.
        """
        now = now or time.time()
        with self.lock:
            ranked = self._ranked(self._tick, now)
            if ranked and (ranked[0][1] or relaxed):
                # The waiting posts are ranked by when they were last shown,
                # oldest first, so in relaxed mode this is the fairest repeat.
                post = ranked[0][0] if ranked[0][1] else min(
                    (p for p, _ in ranked), key=lambda p: p['last_tick'])
            elif relaxed and self._sample is not None:
                post = self._sample
            else:
                return None
            post['shown'] += 1
            post['last_tick'] = self._tick
        try:
            return self._write_card(post, config, now)
        except Exception as e:
            print(f'⚠️ Nostr: could not render card {post["key"]}: {e}')
            return None

    def has_posts(self):
        with self.lock:
            self._expire(time.time())
            return bool(self._pool)

    # -- cards ----------------------------------------------------------

    def _render(self, post, theme, now=None):
        from lib.nostr_card import render_card
        profile = self._profiles().get(post['pubkey'], {})
        image = Image.open(io.BytesIO(post['image']))
        return render_card(image, profile.get('name') or npub(post['pubkey'])[:16] + '…',
                           post['text'], post['created_at'],
                           avatar_path=self._avatar_path(post['pubkey']), theme=theme, now=now)

    def _write_card(self, post, config, now):
        card = self._render(post, card_theme(config), now)
        os.makedirs(CARD_DIR, exist_ok=True)
        # A new file for every pick, never one rewritten in place. The block
        # render, the next block's pre-render and the precache each pick, often
        # the same post at the same moment: sharing one file (and one '.tmp')
        # interleaved their writes into a corrupt JPEG, or replaced a card a
        # renderer was still reading.
        name = f'{post["key"]}_{card_theme(config)}_{uuid.uuid4().hex[:8]}'
        path = os.path.join(CARD_DIR, name + '.jpg')
        tmp = os.path.join(CARD_DIR, name + '.tmp')
        try:
            card.save(tmp, 'JPEG', quality=92)
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        # Old cards go by age, not by count - see _CARD_MAX_AGE.
        for name in os.listdir(CARD_DIR):
            old = os.path.join(CARD_DIR, name)
            try:
                if now - os.path.getmtime(old) > _CARD_MAX_AGE:
                    os.remove(old)
            except OSError:
                pass
        return path

    def preview_jpeg(self, key, theme, width=None):
        """The card as JPEG bytes for the settings page, or None."""
        with self.lock:
            post = self._pool.get(key) or (self._sample if self._sample and self._sample['key'] == key else None)
        if post is None:
            return None
        cache_key = (key, theme, width)
        cached = self._preview_cache.get(cache_key)
        # The age on the card moves, so a cached preview lives a minute.
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        card = self._render(post, theme)
        if width and width < card.width:
            card = card.resize((width, round(card.height * width / card.width)), Image.LANCZOS)
        buf = io.BytesIO()
        card.save(buf, 'JPEG', quality=88)
        data = buf.getvalue()
        if len(self._preview_cache) > 100:
            self._preview_cache.clear()
        self._preview_cache[cache_key] = (time.time(), data)
        return data

    def dismiss(self, key):
        """Take a post out of the pool for good."""
        with self.lock:
            post = self._pool.pop(key, None)
            if post is None and self._sample and self._sample['key'] == key:
                post, self._sample = self._sample, None
            if post is None:
                return False
            self._dismissed.add(post['event_id'])
            return True

    def overview(self, now=None):
        """The pool in pick order, for the settings page."""
        now = now or time.time()
        with self.lock:
            # Ranked at the next tick: what the next pick would see.
            ranked = self._ranked(self._tick + 1, now)
            posts = []
            for i, (p, eligible) in enumerate(ranked):
                posts.append({
                    **self._describe(p),
                    'shown': p['shown'],
                    'state': 'next' if i == 0 and eligible else ('queued' if eligible else 'waiting'),
                    'expires_in': max(0, int(POOL_WINDOW - (now - p['created_at']))),
                })
            sample = self._describe(self._sample) if self._sample and not posts else None
            counts = {}
            for p in self._pool.values():
                counts[p['pubkey']] = counts.get(p['pubkey'], 0) + 1
        return {'posts': posts, 'sample': sample, 'counts': counts}

    def _describe(self, p):
        profile = self._profiles().get(p['pubkey'], {})
        return {'key': p['key'], 'note': note_id(p['event_id']), 'pubkey': p['pubkey'],
                'name': profile.get('name', ''), 'npub': npub(p['pubkey']),
                'created_at': p['created_at'], 'text': p['text'][:200]}

    # -- fetching -------------------------------------------------------

    def fetch(self, config, log=print):
        """One fetch run. Returns the status dict. Never runs twice at once."""
        if not self._fetch_lock.acquire(blocking=False):
            return self.status
        try:
            self.status.update(running=True, message='', added=0, duplicates=0, errors=[])
            try:
                self._fetch(config, log)
            except Exception as e:
                self.status['message'] = f'{type(e).__name__}: {e}'
                log(f'⚠️ Nostr fetch failed: {e}')
            return self.status
        finally:
            self.status['running'] = False
            self.status['last_run'] = time.time()
            self._fetch_lock.release()

    def _migrate(self):
        """Earlier versions kept every image under static/. Free that space."""
        if self._migrated:
            return
        self._migrated = True
        for path in (_LEGACY_DIR,):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                print('🧹 Nostr: removed the image store of the previous version')
        try:
            os.remove(_LEGACY_SHOWN)
        except OSError:
            pass

    def _fetch(self, config, log):
        self._migrate()
        accounts = configured_accounts(config)
        relays = configured_relays(config)
        followed = {pk for pk, _ in accounts}
        now = int(time.time())

        with self.lock:
            self._prune_unfollowed(followed)
            self._expire(now)
        if not accounts:
            self.status['message'] = 'No accounts configured'
            return

        pubkeys = [pk for pk, _ in accounts]
        labels = dict(accounts)

        # Profiles, for the name and avatar on each card. Not every run: they
        # rarely change, and a new account is looked up straight away anyway.
        state = _load_json(_STATE_PATH, {})
        profiles = state.setdefault('profiles', {})
        if (now - self._profiles_fetched > _PROFILE_REFRESH_SECONDS
                or any(pk not in profiles for pk in pubkeys)):
            lookup = _profile_relays(config)
            events, errors = query_relays(lookup, _profile_filters(pubkeys), config)
            self.status['errors'].extend(e for e in errors if not e.startswith(tuple(INDEXER_RELAYS)))
            if len(errors) == len(lookup):
                self.status['message'] = 'No relay could be reached'
                log('⚠️ Nostr: no relay could be reached')
                return
            before = json.dumps(profiles, sort_keys=True)
            self._apply_profiles(events, set(pubkeys), profiles, config, avatars=False)
            self._names_from_own_relays(pubkeys, profiles, config)
            for pk in pubkeys:
                profiles.setdefault(pk, {'name': '', 'picture': '', 'updated': 0})['checked'] = now
            self._fill_avatars(pubkeys, profiles, config, _AVATARS_PER_RUN)
            if json.dumps(profiles, sort_keys=True) != before:
                os.makedirs(NOSTR_DIR, exist_ok=True)
                atomic_write_json(_STATE_PATH, state, ensure_ascii=False)
            self._profiles_fetched = now

        # Posts since the last run, never older than the window. While there is
        # nothing to preview yet, a day back, to find one.
        with self.lock:
            need_sample = self._sample is None and not self._pool
        floor = now - (_SAMPLE_WINDOW if need_sample else POOL_WINDOW)
        # One filter per group of authors, from the oldest cursor in the group;
        # anything already handled is skipped by its event id.
        filters = _author_filters(
            pubkeys, kinds=_IMAGE_KINDS, limit=_EVENT_LIMIT,
            since=lambda group: max(min(self._cursors.get(pk, 0) for pk in group) + 1, floor))
        # Plus the relays the followed accounts say they write to, each asked
        # only about the accounts that use it.
        by_relay = {}
        for pk in pubkeys:
            for relay in profiles.get(pk, {}).get('relays', []):
                if relay not in relays:
                    by_relay.setdefault(relay, []).append(pk)
        busiest = sorted(by_relay, key=lambda r: -len(by_relay[r]))[:_MAX_OUTBOX_RELAYS]
        extra = {r: _author_filters(
                    by_relay[r], kinds=_IMAGE_KINDS, limit=_EVENT_LIMIT,
                    since=lambda group: max(min(self._cursors.get(pk, 0) for pk in group) + 1, floor))
                 for r in busiest}
        events, errors = query_relays(relays, filters, config, extra=extra)
        self.status['errors'].extend(errors)
        if len(errors) == len(relays) and not events:
            self.status['message'] = 'No relay could be reached'
            log('⚠️ Nostr: no relay could be reached')
            return

        events = sorted((e for e in events if e.get('pubkey') in labels
                         and isinstance(e.get('created_at'), int)),
                        key=lambda e: -e['created_at'])
        added = 0
        sample_found = not need_sample
        for ev in events:
            eid = ev.get('id', '')
            if eid in self._seen_events or eid in self._dismissed:
                continue
            in_window = now - ev['created_at'] <= POOL_WINDOW
            if not in_window and sample_found:
                continue
            post = self._make_post(ev, config, log)
            if post is None:
                continue
            with self.lock:
                if in_window:
                    self._pool[post['key']] = post
                    added += 1
                elif self._sample is None or post['created_at'] > self._sample['created_at']:
                    self._sample = post
                    sample_found = True

        # A card needs its author's avatar now, not in a few runs.
        with self.lock:
            authors = {p['pubkey'] for p in self._pool.values()}
            if self._sample:
                authors.add(self._sample['pubkey'])
        if authors:
            self._fill_avatars(sorted(authors), self._profiles(), config, len(authors))

        with self.lock:
            for ev in events:
                pk = ev['pubkey']
                self._cursors[pk] = max(self._cursors.get(pk, 0), ev['created_at'])
            # Newest first beyond the cap.
            if len(self._pool) > _MAX_POOL:
                for key in sorted(self._pool, key=lambda k: self._pool[k]['created_at'])[:len(self._pool) - _MAX_POOL]:
                    del self._pool[key]
            cutoff = now - 2 * DAY
            self._seen_events = {k: t for k, t in self._seen_events.items() if t > cutoff}
            self._recent_hashes = [h for h in self._recent_hashes if now - h[0] <= _DUPLICATE_MEMORY]
            self._preview_cache.clear()
            pool_size = len(self._pool)

        self.status['added'] = added
        self.status['message'] = 'ok'
        # Every five minutes; a line for each quiet run would only fill the journal.
        if added or self.status['duplicates']:
            log(f'🟣 Nostr: {added} new post(s), {self.status["duplicates"]} duplicate(s) skipped, '
                f'{pool_size} in the pool')

    def _make_post(self, ev, config, log):
        """The post for an event, its first usable image held in memory; None
        when it has none, is not genuine, or repeats one already seen."""
        eid = ev['id']
        urls = [u for u in image_urls(ev) if not _is_private_host(u)]
        if not urls:
            self._seen_events[eid] = ev['created_at']
            return None
        if not verify_event(ev):
            self._seen_events[eid] = ev['created_at']
            log(f'⚠️ Nostr: dropped event {eid[:12]} with a bad signature')
            return None

        failed = False
        for url in urls:
            try:
                data = _download(url, config)
                img = Image.open(io.BytesIO(data))
                img.seek(0)
                img = ImageOps.exif_transpose(img)
                img.load()
            except Exception as e:
                reason = _describe_error(e)
                self.status['errors'].append(f'{_short_url(url)}: {reason}')
                log(f'⚠️ Nostr: could not download {url}: {reason}')
                failed = True
                continue
            if min(img.size) < _MIN_SIDE:
                continue

            sha = hashlib.sha256(data).hexdigest()
            aspect = img.width / img.height
            dh = dhash(img)
            known = [(h[2], h[3], h[4]) for h in self._recent_hashes]
            match = next((h[4] for h in self._recent_hashes if h[1] == sha), None)
            if match is None:
                near = _near_duplicate(dh, aspect, known)
                match = near[0] if near else None
            if match:
                self.status['duplicates'] += 1
                self._seen_events[eid] = ev['created_at']
                log(f'↺ Nostr: skipped {url}, same image as {match}')
                return None

            img.thumbnail((_MAX_HELD_SIDE, _MAX_HELD_SIDE), Image.LANCZOS)
            buf = io.BytesIO()
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img.convert('RGBA').save(buf, 'PNG')
            else:
                img.convert('RGB').save(buf, 'JPEG', quality=88)
            self._recent_hashes.append((time.time(), sha, dh, aspect, f'post {eid[:12]}'))
            self._seen_events[eid] = ev['created_at']
            self._failures.pop(eid, None)
            return {
                'key': eid[:16], 'event_id': eid, 'pubkey': ev['pubkey'],
                'created_at': ev['created_at'],
                'text': _post_text(ev.get('content', ''), image_urls(ev)),
                'image': buf.getvalue(), 'shown': 0, 'last_tick': None,
            }

        # Every image failed to download: try again next run, but not forever.
        if failed:
            self._failures[eid] = self._failures.get(eid, 0) + 1
            if self._failures[eid] >= 3:
                self._seen_events[eid] = ev['created_at']
                self._failures.pop(eid, None)
        else:
            self._seen_events[eid] = ev['created_at']
        return None

    def _prune_unfollowed(self, followed):
        for key in [k for k, p in self._pool.items() if p['pubkey'] not in followed]:
            del self._pool[key]
        if self._sample and self._sample['pubkey'] not in followed:
            self._sample = None
        for pk in list(self._cursors):
            if pk not in followed:
                del self._cursors[pk]
        state = _load_json(_STATE_PATH, {})
        profiles = state.get('profiles', {})
        gone = [pk for pk in profiles if pk not in followed]
        if gone:
            for pk in gone:
                del profiles[pk]
            atomic_write_json(_STATE_PATH, state, ensure_ascii=False)
        if os.path.isdir(AVATAR_DIR):
            for name in os.listdir(AVATAR_DIR):
                if os.path.splitext(name)[0] not in followed:
                    try:
                        os.remove(os.path.join(AVATAR_DIR, name))
                    except OSError:
                        pass

    def clear(self):
        """Everything: pool, profiles, avatars, cards. For the factory reset."""
        with self.lock:
            self._pool.clear()
            self._sample = None
            self._cursors.clear()
            self._seen_events.clear()
            self._recent_hashes.clear()
            self._preview_cache.clear()
            for path in (NOSTR_DIR, CARD_DIR, _LEGACY_DIR):
                shutil.rmtree(path, ignore_errors=True)

    # -- profiles -------------------------------------------------------

    def _apply_profiles(self, events, wanted, profiles, config, avatars=True):
        """Fold the newest signed kind-0 of each wanted author into profiles.

        With avatars, also download the profile picture when it changed;
        without, a changed picture only drops the stale copy, and
        _fill_avatars() fetches the new one when its turn comes.
        """
        newest = {}
        for ev in events:
            pk, kind = ev.get('pubkey'), ev.get('kind')
            if (pk in wanted and kind in (0, 10002)
                    and ev.get('created_at', 0) > newest.get((pk, kind), {}).get('created_at', -1)):
                newest[(pk, kind)] = ev
        for (pk, kind), ev in newest.items():
            known = profiles.get(pk, {})
            if kind == 10002:
                # Where the account publishes: used to find its posts.
                if known.get('relays_updated', -1) < ev['created_at'] and verify_event(ev):
                    profiles[pk] = {**known, 'relays': _write_relays(ev),
                                    'relays_updated': ev['created_at']}
                continue
            if known.get('updated', -1) >= ev['created_at'] and (self._avatar_path(pk) or not avatars):
                continue
            if not verify_event(ev):
                continue
            try:
                meta = json.loads(ev.get('content') or '{}')
            except ValueError:
                continue
            if not isinstance(meta, dict):
                continue
            name = _name_of(meta)
            picture = str(meta.get('picture') or '').strip()
            entry = {**known, 'name': name, 'picture': picture, 'updated': ev['created_at']}
            changed = picture != known.get('picture')
            if avatars and ((picture and changed) or not self._avatar_path(pk)):
                self._save_avatar(pk, picture, config)
            elif changed and self._avatar_path(pk):
                try:
                    os.remove(self._avatar_path(pk))
                except OSError:
                    pass
            profiles[pk] = entry

    def _names_from_own_relays(self, pubkeys, profiles, config):
        """Second pass for accounts still without a name: ask the relays their
        own relay list names. An indexer knows only part of the network, and
        a profile published only to its author's relays is found nowhere else.
        """
        by_relay = {}
        for pk in pubkeys:
            entry = profiles.get(pk, {})
            if entry.get('name'):
                continue
            for relay in entry.get('relays', []):
                by_relay.setdefault(relay, []).append(pk)
        if not by_relay:
            return
        busiest = sorted(by_relay, key=lambda r: -len(by_relay[r]))[:_MAX_OUTBOX_RELAYS * 2]
        extra = {}
        for relay in busiest:
            extra[relay] = [dict(f, limit=len(f['authors']))
                            for f in _author_filters(by_relay[relay], kinds=[0])]
        events, _ = query_relays([], [], config, extra=extra)
        self._apply_profiles(events, set(pubkeys), profiles, config, avatars=False)

    def _fill_avatars(self, pubkeys, profiles, config, budget):
        """Download up to budget missing avatars, in the order given."""
        for pk in pubkeys:
            if budget <= 0:
                return
            picture = profiles.get(pk, {}).get('picture')
            if picture and not self._avatar_path(pk):
                self._save_avatar(pk, picture, config)
                budget -= 1

    def follows_of(self, pubkey, config):
        """The accounts pubkey follows, from its newest signed contact list
        (NIP-02, kind 3), with their names looked up in bulk.

        Returns (list of {'pubkey', 'npub', 'name', 'avatar'}, error or None).
        Names are stored like any other profile, so the rows the page adds for
        them do not each ask the relays again. Avatars are left to the fetch.
        """
        relays = _profile_relays(config)
        events, errors = query_relays(relays, [{'kinds': [3], 'authors': [pubkey], 'limit': 5}], config)
        lists = sorted((e for e in events if e.get('kind') == 3 and e.get('pubkey') == pubkey),
                       key=lambda e: -e.get('created_at', 0))
        contact_list = next((e for e in lists if verify_event(e)), None)
        if contact_list is None:
            if len(errors) == len(relays):
                return [], 'No relay could be reached'
            return [], 'No follow list found for this account'

        follows = []
        for tag in contact_list.get('tags', []):
            if (isinstance(tag, list) and len(tag) >= 2 and tag[0] == 'p'
                    and isinstance(tag[1], str) and re.fullmatch(r'[0-9a-f]{64}', tag[1])
                    and tag[1] != pubkey and tag[1] not in follows):
                follows.append(tag[1])

        profiles = self._profiles()
        missing = [pk for pk in follows if pk not in profiles]
        if missing:
            events, _ = query_relays(relays, _profile_filters(missing), config)
            with self.lock:
                state = _load_json(_STATE_PATH, {})
                profiles = state.setdefault('profiles', {})
                self._apply_profiles(events, set(missing), profiles, config, avatars=False)
                self._names_from_own_relays(missing, profiles, config)
                # Remembered even without a profile, so the page does not ask
                # the relays once per row for accounts that have none.
                now = int(time.time())
                for pk in missing:
                    profiles.setdefault(pk, {'name': '', 'picture': '', 'updated': 0})['checked'] = now
                os.makedirs(NOSTR_DIR, exist_ok=True)
                atomic_write_json(_STATE_PATH, state, ensure_ascii=False)
        return [{'pubkey': pk, 'npub': npub(pk), 'name': profiles.get(pk, {}).get('name', ''),
                 'avatar': bool(self._avatar_path(pk))} for pk in follows], None

    @staticmethod
    def _avatar_path(pubkey):
        path = os.path.join(AVATAR_DIR, f'{pubkey}.jpg')
        return path if os.path.exists(path) else None

    @staticmethod
    def _save_avatar(pubkey, url, config):
        """Store a small copy of the profile picture, so neither the card nor
        the settings page has to reach the image host each time."""
        if not url or not url.lower().startswith(('http://', 'https://')) or _is_private_host(url):
            return
        try:
            img = Image.open(io.BytesIO(_download(url, config)))
            img.seek(0)
            img = ImageOps.fit(ImageOps.exif_transpose(img).convert('RGB'), (128, 128), Image.LANCZOS)
            os.makedirs(AVATAR_DIR, exist_ok=True)
            img.save(os.path.join(AVATAR_DIR, f'{pubkey}.jpg'), 'JPEG', quality=88)
        except Exception as e:
            print(f'⚠️ Nostr: could not fetch avatar for {pubkey[:12]}: {e}')

    @staticmethod
    def _profiles():
        return _load_json(_STATE_PATH, {}).get('profiles', {})

    def resolve_profile(self, pubkey, config):
        """Name and avatar of one account, asking the relays if not yet known.

        For the settings page, which shows who an npub is as soon as it is
        typed in. Returns {'name', 'npub', 'avatar'}; avatar is a bool.
        """
        profiles = self._profiles()
        known = profiles.get(pubkey)
        now = int(time.time())
        if known is None or (not known.get('name')
                             and now - known.get('checked', 0) > _NO_PROFILE_RETRY):
            events, _ = query_relays(_profile_relays(config),
                                     [{'kinds': [0, 10002], 'authors': [pubkey], 'limit': 5}], config)
            with self.lock:
                state = _load_json(_STATE_PATH, {})
                profiles = state.setdefault('profiles', {})
                self._apply_profiles(events, {pubkey}, profiles, config)
                if not profiles.get(pubkey, {}).get('name'):
                    self._names_from_own_relays([pubkey], profiles, config)
                    if profiles.get(pubkey, {}).get('name') and not self._avatar_path(pubkey):
                        self._save_avatar(pubkey, profiles[pubkey].get('picture'), config)
                # Recorded either way: a key with no profile anywhere is not
                # looked up again on every page load.
                profiles.setdefault(pubkey, {'name': '', 'picture': '', 'updated': 0})['checked'] = now
                os.makedirs(NOSTR_DIR, exist_ok=True)
                atomic_write_json(_STATE_PATH, state, ensure_ascii=False)
        p = profiles.get(pubkey, {})
        return {'name': p.get('name', ''), 'npub': npub(pubkey),
                'avatar': bool(self._avatar_path(pubkey))}


def _post_text(content, urls):
    from lib.nostr_card import post_text
    return post_text(content, urls)


_store = None
_store_lock = threading.Lock()


def get_store():
    global _store
    with _store_lock:
        if _store is None:
            _store = NostrPostStore()
        return _store
