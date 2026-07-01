#!/usr/bin/env python3
"""Audit and prune source/license boilerplate chunks from book manifests.

The multilingual pipeline should not render Wikisource public-domain notices,
publisher copyright lines, redirect stubs, or Project Gutenberg boilerplate as
book content.  This tool scans actual content/task records, reports matching
chunks, and optionally removes those records from the manifests that drive
assembly while keeping old generated JSON files in place for provenance.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]


BOILERPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "wikisource_public_domain_zh",
        re.compile(
            r"(此(?:[^，。；;]{0,12})?作品在全世界都[属屬][于於]公有领域|"
            r"作者逝世已经超过\s*100\s*年|于\s*1931年1月1日之前出版)"
        ),
    ),
    (
        "wikisource_public_domain_en",
        re.compile(r"(This work is in the public domain worldwide|author died more than 100 years ago|published before January 1, 1931)", re.I),
    ),
    (
        "wikisource_public_domain_ja",
        re.compile(r"(この作品は.*パブリックドメイン|作者の没後.*100年)", re.I),
    ),
    (
        "publisher_license_zh",
        re.compile(r"(本书由.*提供授权|版权所有[·・]?\s*侵权必究|版權所有[·・]?\s*侵權必究)"),
    ),
    (
        "publisher_license_en",
        re.compile(r"(This book is licensed by|All rights reserved; infringement will be prosecuted)", re.I),
    ),
    (
        "project_gutenberg_boilerplate",
        re.compile(r"(Project Gutenberg|This eBook is for the use of anyone anywhere|Produced by .*Distributed Proofreaders)", re.I),
    ),
    (
        "redirect_stub",
        re.compile(r"^\s*#\s*(?:重定向|redirect)\b", re.I),
    ),
)


CONTENT_KEYS = {
    "text",
    "source_text",
    "source_wenyan",
    "source_zh",
    "source_ja",
    "source_en",
    "wenyan",
    "zh",
    "zh_modern",
    "ja",
    "ja_modern",
    "en",
    "modern_zh",
    "modern_ja",
    "modern_en",
    "t",
}


@dataclass(frozen=True)
class Match:
    kind: str
    text: str
    field: str


@dataclass
class PruneResult:
    group: str
    book_id: str
    path: Path
    manifest: Path | None
    pruned_ids: list[str]
    matches: dict[str, list[Match]]
    backup_paths: list[Path]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def backup(path: Path, stamp: str) -> Path:
    target = path.with_suffix(path.suffix + f".bak-{stamp}-boilerplate")
    shutil.copy2(path, target)
    return target


def compact(text: str, *, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def iter_content_strings(value: Any, field: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            next_field = f"{field}.{key}" if field else str(key)
            if key in CONTENT_KEYS:
                yield from iter_leaf_strings(child, next_field)
            else:
                yield from iter_content_strings(child, next_field)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_content_strings(child, f"{field}[{index}]")


def iter_source_content_strings(record: dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Yield likely book-content strings without traversing large token trees.

    Source manifests are large and may contain reference metadata.  For pruning
    source/license boilerplate we only need paragraph/unit body fields.
    """
    direct_keys = CONTENT_KEYS - {"t"}
    for key in direct_keys:
        value = record.get(key)
        if isinstance(value, str):
            yield key, value

    for index, paragraph in enumerate(record.get("paragraphs") or []):
        if not isinstance(paragraph, dict):
            continue
        for key in direct_keys:
            value = paragraph.get(key)
            if isinstance(value, str):
                yield f"paragraphs[{index}].{key}", value

    for index, unit in enumerate(record.get("units") or []):
        if not isinstance(unit, dict):
            continue
        for key in direct_keys:
            value = unit.get(key)
            if isinstance(value, str):
                yield f"units[{index}].{key}", value
            elif key in {"en", "zh", "ja", "wenyan", "zh_modern", "ja_modern"} and isinstance(value, list):
                for token_index, token in enumerate(value):
                    if isinstance(token, dict) and isinstance(token.get("t"), str):
                        yield f"units[{index}].{key}[{token_index}].t", token["t"]


def iter_leaf_strings(value: Any, field: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, dict):
        for key, child in value.items():
            next_field = f"{field}.{key}"
            if key in CONTENT_KEYS or isinstance(child, (dict, list)):
                yield from iter_leaf_strings(child, next_field)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_leaf_strings(child, f"{field}[{index}]")


def matches_boilerplate(record: dict[str, Any]) -> list[Match]:
    matches: list[Match] = []
    for field, value in iter_content_strings(record):
        for kind, regex in BOILERPLATE_PATTERNS:
            if regex.search(value):
                matches.append(Match(kind=kind, text=compact(value), field=field))
                break
    return matches


