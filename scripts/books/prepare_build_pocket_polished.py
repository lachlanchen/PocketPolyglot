#!/usr/bin/env python3
"""Prepare lossless page/chunk tasks for build-pocket-polished editions."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from pocket_polished_common import (
    OUTPUT_ROOT,
    ROOT,
    SOURCE_QUEUE,
    apply_exact_paragraph_drops,
    apply_exact_text_replacements,
    detect_source_language,
    make_review_chunks,
    normalize_page_boundary_artifacts,
    normalize_split_prose_paragraphs,
    output_schema,
    read_json,
    reviewer_schema,
    sha256_text,
    source_english_writer_schema,
    source_tasks,
    split_tex_segments,
    write_json,
    write_jsonl,
)


INPUT_RE = re.compile(r"\\input\{(?P<path>[^{}]+)\}")


def source_paths(task: dict) -> tuple[Path, Path | None]:
    if task.get("source_exact_tex"):
        exact = ROOT / task["source_exact_tex"]
    else:
        exact = ROOT / "build-pocket" / task["book_id"] / "exact/tex/book.tex"
    body = ROOT / task["source_body_tex"] if task.get("source_body_tex") else None
    return exact, body


def flatten_source(task: dict, destination: Path) -> tuple[str, Path, Path | None]:
    exact, body = source_paths(task)
    if not exact.exists():
        raise FileNotFoundError(f"missing exact source TeX: {exact}")
    text = exact.read_text(encoding="utf-8", errors="strict")
    if body is not None:
        if not body.exists():
            raise FileNotFoundError(f"missing source body TeX: {body}")
        body_text = body.read_text(encoding="utf-8", errors="strict")
        matches = list(INPUT_RE.finditer(text))
        matching = [
            match
            for match in matches
            if (ROOT / match.group("path")).resolve() == body.resolve()
        ]
        if len(matching) != 1:
            raise ValueError(
                f"expected one input of {body.relative_to(ROOT)} in {exact.relative_to(ROOT)}, "
                f"found {len(matching)}"
            )
        match = matching[0]
        text = text[: match.start()] + body_text + text[match.end() :]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return text, exact, body


def source_replacement_rules(task: dict) -> list[dict]:
    """Load task-local evidence repairs without embedding them in shared code."""

    rules = list(task.get("polish_source_replacements", []))
    plan_name = task.get("polish_source_replacements_file")
    if not plan_name:
        return rules
    plan_path = ROOT / str(plan_name)
    payload = read_json(plan_path)
    file_rules = payload.get("replacements") if isinstance(payload, dict) else None
    if not isinstance(file_rules, list):
        raise ValueError(f"source replacement plan has no replacements array: {plan_path}")
    rules.extend(file_rules)
    return rules


def prepare_book(
    task: dict,
    *,
    max_chars: int,
    max_segments: int,
    force: bool,
) -> dict:
    book_id = task["book_id"]
    book_root = OUTPUT_ROOT / book_id
    manifest_path = book_root / "tasks/manifest.json"
    source_tex = book_root / "source/exact-flattened.tex"
    upstream_flattened = book_root / "source/upstream-exact-flattened.tex"
    upstream_text, upstream_exact, upstream_body = flatten_source(
        task, upstream_flattened
    )
    source_text, source_normalizations = normalize_page_boundary_artifacts(
        upstream_text
    )
    source_text, configured_normalizations = apply_exact_paragraph_drops(
        source_text,
        task.get("polish_source_normalizations", []),
    )
    source_normalizations.extend(configured_normalizations)
    source_text, configured_replacements = apply_exact_text_replacements(
        source_text,
        source_replacement_rules(task),
    )
    source_normalizations.extend(configured_replacements)
    source_text, prose_join_normalizations = normalize_split_prose_paragraphs(
        source_text
    )
    source_normalizations.extend(prose_join_normalizations)
    source_tex.parent.mkdir(parents=True, exist_ok=True)
    source_tex.write_text(source_text, encoding="utf-8")
    write_json(
        book_root / "source/normalizations.json",
        {
            "schema_version": 1,
            "upstream_sha256": sha256_text(upstream_text),
            "polish_input_sha256": sha256_text(source_text),
            "changes": source_normalizations,
        },
    )
    source_hash = sha256_text(source_text)
    validation_profile = task.get("validation_profile", "prose_exact")
    source_language = detect_source_language(
        source_text,
        validation_profile=validation_profile,
    )
    if manifest_path.exists() and not force:
        current = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
        if (
            current.get("source_tex_sha256") == source_hash
            and current.get("max_chunk_chars") == max_chars
            and current.get("max_chunk_segments") == max_segments
            and current.get("validation_profile", "prose_exact") == validation_profile
            and current.get("pipeline_schema_version") == 3
        ):
            return current

    segments = split_tex_segments(
        source_text,
        book_id,
        validation_profile=validation_profile,
    )
    chunks = make_review_chunks(
        segments,
        book_id=book_id,
        title=task.get("title", book_id),
        source=task["source"],
        source_language=source_language,
        max_chars=max_chars,
        max_segments=max_segments,
        validation_profile=validation_profile,
    )
    for chunk in chunks:
        chunk["validation_profile"] = validation_profile
    write_jsonl(book_root / "source/segments.jsonl", segments)
    write_jsonl(book_root / "tasks/chunks.jsonl", chunks)
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "title": task.get("title", book_id),
        "author": task.get("author", ""),
        "source": task["source"],
        "source_route": task.get("source_route", "unspecified"),
        "source_cache_immutable": bool(task.get("source_cache_immutable", True)),
        "source_language": source_language,
        "source_exact_tex": str(source_tex.relative_to(ROOT)),
        "upstream_exact_tex": str(upstream_exact.relative_to(ROOT)),
        "upstream_body_tex": (
            str(upstream_body.relative_to(ROOT)) if upstream_body is not None else None
        ),
        "source_tex_sha256": source_hash,
        "upstream_flattened_tex": str(upstream_flattened.relative_to(ROOT)),
        "upstream_flattened_sha256": sha256_text(upstream_text),
        "source_normalization_count": len(source_normalizations),
        "source_replacement_plan": task.get("polish_source_replacements_file"),
        "segment_count": len(segments),
        "review_segment_count": sum(
            item["kind"]
            in (
                {"text", "table", "math"}
                if validation_profile == "technical_exact"
                else {"text", "table"}
            )
            for item in segments
        ),
        "protected_segment_count": sum(item["kind"] == "protected" for item in segments),
        "chunk_count": len(chunks),
        "max_chunk_chars": max_chars,
        "max_chunk_segments": max_segments,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "validation_profile": validation_profile,
        "pipeline_schema_version": 3,
        "policy": {
            "upstream_source_is_immutable": True,
            "polish_input": "evidence-logged-deterministic-normalization",
            "no_facsimile": True,
            "languages": ["en", "ja"],
            "semantic_review_required": True,
            "semantic_review_unit": "segment",
            "translated_numeric_values": "semantic-review",
            "english_source_output": "grounded-repair-patches",
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
    parser.add_argument("--max-segments", type=int, default=16)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output-queue",
        type=Path,
        default=OUTPUT_ROOT / "tasks/queue.json",
        help="Write the runnable prepared queue to this path.",
    )
    args = parser.parse_args()
    if args.max_chars < 1500:
        parser.error("--max-chars must be at least 1500")
    if args.max_segments < 1:
        parser.error("--max-segments must be at least 1")

    available = source_tasks(args.queue)
    if args.book_id:
        by_id = {task["book_id"]: task for task in available}
        missing = [book_id for book_id in args.book_id if book_id not in by_id]
        if missing:
            parser.error(f"unknown --book-id values: {', '.join(missing)}")
        tasks = [by_id[book_id] for book_id in args.book_id]
    else:
        tasks = available
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_ROOT / "tasks/polish-output.schema.json", output_schema())
    write_json(
        OUTPUT_ROOT / "tasks/polish-source-en-output.schema.json",
        source_english_writer_schema(),
    )
    write_json(OUTPUT_ROOT / "tasks/semantic-review.schema.json", reviewer_schema())
    queue_rows: list[dict] = []
    for index, task in enumerate(tasks, start=1):
        manifest = prepare_book(
            task,
            max_chars=args.max_chars,
            max_segments=args.max_segments,
            force=args.force,
        )
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
        args.output_queue,
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
