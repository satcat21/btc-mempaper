#!/usr/bin/env python3
"""Meme sync against einundzwanzig-memes.space.

One file, because it is deployed as one thing: the weekly crontab entry names
this path, the "Sync now" button in the web UI runs the same command, and both
now get the whole implementation rather than a stub that delegated to two
untracked modules and failed on machines that did not happen to have them.

It has two halves. The first is a client for the site's API - search, tags,
newest, per-meme lookup, with Tor support and a shared rate limiter. The second
is the downloader built on it: a full catalogue crawl by tag, an incremental
update against /newest, resumable state, and the index the renderer reads.

Command line, which routes/updates.py depends on:

  --update   Download whatever is missing. Streams progress to stdout, one line
             at a time, and the web UI shows those lines as they arrive. A
             non-zero exit is reported as a failed sync.
  --deep     With --update: enumerate the whole catalogue by tag instead of
             reading /newest, which only ever returns the latest fifty.
  --status   Print exactly one word as the last line of stdout - idle, running,
             paused or done. Anything but "idle" makes the web UI show a sync
             as being in progress.
  --stop     Ask a running sync to stop after the current page, and exit 0.
  --tor      Route everything through the local SOCKS proxy.

Unknown flags are accepted and ignored, so a crontab written by an older or
newer release does not become a weekly failure email.

Output carries emoji and typographic dashes, so main() re-encodes stdout and
stderr with errors="replace" before printing anything. Under cron the locale is
whatever the system defaults to and is often plain ASCII, where the first such
print would otherwise raise UnicodeEncodeError - see
_make_output_encoding_safe().

    .venv/bin/python tools/sync_memes.py --update [--deep] [--tor]
    .venv/bin/python tools/sync_memes.py --status
    .venv/bin/python tools/sync_memes.py --stop
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor, wait as _fut_wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import argparse
import http.client
import json
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ===========================================================================
# API client for einundzwanzig-memes.space
# ===========================================================================

BASE_URL = "https://einundzwanzig-memes.space"
API_BASE = f"{BASE_URL}/api/v1"

# ---------------------------------------------------------------------------
# Proxy / Tor support
# ---------------------------------------------------------------------------

_original_socket_class = None  # saved so reset_proxy() can restore it
_proxy_active = False          # True while requests are routed through SOCKS
_proxy_endpoint: tuple[str, int] | None = None

# Timeouts, direct and over Tor. A Tor request pays for a three-hop circuit
# before a single byte of HTTP moves, and on a Pi Zero building that circuit
# from cold regularly takes longer than the direct-connection timeout allows.
# Ten seconds was enough to fail the SOCKS5 handshake itself — the negotiation
# read timed out mid-reply, every retry re-paid the same cost, and the run died
# with five identical timeouts before Tor had finished bootstrapping once.
API_TIMEOUT_DIRECT = 10
API_TIMEOUT_TOR = 60
IMAGE_TIMEOUT_DIRECT = 15
IMAGE_TIMEOUT_TOR = 90


def _resolve_timeout(explicit: Optional[int], direct: int, over_tor: int) -> int:
    """Pick the timeout for a request: caller's value wins, else proxy-aware."""
    if explicit is not None:
        return explicit
    return over_tor if _proxy_active else direct


def _transient_errors() -> tuple:
    """Exception types worth retrying, including the SOCKS ones when present.

    PySocks raises its own errors rather than the socket ones. Most surface
    already wrapped in URLError, because they happen inside urllib's do_open —
    but not all of them do, and an unwrapped ProxyError escaping a retry loop
    ends the whole run over what is usually a circuit that needed another try.
    """
    base = (urllib.error.URLError, TimeoutError,
            http.client.RemoteDisconnected, ConnectionResetError)
    try:
        import socks
        return base + (socks.ProxyError,)
    except ImportError:
        return base


def configure_proxy(host: str = "127.0.0.1", port: int = 9050) -> bool:
    """Route all outgoing requests through a SOCKS5 proxy (e.g. Tor).

    Must be called before any network request is made.
    Requires PySocks:  pip install PySocks

    Returns True when the proxy is configured, False when PySocks is missing.
    Configuring the proxy does not mean Tor can reach anything yet — call
    wait_for_proxy() before the first real request to find that out cheaply.
    """
    global _original_socket_class, _proxy_active, _proxy_endpoint
    try:
        import socks
        import socket
        if _original_socket_class is None:
            _original_socket_class = socket.socket  # save for reset
        socks.set_default_proxy(socks.SOCKS5, host, port)
        socket.socket = socks.socksocket
        _proxy_active = True
        _proxy_endpoint = (host, port)
        return True
    except ImportError:
        return False


def wait_for_proxy(host: str = "einundzwanzig-memes.space", port: int = 443,
                   deadline: int = 240, verbose: bool = True) -> bool:
    """Block until the proxy can actually open a circuit to *host*, or give up.

    This exists because "the SOCKS port accepts connections" and "Tor can carry
    traffic" are different states, and only the second one is useful. A weekly
    cron run that fires shortly after boot hits the gap between them: tor is
    listening, the connect succeeds, and then the SOCKS5 negotiation stalls
    waiting for a circuit that is still being built.

    Spending that wait here rather than in the API retry loop is what makes it
    survivable. The retry loop re-pays the request timeout on every attempt and
    then fails the run; this probe is one cheap connection, retried against a
    deadline, and it reports what it is waiting for instead of printing the same
    timeout five times.

    Returns True once a circuit is up, False if the deadline passes — the caller
    decides whether that is fatal, because a slow circuit here does not
    guarantee the real request will fail.
    """
    if not _proxy_active:
        return True

    import socket as _socket

    started = time.monotonic()
    attempt = 0
    last_error: Optional[BaseException] = None
    while time.monotonic() - started < deadline:
        attempt += 1
        try:
            # socket.socket is already the SOCKS class, so this connection is
            # the same path a real request takes — including circuit building.
            with _socket.create_connection((host, port), timeout=30):
                if verbose and attempt > 1:
                    waited = int(time.monotonic() - started)
                    print(f"🧅 Tor circuit ready after {waited}s", file=sys.stderr)
                return True
        except Exception as exc:  # noqa: BLE001 - probe reports, never raises
            last_error = exc
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0:
                break
            if verbose:
                print(f"  [tor] waiting for a circuit ({attempt}) — {exc!s:.60}",
                      file=sys.stderr)
            sleep_for = min(5, remaining)
            if _stop_event is not None:
                if _stop_event.wait(sleep_for):
                    return False
            else:
                time.sleep(sleep_for)

    if verbose:
        print(f"⚠️  Tor did not produce a working circuit within {deadline}s "
              f"(last error: {last_error!s:.80})", file=sys.stderr)
    return False


