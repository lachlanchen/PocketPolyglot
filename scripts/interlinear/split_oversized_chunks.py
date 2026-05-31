#!/usr/bin/env python3
"""Split oversized single-paragraph chunks into stable subchunks.

This is a manifest-preserving repair tool for provider workers. It keeps the
original chunk id for the first subchunk and appends ``-part-NN`` for later
subchunks, so existing valid neighboring chunks remain reusable.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENTENCE_BOUNDARY_RE = re.compile(r".+?(?:[。！？；;]|$)", re.S)
SOFT_BOUNDARY_RE = re.compile(r".+?(?:[，、,]|$)", re.S)
LEADING_CLOSE_NOTE_RE = re.compile(r"^(\s*〉\s*)")
PART_SUFFIX_RE = re.compile(r"-part-\d+$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_chunks(path: Path, chunks: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")


def regex_pieces(text: str, pattern: re.Pattern[str]) -> list[str]:
    pieces = [match.group(0) for match in pattern.finditer(text) if match.group(0)]
    return pieces or [text]


def pack_pieces(pieces: list[str], max_chars: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > max_chars:
            packed.append(current)
            current = piece
        else:
            current += piece
    if current:
        packed.append(current)
    return packed


def hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index:index + max_chars] for index in range(0, len(text), max_chars)]


def attach_leading_note_closers(parts: list[str]) -> list[str]:
    """Move a leading 〉 marker back to the previous part.

    Classical note text often uses 〈 ... 〉. Sentence splitting can leave the
    closing marker alone at the start of the next subchunk, which confuses the
    annotator and makes source reconstruction more brittle.
    """
    fixed = parts[:]
    for index in range(1, len(fixed)):
        match = LEADING_CLOSE_NOTE_RE.match(fixed[index])
        if not match:
            continue
        fixed[index - 1] += match.group(1)
        fixed[index] = fixed[index][match.end():]
    return [part for part in fixed if part]


def strip_part_suffix(value: str) -> str:
    return PART_SUFFIX_RE.sub("", value)


def merge_existing_split_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    first = group[0]
    origin = str(first.get("split_from_chunk_id") or first["chunk_id"])
    ordered = sorted(group, key=lambda item: int(item.get("split_part", 0) or 0))
    base = dict(first)
    base["chunk_id"] = origin
    base.pop("split_from_chunk_id", None)
    base.pop("split_part", None)
    base.pop("split_part_count", None)

    first_paragraph = dict(ordered[0]["paragraphs"][0])
    first_paragraph["id"] = strip_part_suffix(str(first_paragraph["id"]))
    first_paragraph["text"] = "".join(str(item["paragraphs"][0].get("text", "")) for item in ordered)
    base["paragraphs"] = [first_paragraph]
    return base


def merge_existing_split_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild original chunks before re-splitting.

    This makes the tool safe to rerun after tuning ``--max-chars`` or fixing the
    split algorithm: existing split chunks are first merged by origin, then the
    current splitter creates the new stable manifest.
    """
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        origin = chunk.get("split_from_chunk_id")
        if not origin:
            merged.append(chunk)
            index += 1
            continue

        group = [chunk]
        index += 1
        while index < len(chunks) and chunks[index].get("split_from_chunk_id") == origin:
            group.append(chunks[index])
            index += 1
        merged.append(merge_existing_split_group(group))
    return merged


def split_text(text: str, max_chars: int) -> list[str]:
    sentence_parts = pack_pieces(regex_pieces(text, SENTENCE_BOUNDARY_RE), max_chars)
    final: list[str] = []
    for sentence_part in sentence_parts:
        if len(sentence_part) <= max_chars:
            final.append(sentence_part)
            continue
        comma_parts = pack_pieces(regex_pieces(sentence_part, SOFT_BOUNDARY_RE), max_chars)
        for comma_part in comma_parts:
            if len(comma_part) <= max_chars:
                final.append(comma_part)
            else:
                final.extend(hard_split(comma_part, max_chars))
    return attach_leading_note_closers([part for part in final if part])


def split_chunk(chunk: dict[str, Any], max_chars: int) -> list[dict[str, Any]]:
    paragraphs = chunk.get("paragraphs")
    if not isinstance(paragraphs, list) or len(paragraphs) != 1:
        return [chunk]
    paragraph = paragraphs[0]
    text = str(paragraph.get("text", ""))
    if len(text) <= max_chars:
        return [chunk]

    parts = split_text(text, max_chars)
    if len(parts) <= 1 or "".join(parts) != text:
        return [chunk]

    split_chunks: list[dict[str, Any]] = []
    for index, part in enumerate(parts, start=1):
        new_paragraph = dict(paragraph)
        new_paragraph["id"] = f"{paragraph['id']}-part-{index:02d}"
        new_paragraph["text"] = part
        new_chunk = dict(chunk)
        new_chunk["chunk_id"] = chunk["chunk_id"] if index == 1 else f"{chunk['chunk_id']}-part-{index:02d}"
        new_chunk["paragraphs"] = [new_paragraph]
        new_chunk["split_from_chunk_id"] = chunk["chunk_id"]
        new_chunk["split_part"] = index
        new_chunk["split_part_count"] = len(parts)
        split_chunks.append(new_chunk)
    return split_chunks


def manifest_item(chunk: dict[str, Any]) -> dict[str, Any]:
    item = {
        "chunk_id": chunk["chunk_id"],
        "story_id": chunk["story_id"],
        "paragraph_ids": [paragraph["id"] for paragraph in chunk.get("paragraphs", [])],
    }
    for key in ("paired_story_key", "paired_reference_key", "jp_reference_scope"):
        if key in chunk:
            item[key] = chunk[key]
    if "jp_reference" in chunk:
        item["jp_reference_ids"] = [paragraph["id"] for paragraph in chunk.get("jp_reference", [])]
    if "split_from_chunk_id" in chunk:
        item["split_from_chunk_id"] = chunk["split_from_chunk_id"]
        item["split_part"] = chunk["split_part"]
        item["split_part_count"] = chunk["split_part_count"]
    return item


def backup(path: Path, stamp: str) -> Path:
    target = path.with_name(f"{path.name}.before-split-{stamp}")
    shutil.copy2(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-chars", type=int, default=420)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chunks_path = Path(args.chunks_jsonl)
    manifest_path = Path(args.manifest)
    chunks = merge_existing_split_chunks(load_chunks(chunks_path))
    manifest = load_json(manifest_path)

    split_chunks: list[dict[str, Any]] = []
    split_source_count = 0
    for chunk in chunks:
        parts = split_chunk(chunk, args.max_chars)
        if len(parts) > 1:
            split_source_count += 1
        split_chunks.extend(parts)

    print(
        f"chunks_before={len(chunks)} chunks_after={len(split_chunks)} "
        f"split_sources={split_source_count} max_chars={args.max_chars}"
    )
    if args.dry_run or split_chunks == chunks:
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chunks_backup = backup(chunks_path, stamp)
    manifest_backup = backup(manifest_path, stamp)

    manifest["chunk_count"] = len(split_chunks)
    manifest["split_oversized_chunks"] = True
    manifest["split_max_chars"] = args.max_chars
    manifest["split_updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["split_backups"] = {
        "chunks_jsonl": str(chunks_backup),
        "manifest": str(manifest_backup),
    }
    manifest["chunks"] = [manifest_item(chunk) for chunk in split_chunks]

    write_chunks(chunks_path, split_chunks)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
