"""
download_all_memes.py
~~~~~~~~~~~~~~~~~~~~~
Bulk-download all memes from einundzwanzig-memes.space into static/memes/.

HOW IT WORKS
------------
The site exposes no public "list all" endpoint. /random is server-cached
(always returns the same 50 memes). filter_template/filter_tag are capped
at 100 results and return the same popular memes for every filter value.

The only working strategy is semantic search: fetch all ~5 800 real tags
from /api/v1/tags, then run /search?q=TAG with cursor pagination for each.
Since every meme is described with real tag terms, this reaches near-100%
coverage. Results are de-duplicated by UUID.

Discovery and downloading run in parallel: as soon as a new meme UUID is
found it is queued for download immediately, so both phases overlap.

DUPLICATE DETECTION
-------------------
Images are downloaded as {uuid}.webp. Before queuing any download, the
script checks whether {uuid}.webp already exists on disk with a non-zero
size. If it does, the meme is skipped entirely — no HTTP request is made.
This means re-running the script after a completed full download to pick up
2-3 new memes costs almost nothing: only the 2-3 new UUIDs are downloaded.

RESUMABLE RUNS
--------------
A progress cache is kept in the output directory by default:
  _state_tags.txt    – completed tag names, one per line (append-only)
  _state_memes.jsonl – discovered meme metadata, one JSON per line

On restart, completed tags are skipped and previously discovered memes
that are not yet on disk are re-queued for download automatically.

When a full run completes successfully, _state_tags.txt is deleted so that
the next run re-scans all tags to discover newly added memes.
_state_memes.jsonl is kept so that already-known UUIDs are not re-queued.

STATUS AND CONTROL
------------------
  _state_status.txt  – current state: idle / running / paused / done
  _state_stop        – create this file to signal a running download to pause

The script does NOT auto-start when the app service restarts.  It only runs
when explicitly invoked (via CLI or the GUI "Start/Resume" button).

USAGE
-----
    # Full bulk download (first time, or re-scan for new memes)
    python scripts/download_all_memes.py

    # Resume an interrupted run
    python scripts/download_all_memes.py

    # Check current status (for GUI polling)
    python scripts/download_all_memes.py --status

    # Signal a running download to pause cleanly
    python scripts/download_all_memes.py --stop

    # Check for new memes only (fast, for cron / daily updates)
    python scripts/download_all_memes.py --update

    # Dry run — discover UUIDs and write index, no image downloads
    python scripts/download_all_memes.py --dry-run

    # Disable resume cache (full re-scan, ignores previous progress)
    python scripts/download_all_memes.py --no-cache

    # Custom output directory and concurrency
    python scripts/download_all_memes.py --out-dir /tmp/btc_memes --workers 4
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from einundzwanzig_memes import collect_all_ids, fetch_image_bytes, get_new_meme_ids, image_url

_STATUS_FILE = "_state_status.txt"
_STOP_FILE = "_state_stop"


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
    parser = argparse.ArgumentParser(
        description="Bulk-download all memes from einundzwanzig-memes.space"
    )
    parser.add_argument(
        "--out-dir", default="static/memes", help="Output directory (default: static/memes)"
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Concurrent download threads (default: 4)"
    )
    parser.add_argument(
        "--search-workers", type=int, default=4,
        help="Parallel tag-search workers (default: 4)"
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
    parser.add_argument("--update", action="store_true",
                        help="Fast mode: check /newest for memes not yet on disk")
    parser.add_argument("--status", action="store_true",
                        help="Print current download status (idle/running/paused/done) and exit")
    parser.add_argument("--stop", action="store_true",
                        help="Signal a running download to pause cleanly and exit")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

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
        print("Update mode — checking for new memes …")
        print(f"{'='*60}")
        missing_ids = get_new_meme_ids(str(out_dir), verbose=True)
        if not missing_ids:
            print("No new memes found. Already up to date.")
            return
        print(f"\nDownloading {len(missing_ids)} new meme(s) …")
        success = failed = 0
        for uid in missing_ids:
            _, ok, msg = _download_by_id(uid, out_dir)
            if ok:
                success += 1
                print(f"  ✓ {uid}")
            else:
                failed += 1
                print(f"  ✗ {uid}: {msg}")
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
        for future in as_completed(download_futures):
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


if __name__ == "__main__":
    main()
