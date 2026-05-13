#!/usr/bin/env python3
"""Normalize the anthology's Kokoro section into heading-rich Markdown."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


HEADING_RE = re.compile(r"^#{1,6}\s+")
PARTS = {
    "上 先生と私",
    "中 両親と私",
    "下 先生と遺書",
}
CHAPTER_RE = re.compile(r"^[一二三四五六七八九十]+$")


def normalize(lines: list[str], title: str) -> list[str]:
    output: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            output.append("")
            continue
        if HEADING_RE.match(line):
            output.append(f"# {title}")
        elif line in PARTS:
            output.append(f"## {line}")
        elif CHAPTER_RE.match(line):
            output.append(f"### {line}")
        else:
            output.append(raw_line.rstrip())

    compacted: list[str] = []
    previous_blank = False
    for line in output:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        compacted.append(line)
        previous_blank = is_blank
    while compacted and not compacted[-1].strip():
        compacted.pop()
    return compacted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="こころ")
    args = parser.parse_args()

    source = Path(args.markdown)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = normalize(source.read_text(encoding="utf-8").splitlines(), args.title)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{output}: {len(lines)} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
