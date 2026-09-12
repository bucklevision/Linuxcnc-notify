import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import urllib.error

from . import __version__
from .core import CONFIG_PATH, daemon, ensure_config, load_config, publish, subscription_deep_link


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


def main():
    parser = argparse.ArgumentParser(prog="linuxcnc-notify")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("daemon")
    sub.add_parser("pair")
    sub.add_parser("show-config")
    sub.add_parser("test")
    sub.add_parser("doctor")
    args = parser.parse_args()
    try:
        config = ensure_config()
        if args.command == "daemon":
            daemon()
        elif args.command == "pair":
            pair(config)
        elif args.command == "show-config":
            print(json.dumps(config, indent=2))
        elif args.command == "test":
            publish(config, "LinuxCNC Notify test", f"Notifications are configured for {config['machine_name']}", tags=["white_check_mark"])
            print("Test notification sent.")
        elif args.command == "doctor":
            return doctor()
        else:
            parser.print_help()
    except PermissionError:
        print(f"Permission denied reading or creating {CONFIG_PATH}; try sudo.", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Notification failed: {exc}", file=sys.stderr)
        return 1
    return 0
