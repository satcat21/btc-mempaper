"""Meme and OPSec image selection: the on-disk cache, tag and rename
bookkeeping, holiday-aware picking, and cover-cropping for the panel.
"""

from PIL import Image
from PIL import ImageOps
from datetime import datetime
from lib.btc_holidays import btc_holidays
import os
import random


# Roughly how many blocks Bitcoin produces per day -- the number of memes the
# panel gets through in 24h, used to size the holiday share below.
_BLOCKS_PER_DAY = 144

# How often a single holiday-tagged meme may appear on its holiday. A holiday
# with only 2-3 matching memes would otherwise fill all ~144 blocks of the day
# with those same images. Instead the holiday pool is used with a probability
# proportional to its size, so a small pool is padded out with general memes
# while a large one takes over the day completely.
#
# 24 shows/day is exactly once an hour (144 blocks / 24 h = 6 blocks per hour),
# which reduces the share to a clean pool/6:
#   1 meme -> 1/6 of blocks    3 memes -> 1/2 of blocks
#   2 memes-> 1/3 of blocks    6+      -> every block
# Often enough that the theme of the day is unmistakable, rare enough that the
# panel never looks stuck on one image.
_HOLIDAY_SHOWS_PER_MEME = 24


class MemeMixin:
    """Meme and OPSec image selection: the on-disk cache, tag and rename"""

    def pick_random_meme(self):
        """
        Select a random meme image from the local memes directory.
        Avoids repeating recently shown memes.

        Returns:
            str or None: Path to selected meme or None if no memes found
        """
        # Try holiday-themed selection first
        # Extract keywords from English + German titles (memes may be tagged in either)
        # Use the current round-robin entry (same one get_today_btc_holiday will display)
        today_key = datetime.now().strftime("%m-%d")
        holiday_list = btc_holidays.get(today_key)
        if holiday_list and isinstance(holiday_list, list) and len(holiday_list) > 0:
            idx = self._holiday_rr_index.get(today_key, 0) % len(holiday_list)
            holiday_data = holiday_list[idx]
            en_title = holiday_data.get("en", {}).get("title", "")
            de_title = holiday_data.get("de", {}).get("title", "")
            keywords = list(dict.fromkeys(
                self._holiday_keywords(en_title) + self._holiday_keywords(de_title)
            ))
            if keywords:
                result = self._pick_local_meme_by_keywords(keywords)
                if result:
                    self._track_recent_meme(result)
                    return result
        result = self._pick_local_meme()
        if result:
            self._track_recent_meme(result)
        return result

    def _track_recent_meme(self, path: str) -> None:
        """Record a meme path in the recent history ring buffer."""
        self._recent_memes.append(path)
        if len(self._recent_memes) > self._RECENT_MEMES_MAX:
            self._recent_memes = self._recent_memes[-self._RECENT_MEMES_MAX:]

    @staticmethod
    def _tag_stem(word: str, stopwords: set):
        """The noun inside a German '...tag' compound, or None.

        German glues the day onto the noun where English writes "... Day", so
        the word carrying the meaning ends up fused to a stopword and survives
        as a token nothing is tagged with. The linking -s-/-es- goes with it,
        which is what turns "todestag" into "tod".
        """
        if not word.endswith('tag') or len(word) <= 6:
            return None
        stem = word[:-3]
        if stem.endswith('es') and len(stem) > 4:
            stem = stem[:-2]
        elif stem.endswith('s') and len(stem) > 4:
            stem = stem[:-1]
        return stem if len(stem) >= 3 and stem not in stopwords else None

    @staticmethod
    def _holiday_keywords(title: str) -> list:
        """Extract search keywords from a holiday title.

        Strips common stopwords, 'bitcoin'/'btc'/'day', '#N' tokens,
        and words shorter than 3 characters.
        """
        import re
        STOPWORDS = {
            # English
            'bitcoin', 'btc', 'day', 'the', 'of', 'a', 'an', 'is', 'this', 'in', 'on',
            'not', 'for', 'its', 'was', 'has', 'are', 'but', 'all', 'can',
            'first', 'good',
            # German
            'tag', 'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'und',
            'von', 'auf', 'aus', 'mit', 'zum', 'zur', 'als', 'bei', 'vor', 'nach',
            'erster', 'erste', 'ersten', 'erstes', 'guten', 'gute', 'guter',
            'nicht', 'oder', 'auch', 'noch', 'nur', 'wie',
        }
        # Fold the umlauts before the a-z filter below reaches them. That
        # filter turns anything outside a-z into a space, which would split a
        # German word at its own letters and leave fragments as keywords -
        # "Parität" as "parit", "Händen" as "nden". The ASCII digraphs keep the
        # word in one piece and match how these are typically typed into a
        # filename or a tag.
        folded = title.lower()
        for _src, _dst in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
            folded = folded.replace(_src, _dst)

        # Also filter out pure-numeric tokens (e.g. "000" from "$1,000")
        cleaned = re.sub(r"[^a-z0-9 ]", " ", folded)
        words = [w for w in cleaned.split()
                 if w not in STOPWORDS and not w.startswith('#') and len(w) >= 3
                 and not w.isdigit()]

        # Emit the compound's stem alongside the compound itself: matching is
        # substring, so "registrierungstag" alone would never find a meme tagged
        # "registrierung", while both together cost nothing.
        # Then the same again for ordinary inflection, because a title reading
        # "Tag des ersten Wechselkurses" carries the genitive and nobody tags a
        # meme that way. Matching is substring and directional - the keyword has
        # to appear inside the meme's text - so an inflected keyword is strictly
        # narrower than its stem, and emitting both can only widen the net. The
        # -en rule is kept to that ending so English words ending in -on or -an
        # ("transaction", "hellman") are left alone.
        def _stem(w):
            if len(w) <= 6:
                return None
            if w.endswith('es'):
                s = w[:-2]
            elif w.endswith('s'):
                s = w[:-1]
            elif w.endswith('en'):
                s = w[:-1]
            else:
                return None
            return s if len(s) >= 4 and s not in STOPWORDS else None

        out = []
        for w in words:
            for form in (w, MemeMixin._tag_stem(w, STOPWORDS)):
                if not form:
                    continue
                out.append(form)
                s = _stem(form)
                if s:
                    out.append(s)
        return list(dict.fromkeys(out))

    # ------------------------------------------------------------------
    # Meme cache helpers
    # ------------------------------------------------------------------

    def _refresh_meme_cache(self, force: bool = False) -> None:
        """Rebuild the cached meme file list + metadata if stale or forced."""
        import json as _json
        import time as _time

        now = _time.time()
        if not force and (now - self._meme_cache_ts) < self._MEME_CACHE_TTL and self._meme_cache_files:
            return  # cache still fresh

        memes_dir = self.meme_dir
        if not os.path.isdir(memes_dir):
            self._meme_cache_files = []
            self._meme_cache_stems = set()
            self._meme_cache_stem_to_file = {}
            self._meme_cache_meta = {}
            self._meme_cache_tags = {}
            self._meme_cache_api_tags = {}
            self._meme_cache_ts = now
            return

        # 1. Scan directory once
        files = [
            f for f in os.listdir(memes_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
            and not f.startswith('_')
        ]
        files.sort()
        stems = {os.path.splitext(f)[0] for f in files}

        # 2. Load rename map (_renames.json): {current_stem: original_uuid}
        renames: dict[str, str] = {}
        renames_path = os.path.join(memes_dir, '_renames.json')
        if os.path.exists(renames_path):
            try:
                with open(renames_path, encoding='utf-8') as fh:
                    renames = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        # Build reverse map: uuid -> current_stem (for re-keying)
        uuid_to_stem: dict[str, str] = {}
        for cur_stem, orig_uuid in renames.items():
            uuid_to_stem[orig_uuid] = cur_stem

        # 3. Build metadata map from index.jsonl + _state_memes.jsonl
        #    Keys are resolved to current filename stems (accounting for renames).
        meta: dict[str, list[str]] = {}
        tags_map: dict[str, list[str]] = {}
        api_tags_map: dict[str, list[str]] = {}  # tags from API (read-only)
        for jsonl_name in ('index.jsonl', '_state_memes.jsonl'):
            jsonl_path = os.path.join(memes_dir, jsonl_name)
            if not os.path.exists(jsonl_path):
                continue
            try:
                with open(jsonl_path, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        mid = entry.get('id', '')
                        if not mid:
                            continue
                        # Resolve UUID to current filename stem
                        key = uuid_to_stem.get(mid, mid)
                        if key in meta:
                            continue
                        raw_tags = entry.get('tags', []) or []
                        searchable: list[str] = []
                        searchable.extend(t.lower() for t in raw_tags)
                        for fld in ('description_en', 'description_de', 'ocr_text',
                                    'meme_template', 'sentiment', 'humor_type'):
                            val = entry.get(fld, '')
                            if val:
                                searchable.append(val.lower())
                        meta[key] = searchable
                        tags_map[key] = list(raw_tags)
                        api_tags_map[key] = list(raw_tags)
            except OSError:
                continue

        # 4. Load user-defined tag overrides (_user_tags.json)
        user_tags_path = os.path.join(memes_dir, '_user_tags.json')
        if os.path.exists(user_tags_path):
            try:
                with open(user_tags_path, encoding='utf-8') as fh:
                    user_tags = _json.load(fh)
                for stem, utags in user_tags.items():
                    api_tags = api_tags_map.get(stem, [])
                    merged = list(api_tags) + [t for t in utags
                                               if t.lower() not in {a.lower() for a in api_tags}]
                    tags_map[stem] = merged
                    # Update searchable meta
                    existing = meta.get(stem, [])
                    existing_set = set(existing)
                    meta[stem] = existing + [t.lower() for t in utags
                                             if t.lower() not in existing_set]
            except (OSError, _json.JSONDecodeError):
                pass

        # Build stem -> filename lookup for path resolution
        stem_to_file: dict[str, str] = {}
        for f in files:
            stem_to_file[os.path.splitext(f)[0]] = f

        self._meme_cache_files = files
        self._meme_cache_stems = stems
        self._meme_cache_stem_to_file = stem_to_file
        self._meme_cache_meta = meta
        self._meme_cache_tags = tags_map
        self._meme_cache_api_tags = api_tags_map
        self._meme_cache_ts = now

    def invalidate_meme_cache(self) -> None:
        """Force the meme cache to rebuild on next access."""
        self._meme_cache_ts = 0.0

    def get_cached_meme_files(self) -> list[str]:
        """Return the cached sorted list of meme filenames."""
        self._refresh_meme_cache()
        return self._meme_cache_files

    def get_cached_meme_meta(self) -> dict[str, list[str]]:
        """Return the cached metadata map (stem -> searchable strings)."""
        self._refresh_meme_cache()
        return self._meme_cache_meta

    def get_cached_meme_tags(self) -> dict[str, list[str]]:
        """Return the cached tags map (stem -> list of tag strings)."""
        self._refresh_meme_cache()
        return self._meme_cache_tags

    def get_cached_meme_api_tags(self) -> dict[str, list[str]]:
        """Return the cached API-sourced tags (stem -> read-only tag list)."""
        self._refresh_meme_cache()
        return self._meme_cache_api_tags

    def record_rename(self, old_stem: str, new_stem: str) -> None:
        """Track a file rename in _renames.json so metadata stays linked."""
        import json as _json
        renames_path = os.path.join(self.meme_dir, '_renames.json')
        renames: dict[str, str] = {}
        if os.path.exists(renames_path):
            try:
                with open(renames_path, encoding='utf-8') as fh:
                    renames = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        # Resolve chain: if old_stem was itself a rename, follow to the original UUID
        original_uuid = renames.pop(old_stem, old_stem)
        renames[new_stem] = original_uuid
        with open(renames_path, 'w', encoding='utf-8') as fh:
            _json.dump(renames, fh, ensure_ascii=False, indent=2)

    def set_meme_tags(self, stem: str, tags: list[str]) -> None:
        """Save user-defined tags for a meme (persisted in _user_tags.json)."""
        import json as _json
        user_tags_path = os.path.join(self.meme_dir, '_user_tags.json')
        user_tags: dict[str, list[str]] = {}
        if os.path.exists(user_tags_path):
            try:
                with open(user_tags_path, encoding='utf-8') as fh:
                    user_tags = _json.load(fh)
            except (OSError, _json.JSONDecodeError):
                pass
        user_tags[stem] = tags
        with open(user_tags_path, 'w', encoding='utf-8') as fh:
            _json.dump(user_tags, fh, ensure_ascii=False, indent=2)
        self.invalidate_meme_cache()

    # ------------------------------------------------------------------

    def _pick_local_meme_by_keywords(self, keywords: list) -> str | None:
        """Return a random local meme whose tags contain any of the keywords.

        Uses the cached metadata from index.jsonl and filters to memes whose
        tag list contains at least one keyword as a substring.
        Only returns memes whose file is actually on disk.
        Avoids recently shown memes when possible.
        Falls back to None if no metadata or no matches found.
        """
        self._refresh_meme_cache()
        if not self._meme_cache_meta:
            return None
        try:
            on_disk = self._meme_cache_stems
            matches = []
            for mid, searchable in self._meme_cache_meta.items():
                if mid not in on_disk:
                    continue
                if any(kw in s for kw in keywords for s in searchable):
                    matches.append(mid)

            if not matches:
                print(f"No local memes matched keywords {keywords}, using random")
                return None

            # Small pools are diluted with general memes rather than shown on
            # repeat all day -- see _HOLIDAY_SHOWS_PER_MEME. Returning None here
            # hands this block back to the normal library-wide selection.
            share = min(1.0, (_HOLIDAY_SHOWS_PER_MEME * len(matches)) / _BLOCKS_PER_DAY)
            if share < 1.0 and random.random() > share:
                return None

            # Cycle through the matching memes before repeating any of them, so a
            # 3-meme holiday rotates instead of picking the same one twice in a row.
            sig = "|".join(sorted(keywords))
            cycle_seen = self._holiday_cycle_seen.setdefault(sig, set())
            unused = [m for m in matches if m not in cycle_seen]
            if not unused:
                cycle_seen.clear()
                unused = matches

            # Prefer memes not recently shown
            recent_set = set(self._recent_memes)
            s2f = self._meme_cache_stem_to_file
            unseen = [m for m in unused
                      if os.path.join(self.meme_dir, s2f.get(m, f"{m}.webp")) not in recent_set]
            pool = unseen if unseen else unused

            chosen = random.choice(pool)
            cycle_seen.add(chosen)
            chosen_file = s2f.get(chosen, f"{chosen}.webp")
            print(f"Holiday meme match (keywords={keywords}, pool={len(pool)}/{len(matches)}, "
                  f"share={share:.0%}): {chosen_file}")
            return os.path.join(self.meme_dir, chosen_file)
        except Exception as e:
            print(f"Error in holiday meme selection: {e}")
            return None

    def _pick_local_meme(self):
        """Select a meme, showing every one in the library before repeating any.

        Draws only from memes not yet used in the current cycle (sampling
        without replacement). Picking uniformly at random instead would repeat a
        meme roughly three times a day on a 4800-image library and still leave
        ~40% of it unseen after a month -- the birthday paradox, not a weak RNG.
        """
        try:
            memes = self.get_cached_meme_files()
            if not memes:
                print("No meme images found in directory")
                return None
            # Memes deleted since the cycle began simply drop out of `memes`, and
            # newly synced ones join the current cycle right away.
            unused = [f for f in memes if f not in self._meme_cycle_seen]
            if not unused:
                print(f"🔄 Showed all {len(memes)} memes — starting a new cycle")
                self._meme_cycle_seen.clear()
                unused = memes
            # Recent-window guard on top of the cycle: without it the meme that
            # closed one cycle could open the next one straight after.
            recent_set = set(self._recent_memes)
            unseen = [f for f in unused
                      if os.path.join(self.meme_dir, f) not in recent_set]
            pool = unseen if unseen else unused
            selected = random.choice(pool)
            self._meme_cycle_seen.add(selected)
            return os.path.join(self.meme_dir, selected)
        except Exception as e:
            print(f"Error selecting meme: {e}")
            return None

    def pick_random_opsec_image(self):
        """
        Select a random OPSec image from the opsec directory.

        Returns:
            str or None: Path to selected OPSec image or None if none found
        """
        try:
            if not os.path.exists(self.opsec_dir):
                return None
            images = [f for f in os.listdir(self.opsec_dir)
                      if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
            if not images:
                print("No OPSec images found in directory")
                return None
            selected = random.choice(images)
            return os.path.join(self.opsec_dir, selected)
        except Exception as e:
            print(f"Error selecting OPSec image: {e}")
            return None

    def get_opsec_image_for_eink(self):
        """
        Get a randomly selected OPSec image for e-ink display.
        A new random image is picked on every block update.

        Returns:
            str or None: Path to a randomly selected OPSec image
        """
        image = self.pick_random_opsec_image()
        return image

    def _cover_crop(self, img, target_width, target_height):
        """
        Scale and center-crop an image to exactly cover the target dimensions
        without changing the original aspect ratio (CSS object-fit: cover behaviour).

        The image is scaled up/down uniformly so that both target dimensions are
        fully covered, then the excess is cropped symmetrically from the edges.

        Args:
            img (PIL.Image): Source image (must already be in RGB mode)
            target_width (int): Desired output width in pixels
            target_height (int): Desired output height in pixels

        Returns:
            PIL.Image: Cropped/scaled image of exactly (target_width × target_height)
        """
        img_w, img_h = img.size
        scale = max(target_width / img_w, target_height / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)
        img = img.resize((scaled_w, scaled_h), Image.LANCZOS)
        left = (scaled_w - target_width) // 2
        top = (scaled_h - target_height) // 2
        return img.crop((left, top, left + target_width, top + target_height))

    def render_opsec_eink_image(self):
        """
        Render OPSec image for e-ink display.

        The image is scaled to *cover* the full display area (maintaining the
        original aspect ratio) and center-cropped so no empty borders remain.
        self.width / self.height already reflect the e-ink canvas
        (set by _apply_layout_settings before this method is called), so
        portrait vs. landscape is handled automatically.

        Falls back to a plain white image when no OPSec images are available.

        Returns:
            PIL.Image: E-ink optimized image
        """
        opsec_path = self.get_opsec_image_for_eink()

        if opsec_path and os.path.exists(opsec_path):
            try:
                opsec_img = ImageOps.exif_transpose(Image.open(opsec_path)).convert('RGB')
                opsec_img = self._cover_crop(opsec_img, self.width, self.height)
                print(f"🔒 OPSec: rendering {os.path.basename(opsec_path)} "
                      f"({opsec_img.width}×{opsec_img.height}) on e-ink display")
                return self.convert_to_7color(opsec_img, use_meme_optimization=True)
            except Exception as e:
                print(f"⚠️ OPSec: failed to load image {opsec_path}: {e}")

        # Fallback: plain white background
        print("⚠️ OPSec: no images available, rendering blank fallback")
        return Image.new('RGB', (self.width, self.height), color='white')
