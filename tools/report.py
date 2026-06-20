#!/usr/bin/env python3
"""Report - generates a self-contained HTML digest into reports/.

Writes reports/latest.html (always) and reports/report-YYYY-MM-DD.html (a daily
snapshot). Called automatically at the end of every 30-min auto run, so the
dashboard always has a fresh report. Old snapshots beyond keep_days are pruned.
"""
import os
import sys
import time
import html
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config, ROOT, human_size  # noqa: E402
import weather as weather_mod
import world_news
import health_check

try:
    import psutil
except ImportError:
    psutil = None


def _bar(pct):
    col = "#3fb950" if pct < 70 else "#d29922" if pct < 90 else "#f85149"
    return (f'<div class="bar"><i style="width:{min(pct,100):.0f}%;'
            f'background:{col}"></i></div>')


def _system():
    if psutil is None:
        return "<p class='muted'>psutil unavailable</p>"
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.3)
    up = int(time.time() - psutil.boot_time())
    rows = [("CPU", cpu, f"{cpu:.0f}%"),
            ("Memory", vm.percent, f"{human_size(vm.used)} / {human_size(vm.total)}"),
            ("Disk", du.percent, f"{human_size(du.free)} free of {human_size(du.total)}")]
    bat = ""
    try:
        b = psutil.sensors_battery()
        if b:
            bat = (f'<div class="kv"><span>Battery</span><b>{b.percent:.0f}% '
                   f'{"(charging)" if b.power_plugged else ""}</b></div>')
    except Exception:
        pass
    h = ""
    for name, pct, sub in rows:
        h += (f'<div class="metric"><div class="kv"><span>{name}</span>'
              f'<b>{sub}</b></div>{_bar(pct)}</div>')
    h += bat
    h += (f'<div class="kv muted"><span>Uptime</span>'
          f'<b>{up//86400}d {(up%86400)//3600}h {(up%3600)//60}m</b></div>')
    return h


def _weather():
    w = weather_mod.get_data()
    if w.get("error"):
        return f"<p class='muted'>Weather unavailable</p>"
    rain = f" · {w['rain']}% rain" if w.get("rain") is not None else ""
    return (f'<div class="wx"><div class="wxtemp">{w["temp"]}&deg;{w["deg"]}</div>'
            f'<div><div class="wxdesc">{html.escape(w["desc"])}</div>'
            f'<div class="muted">{html.escape(w["place"])}</div></div></div>'
            f'<div class="kv muted"><span>High {w["hi"]}&deg; / Low {w["lo"]}&deg;{rain}</span>'
            f'<b>feels {w["feels"]}&deg; · wind {w["wind"]}mph</b></div>')


def _health():
    alerts, _ = health_check.check()
    if not alerts:
        return '<p style="color:#3fb950">All systems within limits.</p>'
    return "".join(f'<div class="alert">! {html.escape(m)}</div>' for _, m in alerts)


def _auto(summary):
    if not summary:
        return "<p class='muted'>No auto-run data yet.</p>"
    items = [("Files sorted", summary.get("files", 0)),
             ("Screenshots filed", summary.get("shots", 0)),
             ("Emails sorted", summary.get("emails", 0)),
             ("To Spam", summary.get("spam", 0)),
             ("Reply drafts", summary.get("drafts", 0))]
    return "".join(f'<div class="kv"><span>{k}</span><b>{v}</b></div>' for k, v in items)


def _news(cache_min):
    feeds = world_news.get_data(cache_minutes=cache_min)
    out = ""
    for f in feeds:
        out += f'<div class="feed"><h4>{html.escape(f["source"])}</h4>'
        if f.get("error"):
            out += '<p class="muted">unavailable</p>'
        else:
            out += "<ul>" + "".join(
                f"<li>{html.escape(t)}</li>" for t in f["headlines"]) + "</ul>"
        out += "</div>"
    return out


PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Report {date}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#0d1117;
color:#e6edf3;margin:0;padding:24px;font-size:14px}}
h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8b949e;margin:0 0 20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}
.card{{background:#161b22;border:1px solid #2a3340;border-radius:12px;padding:16px}}
.card h3{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8b949e;margin:0 0 12px}}
.kv{{display:flex;justify-content:space-between;margin:6px 0}}
.bar{{height:7px;border-radius:5px;background:#0a0e14;overflow:hidden;margin:4px 0 10px}}
.bar>i{{display:block;height:100%}}
.muted{{color:#8b949e}} .alert{{color:#f85149;margin:5px 0}}
.wx{{display:flex;gap:14px;align-items:center;margin-bottom:8px}}
.wxtemp{{font-size:34px;font-weight:700;color:#39d0d8}} .wxdesc{{font-size:15px}}
.feed{{margin-bottom:14px}} .feed h4{{color:#39d0d8;margin:0 0 6px;font-size:13px}}
.feed ul{{margin:0;padding:0;list-style:none}} .feed li{{margin:4px 0;color:#c9d3dd;font-size:12.5px}}
.feed li:before{{content:"▸ ";color:#d29922}}
.news{{column-count:2;column-gap:18px}} @media(max-width:700px){{.news{{column-count:1}}}}
</style></head><body>
<h1>◆ Command Center Report</h1>
<p class="sub">{date}</p>
<div class="grid">
<div class="card"><h3>System</h3>{system}</div>
<div class="card"><h3>Weather</h3>{weather}</div>
<div class="card"><h3>Health</h3>{health}</div>
<div class="card"><h3>Last Auto Run</h3>{auto}</div>
</div>
<div class="card" style="margin-top:14px"><h3>World News</h3><div class="news">{news}</div></div>
</body></html>"""


def generate(auto_summary=None):
    cfg = load_config()
    rcfg = cfg.get("report", {})
    rdir = os.path.join(ROOT, rcfg.get("dir", "reports"))
    os.makedirs(rdir, exist_ok=True)
    page = PAGE.format(
        date=datetime.datetime.now().strftime("%A, %B %d %Y · %I:%M %p"),
        system=_system(), weather=_weather(), health=_health(),
        auto=_auto(auto_summary), news=_news(rcfg.get("news_cache_minutes", 180)))
    latest = os.path.join(rdir, "latest.html")
    dated = os.path.join(rdir, f"report-{datetime.date.today():%Y-%m-%d}.html")
    for p in (latest, dated):
        open(p, "w").write(page)
    _prune(rdir, rcfg.get("keep_days", 30))
    return latest


def _prune(rdir, keep_days):
    cutoff = time.time() - keep_days * 86400
    for f in os.listdir(rdir):
        if f.startswith("report-") and f.endswith(".html"):
            p = os.path.join(rdir, f)
            if os.path.getmtime(p) < cutoff:
                try:
                    os.remove(p)
                except OSError:
                    pass


def run():
    header("Generate Report", "[REPORT]")
    path = generate()
    print(f"  {C.GRN}Report written:{C.R} {path.replace(os.path.expanduser('~'),'~')}")
    print(f"  {C.GRY}View it in the dashboard's Reports tab.{C.R}")


if __name__ == "__main__":
    run()
