#!/usr/bin/env python3
"""Download a complete local Zhouyi/Yijing source tree from Chinese Wikisource."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "sources" / "yijing" / "zh" / "wenyan-wikisource"
USER_AGENT = "LinguaLeaf/0.1 (local task preparation; https://learn.lazying.art)"

HEXAGRAMS = [
    "乾",
    "坤",
    "屯",
    "蒙",
    "需",
    "訟",
    "師",
    "比",
    "小畜",
    "履",
    "泰",
    "否",
    "同人",
    "大有",
    "謙",
    "豫",
    "隨",
    "蠱",
    "臨",
    "觀",
    "噬嗑",
    "賁",
    "剝",
    "復",
    "无妄",
    "大畜",
    "頤",
    "大過",
    "坎",
    "離",
    "咸",
    "恒",
    "遯",
    "大壯",
    "晉",
    "明夷",
    "家人",
    "睽",
    "蹇",
    "解",
    "損",
    "益",
    "夬",
    "姤",
    "萃",
    "升",
    "困",
    "井",
    "革",
    "鼎",
    "震",
    "艮",
    "漸",
    "歸妹",
    "豐",
    "旅",
    "巽",
    "兌",
    "渙",
    "節",
    "中孚",
    "小過",
    "既濟",
    "未濟",
]

APPENDICES = [
    "彖",
    "大象",
    "小象",
    "文言",
    "繫辭上",
    "繫辭下",
    "說卦",
    "序卦",
    "雜卦",
]

REDIRECT_RE = re.compile(r"^#(?:REDIRECT|重定向)\s*\[\[([^]#|]+)", re.I)


def request_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def wiki_url(title: str, action: str) -> str:
    return (
        "https://zh.wikisource.org/w/index.php?title="
        + urllib.parse.quote(title)
        + f"&action={action}"
    )


def fetch_page(title: str, *, sleep_seconds: float) -> tuple[str, str, str]:
    raw = request_text(wiki_url(title, "raw"))
    actual_title = title
    match = REDIRECT_RE.match(raw.strip())
    if match:
        actual_title = match.group(1).strip()
        time.sleep(sleep_seconds)
        raw = request_text(wiki_url(actual_title, "raw"))
    time.sleep(sleep_seconds)
    html = request_text(wiki_url(actual_title, "render"))
    return actual_title, raw, html


def safe_name(title: str) -> str:
    return title.replace("/", "__").replace(" ", "_")


def page_titles() -> list[str]:
    return ["周易"] + [f"周易/{name}" for name in HEXAGRAMS] + [f"周易/{name}" for name in APPENDICES]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args()

    out_dir = args.out_dir
    raw_dir = out_dir / "raw"
    html_dir = out_dir / "html"
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for index, requested_title in enumerate(page_titles(), start=1):
        actual_title, raw, html = fetch_page(requested_title, sleep_seconds=args.sleep_seconds)
        stem = f"{index:04d}-{safe_name(requested_title)}"
        raw_path = raw_dir / f"{stem}.wiki"
        html_path = html_dir / f"{stem}.html"
        raw_path.write_text(raw, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        manifest.append(
            {
                "index": index,
                "title": requested_title,
                "actual_title": actual_title,
                "status": "ok",
                "raw": str(raw_path.relative_to(out_dir)),
                "html": str(html_path.relative_to(out_dir)),
                "source_url": wiki_url(actual_title, "view"),
            }
        )
        print(f"{index:04d} {requested_title} -> {actual_title}")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "# 周易 Wikisource Local Mirror\n\n"
        f"Downloaded from Chinese Wikisource on {datetime.now(timezone.utc).isoformat()}.\n\n"
        "Includes the Zhouyi index page, the 64 hexagram pages in King Wen order, "
        "and the traditional appendix pages. Redirected appendix pages are resolved "
        "to their `易傳/*` targets while preserving the requested `周易/*` title in "
        "`manifest.json`.\n",
        encoding="utf-8",
    )
    print(f"manifest: {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
