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

from utils.paths import PROJECT_ROOT

# Tang answers in milliseconds on a LAN. These bounds exist so an unreachable
# or half-open host cannot wedge a config-page request or the boot path.
ADV_TIMEOUT = 10
CLEVIS_TIMEOUT = 20
DISCOVER_TIMEOUT = 5

# \Z rather than $, which also matches before a trailing newline - these guard
# what is handed to a subprocess, so the end of the string has to mean the end.
_THUMBPRINT_RE = re.compile(r'^[A-Za-z0-9_-]{20,}\Z')

# The URL and thumbprint reach a command line: clevis-encrypt-tang is a shell
# script that hands both to curl. A value starting with '-' would be read as a
# curl option rather than an address, so anything outside this shape is refused
# rather than quoted or escaped - no real Tang URL needs the difference.
_TANG_URL_RE = re.compile(
    r'^https?://'
    r'(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9._-]+)'   # host, or bracketed IPv6 literal
    r'(?::[0-9]{1,5})?'
    r'(?:/[A-Za-z0-9._~/-]*)?\Z'
)


class TangError(Exception):
    """A Tang operation failed. The message is safe to show to an operator.

    Safe means it says what went wrong without quoting the thing that said so.
    The config page renders these verbatim in the browser, so a message built
    from a requests exception or from clevis stderr puts filesystem paths,
    internal hostnames and library internals on a page anyone holding a session
    can read. Use _detail() to send that text to the journal instead, where it
    is more useful anyway - the check dialog has an Open Log button for exactly
    this.
    """


def _detail(context, text):
    """Log the raw text of a failure and keep it out of the exception."""
    text = (text or '').strip()
    if text:
        print(f"⚠️ {context}: {text}")


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

    # ── input the command line will see ──────────────────────────────────────

    @staticmethod
    def _checked_url(url):
        """Return the normalised URL, or raise TangError if it is not one.

        Both the config file and the config page can supply this, and it ends
        up as an argument to clevis, so it is validated at every entry rather
        than trusted because it came from disk.
        """
        url = (url or '').strip().rstrip('/')
        if not url:
            raise TangError('no Tang URL configured')
        if not _TANG_URL_RE.match(url):
            raise TangError('Tang URL must look like http://host:port '
                            '(no spaces, credentials or query string)')
        return url

    @staticmethod
    def _checked_thumbprint(thumbprint):
        """Return the thumbprint, empty for none, or raise TangError."""
        thumbprint = (thumbprint or '').strip()
        if thumbprint and not _THUMBPRINT_RE.match(thumbprint):
            raise TangError('Thumbprint must be at least 20 characters of '
                            'base64url (A-Z a-z 0-9 - _)')
        return thumbprint

    # ── configuration ────────────────────────────────────────────────────────

    def settings(self):
        """(enabled, url, thumbprint) from config, with the URL normalised.

        Read from config.json rather than through ConfigManager. That manager
        answers by loading the sensitive file, which may itself be sealed, so
        going through it while sealing or unsealing recurses back here. All
        three tang keys are non-sensitive and stay in the plain file precisely
        so this lookup can never depend on the thing it is used to unlock.
        """
        cfg = {}
        try:
            with open(os.path.join(PROJECT_ROOT, 'config', 'config.json'),
                      encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
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
        url = self._checked_url(url)
        try:
            resp = requests.get(f'{url}/adv', timeout=ADV_TIMEOUT, proxies={'http': None, 'https': None})
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.Timeout as e:
            _detail('Tang advertisement timed out', str(e))
            raise TangError(f'No answer within {ADV_TIMEOUT} s')
        except requests.exceptions.HTTPError as e:
            # The status code is the useful half and carries nothing internal.
            _detail('Tang advertisement rejected', str(e))
            code = getattr(e.response, 'status_code', None)
            raise TangError(f'Server answered HTTP {code}' if code
                            else 'Server rejected the request')
        except requests.exceptions.RequestException as e:
            _detail('Tang server unreachable', str(e))
            raise TangError('Could not connect - check the address and that '
                            'tangd is running on it')
        except Exception as e:
            _detail('Tang advertisement failed', str(e))
            raise TangError('Could not read the advertisement')

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
            _detail('jose could not read the signing key', err)
            raise TangError('Could not read a signing key from the advertisement')
        return thumbprint

    # ── seal and unseal ──────────────────────────────────────────────────────

    def seal(self, data: bytes, url=None, thumbprint=None) -> bytes:
        """Seal bytes to the Tang server, returning a JWE."""
        _, cfg_url, cfg_thp = self.settings()
        url = self._checked_url(url or cfg_url)
        thumbprint = self._checked_thumbprint(thumbprint or cfg_thp)

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
            _detail('clevis encrypt failed', err)
            raise TangError('clevis could not seal the key')
        return out

    def unseal(self, jwe: bytes) -> bytes:
        """Recover bytes from a JWE. Fails when the server is unreachable,
        which is the entire point of sealing them this way."""
        ok, out, err = self._run(['clevis', 'decrypt'], stdin_bytes=jwe)
        if not ok:
            _detail('clevis decrypt failed', err)
            raise TangError('clevis could not unseal the key')
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
        try:
            url = self._checked_url(url)
        except TangError as e:
            add('Tang URL configured', False, error=str(e))
            return checks
        add('Tang URL configured', True, target=url)

        try:
            thumbprint = self._checked_thumbprint(thumbprint)
        except TangError as e:
            add('Thumbprint well-formed', False, error=str(e))
            return checks

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
