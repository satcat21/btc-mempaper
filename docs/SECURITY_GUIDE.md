# mempaper Security Guide

This guide covers the full security posture of a mempaper installation and how to harden it for your deployment scenario.

---

## Threat model

mempaper is designed for **trusted local networks**. It is not designed to be directly exposed to the internet without additional protection (reverse proxy + authentication layer).

| Scenario | Risk level | Required hardening |
|---|---|---|
| Home LAN, no port forwarding | Low | Strong password, default setup is sufficient |
| Home LAN with internet exposure via Traefik | Medium | Traefik + OIDC + UFW (see Self-Hosting Guide) |
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
# On the Pi, as the 'pi' user (or any sudo-capable user):
git clone https://github.com/your-org/btc-mempaper.git ~/btc-mempaper
cd ~/btc-mempaper
bash install.sh
```

`install.sh` will:
- Create the `mempaper` service user
- Add it to the `gpio`, `spi`, `i2c`, `netdev` groups (required for display and WiFi)
- Install the Python virtual environment as the `mempaper` user
- Generate the systemd service file

### 2. Install WiFi and sudo permissions

```bash
sudo bash ~/btc-mempaper/tools/install_wifi_permissions.sh mempaper
```

This installs:
- Polkit rules for NetworkManager (WiFi onboarding)
- A scoped `/etc/sudoers.d/mempaper-wifi` with exactly the commands mempaper needs
- The `/usr/local/bin/mempaper-apt-install` wrapper (restricts package installs to `apt-requirements.txt`)

### 3. Enable and start the service

```bash
sudo systemctl enable mempaper.service
sudo systemctl start mempaper.service
```

### 4. First-time admin setup

Open `http://<pi-ip>:5000` in a browser. You will be prompted to create an admin user. Use a strong, unique password (a password manager is recommended).

### 5. Harden SSH access (recommended)

Generate an SSH key pair on your computer:

```bash
ssh-keygen -t ed25519 -C "mempaper-admin"
```

Add the public key to the Pi via **Settings → General → Advanced → SSH Access**, then disable password-based SSH:

```bash
# /etc/ssh/sshd_config
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
```

```bash
sudo systemctl restart ssh
```

> **Test your SSH key login before closing the current session.**

---

## Migrating an existing installation

### From `pi` user to `mempaper` user

If your installation runs as the `pi` user instead of the dedicated `mempaper` service user, re-run the installer to switch it over:

```bash
cd ~/btc-mempaper
bash install.sh
```

Then reinstall the WiFi permissions for the new user:

```bash
sudo bash tools/install_wifi_permissions.sh mempaper
```

Check that the display still works (the `mempaper` user needs the hardware groups):

```bash
sudo usermod -aG gpio,spi,i2c mempaper
# Reboot or log out and back in for group changes to take effect
```

If the Waveshare drivers were not downloaded, run the display configuration tool:

```bash
sudo -u mempaper .venv/bin/python tools/configure_display.py 1
```

### Update the donation webhook URL

The donation webhook endpoint requires a per-installation secret token in the URL. To (re)configure it:

1. Open **Settings → Lightning Donations**
2. Copy the webhook URL (it includes a 64-character token)
3. Update the webhook URL in your LNbits Pay Link settings

Requests to the bare `/api/donation-webhook` URL (without a valid token) return HTTP 410.

---

## Firewall configuration (UFW)

For **all deployments**, apply UFW rules to limit surface:

```bash
# Allow mempaper web UI only from your home network
sudo ufw allow from 192.168.0.0/16 to any port 5000
sudo ufw allow from 10.0.0.0/8 to any port 5000
sudo ufw allow from 172.16.0.0/12 to any port 5000

# Restrict SSH to LAN only
sudo ufw allow from 192.168.0.0/16 to any port 22
sudo ufw allow from 10.0.0.0/8 to any port 22
sudo ufw allow from 172.16.0.0/12 to any port 22

# Block everything else (including internet)
sudo ufw --force enable
```

