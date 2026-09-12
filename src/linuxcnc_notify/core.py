import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("LINUXCNC_NOTIFY_CONFIG", "/etc/linuxcnc-notify/config.json"))
STATE_PATH = Path(os.environ.get("LINUXCNC_NOTIFY_STATE", "/var/lib/linuxcnc-notify/state.json"))


def default_config():
    return {
        "server": "https://ntfy.sh",
        "topic": "linuxcnc-" + secrets.token_hex(24),
        "machine_name": socket.gethostname(),
        "notify_start": False,
        "notify_pause": True,
        "notify_stop": True,
        "notify_fault": True,
        "web_listen": "127.0.0.1",
        "web_port": 8765,
    }


def ensure_config(path=CONFIG_PATH):
    if path.exists():
        return load_config(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    config = default_config()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    return config


def load_config(path=CONFIG_PATH):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def publish(config, title, message, priority=3, tags=None):
    payload = {
        "topic": config["topic"],
        "title": title,
        "message": message,
        "priority": priority,
    }
    if tags:
        payload["tags"] = tags
    request = urllib.request.Request(
        config["server"].rstrip("/"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "linuxcnc-notify/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


class SharedStatus:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {"connected": False, "state": "waiting", "machine": socket.gethostname()}

    def update(self, **values):
        with self.lock:
            self.data.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.data)


def web_handler(shared, config):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/status":
                body = json.dumps(shared.snapshot()).encode()
                content_type = "application/json"
            elif self.path in ("/", "/pair"):
                state = shared.snapshot()
                subscription = config["server"].rstrip("/") + "/" + config["topic"]
                body = ("<!doctype html><meta name='viewport' content='width=device-width'>"
                        "<title>LinuxCNC Notify</title><style>body{font:18px system-ui;max-width:46rem;"
                        "margin:3rem auto;padding:1rem}code{overflow-wrap:anywhere}</style>"
                        f"<h1>LinuxCNC Notify</h1><p>Status: <strong>{state.get('state')}</strong></p>"
                        f"<p>Machine: {config['machine_name']}</p><h2>Phone pairing</h2>"
                        "<p>Install ntfy, add a subscription using this server and topic:</p>"
                        f"<p>Server: <code>{config['server']}</code><br>Topic: "
                        f"<code>{config['topic']}</code></p><p><a href='{subscription}'>Open topic</a></p>").encode()
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return
    return Handler


def start_web(shared, config):
    server = ThreadingHTTPServer((config["web_listen"], int(config["web_port"])), web_handler(shared, config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def active(status, linuxcnc):
    return status.interp_state in tuple(
        value for value in (
            getattr(linuxcnc, "INTERP_READING", None),
            getattr(linuxcnc, "INTERP_WAITING", None),
            getattr(linuxcnc, "INTERP_PAUSED", None),
        ) if value is not None
    )


def faults(status):
    found = []
    for index, joint in enumerate(getattr(status, "joint", ())):
        if joint.get("fault"):
            found.append(f"joint {index} drive fault")
        if joint.get("min_hard_limit"):
            found.append(f"joint {index} minimum hard limit")
        if joint.get("max_hard_limit"):
            found.append(f"joint {index} maximum hard limit")
        if joint.get("min_soft_limit"):
            found.append(f"joint {index} minimum soft limit")
        if joint.get("max_soft_limit"):
            found.append(f"joint {index} maximum soft limit")
    return found


def daemon():
    config = ensure_config()
    shared = SharedStatus()
    start_web(shared, config)
    previous_active = False
    previous_paused = False
    previous_task_state = None
    previous_faults = set()
    previous_error = False
    was_connected = False
    status = None
    linuxcnc = None

    while True:
        try:
            if linuxcnc is None:
                import linuxcnc as module
                linuxcnc = module
            if status is None:
                status = linuxcnc.stat()
            status.poll()
            is_active = active(status, linuxcnc)
            is_paused = status.interp_state == getattr(linuxcnc, "INTERP_PAUSED", -1)
            filename = os.path.basename(status.file) if getattr(status, "file", "") else "No program"
            line = int(getattr(status, "current_line", 0))
            current_faults = set(faults(status))
            state_error = getattr(status, "state", None) == getattr(linuxcnc, "RCS_ERROR", object())
            exec_error = getattr(status, "exec_state", None) == getattr(linuxcnc, "EXEC_ERROR", object())
            interp_code = int(getattr(status, "interpreter_errcode", 0) or 0)
            current_error = bool(state_error or exec_error or interp_code)

            shared.update(connected=True, state="paused" if is_paused else "running" if is_active else "idle",
                          program=filename, line=line, faults=sorted(current_faults), updated=time.time())

            if is_active and not previous_active and config.get("notify_start"):
                publish(config, "LinuxCNC program started", f"{filename}\nLine: {line}", tags=["arrow_forward"])
            if is_paused and not previous_paused and config.get("notify_pause"):
                publish(config, "LinuxCNC program paused", f"{filename}\nLine: {line}", tags=["pause_button"])

            new_faults = current_faults - previous_faults
            if (new_faults or (current_error and not previous_error)) and config.get("notify_fault"):
                details = ", ".join(sorted(new_faults)) or "LinuxCNC reported an execution/interpreter error"
                publish(config, "LinuxCNC fault", f"{filename}\nLine: {line}\n{details}", 5, ["rotating_light"])

            if previous_active and not is_active and config.get("notify_stop"):
                reason = "Stopped after a fault" if current_faults or current_error else "Program stopped"
                publish(config, f"LinuxCNC: {reason}", f"{filename}\nLast reported line: {line}", 4, ["stop_sign"])

            if previous_task_state is not None and status.task_state != previous_task_state:
                if status.task_state in (getattr(linuxcnc, "STATE_ESTOP", -2), getattr(linuxcnc, "STATE_OFF", -3)):
                    publish(config, "LinuxCNC machine disabled", f"{filename}\nLine: {line}", 5, ["warning"])

            previous_active, previous_paused = is_active, is_paused
            previous_task_state, previous_faults = status.task_state, current_faults
            previous_error = current_error
            was_connected = True
        except Exception as exc:
            status = None
            shared.update(connected=False, state="waiting for LinuxCNC", detail=str(exc), updated=time.time())
            if previous_active and was_connected:
                try:
                    publish(config, "LinuxCNC connection lost", "LinuxCNC disappeared while a program was active", 5, ["warning"])
                except Exception:
                    pass
                previous_active = False
            time.sleep(4)
            continue
        time.sleep(1)
