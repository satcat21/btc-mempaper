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
import shutil
import signal
import subprocess
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from utils.wheel_platform import (  # noqa: E402
    MAX_ATTEMPTS, SOURCE_BUILD_TIMEOUT, WHEEL_FETCH_TIMEOUT,
    build_env, build_tmpdir, incompatible_dists, platform_tag, rebuild,
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
        self.events = []
        self.started = time.time()

    def log_line(self, line):
        """Raw output from a build. Nothing here to translate or reword."""
        self.event('output', line=line, text=line)

    def event(self, kind, text, **fields):
        """Record one step, as structure for the browser and prose for the journal.

        The browser composes its own wording from `kind`, so the log reads in the
        reader's language rather than in whatever this process happened to write.
        `text` is what the journal gets, and what the browser falls back to for a
        kind it does not recognise.
        """
        self.events.append(dict(fields, kind=kind, text=text))
        if len(self.events) > MAX_LOG_LINES:
            del self.events[:-MAX_LOG_LINES]
        self.log.append(text)
        if len(self.log) > MAX_LOG_LINES:
            del self.log[:-MAX_LOG_LINES]
        print(text, flush=True)
        self.publish()

    def publish(self, running=True, finished=None):
        _write_json(STATUS_FILE, {
            'running': running,
            'started': self.started,
            'finished': finished,
            'target': platform_tag(),
            'total': self.total,
            'index': self.index,
            # Jobs finished, which is what a progress bar measures. `index` is
            # the job being worked on and is 1-based, so on a single-job queue
            # it reads 1/1 from the moment the build starts.
            'completed': len(self.done) + len(self.failed),
            'current': self.current,
            'done': self.done,
            'failed': self.failed,
            'log': self.log,
            'events': self.events,
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


def _clear_scratch():
    """Remove what earlier builds left in the scratch directory.

    pip cleans up after itself when it exits normally. A build killed partway -
    by a restart, by the timeout, or by the machine losing power - leaves its
    whole tree behind, and on a device where several have been interrupted that
    is hundreds of megabytes of dead object files nothing will ever collect.
    Only one worker runs at a time, so the start of a run is the safe moment.
    """
    scratch = build_tmpdir()
    if not scratch:
        return
    try:
        entries = os.listdir(scratch)
    except OSError:
        return
    for entry in entries:
        path = os.path.join(scratch, entry)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError:
            pass


def _tail_lines(output, count=3):
    """The last few whole lines of a failure.

    A fixed character count cuts mid-sentence - 'could not be built - problem
    with pip.' was the end of 'is likely not a problem with pip.', which reads
    as the opposite of what it said.
    """
    lines = [ln for ln in (output or '').splitlines() if ln.strip()]
    return ' / '.join(lines[-count:]) or 'no output captured'


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
        run.event('skip', f'{spec}: already runs on this CPU, skipping', spec=spec)
        return 'skipped'

    ok, output = rebuild(VENV_PIP, name, version, source=False,
                         timeout=WHEEL_FETCH_TIMEOUT, on_line=_stream(run, spec))
    if ok and any(n == name for n, _, _ in incompatible_dists()):
        ok = False
        run.event('wheel_rejected',
                  f'{spec}: the published wheel is built for another CPU too',
                  spec=spec)
    if ok:
        run.event('wheel_ok', f'{spec}: installed a wheel for this CPU', spec=spec)
        return True

    run.event('source', f'{spec}: building from source, this can take hours',
              spec=spec)
    ok, output = rebuild(VENV_PIP, name, version, source=True,
                         timeout=SOURCE_BUILD_TIMEOUT, on_line=_stream(run, spec))
    # pip exiting zero says it installed something, not that what it installed
    # suits this CPU. Checked the same way the wheel attempt is: a build that
    # leaves the module still unrunnable is a failure, not a success that gets
    # re-queued by the next update as though nothing had happened.
    if ok and any(n == name for n, _, _ in incompatible_dists()):
        ok = False
        output = ((output or '') + chr(10)
                  + 'the build produced code this CPU still cannot run')
    if ok:
        run.event('built', f'{spec}: built for this CPU', spec=spec)
    else:
        detail = _tail_lines(output)
        run.event('failed', f'{spec}: could not be built - {detail}',
                  spec=spec, detail=detail)
    return ok


def _run_pip(run, label, argv, timeout):
    """Run a pip command, streaming its output into the log."""
    emit = _stream(run, label)
    env = build_env()
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
    _clear_scratch()
    run = Run(jobs, queue.get('restart_when_done', True))
    run.publish()
    run.event('intro',
              f'{run.total} job(s) queued. This can take hours; leave the '
              f'device powered on. The dashboard stays available throughout.',
              total=run.total, target=platform_tag())

    remaining = list(jobs)
    changed = False

    for position, job in enumerate(jobs, start=1):
        if _stopping:
            run.event('stopped',
                      'stopped on request; the queue is kept for next time')
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
    run.event('finished', f'finished: {len(run.done)} done, '
              f'{len(run.failed)} failed',
              done=len(run.done), failed=len(run.failed))

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
