"""Data-at-rest sealing backed by a Tang server.

The key is random and lives only in memory once unsealed. On disk there is a
JWE holding it, which can be opened only while the Tang server is reachable -
so a device carried off the network has nothing to guess.

Unsealing happens once, at startup. clevis is a shell script and costs a
process spawn of roughly 100-300 ms per call, so per-read use would be visible
on a Pi Zero. Everything after startup is Fernet against the in-memory key,
which is microseconds.

Three states:

  disabled  tang_enabled is off. Every call is a pass-through and nothing on
            disk changes shape, so leaving Tang off costs nothing.
  ready     the key is held and data can be sealed and opened.
  locked    Tang is configured but could not be reached, so the key is not
            available. Callers must degrade rather than fall back to plaintext:
            silently writing clear text because the server was down would undo
            the protection at the worst possible moment.
"""

import os
import threading

from cryptography.fernet import Fernet, InvalidToken

from managers.tang_manager import TangManager, TangError
from utils.paths import PROJECT_ROOT

# Holds the Tang-sealed data key. Not secret in itself - without the Tang
# server it cannot be opened - but there is no reason to leave it world
# readable either.
KEY_FILE = os.path.join(PROJECT_ROOT, 'config', 'tang_key.jwe')
KEY_FILE_MODE = 0o600


# Everything the store seals, with a label fit to show an operator. Used to
# migrate on enable, to reverse it on disable, and to say exactly what is lost
# when someone discards a key they can no longer open. Anything sealed must be
# listed here or the disable paths will silently miss it.
SEALED_PATHS = [
    ('config/config.sensitive.json',
     'Wallet addresses and xpubs'),
    ('cache/cache.sensitive.json',
     'Balance and block-reward caches'),
    ('cache/async_wallet_address_cache.sensitive.json',
     'Derived wallet addresses'),
    ('cache/donations.json',
     'Lightning donation history'),
    ('cache/current.png',
     'Rendered dashboard image'),
    ('cache/current.webp',
     'Rendered dashboard image (WebP)'),
    ('cache/current_eink.png',
     'Rendered e-ink image'),
]


def sealed_targets(root=None):
    """(absolute path, label) for every sealed file that currently exists."""
    base = root or PROJECT_ROOT
    found = []
    for rel, label in SEALED_PATHS:
        path = os.path.join(base, rel)
        if os.path.exists(path):
            found.append((path, label))
    return found


class TangLocked(Exception):
    """Sealed data was requested while the key is unavailable."""


_shared_store = None
_shared_lock = threading.Lock()


def get_shared_store(config_manager=None):
    """The process-wide store, unsealing at most once.

    Several components need sealed I/O - the config manager, the cache manager
    and the app itself - and each unseal is a clevis process spawn. Sharing one
    instance keeps that to a single call at startup, and means they cannot
    disagree about whether sealing is currently available.
    """
    global _shared_store
    with _shared_lock:
        if _shared_store is None:
            _shared_store = TangStore(config_manager)
            _shared_store.unlock()
        elif config_manager is not None and _shared_store.config_manager is None:
            # Created during early startup with nothing to ask; adopt the real
            # manager now that one exists.
            _shared_store.config_manager = config_manager
        return _shared_store


