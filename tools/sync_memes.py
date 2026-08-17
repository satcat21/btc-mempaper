#!/usr/bin/env python3
"""
Meme sync against einundzwanzig-memes.space.

This is the entry point the weekly cron line invokes — _apply_meme_sync_crontab()
in mempaper_app.py writes a crontab entry naming this file, and the web "Sync
now" button runs the same command. It used to be a placeholder that printed what
it would have done and exited 0, on the understanding that a list-all API
endpoint was still needed.

That endpoint never arrived, and it turned out not to be needed: tools/
download_all_memes.py already solves the problem the hard way. The site caps
/random and the filter endpoints at the same popular results, so the working
strategy is semantic search across the ~5 800 real tags from /api/v1/tags, with
cursor pagination and de-duplication by UUID. That is a lot of machinery, it
exists, it is resumable, and it is tested — so this file delegates to it rather
than growing a second, thinner implementation that would drift out of agreement.

Kept as its own entry point rather than pointing cron straight at
download_all_memes.py, because crontab lines written by earlier releases already
name this path. Repointing them would strand every device whose schedule was
written before the change.

    .venv/bin/python tools/sync_memes.py --update [--tor] [--out-dir static/memes]
    .venv/bin/python tools/sync_memes.py --status
    .venv/bin/python tools/sync_memes.py --stop

Run it with the project virtualenv's interpreter, not the system one: requests
and PySocks are installed in the venv only.
"""

import sys
from pathlib import Path

# tools/ has to be importable by name: download_all_memes does a top-level
# `import einundzwanzig_memes`, which only resolves when its own directory is on
# the path. Direct execution puts it there already; a cron run with a different
# cwd does not, and that difference used to be an ImportError hours after the
# fact in a log nobody reads.
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

PROJECT_ROOT = TOOLS_DIR.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "static" / "memes"
VENV_DIR = PROJECT_ROOT / ".venv"


def warn_if_outside_venv():
    """Say so when this is running on an interpreter other than the project venv.

    The dependencies live in .venv only, so a system-python run fails at import
    time — with a bare ImportError in a cron log, hours after the fact. Checking
    the interpreter instead names the cause while there is still something
    readable on screen. A warning rather than an exit: a venv somewhere else
    that has the packages is perfectly fine.
    """
    if not VENV_DIR.exists():
        return
    try:
        inside = Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return
    if not inside:
        # Plain ASCII: this line has to survive a cron log written under a
        # non-UTF-8 locale, where an emoji raises UnicodeEncodeError and takes
        # the run down with it — a warning must never be what breaks the job.
        print(f"WARNING: running on {sys.executable}, not the project venv.")
        print(f"   Dependencies are installed in {VENV_DIR}, use "
              f"{VENV_DIR / 'bin' / 'python'} instead.")
        print()


def main():
    warn_if_outside_venv()

    try:
        import download_all_memes
    except ImportError as exc:
        # Almost always the venv warning above coming true.
        print(f"ERROR: cannot import the downloader: {exc}")
        print("   Install dependencies with: .venv/bin/pip install -r requirements.txt")
        return 1

    # Hand the arguments straight through. The downloader owns the CLI contract
    # — --update, --tor, --out-dir, --status, --stop, --workers and the rest —
    # and re-declaring a subset here would mean two parsers to keep in agreement
    # and a flag that works on one entry point but not the other.
    #
    # --out-dir is defaulted only when the caller did not supply one, so a cron
    # line written without it still writes where the app reads.
    argv = sys.argv[1:]
    if not any(a == "--out-dir" or a.startswith("--out-dir=") for a in argv):
        argv += ["--out-dir", str(DEFAULT_OUT_DIR)]

    sys.argv = ["download_all_memes.py"] + argv
    try:
        download_all_memes.main()
    except SystemExit as exc:
        return exc.code or 0
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
