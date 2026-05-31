#!/usr/bin/env python3
"""Convert an EPUB to reviewable Markdown and a cleaned Markdown source."""

from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path


LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
RT_RE = re.compile(r"<rt[^>]*>.*?</rt>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
HEADING_RE = re.compile(r"^#{1,6}\s+")


def run_pandoc(epub: Path, raw_output: Path) -> None:
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pandoc", str(epub), "-t", "gfm", "--wrap=none", "-o", str(raw_output)],
        check=True,
    )


def clean_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = LINK_RE.sub(r"\1", line)
    line = RT_RE.sub("", line)
    line = TAG_RE.sub("", line)
    line = html.unescape(line)
    line = line.replace("\u3000", " ")
    if HEADING_RE.match(line):
        line = re.sub(r"[ \t]+", " ", line).strip()
    else:
        line = re.sub(r"[ \t]+", " ", line).strip()
    return line


def clean_markdown(raw_text: str, start_heading: str | None = None, start_text: str | None = None) -> str:
    lines = raw_text.splitlines()
    start = 0
    if start_text:
        wanted = start_text.strip()
        for index, line in enumerate(lines):
            cleaned = clean_line(line)
            if cleaned == wanted:
                start = index
                break
    elif start_heading:
        wanted = start_heading.strip()
        for index, line in enumerate(lines):
            cleaned = clean_line(line)
            if HEADING_RE.match(cleaned) and cleaned.lstrip("#").strip() == wanted:
                start = index
                break
    else:
        for index, line in enumerate(lines):
            cleaned = clean_line(line)
            if cleaned.startswith("# "):
                start = index
                break

    cleaned_lines: list[str] = []
    blank_count = 0
    for raw_line in lines[start:]:
        line = clean_line(raw_line)
        if not line:
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
            continue
        blank_count = 0
        if line.startswith("![]("):
            continue
        if line in {"目录"}:
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", help="input EPUB")
    parser.add_argument("--raw-output", required=True, help="raw Pandoc Markdown")
    parser.add_argument("--clean-output", required=True, help="cleaned Markdown")
    parser.add_argument("--start-heading", help="first heading to keep, e.g. 总序")
    parser.add_argument("--start-text", help="first plain cleaned line to keep, e.g. 第一章")
    args = parser.parse_args()

    epub = Path(args.epub)
    raw_output = Path(args.raw_output)
    clean_output = Path(args.clean_output)

    run_pandoc(epub, raw_output)
    raw_text = raw_output.read_text(encoding="utf-8")
    clean_output.parent.mkdir(parents=True, exist_ok=True)
    clean_output.write_text(clean_markdown(raw_text, args.start_heading, args.start_text), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
