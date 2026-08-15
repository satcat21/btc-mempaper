"""What each fee tier has normally cost, over a rolling window of days.

The block-height colour asks "is this fee cheap right now", which only has an
answer relative to what that *same* fee has been doing lately. The earlier
baseline answered it with a median of mined-block medians, which is a different
quantity from the tier being coloured: fastestFee sits above a block median by
construction and minimumFee below it, so every reading carried a constant offset
set by the chosen tier rather than by the market. A minimumFee device read blue
more or less permanently.

There is no way to fetch that history. mempool exposes past block medians, but
the fee tiers are point-in-time only - no endpoint returns what fastestFee was
last Tuesday. So the window is accumulated locally instead, and all five
tiers are recorded on every sample: get_fee_recommendations() returns them
together in one call already, so keeping all five costs nothing and means
changing fee_parameter does not start a new cold window.

Shape of the window:

  in RAM     every sample of today, five tiers each (~144/day at 10 min)
  on disk    one tuple of five medians per finished day, up to window_days

A day is closed at the local date change and reduced to one median per tier.
The baseline is then the median *of those daily medians*, which weights every
day equally however many samples it contributed - a device booted at 20:00
cannot outvote a full day, and one frantic hour cannot move the window.

Days the device was switched off are simply absent. Nothing is interpolated;
the window is however many of the last window_days actually have data, and it
repairs itself as new days arrive and old ones age out.

Writes are deliberately rare. The window file is ~2 KB and written once a day.
Today's samples live in RAM and are flushed to a small separate file about
hourly, purely so a restart before midnight does not discard the day - without
it, a device that never reaches 00:00 would never contribute a tuple at all,
and would fail silently while looking fine.
"""

import json
import os
import threading
import time
from datetime import datetime

from utils.atomic_io import atomic_write_json

# Every tier get_fee_recommendations() returns. Recorded together so switching
# fee_parameter reads an already-warm window instead of starting from nothing.
TIERS = ('fastestFee', 'halfHourFee', 'hourFee', 'economyFee', 'minimumFee')

# A day needs at least this many samples before it is allowed into the window,
# or a device booted at 23:50 would contribute a two-sample "day" carrying the
# same weight as a full one.
MIN_SAMPLES_PER_DAY = 6

# Today's partial counts as a day once it clears the same bar, so a fresh
# install has a tier-correct baseline within an hour rather than tomorrow.
FLUSH_INTERVAL = 3600


def _median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def _day_key(ts=None):
    """Local date, matching the rollover the display already follows."""
    return datetime.fromtimestamp(ts or time.time()).strftime('%Y-%m-%d')


