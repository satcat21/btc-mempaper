# mempaper Security Guide

This guide covers the full security posture of a mempaper installation and how to harden it for your deployment scenario.

---

## Threat model

mempaper is designed for **trusted local networks**. It is not designed to be directly exposed to the internet without additional protection (reverse proxy + authentication layer).

| Scenario | Risk level | Required hardening |
|---|---|---|
| Home LAN, no port forwarding | Low | Strong password, default setup is sufficient |
| Home LAN with internet exposure via Traefik | Medium | Traefik + OIDC (see Self-Hosting Guide) |
| Untrusted network (hotel, office) | High | VPN-only access, no direct port forwarding |

---

## What mempaper protects by default

| Protection | Detail |
|---|---|
| **Password hashing** | Argon2id with memory/iteration hardening |
| **Login rate limiting** | 10 failed attempts per 5-minute window before lockout |
| **Session timeout** | 30-minute idle timeout |
| **Session cookies** | `HttpOnly`, `SameSite=Strict` |
| **Security headers** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection` |
| **Service isolation** | App runs as dedicated `mempaper` user, not `pi` or `root` |
| **Scoped sudo** | Only the exact commands mempaper needs; no wildcard `NOPASSWD: ALL` |
| **Upload limit** | Rejects files larger than 15 MB at the HTTP layer |
| **Webhook token** | Donation webhook requires a per-installation secret in the URL |

---

## Initial secure installation

### 1. Run the installer

```bash
# On the Pi, as the 'pi' user (or any sudo-capable user) — never as root:
sudo apt install -y git
git clone https://github.com/satcat21/btc-mempaper.git ~/btc-mempaper
cd ~/btc-mempaper
bash install.sh
```

**The installer applies the hardening for you.** It asks these questions upfront
and then runs unattended — there are no manual security steps to perform
afterwards:

| Prompt | Default | Recommended | Effect |
|---|---|---|---|
| Admin username and password | — | password manager | Argon2id hash in `config/config.json`; enforced minimum 16 characters with upper, lower, digit and symbol |
| Reach mempool.space over Tor | Yes | **Yes** | Queries go to the onion service, so the public instance never sees your home IP |
| fail2ban | Yes | **Yes** | Bans repeated SSH authentication failures |
| Unattended security updates | Yes | **Yes** | Patches land without you remembering to apply them |
| ↳ auto-reboot after updates | Yes | **Yes**, off-hours | Skipped automatically while an SSH session is active |
| Disable SSH password authentication | Yes | **Yes** — read the warning below | Key-only login |
| Wi-Fi country code | `DE` | your own country | Lifts the rfkill block that otherwise keeps the radio disabled |
| Minify JavaScript | Yes | Yes | Smaller payloads; no security effect |
| Persistent logging | No | No, unless debugging | Journal survives reboots, at the cost of SD card wear |

**Accepting every default gives you the hardened configuration** — the defaults
were chosen to be the secure answer, so pressing Enter through the prompts is
the right move for almost everyone. Two are worth a moment's thought:

- **Disabling SSH password authentication locks you out until you add a key.**
  The installer warns about this, and it is not reversible from the web UI —
  recovering means physical access to the SD card. Accept it, then add your
  public key immediately via **Settings → General → Advanced → SSH Access** (see
  [step 4](#4-ssh-keys-and-password-login)). If you are installing remotely and
  have no key ready, answer **no** and harden later.
- **Tor is right for the public mempool.space, and wrong for a self-hosted one.**
  Against the public instance it costs a few seconds of latency the dashboard
  never notices — blocks arrive ten minutes apart — and it keeps your home IP
  out of the picture. Against your own node on the LAN it buys nothing: the
  traffic never leaves the house. Worse, **Tor refuses to route private
  addresses**, so leaving the toggle on while `mempool_host` points at
  `192.168.x.x` breaks mempool access completely rather than merely slowing it.
  It also runs a `tor` daemon the Pi Zero does not need — the installer already
  nices it to 15 and defers its startup precisely because it competes with
  mempaper on a single core.

  Switching to your own node is therefore two changes, not one: set
  `mempool_host`, **and turn the Tor toggle off**. Nothing does it for you — the
  config auto-*enables* Tor for a `.onion` host, but never disables it when you
  move to a LAN address.

Without asking, it also creates the `mempaper` service account and adds it to
`gpio`/`spi`/`i2c`/`netdev`; builds the virtualenv and pins pip; installs the
polkit rule, the scoped `/etc/sudoers.d/mempaper-wifi`, and the
`/usr/local/bin/mempaper-apt-install` wrapper that restricts package installs to
`apt-requirements.txt`; generates and enables the systemd unit; and disables UFW
and `nftables` (see [Host firewall](#host-firewall-do-not-use-ufw)).

> Answering **no** to a prompt is a deliberate choice, not something to fix
> later by re-running the installer — a second run skips anything already
> configured. The manual equivalents are in
> [Manual Installation](MANUAL_INSTALL.md#17-optional-hardening).

### 2. Verify what was applied

Do this once, on a freshly installed device:

```bash
sudo sshd -T | grep -i '^passwordauthentication'   # expect: no
systemctl is-active fail2ban                       # expect: active
systemctl is-enabled mempaper.service              # expect: enabled
sudo nft list ruleset                              # expect: empty
sudo ufw status 2>/dev/null                        # expect: inactive or absent
```

Check `passwordauthentication` against `sshd -T` rather than reading
`sshd_config`. Some Raspberry Pi OS images ship a
`/etc/ssh/sshd_config.d/50-cloud-init.conf` that re-enables password login, and
sshd's `Include` is first-match-wins — so the file can say one thing while the
running daemon does another.

### 3. First login

Open `http://<pi-ip>:5000` and sign in with the admin account you created during
installation. If you skipped that prompt, create one now:

