#!/usr/bin/env python3
"""Fetch Quran.com word-level Arabic data for all suras.

This caches verse text, word segmentation, word glosses, and transliteration.
The cache is local source material under ignored `sources/`.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
API = "https://api.quran.com/api/v4/verses/by_chapter/{chapter}"


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "LinguaLeaf/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="sources/quran/qurancom/verses-by-chapter",
        help="cache directory, relative to repo root unless absolute",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    fetched = 0
    skipped = 0
    for chapter in range(1, 115):
        path = out_dir / f"{chapter:03d}.json"
        if path.exists() and not args.force:
            skipped += 1
            continue
        url = (
            API.format(chapter=chapter)
            + "?words=true"
            + "&word_fields=text_uthmani,transliteration,translation"
            + "&fields=text_uthmani"
            + "&per_page=300"
        )
        data = fetch_json(url)
        verses = data.get("verses") or []
        if not verses:
            raise RuntimeError(f"chapter {chapter}: no verses returned")
        if data.get("pagination", {}).get("next_page"):
            raise RuntimeError(f"chapter {chapter}: pagination exceeded per_page=300")
        write_json(path, data)
        fetched += 1
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    manifest = {
        "source": "https://api.quran.com/api/v4",
        "chapters": 114,
        "fetched": fetched,
        "skipped": skipped,
        "files": [f"{chapter:03d}.json" for chapter in range(1, 115)],
    }
    write_json(out_dir / "manifest.json", manifest)
    print(f"quran.com word data: fetched={fetched} skipped={skipped} out={out_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
