#!/usr/bin/env python3
"""File Sorter - organizes a folder into category subfolders by file type."""
import os
import sys
import shutil
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, human_size, load_config, confirm  # noqa: E402


def build_ext_map(categories):
    ext_map = {}
    for cat, exts in categories.items():
        for e in exts:
            ext_map[e.lower()] = cat
    return ext_map


def plan(target, cfg):
    fs = cfg["file_sorter"]
    ext_map = build_ext_map(fs["categories"])
    ignore = set(fs.get("ignore", []))
    category_folders = set(fs["categories"].keys()) | {"Other"}

    moves = defaultdict(list)
    for name in os.listdir(target):
        path = os.path.join(target, name)
        if name in ignore or name.startswith("."):
            continue
        if os.path.isdir(path):
            continue  # never touch existing folders
        ext = os.path.splitext(name)[1].lower()
        cat = ext_map.get(ext, "Other")
        if cat in category_folders and os.path.dirname(path) == os.path.join(target, cat):
            continue
        moves[cat].append(name)
    return moves


def run(target=None, apply=False):
    cfg = load_config()
    target = target or cfg["paths"]["downloads"]
    target = os.path.expanduser(target)
    header(f"File Sorter  ->  {target}", "[FILES]")

    if not os.path.isdir(target):
        print(f"{C.RED}Folder not found: {target}{C.R}")
        return 0

    moves = plan(target, cfg)
    total = sum(len(v) for v in moves.values())
    if total == 0:
        print(f"{C.GRN}Nothing to sort - folder is already tidy.{C.R}")
        return 0

    print(f"Found {C.B}{total}{C.R} files to organize into "
          f"{C.B}{len(moves)}{C.R} categories:\n")
    for cat in sorted(moves):
        names = moves[cat]
        print(f"  {C.CYN}{cat:<14}{C.R} {len(names):>3} files")
        for n in names[:3]:
            print(f"      {C.GRY}- {n}{C.R}")
        if len(names) > 3:
            print(f"      {C.GRY}... and {len(names) - 3} more{C.R}")

    if not apply:
        print(f"\n{C.YEL}This was a preview. Run with --apply (or choose Apply "
              f"in the menu) to move the files.{C.R}")
        return 0

    moved = 0
    for cat, names in moves.items():
        dest_dir = os.path.join(target, cat)
        os.makedirs(dest_dir, exist_ok=True)
        for n in names:
            src = os.path.join(target, n)
            dst = os.path.join(dest_dir, n)
            base, ext = os.path.splitext(n)
            i = 1
            while os.path.exists(dst):
                dst = os.path.join(dest_dir, f"{base} ({i}){ext}")
                i += 1
            try:
                shutil.move(src, dst)
                moved += 1
            except OSError as e:
                print(f"{C.RED}  could not move {n}: {e}{C.R}")
    print(f"\n{C.GRN}Done. Moved {moved} files into category folders.{C.R}")
    return moved


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Sort a folder by file type.")
    p.add_argument("target", nargs="?", help="Folder to sort (default: Downloads)")
    p.add_argument("--apply", action="store_true", help="Actually move files")
    a = p.parse_args()
    run(a.target, a.apply)