class TangStore:
    """Seals and opens byte strings using a key held by a Tang server."""

    DISABLED = 'disabled'
    READY = 'ready'
    LOCKED = 'locked'

    def __init__(self, config_manager, tang_manager=None, key_file=KEY_FILE):
        self.config_manager = config_manager
        self.tang = tang_manager or TangManager(config_manager)
        self.key_file = key_file
        self._fernet = None
        self._state = self.DISABLED
        self._reason = ''
        self._lock = threading.Lock()

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def state(self):
        return self._state

    @property
    def reason(self):
        """Why the store is locked, in a form fit to show an operator."""
        return self._reason

    def _plain_config(self):
        """tang_* read straight from config.json.

        The store has to answer before ConfigManager has finished building,
        because the first thing that manager does is read config.sensitive.json -
        which may itself be sealed. None of the three tang keys are sensitive,
        so they live in the plain file and can be read without the app.
        """
        import json
        try:
            with open(os.path.join(PROJECT_ROOT, 'config', 'config.json'),
                      encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def is_enabled(self):
        cfg = {}
        if self.config_manager is not None:
            try:
                cfg = self.config_manager.get_current_config() or {}
            except Exception:
                cfg = {}
        if 'tang_enabled' not in cfg:
            cfg = self._plain_config()
        return bool(cfg.get('tang_enabled'))

    def is_ready(self):
        return self._state == self.READY

    def has_sealed_key(self):
        return os.path.exists(self.key_file)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def unlock(self):
        """Open the sealed key. Called once at startup and on retry.

        Returns True when the store is usable afterwards, which includes the
        disabled case: nothing to open means nothing is wrong.
        """
        with self._lock:
            if not self.is_enabled():
                self._fernet, self._state, self._reason = None, self.DISABLED, ''
                return True

            if not self.has_sealed_key():
                self._fernet = None
                self._state = self.LOCKED
                self._reason = ('Tang is enabled but no sealed key exists yet. '
                                'Save the configuration to provision one.')
                return False

            try:
                with open(self.key_file, 'rb') as f:
                    jwe = f.read()
                key = self.tang.unseal(jwe)
            except (OSError, TangError) as e:
                self._fernet = None
                self._state = self.LOCKED
                self._reason = f'Tang server unreachable: {e}'
                return False

            try:
                self._fernet = Fernet(key)
            except Exception as e:
                self._fernet = None
                self._state = self.LOCKED
                self._reason = f'Sealed key is not usable: {e}'
                return False

            self._state = self.READY
            self._reason = ''
            return True

    def provision(self):
        """Create and seal a new data key. Only for first enable.

        Refuses to overwrite an existing sealed key, because doing so would
        strand every record already written under the old one.
        """
        with self._lock:
            if self.has_sealed_key():
                raise TangError('a sealed key already exists; refusing to replace it')

            key = Fernet.generate_key()
            jwe = self.tang.seal(key)

            directory = os.path.dirname(self.key_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.key_file + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(jwe)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, KEY_FILE_MODE)
            os.replace(tmp, self.key_file)

            self._fernet = Fernet(key)
            self._state = self.READY
            self._reason = ''
            return True

    def discard_key(self):
        """Delete the sealed key. Used when turning Tang off, once every record
        has been rewritten in the clear, and by the recovery path for a Tang
        server that is never coming back."""
        with self._lock:
            try:
                os.remove(self.key_file)
            except FileNotFoundError:
                pass
            self._fernet = None
            self._state = self.DISABLED
            self._reason = ''

    # ── sealing ──────────────────────────────────────────────────────────────

    def seal_bytes(self, data: bytes) -> bytes:
        """Seal bytes when enabled, pass them through when not.

        Raises TangLocked rather than writing clear text when Tang is
        configured but unavailable. A caller that cannot seal must skip the
        write, not downgrade it.
        """
        if self._state == self.DISABLED:
            if self.is_enabled():
                # Config says sealing is on but this store never unlocked, so
                # passing the bytes through would write clear text under a
                # configuration that promises otherwise. Refuse instead.
                raise TangLocked('Tang is enabled but this store is not unlocked')
            return data
        if self._state != self.READY or self._fernet is None:
            raise TangLocked(self._reason or 'Tang key unavailable')
        return self._fernet.encrypt(data)

    def open_bytes(self, data: bytes) -> bytes:
        """Recover bytes sealed by seal_bytes.

        Data written while Tang was off is returned untouched, so switching it
        on does not orphan what is already there.
        """
        if self._state == self.DISABLED:
            if self.is_enabled() and self.looks_sealed(data):
                # Sealed content with no key to open it. Returning it verbatim
                # is how this surfaced in the field: the caller handed
                # ciphertext to json.loads and reported a parse error, hiding
                # the real cause. Say what is actually wrong.
                raise TangLocked('Tang is enabled but this store is not unlocked')
            return data
        if self._state != self.READY or self._fernet is None:
            raise TangLocked(self._reason or 'Tang key unavailable')
        try:
            return self._fernet.decrypt(data)
        except InvalidToken:
            # Written before Tang was enabled. Fernet tokens start with a
            # version byte of 0x80, which no JSON or PNG payload begins with,
            # so this is a safe distinction to make.
            return data

    # ── recognising what is already on disk ──────────────────────────────────

    # A Fernet token is base64url of 0x80 followed by an 8-byte big-endian
    # timestamp, so the encoded form starts 'gAAAAA' for every timestamp below
    # 2^32 - i.e. until 2106. No JSON, PNG or JWE payload begins that way, so
    # this distinguishes sealed from unsealed content without guessing.
    SEALED_PREFIX = b'gAAAAA'

    @classmethod
    def looks_sealed(cls, data: bytes) -> bool:
        """True when data was produced by seal_bytes."""
        return bool(data) and data.startswith(cls.SEALED_PREFIX)

    def migrate_path(self, path, mode=0o600):
        """Seal a file that is still in the clear, leaving sealed ones alone.

        Returns 'sealed', 'already-sealed', or 'missing'. Reads and rewrites
        atomically, so an interrupted run leaves the original intact rather
        than a half-converted file.

        This cannot reach copies wear-levelling has already scattered across
        freed flash blocks - see docs/SELF_HOSTING_GUIDE.md. Sealing an
        existing device protects it from here on, not retroactively.
        """
        if self._state != self.READY:
            raise TangLocked(self._reason or 'Tang key unavailable')
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return 'missing'
        if self.looks_sealed(raw):
            return 'already-sealed'
        self.write_file(path, raw, mode=mode)
        return 'sealed'

    def unmigrate_path(self, path, mode=0o600):
        """Rewrite a sealed file in the clear, for turning Tang off.

        Returns 'unsealed', 'already-clear', or 'missing'. Requires the key,
        which is why disabling Tang has to happen while the server is still
        reachable.
        """
        if self._state != self.READY:
            raise TangLocked(self._reason or 'Tang key unavailable')
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return 'missing'
        if not self.looks_sealed(raw):
            return 'already-clear'
        plain = self._fernet.decrypt(raw)
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'wb') as f:
            f.write(plain)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        return 'unsealed'

    # ── convenience for whole files ──────────────────────────────────────────

    def write_file(self, path, data: bytes, mode=0o600):
        """Write bytes to disk, sealed when enabled, atomically either way."""
        payload = self.seal_bytes(data)
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)

    def read_file(self, path):
        """Read and open a file written by write_file, or None if absent."""
        try:
            with open(path, 'rb') as f:
                return self.open_bytes(f.read())
        except FileNotFoundError:
            return None

    def enable(self, root=None):
        """Provision a key and seal whatever is already on disk.

        Idempotent: an existing key is reused rather than replaced, and files
        already sealed are left alone, so a repeated call is harmless.

        What this cannot do is reach copies that wear-levelling has scattered
        across freed flash blocks. Enabling on a device that has already held
        wallet addresses in the clear protects it from here on, not
        retroactively - see docs/SELF_HOSTING_GUIDE.md.
        """
        if not self.has_sealed_key():
            self.provision()
        elif not self.unlock():
            raise TangLocked(self._reason or 'Tang server unreachable')

        result = {'sealed': [], 'already_sealed': [], 'failed': []}
        for path, label in sealed_targets(root):
            try:
                outcome = self.migrate_path(path)
            except Exception as e:
                result['failed'].append({'label': label, 'error': str(e)[:200]})
                continue
            if outcome == 'sealed':
                result['sealed'].append(label)
            elif outcome == 'already-sealed':
                result['already_sealed'].append(label)
        return result

    def disable_preview(self, root=None):
        """What turning Tang off would do, without doing any of it.

        Two very different outcomes depending on whether the server answers,
        so the caller can put the destructive one behind a confirmation.
        """
        recoverable = self.is_ready() or self.unlock()
        items = []
        for path, label in sealed_targets(root):
            try:
                with open(path, 'rb') as f:
                    head = f.read(len(self.SEALED_PREFIX))
            except OSError:
                continue
            if self.looks_sealed(head):
                items.append({'path': os.path.relpath(path, root or PROJECT_ROOT),
                              'label': label})
        return {
            'recoverable': bool(recoverable),
            'reason': '' if recoverable else self._reason,
            'items': items,
        }

    def disable(self, discard=False, root=None):
        """Turn sealing off.

        With the server reachable every sealed file is rewritten in the clear
        and nothing is lost. With discard=True and no server, the sealed files
        and the key are deleted instead - they cannot be opened again, so
        leaving them would only strand unreadable data on the card. Callers
        must confirm that with the operator first.
        """
        result = {'unsealed': [], 'deleted': [], 'discarded_key': False}

        if self.is_ready() or self.unlock():
            for path, _ in sealed_targets(root):
                if self.unmigrate_path(path) == 'unsealed':
                    result['unsealed'].append(path)
            self.discard_key()
            result['discarded_key'] = True
            return result

        if not discard:
            raise TangLocked(self._reason
                             or 'Tang server unreachable; cannot unseal to disable')

        # Unreachable and the operator accepted the loss. Only remove files
        # that are actually sealed: a clear-text donations.json written before
        # Tang was switched on is still perfectly readable and must survive.
        for path, _ in sealed_targets(root):
            try:
                with open(path, 'rb') as f:
                    head = f.read(len(self.SEALED_PREFIX))
            except OSError:
                continue
            if not self.looks_sealed(head):
                continue
            try:
                os.remove(path)
                result['deleted'].append(path)
            except OSError:
                pass

        self.discard_key()
        result['discarded_key'] = True
        return result

    def status(self):
        """Summary for the dashboard and the config page."""
        return {
            'state': self._state,
            'enabled': self.is_enabled(),
            'has_sealed_key': self.has_sealed_key(),
            'reason': self._reason,
        }
