"""What is actually installed, written back in the shape of the file that asked for it.

After an install or an upgrade the device knows something the repository does
not: the exact version of every declared dependency that the archive and PyPI
resolved to, on this OS, for this architecture. That set is the one known-good
combination — it booted, it rendered, it is running. Nothing records it, so the
next device resolves the whole set again from scratch and may land somewhere
else entirely.

These reports capture it. Each is a copy of its source file with the resolved
version filled in on every package line and everything else — comments, blank
lines, ordering, the inline notes explaining why a package is there — carried
across untouched. That is the whole point of matching the original layout: once
a report has been tested on a device, it can be copied over the file it came
from and reviewed as a diff of versions rather than read as a new document.

    cache/currently_installed_apt-requirements.txt
    cache/currently_installed_requirements.txt

They are reports, not inputs. Nothing reads them back; promoting one is a
deliberate copy by a human who has decided this particular combination is worth
pinning everywhere.

A declared package that is not installed keeps its original line. The report has
to stay a valid requirements file, and inventing a version for something absent
would be the one way to make it lie.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime

from utils.apt_requirements import package_names, parse_apt_requirements

# name, optional [extras], then whatever version specifier and marker follow.
_PIP_LINE = re.compile(r'^(?P<name>[A-Za-z0-9._-]+)(?P<extras>\[[^\]]*\])?(?P<rest>.*)$')


def _split_comment(line):
    """(code, comment) where comment keeps its leading whitespace and '#'."""
    idx = line.find('#')
    if idx < 0:
        return line, ''
    return line[:idx], line[idx:]


def _normalise(name):
    """PyPI treats '-', '_' and case as the same character. pip freeze does not."""
    return re.sub(r'[-_.]+', '-', name).lower()


def _header(kind, source_name, total, resolved):
    return [
        f'# Resolved {kind} versions as installed on this device.',
        f'# Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} from {source_name}.',
        '#',
        f'# {resolved} of {total} declared packages were installed and have been',
        '# pinned below; any that were not keep their original line.',
        '#',
        '# This is a report, nothing reads it. Once this combination has been',
        f'# tested, copy it over {source_name} to make these versions the',
        '# declared ones — the layout matches so it reviews as a version diff.',
        '#',
    ]


# ── apt ───────────────────────────────────────────────────────────────────

def installed_apt_versions(names):
    """{name: version} for those of `names` dpkg has installed."""
    if not names:
        return {}
    try:
        proc = subprocess.run(
            ['dpkg-query', '-W', '-f=${Package} ${Status} ${Version}\\n'] + list(names),
            capture_output=True, text=True, timeout=30
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    out = {}
    for line in (proc.stdout or '').splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == 'installed':
            out[parts[0]] = parts[4]
    return out


def render_apt_report(source_path, versions):
    """The source file with '=version' filled in on every installed package."""
    with open(source_path, encoding='utf-8') as f:
        source_lines = f.read().splitlines()

    entries = parse_apt_requirements(source_path)
    total = len(entries)
    resolved = sum(1 for n in package_names(entries) if n in versions)

    body = []
    for raw in source_lines:
        code, comment = _split_comment(raw)
        stripped = code.strip()
        if not stripped:
            body.append(raw)
            continue
        name = stripped.split('=', 1)[0].strip()
        version = versions.get(name)
        if not version:
            body.append(raw)
            continue
        lead = code[:len(code) - len(code.lstrip())]
        trail = code[len(code.rstrip()):]
        body.append(f'{lead}{name}={version}{trail}{comment}')

    return '\n'.join(_header('apt', os.path.basename(source_path), total, resolved)
                     + [''] + body) + '\n'


# ── pip ───────────────────────────────────────────────────────────────────

def installed_pip_versions(venv_pip):
    """{normalised name: version} from the project virtualenv."""
    try:
        proc = subprocess.run(
            [venv_pip, 'list', '--format=freeze', '--disable-pip-version-check'],
            capture_output=True, text=True, timeout=60
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    if proc.returncode != 0:
        return {}
    out = {}
    for line in (proc.stdout or '').splitlines():
        if '==' in line:
            name, _, version = line.partition('==')
            out[_normalise(name.strip())] = version.strip()
    return out


def render_pip_report(source_path, versions):
    """The source file with every requirement pinned to the installed version.

    Extras and environment markers are preserved: 'qrcode[pil]>=7.4' becomes
    'qrcode[pil]==8.2', because the extras are part of what was asked for and
    dropping them would change what a future install resolves.

    Commented-out optional packages stay commented. They are documentation of
    what *could* be installed - hardware GPIO libraries, omni-epd - and pinning
    a version into a line nothing reads would only make it stale.
    """
    with open(source_path, encoding='utf-8') as f:
        source_lines = f.read().splitlines()

    total = 0
    resolved = 0
    body = []
    for raw in source_lines:
        code, comment = _split_comment(raw)
        stripped = code.strip()
        if not stripped:
            body.append(raw)
            continue
        m = _PIP_LINE.match(stripped)
        if not m:
            body.append(raw)
            continue
        total += 1
        name = m.group('name')
        extras = m.group('extras') or ''
        rest = m.group('rest') or ''
        version = versions.get(_normalise(name))
        if not version:
            body.append(raw)
            continue
        resolved += 1
        # Keep an environment marker if the line carries one; drop only the
        # version specifier, which is the part being replaced.
        marker = ''
        if ';' in rest:
            marker = rest[rest.index(';'):]
        lead = code[:len(code) - len(code.lstrip())]
        trail = code[len(code.rstrip()):]
        body.append(f'{lead}{name}{extras}=={version}{marker}{trail}{comment}')

    return '\n'.join(_header('pip', os.path.basename(source_path), total, resolved)
                     + [''] + body) + '\n'


# ── the one call sites use ────────────────────────────────────────────────

def write_installed_reports(project_root, log=None):
    """Write both reports into cache/. Returns the paths actually written.

    Never raises. This runs at the tail of an update that has already
    succeeded, and a report that could not be written is not a reason to
    report the update as failed - the device is upgraded either way.
    """
    written = []

    def _say(msg):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    cache_dir = os.path.join(project_root, 'cache')
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError as exc:
        _say(f'Could not create {cache_dir}: {exc}')
        return written

    apt_src = os.path.join(project_root, 'apt-requirements.txt')
    if os.path.exists(apt_src):
        try:
            entries = parse_apt_requirements(apt_src)
            versions = installed_apt_versions(package_names(entries))
            if versions:
                dest = os.path.join(cache_dir, 'currently_installed_apt-requirements.txt')
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(render_apt_report(apt_src, versions))
                written.append(dest)
                _say(f'Wrote {os.path.relpath(dest, project_root)} '
                     f'({len(versions)} packages pinned)')
        except Exception as exc:
            _say(f'Could not write apt version report: {exc}')

    pip_src = os.path.join(project_root, 'requirements.txt')
    venv_pip = os.path.join(project_root, '.venv', 'bin', 'pip')
    if os.path.exists(pip_src) and os.path.exists(venv_pip):
        try:
            versions = installed_pip_versions(venv_pip)
            if versions:
                dest = os.path.join(cache_dir, 'currently_installed_requirements.txt')
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(render_pip_report(pip_src, versions))
                written.append(dest)
                _say(f'Wrote {os.path.relpath(dest, project_root)}')
        except Exception as exc:
            _say(f'Could not write pip version report: {exc}')

    return written
