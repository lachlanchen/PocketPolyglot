#!/usr/bin/env python3
"""Remove misleading one-color grammar roles from collapsed rows.

For contents pages, acknowledgements, bibliographic notes, and critical
apparatus, a model can mark nearly every token as one grammar role. That renders
as a page-sized single-color block. This script keeps the text/readings but
removes only the collapsed ``g`` roles from rows whose dominant role exceeds the
configured ratio.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUBSTANTIVE_RE = re.compile(r"[A-Za-z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
GRAMMAR_ROLES = {
    "subject",
    "predicate",
    "object",
    "attributive",
    "adverbial",
    "complement",
    "topic",
    "function",
}


def role_counts(tokens: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(tokens, list):
        return counts
    for token in tokens:
        if not isinstance(token, dict):
            continue
        if not SUBSTANTIVE_RE.search(str(token.get("t", ""))):
            continue
        role = str(token.get("g") or "")
        if role in GRAMMAR_ROLES:
            counts[role] += 1
    return counts


def soften_tokens(tokens: Any, *, min_tokens: int, ratio: float) -> int:
    counts = role_counts(tokens)
    total = sum(counts.values())
    if total < min_tokens:
        return 0
    _role, count = counts.most_common(1)[0]
    if count / total < ratio:
        return 0
    changed = 0
    for token in tokens:
        if isinstance(token, dict) and token.pop("g", None) is not None:
            changed += 1
    return changed


def soften_file(path: Path, backup_dir: Path | None, dry_run: bool, min_tokens: int, ratio: float) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for paragraph in data.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        for unit in paragraph.get("units") or []:
            if not isinstance(unit, dict):
                continue
            for lang in ("en", "zh", "ja"):
                changed += soften_tokens(unit.get(lang), min_tokens=min_tokens, ratio=ratio)
    if changed and not dry_run:
        if backup_dir is not None:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / path.name)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", action="append", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=Path("books/_backups/collapsed-grammar-soften"))
    parser.add_argument("--min-tokens", type=int, default=40)
    parser.add_argument("--ratio", type=float, default=0.95)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total_files = 0
    total_tokens = 0
    for chunk_dir in args.chunk_dir:
        book_id = chunk_dir.parts[1] if len(chunk_dir.parts) > 1 and chunk_dir.parts[0] == "books" else chunk_dir.name
        backup_dir = None if args.dry_run else args.backup_root / stamp / book_id
        book_files = 0
        book_tokens = 0
        for path in sorted(chunk_dir.glob("*.json")):
            changed = soften_file(path, backup_dir, args.dry_run, args.min_tokens, args.ratio)
            if changed:
                print(f"{path}: removed_g={changed}")
                book_files += 1
                book_tokens += changed
        print(f"book={book_id} changed_files={book_files} removed_g={book_tokens}")
        total_files += book_files
        total_tokens += book_tokens
    print(f"changed_files={total_files}")
    print(f"removed_g={total_tokens}")
    if not args.dry_run:
        print(f"backup_root={args.backup_root / stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
