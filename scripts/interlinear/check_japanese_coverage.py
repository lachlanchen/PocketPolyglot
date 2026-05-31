#!/usr/bin/env python3
"""Report Japanese coverage problems in interlinear chunk JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PLACEHOLDER_JA = {"注", "注。", "。"}


def token_text(tokens: list[dict[str, Any]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def unit_ja_text(unit: dict[str, Any]) -> str:
    return "".join(token_text(line) for line in unit.get("ja", []) if isinstance(line, list)).strip()


def inspect_chunk(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    units = zh_chars = ja_chars = empty = placeholder = short = 0
    for paragraph in data.get("paragraphs", []):
        for unit in paragraph.get("units", []):
            units += 1
            zh = token_text(unit.get("zh", [])).strip()
            ja = unit_ja_text(unit)
            zh_chars += len(zh)
            ja_chars += len(ja)
            if not ja:
                empty += 1
            if ja in PLACEHOLDER_JA:
                placeholder += 1
            if len(ja) < max(3, len(zh) // 8):
                short += 1
    ratio = ja_chars / zh_chars if zh_chars else 0.0
    failed = bool(empty or placeholder or (zh_chars >= 120 and ratio < 0.18))
    return {
        "path": str(path),
        "chunk": path.stem,
        "units": units,
        "zh_chars": zh_chars,
        "ja_chars": ja_chars,
        "ratio": ratio,
        "empty_units": empty,
        "placeholder_units": placeholder,
        "short_units": short,
        "failed": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="chunk JSON files or directories")
    parser.add_argument("--all", action="store_true", help="print passing chunks too")
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        else:
            files.append(path)

    failed = 0
    for path in sorted(files):
        report = inspect_chunk(path)
        if report["failed"]:
            failed += 1
        if args.all or report["failed"]:
            print(
                "{chunk}: units={units} zh={zh_chars} ja={ja_chars} ratio={ratio:.2f} "
                "empty={empty_units} placeholder={placeholder_units} short={short_units} {status}".format(
                    **report,
                    status="FAIL" if report["failed"] else "ok",
                )
            )
    if failed:
        print(f"failed chunks: {failed}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
