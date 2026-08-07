#!/usr/bin/env python3
"""Promote reviewed OCR repair audits into a strict parsed-source ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_review_decisions(
    path_value: Path | None,
    *,
    book_id: str,
) -> tuple[dict[tuple[str, str], str], str]:
    if path_value is None:
        return {}, ""
    path = resolve(path_value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("book_id") != book_id:
        raise ValueError(
            "review decisions book_id does not match: "
            f"{payload.get('book_id')!r} != {book_id!r}"
        )
    rejected: dict[tuple[str, str], str] = {}
    for index, item in enumerate(payload.get("rejected_repairs", []), start=1):
        before = str(item.get("before") or "")
        after = str(item.get("after") or "")
        reason = str(item.get("reason") or "").strip()
        if not before or not after or not reason:
            raise ValueError(f"invalid rejected repair {index} in {path}")
        key = (before, after)
        if key in rejected:
            raise ValueError(f"duplicate rejected repair in {path}: {key!r}")
        rejected[key] = reason
    return rejected, display_path(path)


def load_repairs(
    paths: list[Path],
    accepted: set[str],
    rejected: dict[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repairs: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    used_rejections: set[tuple[str, str]] = set()
    rejected_rows: list[dict[str, Any]] = []
    for path_value in paths:
        path = resolve(path_value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("repairs", []):
            confidence = str(item.get("confidence") or "")
            if confidence not in accepted:
                continue
            before = str(item.get("before") or "")
            after = str(item.get("after") or "")
            key = (before, after)
            if key in rejected:
                used_rejections.add(key)
                rejected_rows.append(
                    {
                        "before": before,
                        "after": after,
                        "reason": rejected[key],
                        "audit_path": display_path(path),
                    }
                )
                continue
            if not before or not after or before == after:
                raise ValueError(f"invalid repair in {path}: {item!r}")
            if "\n" in before or "\n" in after:
                raise ValueError(f"multiline parsed repair is not supported: {before!r}")
            previous = seen.get(before)
            if previous is not None:
                if previous != after:
                    raise ValueError(
                        f"conflicting repairs for {before!r}: {previous!r} != {after!r}"
                    )
                continue
            seen[before] = after
            repairs.append(
                {
                    "before": before,
                    "after": after,
                    "category": str(item.get("category") or "other"),
                    "confidence": confidence,
                    "evidence": str(item.get("evidence") or item.get("reason") or "").strip(),
                    "source_pages": item.get("source_pages", []),
                    "audit_path": display_path(path),
                }
            )
    unused = set(rejected) - used_rejections
    if unused:
        formatted = ", ".join(repr(item) for item in sorted(unused))
        raise ValueError(f"review decisions do not match accepted audit candidates: {formatted}")
    return repairs, rejected_rows


def build_ledger(
    *,
    book_id: str,
    source_markdown: Path,
    audit_paths: list[Path],
    accepted: set[str],
    review_decisions: Path | None = None,
) -> dict[str, Any]:
    source_path = resolve(source_markdown)
    source_text = source_path.read_text(encoding="utf-8")
    rejected, decisions_path = load_review_decisions(
        review_decisions,
        book_id=book_id,
    )
    repairs, rejected_rows = load_repairs(audit_paths, accepted, rejected)
    repairs.sort(key=lambda item: len(item["before"]), reverse=True)
    promoted: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in repairs:
        before = item["before"]
        count = source_text.count(before)
        if count < 1:
            covering = next(
                (
                    earlier
                    for earlier in promoted
                    if before in earlier["before"] and item["after"] in earlier["after"]
                ),
                None,
            )
            if covering is not None:
                superseded.append(
                    {
                        **item,
                        "superseded_by_before": covering["before"],
                        "superseded_by_after": covering["after"],
                    }
                )
                continue
            missing.append(before)
            continue
        source_text = source_text.replace(before, item["after"])
        promoted.append({**item, "expected_count": count})
    if missing:
        formatted = "\n".join(f"- {item!r}" for item in missing)
        raise RuntimeError(
            "repair source text is absent after prior exact repairs:\n" + formatted
        )
    return {
        "schema_version": 1,
        "book_id": book_id,
        "stage": "parsed_paragraphs",
        "source_markdown": display_path(source_path),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted_confidences": sorted(accepted),
        "audit_paths": [display_path(resolve(path)) for path in audit_paths],
        "review_decisions": decisions_path,
        "rejected_repairs": rejected_rows,
        "superseded_repairs": superseded,
        "repairs": promoted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--source-markdown", required=True, type=Path)
    parser.add_argument("--audit", required=True, action="append", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--accept-confidence",
        action="append",
        choices=("high", "medium"),
        default=[],
        help="accepted audit confidence; repeat as needed (default: high)",
    )
    args = parser.parse_args()
    accepted = set(args.accept_confidence or ["high"])
    ledger = build_ledger(
        book_id=args.book_id,
        source_markdown=args.source_markdown,
        audit_paths=args.audit,
        accepted=accepted,
        review_decisions=args.review_decisions,
    )
    output = resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={output.relative_to(ROOT)} repairs={len(ledger['repairs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
