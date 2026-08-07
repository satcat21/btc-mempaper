# Security Policy

This document is about **reporting a vulnerability in mempaper**.

If you are instead looking to *secure your own installation* — firewall rules,
SSH hardening, exposing the dashboard safely — see the
[Security Guide](docs/SECURITY_GUIDE.md).

---

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** A public report
tells everyone running mempaper about the flaw before there is a fix available.

Use one of these instead:

1. **GitHub private vulnerability reporting** — on the repository's *Security*
   tab, "Report a vulnerability". This is the preferred route: it is private,
   threaded, and keeps everything in one place.
2. **Email** — <satcat21@proton.me>. If the report is sensitive, encrypt it to
   the PGP key in [`pubkey.asc`](pubkey.asc) at the repository root:

   ```bash
   gpg --import pubkey.asc
   gpg --show-keys pubkey.asc      # verify the fingerprint before trusting it
   gpg --encrypt --armor -r <key-id> report.txt
   ```

### What to include

The more of this you can provide, the faster it can be confirmed:

- What the issue is and what an attacker gains from it
- Steps to reproduce, or a proof of concept
- The mempaper version (`git describe --tags`) and how it is deployed —
  LAN-only, behind a reverse proxy, or internet-exposed
- Anything about the setup that matters: Tor enabled, self-hosted mempool,
  wallet monitoring on

### What to expect

mempaper is maintained by one person as a spare-time project, so please read
these as intentions rather than guarantees:

- An acknowledgement that the report arrived, usually within a few days
- An assessment of whether it is reproducible and how serious it looks
- A fix released as soon as is practical, prioritised by severity
- Credit in the release notes if you would like it — tell me how you want to be
  named, or say if you would rather stay anonymous

There is **no bug bounty**. Nothing is paid for reports.

Please give a reasonable window to ship a fix before disclosing publicly.
Ninety days is the usual convention and is fine here; if a flaw is being
actively exploited, say so and it will be treated with more urgency.

---

## Supported versions

Only the **latest release** receives security fixes. mempaper is a small project
with a single active line — there are no long-term support branches, and older
tags are not patched.

If you are behind, update before reporting: the issue may already be fixed.
The dashboard's built-in updater, or `git pull` followed by a service restart,
is enough.

---

## Scope

**In scope** — anything in this repository:

- Authentication and session handling: login, rate limiting, session lifetime
- The configuration and secrets layer: encrypted config, password hashing,
  the donation webhook token
- Wallet privacy: anything that leaks xpubs, derived addresses or balances
  beyond the configured mempool host
- Web surface: the dashboard, the config page, the REST and WebSocket endpoints
- The installer and the update path, including the sudo rules they add
- Dependency issues, where mempaper's use of the dependency is what makes it
  exploitable

**Out of scope:**

- Vulnerabilities in mempool.space, einundzwanzig-memes.space, Tor, or any other
  third-party service — report those to the people who run them
- Issues that need physical access to the device. Anyone holding the Pi can read
  its SD card; mempaper does not defend against that and does not claim to
- Operator misconfiguration, such as forwarding port 5000 straight to the
  internet. See the [Security Guide](docs/SECURITY_GUIDE.md) for how to avoid it
- Missing hardening that only matters on an internet-exposed deployment which
  the documentation already tells you not to run
- Findings from automated scanners with no demonstrated impact

---

## Known design limits

These are deliberate trade-offs, not bugs. Reporting them is welcome only if you
have found a way to exploit one beyond what is described here.

- **Bitcoin addresses reach the configured mempool host.** That is how balances
  are fetched. The extended public key itself never leaves the device —
  derivation happens locally — but derived addresses are queried. Options for
  narrowing that, including Tor and self-hosting, are compared in
  [Architecture](docs/ARCHITECTURE.md).
- **The dashboard can be read without a login** when `public_dashboard` is
  enabled. That is the point of the setting; the config page always requires
  authentication regardless.
- **The setup hotspot is open** during first-time Wi-Fi onboarding, by
  necessity — you cannot join a network to configure the network. It shuts down
  once Wi-Fi is configured.
- **Secrets are encrypted at rest with a key stored on the same device.** This
  protects against a copied config file, not against someone with root on the
  running machine.
