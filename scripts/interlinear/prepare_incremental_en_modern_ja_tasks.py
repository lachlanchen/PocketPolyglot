#!/usr/bin/env python3
"""Prepare incremental English and modern-Japanese overlay tasks.

This script does not generate language content. It creates durable task
manifests that tell future workers how to read existing bilingual chunks as
read-only input and write new language layers to separate overlay paths.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "data" / "source-plan" / "incremental-en-modern-ja"
GLOBAL_MANIFEST = ROOT / "data" / "source-plan" / "incremental-english-modern-japanese.json"


@dataclasses.dataclass(frozen=True)
class EnhancementBook:
    book_id: str
    title: str
    category: str
    source_area: str
    add_modern_zh: bool = False
    add_english: bool = True
    add_modern_ja: bool = False
    priority: int = 100
    dependency: str = "base_chunks_exist"
    notes: str = ""


BOOKS: list[EnhancementBook] = [
    EnhancementBook("kokoro", "心 / こころ", "early_bilingual", "sources/kokoro", priority=10),
    EnhancementBook("snow-country", "雪国", "early_bilingual", "sources/snow-country", priority=20),
    EnhancementBook("no-longer-human", "人間失格", "early_bilingual", "sources/no-longer-human", priority=30),
    EnhancementBook("rashomon-stories", "羅生門短篇集", "early_bilingual", "sources/罗生门", priority=40),
    EnhancementBook(
        "sichuan-folk-stories-vol1",
        "中国民间故事集成 四川卷 上",
        "ocr_folk",
        "sources/中国民间故事集成 四川卷 上 10978512.pdf",
        add_modern_ja=True,
        priority=50,
        notes="Use corrected_text when present; generate plain, natural Japanese from the corrected modern Chinese story text.",
    ),
    EnhancementBook("kinkakuji", "金阁寺 / 金閣寺", "early_bilingual", "sources/金阁寺", priority=60),
    EnhancementBook(
        "sishu-jizhu-aginti",
        "四書章句集註",
        "classical_chinese",
        "sources/sishu",
        add_modern_zh=True,
        add_modern_ja=True,
        priority=70,
        notes="Preferred Sishu pass. Preserve classical/commentary fields. Add modern Chinese first, then generate English and readable modern Japanese from that modern Chinese bridge.",
    ),
    EnhancementBook(
        "sishu-jizhu",
        "四書章句集註 legacy",
        "classical_chinese_legacy",
        "sources/sishu",
        add_modern_zh=True,
        add_modern_ja=True,
        priority=75,
        notes="Legacy Sishu pass. Keep old output; write only overlay files. Add modern Chinese first, then English and readable modern Japanese.",
    ),
    EnhancementBook(
        "shiji-aginti",
        "史記",
        "classical_chinese",
        "sources/shiji",
        priority=80,
        notes="Shiji chunks already contain zh_original and zh_modern; backfill English from zh_modern without rewriting existing Japanese.",
    ),
    EnhancementBook("the-old-capital", "古都", "early_bilingual", "sources/《古都》（川端康成经典名作，余华倾情推荐）.epub", priority=90),
    EnhancementBook("izu-no-odori", "伊豆的舞女 / 伊豆の踊子", "early_bilingual", "sources/伊豆的舞女 - [日]川端康成.epub", priority=100),
    EnhancementBook("genji-modern", "源氏物语 / 源氏物語", "early_bilingual_large", "sources/源氏物语", priority=110),
    EnhancementBook(
        "kojiki",
        "古事記",
        "ancient_classic",
        "sources/kojiki",
        add_modern_ja=True,
        priority=120,
        notes="Ancient text. Add English and a reader-friendly modern Japanese paraphrase from the modern Chinese bridge/source layer.",
    ),
    EnhancementBook("woman-in-the-dunes", "砂女 / 砂の女", "early_bilingual", "sources/砂女", priority=130),
    EnhancementBook(
        "ginga-tetsudo",
        "銀河鉄道の夜",
        "prepared_bilingual",
        "sources/銀河鉄道の夜",
        priority=140,
        dependency="wait_for_current_bilingual_completion",
        notes="Prepare now, run enhancement only after the current bilingual base queue finishes and reviewed chunks are promoted.",
    ),
    EnhancementBook(
        "chumon-no-ooi-ryoriten",
        "注文の多い料理店",
        "prepared_bilingual",
        "sources/注文の多い料理店",
        priority=150,
        dependency="wait_for_current_bilingual_completion",
        notes="Prepare now, run enhancement only after the current bilingual base queue finishes and reviewed chunks are promoted.",
    ),
]


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_chunk_ids(book_id: str) -> list[str]:
    manifest_path = ROOT / "books" / book_id / "work" / "bilingual" / "chunks" / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        ids = [item.get("chunk_id") for item in manifest.get("chunks", [])]
        return [str(item) for item in ids if item]
    return []


def data_chunk_ids(book_id: str) -> list[str]:
    chunk_dir = ROOT / "data" / "interlinear" / book_id / "chunks"
    ids: list[str] = []
    for path in sorted(chunk_dir.glob("*.json")):
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            data = {}
        ids.append(str(data.get("chunk_id") or path.stem))
    return ids


def chunk_ids_for(book_id: str) -> tuple[list[str], str]:
    ids = manifest_chunk_ids(book_id)
    if ids:
        return ids, "books_manifest"
    return data_chunk_ids(book_id), "data_interlinear_chunks"


def base_candidates(book_id: str, chunk_id: str) -> list[str]:
    candidates = [
        ROOT / "data" / "interlinear" / book_id / "chunks" / f"{chunk_id}.json",
        ROOT / "books" / book_id / "work" / "bilingual" / "reviewed" / "chunks" / f"{chunk_id}.json",
        ROOT / "books" / book_id / "work" / "bilingual" / "interlinear" / "chunks" / f"{chunk_id}.json",
    ]
    return [rel(path) for path in candidates if path.exists()]


def actions_for(book: EnhancementBook) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if book.add_modern_zh:
        actions.append(
            {
                "field": "zh_modern",
                "kind": "modern_chinese_bridge",
                "source_priority": ["unit.zh_modern", "paragraph.corrected_text", "unit.zh_original", "unit.zh", "unit.source_text", "paragraph.source_text"],
                "instruction": "Add accurate, readable modern Chinese aligned to the existing classical Chinese unit. Preserve names, terms, and source order; do not overwrite existing zh or ja.",
            }
        )
    if book.add_english:
        actions.append(
            {
                "field": "en",
                "kind": "understandable_english",
                "source_priority": ["overlay.zh_modern", "unit.zh_modern", "paragraph.corrected_text", "unit.zh_original", "unit.zh", "paragraph.source_text"],
                "instruction": "Add clear, natural English aligned to the existing sentence/unit structure. Prefer modern Chinese when available. Preserve names and culturally specific terms; do not overwrite existing zh or ja.",
            }
        )
    if book.add_modern_ja:
        actions.append(
            {
                "field": "ja_modern",
                "kind": "plain_modern_japanese",
                "source_priority": ["overlay.zh_modern", "unit.zh_modern", "paragraph.corrected_text", "unit.zh_original", "unit.zh", "paragraph.source_text"],
                "instruction": "Add reader-friendly modern Japanese based on the modern Chinese meaning bridge. Preserve the existing ja field as legacy/source/comment Japanese.",
            }
        )
    return actions


def task_for(book: EnhancementBook, chunk_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_type": "incremental_language_overlay",
        "book_id": book.book_id,
        "chunk_id": chunk_id,
        "base_chunk_candidates": base_candidates(book.book_id, chunk_id),
        "task_template_ref": "manifest.task_template",
        "output_overlay_path": f"books/{book.book_id}/work/incremental/en-modern-ja/overlays/chunks/{chunk_id}.json",
        "durable_overlay_path": f"data/interlinear-overlays/en-modern-ja/{book.book_id}/chunks/{chunk_id}.json",
    }


def prepare_book(book: EnhancementBook, *, dry_run: bool = False) -> dict[str, Any]:
    chunk_ids, source = chunk_ids_for(book.book_id)
    task_dir = OUT_ROOT / book.book_id
    tasks_path = task_dir / "tasks.jsonl"
    manifest_path = task_dir / "manifest.json"
    tasks = [task_for(book, chunk_id) for chunk_id in chunk_ids]
    manifest = {
        "schema_version": 1,
        "book_id": book.book_id,
        "title": book.title,
        "category": book.category,
        "source_area": book.source_area,
        "priority": book.priority,
        "dependency": book.dependency,
        "notes": book.notes,
        "chunk_id_source": source,
        "chunk_count": len(chunk_ids),
        "actions": actions_for(book),
        "tasks_jsonl": rel(tasks_path),
        "old_json_is_read_only": True,
        "task_template": {
            "schema_version": 1,
            "task_type": "incremental_language_overlay",
            "category": book.category,
            "dependency": book.dependency,
            "actions": actions_for(book),
            "do_not_modify_templates": [
                f"data/interlinear/{book.book_id}/chunks/{{chunk_id}}.json",
                f"books/{book.book_id}/work/bilingual/interlinear/chunks/{{chunk_id}}.json",
                f"books/{book.book_id}/work/bilingual/reviewed/chunks/{{chunk_id}}.json",
            ],
            "output_overlay_path_template": f"books/{book.book_id}/work/incremental/en-modern-ja/overlays/chunks/{{chunk_id}}.json",
            "durable_overlay_path_template": f"data/interlinear-overlays/en-modern-ja/{book.book_id}/chunks/{{chunk_id}}.json",
            "merge_policy": {
                "preserve_existing_fields": True,
                "append_only_fields": ["zh_modern", "en", "ja_modern"],
                "legacy_japanese_field": "ja",
                "modern_japanese_field": "ja_modern",
                "modern_chinese_field": "zh_modern",
            },
            "validation": {
                "require_no_source_text_loss": True,
                "require_modern_zh_if_requested": book.add_modern_zh,
                "require_english_if_requested": book.add_english,
                "require_modern_ja_if_requested": book.add_modern_ja,
                "forbid_overwriting_legacy_ja": True,
                "require_ruby_for_kanji_tokens_in_ja_modern": True,
            },
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        task_dir.mkdir(parents=True, exist_ok=True)
        tasks_path.write_text("\n".join(json.dumps(task, ensure_ascii=False) for task in tasks) + ("\n" if tasks else ""), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=[book.book_id for book in BOOKS], help="Prepare selected book; repeatable.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    selected = [book for book in BOOKS if not args.book_id or book.book_id in args.book_id]
    manifests = [prepare_book(book, dry_run=args.dry_run) for book in sorted(selected, key=lambda item: item.priority)]
    global_manifest = {
        "schema_version": 1,
        "task_family": "incremental_english_and_modern_japanese_overlays",
        "old_json_is_read_only": True,
        "output_root": rel(OUT_ROOT),
        "durable_overlay_root": "data/interlinear-overlays/en-modern-ja",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "books": manifests,
        "worker_contract": {
            "read_existing_chunks_only": True,
            "never_delete_or_rewrite_old_json": True,
            "write_overlay_chunks_first": True,
            "merge_only_after_validation": True,
            "compile_new_editions_from_overlay_plus_base": True,
        },
    }
    if not args.dry_run:
        GLOBAL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_MANIFEST.write_text(json.dumps(global_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for manifest in manifests:
        print(f"prepared {manifest['book_id']} chunks={manifest['chunk_count']} actions={','.join(action['field'] for action in manifest['actions'])}")
    print(f"global_manifest={rel(GLOBAL_MANIFEST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
