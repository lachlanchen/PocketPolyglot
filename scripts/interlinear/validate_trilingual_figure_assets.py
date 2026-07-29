#!/usr/bin/env python3
"""Validate source-ordered figure assets retained in assembled trilingual JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def collect(data: dict) -> list[dict]:
    return [
        figure
        for chapter in data.get("chapters", [])
        for paragraph in chapter.get("paragraphs", [])
        for figure in paragraph.get("figures", [])
        if isinstance(figure, dict)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = args.source if args.source.is_absolute() else ROOT / args.source
    figures = collect(json.loads(source.read_text(encoding="utf-8")))
    missing: list[str] = []
    empty_paths = 0
    for figure in figures:
        raw_path = str(figure.get("path") or figure.get("image") or "").strip()
        if not raw_path:
            empty_paths += 1
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            missing.append(raw_path)

    expected = args.expected_count
    count_ok = expected is None or len(figures) == expected
    payload = {
        "source": str(source.relative_to(ROOT)),
        "figure_count": len(figures),
        "expected_count": expected,
        "count_ok": count_ok,
        "empty_path_count": empty_paths,
        "missing_count": len(missing),
        "missing": missing,
        "valid": count_ok and not empty_paths and not missing,
    }
    if args.report:
        report = args.report if args.report.is_absolute() else ROOT / args.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
