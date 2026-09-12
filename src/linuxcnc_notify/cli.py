import argparse
import grp
import importlib.util
import json
import os
import platform
import pwd
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

from . import __version__
from .core import CONFIG_PATH, NOTIFY_CONFIG_PATH, daemon, ensure_config, load_config, publish, subscription_deep_link

DROP_IN = "/etc/systemd/system/linuxcnc-notify.service.d/user.conf"


def pair(config):
    print("LinuxCNC Notify phone pairing")
    print(f"Server: {config['server']}")
    print(f"Topic:  {config['topic']}")
    print(f"Web:    http://localhost:{config['web_port']}/pair")
    if shutil.which("qrencode"):
        print("\nScan this code to subscribe in the ntfy app:\n")
        subprocess.run(["qrencode", "-t", "ANSIUTF8", subscription_deep_link(config)], check=False)
    print("\nThe QR uses ntfy's ntfy:// app link. If app-link handling is disabled, add the server and topic shown above manually.")


def doctor():
    checks = [
        ("Python", platform.python_version(), sys.version_info >= (3, 7)),
        ("LinuxCNC Python module", "available" if importlib.util.find_spec("linuxcnc") else "missing",
         importlib.util.find_spec("linuxcnc") is not None),
        ("systemctl", shutil.which("systemctl") or "missing", shutil.which("systemctl") is not None),
    ]
    failed = False
    for name, detail, okay in checks:
        print(f"{'OK' if okay else 'FAIL':4}  {name}: {detail}")
        failed |= not okay
    if failed:
        print("\nLinuxCNC Notify cannot run until the failed requirement is available.")
        return 1
    print("\nThis installation is compatible.")
    return 0


def setup_user(username=None):
    if os.geteuid() != 0:
        print("Setup must be run with sudo.", file=sys.stderr)
        return 1
    username = username or os.environ.get("SUDO_USER")
    if not username or username == "root":
        print("Could not detect the desktop user. Use: sudo linuxcnc-notify setup --user USERNAME", file=sys.stderr)
        return 1
    try:
        account = pwd.getpwnam(username)
    except KeyError:
        print(f"User does not exist: {username}", file=sys.stderr)
        return 1

    config = ensure_config()
    os.chown(CONFIG_PATH, account.pw_uid, account.pw_gid)
    os.chmod(CONFIG_PATH, 0o600)
    CONFIG_PATH.parent.chmod(0o755)
    if NOTIFY_CONFIG_PATH.exists():
        os.chmod(NOTIFY_CONFIG_PATH, 0o644)

    state_directory = Path("/var/lib/linuxcnc-notify")
    state_directory.mkdir(parents=True, exist_ok=True)
    os.chown(state_directory, account.pw_uid, account.pw_gid)
    os.chmod(state_directory, 0o700)

    drop_in = Path(DROP_IN)
    drop_in.parent.mkdir(parents=True, exist_ok=True)
    group_name = grp.getgrgid(account.pw_gid).gr_name
    drop_in.write_text(f"[Service]\nUser={username}\nGroup={group_name}\n", encoding="utf-8")
    os.chmod(drop_in, 0o644)

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "linuxcnc-notify.service"], check=True)
    subprocess.run(["systemctl", "restart", "linuxcnc-notify.service"], check=True)
    print(f"LinuxCNC Notify is configured to run as {username}.")
    print(f"Topic preserved: {config['topic']}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="linuxcnc-notify")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("daemon")
    sub.add_parser("pair")
    sub.add_parser("show-config")
    sub.add_parser("show-notifications")
    sub.add_parser("test")
    sub.add_parser("doctor")
    setup_parser = sub.add_parser("setup")
    setup_parser.add_argument("--user")
    args = parser.parse_args()
    try:
        config = ensure_config()
        if args.command == "daemon":
            daemon()
        elif args.command == "pair":
            pair(config)
        elif args.command == "show-config":
            print(json.dumps(config, indent=2))
        elif args.command == "show-notifications":
            print(NOTIFY_CONFIG_PATH.read_text(encoding="utf-8"))
        elif args.command == "test":
            publish(config, "LinuxCNC Notify test", f"Notifications are configured for {config['machine_name']}", tags=["white_check_mark"])
            print("Test notification sent.")
        elif args.command == "doctor":
            return doctor()
        elif args.command == "setup":
            return setup_user(args.user)
        else:
            parser.print_help()
    except PermissionError:
        print(f"Permission denied reading or creating {CONFIG_PATH}; try sudo.", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Notification failed: {exc}", file=sys.stderr)
        return 1
    return 0
