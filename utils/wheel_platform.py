"""Installed extension modules holding instructions this CPU cannot execute.

A native module built for a higher ARM generation than the hardware implements
imports, and usually runs, until a code path reaches an instruction the CPU does
not have; then it raises SIGILL, which kills the interpreter with no traceback
at whatever moment that path first runs.

The question is answered from the compiled code, not from packaging metadata.
Wheel tags cannot settle it: piwheels builds on ARMv7 hardware and names the
result linux_armv6l, while the WHEEL file inside keeps the build host's tag - so
a correct, ARMv6-compatible wheel declares armv7l and comparing tags reports
every one of them as wrong, forever. Nothing in the metadata distinguishes
"built on armv7, targeted at armv6" from "armv7 code".

The ELF does. Every ARM object carries a .ARM.attributes section whose
Tag_CPU_arch names the architecture the compiler was targeting, and e_machine
names the instruction set. Reading those from the installed .so files says what
the code actually requires, which is the property that decides whether it runs.

Anything that needs rebuilding is recorded and worked through in the background
after a restart rather than holding an update open. A published wheel for this
platform is tried first - fetched in seconds where a source build costs tens of
minutes - and only then a build from source.
"""

import collections
import os
import platform
import struct
import subprocess
import sysconfig
import threading
import time
from importlib.metadata import distributions

# Written by the updater, read at startup. One "name==version" per line, with an
# optional ";attempts" suffix so a package that cannot build is not retried for
# ever on every boot.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REBUILD_FLAG = '.wheel-rebuild-needed'
MAX_ATTEMPTS = 3

# How long a source build may take before it is abandoned. numpy's meson build
# on a Pi Zero runs for hours, and a cap set to what a fast package needs throws
# away the whole build rather than the last part of it. Long enough that hitting
# it means something is wrong, not merely slow.
SOURCE_BUILD_TIMEOUT = 6 * 3600

# A wheel is fetched, not built. Anything slower than this is a network problem,
# and waiting hours for it only delays finding that out.
WHEEL_FETCH_TIMEOUT = 900

# Packages the worker doing the rebuilding is itself running on. pip replaces a
# package by uninstalling it first, so rebuilding one of these pulls the runtime
# out from under the process, which systemd then restarts. Queued last, that
# costs only the package itself instead of everything queued behind it.
DEFER_LAST = frozenset({'gevent', 'greenlet'})


def queue_order(entries):
    """[(name, version, attempts)] with the runtime's own packages last."""
    return sorted(entries, key=lambda e: e[0].lower().replace('_', '-') in DEFER_LAST)


# ELF machine types, and the ARM ABI's Tag_CPU_arch mapped to the architecture
# generation each value names. Only the ordering of the generations matters: a
# module built for a higher one than the CPU implements can reach an instruction
# the hardware does not have. The M-profile values sit above v7 numerically but
# describe microcontrollers, so they are placed by what they actually require.
EM_ARM = 40
EM_AARCH64 = 183
SHT_ARM_ATTRIBUTES = 0x70000003

_CPU_ARCH_LEVEL = {
    0: 4, 1: 4, 2: 4,            # pre-v4, v4, v4T
    3: 5, 4: 5, 5: 5,            # v5T, v5TE, v5TEJ
    6: 6, 7: 6, 8: 6, 9: 6,      # v6, v6KZ, v6T2, v6K
    10: 7,                       # v7
    11: 6, 12: 6, 13: 7,         # v6-M, v6S-M, v7E-M
    14: 8, 15: 8, 16: 8, 17: 8,  # v8-A and later profiles
}

# Attributes whose value is a NUL-terminated string rather than a ULEB128
# integer. Needed even though none of them are read, because the attribute
# stream is a flat sequence and misreading one loses the position of the rest.
_STRING_ATTRS = frozenset({4, 5, 32, 65, 67})

# Extension modules within one distribution are built together, so a handful
# settles it. On a Pi this is the difference between reading a few files and
# reading a few hundred.
_MAX_FILES_PER_DIST = 4


def platform_tag():
    """This interpreter's wheel platform tag, e.g. linux_armv6l."""
    return sysconfig.get_platform().replace('-', '_').replace('.', '_')


def _uleb128(buf, i):
    value = shift = 0
    while i < len(buf):
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    return value, i


