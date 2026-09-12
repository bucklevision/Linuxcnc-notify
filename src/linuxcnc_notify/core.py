import json
import os
import secrets
import socket
import threading
import time
import traceback
import urllib.error
import urllib.request
import urllib.parse
from configparser import ConfigParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .dashboard import DASHBOARD_HTML, collect_variables

CONFIG_PATH = Path(os.environ.get("LINUXCNC_NOTIFY_CONFIG", "/etc/linuxcnc-notify/config.json"))
STATE_PATH = Path(os.environ.get("LINUXCNC_NOTIFY_STATE", "/var/lib/linuxcnc-notify/state.json"))
NOTIFY_CONFIG_PATH = Path(os.environ.get("LINUXCNC_NOTIFY_EVENTS", "/etc/linuxcnc-notify/notify.conf"))


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


def load_notification_config(path=NOTIFY_CONFIG_PATH):
    parser = ConfigParser()
    parser.read(str(path))
    if not parser.has_section("notifications"):
        return {}
    return {key: value.strip().lower() for key, value in parser.items("notifications")}


def event_enabled(settings, event, program_active=False):
    value = settings.get(event, "no")
    return value in ("yes", "true", "1", "on") or (value == "running" and program_active)


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
        headers={"Content-Type": "application/json", "User-Agent": "linuxcnc-notify/0.2.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def subscription_deep_link(config):
    """Return the ntfy app's documented custom-scheme subscription link."""
    server = urllib.parse.urlparse(config["server"])
    if server.scheme not in ("http", "https") or not server.netloc:
        raise ValueError("ntfy server must be an http or https URL")
    query = {"display": f"{config['machine_name']} LinuxCNC"}
    if server.scheme == "http":
        query["secure"] = "false"
    topic = urllib.parse.quote(config["topic"], safe="")
    return f"ntfy://{server.netloc}/{topic}?{urllib.parse.urlencode(query)}"


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
            elif self.path == "/":
                body = DASHBOARD_HTML.encode()
                content_type = "text/html; charset=utf-8"
            elif self.path == "/pair":
                state = shared.snapshot()
                subscription = subscription_deep_link(config)
                body = ("<!doctype html><meta name='viewport' content='width=device-width'>"
                        "<title>LinuxCNC Notify</title><style>body{font:18px system-ui;max-width:46rem;"
                        "margin:3rem auto;padding:1rem}code{overflow-wrap:anywhere}</style>"
                        f"<h1>LinuxCNC Notify</h1><p>Status: <strong>{state.get('state')}</strong></p>"
                        f"<p>Machine: {config['machine_name']}</p><h2>Phone pairing</h2>"
                        "<p>Install ntfy, add a subscription using this server and topic:</p>"
                        f"<p>Server: <code>{config['server']}</code><br>Topic: "
                        f"<code>{config['topic']}</code></p><p><a href='{subscription}'>Open in ntfy app</a></p>").encode()
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
    all_joints = getattr(status, "joint", ())
    configured = int(getattr(status, "joints", len(all_joints)))
    for index, joint in enumerate(all_joints[:configured]):
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


def fault_groups(status):
    groups = {"joint_fault": set(), "hard_limit": set(), "soft_limit": set()}
    all_joints = getattr(status, "joint", ())
    configured = int(getattr(status, "joints", len(all_joints)))
    for index, joint in enumerate(all_joints[:configured]):
        if joint.get("fault"):
            groups["joint_fault"].add(f"joint {index} drive fault")
        for side, label in (("min", "minimum"), ("max", "maximum")):
            if joint.get(f"{side}_hard_limit"):
                groups["hard_limit"].add(f"joint {index} {label} hard limit")
            if joint.get(f"{side}_soft_limit"):
                groups["soft_limit"].add(f"joint {index} {label} soft limit")
    return groups


def program_details(filename, line, prefix="Line"):
    return f"{filename}\n{prefix}: {line}"


def daemon():
    config = ensure_config()
    settings = load_notification_config()
    shared = SharedStatus()
    start_web(shared, config)
    previous_active = previous_paused = previous_error = False
    previous_homing = False
    previous_task_state = None
    previous_groups = {name: set() for name in ("joint_fault", "hard_limit", "soft_limit")}
    previous_tool = previous_spindle = previous_flood = previous_mist = None
    connected = False
    last_program, last_line, last_variables = "No program", 0, 0
    status = linuxcnc = None
    operation = "starting"

    def send(event, title, message, priority=3, tags=None, running=False):
        if not event_enabled(settings, event, running):
            return
        try:
            publish(config, title, message, priority, tags)
        except Exception:
            traceback.print_exc()

    while True:
        try:
            operation = "loading LinuxCNC Python module"
            if linuxcnc is None:
                import linuxcnc as module
                linuxcnc = module
            operation = "opening LinuxCNC status channel"
            if status is None:
                status = linuxcnc.stat()
            operation = "polling LinuxCNC status"
            status.poll()
            operation = "reading LinuxCNC status"
            is_active = active(status, linuxcnc)
            is_paused = status.interp_state == getattr(linuxcnc, "INTERP_PAUSED", -1)
            filename = os.path.basename(status.file) if getattr(status, "file", "") else "No program"
            line = int(getattr(status, "current_line", 0))
            groups = fault_groups(status)
            current_faults = set().union(*groups.values())
            state_error = getattr(status, "state", None) == getattr(linuxcnc, "RCS_ERROR", object())
            exec_error = getattr(status, "exec_state", None) == getattr(linuxcnc, "EXEC_ERROR", object())
            current_error = bool(state_error or exec_error or int(getattr(status, "interpreter_errcode", 0) or 0))
            configured = list(getattr(status, "joint", ()))[:int(getattr(status, "joints", 0))]
            is_homing = any(bool(joint.get("homing")) for joint in configured)
            all_homed = bool(configured) and all(bool(joint.get("homed")) for joint in configured)
            tool = int(getattr(status, "tool_in_spindle", 0) or 0)
            spindle = any(bool(item.get("enabled")) for item in getattr(status, "spindle", ()))
            flood, mist = bool(getattr(status, "flood", False)), bool(getattr(status, "mist", False))
            if is_active:
                last_program, last_line = filename, line

            now = time.time()
            update = dict(connected=True, state="paused" if is_paused else "running" if is_active else "idle",
                          program=filename, program_label="Running program" if is_active else "Loaded program",
                          line=line, faults=sorted(current_faults), updated=now)
            if now - last_variables >= 3:
                operation = "collecting dashboard variables"
                update["variables"] = collect_variables(status)
                last_variables = now
            shared.update(**update)

            if not connected:
                send("linuxcnc_connected", "LinuxCNC connected", config["machine_name"])
            if is_active and not previous_active:
                send("program_started", "LinuxCNC program started", program_details(filename, line), tags=["arrow_forward"], running=True)
            if is_paused and not previous_paused:
                send("program_paused", "LinuxCNC program paused", program_details(filename, line), tags=["pause_button"], running=True)
            if previous_paused and is_active and not is_paused:
                send("program_resumed", "LinuxCNC program resumed", program_details(filename, line), tags=["arrow_forward"], running=True)

            for event, current in groups.items():
                new_items = current - previous_groups[event]
                if new_items:
                    message = ", ".join(sorted(new_items))
                    if is_active:
                        message = program_details(filename, line) + "\n" + message
                    send(event, "LinuxCNC fault", message, 5, ["rotating_light"], is_active)
            if current_error and not previous_error:
                message = "LinuxCNC reported an execution/interpreter error"
                if is_active:
                    message = program_details(filename, line) + "\n" + message
                send("interpreter_error", "LinuxCNC interpreter error", message, 5, ["rotating_light"], is_active)
            if previous_active and not is_active:
                reason = "Stopped after a fault" if current_faults or current_error else "Program stopped"
                send("program_stopped", f"LinuxCNC: {reason}", program_details(last_program, last_line, "Last reported line"), 4, ["stop_sign"], True)

            if previous_task_state is not None and status.task_state != previous_task_state:
                states = {
                    getattr(linuxcnc, "STATE_ON", object()): ("machine_on", "LinuxCNC machine power on"),
                    getattr(linuxcnc, "STATE_OFF", object()): ("machine_off", "LinuxCNC machine power off"),
                    getattr(linuxcnc, "STATE_ESTOP", object()): ("estop_engaged", "LinuxCNC E-stop engaged"),
                    getattr(linuxcnc, "STATE_ESTOP_RESET", object()): ("estop_reset", "LinuxCNC E-stop reset"),
                }
                if status.task_state in states:
                    event, title = states[status.task_state]
                    send(event, title, config["machine_name"], 5 if event == "estop_engaged" else 3,
                         ["warning"] if event == "estop_engaged" else None, is_active)
            if is_homing and not previous_homing:
                send("homing_started", "LinuxCNC homing started", config["machine_name"], running=is_active)
            if previous_homing and not is_homing and all_homed:
                send("homing_completed", "LinuxCNC homing completed", config["machine_name"], running=is_active)
            if previous_tool is not None and tool != previous_tool:
                send("tool_changed", "LinuxCNC tool changed", f"Tool in spindle: {tool}", running=is_active)
            if previous_spindle is not None and spindle != previous_spindle:
                send("spindle_started" if spindle else "spindle_stopped", f"LinuxCNC spindle {'started' if spindle else 'stopped'}", config["machine_name"], running=is_active)
            if previous_flood is not None and flood != previous_flood:
                send("flood_changed", "LinuxCNC flood coolant changed", f"Flood coolant: {'on' if flood else 'off'}", running=is_active)
            if previous_mist is not None and mist != previous_mist:
                send("mist_changed", "LinuxCNC mist coolant changed", f"Mist coolant: {'on' if mist else 'off'}", running=is_active)

            previous_active, previous_paused, previous_error = is_active, is_paused, current_error
            previous_task_state, previous_groups = status.task_state, groups
            previous_homing = is_homing
            previous_tool, previous_spindle = tool, spindle
            previous_flood, previous_mist = flood, mist
            connected = True
        except Exception as exc:
            traceback.print_exc()
            status = None
            shared.update(connected=False, state="waiting for LinuxCNC", detail=f"{operation}: {exc}", updated=time.time())
            if connected:
                send("linuxcnc_disconnected", "LinuxCNC connection lost", "LinuxCNC status connection was lost", 5, ["warning"], previous_active)
            connected = False
            previous_active = False
            time.sleep(4)
            continue
        time.sleep(1)
