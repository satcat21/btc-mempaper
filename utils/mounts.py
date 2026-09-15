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
import os
import subprocess

APT_STATE_DIR = '/run/mempaper-apt'


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
