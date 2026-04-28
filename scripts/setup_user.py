#!/usr/bin/env python3
"""
setup_user.py
~~~~~~~~~~~~~
Create or update admin users for the Mempaper application.

Usage:
    python scripts/setup_user.py              # interactive: list users, add/update one
    python scripts/setup_user.py --list       # list existing users and exit
    python scripts/setup_user.py --delete <username>  # remove a user
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.config_manager import ConfigManager
from managers.secure_password_manager import SecurePasswordManager


def _get_managers():
    config_manager = ConfigManager()
    # Disable file watching — this is a standalone CLI script, not the running app
    config_manager._stop_file_watching()
    config_manager.watching_enabled = False
    pm = SecurePasswordManager(config_manager)
    # Migrate legacy single-user format if needed
    pm._migrate_to_multi_user()
    return config_manager, pm


def cmd_list(pm: SecurePasswordManager) -> None:
    users = pm.list_users()
    if not users:
        print("No users configured.")
    else:
        print(f"{len(users)} user(s) configured:")
        for name in users:
            print(f"  - {name}")


def cmd_create(pm: SecurePasswordManager) -> None:
    users = pm.list_users()
    if users:
        print(f"Existing users: {', '.join(users)}")
    print()

    # Username
    try:
        username = input("Username: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    if username in users:
        try:
            confirm = input(f"User '{username}' already exists. Update password? [y/N]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if confirm.lower() != "y":
            print("Aborted.")
            sys.exit(0)

    # Password
    for attempt in range(3):
        try:
            password = getpass.getpass("Password (min 8 chars): ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)

        if len(password) < 8:
            print("Password must be at least 8 characters.")
            continue

        try:
            confirm_pw = getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)

        if password != confirm_pw:
            print("Passwords do not match.")
            continue

        break
    else:
        print("Too many failed attempts.")
        sys.exit(1)

    if pm.create_user(username, password):
        print(f"User '{username}' saved successfully.")
    else:
        print("Failed to save user.")
        sys.exit(1)


def cmd_delete(pm: SecurePasswordManager, config_manager: ConfigManager, username: str) -> None:
    users = pm.list_users()
    if username not in users:
        print(f"User '{username}' not found. Existing users: {', '.join(users) or 'none'}")
        sys.exit(1)

    if len(users) == 1:
        print("Cannot delete the last user — the application would be inaccessible.")
        sys.exit(1)

    try:
        confirm = input(f"Delete user '{username}'? [y/N]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    with config_manager.config_lock:
        u = dict(config_manager.config.get('admin_users') or {})
        u.pop(username, None)
        config_manager.config['admin_users'] = u
    config_manager.save_config()
    print(f"User '{username}' deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Mempaper admin users"
    )
    parser.add_argument("--list", action="store_true", help="List configured users and exit")
    parser.add_argument("--delete", metavar="USERNAME", help="Delete a user")
    args = parser.parse_args()

    config_manager, pm = _get_managers()

    if args.list:
        cmd_list(pm)
    elif args.delete:
        cmd_delete(pm, config_manager, args.delete)
    else:
        cmd_create(pm)


if __name__ == "__main__":
    main()
