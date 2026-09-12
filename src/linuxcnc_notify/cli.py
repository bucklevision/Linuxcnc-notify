import argparse
import json
import shutil
import subprocess
import sys
import urllib.error

from . import __version__
from .core import CONFIG_PATH, daemon, ensure_config, load_config, publish


def pair(config):
    print("LinuxCNC Notify phone pairing")
    print(f"Server: {config['server']}")
    print(f"Topic:  {config['topic']}")
    print(f"Web:    http://localhost:{config['web_port']}/pair")
    if shutil.which("qrencode"):
        print("\nScan this code to open the topic:\n")
        subprocess.run(["qrencode", "-t", "ANSIUTF8", config["server"].rstrip("/") + "/" + config["topic"]], check=False)
    print("\nInstall the ntfy phone app, then subscribe using the server and topic above.")


def main():
    parser = argparse.ArgumentParser(prog="linuxcnc-notify")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("daemon")
    sub.add_parser("pair")
    sub.add_parser("show-config")
    sub.add_parser("test")
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
        else:
            parser.print_help()
    except PermissionError:
        print(f"Permission denied reading or creating {CONFIG_PATH}; try sudo.", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Notification failed: {exc}", file=sys.stderr)
        return 1
    return 0
