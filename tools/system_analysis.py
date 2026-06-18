#!/usr/bin/env python3
"""System Analysis - snapshot of CPU, memory, disk, battery and top processes."""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, human_size  # noqa: E402

try:
    import psutil
except ImportError:
    psutil = None


def bar(pct, width=30):
    filled = int(width * pct / 100)
    color = C.GRN if pct < 70 else (C.YEL if pct < 90 else C.RED)
    return f"{color}{'#' * filled}{C.GRY}{'.' * (width - filled)}{C.R} {pct:5.1f}%"


def run(top=8):
    header("System Analysis", "[SYS]")
    if psutil is None:
        print(f"{C.RED}psutil not installed. Run: pip install psutil{C.R}")
        return

    # Uptime
    boot = psutil.boot_time()
    up = time.time() - boot
    d, rem = divmod(int(up), 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    print(f"  {C.B}Uptime{C.R}      {d}d {h}h {m}m")

    # CPU
    cpu = psutil.cpu_percent(interval=0.6)
    cores = psutil.cpu_count(logical=True)
    load = os.getloadavg()
    print(f"  {C.B}CPU{C.R} ({cores} cores) {bar(cpu)}")
    print(f"  {C.B}Load{C.R}        {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}  (1/5/15 min)")

    # Memory
    vm = psutil.virtual_memory()
    print(f"  {C.B}Memory{C.R}      {bar(vm.percent)}  "
          f"{C.GRY}{human_size(vm.used)} / {human_size(vm.total)}{C.R}")
    sw = psutil.swap_memory()
    if sw.total:
        print(f"  {C.B}Swap{C.R}        {bar(sw.percent)}  "
              f"{C.GRY}{human_size(sw.used)} / {human_size(sw.total)}{C.R}")

    # Disk
    du = psutil.disk_usage("/")
    print(f"  {C.B}Disk (/){C.R}    {bar(du.percent)}  "
          f"{C.GRY}{human_size(du.used)} / {human_size(du.total)} "
          f"({human_size(du.free)} free){C.R}")

    # Battery
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            plug = "charging" if bat.power_plugged else "on battery"
            secs = bat.secsleft
            eta = ""
            if secs and secs > 0 and not bat.power_plugged:
                eta = f"  (~{secs // 3600}h {(secs % 3600) // 60}m left)"
            print(f"  {C.B}Battery{C.R}     {bar(bat.percent)}  {C.GRY}{plug}{eta}{C.R}")
    except Exception:
        pass

    # Network totals
    net = psutil.net_io_counters()
    print(f"  {C.B}Network{C.R}     sent {human_size(net.bytes_sent)}, "
          f"recv {human_size(net.bytes_recv)} (since boot)")

    # Top processes by memory
    procs = []
    for p in psutil.process_iter(["name", "memory_info", "cpu_percent"]):
        try:
            procs.append((p.info["name"], p.info["memory_info"].rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass
    procs.sort(key=lambda x: x[1], reverse=True)
    print(f"\n  {C.B}Top {top} processes by memory:{C.R}")
    for name, rss in procs[:top]:
        print(f"      {C.MAG}{human_size(rss):>9}{C.R}  {name}")

    # Health verdict
    flags = []
    if cpu > 85:
        flags.append("high CPU")
    if vm.percent > 88:
        flags.append("memory pressure")
    if du.percent > 90:
        flags.append("disk nearly full")
    print()
    if flags:
        print(f"  {C.RED}Attention: {', '.join(flags)}.{C.R}")
    else:
        print(f"  {C.GRN}System looks healthy.{C.R}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=8)
    run(p.parse_args().top)
