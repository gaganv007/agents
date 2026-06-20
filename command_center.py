#!/usr/bin/env python3
"""
COMMAND CENTER - one launcher for all your local agents.

Usage:
    python3 command_center.py            # interactive menu
    python3 command_center.py news       # run one agent directly by key
    python3 command_center.py briefing
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
from common import C, confirm  # noqa: E402

import system_analysis
import world_news
import weather
import file_sorter
import junk_cleaner
import screenshot_organizer
import disk_analyzer
import gmail_sorter
import health_check
import report
import daily_briefing
import daily_auto


# key: (label, description, callable, supports_apply)
AGENTS = {
    "briefing":   ("Daily Briefing",      "System + news + files, all at once",      daily_briefing.run, False),
    "system":     ("System Analysis",     "CPU, memory, disk, battery, top procs",   system_analysis.run, False),
    "weather":    ("Weather",             "Current conditions for your location",    weather.run,         False),
    "news":       ("World News",          "Top headlines from global sources",       world_news.run,      False),
    "health":     ("Health Check",        "Alert on low disk / battery / memory",    health_check.run,    False),
    "files":      ("File Sorter",         "Organize Downloads by file type",         file_sorter.run,     True),
    "screenshots":("Screenshot Organizer","Tidy screenshots into dated folders",     screenshot_organizer.run, True),
    "junk":       ("Junk / Cache Cleaner","Reclaim disk from caches & dev junk",      junk_cleaner.run,    True),
    "disk":       ("Disk Analyzer",       "Find your biggest files and folders",     disk_analyzer.run,   False),
    "gmail":      ("Gmail AI Agent",      "AI triage / search / draft (OAuth)",      gmail_sorter.interactive, "gmail"),
    "report":     ("Generate Report",     "Write an HTML digest to reports/",        report.run,          False),
    "auto":       ("Auto Run (30 min)",   "Everything safe, unattended (no cleaner)",daily_auto.run,      False),
}
ORDER = ["briefing", "system", "weather", "news", "health", "files",
         "screenshots", "junk", "disk", "gmail", "report"]


def banner():
    print(f"""{C.CYN}{C.B}
  +==========================================================+
  |                                                          |
  |            G A G A N ' S   C O M M A N D   C E N T E R    |
  |              local agents - no cloud, no keys*           |
  |                                                          |
  +==========================================================+{C.R}
  {C.GRY}* except Gmail, which uses your own Google OAuth credentials{C.R}""")


def run_agent(key):
    label, _, fn, mode = AGENTS[key]
    try:
        if mode == "gmail":
            fn()  # gmail_sorter.interactive() runs its own submenu
        elif mode is True:
            fn(apply=False)  # always preview first
            if confirm(f"\nApply changes for '{label}' now?"):
                fn(apply=True)
        else:
            fn()
    except KeyboardInterrupt:
        print(f"\n{C.GRY}(interrupted){C.R}")
    except Exception as e:
        print(f"\n{C.RED}{label} hit an error: {e}{C.R}")


def menu():
    banner()
    while True:
        print(f"\n  {C.B}Pick an agent:{C.R}")
        for i, key in enumerate(ORDER, 1):
            label, desc, _, mode = AGENTS[key]
            tag = f" {C.YEL}(asks first){C.R}" if mode is True else ""
            print(f"    {C.GRN}{i}{C.R}. {C.B}{label:<22}{C.R} {C.GRY}{desc}{C.R}{tag}")
        print(f"    {C.GRN}a{C.R}. {C.B}Run ALL read-only agents{C.R} {C.GRY}(briefing){C.R}")
        print(f"    {C.GRN}q{C.R}. Quit")

        try:
            choice = input(f"\n  {C.CYN}> {C.R}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if choice in ("q", "quit", "exit"):
            print(f"  {C.GRY}Bye!{C.R}")
            break
        if choice == "a":
            run_agent("briefing")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(ORDER):
            run_agent(ORDER[int(choice) - 1])
        elif choice in AGENTS:
            run_agent(choice)
        else:
            print(f"  {C.RED}Unknown choice.{C.R}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        key = sys.argv[1].lower()
        if key in AGENTS:
            run_agent(key)
        else:
            print(f"Unknown agent '{key}'. Options: {', '.join(ORDER)}")
            sys.exit(1)
    else:
        menu()