def matches_source_boilerplate(record: dict[str, Any]) -> list[Match]:
    matches: list[Match] = []
    for field, value in iter_source_content_strings(record):
        for kind, regex in BOILERPLATE_PATTERNS:
            if regex.search(value):
                matches.append(Match(kind=kind, text=compact(value), field=field))
                break
    return matches


def record_id(record: dict[str, Any]) -> str:
    for key in ("chunk_id", "id", "task_id"):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def manifest_chunk_ids(manifest: dict[str, Any]) -> list[str]:
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        return []
    ids: list[str] = []
    for item in chunks:
        if isinstance(item, dict):
            chunk_id = item.get("chunk_id") or item.get("id")
        else:
            chunk_id = item
        if chunk_id:
            ids.append(str(chunk_id))
    return ids


def filter_manifest(manifest: dict[str, Any], remove_ids: set[str]) -> dict[str, Any]:
    chunks = manifest.get("chunks")
    if isinstance(chunks, list):
        filtered = []
        for item in chunks:
            chunk_id = item.get("chunk_id") if isinstance(item, dict) else item
            if str(chunk_id) not in remove_ids:
                filtered.append(item)
        manifest["chunks"] = filtered
        manifest["chunk_count"] = len(filtered)
    elif "chunk_count" in manifest:
        manifest["chunk_count"] = max(0, int(manifest.get("chunk_count") or 0) - len(remove_ids))
    return manifest


def book_id_from_chunks_path(path: Path) -> str:
    parts = path.parts
    if "books" in parts:
        idx = parts.index("books")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return path.parent.name


def audit_chunks_jsonl(path: Path, *, apply: bool, stamp: str) -> PruneResult | None:
    matches_by_id: dict[str, list[Match]] = {}
    remove_ids: set[str] = set()
    line_count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            line_count += 1
            row = json.loads(line)
            rid = record_id(row)
            found = matches_source_boilerplate(row)
            if found and rid:
                remove_ids.add(rid)
                matches_by_id[rid] = found
    if not remove_ids:
        return None

    manifest = path.with_name("manifest.json")
    backups: list[Path] = []
    if apply:
        backups.append(backup(path, stamp))
        tmp = path.with_suffix(path.suffix + f".tmp-{stamp}")
        with path.open(encoding="utf-8") as source, tmp.open("w", encoding="utf-8") as target:
            for line in source:
                if not line.strip():
                    continue
                row = json.loads(line)
                if record_id(row) not in remove_ids:
                    target.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(path)
        if manifest.exists():
            backups.append(backup(manifest, stamp))
            data = filter_manifest(load_json(manifest), remove_ids)
            data.setdefault("pruned_boilerplate_chunks", [])
            now = datetime.now(timezone.utc).isoformat()
            for chunk_id in sorted(remove_ids):
                data["pruned_boilerplate_chunks"].append(
                    {
                        "chunk_id": chunk_id,
                        "pruned_at": now,
                        "reason": "source/license boilerplate detected",
                        "matches": [
                            {"kind": match.kind, "field": match.field, "text": match.text}
                            for match in matches_by_id[chunk_id]
                        ],
                    }
                )
            write_json(manifest, data)

    return PruneResult(
        group="source_chunks",
        book_id=book_id_from_chunks_path(path),
        path=path,
        manifest=manifest if manifest.exists() else None,
        pruned_ids=sorted(remove_ids),
        matches=matches_by_id,
        backup_paths=backups,
    )


