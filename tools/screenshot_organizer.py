#!/usr/bin/env python3
"""Screenshot Organizer - moves screenshots into ~/Pictures/Screenshots/YYYY-MM."""
import os
import sys
import shutil
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config, confirm  # noqa: E402

PATTERNS = ("screenshot", "screen shot", "cleanshot")
EXTS = (".png", ".jpg", ".jpeg", ".heic")


def is_screenshot(name):
    low = name.lower()
    return low.endswith(EXTS) and any(p in low for p in PATTERNS)


def run(apply=False):
    cfg = load_config()
    sources = [os.path.expanduser(cfg["paths"]["desktop"]),
               os.path.expanduser(cfg["paths"]["downloads"])]
    dest_root = os.path.expanduser(cfg["paths"]["screenshots_dest"])
    header("Screenshot Organizer", "[SHOT]")

    found = []
    for src in sources:
        if not os.path.isdir(src):
            continue
        for name in os.listdir(src):
            path = os.path.join(src, name)
            if os.path.isfile(path) and is_screenshot(name):
                found.append(path)

    if not found:
        print(f"{C.GRN}No loose screenshots found on Desktop or in Downloads.{C.R}")
        return

    print(f"  Found {C.B}{len(found)}{C.R} screenshots to move into "
          f"{dest_root.replace(os.path.expanduser('~'), '~')}/YYYY-MM/\n")
    for p in found[:10]:
        print(f"      {C.GRY}- {os.path.basename(p)}{C.R}")
    if len(found) > 10:
        print(f"      {C.GRY}... and {len(found) - 10} more{C.R}")

    if not apply:
        print(f"\n{C.YEL}Preview only. Run with --apply to move them.{C.R}")
        return

    moved = 0
    for p in found:
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        except OSError:
            mtime = datetime.datetime.now()
        sub = os.path.join(dest_root, mtime.strftime("%Y-%m"))
        os.makedirs(sub, exist_ok=True)
        name = os.path.basename(p)
        dst = os.path.join(sub, name)
        base, ext = os.path.splitext(name)
        i = 1
        while os.path.exists(dst):
            dst = os.path.join(sub, f"{base} ({i}){ext}")
            i += 1
        try:
            shutil.move(p, dst)
            moved += 1
        except OSError as e:
            print(f"{C.RED}  could not move {name}: {e}{C.R}")
    print(f"\n{C.GRN}Done. Moved {moved} screenshots.{C.R}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    run(p.parse_args().apply)
