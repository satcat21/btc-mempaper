"""Which pinned versions install as wheels on a target device, and which compile.

Run before publishing a requirements.txt. For every pin it finds the wheel a
device would actually download and reads the machine code inside it, so a
release can be chosen for "installs in minutes" instead of discovering on a Pi
Zero that one package takes most of a night.

    python tools/check_wheels.py
    python tools/check_wheels.py --platform linux_armv6l --python cp313
    python tools/check_wheels.py --suggest        # name the newest safe version

Exits non-zero when anything would be built from source, so it can gate a
release.

The filename cannot answer this. piwheels builds on ARMv8 hardware and publishes
the result under linux_armv6l and linux_armv7l names, so a wheel can be tagged
for a CPU it cannot run on - numpy has been shipping that way since 2.2.6. What
settles it is Tag_CPU_arch in the ELF's .ARM.attributes section, which names the
architecture the compiler was targeting. That is what this reads, from the same
bytes the device would install.
"""

import argparse
import io
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.wheel_platform import (  # noqa: E402
    _CPU_ARCH_LEVEL, _arm_attributes, cpu_profile, platform_tag,
)

PIWHEELS = 'https://www.piwheels.org/simple/{name}/'
PYPI = 'https://pypi.org/simple/{name}/'
SHT_ARM_ATTRIBUTES = 0x70000003
EM_ARM = 40


def normalise(name):
    """PyPI's canonical form, which is also the path both indexes serve."""
    return re.sub(r'[-_.]+', '-', name.split('[')[0]).lower()


def read_index(name):
    """[(version, url)] for every wheel both indexes publish for this project.

    piwheels first, because it is where a Pi finds ARM builds; PyPI second for
    packages it does not carry. Hrefs are resolved against the index URL rather
    than assembled by hand - piwheels serves files from archive hosts, so a
    guessed path 404s.
    """
    found = []
    for template in (PIWHEELS, PYPI):
        url = template.format(name=normalise(name))
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                html = response.read().decode('utf-8', 'replace')
        except Exception:
            continue
        for href in re.findall(r'href="([^"]+\.whl)[^"]*"', html):
            absolute = urllib.parse.urljoin(url, href)
            filename = absolute.rsplit('/', 1)[-1]
            version = filename.split('-')[1]
            found.append((version, filename, absolute))
    return found


def wheels_for(index, version, platform, python):
    """Wheels a device on this platform and interpreter would consider."""
    out = []
    for ver, filename, url in index:
        if ver != version:
            continue
        if filename.endswith('-none-any.whl'):
            out.append((filename, url, True))
        elif platform in filename and (python in filename or 'abi3' in filename):
            out.append((filename, url, False))
    return out


def arm_level(blob):
    """Highest ARM generation any compiled module in the wheel requires.

    None when nothing inside carries ARM machine code - a pure-Python wheel, or
    one built for another architecture entirely, which the caller reports
    separately.
    """
    worst = None
    archive = zipfile.ZipFile(io.BytesIO(blob))
    for entry in archive.namelist():
        base = entry.rsplit('/', 1)[-1]
        if not (base.endswith('.so') or '.so.' in base):
            continue
        data = archive.read(entry)
        if data[:4] != b'\x7fELF' or data[4] == 2:
            continue
        endian = '<' if data[5] == 1 else '>'
        machine, = struct.unpack_from(endian + 'H', data, 18)
        if machine != EM_ARM:
            continue
        sh_off, = struct.unpack_from(endian + 'I', data, 32)
        sh_entsize, sh_num = struct.unpack_from(endian + 'HH', data, 46)
        for index in range(sh_num):
            header = sh_off + index * sh_entsize
            if header + 24 > len(data):
                break
            sh_type, = struct.unpack_from(endian + 'I', data, header + 4)
            if sh_type != SHT_ARM_ATTRIBUTES:
                continue
            offset, length = struct.unpack_from(endian + 'II', data, header + 16)
            attrs = _arm_attributes(data[offset:offset + length], endian)
            level = _CPU_ARCH_LEVEL.get(attrs.get(6))
            if level is not None and (worst is None or level > worst):
                worst = level
            break
    return worst


def fetch(url, timeout=180):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def version_key(version):
    return [int(part) if part.isdigit() else part
            for part in re.split(r'[._-]', version)]


def verdict(index, version, platform, python, want_level):
    """(status, detail) for one pinned version."""
    candidates = wheels_for(index, version, platform, python)
    if not candidates:
        return 'BUILDS', 'no wheel published for this platform'
    filename, url, pure = candidates[-1]
    if pure:
        return 'OK', 'pure Python'
    try:
        level = arm_level(fetch(url))
    except Exception as exc:
        return 'UNKNOWN', f'{type(exc).__name__} reading {filename}'
    if level is None:
        return 'OK', 'no ARM code'
    if want_level is None or level <= want_level:
        return 'OK', f'ARMv{level}'
    return 'BUILDS', f'wheel is ARMv{level}, device is ARMv{want_level}'


def newest_safe(index, below, platform, python, want_level):
    """The newest published version whose wheel runs on this device."""
    versions = sorted({v for v, _, _ in index}, key=version_key, reverse=True)
    for candidate in versions:
        if re.search(r'[a-z]', candidate.replace('post', '')):
            continue                      # skip rc/alpha/beta
        if version_key(candidate) >= version_key(below):
            continue
        status, _ = verdict(index, candidate, platform, python, want_level)
        if status == 'OK':
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--requirements', default='requirements.txt')
    parser.add_argument('--platform', default=None,
                        help='wheel platform tag, e.g. linux_armv6l')
    parser.add_argument('--python', default=f'cp{sys.version_info.major}{sys.version_info.minor}')
    parser.add_argument('--arm-level', type=int, default=None,
                        help='ARM generation the device implements, e.g. 6')
    parser.add_argument('--suggest', action='store_true',
                        help='name the newest safe version for anything that builds')
    args = parser.parse_args()

    platform = args.platform or platform_tag()
    want_level = args.arm_level
    if want_level is None:
        _, want_level = cpu_profile()
    if want_level is None and platform.startswith('linux_armv'):
        digits = ''.join(c for c in platform[len('linux_armv'):] if c.isdigit())
        want_level = int(digits) if digits else None

    print(f'target: {platform}, {args.python}'
          + (f', ARMv{want_level}' if want_level else ''))
    print('-' * 72)

    builds = []
    with open(args.requirements) as fh:
        for line in fh:
            line = line.split('#', 1)[0].strip()
            if not line or '==' not in line:
                continue
            name, _, version = line.partition('==')
            index = read_index(name)
            if not index:
                print(f'{name:22} {version:12} UNKNOWN  not on either index')
                continue
            status, detail = verdict(index, version, platform, args.python, want_level)
            note = ''
            if status == 'BUILDS':
                builds.append(name)
                if args.suggest:
                    safe = newest_safe(index, version, platform, args.python, want_level)
                    note = f'; newest safe: {safe}' if safe else '; none found'
            print(f'{name:22} {version:12} {status:8} {detail}{note}')

    print('-' * 72)
    if builds:
        print(f'{len(builds)} package(s) would be built from source: '
              f'{", ".join(builds)}')
        return 1
    print('every pinned package installs as a wheel this device can run')
    return 0


if __name__ == '__main__':
    sys.exit(main())
