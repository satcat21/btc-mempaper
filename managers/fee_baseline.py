"""Rolling fee baseline: what a normal fee has looked like lately.

The block-height colour used to be read off a fixed table of absolute fee
levels, which stopped saying anything useful once fees settled into the low
single digits - 0 to 5 sat/vB all mapped to the same green, so every block for
most of a year looked identical. What a user actually wants to know is not
"is this fee 3 sat/vB" but "is 3 cheap *right now*", and that only has an
answer relative to what fees have been doing.

This module keeps that reference point: the median block fee over a rolling
window (30 days by default). Median rather than mean on purpose - a single
ordinal-inscription day at 300 sat/vB would drag a mean upward for weeks and
make genuinely expensive blocks read as normal, while the median barely moves.

Three sources feed it, in descending order of quality:

  1. Locally recorded blocks. mempaper already fetches fee data on every new
     block, so the window fills itself in normal operation and is correct for
     whatever backend the user actually runs.
  2. /v1/mining/blocks/fee-rates - a whole window in one request, but only on
     a mempool instance with block indexing enabled.
  3. /v1/blocks - the last ~15 blocks. Always available; enough to warm a cold
     cache so a fresh install is not colourless until tomorrow.

Nothing here raises. A missing or unreadable history returns no baseline, and
the caller falls back to the absolute scale.
"""

import os
import threading
import time

from utils.atomic_io import atomic_write_json

try:
    import json
except ImportError:      # pragma: no cover - json is stdlib
    json = None


SECONDS_PER_DAY = 86400

# A baseline computed from a handful of blocks is noise. Under this many samples
# the caller is told there is no baseline yet rather than being handed a bad one.
MIN_SAMPLES = 12


