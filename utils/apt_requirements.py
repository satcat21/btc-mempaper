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
+deb12u2 - so a pinned package stops receiving them. A pin is also codename-
bound: a version that exists in bookworm generally does not exist in trixie, and
the same file is read on both. Pin what actually breaks when it moves, and leave
the rest floating.
"""

from __future__ import annotations

import os


def parse_apt_requirements(path):
    """Read the file into a list of (name, version_or_None), declaration order.

    Comments and blank lines are dropped. A stray '\\r' from a file edited on
    Windows is stripped too - the bash wrapper has always done this with `tr -d`
    and the Python readers never did, so a CRLF checkout produced package names
    with a trailing carriage return that dpkg silently reported as missing.

    A missing file is an empty declaration rather than an error: install.sh and
    the startup check both treat "nothing declared" as "nothing to do", and a
    dev checkout without the file should not raise.
    """
    if not path or not os.path.exists(path):
        return []
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
                out.append((name, version or None))
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
