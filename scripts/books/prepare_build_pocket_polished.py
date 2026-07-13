#!/usr/bin/env python3
"""Prepare lossless page/chunk tasks for build-pocket-polished editions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from pocket_polished_common import (
    OUTPUT_ROOT,
    ROOT,
    SOURCE_QUEUE,
    detect_source_language,
    make_review_chunks,
    output_schema,
    reviewer_schema,
    sha256_text,
    source_tasks,
    split_tex_segments,
    write_json,
    write_jsonl,
)


def prepare_book(task: dict, *, max_chars: int, force: bool) -> dict:
    book_id = task["book_id"]
    source_tex = ROOT / "build-pocket" / book_id / "exact/tex/book.tex"
    if not source_tex.exists():
        raise FileNotFoundError(f"missing exact source TeX: {source_tex}")
    book_root = OUTPUT_ROOT / book_id
    manifest_path = book_root / "tasks/manifest.json"
    source_text = source_tex.read_text(encoding="utf-8", errors="strict")
    source_hash = sha256_text(source_text)
    source_language = detect_source_language(source_text)
    if manifest_path.exists() and not force:
        current = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
        if current.get("source_tex_sha256") == source_hash and current.get("max_chunk_chars") == max_chars:
            return current

    segments = split_tex_segments(source_text, book_id)
    chunks = make_review_chunks(
        segments,
        book_id=book_id,
        title=task.get("title", book_id),
        source=task["source"],
        source_language=source_language,
        max_chars=max_chars,
    )
    write_jsonl(book_root / "source/segments.jsonl", segments)
    write_jsonl(book_root / "tasks/chunks.jsonl", chunks)
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "title": task.get("title", book_id),
        "author": task.get("author", ""),
        "source": task["source"],
        "source_language": source_language,
        "source_exact_tex": str(source_tex.relative_to(ROOT)),
        "source_tex_sha256": source_hash,
        "segment_count": len(segments),
        "review_segment_count": sum(item["kind"] in {"text", "table"} for item in segments),
        "protected_segment_count": sum(item["kind"] == "protected" for item in segments),
        "chunk_count": len(chunks),
        "max_chunk_chars": max_chars,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "source_is_immutable": True,
            "no_facsimile": True,
                "languages": ["en", "ja"],
            "semantic_review_required": True,
            "protected_objects": ["figures", "equations", "references", "labels", "numeric_facts"],
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=SOURCE_QUEUE)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--max-chars", type=int, default=7000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.max_chars < 1500:
        parser.error("--max-chars must be at least 1500")

    selected = set(args.book_id)
    tasks = [task for task in source_tasks(args.queue) if not selected or task["book_id"] in selected]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_ROOT / "tasks/polish-output.schema.json", output_schema())
    write_json(OUTPUT_ROOT / "tasks/semantic-review.schema.json", reviewer_schema())
    queue_rows: list[dict] = []
    for index, task in enumerate(tasks, start=1):
        manifest = prepare_book(task, max_chars=args.max_chars, force=args.force)
        queue_rows.append(
            {
                "order": index,
                "book_id": task["book_id"],
                "title": task.get("title", task["book_id"]),
                "chunk_count": manifest["chunk_count"],
                "manifest": str((OUTPUT_ROOT / task["book_id"] / "tasks/manifest.json").relative_to(ROOT)),
            }
        )
        print(
            f"[{index}/{len(tasks)}] {task['book_id']}: "
            f"segments={manifest['segment_count']} review={manifest['review_segment_count']} "
            f"chunks={manifest['chunk_count']}",
            flush=True,
        )
    write_json(
        OUTPUT_ROOT / "tasks/queue.json",
        {
            "schema_version": 1,
            "model": "gpt-5.6-sol",
            "reasoning": "low",
            "books": queue_rows,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