> `192.168.0.0/16` covers all common home router subnets including FritzBox (`192.168.178.x`).

---

## Deployment-specific hardening

### Home LAN (no internet access)

The default installation is sufficient for most home users:

- Router NAT blocks all inbound internet connections
- `mempaper` auth (Argon2id + rate limiting) is the only barrier needed
- UFW is optional but recommended for defense in depth

**Checklist:**
- [x] Strong admin password (minimum 12 characters, unique)
- [x] No port forwarding for port 5000 or 22 on your router
- [x] `unattended-upgrades` enabled for automatic OS security patches (see below)
- [ ] UFW enabled (optional, but good practice)

### Internet-accessible via Traefik + OIDC

See the [Self-Hosting Guide](SELF_HOSTING_GUIDE.md) for full Traefik setup. Additionally:

**Set the `MEMPAPER_BEHIND_PROXY` environment variable** so the session cookie gets the `Secure` flag:

Add to `/etc/systemd/system/mempaper.service` in the `[Service]` section:

```ini
Environment="MEMPAPER_BEHIND_PROXY=1"
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mempaper.service
```

Without this flag, the `Secure` cookie attribute is not set, meaning browsers may send the session cookie over HTTP if the Pi is ever accessed directly (bypassing Traefik).

**Restrict port 5000 with UFW:**

If you want all traffic to go through Traefik (not directly to Flask), bind UFW to block direct port 5000 access from outside your LAN, and ensure Traefik is the only way in from the internet.

---

## Automatic OS security updates

Install `unattended-upgrades` to keep the Pi patched automatically:

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

This installs security updates automatically without manual intervention.

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

Sensitive fields are stored in an encrypted configuration file:

| Field | Storage |
|---|---|
| `admin_password_hash` (Argon2id) | `config/config.secure.json` (AES-128) |
| `wallet_balance_addresses` | `config/config.secure.json` |
| `block_reward_addresses` | `config/config.secure.json` |
| `secret_key` (Flask session) | `config/.secret_key` (permissions 600) |
| `donation_webhook_token` | `config/config.json` (not sensitive to encrypt, required for webhook validation) |

The encryption key is derived from the Pi's hardware fingerprint (CPU serial + MAC address) — the encrypted config cannot be decrypted on a different device.

---

## Security audit checklist

### Installation

- [ ] `mempaper` service user created (not running as `pi` or `root`)
- [ ] `install_wifi_permissions.sh mempaper` run (scoped sudoers, apt wrapper installed)
- [ ] Admin password set via first-time setup (not the old default `mempaper2025`)

### SSH

- [ ] SSH key uploaded via web UI (Settings → General → Advanced → SSH Access)
- [ ] `PasswordAuthentication no` in `/etc/ssh/sshd_config`
- [ ] `PermitRootLogin no` in `/etc/ssh/sshd_config`
- [ ] SSH restricted to LAN via UFW

### Network

- [ ] UFW enabled with LAN-only rules for port 5000 and 22
- [ ] No port forwarding for port 5000 or 22 on the router (for home users)
- [ ] If using Traefik: `MEMPAPER_BEHIND_PROXY=1` set in systemd unit

### Application

- [ ] Donation webhook URL updated in LNbits to include the security token
- [ ] `unattended-upgrades` installed and enabled

---

## Known limitations

- **No CSRF tokens**: SameSite=Strict cookies prevent the vast majority of CSRF attacks, but token-based CSRF protection is not implemented. Risk is low for local network use.
- **LAN bypass of Traefik/OIDC**: Port 5000 is accessible to any LAN device. The mempaper login is the only barrier for direct LAN access. Use UFW to restrict if needed.
- **Webhook relay trust**: If you use an event-hub relay, the relay URL should include a high-entropy secret token (32+ random bytes). The Pi trusts all events it receives over the WebSocket.
