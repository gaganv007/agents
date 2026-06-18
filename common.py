"""Shared helpers for all agents."""
import os
import sys
import json

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
HOME = os.path.expanduser("~")


class C:
    """ANSI colors (auto-disabled when output isn't a terminal)."""
    _on = sys.stdout.isatty()
    R = "\033[0m" if _on else ""
    B = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""
    RED = "\033[31m" if _on else ""
    GRN = "\033[32m" if _on else ""
    YEL = "\033[33m" if _on else ""
    BLU = "\033[34m" if _on else ""
    MAG = "\033[35m" if _on else ""
    CYN = "\033[36m" if _on else ""
    GRY = "\033[90m" if _on else ""


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # expand ~ in any path-like string values
    return _expand(cfg)


def _expand(obj):
    if isinstance(obj, str) and obj.startswith("~"):
        return os.path.expanduser(obj)
    if isinstance(obj, list):
        return [_expand(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand(v) for k, v in obj.items()}
    return obj


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def human_size(n):
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def header(title, emoji=""):
    line = "=" * 62
    print(f"\n{C.CYN}{line}{C.R}")
    print(f"{C.B}{C.CYN}  {emoji}  {title}{C.R}")
    print(f"{C.CYN}{line}{C.R}")


def confirm(prompt):
    try:
        return input(f"{C.YEL}{prompt} [y/N]: {C.R}").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
            except OSError:
                pass
    return total
