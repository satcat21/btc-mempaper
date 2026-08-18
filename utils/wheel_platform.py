"""Installed wheels built for a platform other than this device's.

pip will install a wheel tagged for a neighbouring ARM platform - an armv7l
wheel on an armv6l interpreter, most often, because that is what piwheels and
PyPI publish. It imports, and usually runs, until a code path reaches an
instruction the CPU does not have; then it raises SIGILL, which kills the
interpreter with no traceback at whatever moment that path first runs.

The device tells us which platform it wants: sysconfig reports the tag the
interpreter was built for, and every wheel records the tag it was built for.
Comparing the two finds the mismatches without knowing any package by name, so
this covers armv6l (Pi Zero 1), armv7l (Pi Zero 2 W, Pi 3/4 on 32-bit) and
aarch64 alike, and a dependency added later is covered by the same pass.

A wheel for an older ARM platform runs correctly on a newer one, so a mismatch
is not always a crash - but it is always a build that is not the one this device
would have produced. Both are rebuilt, because "the wheel matches the platform"
is the property worth holding.

A rebuild costs tens of minutes per package here, so callers record what needs
doing and rebuild in the background after a restart rather than holding an
update open.
"""

import subprocess
import sysconfig
from importlib.metadata import distributions

# Written by the updater, read at startup. One "name==version" per line, with an
# optional ";attempts" suffix so a package that cannot build is not retried for
# ever on every boot.
REBUILD_FLAG = '.wheel-rebuild-needed'
MAX_ATTEMPTS = 3


def platform_tag():
    """This interpreter's wheel platform tag, e.g. linux_armv6l."""
    return sysconfig.get_platform().replace('-', '_').replace('.', '_')


def foreign_wheels():
    """[(name, version, [platforms])] for wheels built for another platform.

    A distribution with no WHEEL metadata was not installed from a wheel, and one
    tagged `any` is pure Python; neither carries machine code, so neither can
    hold an instruction this CPU lacks.
    """
    mine = platform_tag()
    found = []
    for dist in distributions():
        try:
            wheel = dist.read_text('WHEEL') or ''
        except Exception:
            continue
        tags = [ln.split(':', 1)[1].strip()
                for ln in wheel.splitlines() if ln.startswith('Tag:')]
        if not tags:
            continue
        platforms = {t.rsplit('-', 1)[-1] for t in tags}
        if 'any' in platforms or mine in platforms:
            continue
        try:
            name = dist.metadata['Name']
        except Exception:
            continue
        if name:
            found.append((name, dist.version, sorted(platforms)))
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


def rebuild_argv(pip_path, name, version):
    """pip command that replaces a wheel with a build from this device's source.

    --no-binary :all: is the whole point; --no-cache-dir stops pip satisfying the
    request out of the very wheel it just downloaded.
    """
    return [pip_path, 'install', '--force-reinstall', '--no-cache-dir',
            '--no-binary', ':all:', f'{name}=={version}']


def rebuild(pip_path, name, version, timeout=5400):
    """Rebuild one distribution from source. Returns (ok, output)."""
    try:
        proc = subprocess.run(rebuild_argv(pip_path, name, version),
                              capture_output=True, text=True, timeout=timeout)
        return proc.returncode == 0, (proc.stdout or '') + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        return False, f'timed out after {timeout}s'
    except Exception as exc:
        return False, str(exc)
