#!/usr/bin/env python3
"""World News - pulls top headlines from public RSS feeds (no API key needed)."""
import os
import sys
import argparse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch(name, url, limit):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        root = ET.fromstring(data)
        items = root.findall(".//item")[:limit]
        if not items:  # Atom feed fallback
            ns = "{http://www.w3.org/2005/Atom}"
            items = root.findall(f".//{ns}entry")[:limit]
            titles = [unescape((it.findtext(f"{ns}title") or "").strip()) for it in items]
        else:
            titles = [unescape((it.findtext("title") or "").strip()) for it in items]
        return name, [t for t in titles if t], None
    except Exception as e:
        return name, [], str(e)


def run(per_feed=None):
    cfg = load_config()
    feeds = cfg["world_news"]["feeds"]
    limit = per_feed or cfg["world_news"].get("per_feed", 5)
    header("Trending World News", "[NEWS]")
    print(f"  {C.GRY}Fetching {len(feeds)} sources...{C.R}\n")

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda kv: fetch(kv[0], kv[1], limit), feeds.items()))

    for name, titles, err in results:
        print(f"  {C.B}{C.BLU}{name}{C.R}")
        if err:
            print(f"      {C.RED}(unavailable: {err}){C.R}")
        for t in titles:
            t = t if len(t) <= 100 else t[:97] + "..."
            print(f"      {C.YEL}-{C.R} {t}")
        print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--per-feed", type=int, default=None)
    run(p.parse_args().per_feed)
