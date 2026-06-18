#!/usr/bin/env python3
"""Daily Briefing - one-shot morning summary that runs the read-only agents."""
import os
import sys
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config  # noqa: E402
import system_analysis
import world_news
import file_sorter


def notify(title, message):
    """Best-effort macOS notification; silently ignored if unavailable."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}" '
             f'subtitle "Daily briefing ready" sound name "Glass"'],
            check=False, capture_output=True, timeout=10,
        )
    except Exception:
        pass


def run():
    now = datetime.datetime.now()
    print(f"\n{C.B}{C.MAG}  GOOD {'MORNING' if now.hour < 12 else 'AFTERNOON' if now.hour < 18 else 'EVENING'}, "
          f"GAGAN{C.R}")
    print(f"  {C.GRY}{now.strftime('%A, %B %d, %Y  -  %I:%M %p')}{C.R}")

    # System health (compact)
    system_analysis.run(top=5)

    # Files needing attention
    header("Inbox of Files", "[FILES]")
    try:
        cfg = load_config()
        dl = os.path.expanduser(cfg["paths"]["downloads"])
        moves = file_sorter.plan(dl, cfg)
        n = sum(len(v) for v in moves.values())
        if n:
            print(f"  {C.YEL}{n} files in Downloads need sorting{C.R} "
                  f"{C.GRY}(run File Sorter to tidy){C.R}")
        else:
            print(f"  {C.GRN}Downloads is tidy.{C.R}")
    except PermissionError:
        print(f"  {C.GRY}(skipped - grant Full Disk Access to run this unattended){C.R}")
    except Exception as e:
        print(f"  {C.GRY}(file check skipped: {e}){C.R}")

    # News
    world_news.run()

    print(f"\n{C.GRN}  That's your briefing. Have a great day!{C.R}\n")
    notify("Command Center", "Your morning briefing is ready.")


if __name__ == "__main__":
    run()
