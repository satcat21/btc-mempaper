"""
einundzwanzig_memes.py
~~~~~~~~~~~~~~~~~~~~~~
Fetch Bitcoin memes from einundzwanzig-memes.space.

The site exposes an undocumented but stable REST API at /api/v1.
No authentication is required.

Quick start
-----------
    from einundzwanzig_memes import get_random_meme, get_random_memes, download_meme

    meme = get_random_meme()
    print(meme.description_en)
    print(meme.image_url)          # full .webp URL, always 200
    print(meme.thumb_url)          # thumbnail .webp URL

    # Download the image bytes directly
    image_bytes = meme.download()

    # Save to disk
    path = download_meme(meme, "meme.webp")

    # Fetch a batch
    memes = get_random_memes(count=5)

    # Bulk-discover meme IDs via search (used by download_all_memes.py)
    all_memes = collect_all_ids()
"""

from __future__ import annotations

import io
import json
import sys
import time
import threading
import http.client
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_URL = "https://einundzwanzig-memes.space"
API_BASE = f"{BASE_URL}/api/v1"

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

    def download(self, timeout: int = 15) -> bytes:
        """Return the raw image bytes of the full-size meme."""
        return fetch_image_bytes(self.image_url, timeout=timeout)

    def download_thumb(self, timeout: int = 15) -> bytes:
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


def fetch_image_bytes(url: str, timeout: int = 15) -> bytes:
    """Download raw image bytes from *url*, retrying up to 3 times.

    Uses the same global rate limiter as _request() since both hit the same
    host, preventing connection-refused cascades from concurrent downloads.
    """
    global _last_request_time
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
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise RuntimeError(f"Download failed for {url}: {exc}") from exc
            wait = 1.5 ** attempt
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
_MIN_REQUEST_INTERVAL = 0.5  # base seconds between requests (2 req/s)
_rate_backoff: float = 1.0   # dynamic multiplier; doubles on HTTP 429, recovers on success
_MAX_BACKOFF: float = 8.0    # cap at 8× = one request per 4 s

# Set by the caller (e.g. download_all_memes.py) so retry sleeps can be
# interrupted immediately when the user presses Ctrl+C.
_stop_event: threading.Event | None = None


def _request(path: str, timeout: int = 10) -> dict:
    """Fetch JSON from the API, retrying up to 5 times on transient errors.

    DNS failures (Errno -3) get a longer back-off (30 s) so a temporary
    network hiccup on a Pi doesn't permanently skip queries.

    A global rate limiter ensures at most ~3 requests/s across all threads,
    which avoids HTTP 429 responses from the server.
    """
    global _last_request_time, _rate_backoff
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
                    _rate_backoff = max(1.0, _rate_backoff * 0.9)
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
        except (urllib.error.URLError, TimeoutError,
                http.client.RemoteDisconnected, ConnectionResetError) as exc:
            if attempt == 4:
                raise RuntimeError(f"Network error fetching {url}: {exc}") from exc
            # DNS failure → long back-off; remote-disconnect → short back-off
            is_dns = "Name or service not known" in str(exc) or "Errno -3" in str(exc)
            wait = 30 if is_dns else 2 ** attempt
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

def get_random_meme(timeout: int = 10) -> Meme:
    """Fetch a single random meme."""
    results = get_random_memes(count=1, timeout=timeout)
    if not results:
        raise RuntimeError("API returned no memes")
    return results[0]


def get_random_memes(count: int = 5, timeout: int = 10) -> list[Meme]:
    """Fetch *count* random memes in a single request (1–50 recommended)."""
    data = _request(f"/random?count={count}&full=true", timeout=timeout)
    return [_parse_meme(m) for m in data.get("results", [])]


def get_newest_memes(count: int = 12, timeout: int = 10) -> list[Meme]:
    """Fetch the most recently added memes."""
    data = _request(f"/newest?count={count}", timeout=timeout)
    return [_parse_meme(m) for m in data.get("results", [])]