```bash
cd /home/mempaper/btc-mempaper
sudo -u mempaper .venv/bin/python tools/setup_user.py
```

### 4. SSH keys and password login

If you accepted the SSH hardening prompt, password login is **already disabled**
and you need a key to get back in. Add one before you log out of your current
session.

This is also the procedure for giving an admin ongoing access to a device that
has already been delivered.

**On your own machine**, generate a key pair. The private key never leaves it:

```bash
ssh-keygen -t ed25519 -C "your-name-mempaper"
cat ~/.ssh/id_ed25519.pub   # copy this output
```

**On the device**, log into the web UI → **Settings → General → Advanced → SSH
Access** → paste the public key → **Add Key**.

The key is installed for *both* service accounts, each with its own entry that
can be removed individually through the same page:

| Account | Access level | Use it for |
|---|---|---|
| `mempaper` | Scoped sudo | `apt-get upgrade`, service restart, reboot |
| `pi` | Full sudo | `apt dist-upgrade`, system configuration |

```bash
ssh mempaper@<pi-ip>
ssh pi@<pi-ip>
```

**Then disable password login.** Edit `/etc/ssh/sshd_config`:

```bash
# /etc/ssh/sshd_config
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
AuthorizedKeysFile .ssh/authorized_keys
```

```bash
sudo systemctl restart ssh
```

> **Test your SSH key login in a second terminal before closing the current
> session** — otherwise a typo in `sshd_config` locks you out of the device.

Password login is the only part of this worth doing for a home deployment;
restricting SSH by source address is handled by your router, not by a firewall
on the Pi. See [Host firewall](#host-firewall-do-not-use-ufw).

---

## Migrating an existing installation

### From `pi` user to `mempaper` user

If your installation runs as the `pi` user instead of the dedicated `mempaper`
service user, re-run the installer to switch it over:

```bash
cd ~/btc-mempaper
bash install.sh
```

That is the whole migration. The installer creates the service account, adds it
to the `gpio`/`spi`/`i2c`/`netdev` groups, relocates the repo to
`/home/mempaper/btc-mempaper`, reinstalls the polkit and sudoers rules for the
new user, and regenerates the systemd unit. It skips anything already correct,
so re-running it is safe.

Group membership only takes effect after a reboot, so do that before deciding
the display is broken:

```bash
sudo reboot
id mempaper            # afterwards: confirm gpio, spi, i2c, netdev
```

If the Waveshare drivers did not download — most likely the Pi was offline
during the run — configure the display again:

```bash
cd /home/mempaper/btc-mempaper
sudo -u mempaper .venv/bin/python tools/configure_display.py
```

### Update the donation webhook URL

The donation webhook endpoint requires a per-installation secret token in the URL. To (re)configure it:

1. Open **Settings → Lightning Donations**
2. Copy the webhook URL (it includes a 64-character token)
3. Update the webhook URL in your LNbits Pay Link settings

Requests to the bare `/api/donation-webhook` URL (without a valid token) return HTTP 410.

---

## Host firewall: do not use UFW

> **Do not install or enable UFW on a mempaper device**, and do not re-enable
> `nftables`. The installer turns both off on purpose
> ([`install.sh`](../install.sh)), and switching them back on breaks first-time
> setup.

UFW's `ufw-after-input` chain unconditionally drops UDP port 67 (DHCP
broadcasts) *before* any allow-rule you add can accept them. The setup hotspot
runs its own DHCP server, so while UFW is active that server can never reply —
a phone connecting to `mempaper-XXXX` gets no address and the setup page is
unreachable. `nftables` on Trixie causes the same failure.

