#!/usr/bin/env python3
"""Repair structural main-text spans in the Zizhi Tongjian comment sidecar.

The primary sidecar is inferred from the PDF font layer.  That works well for
inline Hu Sanxing notes, but the source edition also prints prefaces, repeated
volume headings, author/title lines, and colophon material in small type.  These
are still source text, not Hu-style comments.  This post-pass keeps the expensive
language JSON intact and only repairs the sidecar classification.
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

MAIN = "main"

STRUCTURAL_DYNASTY_RE = re.compile(
    r"^(?:後梁|後唐|後晉|後漢|後周|周|秦|漢|魏|晉|宋|齊|梁|陳|隋|唐)"
    r"紀[一二三四五六七八九十百〇零]+"
)
PUNCT_RE = re.compile(r"[。！？；：:「」『』]")
OFFICIAL_TITLE_MARKERS = (
    "大夫",
    "學士",
    "学士",
    "御使",
    "御史",
    "知制誥",
    "侍講",
    "上護軍",
    "賜紫金魚袋",
    "開國",
    "食邑",
    "端明殿",
    "翰林",
)
PROTECTED_TITLES = {
    "胡刻通鑑正文校宋記述略",
    "新註資治通鑑序",
    "興文署新刊資治通鑑序",
    "宋神宗資治通鑑序 禦製",
    "通鑑電子化校勘紀略",
    "《通鑑》電子化之用字說明",
    "《通鑑》電子化校勘人姓名",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sidecar_key(paragraph_id: str, unit_index: int) -> str:
    return f"{paragraph_id}#{unit_index:04d}"


def one_main_span(text: str, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "start": 0,
            "end": len(text),
            "kind": MAIN,
            "confidence": 1.0,
            "method": reason,
            "sample": text[:80],
        }
    ]


def is_official_title_line(text: str) -> bool:
    stripped = " ".join(text.split())
    if not stripped or len(stripped) > 90 or PUNCT_RE.search(stripped):
        return False
    return "臣" in stripped and any(marker in stripped for marker in OFFICIAL_TITLE_MARKERS)


def is_author_or_commentator_heading(text: str) -> bool:
    stripped = " ".join(text.split())
    if "司馬光" in stripped and "奉敕" in stripped:
        return True
    if "胡三省" in stripped and ("註" in stripped or "注" in stripped) and len(stripped) <= 32:
        return True
    return False


def is_dynasty_range_heading(text: str) -> bool:
    return bool(STRUCTURAL_DYNASTY_RE.search(" ".join(text.split())))


def first_chunk_by_chapter(chunks: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
        try:
            number = int(chunk.get("chapter_number") or 0)
        except (TypeError, ValueError):
            continue
        result.setdefault(number, chunk)
    return result


def iter_units(chunk: dict[str, Any]) -> list[tuple[str, int, str]]:
    units: list[tuple[str, int, str]] = []
    for paragraph in chunk.get("paragraphs", []):
        paragraph_id = str(paragraph.get("id", ""))
        for unit_index, unit in enumerate(paragraph.get("units", [])):
            units.append((paragraph_id, unit_index, str(unit.get("source_wenyan", ""))))
    return units


def build_metadata(
    chunks_jsonl: Path,
    chunk_dir: Path,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    chunks = load_jsonl(chunks_jsonl)
    key_meta: dict[str, dict[str, Any]] = {}
    structural_heading_keys: set[str] = set()
    first_chunks = first_chunk_by_chapter(chunks)

    for source in chunks:
        chunk_id = str(source["chunk_id"])
        chunk_path = chunk_dir / f"{chunk_id}.json"
        if not chunk_path.exists():
            continue
        chunk_data = load_json(chunk_path)
        chapter_number = int(source.get("chapter_number") or 0)
        chapter_title = str(source.get("chapter_title_wenyan") or "")
        for paragraph_id, unit_index, source_text in iter_units(chunk_data):
            key = sidecar_key(paragraph_id, unit_index)
            key_meta[key] = {
                "chunk_id": chunk_id,
                "chapter_number": chapter_number,
                "chapter_title_wenyan": chapter_title,
            }

    for chapter_number, source in first_chunks.items():
        if chapter_number < 5 or chapter_number > 298:
            continue
        chunk_path = chunk_dir / f"{source['chunk_id']}.json"
        if not chunk_path.exists():
            continue
        seen_range = False
        for paragraph_id, unit_index, source_text in iter_units(load_json(chunk_path))[:12]:
            key = sidecar_key(paragraph_id, unit_index)
            if (
                is_official_title_line(source_text)
                or is_author_or_commentator_heading(source_text)
                or is_dynasty_range_heading(source_text)
            ):
                structural_heading_keys.add(key)
                if is_dynasty_range_heading(source_text):
                    seen_range = True
            elif seen_range:
                break
    return key_meta, structural_heading_keys


def force_main_reason(
    record: dict[str, Any],
    meta: dict[str, Any],
    structural_heading_keys: set[str],
    appendix_started: bool,
) -> str | None:
    key = str(record["key"])
    text = str(record.get("source_wenyan", ""))
    chapter_number = int(meta.get("chapter_number") or 0)
    chapter_title = str(meta.get("chapter_title_wenyan") or "")

    if chapter_title in PROTECTED_TITLES or chapter_number in {1, 2, 3, 4, 299, 300, 301}:
        return "manual-preface-or-editorial-main"
    if key in structural_heading_keys:
        return "manual-volume-heading-main"
    if appendix_started and chapter_number == 298:
        return "manual-postscript-main"
    if is_author_or_commentator_heading(text) or is_dynasty_range_heading(text):
        return "manual-structural-heading-main"
    return None


def rewrite_sidecar(
    *,
    sidecar: Path,
    chunks_jsonl: Path,
    chunk_dir: Path,
    report_path: Path,
    backup: bool,
) -> dict[str, Any]:
    key_meta, structural_heading_keys = build_metadata(chunks_jsonl, chunk_dir)
    records = load_jsonl(sidecar)
    original_text = sidecar.read_text(encoding="utf-8")
    if backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(sidecar, sidecar.with_name(f"{sidecar.name}.bak-{stamp}"))

    counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    appendix_started = False
    rewritten: list[str] = []
    for record in records:
        text = str(record.get("source_wenyan", ""))
        if "進書表臣光言" in text:
            appendix_started = True
        meta = key_meta.get(str(record["key"]), {})
        reason = force_main_reason(record, meta, structural_heading_keys, appendix_started)
        if reason and any(span.get("kind") != MAIN for span in record.get("spans", [])):
            counts[reason] += 1
            if len(examples) < 80:
                examples.append(
                    {
                        "key": record["key"],
                        "chunk_id": record.get("chunk_id"),
                        "chapter_number": meta.get("chapter_number"),
                        "chapter_title_wenyan": meta.get("chapter_title_wenyan"),
                        "reason": reason,
                        "source_wenyan": text[:180],
                        "old_spans": record.get("spans", [])[:6],
                    }
                )
            record["spans"] = one_main_span(text, reason)
        elif reason:
            counts[f"{reason}:already-main"] += 1
        rewritten.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    new_text = "\n".join(rewritten) + "\n"
    changed = new_text != original_text
    if changed:
        sidecar.write_text(new_text, encoding="utf-8")

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sidecar": str(sidecar),
        "chunks_jsonl": str(chunks_jsonl),
        "chunk_dir": str(chunk_dir),
        "changed": changed,
        "records": len(records),
        "structural_heading_keys": len(structural_heading_keys),
        "rewrite_counts": dict(counts),
        "examples": examples,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    report = rewrite_sidecar(
        sidecar=Path(args.sidecar),
        chunks_jsonl=Path(args.chunks_jsonl),
        chunk_dir=Path(args.chunk_dir),
        report_path=Path(args.report),
        backup=args.backup,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
