#!/usr/bin/env python3
"""Health Check - watches disk / battery / memory and alerts when they cross
thresholds (config.json -> health). Has a per-alert cooldown so it won't nag.
Runs inside the 30-minute auto cycle.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config, ROOT  # noqa: E402

try:
    import psutil
except ImportError:
    psutil = None

STATE = os.path.join(ROOT, "reports", ".health_state.json")


def _load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    try:
        json.dump(s, open(STATE, "w"))
    except Exception:
        pass


def check():
    """Returns (alerts, fresh_alerts) where fresh = not in cooldown."""
    if psutil is None:
        return [], []
    cfg = load_config()["health"]
    cooldown = cfg.get("notify_cooldown_min", 180) * 60
    alerts = []

    du = psutil.disk_usage("/")
    if du.percent >= cfg.get("disk_pct", 90):
        from common import human_size
        alerts.append(("disk", f"Disk almost full: {du.percent:.0f}% used, "
                               f"{human_size(du.free)} free"))
    vm = psutil.virtual_memory()
    if vm.percent >= cfg.get("mem_pct", 90):
        alerts.append(("mem", f"Memory pressure: {vm.percent:.0f}% used"))
    try:
        b = psutil.sensors_battery()
        if b and not b.power_plugged and b.percent <= cfg.get("battery_pct", 20):
            alerts.append(("battery", f"Battery low: {b.percent:.0f}% — plug in"))
    except Exception:
        pass

    state = _load()
    now = time.time()
    fresh = []
    for key, msg in alerts:
        if now - state.get(key, 0) >= cooldown:
            fresh.append((key, msg))
            state[key] = now
    # clear cooldowns for conditions that recovered
    for key in list(state.keys()):
        if key not in {k for k, _ in alerts}:
            state.pop(key, None)
    _save(state)
    return alerts, fresh


def run(quiet=False):
    if not quiet:
        header("Health Check", "[HEALTH]")
    alerts, fresh = check()
    if not alerts:
        if not quiet:
            print(f"  {C.GRN}All good — disk, memory and battery within limits.{C.R}")
        return []
    for _, msg in alerts:
        print(f"  {C.RED}! {msg}{C.R}")
    # fire notifications for fresh alerts
    if fresh:
        from daily_briefing import notify
        notify("Command Center — heads up", " · ".join(m for _, m in fresh))
    return [m for _, m in alerts]


if __name__ == "__main__":
    run()