The trap is that this stays invisible. A device already on Wi-Fi keeps working
perfectly with UFW enabled; the breakage only surfaces later, when the device
falls back to hotspot mode after a Wi-Fi change, a router swap, or a factory
reset — exactly the moment you need it to work, and with no console to debug
from. mempaper installs its own narrow `iptables` rules for the captive portal
while the hotspot is up, and removes them when it shuts down.

**What protects the device instead:**

- **Your router.** NAT drops unsolicited inbound connections, and no port
  forwarding means nothing from the internet reaches port 5000 or 22. This is
  the control that actually matters for a home deployment.
- **The application.** Argon2id password hashing plus login rate limiting gates
  the config page; `public_dashboard` decides whether the read-only view needs
  a login at all.
- **SSH configuration.** Key-only authentication and `PermitRootLogin no`
  restrict shell access without touching the packet filter (see below).

**If you genuinely need per-source filtering** — an untrusted LAN, a shared
office network — do it on the router or a managed switch rather than on the Pi.
That keeps the device's own network stack free for the hotspot. Host-level
filtering on the Pi is only safe if you are certain the device will never need
hotspot onboarding again, and it will not warn you when that assumption breaks.

---

## Deployment-specific hardening

### Home LAN (no internet access)

The default installation is sufficient for most home users:

