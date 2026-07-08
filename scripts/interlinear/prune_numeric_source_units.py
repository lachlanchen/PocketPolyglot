#!/usr/bin/env python3
"""Remove standalone numeric source markers from trilingual chunk JSON.

Poetry PDFs often carry marginal line numbers or note/page markers. Spark can
faithfully translate those as separate EN/ZH/JA rows, which then renders as
meaningless isolated numbers in the pocket book. This script removes a unit only
when all three language rows are numeric/chrome markers.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NUMERIC_MARKER_RE = re.compile(
    r"^[\s\[\]().,:;:：，。；、'’\"“”\-–—]*"
    r"\d+"
    r"[\d\s\[\]().,:;:：，。；、'’\"“”\-–—]*$"
)


def token_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(str(token.get("t", "")) for token in value if isinstance(token, dict)).strip()


def is_numeric_marker_unit(unit: Any) -> bool:
    if not isinstance(unit, dict):
        return False
    texts = [token_text(unit.get(lang)) for lang in ("en", "zh", "ja")]
    return all(text and NUMERIC_MARKER_RE.fullmatch(text) for text in texts)


def prune_file(path: Path, backup_dir: Path | None, dry_run: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    removed = 0
    for paragraph in data.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        units = paragraph.get("units")
        if not isinstance(units, list):
            continue
        kept = []
        paragraph_removed = 0
        for unit in units:
            if is_numeric_marker_unit(unit):
                paragraph_removed += 1
            else:
                kept.append(unit)
        removed += paragraph_removed
        if paragraph_removed and not dry_run:
            paragraph["units"] = kept
    if removed and not dry_run:
        if backup_dir is not None:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / path.name)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", action="append", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=Path("books/_backups/numeric-source-unit-prune"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total_files = 0
    total_units = 0
    for chunk_dir in args.chunk_dir:
        book_id = chunk_dir.parts[1] if len(chunk_dir.parts) > 1 and chunk_dir.parts[0] == "books" else chunk_dir.name
        backup_dir = None if args.dry_run else args.backup_root / stamp / book_id
        book_files = 0
        book_units = 0
        for path in sorted(chunk_dir.glob("*.json")):
            removed = prune_file(path, backup_dir, args.dry_run)
            if removed:
                print(f"{path}: removed_units={removed}")
                book_files += 1
                book_units += removed
        print(f"book={book_id} changed_files={book_files} removed_units={book_units}")
        total_files += book_files
        total_units += book_units
    print(f"changed_files={total_files}")
    print(f"removed_units={total_units}")
    if not args.dry_run:
        print(f"backup_root={args.backup_root / stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
