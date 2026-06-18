#!/usr/bin/env python3
"""Auto routine - runs every 30 minutes via launchd.

Keeps things tidy and triages new Gmail with AI. It only notifies you when it
actually did something, so a quiet inbox stays quiet. The Junk/Cache Cleaner is
deliberately NOT here (it deletes data) - run it by hand with ./cc junk.
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header  # noqa: E402
import file_sorter
import screenshot_organizer
import gmail_sorter
from daily_briefing import notify


def step(label, fn, default=None):
    try:
        return fn()
    except Exception as e:
        header(label, "[SKIP]")
        print(f"  {C.GRY}skipped: {e}{C.R}")
        return default


def run():
    now = datetime.datetime.now()
    print(f"\n{C.B}{C.MAG}  AUTO RUN{C.R}  "
          f"{C.GRY}{now.strftime('%a %Y-%m-%d %I:%M %p')}{C.R}")

    files = step("File Sorter", lambda: file_sorter.run(apply=True), 0) or 0
    shots = step("Screenshot Organizer", lambda: screenshot_organizer.run(apply=True), 0) or 0
    gmail = step("Gmail AI triage",
                 lambda: gmail_sorter.triage(apply=True, assume_yes=True), {}) or {}

    sorted_n = gmail.get("sorted", 0)
    spam_n = gmail.get("spam", 0)
    drafts = gmail.get("drafts", 0)

    bits = []
    if files:
        bits.append(f"{files} files sorted")
    if shots:
        bits.append(f"{shots} screenshots filed")
    if sorted_n or spam_n:
        bits.append(f"{sorted_n + spam_n} emails sorted")
    if drafts:
        bits.append(f"{drafts} reply drafts ready")

    print(f"\n{C.GRN}  Auto run complete.{C.R} "
          f"{C.GRY}{', '.join(bits) if bits else 'nothing to do'}{C.R}\n")

    # Only ping you when something happened.
    if bits:
        notify("Command Center", "; ".join(bits))


if __name__ == "__main__":
    run()
