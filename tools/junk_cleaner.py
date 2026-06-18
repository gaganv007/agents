#!/usr/bin/env python3
"""Junk / Cache Cleaner - reports and (with --apply) clears caches and dev junk."""
import os
import sys
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, human_size, load_config, dir_size, confirm  # noqa: E402


def find_junk_dirs(root, names):
    hits = []
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return hits
    for dirpath, dirnames, _ in os.walk(root):
        for d in list(dirnames):
            if d in names:
                hits.append(os.path.join(dirpath, d))
                dirnames.remove(d)  # don't descend into it
    return hits


def run(apply=False, assume_yes=False):
    cfg = load_config()
    jc = cfg["junk_cleaner"]
    header("Junk / Cache Cleaner", "[CLEAN]")

    entries = []  # (path, size, is_cache_contents)
    for t in jc["targets"]:
        t = os.path.expanduser(t)
        if os.path.isdir(t):
            sz = dir_size(t)
            if sz > 0:
                entries.append((t, sz, True))

    junk_dirs = find_junk_dirs(jc.get("scan_root_for_junk", "~/Desktop"),
                               set(jc.get("find_junk_dirs", [])))
    for jd in junk_dirs:
        try:
            entries.append((jd, dir_size(jd), False))
        except OSError:
            pass

    if not entries:
        print(f"{C.GRN}Nothing notable to clean.{C.R}")
        return

    entries.sort(key=lambda x: x[1], reverse=True)
    total = sum(e[1] for e in entries)
    print(f"  Reclaimable: {C.B}{C.YEL}{human_size(total)}{C.R}\n")
    for path, size, is_cache in entries:
        label = "cache" if is_cache else "dev junk"
        disp = path.replace(os.path.expanduser("~"), "~")
        disp = disp if len(disp) <= 60 else "..." + disp[-57:]
        print(f"      {C.MAG}{human_size(size):>9}{C.R}  {C.GRY}[{label}]{C.R} {disp}")

    if not apply:
        print(f"\n{C.YEL}Preview only. Run with --apply to delete cache CONTENTS and "
              f"junk folders.{C.R}")
        print(f"{C.GRY}(Cache folders are emptied, not removed. Apps regenerate them.){C.R}")
        return

    if not assume_yes and not confirm(f"\nDelete the above and reclaim ~{human_size(total)}?"):
        print(f"{C.GRY}Cancelled.{C.R}")
        return

    freed = 0
    for path, size, is_cache in entries:
        try:
            if is_cache:
                # empty the cache dir contents, keep the dir itself
                for name in os.listdir(path):
                    p = os.path.join(path, name)
                    if os.path.isdir(p) and not os.path.islink(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        try:
                            os.remove(p)
                        except OSError:
                            pass
            else:
                shutil.rmtree(path, ignore_errors=True)
            freed += size
        except OSError as e:
            print(f"{C.RED}  skip {path}: {e}{C.R}")
    print(f"\n{C.GRN}Done. Reclaimed approximately {human_size(freed)}.{C.R}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    a = p.parse_args()
    run(a.apply, a.yes)
