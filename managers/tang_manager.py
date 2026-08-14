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


# Everything a Tang failure is allowed to say to a browser. Fixed strings, no
# interpolation from anything a request or a subprocess produced.
TANG_MESSAGES = {
    'no_url': 'No Tang server URL is configured. Enter one above, then check again.',
    'bad_url': ('Tang URL must look like http://host:port '
                '(no spaces, credentials or query string)'),
    'bad_thumbprint': ('Thumbprint must be at least 20 characters of '
                       'base64url (A-Z a-z 0-9 - _)'),
    'adv_timeout': f'No answer within {ADV_TIMEOUT} s',
    'adv_http_client': 'The server refused the request - check the address and port',
    'adv_http_server': 'The Tang server reported an internal error',
    'adv_rejected': 'The server rejected the request',
    'adv_unreachable': ('Could not connect - check the address and that '
                        'tangd is running on it'),
    'adv_unreadable': 'Could not read the advertisement',
    'no_signing_key': 'Could not read a signing key from the advertisement',
    'seal_failed': 'clevis could not seal the key',
    'unseal_failed': 'clevis could not unseal the key',
    'key_exists': 'a sealed key already exists; refusing to replace it',
    'clevis_missing': 'clevis is not installed. Run: sudo apt-get install -y clevis',
    'thumbprint_mismatch': 'The configured thumbprint does not match this server.',
    'no_thumbprint_pinned': 'No thumbprint set, so the server is trusted on sight. Set it to the value shown.',
    'unseal_mismatch': 'The recovered value did not match what was sealed.',
}
TANG_FALLBACK = 'The Tang operation failed - see the server log for details'


class TangError(Exception):
    """A Tang operation failed, named by a code rather than by a message.

    The config page renders these in the browser, so a message built from a
    requests exception or from clevis stderr would put filesystem paths,
    internal hostnames and library internals on a page anyone holding a session
    can read. _detail() sends that text to the journal instead, where it is more
    useful anyway - the check dialog has an Open Log button for exactly this.

    The code is what travels, and check() answers by looking it up in
    TANG_MESSAGES, so no string derived from an exception object reaches the
    response. That is what py/stack-trace-exposure tracks, and it is right to:
    "these messages are hand-written" was an invariant held up by a comment.
    A fixed table holds it up structurally, and stops the next person writing
    f'... {e}' here from quietly undoing it.

    str() still yields the same operator-facing sentence, for the journal and
    for callers like TangStore that fold it into their own reason string.
    """

    def __init__(self, code):
        self.code = code
        super().__init__(TANG_MESSAGES.get(code, TANG_FALLBACK))


def safe_message(exc):
    """The operator-facing text for a failure, read from the fixed table."""
    return TANG_MESSAGES.get(getattr(exc, 'code', None), TANG_FALLBACK)


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
            raise TangError('no_url')
        if not _TANG_URL_RE.match(url):
            raise TangError('bad_url')
        return url

    @staticmethod
    def _checked_thumbprint(thumbprint):
        """Return the thumbprint, empty for none, or raise TangError."""
        thumbprint = (thumbprint or '').strip()
        if thumbprint and not _THUMBPRINT_RE.match(thumbprint):
            raise TangError('bad_thumbprint')
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
            raise TangError('adv_timeout')
        except requests.exceptions.HTTPError as e:
            # The status code is the useful half and carries nothing internal.
            _detail('Tang advertisement rejected', str(e))
            status = getattr(e.response, 'status_code', None)
            if not status:
                raise TangError('adv_rejected')
            raise TangError('adv_http_server' if 500 <= status < 600
                            else 'adv_http_client')
        except requests.exceptions.RequestException as e:
            _detail('Tang server unreachable', str(e))
            raise TangError('adv_unreachable')
        except Exception as e:
            _detail('Tang advertisement failed', str(e))
            raise TangError('adv_unreadable')

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
            raise TangError('no_signing_key')
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
            raise TangError('seal_failed')
        return out

    def unseal(self, jwe: bytes) -> bytes:
        """Recover bytes from a JWE. Fails when the server is unreachable,
        which is the entire point of sealing them this way."""
        ok, out, err = self._run(['clevis', 'decrypt'], stdin_bytes=jwe)
        if not ok:
            _detail('clevis decrypt failed', err)
            raise TangError('unseal_failed')
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
        with the same code: a list of
        {key, name, ok, detail, url, code, error}.
        """
        _, cfg_url, cfg_thp = self.settings()
        url = (url if url is not None else cfg_url).strip().rstrip('/')
        thumbprint = (thumbprint if thumbprint is not None else cfg_thp).strip()

        checks = []

        def add(key, name, ok, detail='', code='', target=''):
            # key identifies the row for the page and for translation; name is
            # the English fallback, used when a language has no entry for it.
            entry = {'key': key, 'name': name, 'ok': bool(ok)}
            if detail:
                entry['detail'] = detail
            if code:
                entry['code'] = code
                entry['error'] = TANG_MESSAGES.get(code, TANG_FALLBACK)
            if target:
                entry['url'] = target
            checks.append(entry)
            return ok

        if not self.clevis_available():
            add('clevis_installed', 'clevis installed', False, code='clevis_missing')
            return checks
        add('clevis_installed', 'clevis installed', True, detail=shutil.which('clevis'))

        if not url:
            add('url_configured', 'Tang URL configured', False, code='no_url')
            return checks
        try:
            url = self._checked_url(url)
        except TangError as e:
            add('url_configured', 'Tang URL configured', False, code=e.code)
            return checks
        add('url_configured', 'Tang URL configured', True, target=url)

        try:
            thumbprint = self._checked_thumbprint(thumbprint)
        except TangError as e:
            add('thumbprint_format', 'Thumbprint well-formed', False, code=e.code)
            return checks

        try:
            advertisement = self.fetch_advertisement(url)
        except TangError as e:
            add('server_reachable', 'Server reachable', False,
                target=f'{url}/adv', code=e.code)
            return checks
        add('server_reachable', 'Server reachable', True, target=f'{url}/adv',
            detail=f'{len(advertisement)} bytes')

        try:
            server_thumbprint = self.signing_thumbprint(advertisement)
        except TangError as e:
            add('advertisement_valid', 'Advertisement valid', False, code=e.code)
            return checks
        add('advertisement_valid', 'Advertisement valid', True, detail=server_thumbprint)

        if thumbprint:
            matched = thumbprint == server_thumbprint
            # The two thumbprints go in detail rather than into the message, so
            # the message itself stays a fixed string the page can translate.
            add('thumbprint_matches', 'Thumbprint matches', matched,
                detail=('pinned' if matched else
                        f'configured: {thumbprint}\nserver:     {server_thumbprint}'),
                code='' if matched else 'thumbprint_mismatch')
            if not matched:
                return checks
        else:
            add('thumbprint_pinned', 'Thumbprint pinned', False,
                detail=server_thumbprint, code='no_thumbprint_pinned')

        probe = os.urandom(32)
        try:
            jwe = self.seal(probe, url=url, thumbprint=thumbprint or server_thumbprint)
        except TangError as e:
            add('seal_test', 'Seal test key', False, code=e.code)
            return checks
        add('seal_test', 'Seal test key', True, detail=f'{len(jwe)} bytes JWE')

        try:
            recovered = self.unseal(jwe)
        except TangError as e:
            add('unseal_test', 'Unseal test key', False, code=e.code)
            return checks
        add('unseal_test', 'Unseal test key', recovered == probe,
            detail='byte-identical' if recovered == probe else '',
            code='' if recovered == probe else 'unseal_mismatch')

        return checks
