"""Work through the package build queue, outside the web app's control group.

Started by mempaper as `sudo systemctl start mempaper-build.service`, never
directly. What it does is decided entirely by the queue file mempaper writes, so
the app never needs a privileged command per job - only permission to start and
stop one fixed unit.

Everything a build produces goes to files rather than to a socket, because the
reader outlives no part of this: the app restarts, the browser reloads, and a
build runs for hours across both. The status file is the whole state, so a page
opened at any point shows the same thing.

Handlers return True when they changed the virtualenv, 'skipped' when the job
turned out to be unnecessary, and False when it failed. Only a real change earns
the restart at the end.

Jobs are attempted in order. One that fails goes to the back with its attempt
count raised, so a restart makes progress on the packages that can be fixed
rather than spending another hour on the one that just failed; past MAX_ATTEMPTS
it is dropped rather than retried for ever.
"""

import json
import os
import signal
import subprocess
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from utils.wheel_platform import (  # noqa: E402
    MAX_ATTEMPTS, SOURCE_BUILD_TIMEOUT, WHEEL_FETCH_TIMEOUT,
    incompatible_dists, rebuild,
)

CACHE_DIR = os.path.join(PROJECT_DIR, 'cache')
QUEUE_FILE = os.path.join(CACHE_DIR, 'build-queue.json')
STATUS_FILE = os.path.join(CACHE_DIR, 'build-status.json')
LOG_FILE = os.path.join(CACHE_DIR, 'build.log')
VENV_PIP = os.path.join(PROJECT_DIR, '.venv', 'bin', 'pip')

# The log is read by a browser and held in memory while it is displayed, so it
# is capped rather than allowed to grow with the compiler's output.
MAX_LOG_LINES = 400

# One line every few seconds is enough to show a build is moving. pip and the
# compilers under it emit thousands.
LOG_THROTTLE_SECONDS = 5

_stopping = False


def _stop(signum, frame):
    """Record that a stop was asked for; the job loop notices between jobs."""
    global _stopping
    _stopping = True


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def _read_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """Write via a temporary file, so a reader never sees half a document."""
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w') as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


class Run:
    """The state of one pass through the queue, mirrored to disk as it changes."""

    def __init__(self, jobs, restart_when_done):
        self.jobs = jobs
        self.restart_when_done = restart_when_done
        self.total = len(jobs)
        self.index = 0
        self.current = None
        self.done = []
        self.failed = []
        self.log = []
        self.started = time.time()

    def log_line(self, line):
        self.log.append(line)
        if len(self.log) > MAX_LOG_LINES:
            del self.log[:-MAX_LOG_LINES]
        print(line, flush=True)
        self.publish()

    def publish(self, running=True, finished=None):
        _write_json(STATUS_FILE, {
            'running': running,
            'started': self.started,
            'finished': finished,
            'total': self.total,
            'index': self.index,
            'current': self.current,
            'done': self.done,
            'failed': self.failed,
            'log': self.log,
        })

    def save_queue(self):
        if self.jobs:
            _write_json(QUEUE_FILE, {'jobs': self.jobs,
                                     'restart_when_done': self.restart_when_done})
        else:
            try:
                os.remove(QUEUE_FILE)
            except OSError:
                pass


def _job_label(job):
    kind = job.get('kind')
    if kind == 'rebuild':
        return job.get('spec', 'unknown')
    if kind == 'pip-requirements':
        return 'requirements.txt'
    if kind == 'pillow':
        return 'Pillow'
    return kind or 'unknown'


def _stream(run, label):
    """A throttled sink for a build's output, shared by every job kind."""
    last = [0.0]

    def emit(line):
        now = time.monotonic()
        if now - last[0] < LOG_THROTTLE_SECONDS:
            return
        last[0] = now
        run.log_line(line)

    return emit


def _do_rebuild(run, job):
    """Reinstall one package so its compiled code suits this CPU.

    A published wheel is tried first: fetching one takes seconds where building
    the same package takes hours, and most are published for this platform. pip
    reports success for a wheel whose code is still wrong, so the result is
    rechecked against the ELF rather than trusted.
    """
    spec = job.get('spec', '')
    name, _, version = spec.partition('==')
    if not name or not version:
        run.log_line(f'skipping malformed job: {spec}')
        return True

    if not any(n == name for n, _, _ in incompatible_dists()):
        run.log_line(f'{spec}: already runs on this CPU, skipping')
        return 'skipped'

    ok, output = rebuild(VENV_PIP, name, version, source=False,
                         timeout=WHEEL_FETCH_TIMEOUT, on_line=_stream(run, spec))
    if ok and any(n == name for n, _, _ in incompatible_dists()):
        ok = False
        run.log_line(f'{spec}: the published wheel is built for another CPU too')
    if ok:
        run.log_line(f'{spec}: installed a wheel for this CPU')
        return True

    run.log_line(f'{spec}: building from source, this can take hours')
    ok, output = rebuild(VENV_PIP, name, version, source=True,
                         timeout=SOURCE_BUILD_TIMEOUT, on_line=_stream(run, spec))
    if ok:
        run.log_line(f'{spec}: built for this CPU')
    else:
        run.log_line(f'{spec}: could not be built - '
                     f'{(output or "").strip()[-300:] or "no output captured"}')
    return ok