def candidate_paths_from_task(task: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("base_chunk_candidates", "overlay_candidates", "chunk_candidates", "source_candidates"):
        value = task.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    paths.append(ROOT / item)
    for key in ("base_chunk", "overlay_chunk", "chunk_path", "source_chunk"):
        value = task.get(key)
        if isinstance(value, str):
            paths.append(ROOT / value)
    return paths


def audit_overlay_tasks(path: Path, *, apply: bool, stamp: str) -> PruneResult | None:
    tasks = load_jsonl(path)
    matches_by_id: dict[str, list[Match]] = {}
    remove_ids: set[str] = set()
    for task in tasks:
        tid = record_id(task)
        found = matches_boilerplate(task)
        for candidate in candidate_paths_from_task(task):
            if candidate.exists() and candidate.suffix == ".json":
                try:
                    found.extend(matches_boilerplate(load_json(candidate)))
                except (OSError, json.JSONDecodeError):
                    pass
        if found and tid:
            remove_ids.add(tid)
            matches_by_id[tid] = found
    if not remove_ids:
        return None

    manifest = path.with_name("manifest.json")
    backups: list[Path] = []
    if apply:
        backups.append(backup(path, stamp))
        write_jsonl(path, [task for task in tasks if record_id(task) not in remove_ids])
        if manifest.exists():
            backups.append(backup(manifest, stamp))
            data = filter_manifest(load_json(manifest), remove_ids)
            data.setdefault("pruned_boilerplate_tasks", [])
            now = datetime.now(timezone.utc).isoformat()
            for task_id in sorted(remove_ids):
                data["pruned_boilerplate_tasks"].append(
                    {
                        "task_id": task_id,
                        "pruned_at": now,
                        "reason": "source/license boilerplate detected",
                        "matches": [
                            {"kind": match.kind, "field": match.field, "text": match.text}
                            for match in matches_by_id[task_id]
                        ],
                    }
                )
            write_json(manifest, data)

    book_id = path.parent.name
    return PruneResult(
        group="overlay_tasks",
        book_id=book_id,
        path=path,
        manifest=manifest if manifest.exists() else None,
        pruned_ids=sorted(remove_ids),
        matches=matches_by_id,
        backup_paths=backups,
    )


def discover_chunk_jsonls(book_filter: set[str]) -> list[Path]:
    paths = sorted(ROOT.glob("books/*/work/**/chunks/chunks.jsonl"))
    if book_filter:
        paths = [path for path in paths if book_id_from_chunks_path(path) in book_filter]
    return paths


def discover_overlay_tasks(book_filter: set[str]) -> list[Path]:
    paths = sorted(ROOT.glob("data/source-plan/*/*/tasks.jsonl"))
    if book_filter:
        paths = [path for path in paths if path.parent.name in book_filter]
    return paths


def write_report(results: list[PruneResult], *, apply: bool, stamp: str) -> Path:
    report = ROOT / "references" / f"BOILERPLATE_CHUNK_AUDIT_{stamp}.md"
    lines = [
        f"# Boilerplate Chunk Audit - {stamp}",
        "",
        f"Mode: {'apply' if apply else 'dry-run'}",
        "",
        "This report lists chunks/tasks whose actual book content matched source",
        "or license boilerplate patterns. The cleanup removes only manifest/task",
        "records; generated chunk files are left in place as provenance.",
        "",
    ]
    if not results:
        lines.extend(["No book-content boilerplate matches were found.", ""])
    by_book: dict[str, list[PruneResult]] = defaultdict(list)
    for result in results:
        by_book[result.book_id].append(result)
    for book_id in sorted(by_book):
        lines.extend([f"## {book_id}", ""])
        for result in by_book[book_id]:
            lines.append(f"- `{result.group}` `{result.path.relative_to(ROOT)}`")
            if result.manifest:
                lines.append(f"  - manifest: `{result.manifest.relative_to(ROOT)}`")
            lines.append(f"  - pruned: {len(result.pruned_ids)}")
            if result.backup_paths:
                for backup_path in result.backup_paths:
                    lines.append(f"  - backup: `{backup_path.relative_to(ROOT)}`")
            for item_id in result.pruned_ids[:40]:
                samples = result.matches.get(item_id, [])
                sample = samples[0] if samples else Match("", "", "")
                lines.append(f"  - `{item_id}`: {sample.kind} `{sample.field}` - {sample.text}")
            if len(result.pruned_ids) > 40:
                lines.append(f"  - ... {len(result.pruned_ids) - 40} more")
            lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", default=[], help="Limit to a book id. Repeatable.")
    parser.add_argument("--apply", action="store_true", help="Rewrite matching manifests/tasks after backups.")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    book_filter = set(args.book)
    results: list[PruneResult] = []
    for path in discover_chunk_jsonls(book_filter):
        result = audit_chunks_jsonl(path, apply=args.apply, stamp=stamp)
        if result:
            results.append(result)
    for path in discover_overlay_tasks(book_filter):
        result = audit_overlay_tasks(path, apply=args.apply, stamp=stamp)
        if result:
            results.append(result)

    total = sum(len(result.pruned_ids) for result in results)
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    print(f"affected_books={len({result.book_id for result in results})}")
    print(f"affected_records={total}")
    for result in results:
        ids = ", ".join(result.pruned_ids[:8])
        suffix = "" if len(result.pruned_ids) <= 8 else f", ... +{len(result.pruned_ids) - 8}"
        print(f"{result.book_id}: {result.group} {len(result.pruned_ids)} [{ids}{suffix}]")
    if not args.no_report:
        report = write_report(results, apply=args.apply, stamp=stamp)
        print(f"report={report.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
