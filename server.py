#!/usr/bin/env python3
"""Command Center web dashboard - live agents, reports, and the daily log.

Run:  ./web   (or  python3 server.py)  then open http://127.0.0.1:8765
Local only: binds to 127.0.0.1. No data leaves your machine.
"""
import os
import sys
import time
import json
import shlex
import subprocess

from flask import Flask, Response, request, jsonify, send_from_directory

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import psutil  # noqa: E402
import world_news  # noqa: E402
from common import human_size  # noqa: E402

PY = sys.executable  # same interpreter that launched the server
PORT = 8765

app = Flask(__name__, static_folder=os.path.join(ROOT, "web"), static_url_path="")

# key -> (argv after python, supports_apply, needs_yes_on_apply)
AGENTS = {
    "system":       (["command_center.py", "system"], False, False),
    "weather":      (["tools/weather.py"], False, False),
    "news":         (["command_center.py", "news"], False, False),
    "health":       (["tools/health_check.py"], False, False),
    "briefing":     (["command_center.py", "briefing"], False, False),
    "disk":         (["tools/disk_analyzer.py"], False, False),
    "files":        (["tools/file_sorter.py"], True, False),
    "screenshots":  (["tools/screenshot_organizer.py"], True, False),
    "junk":         (["tools/junk_cleaner.py"], True, True),
    "gmail_triage": (["tools/gmail_sorter.py", "triage"], True, True),
    "gmail_search": (["tools/gmail_sorter.py", "search"], False, False),
    "report":       (["tools/report.py"], False, False),
    "auto":         (["command_center.py", "auto"], False, False),
}
REPORTS_DIR = os.path.join(ROOT, "reports")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/stats")
def stats():
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.3)
    up = int(time.time() - psutil.boot_time())
    bat = None
    try:
        b = psutil.sensors_battery()
        if b:
            bat = {"pct": round(b.percent), "plugged": b.power_plugged}
    except Exception:
        pass
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["name"], p.info["memory_info"].rss))
        except Exception:
            pass
    procs.sort(key=lambda x: x[1], reverse=True)
    return jsonify({
        "cpu": cpu,
        "cores": psutil.cpu_count(),
        "mem": {"pct": vm.percent, "used": human_size(vm.used), "total": human_size(vm.total)},
        "disk": {"pct": du.percent, "used": human_size(du.used), "total": human_size(du.total),
                 "free": human_size(du.free)},
        "battery": bat,
        "uptime": f"{up // 86400}d {(up % 86400) // 3600}h {(up % 3600) // 60}m",
        "load": [round(x, 2) for x in os.getloadavg()],
        "top": [{"name": n, "mem": human_size(r)} for n, r in procs[:6]],
    })


@app.route("/api/news")
def news():
    cfg = world_news.load_config()["world_news"]
    feeds = cfg["feeds"]
    limit = cfg.get("per_feed", 5)
    out = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        for name, titles, err in ex.map(
                lambda kv: world_news.fetch(kv[0], kv[1], limit), feeds.items()):
            out.append({"source": name, "headlines": titles, "error": err})
    return jsonify(out)


@app.route("/api/schedule")
def schedule():
    uid = os.getuid()
    label = "com.gagan.commandcenter.briefing"
    loaded = False
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
        loaded = label in res.stdout
    except Exception:
        pass
    from common import get_secret
    return jsonify({
        "loaded": loaded,
        "time": "every 30 min",
        "gmail_ready": os.path.exists(os.path.join(ROOT, "credentials.json")),
        "gmail_authed": os.path.exists(os.path.join(ROOT, "token.json")),
        "llm_drafts": bool(get_secret("ANTHROPIC_API_KEY")),
    })


@app.route("/api/reports")
def reports_list():
    items = []
    if os.path.isdir(REPORTS_DIR):
        for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if f.endswith(".html"):
                items.append(f)
    return jsonify(items)


@app.route("/reports/<path:name>")
def reports_file(name):
    return send_from_directory(REPORTS_DIR, name)


@app.route("/api/log")
def log():
    path = os.path.join(ROOT, "briefing.log")
    if not os.path.exists(path):
        return Response("No runs logged yet. The daily job writes here at 8 AM.",
                        mimetype="text/plain")
    with open(path, errors="replace") as f:
        lines = f.readlines()[-400:]
    return Response("".join(lines), mimetype="text/plain")


@app.route("/api/run/<key>")
def run_agent(key):
    if key not in AGENTS:
        return jsonify({"error": "unknown agent"}), 404
    argv, supports_apply, needs_yes = AGENTS[key]
    cmd = [PY] + argv
    if key == "gmail_search":
        q = request.args.get("q", "is:unread").strip() or "is:unread"
        cmd.append(q)
    apply = request.args.get("apply") == "1" and supports_apply
    if apply:
        cmd.append("--apply")
        if needs_yes:
            cmd.append("--yes")

    def stream():
        yield f"data: $ {' '.join(shlex.quote(c) for c in cmd[1:])}\n\n"
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        except Exception as e:
            yield f"data: [error launching: {e}]\n\nevent: done\ndata: 1\n\n"
            return
        for line in iter(proc.stdout.readline, ""):
            yield f"data: {line.rstrip(chr(10))}\n\n"
        proc.stdout.close()
        code = proc.wait()
        yield f"event: done\ndata: {code}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print(f"\n  Command Center dashboard -> http://127.0.0.1:{PORT}\n")
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False)
