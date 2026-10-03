"""Which version pins in apt-requirements.txt the archive still offers.

The Debian and Raspberry Pi archives keep only the current version of each
package. A pin is right on the day it is written and stale the day a security
or point release replaces that version - and nothing on a device says so until
an install trips over it. This reads the same package indexes a device reads,
straight over HTTP, so it runs anywhere: on a laptop, or on a schedule in CI.

    python tools/check_apt_pins.py
    python tools/check_apt_pins.py --suggest      # print the lines to paste
    python tools/check_apt_pins.py --write        # rewrite the stale pins in place

Exits 1 when any pin is stale or its package is not found, 0 when every pin is
still offered, and 2 when an index could not be read at all.

The suite comes from the file's own '# pins-for:' line. The archives default to
the two a 32-bit Raspberry Pi OS device uses, for armhf.
"""

import argparse
import gzip
import lzma
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.apt_requirements import (  # noqa: E402
    parse_apt_requirements, pinned_versions, pins_target,
)

DEFAULT_ARCHIVES = (
    'http://raspbian.raspberrypi.com/raspbian',
    'http://archive.raspberrypi.com/debian',
)
DEFAULT_COMPONENTS = ('main',)
DEFAULT_ARCH = 'armhf'


# ── Debian version ordering ──────────────────────────────────────────────────
# Where two archives offer the same package (hostapd is in both), apt installs
# the higher version, so "current" has to mean what apt would pick. This is
# dpkg's own comparison: epoch, then upstream, then revision, each compared as
# alternating non-digit and digit runs, with '~' sorting before everything,
# even the end of the string.

def _order(c):
    if c == '~':
        return -1
    if c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _compare_part(a, b):
    while a or b:
        a_str = re.match(r'^[^\d]*', a).group(0)
        b_str = re.match(r'^[^\d]*', b).group(0)
        a, b = a[len(a_str):], b[len(b_str):]
        for i in range(max(len(a_str), len(b_str))):
            ca = _order(a_str[i]) if i < len(a_str) else 0
            cb = _order(b_str[i]) if i < len(b_str) else 0
            if ca != cb:
                return -1 if ca < cb else 1
        a_num = re.match(r'^\d*', a).group(0)
        b_num = re.match(r'^\d*', b).group(0)
        a, b = a[len(a_num):], b[len(b_num):]
        na, nb = int(a_num or 0), int(b_num or 0)
        if na != nb:
            return -1 if na < nb else 1
    return 0


def _split(version):
    epoch, _, rest = version.rpartition(':') if ':' in version else ('0', '', version)
    upstream, _, revision = rest.rpartition('-') if '-' in rest else (rest, '', '0')
    return int(epoch or 0), upstream, revision


def compare_versions(a, b):
    """-1, 0 or 1, as dpkg --compare-versions orders a against b."""
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _compare_part(ua, ub) or _compare_part(ra, rb)


def newest(versions):
    best = None
    for v in versions:
        if best is None or compare_versions(v, best) > 0:
            best = v
    return best


# ── Package indexes ──────────────────────────────────────────────────────────

def _fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'mempaper-check-apt-pins'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def read_index(archive, suite, component, arch):
    """{package: {versions}} from one archive's Packages index."""
    base = f'{archive.rstrip("/")}/dists/{suite}/{component}/binary-{arch}/Packages'
    last_err = None
    for suffix, decode in (('.xz', lzma.decompress), ('.gz', gzip.decompress), ('', bytes)):
        try:
            text = decode(_fetch(base + suffix)).decode('utf-8', 'replace')
            break
        except (urllib.error.URLError, OSError, lzma.LZMAError, EOFError) as e:
            last_err = e
    else:
        raise RuntimeError(f'{base}[.xz|.gz]: {last_err}')

    offered = {}
    name = None
    for line in text.splitlines():
        if line.startswith('Package:'):
            name = line.split(':', 1)[1].strip()
        elif line.startswith('Version:') and name:
            offered.setdefault(name, set()).add(line.split(':', 1)[1].strip())
        elif not line.strip():
            name = None
    return offered


def check(pins, offered):
    """[(name, pinned, status, current)], status one of ok / stale / missing."""
    rows = []
    for name, pinned in pins.items():
        versions = offered.get(name)
        if not versions:
            rows.append((name, pinned, 'missing', None))
        elif pinned in versions:
            rows.append((name, pinned, 'ok', newest(versions)))
        else:
            rows.append((name, pinned, 'stale', newest(versions)))
    return rows


def rewrite(path, replacements):
    """Swap 'name=old' for 'name=new' in place, keeping comments and layout."""
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    for name, (old, new) in replacements.items():
        text = re.sub(rf'(?m)^(\s*{re.escape(name)}=){re.escape(old)}(?=\s|$)',
                      lambda m: m.group(1) + new, text)
        # The header lists pinned packages as examples; keep those in step too.
        text = text.replace(f'{name}={old}', f'{name}={new}')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--file', default=os.path.join(root, 'apt-requirements.txt'))
    ap.add_argument('--suite', help="default: the file's '# pins-for:' line")
    ap.add_argument('--arch', default=DEFAULT_ARCH)
    ap.add_argument('--archive', action='append', help='repeatable; default: the Raspberry Pi OS archives')
    ap.add_argument('--component', action='append', help='repeatable; default: main')
    ap.add_argument('--suggest', action='store_true', help='print replacement lines for stale pins')
    ap.add_argument('--write', action='store_true', help='rewrite stale pins in the file')
    ap.add_argument('--markdown', action='store_true', help='report as a markdown table (for CI issues)')
    args = ap.parse_args()

    suite = args.suite or pins_target(args.file)
    if not suite:
        print("No '# pins-for:' line in the file and no --suite given.", file=sys.stderr)
        return 2
    pins = pinned_versions(parse_apt_requirements(args.file, apply_pins=True))
    if not pins:
        print('No pinned packages - nothing to check.')
        return 0

    offered = {}
    for archive in args.archive or DEFAULT_ARCHIVES:
        for component in args.component or DEFAULT_COMPONENTS:
            try:
                for name, versions in read_index(archive, suite, component, args.arch).items():
                    offered.setdefault(name, set()).update(versions)
            except RuntimeError as e:
                print(f'Could not read index: {e}', file=sys.stderr)
                return 2

    rows = check(pins, offered)
    bad = [r for r in rows if r[2] != 'ok']

    if args.markdown:
        print(f'Pinned packages checked against {suite}/{args.arch}:\n')
        print('| Package | Pinned | Archive offers | Status |')
        print('|---|---|---|---|')
        for name, pinned, status, current in rows:
            print(f'| {name} | `{pinned}` | `{current or "-"}` | {status} |')
    else:
        width = max(len(r[0]) for r in rows)
        for name, pinned, status, current in rows:
            note = '' if status == 'ok' else f'  -> archive has {current}' if current else '  -> not in archive'
            print(f'{name:<{width}}  {pinned:<32} {status.upper():<7}{note}')

    stale = {name: (pinned, current) for name, pinned, status, current in rows if status == 'stale'}
    if args.suggest and stale:
        print('\nReplacement lines for apt-requirements.txt:')
        for name, (_old, new) in stale.items():
            print(f'{name}={new}')
    if args.write and stale:
        rewrite(args.file, stale)
        print(f'\nRewrote {len(stale)} pin(s) in {args.file}.')

    if bad:
        print(f'\n{len(bad)} of {len(rows)} pins are not offered by the archive.', file=sys.stderr)
        return 1
    print(f'\nAll {len(rows)} pins are offered by the archive.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
