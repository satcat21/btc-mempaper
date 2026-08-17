"""The weekly meme-sync cron entry: one implementation, two callers.

install.sh writes this entry at install time so the schedule exists on the
device before the app has ever run, and mempaper_app rewrites it whenever the
Meme Sync settings change. Those two used to be one implementation and one
absence — the installer wrote nothing at all, so a fresh device had no entry
until the service had started at least once with the toggle already on.

Putting the line in one place is what keeps them honest. The marker, the
schedule fields, the interpreter choice and the log path all have to agree
between installer and app, because whichever runs last rewrites the block; two
copies of that format would drift and the drift would only show up as a job
that silently stopped running.

Entry point for shell callers:

    python3 -m utils.meme_sync_cron --apply [--config config/config.json]

It reads the config, rewrites the block in the current user's crontab, and
prints what it did. Run it as the user that owns the job (the installer uses
`sudo -u mempaper`), because `crontab` always edits the caller's own table.
"""

import argparse
import json
import os
import posixpath
import subprocess
import sys

from utils.paths import PROJECT_ROOT

# Tags every line this module writes, so a rewrite can find its own previous
# block without touching anything else in the user's crontab. Both the active
# line and the commented-out placeholder carry it.
MARKER = '# mempaper-meme-sync'

# Hand-written entries from before this module existed. They predate the marker,
# so the marker sweep cannot see them, and leaving one in place means two
# downloaders on the same device: the old line and the one written here, hours
# apart, both walking the catalogue and writing the same directory. Matched by
# the script they invoke rather than by their exact text, because these were
# typed by hand and no two are formatted alike.
LEGACY_SCRIPTS = ('sync_memes.py', 'download_all_memes.py')

DEFAULT_SCHEDULE = {'minute': '0', 'hour': '13', 'day': '4'}


def _interpreter(project_dir):
    """Full path to the venv interpreter, falling back to python3.

    cron runs with a bare environment and nothing activated, so the interpreter
    has to be named by absolute path — requests and PySocks are installed in the
    venv only. The fallback is for a dev checkout without a venv; on a real
    install .venv always exists, and sync_memes.py warns when it is run outside
    one rather than failing with a bare ImportError in a log nobody reads.
    """
    # posixpath, not os.path: this string goes into a crontab on a Linux device,
    # so it must not pick up the separator of whatever machine rendered it.
    venv_python = posixpath.join(project_dir, '.venv', 'bin', 'python')
    return venv_python if os.path.exists(venv_python) else 'python3'


def _schedule(config):
    """(minute, hour, day) as strings, falling back to the shipped default.

    install.sh randomises all three per device and records that it has done so,
    so the world's mempapers do not all reach the meme host in the same minute.
    """
    return (
        str(config.get('meme_sync_minute', DEFAULT_SCHEDULE['minute'])),
        str(config.get('meme_sync_hour', DEFAULT_SCHEDULE['hour'])),
        str(config.get('meme_sync_day', DEFAULT_SCHEDULE['day'])),
    )


def build_cron_line(config, project_dir=PROJECT_ROOT, commented=False):
    """Render the crontab line for the current settings.

    The date banner is deliberate: the log is append-only and a run is weekly,
    so without a timestamp per run the file reads as one undifferentiated wall
    of progress output. It is `;` rather than `&&` so a failed echo — a full
    disk, most likely — still lets the download attempt run.

    No `%` appears anywhere in the line by construction. cron treats an
    unescaped `%` as a newline and would truncate the command at it, which is
    why the banner uses `$(date)` with no format string.
    """
    minute, hour, day = _schedule(config)
    python = _interpreter(project_dir)
    script = posixpath.join(project_dir, 'tools', 'sync_memes.py')
    log_file = posixpath.join(project_dir, 'logs', 'meme-sync.log')
    tor_flag = ' --tor' if config.get('tor_meme_downloads', False) else ''

    line = (
        f'{minute} {hour} * * {day} '
        f'echo "===== $(date) =====" >> {log_file}; '
        f'cd {project_dir} && {python} {script} --update{tor_flag} '
        f'>> {log_file} 2>&1 {MARKER}'
    )
    return f'#{line}' if commented else line


def _is_ours(line):
    """True for a line this module wrote on a previous run."""
    return MARKER in line