- Router NAT blocks all inbound internet connections
- `mempaper` auth (Argon2id + rate limiting) is the only barrier needed
- No host firewall — see [above](#host-firewall-do-not-use-ufw)

**Checklist:**
- [x] Strong admin password (minimum 12 characters, unique)
- [x] No port forwarding for port 5000 or 22 on your router
- [x] `unattended-upgrades` enabled for automatic OS security patches (see below)
- [x] UFW and `nftables` left disabled, as the installer configured them

### Internet-accessible via Traefik + OIDC

See the [Self-Hosting Guide](SELF_HOSTING_GUIDE.md) for full Traefik setup. Additionally:

**The session cookie is `HttpOnly` and `SameSite=Strict`, but not `Secure`.**
mempaper is reached over plain HTTP on the LAN, and a `Secure` cookie is never
sent over HTTP — setting it would break login for every local user. The flag is
process-wide, so a device reachable both through Traefik and directly on the LAN
cannot have it both ways.

The practical consequence: if someone reaches the Pi directly on port 5000
instead of through Traefik, the session cookie travels in clear text on your
LAN. Treat that as the reason to keep port 5000 unreachable from anywhere you do
not trust, rather than something a cookie attribute will solve.

**Keep port 5000 off the internet:**

Traefik should be the only route in from outside. Forward only Traefik's ports
(80/443) on your router and never forward 5000 — that, not a host firewall,
is what keeps Flask unreachable directly. Port 5000 stays open to your LAN by
design; see [Known limitations](#known-limitations).

---

## Automatic OS security updates

**The installer sets this up** unless you declined the prompt. Confirm before
adding it again:

```bash
systemctl is-enabled unattended-upgrades
```

If that reports anything other than `enabled`, install it:

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

Optionally reboot automatically once patches need it. `Automatic-Reboot-WithUsers
"false"` holds the reboot back while anyone is logged in over SSH, so it will not
cut off a session mid-command:

```bash
sudo tee /etc/apt/apt.conf.d/52mempaper-reboot > /dev/null <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
```

Note that `apt-mark hold` keeps the Python minor version pinned, so unattended
upgrades can never swap the interpreter out from under the virtualenv — security
patches within the held minor still install. See the
[Maintenance Guide](MAINTENANCE_GUIDE.md).

---

## Sudo rules — what mempaper can do as root

The scoped sudoers file (`/etc/sudoers.d/mempaper-wifi`) grants exactly:

| Command | Purpose |
|---|---|
| `nmcli` | WiFi management via NetworkManager |
| `iw dev * scan passive` | Read-only WiFi scan during AP mode |
| `iptables -t nat/filter ...` | Captive-portal redirect rules (setup hotspot) |
| `dnsmasq --conf-file=/tmp/mempaper-captive-dns.conf ...` | On-demand DNS for captive portal |
| `kill [PID]` / `pkill -f /tmp/mempaper-captive-dns.conf` | Stop captive-portal dnsmasq |
| `mount -o remount,rw/ro /` | Remount root for apt on read-only Pi OS |
| `mount -o remount,rw/ro /boot/firmware` | Remount boot partition for apt (initramfs-tools writes here) |
| `apt update / upgrade -y / autoremove -y` | System package maintenance (SSH admin use) |
| `/usr/local/bin/mempaper-apt-install` | Install packages from `apt-requirements.txt` only |
| `systemctl restart mempaper.service` | Restart after software update |
| `systemctl reboot` | Reboot via web UI |
| `mkdir/tee/chmod/cat` on `/home/pi/.ssh/` | SSH key provisioning for admin access |

The apt install wrapper (`/usr/local/bin/mempaper-apt-install`) is root-owned and accepts no arguments — it reads the package list from `apt-requirements.txt` and cannot be used to install arbitrary packages even if the web process is compromised.

---

## Sensitive data storage

Sensitive fields live in a separate file from the rest of the configuration:

| Field | Storage |
|---|---|
| `admin_password_hash`, `admin_users` | `config/config.sensitive.json` (Argon2id hashes) |
| `wallet_balance_addresses`, `block_reward_addresses` | `config/config.sensitive.json` |
| `mempool_password` | `config/config.sensitive.json` |
| `secret_key` (Flask session) | `config/.secret_key` (permissions 600) |
| `donation_webhook_token` | `config/config.json` (required for webhook validation) |

The separate file is kept at permissions `600` while `config/config.json` stays
group-readable, it is the unit Tang seals, and keeping `tang_url` out of it is
what lets the Tang client start up before the sensitive file is read.

### Encryption at rest

**This file is stored in the clear unless Tang is configured, and that is a
deliberate choice.**

Any key mempaper could derive on its own would have to be reconstructible from
the device, so that anyone holding the Pi could reconstruct it too. Encryption
under such a key looks like protection without being any, and an owner who
believes their addresses are protected makes different decisions than one who
knows they are not.

So the guarantee is stated plainly instead:

- **Physical access to the device means access to this data.**
- File permissions are the only barrier: `600` on the sensitive file, `640` on
  `config/config.json`. That stops other local accounts, not someone with the
  card.
- Nothing is derived at startup, so there is no boot-time cost for a protection
  that would not hold.

**Password hashing is different, and uses Argon2id.** A password carries enough
entropy for a slow hash to be worth the cost, and it is not recoverable from the
hardware, so the maths works out the opposite way. Hashes are safe to store in
the clear by design.

### Protecting the data against a stolen device

Use [Tang](SELF_HOSTING_GUIDE.md#part-8--tang-network-bound-encryption-for-wallet-data-optional).
It seals the sensitive config, the balance caches, the donation history and the
rendered images with a random 256-bit key held on a server on your LAN, so the
key is not on the card at all. Carried off your network the data cannot be
decrypted — there is nothing to guess.

Tang does not protect against SSH or admin access on a running device, or a
thief still on your LAN. Enable it **before** entering wallet addresses: freed
flash blocks retain earlier clear-text copies, which sealing afterwards cannot
reach.

---

## Security audit checklist

A stock install with the default answers already satisfies the *Installation*
and *SSH* sections — verify rather than perform them. Each item below can be
checked with one command.

### Installation

- [ ] Service runs as `mempaper`, not `pi` or `root` — `systemctl show -p User mempaper.service`
- [ ] Scoped sudoers and apt wrapper present — `ls /etc/sudoers.d/mempaper-wifi /usr/local/bin/mempaper-apt-install`
- [ ] At least one admin account exists with a strong password — `sudo -u mempaper .venv/bin/python tools/setup_user.py --list`
- [ ] Config not world-readable — `stat -c '%a' config/config.json` returns `640`

### SSH

- [ ] Password login off in the *effective* config — `sudo sshd -T | grep -i '^passwordauthentication'`
- [ ] Root login off — `sudo sshd -T | grep -i '^permitrootlogin'`
- [ ] A key is actually installed, or the above locks you out — `wc -l < /home/mempaper/.ssh/authorized_keys`

### Network

- [ ] UFW and `nftables` still disabled (re-enabling them breaks hotspot setup) — `sudo nft list ruleset` is empty
- [ ] No port forwarding for port 5000 or 22 on the router (for home users)
- [ ] If using Traefik: port 5000 not forwarded, so 80/443 via Traefik is the only way in

### Application

- [ ] Donation webhook URL updated in LNbits to include the security token
- [ ] Unattended upgrades running — `systemctl is-enabled unattended-upgrades`
- [ ] Mempool queries not leaking your IP — `mempool_host` is a `.onion`, or your own node

---

## Known limitations

- **No CSRF tokens**: SameSite=Strict cookies prevent the vast majority of CSRF attacks, but token-based CSRF protection is not implemented. Risk is low for local network use.
- **LAN bypass of Traefik/OIDC**: Port 5000 is accessible to any LAN device, and the mempaper login is the only barrier for direct LAN access. A host firewall is not the fix here — see [Host firewall](#host-firewall-do-not-use-ufw); restrict at the router or on a VLAN if your LAN is not trusted.
- **Webhook relay trust**: If you use an event-hub relay, the relay URL should include a high-entropy secret token (32+ random bytes). The Pi trusts all events it receives over the WebSocket.