def _arm_attributes(data, endian):
    """{tag: value} from a .ARM.attributes section, aeabi vendor, file scope."""
    if not data or data[:1] != b'A':
        return {}
    attrs = {}
    pos, size = 1, len(data)
    while pos + 4 <= size:
        section_len, = struct.unpack_from(endian + 'I', data, pos)
        if section_len < 5 or pos + section_len > size:
            break
        section_end = pos + section_len
        cursor = pos + 4
        vendor_end = data.find(b'\0', cursor, section_end)
        if vendor_end < 0:
            break
        vendor = data[cursor:vendor_end]
        cursor = vendor_end + 1
        # Other vendors define their own tags; skipping the whole subsection is
        # the only safe move, since their layout is not ours to parse.
        while vendor == b'aeabi' and cursor < section_end:
            scope, after_scope = _uleb128(data, cursor)
            if after_scope + 4 > section_end:
                break
            sub_len, = struct.unpack_from(endian + 'I', data, after_scope)
            sub_end = cursor + sub_len
            if sub_len < 5 or sub_end > section_end:
                break
            inner = after_scope + 4
            # 1 is file scope, which is what applies to the object as a whole;
            # 2 and 3 scope attributes to sections and symbols and are skipped
            # by their own length.
            while scope == 1 and inner < sub_end:
                tag, inner = _uleb128(data, inner)
                if tag in _STRING_ATTRS:
                    end = data.find(b'\0', inner, sub_end)
                    if end < 0:
                        break
                    attrs.setdefault(tag, data[inner:end].decode('latin-1'))
                    inner = end + 1
                else:
                    value, inner = _uleb128(data, inner)
                    attrs.setdefault(tag, value)
            cursor = sub_end
        pos = section_end
    return attrs


def elf_profile(path):
    """(e_machine, arm generation or None) for an ELF file, None if unreadable.

    The generation is None for anything that is not 32-bit ARM: there is no
    .ARM.attributes section to read, and the machine type alone already settles
    whether the code can run here.
    """
    try:
        with open(path, 'rb') as fh:
            header = fh.read(52)
            if len(header) < 52 or header[:4] != b'\x7fELF':
                return None
            endian = '<' if header[5] == 1 else '>'
            machine, = struct.unpack_from(endian + 'H', header, 18)
            if header[4] == 2 or machine != EM_ARM:
                return machine, None

            sh_off, = struct.unpack_from(endian + 'I', header, 32)
            sh_entsize, sh_num = struct.unpack_from(endian + 'HH', header, 46)
            if not sh_off or not sh_num or sh_entsize < 24:
                return machine, None
            fh.seek(sh_off)
            table = fh.read(sh_entsize * sh_num)
            for index in range(sh_num):
                base = index * sh_entsize
                if base + 24 > len(table):
                    break
                sh_type, = struct.unpack_from(endian + 'I', table, base + 4)
                if sh_type != SHT_ARM_ATTRIBUTES:
                    continue
                offset, length = struct.unpack_from(endian + 'II', table, base + 16)
                fh.seek(offset)
                attrs = _arm_attributes(fh.read(length), endian)
                return machine, _CPU_ARCH_LEVEL.get(attrs.get(6))
            return machine, None
    except (OSError, struct.error):
        return None


def cpu_profile():
    """(e_machine, arm generation) this CPU can execute, or (None, None).

    None means the check does not apply: the SIGILL this guards against is an
    ARM story, and on anything else pip's own tag matching is the whole answer.
    """
    machine = platform.machine().lower()
    if machine in ('aarch64', 'arm64'):
        return EM_AARCH64, 8
    if machine.startswith('armv'):
        digits = ''.join(c for c in machine[4:] if c.isdigit())
        return EM_ARM, int(digits) if digits else 6
    return None, None


def _extension_modules(dist):
    """Absolute paths of the compiled modules a distribution installed."""
    try:
        files = dist.files or []
    except Exception:
        return []
    found = []
    for entry in files:
        name = os.path.basename(str(entry))
        if not (name.endswith('.so') or '.so.' in name):
            continue
        try:
            found.append(str(dist.locate_file(entry)))
        except Exception:
            continue
        if len(found) >= _MAX_FILES_PER_DIST:
            break
    return found


def incompatible_dists():
    """[(name, version, [reasons])] for packages this CPU cannot safely run.

    A distribution with no compiled modules is pure Python and cannot hold an
    instruction this CPU lacks, so it is never reported. Nor is one whose
    modules read as built for this generation or an older one - older ARM code
    runs correctly on newer hardware.
    """
    want_machine, want_level = cpu_profile()
    if want_machine is None:
        return []

    found = []
    for dist in distributions():
        try:
            name = dist.metadata['Name']
        except Exception:
            continue
        if not name:
            continue

        reasons = []
        for path in _extension_modules(dist):
            profile = elf_profile(path)
            if profile is None:
                continue
            machine, level = profile
            if machine != want_machine:
                reasons.append(f'{os.path.basename(path)}: built for machine '
                               f'{machine}, this CPU is {want_machine}')
            elif level is not None and level > want_level:
                reasons.append(f'{os.path.basename(path)}: built for ARMv{level}, '
                               f'this CPU is ARMv{want_level}')
        if reasons:
            found.append((name, dist.version, reasons))
    return sorted(found)