def _run_pip(run, label, argv, timeout):
    """Run a pip command, streaming its output into the log."""
    emit = _stream(run, label)
    env = dict(os.environ, PYTHONUNBUFFERED='1')
    try:
        proc = subprocess.Popen(argv, cwd=PROJECT_DIR, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
    except OSError as exc:
        run.log_line(f'{label}: could not start pip - {exc}')
        return False

    deadline = time.monotonic() + timeout
    tail = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            del tail[:-40]
            emit(line)
            if _stopping or time.monotonic() > deadline:
                proc.terminate()
                break
        proc.wait(timeout=30)
    except Exception as exc:
        proc.kill()
        run.log_line(f'{label}: {exc}')
        return False
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass

    if proc.returncode == 0:
        return True
    run.log_line(f'{label}: failed - {" / ".join(tail[-3:]) or "no output captured"}')
    return False


def _do_pip_requirements(run, job):
    """Install requirements.txt, however long that turns into.

    A version bump that has no wheel for this platform becomes a source build,
    which is exactly the case that could not survive running inside the app.
    """
    requirements = os.path.join(PROJECT_DIR, 'requirements.txt')
    if not os.path.exists(requirements):
        run.log_line('requirements.txt not found')
        return False
    return _run_pip(run, 'requirements.txt',
                    [VENV_PIP, 'install', '-r', requirements],
                    SOURCE_BUILD_TIMEOUT)


def _do_pillow(run, job):
    """Rebuild Pillow from source, for the native codecs the wheels omit."""
    return _run_pip(run, 'Pillow',
                    [VENV_PIP, 'install', '--force-reinstall', '--no-cache-dir',
                     '--no-binary', ':all:', 'Pillow'],
                    SOURCE_BUILD_TIMEOUT)


HANDLERS = {
    'rebuild': _do_rebuild,
    'pip-requirements': _do_pip_requirements,
    'pillow': _do_pillow,
}


def main():
    queue = _read_json(QUEUE_FILE, {})
    jobs = [j for j in queue.get('jobs', []) if j.get('attempts', 0) < MAX_ATTEMPTS]
    if not jobs:
        try:
            os.remove(QUEUE_FILE)
        except OSError:
            pass
        return 0

    os.makedirs(CACHE_DIR, exist_ok=True)
    run = Run(jobs, queue.get('restart_when_done', True))
    run.publish()
    run.log_line(f'{run.total} job(s) queued. This can take hours; leave the '
                 f'device powered on. The dashboard stays available throughout.')

    remaining = list(jobs)
    changed = False

    for position, job in enumerate(jobs, start=1):
        if _stopping:
            run.log_line('stopped on request; the queue is kept for next time')
            break

        label = _job_label(job)
        run.index = position
        run.current = label
        run.publish()

        handler = HANDLERS.get(job.get('kind'))
        if handler is None:
            run.log_line(f'unknown job kind: {job.get("kind")}')
            remaining = [j for j in remaining if j is not job]
            run.save_queue()
            continue

        # The attempt is recorded before it is made. A build heavy enough to
        # take this process down never reaches the line that records a failure,
        # and an attempt counted afterwards would leave the job first in the
        # queue and retried from the top for ever.
        job['attempts'] = job.get('attempts', 0) + 1
        remaining = [j for j in remaining if j is not job] + [job]
        run.jobs = remaining
        run.save_queue()

        try:
            ok = handler(run, job)
        except Exception as exc:
            run.log_line(f'{label}: {exc}')
            ok = False

        if ok:
            # A skip leaves the virtualenv exactly as it was, so it clears the
            # job without earning the restart at the end. A queue that turned
            # out to be entirely stale would otherwise bounce the service for
            # nothing.
            changed = changed or ok != 'skipped'
            run.done.append(label)
            remaining = [j for j in remaining if j is not job]
        else:
            run.failed.append(label)

        run.jobs = remaining
        run.current = None
        run.save_queue()
        run.publish()

    run.current = None
    run.publish(running=False, finished=time.time())
    run.log_line(f'finished: {len(run.done)} done, {len(run.failed)} failed')

    # The app is running the packages this replaced, so it only picks them up
    # after a restart. Nothing else reaches this point - the update that queued
    # the work finished hours ago.
    if changed and run.restart_when_done and not _stopping:
        run.log_line('restarting mempaper to load the new packages')
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'mempaper.service'],
                           timeout=60)
        except Exception as exc:
            run.log_line(f'could not restart mempaper: {exc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
