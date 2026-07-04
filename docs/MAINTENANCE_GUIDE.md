# mempaper Maintenance Guide

Developer and admin reference for system maintenance, Python version management, and the SSH login overview.

---

## Safe `apt upgrade` on a deployed device

`install.sh` holds the Python default metapackages to protect the virtual environment:

```bash
sudo apt-mark hold python3 python3-dev python3-venv
```

### What is held and why

| Package | Held | Reason |
|---------|------|--------|
| `python3` | ✅ yes | Controls which Python minor is the system default. Upgrading it (e.g. 3.13 → 3.14) orphans the `.venv` whose symlinks still point to the old binary. |
| `python3-dev` | ✅ yes | C extension headers tied to the minor version. |
| `python3-venv` | ✅ yes | Metapackage that follows `python3`. |
| `python3.13` | ❌ no | The version-specific package. Security patches within the same minor flow freely. |

### What is safe to upgrade freely

- Security patches for the current Python minor (`python3.13`, `python3.13-minimal`, …)
- Everything in `apt-requirements.txt` — system libs, networking tools, git, curl
- Kernel, openssh, systemd, and all other non-Python packages

```bash
# Safe — security patches within the held minor still install
sudo apt update && sudo apt upgrade -y
```

The `python3` hold blocks the metapackage from switching to a new minor. Individual `python3.13` security updates are not blocked.

---

## Python version upgrade path (developer workflow)

When a new Python minor (e.g. 3.14) is packaged for Raspberry Pi OS, follow this process before shipping it to devices.

### Step 1 — Test on Pi Zero 1 WH hardware

On a Pi Zero 1 WH running the new OS version:

```bash
sudo apt-mark unhold python3 python3-dev python3-venv
sudo apt update && sudo apt upgrade python3 python3-dev python3-venv -y
python3 --version   # confirm new minor
```

Then verify:
- `gevent` C extension works: `python3 -c "import gevent.ssl; print('ok')"` — if SIGILL, a source rebuild is needed
- Pillow WebP works: `python3 -c "from PIL import Image; import io; b=io.BytesIO(); Image.new('RGB',(1,1)).save(b,'WEBP'); print('ok')"` — if SIGILL, libwebp source build needed
- Full install: delete `.venv`, re-run install.sh, confirm the service starts correctly

### Step 2 — Update the version spec file

Edit `tools/python_version` and bump the entry for the relevant OS codename:

```
# before
trixie=13

# after
trixie=14
```

Then commit:

```bash
git commit tools/python_version -m "feat(trixie): require Python 3.14"
```

`tools/python_version` is a git-managed spec file mapping Raspberry Pi OS codenames to the minimum required Python minor. The web UI update flow detects the current OS via `/etc/os-release`, looks up its entry, and only triggers an upgrade when `current_minor < required_minor`. Devices already on a newer minor are not affected.

```
bookworm=11
trixie=13
```

> **Current entries:** Bookworm (Python 3.11 minimum) and Trixie (Python 3.13 minimum).
> A Trixie device running 3.13 passes (13 ≥ 13). A Bookworm device running 3.11 passes (11 ≥ 11).
> Only if a future release sets `bookworm=12` would Bookworm devices see an upgrade prompt.

To **add a new OS** (e.g. Forky/Debian 14): add `forky=14` to the file and push. Devices on that OS will auto-upgrade Python when they pull the update.

### Step 3 — Push a release

Tag and push normally. When users update via the web UI:

1. The update flow reads `tools/python_version` and detects a mismatch with the running interpreter
2. Runs `sudo /usr/local/bin/mempaper-upgrade-python` (a scoped wrapper installed by `install_wifi_permissions.sh`)
3. Output streams live to the update log in the web UI
4. After the Python upgrade completes (including ARMv6 source builds if needed), the normal pip install and service restart follow
5. The whole flow is hands-free — no SSH required

On Pi Zero 1 WH the ARMv6 source builds for `gevent` and `Pillow` take 20–30 minutes. The web UI shows live progress.

### Manual upgrade via SSH

If the web UI upgrade fails or you prefer to run it manually:

```bash
sudo bash /home/mempaper/btc-mempaper/tools/upgrade_python.sh
```

Flags:
- `--force` — skip the interactive confirmation prompt
- `--no-restart` — skip the service restart at the end (the web update flow uses this)
