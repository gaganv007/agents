#!/usr/bin/env python3
"""Disk Space Analyzer - finds the biggest files and folders under a path."""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, human_size, load_config, dir_size  # noqa: E402


def run(root=None, top_n=None):
    cfg = load_config()
    root = os.path.expanduser(root or cfg["disk_analyzer"]["scan_root"])
    top_n = top_n or cfg["disk_analyzer"].get("top_n", 20)
    header(f"Disk Analyzer  ->  {root}", "[DISK]")

    if not os.path.isdir(root):
        print(f"{C.RED}Not a folder: {root}{C.R}")
        return

    # Top-level folder sizes
    print(f"  {C.B}Largest folders (top level):{C.R}")
    folders = []
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.isdir(p) and not os.path.islink(p):
            try:
                folders.append((name, dir_size(p)))
            except OSError:
                pass
    folders.sort(key=lambda x: x[1], reverse=True)
    for name, size in folders[:min(top_n, 12)]:
        print(f"      {C.MAG}{human_size(size):>9}{C.R}  {name}/")

    # Largest individual files (recursive)
    print(f"\n  {C.B}Largest individual files:{C.R}")
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip system/hidden heavy trees to keep it quick
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                if not os.path.islink(fp):
                    files.append((fp, os.path.getsize(fp)))
            except OSError:
                pass
    files.sort(key=lambda x: x[1], reverse=True)
    for fp, size in files[:top_n]:
        rel = os.path.relpath(fp, root)
        rel = rel if len(rel) <= 70 else "..." + rel[-67:]
        print(f"      {C.MAG}{human_size(size):>9}{C.R}  {rel}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--top", type=int, default=None)
    a = p.parse_args()
    run(a.root, a.top)
