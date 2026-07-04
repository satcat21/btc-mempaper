#!/usr/bin/env python3
"""
Generate systemd service file for mempaper Bitcoin Dashboard.

This script automatically creates a systemd service file with the correct
paths and user settings based on the current installation directory and user.

Usage:
    python tools/generate_service_file.py
    
The generated file will be saved as 'mempaper.service' in the current directory.
You can then copy it to /etc/systemd/system/ to install the service.
"""

import os
import sys
import pwd
import grp
from pathlib import Path


def get_current_user():
    """Get the current user's username."""
    return pwd.getpwuid(os.getuid()).pw_name


def get_current_group():
    """Get the current user's primary group name."""
    return grp.getgrgid(os.getgid()).gr_name


def get_project_root():
    """Get the absolute path to the project root directory."""
    # Get the directory where this script is located
    script_dir = Path(__file__).resolve().parent
    # Go up one level to get project root
    project_root = script_dir.parent
    return str(project_root)


def generate_service_file():
    """Generate the systemd service file content."""
    user = get_current_user()
    group = get_current_group()
    project_path = get_project_root()
    venv_path = os.path.join(project_path, ".venv")

    # Check if .venv exists
    if not os.path.exists(venv_path):
        print(f"⚠️  Warning: Virtual environment not found at {venv_path}")
        print("   Please create the virtual environment first:")
        print(f"   python3 -m venv {venv_path}")
        print()

    # Home dir of the service user — used for ReadWritePaths so the SSH-key
    # management GUI can write to ~/.ssh/authorized_keys.  ProtectSystem=strict
    # creates a read-only mount namespace; any path that must be writable (even
    # via sudo'd child processes, which inherit the namespace) needs an entry here.
    user_home = os.path.expanduser('~')
    service_user_ssh = os.path.join(user_home, '.ssh')

    # Pi user authorized_keys — the GUI also writes here via 'sudo tee' so that
    # the SSH admin key works regardless of which shell user is used to log in.
    pi_ssh = '/home/pi/.ssh'

    # crontab writes temp files to /var/spool/cron when scheduling meme sync.
    cron_spool = '/var/spool/cron'

    # Build ReadWritePaths lines; deduplicate in case service runs as pi.
    rw_paths = [project_path]
    if service_user_ssh not in rw_paths:
        rw_paths.append(service_user_ssh)
    if pi_ssh not in rw_paths and pi_ssh != service_user_ssh:
        rw_paths.append(pi_ssh)
    if cron_spool not in rw_paths:
        rw_paths.append(cron_spool)
    rw_lines = '\n'.join(f'ReadWritePaths={p}' for p in rw_paths)

    return f"""# /etc/systemd/system/mempaper.service
# Generated automatically by tools/generate_service_file.py

[Unit]
Description=mempaper Bitcoin Dashboard
Documentation=https://github.com/satcat21/btc-mempaper
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/bin/sh -c ". {project_path}/.venv/bin/activate && gunicorn --config {project_path}/gunicorn.conf.py wsgi:application"
WorkingDirectory={project_path}
Restart=always
RestartSec=5
User={user}
Group={group}
Environment="PATH={project_path}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH={project_path}"
Environment="PYTHONUNBUFFERED=1"
Environment="API_RATE_LIMIT_DELAY=3"
Environment="FLASK_ENV=production"
Environment="MAX_REQUESTS_PER_MINUTE=10"
Environment="CACHE_DURATION=300"
Environment="REQUEST_TIMEOUT=30"

# Security settings
# NoNewPrivileges is intentionally omitted: the service needs to call
# 'sudo nmcli' to manage NetworkManager connections (WPA2 hotspot onboarding).
# The sudo rule is narrowly scoped to /usr/bin/nmcli only (see
# /etc/sudoers.d/mempaper-wifi installed by install_wifi_permissions.sh).
TimeoutStopSec=10
PrivateTmp=true
ProtectSystem=strict
ProtectHome=false
{rw_lines}

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mempaper

[Install]
WantedBy=multi-user.target
"""


def main():
    """Main function to generate and save the service file."""
    print("🔧 Generating systemd service file for mempaper...")
    print()
    
    user = get_current_user()
    group = get_current_group()
    project_path = get_project_root()
    
    print(f"📍 Project path: {project_path}")
    print(f"👤 User:         {user}")
    print(f"👥 Group:        {group}")
    print()
    
    service_content = generate_service_file()
    
    # Save to current directory
    output_file = "mempaper.service"
    with open(output_file, 'w') as f:
        f.write(service_content)
    
    print(f"✅ Service file generated successfully: {output_file}")

    if "--quiet" not in sys.argv:
        print()
        print("📋 Next steps:")
        print(f"   1. Review the file: cat {output_file}")
        print(f"   2. Copy to system:  sudo cp {output_file} /etc/systemd/system/")
        print("   3. Reload systemd:  sudo systemctl daemon-reload")
        print("   4. Enable service:  sudo systemctl enable mempaper.service")
        print("   5. Start service:   sudo systemctl start mempaper.service")
        print("   6. Check status:    sudo systemctl status mempaper.service")
        print("   7. View logs:       sudo journalctl -u mempaper.service -f")
        print()
        print("⚠️  Important: Make sure you have created the virtual environment and installed dependencies:")
        print(f"   python3 -m venv {project_path}/.venv")
        print(f"   {project_path}/.venv/bin/pip install -r requirements.txt")
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
