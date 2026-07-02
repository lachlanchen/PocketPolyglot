#!/usr/bin/env python3
"""Split trilingual chunks that already contain explicit source units.

This is for long source-spine chunks such as Bible chapters. It preserves the
original chunk id for the first split part and appends ``-part-NN`` for later
parts, so completed neighboring chunks can still be reused.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def backup(path: Path, stamp: str) -> Path:
    target = path.with_name(f"{path.name}.before-unit-split-{stamp}")
    shutil.copy2(path, target)
    return target


def unit_source_len(unit: dict[str, Any]) -> int:
    return sum(len(str(unit.get(lang, ""))) for lang in ("en", "zh", "ja"))


def join_en(units: list[dict[str, Any]]) -> str:
    return " ".join(str(unit.get("en", "")).strip() for unit in units if str(unit.get("en", "")).strip())


def join_cjk(units: list[dict[str, Any]], lang: str) -> str:
    return "".join(str(unit.get(lang, "")).strip() for unit in units if str(unit.get(lang, "")).strip())


def pack_units(units: list[dict[str, Any]], *, max_units: int, max_source_chars: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for unit in units:
        next_chars = unit_source_len(unit)
        if current and (len(current) >= max_units or current_chars + next_chars > max_source_chars):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(unit)
        current_chars += next_chars
    if current:
        groups.append(current)
    return groups


def split_chunk(chunk: dict[str, Any], *, max_units: int, max_source_chars: int) -> list[dict[str, Any]]:
    paragraphs = chunk.get("paragraphs")
    if not isinstance(paragraphs, list) or len(paragraphs) != 1:
        return [chunk]
    paragraph = paragraphs[0]
    units = paragraph.get("units")
    if not isinstance(units, list) or len(units) <= max_units and sum(unit_source_len(unit) for unit in units) <= max_source_chars:
        return [chunk]

    groups = pack_units(units, max_units=max_units, max_source_chars=max_source_chars)
    if len(groups) <= 1:
        return [chunk]

    split_chunks: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        new_paragraph = dict(paragraph)
        new_paragraph["id"] = f"{paragraph['id']}-part-{index:02d}"
        new_paragraph["units"] = group
        new_paragraph["en"] = join_en(group)
        if any(unit.get("zh") for unit in group):
            new_paragraph["zh"] = join_cjk(group, "zh")
        if any(unit.get("ja") for unit in group):
            new_paragraph["ja"] = join_cjk(group, "ja")

        new_chunk = dict(chunk)
        new_chunk["chunk_id"] = chunk["chunk_id"] if index == 1 else f"{chunk['chunk_id']}-part-{index:02d}"
        new_chunk["paragraphs"] = [new_paragraph]
        new_chunk["split_from_chunk_id"] = chunk["chunk_id"]
        new_chunk["split_part"] = index
        new_chunk["split_part_count"] = len(groups)
        new_chunk["chapter_part_en"] = f"{chunk.get('chapter_part_en', chunk['chunk_id'])} (part {index}/{len(groups)})"
        split_chunks.append(new_chunk)
    return split_chunks


def manifest_item(chunk: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "chunk_id": chunk["chunk_id"],
        "paragraph_ids": [paragraph["id"] for paragraph in chunk.get("paragraphs", [])],
    }
    for key in ("split_from_chunk_id", "split_part", "split_part_count"):
        if key in chunk:
            item[key] = chunk[key]
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=0)
    parser.add_argument("--max-units", type=int, default=8)
    parser.add_argument("--max-source-chars", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chunks_path = Path(args.chunks_jsonl)
    manifest_path = Path(args.manifest)
    chunks = load_jsonl(chunks_path)
    manifest = load_json(manifest_path)

    out: list[dict[str, Any]] = []
    split_sources = 0
    for index, chunk in enumerate(chunks, start=1):
        if index < args.start_index or (args.end_index and index > args.end_index):
            out.append(chunk)
            continue
        parts = split_chunk(chunk, max_units=args.max_units, max_source_chars=args.max_source_chars)
        if len(parts) > 1:
            split_sources += 1
        out.extend(parts)

    print(
        f"chunks_before={len(chunks)} chunks_after={len(out)} split_sources={split_sources} "
        f"start_index={args.start_index} max_units={args.max_units} max_source_chars={args.max_source_chars}"
    )
    if args.dry_run or out == chunks:
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chunks_backup = backup(chunks_path, stamp)
    manifest_backup = backup(manifest_path, stamp)
    write_jsonl(chunks_path, out)

    manifest["chunk_count"] = len(out)
    manifest["chunks"] = [manifest_item(chunk) for chunk in out]
    manifest["unit_split_updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["unit_split"] = {
        "start_index": args.start_index,
        "max_units": args.max_units,
        "max_source_chars": args.max_source_chars,
        "split_sources": split_sources,
        "chunks_jsonl_backup": str(chunks_backup),
        "manifest_backup": str(manifest_backup),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
