"""Which memes on disk the renderer cannot match, and why.

A meme is only reachable if two things are true: the image is in the memes
directory, and a record for it exists in index.jsonl or _state_memes.jsonl
carrying something to match on. An image without a record is invisible to
holiday and tag selection however good the picture is - it sits on the card and
is never chosen.

That happens when a meme arrives by a route that saves the file and not the
metadata. Run this to find out how many are in that state before deciding
whether a full re-crawl is worth the hours it costs.

It also reports the opposite drift: one meme sitting in the directory as two
files, a .webp from the API and a .jpg or .png converted from it. The renderer
picks from the directory, so a meme with two files comes up twice as often as
every other one.

    python tools/meme_index_audit.py
    python tools/meme_index_audit.py --list          # every affected filename
    python tools/meme_index_audit.py --list --csv    # to pipe somewhere
    python tools/meme_index_audit.py --repair        # refetch the missing records

Read-only unless --repair is given, which appends to index.jsonl and touches
nothing else.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# What the renderer treats as matchable text, from lib/render/memes.py. Kept in
# the same order so the two read the same way; a record with a record but none
# of these fields is indexed and still unmatchable.
TEXT_FIELDS = ('description_en', 'description_de', 'ocr_text',
               'meme_template', 'sentiment', 'humor_type')

IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

# A file named as a uuid came from the API, so a record for it exists upstream
# and can be recovered. Anything else was put in the directory by hand - the
# folder is group-writable for exactly that - and no crawl will ever describe
# it. The two need different answers, so they are counted apart.
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
                     r'[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

SITE = 'https://einundzwanzig-memes.space'
API = SITE + '/api/v1'


def fetch_record(meme_id, timeout=30):
    """One meme's metadata from /memes/<uuid>, or None.

    The response has been seen bare and wrapped depending on endpoint, so the
    record is taken from whichever shape arrives rather than assumed.
    """
    req = urllib.request.Request(f'{API}/memes/{meme_id}',
                                 headers={'User-Agent': 'mempaper-index-repair/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict):
        if data.get('id'):
            return data
        for key in ('meme', 'result', 'data'):
            inner = data.get(key)
            if isinstance(inner, dict) and inner.get('id'):
                return inner
    return None


def repair(memes_dir, names, delay):
    """Fetch a record for each file and append it to index.jsonl.

    Appends rather than rewrites: index.jsonl already describes four thousand
    memes this run knows nothing about, and rebuilding it from what is in hand
    would discard them.
    """
    index_path = os.path.join(memes_dir, 'index.jsonl')
    added = failed = 0
    with open(index_path, 'a', encoding='utf-8') as out:
        for n, name in enumerate(names, 1):
            uid = os.path.splitext(name)[0]
            record = fetch_record(uid)
            if record is None:
                failed += 1
                print(f'  [{n}/{len(names)}] {uid}  no record returned')
            else:
                record['image_url'] = f'{SITE}/images/medium/{uid}.webp'
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                out.flush()
                added += 1
                tags = record.get('tags') or []
                print(f'  [{n}/{len(names)}] {uid}  {len(tags)} tag(s)')
            # The same courtesy the downloader extends: this is somebody else's
            # server and there are hundreds of these.
            time.sleep(delay)
    return added, failed
INDEX_FILES = ('index.jsonl', '_state_memes.jsonl')


def load_renames(memes_dir):
    """{current_stem: original_uuid} - a renamed file is still indexed by uuid."""
    path = os.path.join(memes_dir, '_renames.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def load_records(memes_dir):
    """{id: record} from both index files, first occurrence winning."""
    records = {}
    for name in INDEX_FILES:
        path = os.path.join(memes_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mid = entry.get('id', '')
                if mid and mid not in records:
                    records[mid] = entry
    return records


def matchable(record):
    """True when the record carries anything the renderer could match on."""
    if record.get('tags'):
        return True
    return any(record.get(f) for f in TEXT_FIELDS)


def dupe_key(name, renames):
    """The identity a converted copy shares with the file it was made from.

    A converter keeps the name and changes the extension, and some keep the old
    extension as well and write <uuid>.webp.jpg. Case is dropped because a copy
    that has passed through a case-insensitive filesystem can come back spelled
    differently from the file it was made from.
    """
    stem = os.path.splitext(name)[0]
    if stem in renames:
        return renames[stem].lower()
    inner, ext = os.path.splitext(stem)
    if ext.lower() in IMAGE_SUFFIXES:
        stem = inner
    return stem.lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--memes-dir', default='static/memes')
    parser.add_argument('--list', action='store_true',
                        help='print every affected filename and every '
                             'duplicate group, not just a sample')
    parser.add_argument('--csv', action='store_true',
                        help='filename,problem - one per line, no headings')
    parser.add_argument('--repair', action='store_true',
                        help='fetch the missing records from the API and append '
                             'them to index.jsonl')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='seconds between API calls when repairing '
                             '(default: 0.5)')
    args = parser.parse_args()

    memes_dir = args.memes_dir
    if not os.path.isdir(memes_dir):
        print(f'No such directory: {memes_dir}', file=sys.stderr)
        return 2

    files = sorted(
        f for f in os.listdir(memes_dir)
        if f.lower().endswith(IMAGE_SUFFIXES) and not f.startswith('_')
    )
    renames = load_renames(memes_dir)
    records = load_records(memes_dir)

    no_record, local_only, no_text, fine = [], [], [], 0
    for name in files:
        stem = os.path.splitext(name)[0]
        # A renamed file is indexed under the uuid it arrived with, and a
        # converted copy under the name it had before the conversion. Both are
        # what dupe_key resolves, so a .jpg made from a .webp is judged on the
        # record that describes the picture rather than counted as a stray.
        key = dupe_key(name, renames)
        record = records.get(key) or records.get(stem)
        if record is None:
            (no_record if UUID_RE.match(key) else local_only).append(name)
        elif not matchable(record):
            no_text.append(name)
        else:
            fine += 1

    # The same meme as several files. The renderer draws whatever is in the
    # directory, so a .jpg converted from a .webp that was left in place beside
    # it is a second chance for that one meme every time a card is filled.
    groups = {}
    for name in files:
        groups.setdefault(dupe_key(name, renames), []).append(name)
    duplicates = sorted((k, sorted(v)) for k, v in groups.items() if len(v) > 1)
    dupe_extra = sum(len(v) - 1 for _, v in duplicates)

    # Records with no image left. Harmless to the renderer, but a sign the
    # directory and the index have drifted apart.
    stems = {os.path.splitext(f)[0] for f in files}
    keyed = stems | {dupe_key(f, renames) for f in files}
    orphans = sorted(mid for mid in records if mid not in keyed)

    if args.csv:
        for name in no_record:
            print(f'{name},no-record')
        for name in local_only:
            print(f'{name},not-from-api')
        for name in no_text:
            print(f'{name},no-tags')
        for key, names in duplicates:
            for name in names:
                print(f'{name},duplicate-of-{key}')
        return 0

    print(f'memes directory : {os.path.abspath(memes_dir)}')
    print(f'image files     : {len(files)}')
    print(f'index records   : {len(records)}'
          f"  (from {', '.join(n for n in INDEX_FILES if os.path.exists(os.path.join(memes_dir, n))) or 'nothing'})")
    if renames:
        print(f'renamed files   : {len(renames)}')
    print()
    print(f'  matchable                       {fine}')
    print(f'  from the API, no record         {len(no_record)}   <- recoverable')
    print(f'  added by hand, no record        {len(local_only)}   <- never had one')
    print(f'  record, nothing to match on     {len(no_text)}')
    if duplicates:
        print(f'  same meme, several files        {dupe_extra}'
              f'   <- {len(duplicates)} group(s)')
    if orphans:
        print(f'  index entries with no image     {len(orphans)}')

    affected = no_record + local_only + no_text

    if args.repair:
        if not no_record:
            print()
            print('Nothing to repair - every meme from the API already has a '
                  'record.')
            print('Files added by hand have none to fetch.')
            return 0
        print()
        print(f'Fetching {len(no_record)} record(s) from {API}/memes/<id> ...')
        added, failed = repair(memes_dir, no_record, args.delay)
        print()
        print(f'Appended {added} record(s) to index.jsonl'
              + (f', {failed} could not be fetched' if failed else ''))
        if added:
            print('Restart mempaper, or wait for the meme cache to expire, for '
                  'the display to pick them up.')
        return 0
    if not affected:
        print('\nEvery meme on disk can be matched.')
    else:
        print()
        shown = affected if args.list else affected[:15]
        for name in shown:
            if name in set(no_record):
                why = 'no record (recoverable)'
            elif name in set(local_only):
                why = 'not from the API'
            else:
                why = 'no tags or text'
            print(f'  {name}  -  {why}')
        if not args.list and len(affected) > len(shown):
            print(f'  ... and {len(affected) - len(shown)} more (--list for all)')

        print(f'\n{len(affected)} of {len(files)} cannot be matched by the renderer.')
        if no_record:
            print(f'{len(no_record)} came from the API and can get their records back:')
            print('  python tools/meme_index_audit.py --repair')
        if local_only:
            print(f'{len(local_only)} were added to the directory by hand and have no')
            print('upstream record at all. They still appear in the ordinary rotation;')
            print('only holiday and tag matching needs what they lack, and tags can be')
            print('set for them in the settings page.')

    if duplicates:
        print()
        print('Same meme, more than one file:')
        shown = duplicates if args.list else duplicates[:10]
        for key, names in shown:
            print(f'  {key}')
            for name in names:
                try:
                    kb = os.path.getsize(os.path.join(memes_dir, name)) / 1024
                    size = f'{kb:8.0f} KB'
                except OSError:
                    size = '           ?'
                print(f'    {size}  {name}')
        if not args.list and len(duplicates) > len(shown):
            print(f'  ... and {len(duplicates) - len(shown)} more (--list for all)')
        print()
        print(f'{dupe_extra} extra file(s) across {len(duplicates)} meme(s). Each of those')
        print('memes can be drawn more than once, and each extra file is disk the')
        print('card did not need. Where a group holds a .webp, that is the file the')
        print('API served and the one index.jsonl names by image_url; the copy in')
        print('another format was made on this device and is the one to remove.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
