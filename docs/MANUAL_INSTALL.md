# Manual Installation

Everything [`install.sh`](../install.sh) does, as individual commands.

**You probably do not need this.** The one-line installer is the supported path
and handles the awkward parts — ARMv6 source builds, sudoers and polkit rules,
DHCP-blocking firewalls — without you having to think about them:

```bash
sudo apt install -y git \
&& git clone https://github.com/satcat21/btc-mempaper.git \
&& cd btc-mempaper && bash install.sh
```

This document exists for three cases: you want to know what the script touches
before running it, you are adapting mempaper to a distribution it does not
support, or an install failed partway and you need to resume from a specific
step.

> **`install.sh` is authoritative.** If anything here disagrees with it, the
> script is right and this file has drifted — please open an issue.

Commands assume Raspberry Pi OS Lite 32-bit (Trixie / Debian 13), run as a
normal sudo-capable user such as `pi`. **Never run the installer or these
commands as root** — the script refuses, and several steps depend on `sudo -u`
dropping privileges correctly.

> **Bookworm (Debian 12) is not supported or tested.** The versions pinned in
> `apt-requirements.txt` exist only in the Trixie archive, so a device on any
> other suite ignores them and installs those packages unpinned — the apt step
> below still works, it just gives you whatever versions Bookworm currently
> offers. See the note under
> [Installation in the README](../README.md#installation).

---

## Contents

- [0. Configuration decisions](#0-configuration-decisions)
- [1. System update](#1-system-update)
- [2. Persistent logging (optional)](#2-persistent-logging-optional)
- [3. Network pre-configuration](#3-network-pre-configuration)
- [4. Service user and repo location](#4-service-user-and-repo-location)
- [5. System packages](#5-system-packages)
- [6. Firewall and DNS conflicts](#6-firewall-and-dns-conflicts)
- [7. Python virtual environment](#7-python-virtual-environment)
- [8. Python dependencies](#8-python-dependencies)
- [9. ARMv6 source rebuilds (Pi Zero 1 WH)](#9-armv6-source-rebuilds-pi-zero-1-wh)
- [10. Configuration file](#10-configuration-file)
- [11. Admin account](#11-admin-account)
- [12. E-ink display and SPI](#12-e-ink-display-and-spi)
- [13. Systemd service](#13-systemd-service)
- [14. Wi-Fi permissions and radio](#14-wi-fi-permissions-and-radio)
- [15. Wi-Fi power management](#15-wi-fi-power-management)
- [16. Login banner and CLI](#16-login-banner-and-cli)
- [17. Optional hardening](#17-optional-hardening)
- [18. Start the service](#18-start-the-service)
- [Verifying the result](#verifying-the-result)

---

## 0. Configuration decisions

The installer asks these upfront and then runs unattended. Decide them now:

| Question | Default | Where it lands |
|---|---|---|
| Display model | — | [Step 12](#12-e-ink-display-and-spi) |
| Admin username / password | — | [Step 11](#11-admin-account) |
| Reach mempool.space over Tor | **Yes** | [Step 10](#10-configuration-file) |
| Minify JavaScript | Yes | [Step 8](#8-python-dependencies) |
| fail2ban | Yes | [Step 17](#17-optional-hardening) |
| Unattended security updates | Yes | [Step 17](#17-optional-hardening) |
| Persistent logging | **No** | [Step 2](#2-persistent-logging-optional) |
| Wi-Fi country code | `DE` | [Step 14](#14-wi-fi-permissions-and-radio) |
| Disable SSH password auth | Yes | [Step 17](#17-optional-hardening) |

The admin password is validated: at least 16 characters, with an uppercase
letter, a lowercase letter, a digit, and a special character.

---

## 1. System update

Run first, so everything installed afterwards is current.

```bash
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -q
sudo apt-get install -y locales-all -q
```

---

## 2. Persistent logging (optional)

Raspberry Pi OS ships `Storage=volatile`, so journal logs live in RAM and vanish
on every reboot. That protects the SD card but makes debugging a crash from the
previous boot impossible. Enable persistence only if you need it:

```bash
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/persistent.conf > /dev/null << 'EOF'
[Journal]
Storage=persistent
SystemMaxUse=200M
EOF
sudo systemctl restart systemd-journald
```

The 200 MB cap keeps SD growth bounded. Later-sorting filenames win for
duplicate systemd `conf.d` keys, so this `/etc/` drop-in overrides the vendor
default in `/usr/lib/`.

---

## 3. Network pre-configuration

Three unrelated fixes that all prevent the Wi-Fi stack from misbehaving on boot.

**Netplan file permissions** — NetworkManager warns and can refuse to apply a
world-readable config:

```bash
sudo mkdir -p /etc/tmpfiles.d
sudo tee /etc/tmpfiles.d/mempaper-netplan-perms.conf > /dev/null << 'EOF'
z /lib/netplan/00-network-manager-all.yaml 0600 root root - -
EOF
sudo systemd-tmpfiles --create /etc/tmpfiles.d/mempaper-netplan-perms.conf
```

**Stop cloud-init rewriting the network on every boot:**

```bash
sudo mkdir -p /etc/cloud/cloud.cfg.d
sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg > /dev/null << 'EOF'
network: {config: disabled}
EOF
```

**Pre-render netplan before NetworkManager starts.** NM runs `netplan generate`
internally at startup; if the result differs from what is on disk it triggers a
`systemd daemon-reload`, which can cascade and delay NM's readiness — long
enough that the hotspot misses its window:

```bash
sudo tee /etc/systemd/system/mempaper-netplan-pregenerate.service > /dev/null << 'EOF'
[Unit]
Description=Pre-render netplan config before NetworkManager starts
DefaultDependencies=no
After=systemd-udevd.service local-fs.target
Before=NetworkManager.service
Wants=systemd-udevd.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/netplan generate
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable mempaper-netplan-pregenerate.service
```

---

## 4. Service user and repo location

mempaper runs as a dedicated system account, and the code lives in that
account's home directory so every app file is owned and contained by it.

```bash
sudo useradd -r -m -s /bin/bash mempaper

# Hardware and network access
for grp in netdev gpio spi i2c; do
    getent group "$grp" >/dev/null && sudo usermod -aG "$grp" mempaper
done
```

**Move the repo** from wherever you cloned it to `/home/mempaper/`:

```bash
sudo mv ~/btc-mempaper /home/mempaper/btc-mempaper
cd /home/mempaper/btc-mempaper
sudo chown -R mempaper:mempaper /home/mempaper/btc-mempaper
sudo chmod g+x,o+x /home/mempaper
```

**Allow admins to SCP memes in.** `pi` joins the `mempaper` group and therefore
uses *group* permissions, so the repo root and `static/` both need `g+rx` — not
just `o+x`:

```bash
sudo chmod g+rx /home/mempaper/btc-mempaper
sudo mkdir -p static/memes
sudo chown mempaper:mempaper static static/memes
sudo chmod g+rx static
sudo chmod 2775 static/memes      # setgid: new files inherit the mempaper group
sudo usermod -aG mempaper pi
```

**Check out the latest release tag.** You cloned `main` to get the newest
installer, but the installed version should be a tagged release — otherwise the
dashboard shows an update-available banner immediately:

```bash
sudo -u mempaper git checkout "$(sudo -u mempaper git describe --tags --abbrev=0)"
```

**Pre-create the SSH key files.** The service unit uses `ProtectSystem=strict`,
and `ReadWritePaths` silently ignores paths that do not exist when the service
starts — so a missing `authorized_keys` stays unwritable inside the sandbox and
the web UI's SSH key management fails:

```bash
sudo -u mempaper mkdir -p /home/mempaper/.ssh
sudo chmod 700 /home/mempaper/.ssh
sudo -u mempaper touch /home/mempaper/.ssh/authorized_keys
sudo chmod 600 /home/mempaper/.ssh/authorized_keys

sudo mkdir -p /home/pi/.ssh && sudo chmod 700 /home/pi/.ssh
sudo touch /home/pi/.ssh/authorized_keys && sudo chmod 600 /home/pi/.ssh/authorized_keys
sudo chown -R pi:pi /home/pi/.ssh
```

---

## 5. System packages

```bash
sudo apt-get install -y $(grep -v '^\s*#' apt-requirements.txt | grep -v '^\s*$')
sudo apt-get install -y python3-venv
```

See [`apt-requirements.txt`](../apt-requirements.txt) for the list and why each
entry is there. Notable ones: `hostapd` and `dnsmasq` create the setup hotspot,
`iptables`/`nftables` serve the captive portal, `tor` routes mempool traffic to
a `.onion` instance, and `imagemagick` is the WebP/AVIF fallback when Pillow
lacks a native codec.

---

## 6. Firewall and DNS conflicts

**This step is why the setup hotspot works.** Three services, if left running,
each independently break DHCP for hotspot clients — and they break it silently,
so the failure only appears when someone tries to onboard a device.

```bash
# System dnsmasq grabs port 53/67 on all interfaces, preventing
# NetworkManager's own shared-mode dnsmasq from starting.
sudo systemctl stop dnsmasq
sudo systemctl disable dnsmasq
sudo systemctl mask dnsmasq        # mask survives future apt reinstalls

# Trixie ships /etc/nftables.conf with 'inet filter input { policy drop }',
# which drops DHCP DISCOVER broadcasts. Disabling is not enough — the ruleset
# loaded at boot stays resident in memory until flushed.
sudo systemctl stop nftables
sudo systemctl disable nftables
sudo nft flush ruleset

# UFW's ufw-after-input chain unconditionally drops UDP/67 before any user
# allow-rule can accept it.
command -v ufw >/dev/null && sudo ufw disable
```

> **Do not re-enable these later.** A device already on Wi-Fi runs fine with UFW
> active, so the damage stays invisible until the device falls back to hotspot
> mode after a router change or factory reset. See
> [Security Guide → Host firewall](SECURITY_GUIDE.md#host-firewall-do-not-use-ufw).

---

## 7. Python virtual environment

```bash
sudo -u mempaper python3 -m venv /home/mempaper/btc-mempaper/.venv
```

**Pin pip to the version in `requirements.txt`** so every device resolves wheels
identically. Without the pin a fresh install starts on whatever pip is newest
that day and immediately diverges:

```bash
PIP_PIN=$(grep -oE '^pip==[0-9][0-9.]*' requirements.txt | head -1)
sudo -u mempaper .venv/bin/pip install --upgrade "$PIP_PIN" setuptools wheel -q
```

**Hold the Python minor version.** An `apt upgrade` that moves the default
Python from 3.13 to 3.14 orphans the virtualenv — every dependency silently
disappears. Security patches within the held minor still install; only the
metapackage choosing the default is frozen:

```bash
sudo apt-mark hold python3 python3-dev python3-venv
```

To move to a new minor deliberately, use `tools/upgrade_python.sh` rather than
unholding by hand.

---

## 8. Python dependencies

piwheels is added explicitly because Trixie, unlike Bookworm, does not ship it
in `pip.conf` — and it is the only source of ARMv6-compatible wheels.

```bash
PIW="--extra-index-url https://www.piwheels.org/simple"

sudo -u mempaper .venv/bin/pip install $PIW -r requirements.txt
sudo -u mempaper .venv/bin/pip install $PIW spidev gpiozero lgpio
```

**Optional — minify JavaScript** (served from `static/js/dist/`):

```bash
sudo -u mempaper .venv/bin/python tools/minify.py
```

---

## 9. ARMv6 source rebuilds (Pi Zero 1 WH)

**Skip this entirely unless `uname -m` prints `armv6l`.** On Pi Zero 2 W and
every other supported board, the prebuilt wheels work.

piwheels has no ARMv6 wheels for Python 3.13, and PyPI wheels target ARMv7+.
Installing them produces `SIGILL` crashes at runtime rather than a clean error
at install time, which is what makes this worth doing carefully.

**gevent** — test before rebuilding, since the rebuild takes 10–20 minutes:

```bash
sudo -u mempaper .venv/bin/python -c "import gevent.ssl" \
  || sudo -u mempaper .venv/bin/pip install \
       --force-reinstall --no-cache-dir --no-binary :all: gevent
```

**libwebp** — Raspbian Trixie's build is compiled for ARMv7+ NEON and raises
`SIGILL` on ARMv6 during both encode and decode. Probe it in a subprocess so the
crash kills the child rather than your shell:

```bash
sudo -u mempaper .venv/bin/python -c \
  'from PIL import Image; import io; buf=io.BytesIO(); Image.new("RGB",(1,1)).save(buf,"WEBP")'
```

If that fails, build libwebp with SIMD disabled and overwrite the system copy:

```bash
sudo apt-get install -y cmake
BUILD=$(mktemp -d)
wget -qO "$BUILD/libwebp.tar.gz" \
  https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.5.0.tar.gz
tar xf "$BUILD/libwebp.tar.gz" -C "$BUILD"
SRC=$(find "$BUILD" -maxdepth 1 -name 'libwebp-*' -type d | head -1)
cmake -S "$SRC" -B "$SRC/build" \
    -DWEBP_ENABLE_SIMD=OFF -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release
make -j1 -C "$SRC/build"
sudo make -C "$SRC/build" install

# Overwrite the system shared library so the runtime picks up the NEON-free build
sudo cp "$(find /usr/local/lib -name 'libwebp.so.*.*.*' | head -1)" \
        "$(find /lib/arm-linux-gnueabihf -name 'libwebp.so.*.*.*' | head -1)"
sudo ldconfig
rm -rf "$BUILD"
```

**Pillow** — rebuild so it links against the new libwebp. `TMPDIR` is redirected
because `/tmp` is often too small for the build on a 512 MB device:

```bash
sudo apt-get install -y libjpeg-dev libpng-dev zlib1g-dev libfreetype6-dev libwebp-dev
sudo -u mempaper TMPDIR=/home/mempaper .venv/bin/pip install \
    --force-reinstall --no-cache-dir --no-binary :all: Pillow
```

Use `-j1`. Parallel compilation exhausts RAM on a Pi Zero and the build dies.

---

## 10. Configuration file

```bash
sudo -u mempaper mkdir -p config cache
sudo -u mempaper cp config/config.json.example config/config.json
```

**Route mempool traffic over Tor** (the installer's default). The public
mempool.space otherwise pairs your home IP with every query; Tor costs a few
seconds of latency the dashboard never notices, since blocks arrive ~10 minutes
apart:

```bash
sudo -u mempaper python3 - <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from utils.technical_config import MEMPOOL_ONION_PRESETS

preset = MEMPOOL_ONION_PRESETS[0]
p = Path("config/config.json")
cfg = json.loads(p.read_text())

# Never redirect an instance already pointed somewhere — including your own node
host = str(cfg.get("mempool_host", "")).strip()
if host and host != "mempool.space":
    print(f"mempool_host already set to '{host}' — leaving it alone")
    sys.exit(0)

cfg["mempool_use_tor"]   = True
cfg["mempool_host"]      = preset["host"]
cfg["mempool_use_https"] = preset["use_https"]
cfg["mempool_rest_port"] = preset["port"]
cfg["mempool_ws_port"]   = preset["port"]
p.write_text(json.dumps(cfg, indent=2))
print(f"{preset['label']} via Tor on port {preset['port']}")
EOF
```

Reading the onion address from `utils.technical_config` rather than pasting a
literal matters: a v3 onion address is a public key, so a single wrong character
fails closed with no useful error, and the address can change between releases.

**Randomise the weekly meme sync.** Every install otherwise inherits the same
default (Thu 13:00), which would have every mempaper in the world hit
einundzwanzig-memes.space in the same hour:

```bash
sudo -u mempaper python3 - <<'EOF'
import json, random
from pathlib import Path
p = Path("config/config.json")
cfg = json.loads(p.read_text())
if not cfg.get("meme_sync_schedule_randomised"):
    cfg["meme_sync_day"]  = str(random.randint(0, 6))   # cron: 0=Sun
    cfg["meme_sync_hour"] = str(random.randint(0, 23))
    cfg["meme_sync_schedule_randomised"] = True
    p.write_text(json.dumps(cfg, indent=2))
    print(f"weekly sync: day {cfg['meme_sync_day']} hour {cfg['meme_sync_hour']}")
EOF
```

**Secure the config** — it holds password hashes and API keys. Group-readable so
the `mempaper` CLI works for the `pi` user, but closed to everyone else:

```bash
sudo chmod 750 config/
sudo chmod 640 config/config.json
```

---

## 11. Admin account

```bash
sudo -u mempaper .venv/bin/python tools/setup_user.py
```

Or non-interactively, as the installer does:

```bash
printf '%s\n%s\n' "myadmin" "MyStr0ng!Passphrase" \
  | sudo -u mempaper .venv/bin/python tools/setup_user.py --stdin
```

Exit code `2` means the user already exists — not a failure. Passwords are
stored as Argon2id hashes in `config/config.json` under `admin_users`.

---

## 12. E-ink display and SPI

```bash
sudo -u mempaper .venv/bin/python tools/configure_display.py
```

Pass the menu number to skip the prompt, and add `--offline` if the Pi has no
internet — driver download is then skipped rather than retried, and the web UI
can fetch the missing drivers for the configured model once the Pi is online:

| # | Display |
|---|---|
| 1 | Waveshare 13.3" 6-color (Spectra 6) — recommended |
| 2 | Waveshare 7.3" 7-color |
| 3 | Waveshare 5.83" V2 (omni-epd) |
| 4 | Waveshare 4.2" (omni-epd) |
| 5 | Waveshare 2.7" (omni-epd) |
| 6 | Inky Impression 7-color |
| 7 | Inky Auto-detect |
| 8 | Mock display (testing, no hardware) |

Drivers land in `display/drivers/<device>/` and are MIT licensed by Waveshare
(see [`display/drivers/README.md`](../display/drivers/README.md)).

> **This tool is the only way to change display model.** The Settings page shows
> the configured model as a read-only field — it can trigger a driver download for
> that model, but not switch to a different one. Re-run this tool (or `install.sh`)
> to change hardware.

**Enable SPI** for any real display (harmless when unused, so enable it even if
you will attach the panel later — skip only for the mock display):

```bash
sudo raspi-config nonint do_spi 0
```

If `/dev/spidev0.0` does not exist afterwards, SPI only activates on reboot.

<details>
<summary><b>Option: omni-epd</b> for display types not natively supported</summary>

```bash
git clone https://github.com/robweber/omni-epd.git
cd omni-epd
pip3 install --upgrade pip setuptools wheel
pip3 install --prefer-binary .
```

</details>

---

## 13. Systemd service

```bash
sudo -u mempaper .venv/bin/python tools/generate_service_file.py --quiet
sudo cp mempaper.service /etc/systemd/system/mempaper.service
sudo systemctl daemon-reload
sudo systemctl enable mempaper.service
```

The unit is generated rather than shipped because it embeds absolute paths and
the resolved Python interpreter.

**Deprioritise Tor** if it is installed. Its bootstrap is slow and CPU-hungry,
and on a single-core Pi Zero it competes with mempaper's own time-critical
startup:

```bash
sudo mkdir -p /etc/systemd/system/tor@default.service.d
sudo tee /etc/systemd/system/tor@default.service.d/defer-startup.conf > /dev/null << 'EOF'
[Service]
Nice=15
IOSchedulingClass=idle
EOF
sudo systemctl daemon-reload
```

> **Do not add `After=mempaper.service` here.** It looks tempting, and earlier
> versions did it, but with mempool traffic over Tor mempaper cannot fetch
> anything until tor is up — so ordering tor last costs a failed first request
> and a 20-second connect timeout on every boot. The transport is switchable in
> the web UI while this file is only written at install time, so the ordering
> cannot follow it. The priority settings above give mempaper the CPU it needs
> without creating that dependency.

---

## 14. Wi-Fi permissions and radio

Installs the polkit rule and sudoers entries that let the service manage
NetworkManager connections, the hotspot, and its iptables rules without a
password:

```bash
sudo bash tools/install_permissions.sh mempaper
```

**Set the Wi-Fi country.** Without a regulatory domain the radio can stay
soft-blocked by rfkill, or hostapd fails to pick a channel — on a fresh flash
this prevents *both* normal Wi-Fi and the setup hotspot from ever coming up:

```bash
sudo raspi-config nonint do_wifi_country DE     # your ISO 3166-1 alpha-2 code
sudo rfkill unblock wifi
sudo nmcli radio wifi on
```

---

## 15. Wi-Fi power management

The BCM43430 chip on the Pi Zero W enables power management by default. It then
misses router beacons while idle, the router deauthenticates the Pi, and the
connection drops intermittently:

```bash
sudo tee /etc/NetworkManager/conf.d/99-disable-powersave.conf > /dev/null << 'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager
```

`2` means "disabled" in NetworkManager's enum (0 = default, 1 = ignore,
2 = disable, 3 = enable). Verify with `iwconfig wlan0 | grep Power`, which
should report `Power Management:off`.

---

## 16. Login banner and CLI

Shows block height, mempool status, meme count, service uptime and display info
on SSH login, and installs the same script as a `mempaper` command:

```bash
sudo chmod +x tools/mempaper-motd.sh
sudo ln -sf /home/mempaper/btc-mempaper/tools/mempaper-motd.sh /etc/profile.d/mempaper-motd.sh
sudo ln -sf /home/mempaper/btc-mempaper/tools/mempaper-motd.sh /usr/local/bin/mempaper
```

---

## 17. Optional hardening

**fail2ban** — SSH brute-force protection:

```bash
sudo apt-get install -y fail2ban
```

**Unattended security updates:**

```bash
sudo apt-get install -y unattended-upgrades
sudo DEBIAN_FRONTEND=noninteractive dpkg-reconfigure --priority=low unattended-upgrades

# Optional automatic reboot, skipped while an SSH session is active
sudo tee /etc/apt/apt.conf.d/52mempaper-reboot > /dev/null << 'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
```

**Disable SSH password authentication.** Editing `sshd_config` alone is often
not enough: Raspberry Pi Imager-provisioned images ship a
`/etc/ssh/sshd_config.d/50-cloud-init.conf` that re-enables password auth, and
sshd's `Include` uses **first-match-wins**. A drop-in named to sort first is
what actually decides the outcome:

```bash
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/'               /etc/ssh/sshd_config

sudo mkdir -p /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/00-mempaper-hardening.conf > /dev/null << 'EOF'
PasswordAuthentication no
PermitRootLogin no
EOF
sudo chmod 644 /etc/ssh/sshd_config.d/00-mempaper-hardening.conf
sudo systemctl reload sshd
```

**Verify against the effective config, not your edit** — this catches any other
drop-in that outranks yours:

```bash
sudo sshd -T | grep -i passwordauthentication    # expect: passwordauthentication no
```

> Add your public key through **Settings → General → Advanced → SSH Access** *before* doing
> this, or you will need physical access to get back in.

**Periodic TRIM** — lets the card actually erase deleted data.

```bash
sudo fstrim /                             # succeeds only if the card supports discard
sudo systemctl enable --now fstrim.timer  # weekly
```

Deleting a file on flash does not erase it: the controller marks the old cells free
and writes elsewhere, leaving the previous contents recoverable from the raw NAND.
TRIM asks it to erase them. Best effort — many SD cards ignore discard, and `fstrim`
will say so. This matters mainly if wallet addresses were ever written in clear text;
see the ordering note below.

It applies to freed blocks only, whatever they contained — TRIM works at the block
layer and never reads the data, so encrypted and plaintext files are treated alike.
Files currently in use are untouched. Config and cache saves go through
`atomic_write_json` (temp file, then rename), which is what leaves a full copy of the
*previous* version behind on every save.

**TRIM does not shorten card life.** A discard command updates the controller's
mapping table rather than writing cells, and knowing which blocks are dead lets it
skip relocating them during garbage collection — less write amplification, not more.
`fstrim.timer` is used in preference to the `discard` mount option, which fires on
every delete and behaves poorly on cheap controllers.

**Network-bound encryption (Tang)** — makes wallet data undecryptable on a stolen device.

> **Enable Tang before entering any wallet addresses.** Sealing the live data later
> cannot reach copies already committed to the card by wear-levelling. Retrofitting onto
> a device that already held xpubs means re-flashing for a clean start, or accepting that
> the old plaintext may remain recoverable.

`clevis` is part of [section 5](#5-system-packages) and is inert until switched on, so
install it whether or not you have a Tang server yet:

```bash
sudo apt-get install -y clevis     # already covered by apt-requirements.txt
```

Adding it to an existing mempaper that was installed earlier is the same one command —
no reinstall. The web updater and the startup dependency check both reconcile against
`apt-requirements.txt`, so a device updated through the UI normally gets it without SSH.

> **If `clevis` is missing on a device that has been updated through the UI**, that is
> the bug fixed in this release: the updater skipped apt whenever `apt-requirements.txt`
> had not changed since the last tag, so a package that failed to install once stayed
> missing through every later update, and the wrapper reported success either way. Run
> the command above to install it now, then
> `sudo bash ~/btc-mempaper/tools/install_permissions.sh` once to pick up the
> repaired helper scripts. Verify with `dpkg-query -W -f='${Status}\n' clevis`.

Everything below is optional and needs a Tang server on your LAN
([setup guide](SELF_HOSTING_GUIDE.md#part-8--tang-network-bound-encryption-for-wallet-data-optional)).

```bash
TANG_URL=http://192.168.1.50:7500

# 1. Confirm it answers
curl -sSf --max-time 10 "$TANG_URL/adv" -o /tmp/adv.json && echo reachable

# 2. Read the signing-key thumbprint. This is the value clevis pins - the
#    exchange key has a different one and would always fail.
THP=$(jose fmt --json /tmp/adv.json -g payload -y -o- \
      | jose jwk use -i- -r -u verify -o- \
      | jose jwk thp -i-)
echo "$THP"

# 3. Prove a full round trip before trusting it with anything
echo check | clevis encrypt tang "{\"url\":\"$TANG_URL\",\"thp\":\"$THP\"}" > /tmp/t.jwe
clevis decrypt < /tmp/t.jwe        # expect: check
```

If step 3 prints `check`, set the three keys in `config/config.json`:

```json
{
  "tang_enabled": true,
  "tang_url": "http://192.168.1.50:7500",
  "tang_thumbprint": "faYWs5gMZ4MOKVmw_70zIvgZuzPd6AZnrsF86OgewnI"
}
```

Then `sudo systemctl restart mempaper.service`. The same three settings are editable in
**Settings → General → Advanced**, so this can equally be done from the web UI later
without SSH.

```bash
rm -f /tmp/adv.json /tmp/t.jwe
```

> Verify that decryption **fails** with the Tang server stopped before you rely on this.
> A setup where it still succeeds is not protecting anything — the procedure is in the
> [self-hosting guide](SELF_HOSTING_GUIDE.md#verify-before-pointing-mempaper-at-it).

---

## 18. Start the service

```bash
# Marker that makes the app push an immediate e-ink refresh on this start,
# confirming the install worked even when no reboot was needed
sudo -u mempaper mkdir -p cache
sudo -u mempaper touch cache/boot_refresh_pending

sudo systemctl restart mempaper.service
```

**Reboot instead** if you enabled SPI in step 12 and `/dev/spidev0.0` still does
not exist:

```bash
sudo reboot
```

---

## Verifying the result

```bash
sudo systemctl status mempaper.service
sudo journalctl -u mempaper.service -f
```

The dashboard is at `http://<pi-ip>:5000`. Quick sanity checks:

| Check | Command | Expected |
|---|---|---|
| Service enabled | `systemctl is-enabled mempaper.service` | `enabled` |
| SPI present | `ls /dev/spidev0.0` | exists (unless mock display) |
| Wi-Fi powersave | `iwconfig wlan0 \| grep Power` | `Power Management:off` |
| No blocking firewall | `sudo nft list ruleset` | empty |
| Tor reachable | `curl --socks5-hostname 127.0.0.1:9050 -s https://check.torproject.org/api/ip` | `"IsTor":true` |
| Python held | `apt-mark showhold` | lists `python3` |

If mempool data never loads with Tor enabled, confirm the transport
independently before suspecting mempaper:

```bash
curl -sS --socks5-hostname 127.0.0.1:9050 \
  http://mempoolhqx4isw62xs7abwphsq7ldayuidyx2v2oethdhhj6mlo2r6ad.onion/api/blocks/tip/height
```

A SOCKS `0x04` (host unreachable) or `0x05` (connection refused) reply means the
onion service is not answering — that is a Tor or upstream problem, not a
mempaper one.

---

## See also

- [Configuration Reference](CONFIG_REFERENCE.md) — every setting explained
- [Security Guide](SECURITY_GUIDE.md) — hardening, threat model, audit checklist
- [Maintenance Guide](MAINTENANCE_GUIDE.md) — safe `apt` upgrades, Python version changes
- [Architecture](ARCHITECTURE.md) — how the pieces fit together
