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
- Anything in `apt-requirements.txt` declared **without** a version — system libs,
  networking tools, git, curl
- Kernel, openssh, systemd, and all other non-Python packages

Entries in `apt-requirements.txt` that carry a `=version` are the exception: the
install wrapper `apt-mark hold`s them, so `apt upgrade` cannot move them and they
stop receiving Debian's security updates until the pin is bumped — which happens
when a new release ships, see
[Bumping pinned versions for a release](#bumping-pinned-versions-for-a-release).

```bash
# Safe — security patches within the held minor still install
sudo apt update && sudo apt upgrade -y
```

The `python3` hold blocks the metapackage from switching to a new minor. Individual `python3.13` security updates are not blocked.

---

## Bumping pinned versions for a release

Nothing here concerns the people running mempaper. A release ships the pins it
was tested with, and installing or updating applies them — no steps, no choices.
The work is the maintainer's, once per release: since a pinned package no longer
receives Debian's security updates, **the pins are only as current as the last
time someone bumped them.** That is the job this section describes.

Do not hand-edit the versions. Every device can write down what actually resolved
on it, and promoting that file is the whole workflow. Run this on a **Trixie test
device**, from the repo checkout, and take the steps in order.

### The one trap

The startup dependency check reconciles drift: on service start it compares the
declared pins against dpkg and, finding a package above its pin, runs the install
wrapper — which **downgrades it back**, `--allow-downgrades` and all. So you
cannot simply `apt-mark unhold`, upgrade, and restart to test; the app undoes the
upgrade as it boots. Release the pins in the *declaration* first and everything
else follows without a fight.

### Step 1 — Let the packages float

```bash
cd ~/btc-mempaper
sudo systemctl stop mempaper.service
git stash list >/dev/null && git status --short apt-requirements.txt   # start clean

# Strip '=version' from package lines only. Comments, the '# pins-for:' line and
# trailing inline comments are left alone.
sed -i 's/^\([A-Za-z0-9][A-Za-z0-9+.-]*\)=[^[:space:]#]*/\1/' apt-requirements.txt

# Releases every hold, because nothing declares a version any more.
sudo /usr/local/bin/mempaper-apt-install        # prints "🔓 Pin removed, now floating: …"
apt-mark showhold                               # expect only python3/-dev/-venv
```

`python3`, `python3-dev` and `python3-venv` stay held on purpose — they pin the
Python minor the `.venv` was built against. Moving those is a Python upgrade, a
different job with its own section below.

### Step 2 — Upgrade

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
```

### Step 3 — Upgrade the Python side

```bash
.venv/bin/pip list --outdated                   # what could move, and to where
```

Then bump deliberately rather than wholesale — `pip install -U -r requirements.txt`
does nothing while the file is pinned, and stripping every `==` at once makes a
failure hard to attribute:

```bash
.venv/bin/pip install -U flask werkzeug requests        # a few at a time
```

Two packages need care on a **Pi Zero 1 WH (ARMv6)**, where piwheels' builds are
compiled for ARMv7+ and crash with SIGILL:

```bash
.venv/bin/pip install --no-binary :all: pillow==<new>   # must be built from source
.venv/bin/pip install --no-binary :all: gevent==<new>   # same
```

Allow 20–40 minutes each on that hardware. If you are testing on a Pi 3/4/5, a
wheel is fine there but says nothing about ARMv6 — check `README.md` before
shipping a Pillow or gevent bump.

### Step 4 — Test

```bash
sudo systemctl start mempaper.service
systemctl is-active mempaper.service
```

The native extensions are what package upgrades actually break, so test those
directly rather than trusting a clean start:

```bash
.venv/bin/python -c "import gevent.ssl; print('gevent ok')"
.venv/bin/python -c "from PIL import Image; import io; b=io.BytesIO(); Image.new('RGB',(1,1)).save(b,'WEBP'); print('pillow webp ok')"
.venv/bin/python -c "import numpy; print('numpy', numpy.__version__)"
.venv/bin/python -c "import cryptography, psutil, babel; print('imports ok')"

curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:5000/
journalctl -u mempaper.service --since "5 min ago" -p warning --no-pager
```

A SIGILL shows up as the interpreter dying with no traceback — that is the ARMv6
wheel problem, not a bad version. Then confirm the part no command can check:
**watch the e-ink actually refresh**, and load the config UI.

### Step 5 — Promote what the device resolved to

A CLI upgrade writes no report — only the web update routes do that. Generate one:

```bash
.venv/bin/python -c "from utils.installed_report import write_installed_reports; write_installed_reports('.', log=print)"
```

That writes both files, each a copy of its source with the resolved version filled
in on every package line — comments, ordering and blank lines carried across
untouched, so promoting one reviews as a diff of versions rather than reading as a
new document. Promoting is idempotent; the generated header does not stack.

```bash
cp cache/currently_installed_apt-requirements.txt apt-requirements.txt
cp cache/currently_installed_requirements.txt    requirements.txt
git diff        # reads as: which versions moved
```

> **This pins everything installed, including packages you deliberately left
> floating.** The report describes what is on the device, so a bare `imagemagick`
> comes back as `imagemagick=8:7.1.1.43…`. If you keep intentional floats, restore
> them after promoting — `git diff` shows exactly which lines gained a version
> that had none before.

### Step 6 — Commit

```bash
git checkout -b chore/bump-pins
git add apt-requirements.txt requirements.txt
git commit
```

Check before you do:

- **The `# pins-for:` line** must name the suite the test device was running. It
  scopes every pin below it; a device on another suite ignores them and installs
  floating (see the header of `apt-requirements.txt`).
- **`python3-dev`** must not have moved unless you intended a Python upgrade.
- The pins now name versions **currently in the archive**. A pin Debian later
  supersedes still installs until it is removed from the mirror, at which point
  the wrapper reports it and leaves the package floating rather than holding it at
  the wrong version. That is a signal to bump, not a breakage.

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
>
> The `bookworm` entry is kept so that a device still on Bookworm is not told to
> rebuild its interpreter, **not** as a support claim — Trixie is the only tested
> OS, and `apt-requirements.txt` pins versions that exist only in its archive.
> Leave the entry alone rather than deleting it: removing a codename makes the
> lookup find nothing, which is also treated as "no upgrade needed", but it stops
> recording what that OS was known to ship.

To **add a new OS** (e.g. Forky/Debian 14): add `forky=14` to the file and push. Devices on that OS will auto-upgrade Python when they pull the update.

### Step 3 — Push a release

Tag and push normally. When users update via the web UI:

1. The update flow reads `tools/python_version` and detects a mismatch with the running interpreter
2. Runs `sudo /usr/local/bin/mempaper-upgrade-python` (a scoped wrapper installed by `install_permissions.sh`)
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
