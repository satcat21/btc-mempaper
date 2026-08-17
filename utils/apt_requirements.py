"""What apt-requirements.txt declares, parsed in one place.

The file used to be a bare list of package names, read by five slightly
different snippets - install.sh, the sudo wrapper, the startup dependency check
and both update routes - each re-implementing "strip comments and blanks". That
was survivable while a line was only ever a name. It stops being survivable now
that a line may also carry a version, because a parser that does not know about
the '=' hands 'tor=0.4.8.12-1' to dpkg-query as a package name and reports the
package missing forever.

Grammar, deliberately the same one apt-get install already accepts:

    imagemagick             float - whatever the archive currently offers
    tor=0.4.8.12-1          pinned - exactly this version, and held there

A pin is a promise the device keeps against apt's own upgrade machinery: the
installer puts the named version on and then `apt-mark hold`s it, so neither
`apt upgrade` nor `apt full-upgrade` can move it afterwards. Dropping the '=...'
from a line releases the hold again on the next reconcile.

The cost of a pin is the thing to weigh before adding one. Debian ships security
fixes as new versions of the same upstream release - 1.2.3-4+deb12u1 becomes
+deb12u2 - so a pinned package stops receiving them. Pin what actually breaks
when it moves, and leave the rest floating.

A pin is codename-bound, and the file says which suite it was written for:

    # pins-for: trixie

A version that exists in trixie generally does not exist in bookworm, and the
same file is read on both. Without the directive, a device on the other suite
failed every pin - apt matches a pinned version exactly - and was then held at
whatever it already had, frozen off Debian's security updates while the log
reported the pins applied. With it, such a device installs the same package set
with the versions dropped: floating, unheld, and honest about it. See
pins_apply() for the three cases that keep the pins regardless.
"""

from __future__ import annotations

import os
import re

# The directive that scopes every pin in the file to one Debian suite:
#
#     # pins-for: trixie
#
# A comment line, so every reader that predates it ignores it harmlessly.
_PINS_FOR_RE = re.compile(r'^#\s*pins-for:\s*([A-Za-z0-9_.-]+)', re.IGNORECASE)


def os_codename():
    """VERSION_CODENAME from /etc/os-release, lowercased, or '' if unknown.

    '' covers a dev checkout on Windows or macOS as much as an unreadable file,
    and callers treat it as "cannot tell" rather than as a mismatch.
    """
    try:
        with open('/etc/os-release', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION_CODENAME='):
                    return line.split('=', 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return ''


def pins_target(path):
    """The suite the file's '# pins-for:' directive names, or None if absent."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            for raw in f:
                line = raw.strip().strip('\r')
                if not line:
                    continue
                m = _PINS_FOR_RE.match(line)
                if m:
                    return m.group(1).lower()
    except OSError:
        pass
    return None


def pins_apply(path):
    """(apply, target, actual) - whether this device should honour the pins.

    A pinned version is a string from one suite's archive. apt matches it
    exactly, with no partial matching, so a version pinned for trixie resolves
    to nothing at all on bookworm: every pin fails to install, and the wrapper
    then holds each package at whatever it already had - freezing it off
    Debian's security updates while reporting success. Declaring the suite the
    pins came from turns that into a package set that simply floats instead.

    Three cases deliberately keep the pins:

      no directive     the file predates this mechanism, or its author wants the
                       pins applied unconditionally. Either way, obey the file.
      unknown codename /etc/os-release could not be read. Behaving as declared
                       is the conservative answer - dropping pins would release
                       every hold on a healthy device over a transient read error.
      target matches   the ordinary case.
    """
    target = pins_target(path)
    if not target:
        return True, None, os_codename()
    actual = os_codename()
    if not actual:
        return True, target, ''
    return actual == target, target, actual


def parse_apt_requirements(path, apply_pins=None):
    """Read the file into a list of (name, version_or_None), declaration order.

    Comments and blank lines are dropped. A stray '\\r' from a file edited on
    Windows is stripped too - the bash wrapper has always done this with `tr -d`
    and the Python readers never did, so a CRLF checkout produced package names
    with a trailing carriage return that dpkg silently reported as missing.

    A missing file is an empty declaration rather than an error: install.sh and
    the startup check both treat "nothing declared" as "nothing to do", and a
    dev checkout without the file should not raise.

    `apply_pins` defaults to asking pins_apply() about this device. When the
    answer is no, every entry comes back with version None - the names are
    unchanged, so the same packages are installed, held nowhere and left to
    float. Deciding it here rather than at each call site is what makes the
    startup check, both update routes and the version reports agree without any
    of them knowing the rule. Pass True or False to override.
    """
    if not path or not os.path.exists(path):
        return []
    if apply_pins is None:
        apply_pins = pins_apply(path)[0]
    out = []
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip().strip('\r')
            if not line or line.startswith('#'):
                continue
            # An inline comment after a package is not part of the name.
            # requirements.txt uses them heavily and this file may grow them.
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            name, sep, version = line.partition('=')
            name = name.strip()
            version = version.strip() if sep else None
            if name:
                out.append((name, (version or None) if apply_pins else None))
    return out


def package_names(entries):
    """Just the names - what dpkg-query and apt-mark take.

    Handing either of them a 'name=version' spec is the one mistake this module
    exists to prevent: dpkg-query reports the whole string as an unknown package
    and the caller concludes it is missing.
    """
    return [name for name, _v in entries]


def pinned_versions(entries):
    """{name: version} for the entries that carry one."""
    return {name: version for name, version in entries if version}


def install_specs(entries):
    """The argument list for apt-get install: 'name' or 'name=version'."""
    return [f'{name}={version}' if version else name for name, version in entries]
