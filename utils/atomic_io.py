"""Crash-safe JSON file writes.

Writes go to a temp file in the same directory, fsync it, then os.replace()
onto the target path. os.replace is atomic on both POSIX and Windows — a
power loss mid-write leaves either the old file or the fully-written new
one, never a truncated/corrupt file. The containing directory is fsync'd too
so the rename itself survives a crash (POSIX doesn't guarantee a rename is
durable until the directory entry is flushed).
"""

import json
import os
import tempfile


def atomic_write_json(path, data, *, mode=0o644, **json_kwargs):
    """Write `data` as JSON to `path`, atomically and durably.

    `mode` defaults to 0o644 (matches plain open()'s typical default);
    callers writing secrets should pass mode=0o600.
    """
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.tmp-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, **json_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


def _fsync_dir(directory):
    """Best-effort directory fsync; not supported on Windows, harmless to skip."""
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