class FeeBaseline:
    """Rolling median of recent block fees, persisted across restarts."""

    def __init__(self, cache_path, window_days=30, api=None):
        self.cache_path = cache_path
        self.window_days = self._sane_window(window_days)
        self.api = api
        self._lock = threading.Lock()
        # {height: {'fee': float, 'ts': int}} - keyed by height so a block seen
        # twice (re-render, restart, missed-block recovery) cannot be counted twice.
        self._samples = {}
        self._last_backfill = 0.0
        self._load()

    # ── window helpers ────────────────────────────────────────────────────

    @staticmethod
    def _sane_window(days):
        try:
            days = int(days)
        except (TypeError, ValueError):
            return 30
        return max(3, min(90, days))

    def set_window_days(self, days):
        """Apply a config change without losing samples already collected."""
        with self._lock:
            self.window_days = self._sane_window(days)

    def _cutoff(self, now=None):
        return (now or time.time()) - self.window_days * SECONDS_PER_DAY

    # ── persistence ───────────────────────────────────────────────────────

    def _load(self):
        try:
            if not os.path.exists(self.cache_path):
                return
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            print(f"⚠️ Fee baseline cache unreadable, starting empty: {e}")
            return

        samples = raw.get('samples') if isinstance(raw, dict) else None
        if not isinstance(samples, dict):
            return
        cutoff = self._cutoff()
        loaded = {}
        for height, entry in samples.items():
            try:
                fee = float(entry['fee'])
                ts = int(entry['ts'])
            except (TypeError, ValueError, KeyError):
                continue
            if ts >= cutoff and fee >= 0:
                loaded[str(height)] = {'fee': fee, 'ts': ts}
        self._samples = loaded
        self._last_backfill = float(raw.get('last_backfill') or 0)
        print(f"📊 Fee baseline: loaded {len(loaded)} samples "
              f"({self.window_days}d window)")

    def _save(self):
        """Persist. Caller must hold the lock."""
        try:
            atomic_write_json(self.cache_path, {
                'samples': self._samples,
                'last_backfill': self._last_backfill,
                'window_days': self.window_days,
            })
        except Exception as e:
            print(f"⚠️ Could not save fee baseline: {e}")

    # ── recording ─────────────────────────────────────────────────────────

    def record(self, height, fee, timestamp=None):
        """Record one block's fee. Idempotent per height."""
        if fee is None or height is None:
            return
        try:
            fee = float(fee)
            key = str(int(height))
        except (TypeError, ValueError):
            return
        if fee < 0:
            return
        ts = int(timestamp or time.time())

        with self._lock:
            existing = self._samples.get(key)
            if existing and abs(existing['fee'] - fee) < 1e-9:
                return                       # already have it, unchanged
            self._samples[key] = {'fee': fee, 'ts': ts}
            self._prune_locked()
            self._save()

    def record_many(self, rows):
        """Record a batch of {'height','timestamp','median_fee'} dicts."""
        added = 0
        with self._lock:
            for row in rows or []:
                try:
                    key = str(int(row['height']))
                    fee = float(row['median_fee'])
                    ts = int(row.get('timestamp') or time.time())
                except (TypeError, ValueError, KeyError):
                    continue
                if fee < 0 or ts < self._cutoff():
                    continue
                if key not in self._samples:
                    added += 1
                self._samples[key] = {'fee': fee, 'ts': ts}
            if added:
                self._prune_locked()
                self._save()
        return added

    def _prune_locked(self):
        cutoff = self._cutoff()
        self._samples = {h: e for h, e in self._samples.items()
                         if e['ts'] >= cutoff}

    # ── backfill ──────────────────────────────────────────────────────────

    def backfill(self, force=False):
        """Top up history from the API. Safe to call often; rate-limited.

        Runs at most once every six hours unless forced, because the indexed
        endpoint returns a full window each time and there is nothing to gain
        from asking again between blocks.
        """
        if not self.api:
            return 0
        now = time.time()
        with self._lock:
            fresh_enough = (now - self._last_backfill) < 6 * 3600
            have_enough = len(self._samples) >= MIN_SAMPLES
        if not force and fresh_enough and have_enough:
            return 0

        added = 0
        # Widest indexed window that still fits the configured span.
        period = self._period_for_window()
        rows = []
        try:
            rows = self.api.get_historical_fee_rates(period)
        except Exception as e:
            print(f"⚠️ Fee-rate backfill failed: {e}")
        if rows:
            added += self.record_many(rows)
        else:
            # No mining module. The last ~15 blocks at least give the scale
            # something to stand on until local recording catches up.
            try:
                added += self.record_many(self.api.get_recent_block_fees())
            except Exception as e:
                print(f"⚠️ Recent-block backfill failed: {e}")

        with self._lock:
            self._last_backfill = now
            self._save()
        if added:
            print(f"📊 Fee baseline: backfilled {added} blocks via {period}")
        return added

    def _period_for_window(self):
        for days, period in ((1, '24h'), (3, '3d'), (7, '1w'),
                             (30, '1m'), (90, '3m')):
            if self.window_days <= days:
                return period
        return '3m'

    # ── the answer ────────────────────────────────────────────────────────

    def baseline(self):
        """Median block fee over the window, or None when too little data.

        None is meaningful: it tells the colour mapper to use the absolute
        scale instead of pretending to know what normal looks like.
        """
        with self._lock:
            cutoff = self._cutoff()
            fees = sorted(e['fee'] for e in self._samples.values()
                          if e['ts'] >= cutoff)
        if len(fees) < MIN_SAMPLES:
            return None
        mid = len(fees) // 2
        if len(fees) % 2:
            return fees[mid]
        return (fees[mid - 1] + fees[mid]) / 2.0

    def fee_for(self, height):
        """One block's own median fee, or None if it is not in the window.

        This is what the colour scale reads. The baseline is a median of block
        medians, so the number placed over it has to be the same kind of number.
        A fee recommendation is not: fastestFee sits above the block median by
        construction and hourFee below it, so the ratio moved with whichever
        tier was configured rather than with the market.
        """
        try:
            key = str(int(height))
        except (TypeError, ValueError):
            return None
        with self._lock:
            entry = self._samples.get(key)
        return entry['fee'] if entry else None

    def stats(self):
        """Diagnostics for the config UI and logs."""
        with self._lock:
            cutoff = self._cutoff()
            fees = sorted(e['fee'] for e in self._samples.values()
                          if e['ts'] >= cutoff)
        if not fees:
            return {'samples': 0, 'baseline': None, 'window_days': self.window_days,
                    'min': None, 'max': None}
        return {
            'samples': len(fees),
            'baseline': self.baseline(),
            'window_days': self.window_days,
            'min': fees[0],
            'max': fees[-1],
        }


# ── Process-wide instance ─────────────────────────────────────────────────
# ImageRenderer is rebuilt on every config change and constructed from five
# different places, so the store cannot live on it: five instances would each
# hold a partial window and race each other writing the same file. One store
# per process, reconfigured in place when settings change.

_shared = None
_shared_lock = threading.Lock()


def get_shared_baseline(cache_path=None, window_days=30, api=None):
    """The process-wide FeeBaseline, created on first use.

    Later calls update the window and API client rather than replacing the
    instance, so a config change keeps every sample collected so far.
    """
    global _shared
    with _shared_lock:
        if _shared is None:
            if not cache_path:
                return None
            _shared = FeeBaseline(cache_path, window_days=window_days, api=api)
        else:
            if window_days is not None:
                _shared.set_window_days(window_days)
            if api is not None:
                _shared.api = api
        return _shared