def get_meme_by_id(meme_id: str, timeout: int = 10) -> Meme:
    """Fetch a specific meme by its UUID."""
    data = _request(f"/memes/{meme_id}", timeout=timeout)
    return _parse_meme(data)


def search_memes(query: str, limit: int = 10, timeout: int = 10) -> list[Meme]:
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
        tag_new_total = 0   # new memes found across all pages for this tag
        last_total = 0      # global total after this tag finishes

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

        if verbose and tag_new_total > 0:
            print(
                f"  tag {i:4d}/{n_tags} {tag!r:35s}  "
                f"pages={page}  new={tag_new_total:3d}  total={last_total:5d}"
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


def get_new_meme_ids(memes_dir: str, verbose: bool = True) -> list[str]:
    """
    Return UUIDs of memes on the site that are not yet downloaded to *memes_dir*.

    Paginates /newest with cursor until it encounters a meme already on disk,
    meaning it has gone far enough back in time.  This handles any number of
    new memes added between runs — not just the first 50.

    Parameters
    ----------
    memes_dir : str
        Path to the local memes directory (e.g. "static/memes").
    verbose : bool

    Returns
    -------
    list[str]
        UUIDs of memes that exist on the site but not on disk.
    """
    existing = {
        f.stem for f in Path(memes_dir).glob("*.webp")
        if not f.name.startswith("_")
    }

    missing: list[str] = []
    fetched = 0
    cursor: str | None = None

    while True:
        params: dict[str, str] = {"count": "50", "full": "true"}
        if cursor:
            params["cursor"] = cursor
        data = _request("/newest?" + urllib.parse.urlencode(params))
        results = data.get("results", [])
        fetched += len(results)

        hit_existing = False
        for meme in results:
            uid = meme["id"]
            if uid in existing:
                hit_existing = True
            else:
                missing.append(uid)

        cursor = data.get("next_cursor")

        # Stop once we've overlapped with what's already on disk, or no more pages
        if not results or not cursor or hit_existing:
            break

    if verbose:
        print(
            f"  [get_new_meme_ids] fetched={fetched}  on_disk={len(existing)}"
            f"  missing={len(missing)}"
        )

    return missing


def get_stats(timeout: int = 10) -> dict:
    """Return site statistics (total memes, total searches, top queries)."""
    return _request("/stats", timeout=timeout)


def get_templates(timeout: int = 10) -> list[dict]:
    """Return all meme templates with usage counts, sorted by count descending.

    Each entry: {"name": "photo_macro", "count": 996}
    The API returns all ~450 templates in one response.
    """
    data = _request("/templates", timeout=timeout)
    return data.get("templates", [])


def get_tags(timeout: int = 10) -> list[dict]:
    """Return all meme tags with their type (topic/crypto).

    Each entry: {"name": "bitcoin", "type": "topic"}
    The API returns all ~5800 tags in one response.
    """
    data = _request("/tags", timeout=timeout)
    return data.get("tags", [])


def download_meme(meme: Meme, path: str, use_thumb: bool = False, timeout: int = 15) -> str:
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

if __name__ == "__main__":
    print("Fetching site stats...")
    stats = get_stats()
    print(f"  Total memes : {stats['total_memes']}")
    print(f"  Total searches: {stats['total_searches']}")
    print()

    print("Fetching 3 random memes...")
    memes = get_random_memes(count=3)
    for i, m in enumerate(memes, 1):
        print(f"\n--- Meme {i} ---")
        print(f"  ID         : {m.id}")
        print(f"  Template   : {m.meme_template}")
        print(f"  Sentiment  : {m.sentiment}")
        print(f"  Tags       : {', '.join(m.tags[:5])}")
        print(f"  EN desc    : {(m.description_en or '')[:120]}")
        print(f"  Image URL  : {m.image_url}")

    print("\nDone. Call get_random_meme() in your app to fetch a single random meme.")
