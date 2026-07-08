#!/usr/bin/env python3
"""Sync poetry source paragraphs after source-marker cleanup.

When source line/page markers are removed from output units, the source
``chunks.jsonl`` must be cleaned in lockstep. Otherwise final validation can
fail because units no longer reconstruct the old noisy source paragraph.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRAILING_LINE_NUMBER_RE = re.compile(r"(?s)^(?P<body>.*?[A-Za-z].*?)(?P<space>[ \t]+)(?P<num>[1-9]\d*0)\s*$")


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def strip_trailing_line_number(text: str) -> str:
    match = TRAILING_LINE_NUMBER_RE.fullmatch(str(text or ""))
    if not match:
        return str(text or "")
    # Only remove common poetry marginal line numbers, not arbitrary years or
    # catalogue numbers.
    number = int(match.group("num"))
    if number > 500:
        return str(text or "")
    return match.group("body").rstrip()


def trim_tokens_to_text(tokens: Any, target: str) -> bool:
    if not isinstance(tokens, list):
        return False
    current = token_text(tokens)
    if current == target:
        return False
    if not current.startswith(target):
        return False
    remaining = len(target)
    kept: list[dict[str, Any]] = []
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        if remaining >= len(text):
            kept.append(token)
            remaining -= len(text)
        elif remaining > 0:
            new_token = dict(token)
            new_token["t"] = text[:remaining]
            kept.append(new_token)
            remaining = 0
        else:
            break
    tokens[:] = kept
    return True


def clean_output_chunk(path: Path, *, dry_run: bool) -> tuple[dict[str, str], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    paragraph_source: dict[str, str] = {}
    changes = 0
    for paragraph in data.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        parts: list[str] = []
        for unit in paragraph.get("units") or []:
            if not isinstance(unit, dict):
                continue
            old_source = str(unit.get("source_en", ""))
            new_source = strip_trailing_line_number(old_source)
            if new_source != old_source:
                unit["source_en"] = new_source
                changes += 1
            if trim_tokens_to_text(unit.get("en"), new_source):
                changes += 1
            parts.append(str(unit.get("source_en", "")))
        rebuilt = "".join(parts)
        if rebuilt and paragraph.get("source_en") != rebuilt:
            paragraph["source_en"] = rebuilt
            changes += 1
        paragraph_id = str(paragraph.get("id") or "")
        if paragraph_id:
            paragraph_source[paragraph_id] = rebuilt
    if changes and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paragraph_source, changes


def rewrite_chunks_jsonl(path: Path, paragraph_source: dict[str, str]) -> int:
    rows = []
    changes = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for paragraph in row.get("paragraphs") or []:
            if not isinstance(paragraph, dict):
                continue
            paragraph_id = str(paragraph.get("id") or "")
            if paragraph_id in paragraph_source and paragraph.get("en") != paragraph_source[paragraph_id]:
                paragraph["en"] = paragraph_source[paragraph_id]
                changes += 1
        rows.append(row)
    if changes:
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", type=Path, required=True)
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=Path("books/_backups/poetry-source-sync"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    book_id = args.chunk_dir.parts[1] if len(args.chunk_dir.parts) > 1 and args.chunk_dir.parts[0] == "books" else args.chunk_dir.name
    backup_dir = args.backup_root / stamp / book_id

    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.chunks_jsonl, backup_dir / args.chunks_jsonl.name)

    paragraph_source: dict[str, str] = {}
    changed_chunks = 0
    output_changes = 0
    for path in sorted(args.chunk_dir.glob("*.json")):
        if not args.dry_run:
            shutil.copy2(path, backup_dir / path.name)
        sources, changes = clean_output_chunk(path, dry_run=args.dry_run)
        paragraph_source.update(sources)
        if changes:
            changed_chunks += 1
            output_changes += changes
            print(f"{path}: output_changes={changes}")
    if args.dry_run:
        # Count the source rows that would change without writing them.
        source_changes = 0
        for line in args.chunks_jsonl.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            for paragraph in row.get("paragraphs") or []:
                if not isinstance(paragraph, dict):
                    continue
                paragraph_id = str(paragraph.get("id") or "")
                if paragraph_id in paragraph_source and paragraph.get("en") != paragraph_source[paragraph_id]:
                    source_changes += 1
    else:
        source_changes = rewrite_chunks_jsonl(args.chunks_jsonl, paragraph_source)
    print(f"book={book_id}")
    print(f"changed_output_chunks={changed_chunks}")
    print(f"output_changes={output_changes}")
    print(f"source_paragraph_changes={source_changes}")
    if not args.dry_run:
        print(f"backup_root={backup_dir.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
