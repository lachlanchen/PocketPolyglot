#!/usr/bin/env python3
"""Add TeX furigana macros to plain Japanese text.

This is a drafting helper. Always review the readings, especially for
classical Chinese/Japanese, names, and scholarly terms.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pykakasi


KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
TEXT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff々〆ヵヶー]+")


def strip_matching_tail(reading: str, tail: str) -> str:
    while tail and reading.endswith(tail[-1]):
        reading = reading[:-1]
        tail = tail[:-1]
    return reading


def annotate_token(orig: str, hira: str) -> str:
    if not KANJI_RE.search(orig):
        return orig

    match = TEXT_RE.search(orig)
    if not match:
        return orig

    head = orig[: match.start()]
    core = match.group(0)
    tail = orig[match.end() :]
    reading = strip_matching_tail(hira, tail)
    return rf"{head}\jpruby{{{core}}}{{{reading}}}{tail}"


def annotate(text: str) -> str:
    kakasi = pykakasi.kakasi()
    parts: list[str] = []
    for item in kakasi.convert(text):
        parts.append(annotate_token(item["orig"], item["hira"]))
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text_or_file", nargs="?", help="plain Japanese text or a file path")
    args = parser.parse_args(argv)

    if args.text_or_file:
        path = Path(args.text_or_file)
        text = path.read_text(encoding="utf-8") if path.exists() else args.text_or_file
    else:
        text = sys.stdin.read()

    sys.stdout.write(annotate(text))
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
