"""Network-bound encryption against a Tang server on the LAN.

Tang ships no client of its own, so every operation here shells out to clevis,
the reference implementation. Rolling our own would mean writing the blinding
step of the McCallum-Relyea exchange, where a mistake silently destroys the
security property while everything still appears to work.

The key mempaper seals is random and never derived from anything on the device,
so an attacker holding the SD card has nothing to guess: recovering it requires
the Tang server's private key.
"""

import json
import os
import re
import shutil
import subprocess

# Tang answers in milliseconds on a LAN. These bounds exist so an unreachable
# or half-open host cannot wedge a config-page request or the boot path.
ADV_TIMEOUT = 10
CLEVIS_TIMEOUT = 20
DISCOVER_TIMEOUT = 5

_THUMBPRINT_RE = re.compile(r'^[A-Za-z0-9_-]{20,}$')


class TangError(Exception):
    """A Tang operation failed. The message is safe to show to an operator."""


class TangManager:
    """Seal and unseal a key against a Tang server, and report on the link."""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager

    # ── environment ──────────────────────────────────────────────────────────

    @staticmethod
    def clevis_available():
        """True when the clevis client is installed."""
        return shutil.which('clevis') is not None

    @staticmethod
    def _run(cmd, stdin_bytes=None, timeout=CLEVIS_TIMEOUT):
        """Run a command, returning (ok, stdout_bytes, stderr_text)."""
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except FileNotFoundError:
            return False, b'', f'{cmd[0]} not found'
        except subprocess.TimeoutExpired:
            return False, b'', f'timed out after {timeout}s'
        except Exception as e:
            return False, b'', str(e)
        return proc.returncode == 0, proc.stdout, proc.stderr.decode('utf-8', 'replace').strip()

    # ── configuration ────────────────────────────────────────────────────────

    def settings(self):
        """(enabled, url, thumbprint) from config, with the URL normalised."""
        cfg = self.config_manager.get_current_config() if self.config_manager else {}
        url = (cfg.get('tang_url') or '').strip().rstrip('/')
        return (bool(cfg.get('tang_enabled')), url,
                (cfg.get('tang_thumbprint') or '').strip())

    # ── server interrogation ─────────────────────────────────────────────────

    def fetch_advertisement(self, url):
        """Raw advertisement JSON from the server, or raise TangError.

        Uses requests rather than curl so a proxy configured for mempool
        traffic cannot accidentally capture a LAN request.
        """
        import requests
        try:
            resp = requests.get(f'{url}/adv', timeout=ADV_TIMEOUT, proxies={'http': None, 'https': None})
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            raise TangError(str(e))

    def signing_thumbprint(self, advertisement):
        """Thumbprint of the advertisement's signing key.

        tangd-keygen writes two keys and clevis pins the signing one, so the
        exchange key's thumbprint would fail every time it was used.
        """
        ok, out, err = self._run(
            ['sh', '-c',
             'jose fmt --json=- -g payload -y -o- '
             '| jose jwk use -i- -r -u verify -o- '
             '| jose jwk thp -i-'],
            stdin_bytes=advertisement.encode(),
        )
        thumbprint = out.decode('utf-8', 'replace').strip()
        if not ok or not _THUMBPRINT_RE.match(thumbprint):
            raise TangError(err or 'could not read a signing key from the advertisement')
        return thumbprint

    # ── seal and unseal ──────────────────────────────────────────────────────

    def seal(self, data: bytes, url=None, thumbprint=None) -> bytes:
        """Seal bytes to the Tang server, returning a JWE."""
        _, cfg_url, cfg_thp = self.settings()
        url = (url or cfg_url).rstrip('/')
        thumbprint = thumbprint or cfg_thp
        if not url:
            raise TangError('no Tang URL configured')

        pin = {'url': url}
        if thumbprint:
            pin['thp'] = thumbprint
        cmd = ['clevis', 'encrypt', 'tang', json.dumps(pin)]
        if not thumbprint:
            # Without a pin clevis asks for interactive confirmation, which
            # would hang a background thread forever.
            cmd.append('-y')

        ok, out, err = self._run(cmd, stdin_bytes=data)
        if not ok or not out:
            raise TangError(err or 'clevis could not seal the key')
        return out

    def unseal(self, jwe: bytes) -> bytes:
        """Recover bytes from a JWE. Fails when the server is unreachable,
        which is the entire point of sealing them this way."""
        ok, out, err = self._run(['clevis', 'decrypt'], stdin_bytes=jwe)
        if not ok:
            raise TangError(err or 'clevis could not unseal the key')
        return out

    # ── discovery ────────────────────────────────────────────────────────────

    def discover(self):
        """Tang servers advertising _tang._tcp over mDNS, best effort.

        Returns a list of {host, port, url}. Empty when avahi is absent or
        nothing advertises itself, which is not an error - it just means the
        operator types the address instead.
        """
        if not shutil.which('avahi-browse'):
            return []
        ok, out, _ = self._run(
            ['avahi-browse', '-tprk', '_tang._tcp'], timeout=DISCOVER_TIMEOUT)
        if not ok:
            return []

        found, seen = [], set()
        for line in out.decode('utf-8', 'replace').splitlines():
            # Resolved records look like: =;iface;proto;name;type;domain;host;addr;port;txt
            parts = line.split(';')
            if not line.startswith('=') or len(parts) < 9:
                continue
            address, port = parts[7].strip(), parts[8].strip()
            if not address or not port.isdigit() or address in seen:
                continue
            seen.add(address)
            found.append({'host': address, 'port': int(port),
                          'url': f'http://{address}:{port}'})
        return found

    # ── diagnostics for the config page ──────────────────────────────────────

    def check(self, url=None, thumbprint=None):
        """Walk the whole path and report each step.

        Shaped like the mempool validator so the config page can render both
        with the same code: a list of {name, ok, detail, url, error}.
        """
        _, cfg_url, cfg_thp = self.settings()
        url = (url if url is not None else cfg_url).strip().rstrip('/')
        thumbprint = (thumbprint if thumbprint is not None else cfg_thp).strip()

        checks = []

        def add(name, ok, detail='', error='', target=''):
            entry = {'name': name, 'ok': bool(ok)}
            if detail:
                entry['detail'] = detail
            if error:
                entry['error'] = error
            if target:
                entry['url'] = target
            checks.append(entry)
            return ok

        if not self.clevis_available():
            add('clevis installed', False,
                error='clevis is not installed. Run: sudo apt-get install -y clevis')
            return checks
        add('clevis installed', True, detail=shutil.which('clevis'))

        if not url:
            add('Tang URL configured', False,
                error='No Tang server URL set. Enter one above, then check again.')
            return checks
        add('Tang URL configured', True, target=url)

        try:
            advertisement = self.fetch_advertisement(url)
        except TangError as e:
            add('Server reachable', False, target=f'{url}/adv', error=str(e))
            return checks
        add('Server reachable', True, target=f'{url}/adv',
            detail=f'{len(advertisement)} bytes')

        try:
            server_thumbprint = self.signing_thumbprint(advertisement)
        except TangError as e:
            add('Advertisement valid', False, error=str(e))
            return checks
        add('Advertisement valid', True, detail=server_thumbprint)

        if thumbprint:
            matched = thumbprint == server_thumbprint
            add('Thumbprint matches', matched,
                detail='pinned' if matched else '',
                error='' if matched else
                      f'Configured thumbprint does not match this server.\n'
                      f'configured: {thumbprint}\nserver:     {server_thumbprint}')
            if not matched:
                return checks
        else:
            add('Thumbprint pinned', False,
                error='No thumbprint set, so the server is trusted on sight. '
                      f'Set it to:\n{server_thumbprint}')

        probe = os.urandom(32)
        try:
            jwe = self.seal(probe, url=url, thumbprint=thumbprint or server_thumbprint)
        except TangError as e:
            add('Seal test key', False, error=str(e))
            return checks
        add('Seal test key', True, detail=f'{len(jwe)} bytes JWE')

        try:
            recovered = self.unseal(jwe)
        except TangError as e:
            add('Unseal test key', False, error=str(e))
            return checks
        add('Unseal test key', recovered == probe,
            detail='byte-identical' if recovered == probe else '',
            error='' if recovered == probe else 'Recovered value did not match')

        return checks
