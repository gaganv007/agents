#!/usr/bin/env python3
"""Daily Auto - the unattended routine run by launchd every morning.

Runs every safe agent automatically. Junk/Cache Cleaner is intentionally NOT
here: it deletes data and stays manual. Gmail drafts are created but never sent.
Each step is isolated so one failure never stops the rest.
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header  # noqa: E402
import system_analysis
import world_news
import file_sorter
import screenshot_organizer
import gmail_sorter
from daily_briefing import notify


def step(label, fn):
    try:
        fn()
    except Exception as e:
        header(label, "[SKIP]")
        print(f"  {C.GRY}skipped: {e}{C.R}")


def run():
    now = datetime.datetime.now()
    print(f"\n{C.B}{C.MAG}  DAILY AUTO RUN{C.R}  "
          f"{C.GRY}{now.strftime('%A, %B %d, %Y - %I:%M %p')}{C.R}")

    # Read-only reports
    step("System Analysis", lambda: system_analysis.run(top=5))
    step("World News", lambda: world_news.run())

    # Auto-apply (file moves are reversible; you asked to automate these)
    step("File Sorter", lambda: file_sorter.run(apply=True))
    step("Screenshot Organizer", lambda: screenshot_organizer.run(apply=True))

    # Gmail: sort labels/archive, then create review-ready drafts (never sent)
    step("Gmail Sort", lambda: gmail_sorter.sort(apply=True, assume_yes=True))
    step("Gmail Draft", lambda: gmail_sorter.draft(apply=True, assume_yes=True))

    print(f"\n{C.GRN}  Daily auto run complete.{C.R}\n")
    notify("Command Center", "Daily run done: files sorted, inbox tidied, drafts ready.")


if __name__ == "__main__":
    run()