def _is_legacy(line):
    """True for a pre-marker hand-written meme-download entry.

    Only command lines count. A comment that merely mentions the script is
    somebody's note to themselves and is left alone — this sweep exists to stop
    a second downloader from running, not to tidy up prose.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return False
    return any(script in stripped for script in LEGACY_SCRIPTS)


def render_block(config, project_dir=PROJECT_ROOT):
    """The marked lines to install, active or commented depending on the toggle.

    When the feature is off the block is still written, commented out. That is
    what makes the schedule visible on a device that has never enabled it: the
    randomised day and hour are otherwise buried in config.json, and `crontab -l`
    — the first place anyone looks to answer "is this thing scheduled?" — would
    show nothing at all and imply the feature does not exist.
    """
    enabled = config.get('meme_sync_enabled', False)
    if enabled:
        return [
            f'{MARKER}: weekly meme download. Turn off in the web UI under Meme Sync.',
            build_cron_line(config, project_dir, commented=False),
        ]
    return [
        f'{MARKER}: weekly meme download, currently disabled. '
        f'Turn on in the web UI under Meme Sync. Do not uncomment by hand, '
        f'the app rewrites this block from config.json.',
        build_cron_line(config, project_dir, commented=True),
    ]


def _read_crontab():
    """Current crontab text, or '' when there is none.

    An empty crontab exits non-zero on most implementations, which is not an
    error worth distinguishing from an empty one here.
    """
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ''


def apply_meme_sync_crontab(config, project_dir=PROJECT_ROOT, quiet=False):
    """Rewrite the meme-sync block in the calling user's crontab.

    Returns (ok, message). Never raises on a crontab failure: this runs during
    app startup and during install, and neither should be taken down by a cron
    table that could not be written.
    """
    existing = _read_crontab()

    kept, removed_legacy = [], []
    for line in existing.splitlines():
        if _is_ours(line):
            continue
        if _is_legacy(line):
            removed_legacy.append(line.strip())
            continue
        kept.append(line)

    # Drop trailing blanks so repeated rewrites do not grow a gap before the
    # block each time.
    while kept and not kept[-1].strip():
        kept.pop()

    lines = kept + ([''] if kept else []) + render_block(config, project_dir)

    # The app reads and the cron job writes this directory; create it here so
    # the first scheduled run does not fail on a missing path. Created by
    # whichever user is applying the entry, which is the user that will run it.
    try:
        os.makedirs(os.path.join(project_dir, 'logs'), exist_ok=True)
    except OSError as e:
        if not quiet:
            print(f'WARNING: could not create the log directory: {e}')

    new_crontab = '\n'.join(lines)
    if new_crontab and not new_crontab.endswith('\n'):
        new_crontab += '\n'

    proc = subprocess.run(['crontab', '-'], input=new_crontab, text=True,
                          capture_output=True)
    if proc.returncode != 0:
        msg = f'Failed to update the meme sync crontab: {proc.stderr.strip()}'
        if not quiet:
            print(f'WARNING: {msg}')
        return False, msg

    for old in removed_legacy:
        if not quiet:
            print(f'Replaced a hand-written meme download entry: {old}')

    minute, hour, day = _schedule(config)
    if config.get('meme_sync_enabled', False):
        tor = '  (Tor)' if config.get('tor_meme_downloads', False) else ''
        msg = f'Meme sync scheduled: {minute} {hour} * * {day}{tor}'
        if not quiet:
            print(msg)
    else:
        msg = (f'Meme sync not enabled - schedule written commented out '
               f'({minute} {hour} * * {day})')
        if not quiet:
            print(msg)
    return True, msg


def _load_config(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        print(f'WARNING: no config at {path} - using defaults')
        return {}
    except (OSError, json.JSONDecodeError) as e:
        print(f'ERROR: could not read {path}: {e}')
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Write the mempaper weekly meme-sync crontab entry for the current user.')
    parser.add_argument('--apply', action='store_true',
                        help='Rewrite the crontab block from the config file.')
    parser.add_argument('--show', action='store_true',
                        help='Print the lines that --apply would install, and exit.')
    parser.add_argument('--config', default=os.path.join(PROJECT_ROOT, 'config', 'config.json'),
                        help='Path to config.json (default: config/config.json)')
    args = parser.parse_args(argv)

    if not args.apply and not args.show:
        parser.error('nothing to do: pass --apply or --show')

    config = _load_config(args.config)
    if config is None:
        return 1

    if args.show:
        for line in render_block(config, PROJECT_ROOT):
            print(line)
        return 0

    ok, _ = apply_meme_sync_crontab(config, PROJECT_ROOT)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
