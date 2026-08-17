#!/usr/bin/env bash
# install_wifi_permissions.sh — compatibility shim for tools/install_permissions.sh
#
# The script grew well past Wi-Fi: it installs the polkit rules, the scoped
# sudoers set and every /usr/local/bin/mempaper-* wrapper, including the apt
# ones. It was renamed to install_permissions.sh to say so.
#
# This shim exists because the old path is baked into things that are already on
# devices and cannot be updated from here:
#
#   /usr/local/bin/mempaper-refresh-permissions  execs this path by absolute name
#   docs, delivery notes and support answers     tell people to run this path
#
# The refresh wrapper is the sharp one. It is what lets a release update the
# permission set without an SSH session, and every device that has run the old
# script holds a copy pointing here. Renaming the file without leaving this
# behind would mean the wrapper execs a path that no longer exists — and the
# wrapper is the only thing that could have repaired the wrapper.
#
# Devices re-run through the new script get a wrapper pointing at the new name,
# so this can be deleted once no supported upgrade path starts from a release
# older than the rename. Two releases is the intended life.

exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install_permissions.sh" "$@"
