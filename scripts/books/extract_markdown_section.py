#!/usr/bin/env python3
"""Extract one top-level Markdown section from a larger converted book."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def matches(title: str, wanted: str, *, prefix: bool) -> bool:
    title = title.strip()
    wanted = wanted.strip()
    return title.startswith(wanted) if prefix else title == wanted


def extract_section(
    lines: list[str],
    *,
    start_heading: str,
    end_heading: str | None,
    start_prefix: bool,
    end_prefix: bool,
) -> list[str]:
    start_index: int | None = None
    start_level: int | None = None

    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if matches(match.group(2), start_heading, prefix=start_prefix):
            start_index = index
            start_level = len(match.group(1))
            break

    if start_index is None or start_level is None:
        raise ValueError(f"start heading not found: {start_heading}")

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        if end_heading and matches(title, end_heading, prefix=end_prefix):
            end_index = index
            break
        if not end_heading and level <= start_level:
            end_index = index
            break

    extracted = lines[start_index:end_index]
    while extracted and not extracted[-1].strip():
        extracted.pop()
    return extracted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown")
    parser.add_argument("--start-heading", required=True)
    parser.add_argument("--end-heading")
    parser.add_argument("--start-prefix", action="store_true")
    parser.add_argument("--end-prefix", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.markdown)
    result = extract_section(
        source.read_text(encoding="utf-8").splitlines(),
        start_heading=args.start_heading,
        end_heading=args.end_heading,
        start_prefix=args.start_prefix,
        end_prefix=args.end_prefix,
    )
    if not result:
        print("no lines extracted", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"{output}: {len(result)} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