def parse_flag(text):
    """[(name, version, attempts)] from the flag file, skipping exhausted entries."""
    out = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        spec, _, attempts = line.partition(';')
        name, _, version = spec.partition('==')
        if not name or not version:
            continue
        try:
            n = int(attempts) if attempts else 0
        except ValueError:
            n = 0
        if n < MAX_ATTEMPTS:
            out.append((name.strip(), version.strip(), n))
    return out


def format_flag(entries):
    """Flag file body from [(name, version, attempts)]."""
    return ''.join(f'{n}=={v};{a}\n' for n, v, a in entries)


def build_tmpdir():
    """A scratch directory for source builds, on disk rather than in RAM.

    /tmp is tmpfs on Raspberry Pi OS, sized at half of RAM - about 210 MB on a
    512 MB device. Compiling numpy or Cython writes far more object code than
    that, and the assembler then fails with ENOSPC partway through, which reads
    as a compiler error rather than as a filesystem that ran out. The card has
    tens of gigabytes; the build only has to be pointed at it.
    """
    path = os.path.join(PROJECT_DIR, 'cache', 'build-tmp')
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return None


def build_env():
    """Environment for a pip build: unbuffered output, scratch space on disk."""
    env = dict(os.environ, PYTHONUNBUFFERED='1')
    scratch = build_tmpdir()
    if scratch:
        env['TMPDIR'] = scratch
    return env


def rebuild_argv(pip_path, name, version, source=True):
    """pip command that reinstalls a distribution for this device's platform.

    --no-cache-dir stops pip satisfying the request out of the very wheel it
    just downloaded. `source` picks which way the package is obtained: a
    published wheel for this platform, or a build from source when the index
    carries none.

    The source form names the package rather than passing :all:. :all: applies
    to the whole resolution, so pip also compiles the build backend - ninja,
    Cython, patchelf - from source, none of which is what we are trying to
    replace and all of which have wheels. On a Pi Zero that cost 1h44 before
    numpy's own build had started.
    """
    argv = [pip_path, 'install', '--force-reinstall', '--no-cache-dir']
    argv += ['--no-binary', name] if source else ['--only-binary', ':all:']
    return argv + [f'{name}=={version}']


def rebuild(pip_path, name, version, timeout=5400, on_line=None, source=True):
    """Rebuild one distribution from source. Returns (ok, tail).

    Output is streamed to `on_line` as it arrives rather than collected at the
    end, because a build here runs for hours and a caller with nothing to show
    for that time is indistinguishable from one that has hung. Only the tail is
    returned, which is all a failure message needs.

    The timeout is enforced by a watchdog rather than by the read loop: a
    compile can fall silent for a long stretch, so waiting for the next line to
    check the clock would let a stuck build run for ever.
    """
    tail = collections.deque(maxlen=60)
    env = build_env()
    try:
        proc = subprocess.Popen(rebuild_argv(pip_path, name, version, source),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, env=env)
    except Exception as exc:
        return False, str(exc)

    timed_out = threading.Event()

    def _kill():
        timed_out.set()
        try:
            proc.kill()
        except Exception:
            pass

    watchdog = threading.Timer(timeout, _kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
        proc.wait()
    except Exception as exc:
        _kill()
        return False, str(exc)
    finally:
        watchdog.cancel()
        try:
            proc.stdout.close()
        except Exception:
            pass

    if timed_out.is_set():
        return False, f'timed out after {timeout}s\n' + '\n'.join(tail)
    return proc.returncode == 0, '\n'.join(tail)


if __name__ == '__main__':
    # Run on the device to see what the check makes of it:
    #   .venv/bin/python -m utils.wheel_platform
    machine, level = cpu_profile()
    print(f'platform tag : {platform_tag()}')
    if machine is None:
        print(f'cpu          : {platform.machine()} - not ARM, check does not apply')
    else:
        print(f'cpu          : {platform.machine()} '
              f'(ELF machine {machine}, ARMv{level})')
    bad = incompatible_dists()
    if not bad:
        print('every compiled module runs on this CPU')
    else:
        for name, version, reasons in bad:
            print(f'{name}=={version}')
            for reason in reasons:
                print(f'    {reason}')
