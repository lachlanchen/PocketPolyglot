#!/usr/bin/env python3
"""Rebuild strict trilingual chunks from accepted plain text without model calls."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from codex_trilingual_plain_json_worker import (
    kanji_note_plain_errors_are_promotable,
    load_ja_reading_overrides,
    load_source_chunks,
    normalize_plain_unit_ids,
    plain_text,
    promote_plain_chunk,
    source_unit_plan,
    validate_plain_chunk,
    write_json,
)
from validate_trilingual_interlinear_json import validate_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def token_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(
            str(token.get("t", "")) if isinstance(token, dict) else str(token)
            for token in value
        )
    return plain_text(value)


def strict_to_plain(source: dict[str, Any], strict: dict[str, Any]) -> dict[str, Any]:
    strict_by_id = {
        str(paragraph.get("id")): paragraph
        for paragraph in strict.get("paragraphs", [])
        if isinstance(paragraph, dict)
    }
    paragraphs: list[dict[str, Any]] = []
    for source_paragraph in source_unit_plan(source):
        paragraph_id = source_paragraph["id"]
        strict_paragraph = strict_by_id.get(paragraph_id)
        if not strict_paragraph:
            raise ValueError(f"missing strict paragraph {paragraph_id}")
        strict_units = strict_paragraph.get("units") or []
        source_units = source_paragraph["units"]
        if len(strict_units) != len(source_units):
            raise ValueError(
                f"{paragraph_id}: strict/source unit count mismatch "
                f"{len(strict_units)} != {len(source_units)}"
            )
        units = []
        for source_unit, strict_unit in zip(source_units, strict_units):
            units.append(
                {
                    "unit_id": source_unit["unit_id"],
                    "ja": token_text(strict_unit.get("ja", [])),
                    "zh": token_text(strict_unit.get("zh", [])),
                    **(
                        {"en": token_text(strict_unit.get("en", []))}
                        if source.get("source_spine_lang") != "en"
                        else {}
                    ),
                }
            )
        paragraphs.append({"id": paragraph_id, "units": units})
    return {
        "schema_version": "0.1-plain",
        "mode": "trilingual_plain_alignment",
        "chunk_id": source["chunk_id"],
        "paragraphs": paragraphs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--plain-dir")
    parser.add_argument("--strict-dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reading-overrides")
    parser.add_argument("--backup-dir")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    sources = load_source_chunks(Path(args.chunks_jsonl))
    plain_dir = Path(args.plain_dir) if args.plain_dir else None
    strict_dir = Path(args.strict_dir) if args.strict_dir else None
    output_dir = Path(args.output_dir)
    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    overrides = load_ja_reading_overrides(args.reading_overrides or "")
    output_dir.mkdir(parents=True, exist_ok=True)
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)

    rebuilt = 0
    skipped = 0
    failed = 0
    for index, source in enumerate(sources, start=1):
        if index < args.start_index or (args.end_index and index > args.end_index):
            continue
        chunk_id = source["chunk_id"]
        output_path = output_dir / f"{chunk_id}.json"
        if output_path.exists() and not args.overwrite:
            skipped += 1
            continue
        try:
            plain_path = plain_dir / f"{chunk_id}.json" if plain_dir else None
            strict_path = strict_dir / f"{chunk_id}.json" if strict_dir else None
            if plain_path and plain_path.exists():
                plain = load_json(plain_path)
            elif strict_path and strict_path.exists():
                plain = strict_to_plain(source, load_json(strict_path))
            else:
                skipped += 1
                continue
            normalize_plain_unit_ids(source, plain)
            errors = validate_plain_chunk(source, plain)
            if errors and not kanji_note_plain_errors_are_promotable(plain, errors):
                raise ValueError("; ".join(errors[:20]))
            strict = promote_plain_chunk(source, plain, overrides)
            strict_errors = validate_chunk(source, strict)
            if strict_errors:
                raise ValueError("; ".join(strict_errors[:20]))
            if backup_dir and output_path.exists():
                backup_path = backup_dir / output_path.name
                if not backup_path.exists():
                    shutil.copy2(output_path, backup_path)
            write_json(output_path, strict)
            rebuilt += 1
            print(f"rebuilt {chunk_id}")
        except Exception as exc:
            failed += 1
            print(f"failed {chunk_id}: {exc}")

    print(f"rebuilt={rebuilt} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
