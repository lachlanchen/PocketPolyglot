#!/usr/bin/env python3
"""Assemble the additive Sanguozhi + Pei Songzhi commentary edition."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from codex_trilingual_plain_json_worker import tokenize_en, tokenize_ja, tokenize_zh
from validate_quadrilingual_interlinear_json import validate_chunk


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def chapter_map(book: dict[str, Any]) -> "OrderedDict[int, dict[str, Any]]":
    chapters: "OrderedDict[int, dict[str, Any]]" = OrderedDict()
    for chapter in book.get("chapters", []):
        number = int(chapter.get("number") or 0)
        chapters[number] = chapter
    return chapters


def load_valid_pei_chunks(
    *,
    chunks_jsonl: Path,
    chunk_dir: Path,
    allow_missing: bool,
) -> tuple[dict[int, list[dict[str, Any]]], list[str], list[dict[str, Any]]]:
    sources = load_jsonl(chunks_jsonl)
    by_id = {source["chunk_id"]: source for source in sources}
    grouped: dict[int, list[dict[str, Any]]] = {}
    missing: list[str] = []
    stale: list[dict[str, Any]] = []
    for source in sources:
        chunk_id = source["chunk_id"]
        path = chunk_dir / f"{chunk_id}.json"
        if not path.exists():
            if allow_missing:
                missing.append(chunk_id)
                continue
            raise FileNotFoundError(path)
        data = load_json(path)
        errors = validate_chunk(by_id[chunk_id], data)
        if errors:
            if allow_missing:
                stale.append({"chunk_id": chunk_id, "errors": errors[:40]})
                continue
            raise ValueError(f"{path}: " + "; ".join(errors[:40]))
        grouped.setdefault(int(source["chapter_number"]), []).extend(data.get("paragraphs", []))
    return grouped, missing, stale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-book-json", default="books/sanguozhi/work/quadrilingual/preview/sanguozhi.partial.json")
    parser.add_argument("--pei-manifest", default="data/source-plan/sanguozhi-pei-zhu-maintext/manifest.json")
    parser.add_argument("--pei-chunks-jsonl", default="data/source-plan/sanguozhi-pei-zhu-maintext/chunks.jsonl")
    parser.add_argument("--pei-chunk-dir", default="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/interlinear/chunks")
    parser.add_argument("--output", default="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/preview/sanguozhi-pei-zhu.partial.json")
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    current_book = load_json(ROOT / args.current_book_json)
    pei_manifest = load_json(ROOT / args.pei_manifest)
    pei_by_chapter, missing, stale = load_valid_pei_chunks(
        chunks_jsonl=ROOT / args.pei_chunks_jsonl,
        chunk_dir=ROOT / args.pei_chunk_dir,
        allow_missing=args.allow_missing,
    )

    title_wenyan = "三國志裴松之注"
    title_zh = "三国志裴松之注"
    title_ja = "三国志裴松之注"
    title_en = "Records of the Three Kingdoms with Pei Songzhi Commentary"
    assembled_chapters: list[dict[str, Any]] = []
    used_pei = 0
    for number, chapter in chapter_map(current_book).items():
        new_chapter = {
            "id": chapter.get("id"),
            "number": number,
            "title": chapter.get("title", {}),
            "paragraphs": list(chapter.get("paragraphs", [])),
        }
        pei_paragraphs = pei_by_chapter.get(number, [])
        if pei_paragraphs:
            new_chapter["paragraphs"].extend(pei_paragraphs)
            used_pei += len(pei_paragraphs)
        assembled_chapters.append(new_chapter)

    book = {
        "schema_version": "0.1",
        "mode": "quadrilingual_wenyan_main",
        "title": {
            "wenyan": tokenize_zh(title_wenyan),
            "zh_modern": tokenize_zh(title_zh),
            "ja_modern": tokenize_ja(title_ja),
            "en": tokenize_en(title_en),
        },
        "author": {
            "name": "陳壽／裴松之",
            "reading_zh": "chén shòu / péi sōng zhī",
            "reading_ja": "ちん じゅ／はい しょうし",
        },
        "source": {
            "source_paths": {
                "base_chenshou_current_json": args.current_book_json,
                "pei_manifest": args.pei_manifest,
                "pei_chunks_jsonl": args.pei_chunks_jsonl,
                "pei_chunk_dir": args.pei_chunk_dir,
            },
            "base_book_id": "sanguozhi",
            "book_id": "sanguozhi-pei-zhu",
            "base_policy": "Existing Chen Shou quadrilingual JSON is reused read-only.",
            "pei_policy": "Pei Songzhi commentary chunks are appended as additional wenyan main-text paragraphs in each matching chapter.",
            "pei_total_chunk_count": pei_manifest.get("chunk_count"),
            "pei_used_paragraph_count": used_pei,
            "pei_missing_chunk_count": len(missing),
            "pei_missing_chunks": missing,
            "pei_stale_chunk_count": len(stale),
            "pei_stale_chunks": stale,
        },
        "chapters": assembled_chapters,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT))
    print(f"pei_used_paragraphs={used_pei} missing={len(missing)} stale={len(stale)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