class FeeTierBaseline:
    """Rolling per-tier daily medians, persisted across restarts."""

    def __init__(self, cache_path, day_path, window_days=30):
        self.cache_path = cache_path
        self.day_path = day_path
        self.window_days = self._sane_window(window_days)
        self._lock = threading.Lock()
        self._days = []          # [{'date': 'YYYY-MM-DD', 'n': int, 'medians': {tier: float}}]
        self._day = None         # date key of the samples in _samples
        self._samples = []       # [{tier: float}, ...] for today only
        self._last_flush = 0.0
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
        """Apply a config change without discarding days already collected."""
        with self._lock:
            self.window_days = self._sane_window(days)
            self._prune_locked()

    def _prune_locked(self):
        self._days.sort(key=lambda d: d['date'])
        if len(self._days) > self.window_days:
            self._days = self._days[-self.window_days:]

    # ── persistence ───────────────────────────────────────────────────────

    def _load(self):
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for entry in (raw.get('days') or []):
                    day = self._clean_day(entry)
                    if day:
                        self._days.append(day)
                self._prune_locked()
        except (OSError, ValueError, AttributeError) as e:
            print(f"⚠️ Fee tier window unreadable, starting empty: {e}")

        # Today's partial, if the process restarted inside the same day. A file
        # from an earlier date is a day that ended while we were off - close it
        # rather than throw it away.
        try:
            if os.path.exists(self.day_path):
                with open(self.day_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                stored_day = raw.get('date')
                samples = [s for s in (self._clean_samples(raw.get('samples')))]
                if stored_day == _day_key():
                    self._day = stored_day
                    self._samples = samples
                elif stored_day and samples:
                    self._promote_locked(stored_day, samples)
                    self._save_window_locked()
                    self._clear_day_file()
        except (OSError, ValueError, AttributeError) as e:
            print(f"⚠️ Fee tier day file unreadable, ignoring: {e}")

        if self._days or self._samples:
            print(f"📊 Fee tier baseline: {len(self._days)} day(s) cached, "
                  f"{len(self._samples)} sample(s) today "
                  f"({self.window_days}d window)")

    @staticmethod
    def _clean_day(entry):
        try:
            date = str(entry['date'])
            medians = {t: float(v) for t, v in (entry.get('medians') or {}).items()
                       if t in TIERS and float(v) >= 0}
        except (TypeError, ValueError, KeyError):
            return None
        if not date or not medians:
            return None
        return {'date': date, 'n': int(entry.get('n') or 0), 'medians': medians}

    @staticmethod
    def _clean_samples(rows):
        out = []
        for row in (rows or []):
            if not isinstance(row, dict):
                continue
            vals = {}
            for tier, v in row.items():
                if tier not in TIERS:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                if v >= 0:
                    vals[tier] = v
            if vals:
                out.append(vals)
        return out

    def _save_window_locked(self):
        try:
            atomic_write_json(self.cache_path, {
                'days': self._days,
                'window_days': self.window_days,
            })
        except Exception as e:
            print(f"⚠️ Could not save fee tier window: {e}")

    def _flush_day_locked(self, ts=None):
        try:
            atomic_write_json(self.day_path, {
                'date': self._day,
                'samples': self._samples,
            })
            # Stamped from the sample's own clock, not time.time(): the cadence
            # has to be measured against whatever clock sample() was given, or
            # one flush would set the next due time on a different timebase.
            self._last_flush = ts if ts is not None else time.time()
        except Exception as e:
            print(f"⚠️ Could not save today's fee samples: {e}")

    def _clear_day_file(self):
        try:
            if os.path.exists(self.day_path):
                os.remove(self.day_path)
        except OSError:
            pass

    # ── recording ─────────────────────────────────────────────────────────

    def sample(self, fee_data, now=None):
        """Record one observation of every tier present in fee_data."""
        if not isinstance(fee_data, dict):
            return
        vals = {}
        for tier in TIERS:
            try:
                v = float(fee_data[tier])
            except (TypeError, ValueError, KeyError):
                continue
            if v >= 0:
                vals[tier] = v
        if not vals:
            return

        ts = now or time.time()
        day = _day_key(ts)
        with self._lock:
            if self._day is not None and self._day != day:
                self._close_day_locked()
            self._day = day
            self._samples.append(vals)
            if (ts - self._last_flush) >= FLUSH_INTERVAL:
                self._flush_day_locked(ts)

    def roll_over(self, now=None):
        """Close the day if the local date has moved on.

        Called from the midnight rollover the precache loop already detects, so
        a day closes on time even when the next sample is late.
        """
        day = _day_key(now)
        with self._lock:
            if self._day is not None and self._day != day:
                self._close_day_locked()
                self._day = day
                return True
        return False

    def _close_day_locked(self):
        """Reduce the finished day to one median per tier and file it."""
        promoted = self._promote_locked(self._day, self._samples)
        self._samples = []
        self._day = None
        if promoted:
            self._save_window_locked()
        self._clear_day_file()
        self._last_flush = 0.0

    def _promote_locked(self, date, samples):
        if not date or len(samples) < MIN_SAMPLES_PER_DAY:
            return False
        medians = {}
        for tier in TIERS:
            vals = [s[tier] for s in samples if tier in s]
            if len(vals) >= MIN_SAMPLES_PER_DAY:
                medians[tier] = _median(vals)
        if not medians:
            return False
        self._days = [d for d in self._days if d['date'] != date]
        self._days.append({'date': date, 'n': len(samples), 'medians': medians})
        self._prune_locked()
        print(f"📊 Fee tier baseline: closed {date} from {len(samples)} samples "
              f"({len(self._days)} day(s) in window)")
        return True

    # ── the answer ────────────────────────────────────────────────────────

    def baseline(self, tier):
        """Median of the daily medians for one tier, or None when too thin.

        None is meaningful: it tells the colour mapper to use the absolute scale
        rather than invent a ratio from a handful of minutes.
        """
        if tier not in TIERS:
            return None
        with self._lock:
            vals = [d['medians'][tier] for d in self._days if tier in d['medians']]
            today = [s[tier] for s in self._samples if tier in s]
        if len(today) >= MIN_SAMPLES_PER_DAY:
            vals.append(_median(today))
        return _median(vals) if vals else None

    def stats(self, tier=None):
        """Diagnostics for the config UI and logs."""
        with self._lock:
            days = len(self._days)
            today = len(self._samples)
            span = (self._days[0]['date'], self._days[-1]['date']) if self._days else (None, None)
        return {
            'days': days,
            'samples_today': today,
            'window_days': self.window_days,
            'first_day': span[0],
            'last_day': span[1],
            'baseline': self.baseline(tier) if tier else None,
        }


# ── Process-wide instance ─────────────────────────────────────────────────
# ImageRenderer is rebuilt on every config change and constructed from five
# different places, so the store cannot live on it: five instances would each
# hold a partial day and race each other writing the same files.

_shared = None
_shared_lock = threading.Lock()


def get_shared_tier_baseline(cache_path=None, day_path=None, window_days=30):
    """The process-wide FeeTierBaseline, created on first use.

    Later calls update the window rather than replacing the instance, so a
    config change keeps every sample collected so far.
    """
    global _shared
    with _shared_lock:
        if _shared is None:
            if not cache_path or not day_path:
                return None
            _shared = FeeTierBaseline(cache_path, day_path, window_days=window_days)
        elif window_days is not None:
            _shared.set_window_days(window_days)
        return _shared
