"""Remounting read-only without pulling a filesystem out from under apt.

'mount -o remount,ro' changes the filesystem itself, not only the view of it
inside mempaper.service's sandbox, so it reaches every process on the device -
including an apt step running in mempaper-apt@<step>.service. When the update
route stopped following an upgrade early and restored its mounts, /boot/firmware
went read-only under initramfs-tools, and dpkg left it half-configured.

Every remount back to read-only goes through remount_readonly(), which leaves
the filesystem writable while a step runs. The runner restores the host's own
read-only mounts itself when the step ends.
"""
import contextlib
import os
import subprocess

APT_STATE_DIR = '/run/mempaper-apt'
SWAP_HELPER = '/usr/local/bin/mempaper-swap'


@contextlib.contextmanager
def swap_for_build(holder='pip'):
    """Switch the swap file on for the length of a pip build, then off.

    The file is registered noauto and stays off while mempaper is merely
    serving pages - that is SD-card wear for nothing. A pip install that turns
    into a source build is the case it exists for, and on a 512 MB Pi Zero the
    difference is the build finishing rather than being killed.

    Holds are counted by the helper, so a build unit or an apt step running
    alongside keeps the file on after this one lets go. Every failure is
    non-fatal: without a grant, without the helper, or without a swap file at
    all, the build simply runs the way it did before.
    """
    acquired = False
    try:
        try:
            if os.path.exists(SWAP_HELPER):
                acquired = subprocess.run(['sudo', '-n', SWAP_HELPER, 'acquire', holder],
                                          capture_output=True, timeout=60).returncode == 0
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"⚠️ Could not switch swap on for the build: {exc}")
        yield acquired
    finally:
        if acquired:
            try:
                subprocess.run(['sudo', '-n', SWAP_HELPER, 'release', holder],
                               capture_output=True, timeout=300)
            except (subprocess.SubprocessError, OSError) as exc:
                print(f"⚠️ Could not release the swap hold: {exc}")


def apt_step_running():
    """True while any mempaper-apt@ runner process is alive."""
    try:
        names = os.listdir(APT_STATE_DIR)
    except OSError:
        return False
    for name in names:
        if not name.endswith('.pid'):
            continue
        try:
            with open(os.path.join(APT_STATE_DIR, name)) as f:
                pid = f.read().strip()
        except OSError:
            continue
        if pid.isdigit() and os.path.exists(f'/proc/{pid}'):
            return True
    return False


def remount_readonly(target):
    """Remount target read-only, unless an apt step is running.

    Returns True if the remount ran and succeeded.
    """
    if apt_step_running():
        print(f"⚠️ Leaving {target} writable: a system package step is still running")
        return False
    try:
        return subprocess.run(['sudo', 'mount', '-o', 'remount,ro', target],
                              capture_output=True, timeout=10).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
