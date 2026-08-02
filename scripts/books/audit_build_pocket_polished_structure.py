#!/usr/bin/env python3
"""Audit polished technical books for dropped prose and render regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pocket_polished_common import (
    OUTPUT_ROOT,
    ROOT,
    protected_segment_structure_issues,
    read_json,
    read_jsonl,
    validate_chunk_output,
    write_json,
)


DEFAULT_QUEUE = ROOT / "data/source-plan/technical-exact-polished-queue.json"


def queue_book_ids(path: Path) -> list[str]:
    payload = read_json(path)
    rows = payload.get("tasks") or payload.get("books") or []
    return [
        row["book_id"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("book_id"), str)
    ]


def audit_book(
    book_id: str,
    *,
    require_complete: bool,
    max_protected_chars: int,
    max_protected_prose_words: int,
    max_overfull_pt: float,
) -> dict[str, Any]:
    root = OUTPUT_ROOT / book_id
    errors: list[str] = []
    warnings: list[str] = []
    segments_path = root / "source/segments.jsonl"
    tasks_path = root / "tasks/chunks.jsonl"
    status_path = root / "status.json"

    if not segments_path.is_file():
        errors.append("missing source/segments.jsonl")
        segments: list[dict[str, Any]] = []
    else:
        segments = read_jsonl(segments_path)
        for issue in protected_segment_structure_issues(
            segments,
            max_protected_chars=max_protected_chars,
            max_protected_prose_words=max_protected_prose_words,
        ):
            message = f"{issue['code']}:{issue['segment_id']}"
            if issue.get("severity") == "error":
                errors.append(message)
            else:
                warnings.append(message)

    valid_chunks = 0
    total_chunks = 0
    if not tasks_path.is_file():
        errors.append("missing tasks/chunks.jsonl")
    else:
        tasks = read_jsonl(tasks_path)
        total_chunks = len(tasks)
        for task in tasks:
            output = root / "json" / f"{task['chunk_id']}.json"
            try:
                candidate = read_json(output)
                chunk_errors = validate_chunk_output(task, candidate)
            except (OSError, ValueError, json.JSONDecodeError):
                chunk_errors = ["missing or unreadable"]
            if not chunk_errors:
                valid_chunks += 1
        if require_complete and valid_chunks != total_chunks:
            errors.append(f"chunk coverage {valid_chunks}/{total_chunks}")

    status: dict[str, Any] = {}
    if status_path.is_file():
        try:
            payload = read_json(status_path)
            if isinstance(payload, dict):
                status = payload
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append("unreadable status.json")
    elif require_complete:
        errors.append("missing status.json")

    if require_complete and status.get("status") != "complete":
        errors.append(f"assembly status {status.get('status', 'missing')}")
    coverage = status.get("heading_secondary_coverage") or {}
    expected = int(coverage.get("expected_japanese_heading_bodies", 0) or 0)
    matched = int(coverage.get("matched_japanese_heading_bodies", 0) or 0)
    if matched != expected:
        errors.append(f"Japanese heading-body coverage {matched}/{expected}")
    if status and not status.get("source_inventory_verified", False):
        errors.append("source object inventory is not verified")

    reports = status.get("reports") or {}
    if require_complete and not reports:
        errors.append("missing compiled variant report")
    for variant, report in reports.items():
        if not isinstance(report, dict):
            errors.append(f"{variant}: malformed compile report")
            continue
        if not report.get("objects_complete", False):
            errors.append(f"{variant}: incomplete figure/object inventory")
        if not report.get("searchable_text_present", False):
            errors.append(f"{variant}: searchable text missing")
        missing = int((report.get("figure_inventory") or {}).get("missing_count", 0) or 0)
        if missing:
            errors.append(f"{variant}: {missing} missing figures")
        latex_errors = report.get("latex_error_markers") or []
        if latex_errors:
            errors.append(f"{variant}: {len(latex_errors)} LaTeX errors")
        missing_glyphs = report.get("missing_character_markers") or []
        if missing_glyphs:
            errors.append(f"{variant}: {len(missing_glyphs)} missing glyph warnings")
        worst = float(report.get("worst_overfull_pt", 0) or 0)
        if worst > max_overfull_pt:
            errors.append(f"{variant}: overfull {worst:.2f}pt")
        if require_complete and not report.get("layout_clean", False):
            errors.append(f"{variant}: layout not clean")

    return {
        "book_id": book_id,
        "ok": not errors,
        "valid_chunks": valid_chunks,
        "total_chunks": total_chunks,
        "segment_count": len(segments),
        "heading_bodies_expected": expected,
        "heading_bodies_matched": matched,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--max-protected-chars", type=int, default=8000)
    parser.add_argument("--max-protected-prose-words", type=int, default=120)
    parser.add_argument("--max-overfull-pt", type=float, default=2.0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    book_ids = args.book_id or queue_book_ids(args.queue)
    rows = [
        audit_book(
            book_id,
            require_complete=args.require_complete,
            max_protected_chars=args.max_protected_chars,
            max_protected_prose_words=args.max_protected_prose_words,
            max_overfull_pt=args.max_overfull_pt,
        )
        for book_id in book_ids
    ]
    print("book_id\tchunks\theading_bodies\twarnings\tresult")
    for row in rows:
        result = "OK" if row["ok"] else "FAIL: " + "; ".join(row["errors"])
        print(
            f"{row['book_id']}\t{row['valid_chunks']}/{row['total_chunks']}\t"
            f"{row['heading_bodies_matched']}/{row['heading_bodies_expected']}\t"
            f"{len(row['warnings'])}\t{result}"
        )
    if args.json:
        write_json(
            args.json,
            {
                "schema_version": 1,
                "ok": all(row["ok"] for row in rows),
                "books": rows,
            },
        )
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