def reset_proxy() -> None:
    """Restore direct (non-proxied) socket connections."""
    global _original_socket_class, _proxy_active, _proxy_endpoint
    if _original_socket_class is not None:
        import socket
        socket.socket = _original_socket_class
        _original_socket_class = None
    _proxy_active = False
    _proxy_endpoint = None

# ---------------------------------------------------------------------------
# Fallback query list used only when the live /api/v1/templates endpoint
# cannot be reached.  collect_all_ids() fetches the real template list first
# and only falls back to this if the request fails.
# These are verified template names from the API (photo_macro, wojak, etc.)
# plus a handful of broad topic terms.
# ---------------------------------------------------------------------------
BROAD_QUERIES: list[str] = [
    "photo_macro",
    "multi_panel_comic",
    "comparison",
    "wojak",
    "tweet_screenshot",
    "chart_meme",
    "reaction_image",
    "quote_image",
    "product_parody",
    "change_my_mind",
    "distracted_boyfriend",
    "drake",
    "expanding_brain",
    "bitcoin",
    "hodl",
    "inflation",
    "bank",
    "fiat",
    "lightning",
    "mining",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Meme:
    """A single meme returned by the API."""
    id: str
    description_de: Optional[str]
    description_en: Optional[str]
    ocr_text: Optional[str]
    meme_template: Optional[str]
    sentiment: Optional[str]
    humor_type: Optional[str]
    tags: list[str]
    width: int
    height: int
    format: str
    is_nsfw: bool
    upvotes: int
    downvotes: int
    source: Optional[str]
    indexed_at: Optional[str]

    # Constructed from the id — the /images/medium/ static path always returns
    # 200 externally, while /api/v1/images/full/ returns 404.
    image_url: str = field(init=False)
    thumb_url: str = field(init=False)

    def __post_init__(self) -> None:
        self.image_url = image_url(self.id)
        self.thumb_url = f"{API_BASE}/images/thumb/{self.id}"

    def download(self, timeout: Optional[int] = None) -> bytes:
        """Return the raw image bytes of the full-size meme."""
        return fetch_image_bytes(self.image_url, timeout=timeout)

    def download_thumb(self, timeout: Optional[int] = None) -> bytes:
        """Return the raw image bytes of the thumbnail."""
        return fetch_image_bytes(self.thumb_url, timeout=timeout)

    def __str__(self) -> str:
        return (
            f"Meme(id={self.id!r}, template={self.meme_template!r}, "
            f"sentiment={self.sentiment!r})"
        )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def image_url(meme_id: str) -> str:
    """Return the full-size image URL for a meme ID.

    The /images/medium/ static path always returns 200 externally;
    the /api/v1/images/full/ path returns 404, so we use the static path.
    """
    return f"{BASE_URL}/images/medium/{meme_id}.webp"


def fetch_image_bytes(url: str, timeout: Optional[int] = None) -> bytes:
    """Download raw image bytes from *url*, retrying up to 3 times.

    Uses the same global rate limiter as _request() since both hit the same
    host, preventing connection-refused cascades from concurrent downloads.

    timeout defaults to the proxy-aware value; image bodies are larger than API
    responses, so the Tor allowance here is correspondingly longer.
    """
    global _last_request_time
    timeout = _resolve_timeout(timeout, IMAGE_TIMEOUT_DIRECT, IMAGE_TIMEOUT_TOR)
    with _rate_lock:
        now = time.monotonic()
        scheduled = max(now, _last_request_time + _MIN_REQUEST_INTERVAL * _rate_backoff)
        _last_request_time = scheduled
        wait = scheduled - now
    if wait > 0:
        if _stop_event is not None and _stop_event.wait(wait):
            raise RuntimeError("Stopped")
        elif _stop_event is None:
            time.sleep(wait)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "einundzwanzig-memes-python/1.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except _transient_errors() as exc:
            # Errno 104 (connection reset) and the SOCKS proxy errors were not
            # caught here, only in _request. A reset mid-image — routine on a
            # Tor exit — therefore killed the whole run instead of costing one
            # retry, after the API half had already survived the same error.
            if attempt == 2:
                raise RuntimeError(f"Download failed for {url}: {exc}") from exc
            wait = (2 ** attempt) if _proxy_active else (1.5 ** attempt)
            if _stop_event is not None:
                if _stop_event.wait(wait):
                    raise RuntimeError("Stopped") from exc
            else:
                time.sleep(wait)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Global rate limiter — enforces a minimum gap between any two API requests
# regardless of how many worker threads are running.  Prevents HTTP 429s.
_rate_lock = threading.Lock()
_last_request_time: float = 0.0
_MIN_REQUEST_INTERVAL = 1.5  # base seconds between requests (~0.67 req/s)
_rate_backoff: float = 1.0   # dynamic multiplier; doubles on HTTP 429, recovers on success
_MAX_BACKOFF: float = 8.0    # cap at 8× = one request per 12 s

# Set by the caller (e.g. download_all_memes.py) so retry sleeps can be
# interrupted immediately when the user presses Ctrl+C.
_stop_event: threading.Event | None = None


def _request(path: str, timeout: Optional[int] = None) -> dict:
    """Fetch JSON from the API, retrying up to 5 times on transient errors.

    DNS failures (Errno -3) get a longer back-off (30 s) so a temporary
    network hiccup on a Pi doesn't permanently skip queries.

    A global rate limiter ensures at most ~3 requests/s across all threads,
    which avoids HTTP 429 responses from the server.

    timeout defaults to the proxy-aware value: a Tor request gets substantially
    longer than a direct one, because the circuit is built inside that window.
    """
    global _last_request_time, _rate_backoff
    timeout = _resolve_timeout(timeout, API_TIMEOUT_DIRECT, API_TIMEOUT_TOR)
    with _rate_lock:
        now = time.monotonic()
        scheduled = max(now, _last_request_time + _MIN_REQUEST_INTERVAL * _rate_backoff)
        _last_request_time = scheduled
        wait = scheduled - now
    if wait > 0:
        if _stop_event is not None and _stop_event.wait(wait):
            raise RuntimeError("Stopped")
        elif _stop_event is None:
            time.sleep(wait)

    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "einundzwanzig-memes-python/1.0"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            # Successful response — slowly recover the backoff toward 1.0
            with _rate_lock:
                if _rate_backoff > 1.0:
                    _rate_backoff = max(1.0, _rate_backoff * 0.95)
            return json.loads(raw.decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                with _rate_lock:
                    _rate_backoff = min(_rate_backoff * 2, _MAX_BACKOFF)
                    effective = _MIN_REQUEST_INTERVAL * _rate_backoff
                print(
                    f"  [429] rate limit — interval→{effective:.2f}s, pausing 60s …",
                    file=sys.stderr,
                )
                if _stop_event is not None:
                    if _stop_event.wait(60):
                        raise RuntimeError("Stopped") from exc
                else:
                    time.sleep(60)
                continue
            raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
        except _transient_errors() as exc:
            if attempt == 4:
                raise RuntimeError(f"Network error fetching {url}: {exc}") from exc
            # DNS failure → long back-off; remote-disconnect → short back-off.
            # Over Tor a timeout usually means the circuit is still being built,
            # so back off further rather than hammering a half-open connection.
            is_dns = "Name or service not known" in str(exc) or "Errno -3" in str(exc)
            if is_dns:
                wait = 30
            elif _proxy_active:
                wait = min(30, 5 * 2 ** attempt)
            else:
                wait = 2 ** attempt
            print(f"  [retry {attempt+1}/5] {exc!s:.80}  waiting {wait}s…", file=sys.stderr)
            if _stop_event is not None:
                if _stop_event.wait(wait):
                    raise RuntimeError("Stopped") from exc
            else:
                time.sleep(wait)


def _parse_meme(data: dict) -> Meme:
    return Meme(
        id=data["id"],
        description_de=data.get("description_de"),
        description_en=data.get("description_en"),
        ocr_text=data.get("ocr_text"),
        meme_template=data.get("meme_template"),
        sentiment=data.get("sentiment"),
        humor_type=data.get("humor_type"),
        tags=data.get("tags") or [],
        width=data.get("width", 0),
        height=data.get("height", 0),
        format=data.get("format", ""),
        is_nsfw=data.get("is_nsfw", False),
        upvotes=data.get("upvotes", 0),
        downvotes=data.get("downvotes", 0),
        source=data.get("source"),
        indexed_at=data.get("indexed_at"),
    )



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_random_meme(timeout: Optional[int] = None) -> Meme:
    """Fetch a single random meme."""
    results = get_random_memes(count=1, timeout=timeout)
    if not results:
        raise RuntimeError("API returned no memes")
    return results[0]


def get_random_memes(count: int = 5, timeout: Optional[int] = None) -> list[Meme]:
    """Fetch *count* random memes in a single request (1–50 recommended)."""
    data = _request(f"/random?count={count}&full=true", timeout=timeout)
    return [_parse_meme(m) for m in data.get("results", [])]


def search_memes(query: str, limit: int = 10, timeout: Optional[int] = None) -> list[Meme]:
    """Search the meme collection by text (semantic + OCR search)."""
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    data = _request(f"/search?{params}", timeout=timeout)
    return [_parse_meme(m) for m in data.get("results", [])]


def collect_all_ids(
    page_size: int = 50,
    verbose: bool = True,
    on_progress: callable = None,
    on_new_meme: callable = None,
    workers: int = 4,
    max_zero_pages: int = 0,
    state_dir: str = None,
    stop_event: threading.Event = None,
) -> dict[str, dict]:
    """
    Collect unique meme metadata for the full catalogue.

    Strategy
    --------
    Uses the real tag list from /api/v1/tags (~5 800 tags) as semantic search
    queries.  Each tag is a term that memes are actually described/tagged with,
    so querying every tag via /search?q=TAG with cursor pagination covers the
    full catalogue deterministically — unlike /random (server-cached, always
    returns the same 50 memes) or filter_template/filter_tag (capped at 100).

    For incremental updates (e.g. "5 new memes added") use get_new_meme_ids()
    instead — it checks /newest?count=50 against existing files on disk.

    Parameters
    ----------
    page_size : int
        Results per search page (max 50).
    verbose : bool
    on_progress : callable
        Called as on_progress(tag, page, new_count, total_unique).
    on_new_meme : callable
        Called as on_new_meme(meme_dict) for each newly discovered meme,
        from a worker thread.  Useful for streaming downloads in parallel.
    workers : int
        Number of tags to search in parallel (default 4).
    max_zero_pages : int
        Stop paginating a tag after this many consecutive pages with 0 new
        memes.  Set to 0 to disable early termination.
    state_dir : str
        Directory for persistent resume state.  Two files are maintained:
          _state_tags.txt   – completed tag names, one per line (append-only)
          _state_memes.jsonl – discovered meme metadata, one JSON per line
        On next run, completed tags are skipped and previously discovered
        memes are pre-loaded.  Pass None to disable caching.
    stop_event : threading.Event
        When set, each search worker stops after its current page and exits.

    Returns
    -------
    dict[str, dict]
        Mapping of meme UUID → raw API metadata dict.
    """
    all_memes: dict[str, dict] = {}
    lock = threading.Lock()        # protects all_memes dict
    file_lock = threading.Lock()   # serialises state-file writes
    tags_done = [0]

    # ── Load resume state ────────────────────────────────────────────────
    completed_tags: set[str] = set()
    _tags_file: Path | None = None
    _memes_file: Path | None = None

    if state_dir:
        _sd = Path(state_dir)
        _tags_file = _sd / "_state_tags.txt"
        _memes_file = _sd / "_state_memes.jsonl"

        if _tags_file.exists():
            for line in _tags_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    completed_tags.add(line)

        if _memes_file.exists():
            for line in _memes_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    meme = json.loads(line)
                    uid = meme.get("id")
                    if uid:
                        all_memes[uid] = meme
                except json.JSONDecodeError:
                    pass

        if verbose and (completed_tags or all_memes):
            print(
                f"  [resume] {len(completed_tags)} completed tags  "
                f"{len(all_memes)} memes already discovered"
            )

    # ── Fetch tag list and filter out already-completed tags ─────────────
    try:
        tags = get_tags()
        tag_names = [t["name"] for t in tags if t.get("name")]
    except Exception as exc:
        print(f"  [warn] could not fetch tag list ({exc}), falling back to BROAD_QUERIES", file=sys.stderr)
        tag_names = BROAD_QUERIES

    if completed_tags:
        original_count = len(tag_names)
        tag_names = [t for t in tag_names if t not in completed_tags]
        if verbose:
            print(
                f"  [resume] skipping {original_count - len(tag_names)} completed tags — "
                f"{len(tag_names)} remaining"
            )

    n_tags = len(tag_names)
    if verbose:
        print(
            f"  [collect_all_ids] {n_tags} tags — "
            f"workers={workers}  max_zero_pages={max_zero_pages} …"
        )

    def _search_tag(idx_tag: tuple[int, str]) -> None:
        i, tag = idx_tag
        cursor: str | None = None
        page = 0
        tag_retries = 0
        zero_streak = 0
        tag_new_total = 0    # new memes found across all pages for this tag
        tag_found_total = 0  # all results seen for this tag (new + already known)
        last_total = 0       # global total after this tag finishes

        while True:
            if stop_event and stop_event.is_set():
                break

            params = {"q": tag, "limit": str(page_size)}
            if cursor:
                params["cursor"] = cursor
            try:
                data = _request("/search?" + urllib.parse.urlencode(params))
                tag_retries = 0
            except RuntimeError as exc:
                if tag_retries < 2:
                    tag_retries += 1
                    print(
                        f"  [warn] tag={tag!r} page={page}: {exc}"
                        f"  — retrying in 60s ({tag_retries}/2)", file=sys.stderr
                    )
                    if stop_event and stop_event.wait(60):
                        break
                    continue
                print(f"  [skip] tag={tag!r}: giving up after repeated failures", file=sys.stderr)
                break

            results = data.get("results", [])
            if not results:
                break

            new_count = 0
            new_memes: list[dict] = []
            with lock:
                for meme in results:
                    uid = meme["id"]
                    if uid not in all_memes:
                        all_memes[uid] = meme
                        new_count += 1
                        new_memes.append(meme)
                last_total = len(all_memes)

            tag_found_total += len(results)

            # Persist new memes and notify caller — both outside the main lock
            if new_memes:
                if _memes_file:
                    with file_lock:
                        with open(_memes_file, "a", encoding="utf-8") as f:
                            for meme in new_memes:
                                f.write(json.dumps(meme, ensure_ascii=False) + "\n")
                if on_new_meme:
                    for meme in new_memes:
                        on_new_meme(meme)

            cursor = data.get("next_cursor")
            page += 1
            tag_new_total += new_count

            if new_count > 0:
                zero_streak = 0
            else:
                zero_streak += 1

            if on_progress:
                on_progress(tag, page, new_count, last_total)

            if max_zero_pages > 0 and zero_streak >= max_zero_pages:
                break

            if not cursor:
                break
            time.sleep(0.05)

        # Only mark the tag as completed if we weren't stopped mid-scan
        was_stopped = stop_event and stop_event.is_set()

        if verbose:
            if tag_new_total > 0:
                print(
                    f"  tag {i:4d}/{n_tags} {tag!r:35s}  "
                    f"pages={page}  images={tag_found_total:4d}  new={tag_new_total:3d}  total={last_total:5d}"
                    + ("  [stopped]" if was_stopped else "")
                )
            else:
                print(
                    f"  tag {i:4d}/{n_tags} {tag!r:35s}  "
                    f"pages={page}  images={tag_found_total:4d}  new=  0  (no new images)"
                    + ("  [stopped]" if was_stopped else "")
                )

        with lock:
            tags_done[0] += 1

        if not was_stopped and _tags_file:
            with file_lock:
                with open(_tags_file, "a", encoding="utf-8") as f:
                    f.write(tag + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_search_tag, enumerate(tag_names, 1)))

    return all_memes


def get_new_memes(memes_dir: str, verbose: bool = True,
                  deep: bool = False) -> list[dict]:
    """
    Return metadata for memes on the site that are not yet in *memes_dir*.

    Full records, not just UUIDs.  /newest?full=true already carries tags,
    descriptions and OCR text, and the renderer needs them: it builds its
    metadata map from index.jsonl, so a meme whose image was downloaded without
    its record is invisible to holiday and tag matching however good the picture
    is.  Discarding what the response already contained was the whole bug.

    /newest returns the latest 50 and nothing more: its response carries only
    {count, results} — there is no cursor to follow, and count is capped server
    side.  So this sees the newest 50 and cannot see past them, however the loop
    is written.  That is fine for a daily or weekly check and useless for
    anything else: if more than 50 memes appear between two runs, the surplus is
    invisible here for good.

    Pass deep=True for that case.  It ignores /newest and walks the tag
    traversal instead — /search?q=TAG over the real tag list, which is the only
    enumeration that reaches the whole catalogue, and the one that built the
    local collection in the first place.  Slow, and the only thing that closes a
    gap once one exists.

    Parameters
    ----------
    memes_dir : str
        Path to the local memes directory (e.g. "static/memes").
    verbose : bool
    deep : bool
        Enumerate the whole catalogue by tag rather than reading /newest.
        Minutes rather than seconds, and the only way to find memes that are
        older than the latest fifty.

    Returns
    -------
    list[dict]
        Metadata for memes that exist on the site but not on disk.
    """
    existing = {
        f.stem for f in Path(memes_dir).glob("*.webp")
        if not f.name.startswith("_")
    }

    if deep:
        if verbose:
            print("  [get_new_meme_ids] deep scan: enumerating every tag, "
                  "this takes a while")
        catalogue = collect_all_ids(verbose=verbose, state_dir=memes_dir)
        missing = [meme for uid, meme in catalogue.items() if uid not in existing]
        if verbose:
            print(
                f"  [get_new_meme_ids] catalogue={len(catalogue)}"
                f"  on_disk={len(existing)}  missing={len(missing)}  (deep scan)"
            )
        return missing

    missing: list[dict] = []
    fetched = 0
    pages = 0
    cursor: str | None = None

    while True:
        params: dict[str, str] = {"count": "50", "full": "true"}
        if cursor:
            params["cursor"] = cursor
        data = _request("/newest?" + urllib.parse.urlencode(params))
        results = data.get("results", [])
        fetched += len(results)

        page_new = 0
        for meme in results:
            uid = meme["id"]
            if uid not in existing:
                missing.append(meme)
                page_new += 1

        cursor = data.get("next_cursor")
        pages += 1

        # /newest carries no cursor, so this exits after one page in practice.
        # The page_new test stays for the day the endpoint gains one: a page
        # where everything was already on disk means the overlap with the local
        # collection is solid, not merely touched, whereas one known meme among
        # forty-nine new ones is not a reason to stop.
        if not results or not cursor or page_new == 0:
            break

    # Every single one of the newest fifty being new means the window very
    # likely overflowed: the endpoint has no cursor, so whatever fell past
    # fiftieth place since the last run is not visible here and never will be.
    # Say so, rather than reporting fifty finds as though that were the whole
    # answer.
    if verbose and missing and len(missing) == fetched:
        print(
            "  [get_new_meme_ids] every one of the newest "
            f"{fetched} is new — more have probably been added than this "
            "endpoint can show. Run with --deep to enumerate the catalogue."
        )

    if verbose:
        print(
            f"  [get_new_meme_ids] pages={pages}  fetched={fetched}"
            f"  on_disk={len(existing)}  missing={len(missing)}"
            + ("  (deep scan)" if deep else "")
        )

    return missing


def get_new_meme_ids(memes_dir: str, verbose: bool = True,
                     deep: bool = False) -> list[str]:
    """UUIDs only, for callers that do not need the metadata."""
    return [m["id"] for m in get_new_memes(memes_dir, verbose=verbose, deep=deep)]


def get_stats(timeout: Optional[int] = None) -> dict:
    """Return site statistics (total memes, total searches, top queries)."""
    return _request("/stats", timeout=timeout)


def get_tags(timeout: Optional[int] = None) -> list[dict]:
    """Return all meme tags with their type (topic/crypto).

    Each entry: {"name": "bitcoin", "type": "topic"}
    The API returns all ~5800 tags in one response.
    """
    data = _request("/tags", timeout=timeout)
    return data.get("tags", [])


def download_meme(meme: Meme, path: str, use_thumb: bool = False, timeout: Optional[int] = None) -> str:
    """
    Download a meme image to disk.

    Parameters
    ----------
    meme : Meme
    path : str
        Destination file path, e.g. "my_meme.webp".
    use_thumb : bool
        If True, download the thumbnail instead of the full image.

    Returns
    -------
    str
        The path the file was written to.
    """
    image_bytes = meme.download_thumb(timeout) if use_thumb else meme.download(timeout)
    with open(path, "wb") as f:
        f.write(image_bytes)
    return path


# ---------------------------------------------------------------------------
# CLI demo  (python einundzwanzig_memes.py)
# ---------------------------------------------------------------------------


# ===========================================================================
# Downloader and command line
# ===========================================================================

# wait_for_proxy() is newer than the rest of this import. Neither this file nor
# einundzwanzig_memes.py is tracked by git (see .gitignore), so the two are
# copied between machines by hand and can arrive one at a time - and a missing
# name here is an ImportError at module load, which kills the run before any of
# its own error handling exists to explain it.
#
# The stub keeps the run alive on an older client, but says so every time rather
# than silently: without the real one, requests still use the direct-connection
# timeouts that were too short for a Tor circuit to finish its handshake, which
# is the failure this whole path was changed to fix.
try:
    from einundzwanzig_memes import wait_for_proxy
    _HAVE_PROXY_PROBE = True
except ImportError:
    _HAVE_PROXY_PROBE = False

    def wait_for_proxy(*_args, **_kwargs) -> bool:
        return True

_STATUS_FILE = "_state_status.txt"
_STOP_FILE = "_state_stop"

# Set once a bulk run has claimed the status file, so a failure path can release
# it again. None while no run owns it (--status, --stop and --update never do).
_status_out_dir: Path | None = None


# -------------------------------------------------------------------------
# Status helpers
# -------------------------------------------------------------------------

def read_status(out_dir: Path) -> str:
    f = out_dir / _STATUS_FILE
    return f.read_text(encoding="utf-8").strip() if f.exists() else "idle"


def write_status(out_dir: Path, status: str) -> None:
    (out_dir / _STATUS_FILE).write_text(status, encoding="utf-8")


# -------------------------------------------------------------------------
# Downloading
# -------------------------------------------------------------------------

def _make_output_encoding_safe() -> None:
    """Stop a decorative character from being what kills the run.

    This script prints emoji and typographic dashes throughout. Under a UTF-8
    locale that is fine; under cron's, which is whatever the system defaults to
    and is often plain ASCII, the first such print raises UnicodeEncodeError.
    The Tor banner is one of them, so the crash lands immediately after the
    proxy is configured and reads exactly like a Tor failure - a traceback
    through print(), on the line that announces Tor, in a job that was being
    debugged for Tor timeouts.

    Re-encoding the streams fixes every print at once, which rewriting the
    strings one at a time would not: the next contributor to add an emoji would
    reintroduce it. errors="replace" means an undisplayable character degrades
    to a placeholder instead of raising.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            # Redirected to something without reconfigure(); nothing to do, and
            # failing here would defeat the purpose.
            pass


def _download_one(uid: str, out_dir: Path) -> tuple[str, bool, str]:
    """Download a single meme image. Returns (id, success, error_msg)."""
    dest = out_dir / f"{uid}.webp"
    if dest.exists() and dest.stat().st_size > 0:
        return uid, True, "skipped"
    try:
        dest.write_bytes(fetch_image_bytes(image_url(uid)))
        return uid, True, ""
    except RuntimeError as exc:
        return uid, False, str(exc)


def _download_by_id(uid: str, out_dir: Path) -> tuple[str, bool, str]:
    """Download a meme by UUID only (used for --update mode)."""
    dest = out_dir / f"{uid}.webp"
    try:
        dest.write_bytes(fetch_image_bytes(image_url(uid)))
        return uid, True, ""
    except RuntimeError as exc:
        return uid, False, str(exc)


# -------------------------------------------------------------------------
# Index file (JSONL)
# -------------------------------------------------------------------------

def append_index(memes: list[dict], index_path: Path) -> int:
    """Add records to index.jsonl without disturbing what is already there.

    write_index() below rewrites the file from a full catalogue, which is right
    after a complete crawl and wrong after an incremental one - it would drop
    every meme this run did not look at. Appending is what an update needs.

    Records already present are skipped, so re-running after a partial failure
    does not duplicate lines.
    """
    known: set[str] = set()
    if index_path.exists():
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                try:
                    known.add(json.loads(line)["id"])
                except Exception:
                    continue

    added = 0
    with open(index_path, "a", encoding="utf-8") as f:
        for meme in memes:
            if meme["id"] in known:
                continue
            record = dict(meme)
            record["image_url"] = image_url(meme["id"])
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1
    return added


def write_index(memes: dict[str, dict], index_path: Path) -> None:
    """Write all meme metadata as newline-delimited JSON."""
    with open(index_path, "w", encoding="utf-8") as f:
        for meme in memes.values():
            record = dict(meme)
            record["image_url"] = image_url(meme["id"])
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Index written → {index_path}  ({len(memes)} entries)")


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main() -> None:
    # Before anything prints, including argparse's own error output.
    _make_output_encoding_safe()

    parser = argparse.ArgumentParser(
        description="Bulk-download all memes from einundzwanzig-memes.space"
    )
    parser.add_argument(
        "--out-dir", default="static/memes", help="Output directory (default: static/memes)"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Concurrent download threads (default: 1)"
    )
    parser.add_argument(
        "--search-workers", type=int, default=2,
        help="Parallel tag-search workers (default: 2)"
    )
    parser.add_argument(
        "--max-zero-pages", type=int, default=0,
        help="Stop paginating a tag after N consecutive pages with 0 new memes "
             "(default: 0 = disabled, full coverage)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Collect UUIDs and write index only — do not download images")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable resume cache — re-scan all tags from scratch")
    parser.add_argument("--deep", action="store_true",
                        help="with --update: enumerate the whole catalogue by tag "
                             "instead of reading /newest, which only ever returns "
                             "the latest 50. Slow, and the only way to find memes "
                             "older than those.")
    parser.add_argument("--update", action="store_true",
                        help="Fast mode: check /newest for memes not yet on disk")
    parser.add_argument("--status", action="store_true",
                        help="Print current download status (idle/running/paused/done) and exit")
    parser.add_argument("--stop", action="store_true",
                        help="Signal a running download to pause cleanly and exit")
    parser.add_argument("--tor", action="store_true",
                        help="Route all downloads through Tor via SOCKS5 (127.0.0.1:9050). "
                             "Requires Tor running and PySocks installed: pip install PySocks")
    # parse_known_args, not parse_args: a crontab written by another release
    # may pass a flag this version does not know, and rejecting it would turn
    # into a weekly failure email for an argument nobody needs.
    args, _unknown = parser.parse_known_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Tor proxy ─────────────────────────────────────────────────────────
    if args.tor:
        if configure_proxy():
            print("🧅 Tor proxy active — all requests route through socks5://127.0.0.1:9050")
            if not _HAVE_PROXY_PROBE:
                print("WARNING: tools/einundzwanzig_memes.py is older than this file.")
                print("   Missing wait_for_proxy(), so this run does not wait for a Tor")
                print("   circuit and still uses the short direct-connection timeouts.")
                print("   Expect the timeouts this was meant to fix. Copy the matching")
                print("   einundzwanzig_memes.py across - the two files travel together.")
            # Wait here rather than discovering it in the first API call. A
            # weekly cron run can fire while tor is still bootstrapping, and the
            # retry loop cannot tell "circuit not built yet" from "host is
            # down": it re-pays the request timeout five times and ends the run.
            # Not fatal on failure — a circuit that is merely slow to appear
            # often carries the request fine a moment later, and the retry loop
            # is still there to catch the case where it does not.
            if not wait_for_proxy():
                print("⚠️  Continuing anyway — the request retries may still succeed.")
        else:
            print("❌  PySocks not installed — cannot enable Tor proxy.")
            print("    Install with:  pip install PySocks")
            sys.exit(1)

    # ── Status query (for GUI polling) ────────────────────────────────────
    if args.status:
        print(read_status(out_dir))
        return

    # ── Stop signal (for GUI "Stop" button) ───────────────────────────────
    if args.stop:
        (out_dir / _STOP_FILE).touch()
        print("Stop signal sent. The running download will pause after the current page.")
        return

    state_dir = None if args.no_cache else str(out_dir)

    # ── Update mode: fast check for newly added memes ─────────────────────
    if args.update:
        print(f"\n{'='*60}")
        print("Update mode — checking for new memes …"
              + (" (deep scan — whole catalogue by tag)" if args.deep else ""))
        print(f"{'='*60}")
        new_memes = get_new_memes(str(out_dir), verbose=True, deep=args.deep)
        if not new_memes:
            print("No new memes found. Already up to date.")
            return
        print(f"\nDownloading {len(new_memes)} new meme(s) …")
        success = failed = 0
        downloaded: list[dict] = []
        for meme in new_memes:
            uid = meme["id"]
            _, ok, msg = _download_by_id(uid, out_dir)
            if ok:
                success += 1
                downloaded.append(meme)
                print(f"  ✓ {uid}")
            else:
                failed += 1
                print(f"  ✗ {uid}: {msg}")

        # The image alone is not enough. The renderer matches memes to holidays
        # and tags out of index.jsonl, so one that arrives without its record
        # can never be chosen - it is on the card and invisible to the display.
        # Recorded only for images that actually downloaded, so a failed fetch
        # does not leave a promise the directory cannot keep.
        if downloaded:
            added = append_index(downloaded, out_dir / "index.jsonl")
            print(f"Indexed {added} new meme(s) → {out_dir}/index.jsonl")

        print(f"\nDone.  Downloaded: {success}  Failed: {failed}")
        return

    # ── Bulk mode ─────────────────────────────────────────────────────────

    # Stop event: set by SIGINT, SIGTERM, or _state_stop sentinel file
    stop_event = threading.Event()

    def _on_signal(_signum, _frame):
        print("\n  Interrupt — stopping after current page …", flush=True)
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except (OSError, ValueError):
        pass  # SIGTERM not available on all platforms (e.g. Windows)

    # Share the stop event with the library so retry sleeps can be interrupted.
    globals()["_stop_event"] = stop_event

    # Background thread: watch for _state_stop sentinel file
    stop_file = out_dir / _STOP_FILE
    stop_file.unlink(missing_ok=True)   # clear any leftover from a previous run

    def _watch_stop_file():
        while not stop_event.is_set():
            if stop_file.exists():
                print("\n  [stop] Stop file detected — pausing …", flush=True)
                stop_event.set()
                break
            time.sleep(1.0)

    watcher = threading.Thread(target=_watch_stop_file, daemon=True)
    watcher.start()

    # Remembered so a crash can clear the status it is about to set. The status
    # file outlives the process, and every exit path below writes a terminal
    # value except the one nobody wrote: an unhandled network error left
    # "running" on disk permanently, and the web UI reads that file to decide
    # whether a sync is in progress. The result was a phantom run that no amount
    # of waiting cleared, because the process that would have cleared it had
    # died weeks earlier.
    global _status_out_dir
    _status_out_dir = out_dir
    write_status(out_dir, "running")

    index_path = out_dir / "index.jsonl"

    print(f"\n{'='*60}")
    print("Bulk download — discovery + download run in parallel")
    if state_dir:
        print(f"  Cache        : {out_dir}/_state_tags.txt  +  _state_memes.jsonl")
    print(f"  Search workers: {args.search_workers}   Download workers: {args.workers}")
    print(f"{'='*60}\n")

    if args.dry_run:
        all_memes = collect_all_ids(
            verbose=True,
            workers=args.search_workers,
            max_zero_pages=args.max_zero_pages,
            state_dir=state_dir,
            stop_event=stop_event,
        )
        print(f"\nDiscovered {len(all_memes)} unique memes.")
        write_index(all_memes, index_path)
        print("\n[dry-run] Skipping image downloads.")
        _finalise(out_dir, stop_event, state_dir)
        return

    # ── Parallel discovery + download ─────────────────────────────────────
    # _submit() is called from discovery worker threads for each new meme.
    # It checks disk first (filename = uuid.webp) — if the file already
    # exists, it skips without queuing any download task at all.

    download_futures: list = []
    futures_lock = threading.Lock()
    stats = {"success": 0, "skipped": 0, "failed": 0}
    stats_lock = threading.Lock()

    # Pre-load previously discovered memes from cache so that those not yet
    # on disk are re-queued immediately on startup.
    pre_discovered: dict[str, dict] = {}
    if state_dir:
        memes_file = Path(state_dir) / "_state_memes.jsonl"
        if memes_file.exists():
            for line in memes_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    meme = json.loads(line)
                    uid = meme.get("id")
                    if uid:
                        pre_discovered[uid] = meme
                except json.JSONDecodeError:
                    pass

    with ThreadPoolExecutor(max_workers=args.workers) as download_executor:

        def _submit(meme: dict) -> None:
            """Queue a meme for download — skip if already on disk or stopped."""
            if stop_event.is_set():
                return
            uid = meme["id"]
            dest = out_dir / f"{uid}.webp"
            if dest.exists() and dest.stat().st_size > 0:
                # File already present — no download needed.
                # (UUID filename match is sufficient; no API hash endpoint exists.)
                with stats_lock:
                    stats["skipped"] += 1
                return
            future = download_executor.submit(_download_one, uid, out_dir)
            with futures_lock:
                download_futures.append(future)

        # Re-queue previously discovered memes not yet on disk
        if pre_discovered:
            queued = 0
            for uid, meme in pre_discovered.items():
                dest = out_dir / f"{uid}.webp"
                if not (dest.exists() and dest.stat().st_size > 0):
                    _submit(meme)
                    queued += 1
            if queued:
                print(f"  Re-queued {queued} previously discovered memes not yet on disk.")

        # Run discovery — _submit is called in real-time for each new UUID
        all_memes = collect_all_ids(
            verbose=True,
            workers=args.search_workers,
            max_zero_pages=args.max_zero_pages,
            state_dir=state_dir,
            stop_event=stop_event,
            on_new_meme=_submit,
        )

        # Capture whether discovery finished cleanly BEFORE the drain phase,
        # so a stop triggered during drain doesn't suppress the cache cleanup.
        discovery_stopped = stop_event.is_set()

        print(f"\nDiscovery {'stopped' if discovery_stopped else 'done'} — "
              f"{len(all_memes)} unique memes total.")

        with futures_lock:
            total = len(download_futures)

        if total:
            print(f"Waiting for {total} download task(s) to finish …\n")

        done_count = 0
        remaining_futures = set(download_futures)
        while remaining_futures and not stop_event.is_set():
            done, remaining_futures = _fut_wait(
                remaining_futures, timeout=1.0, return_when=FIRST_COMPLETED
            )
            for future in done:
                uid, ok, msg = future.result()
                done_count += 1
                with stats_lock:
                    if not ok:
                        stats["failed"] += 1
                        print(f"  [FAIL] {uid}: {msg}")
                    elif msg == "skipped":
                        stats["skipped"] += 1
                    else:
                        stats["success"] += 1

                if done_count % 200 == 0 or done_count == total:
                    with stats_lock:
                        print(
                            f"  {done_count:>5}/{total}  "
                            f"✓ {stats['success']}  skip {stats['skipped']}  ✗ {stats['failed']}"
                        )

        # Cancel futures still waiting in the queue (not yet started) so the
        # executor shuts down immediately instead of running all 1500+ tasks.
        if stop_event.is_set():
            for f in remaining_futures:
                f.cancel()

    write_index(all_memes, index_path)

    # Signal watcher to exit cleanly
    stop_event.set()
    watcher.join(timeout=2)
    stop_file.unlink(missing_ok=True)

    print(f"\n{'='*60}")
    print(f"{'Paused' if discovery_stopped else 'Done'}.")
    print(f"  Downloaded : {stats['success']}")
    print(f"  Skipped    : {stats['skipped']}  (already on disk)")
    print(f"  Failed     : {stats['failed']}")
    print(f"  Index      : {index_path}")
    print(f"  Images     : {out_dir.resolve()}/")

    if discovery_stopped:
        print(f"\n  Progress saved. Run again to resume.")
        write_status(out_dir, "paused")
    else:
        # Full run completed — clear the tag cache so the next run re-scans
        # all tags to discover any newly added memes.
        # _state_memes.jsonl is kept so known UUIDs are not re-downloaded.
        if state_dir:
            tags_file = Path(state_dir) / "_state_tags.txt"
            tags_file.unlink(missing_ok=True)
            print(f"\n  Tag cache cleared — next run will re-scan for new memes.")
            print(f"  (Previously discovered UUIDs kept in _state_memes.jsonl)")
        write_status(out_dir, "done")

    print(f"{'='*60}\n")


def _finalise(out_dir: Path, stop_event: threading.Event, state_dir: str | None) -> None:
    """Write final status after a dry-run."""
    if stop_event.is_set():
        write_status(out_dir, "paused")
    else:
        if state_dir:
            (Path(state_dir) / "_state_tags.txt").unlink(missing_ok=True)
        write_status(out_dir, "done")


def _fail_network(exc: BaseException) -> None:
    """Report an unreachable API in a form worth finding in a weekly cron log.

    The API client raises RuntimeError once it has exhausted its retries, and
    nothing used to catch it. That turned an ordinary "the network was down on
    Thursday" into sixty lines of traceback through socks.py, http/client.py and
    urllib, ending in the one line that actually said anything. In a log nobody
    reads until something looks wrong, that is the difference between a
    diagnosis and an archaeology exercise.

    Deliberately plain ASCII. This is the path that runs when things are already
    broken, and an emoji here raises UnicodeEncodeError under a non-UTF-8 cron
    locale - making the error reporter the second thing to fail.
    """
    over_tor = globals().get("_proxy_active", False)
    print()
    print("ERROR: could not reach einundzwanzig-memes.space.")
    print(f"   {exc}")
    print()
    if over_tor:
        print("   Requests were routed through Tor (socks5://127.0.0.1:9050).")
        if _HAVE_PROXY_PROBE:
            print("   This run already waits for a circuit before its first request,")
            print("   so reaching this point usually means tor is not running at all")
            print("   rather than merely slow to bootstrap. Check, in this order:")
        else:
            print("   This run could NOT wait for a circuit - see the warning above,")
            print("   tools/einundzwanzig_memes.py is out of date. Update it first;")
            print("   a timeout here is the expected symptom. Then check:")
        print("     systemctl status tor")
        print("     ss -ltn | grep 9050")
        print("     journalctl -u tor --since -1h")
    else:
        print("   Check the device's internet connection and DNS resolution.")
        print("   If this device is meant to download over Tor, the --tor flag")
        print("   was not passed - the web UI setting is 'Route via Tor'.")
    print()
    print("   Nothing was downloaded. Progress is saved where applicable, and")
    print("   the next scheduled run resumes rather than starting over.")

    # Release the status file. "paused" rather than "idle" because the run is
    # resumable and its discovered-UUID cache survives - there is work
    # outstanding, and saying so is what a later --status is asked to report.
    if _status_out_dir is not None:
        try:
            write_status(_status_out_dir, "paused")
        except OSError as e:
            print(f"   (could not update the status file: {e})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except RuntimeError as exc:
        # "Stopped" is the cooperative stop path (the GUI button or the stop
        # sentinel file), not a failure - the downloader is resumable and has
        # already written its state, so this is a successful early exit.
        if str(exc) == "Stopped":
            print("\nStopped. The next run resumes where this one left off.")
            sys.exit(0)
        _fail_network(exc)
        sys.exit(2)