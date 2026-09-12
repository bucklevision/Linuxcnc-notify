import json
from collections.abc import Mapping


GROUPS = [
    ("Overview", {"ini_filename", "task_state", "task_mode", "state", "exec_state", "enabled", "estop", "paused", "task_paused", "inpos"}),
    ("Program and interpreter", {"file", "command", "current_line", "read_line", "motion_line", "interp_state", "interpreter_errcode", "call_level", "gcodes", "mcodes", "settings", "optional_stop", "block_delete"}),
    ("Motion", {"motion_mode", "motion_type", "current_vel", "velocity", "distance_to_go", "dtg", "delay_left", "queue", "active_queue", "queue_full", "max_velocity", "max_acceleration", "feedrate", "rapidrate"}),
    ("Positions and offsets", {"position", "actual_position", "joint_position", "joint_actual_position", "g5x_index", "g5x_offset", "g92_offset", "tool_offset", "rotation_xy", "probed_position"}),
    ("Axes and joints", {"axes", "axis", "axis_mask", "joints", "joint", "homed", "limit", "kinematics_type"}),
    ("Spindle and coolant", {"spindles", "spindle", "mist", "flood", "brake"}),
    ("Tooling", {"tool_in_spindle", "tool_from_pocket", "pocket_prepped", "tool_table"}),
    ("Inputs and outputs", {"ain", "aout", "din", "dout", "lube", "lube_level", "probe_tripped", "probe_val", "probing", "input_timeout"}),
    ("Overrides and units", {"adaptive_feed_enabled", "feed_hold_enabled", "feed_override_enabled", "spindle_override_enabled", "program_units", "linear_units", "angular_units"}),
]


def json_value(value, depth=0):
    if depth > 5:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_value(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item, depth + 1) for item in value]
    try:
        return {name: json_value(getattr(value, name), depth + 1)
                for name in dir(value) if not name.startswith("_") and not callable(getattr(value, name))}
    except Exception:
        return repr(value)


def collect_variables(status):
    values = {}
    for name in dir(status):
        if name.startswith("_") or name == "poll":
            continue
        try:
            value = getattr(status, name)
            if callable(value):
                continue
            values[name] = json_value(value)
        except Exception as exc:
            values[name] = {"error": str(exc)}

    grouped = {}
    assigned = set()
    for title, names in GROUPS:
        selected = {name: values[name] for name in sorted(names) if name in values}
        if selected:
            grouped[title] = selected
            assigned.update(selected)
    remaining = {name: values[name] for name in sorted(values) if name not in assigned}
    if remaining:
        grouped["Other"] = remaining
    return grouped


DASHBOARD_HTML = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LinuxCNC Notify</title><style>
:root{color-scheme:light dark}body{font:15px system-ui;margin:0;background:#17191c;color:#e8e8e8}
header{position:sticky;top:0;background:#20242a;padding:14px 20px;border-bottom:1px solid #444;z-index:2}
h1{font-size:21px;margin:0 0 5px}.summary{display:flex;gap:18px;flex-wrap:wrap}.ok{color:#69db7c}.bad{color:#ff8787}
main{padding:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
section{background:#20242a;border:1px solid #3b4048;border-radius:8px;overflow:hidden}h2{font-size:16px;margin:0;padding:10px 12px;background:#292e35}
table{border-collapse:collapse;width:100%}td{padding:6px 10px;border-top:1px solid #343941;vertical-align:top}td:first-child{width:38%;color:#9ec5fe;font-family:monospace}
pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:12px ui-monospace,monospace}.muted{color:#aaa}
</style></head><body><header><h1>LinuxCNC Notify</h1><div class="summary" id="summary">Loading…</div></header><main id="groups"></main>
<script>
function value(v){if(v===null)return 'null';if(typeof v==='object')return JSON.stringify(v,null,2);return String(v)}
function draw(data){
 const s=document.getElementById('summary');s.replaceChildren();
 const items=[['Connection',data.connected?'Connected':'Disconnected'],['State',data.state||'unknown'],[data.program_label||'Program',data.program||'—'],['Line',data.line??'—'],['Updated',new Date((data.updated||0)*1000).toLocaleTimeString()]];
 for(const [k,v] of items){const span=document.createElement('span');span.textContent=k+': '+v;if(k==='Connection')span.className=data.connected?'ok':'bad';s.append(span)}
 const root=document.getElementById('groups');root.replaceChildren();
 for(const [title,vars] of Object.entries(data.variables||{})){const sec=document.createElement('section'),h=document.createElement('h2'),table=document.createElement('table');h.textContent=title;sec.append(h,table);
  for(const [name,val] of Object.entries(vars)){const tr=document.createElement('tr'),a=document.createElement('td'),b=document.createElement('td'),pre=document.createElement('pre');a.textContent=name;pre.textContent=value(val);b.append(pre);tr.append(a,b);table.append(tr)}root.append(sec)}
}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});draw(await r.json())}catch(e){document.getElementById('summary').textContent='Status request failed: '+e}}
refresh();setInterval(refresh,3000);
</script></body></html>"""
