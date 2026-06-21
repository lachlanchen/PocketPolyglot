#!/usr/bin/env python3
"""Prepare Kojiki as a wenyan-main quadrilingual task.

This script is additive: it reads the completed bilingual Kojiki chunks and
creates a separate ``kojiki-wenyan`` quadrilingual task without modifying the
original ``books/kojiki`` data.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from json_to_trilingual_pair_tex import token_text


ROOT = Path(__file__).resolve().parents[2]
SOURCE_BOOK_ID = "kojiki"
BOOK_ID = "kojiki-wenyan"
SOURCE_PLAN = ROOT / "books" / SOURCE_BOOK_ID / "book-plan.json"
SOURCE_CHUNK_DIR = ROOT / "books" / SOURCE_BOOK_ID / "work" / "bilingual" / "interlinear" / "chunks"
SOURCE_MANIFEST = ROOT / "books" / SOURCE_BOOK_ID / "work" / "bilingual" / "chunks" / "manifest.json"

OUT_DIR = ROOT / "books" / BOOK_ID
CHUNK_DIR = OUT_DIR / "work" / "quadrilingual" / "chunks"
MANIFEST = CHUNK_DIR / "manifest.json"
CHUNKS_JSONL = CHUNK_DIR / "chunks.jsonl"
PLAN = OUT_DIR / "book-plan.json"

ZH_MD = ROOT / "books" / SOURCE_BOOK_ID / "markdown" / "zh.md"
JA_MODERN_MD = ROOT / "books" / SOURCE_BOOK_ID / "markdown" / "ja_modern.md"
ZH_MODERN_REF = ROOT / "books" / SOURCE_BOOK_ID / "markdown" / "zh_modern_ref.txt"
EN_RAW = ROOT / "books" / SOURCE_BOOK_ID / "markdown" / "en.raw.txt"

SPACE_RE = re.compile(r"\s+")
NOTE_MARK_RE = re.compile(r"[一二三四五六七八九〇零十百]{1,4}$")
HAN_RE = re.compile(r"[\u3400-\u9fff]")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def compact(text: Any) -> str:
    return SPACE_RE.sub(" ", str(text or "").replace("\u3000", " ")).strip()


def flat_tokens(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        out: list[dict[str, Any]] = []
        for item in value:
            out.extend(flat_tokens(item))
        return out
    return [{"t": str(value)}]


def tokens_text(value: Any) -> str:
    return compact(token_text(flat_tokens(value)))


def clean_existing_ja(text: str) -> str:
    text = compact(text)
    # The source Japanese reference sometimes carries old footnote numerals.
    return NOTE_MARK_RE.sub("", text).strip()


def read_text(path: Path, limit: int = 4800) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def source_chunk_paths() -> list[Path]:
    manifest = load_json(SOURCE_MANIFEST)
    paths: list[Path] = []
    for item in manifest.get("chunks", []):
        chunk_id = item.get("chunk_id")
        if chunk_id:
            paths.append(SOURCE_CHUNK_DIR / f"{chunk_id}.json")
    return [path for path in paths if path.exists()]


def node_title(chunk: dict[str, Any], lang: str) -> str:
    key = f"title_{lang}"
    for node_key in ("subsection", "section", "story"):
        node = chunk.get(node_key) or {}
        title = tokens_text(node.get(key))
        if title:
            return title
    return ""


def story_title(chunk: dict[str, Any], lang: str) -> str:
    key = f"title_{lang}"
    for node_key in ("story", "subsection", "section"):
        node = chunk.get(node_key) or {}
        title = tokens_text(node.get(key))
        if title:
            return title
    return ""


def chapter_en(title: str, fallback_number: int) -> str:
    mapping = {
        "序": "Preface",
        "上卷": "Upper Volume",
        "上巻": "Upper Volume",
        "中卷": "Middle Volume",
        "中巻": "Middle Volume",
        "下卷": "Lower Volume",
        "下巻": "Lower Volume",
    }
    return mapping.get(title, f"Volume {fallback_number}")


def chapter_ja(title: str) -> str:
    return title.replace("卷", "巻")


def build_existing_units(paragraph: dict[str, Any]) -> list[dict[str, str]]:
    units: list[dict[str, str]] = []
    for index, unit in enumerate(paragraph.get("units", []), start=1):
        if not isinstance(unit, dict):
            continue
        source = compact(unit.get("source_text"))
        if not source:
            continue
        units.append(
            {
                "unit_id": f"{paragraph.get('id')}-u{index:03d}",
                "source_wenyan": source,
                "existing_zh": tokens_text(unit.get("zh")),
                "existing_ja": clean_existing_ja(tokens_text(unit.get("ja"))),
            }
        )
    return units


def has_book_spine(paragraphs: list[dict[str, Any]]) -> bool:
    """Keep real Kojiki spine text, not source-license/footer debris."""
    text_parts: list[str] = []
    for paragraph in paragraphs:
        text_parts.append(str(paragraph.get("wenyan") or ""))
        for unit in paragraph.get("source_units", []):
            text_parts.append(str(unit.get("source_wenyan") or ""))

    text = "".join(text_parts)
    total_chars = sum(1 for char in text if not char.isspace())
    han_chars = len(HAN_RE.findall(text))
    if han_chars == 0:
        return False
    # Real Kojiki source chunks are short all-Han lines or dense wenyan text.
    # Source-edition tails can contain a few Han usernames inside Latin/URL text.
    if total_chars >= 80 and han_chars / total_chars < 0.15:
        return False
    return True


def prepare_chunks() -> list[dict[str, Any]]:
    zh_reference = read_text(ZH_MODERN_REF)
    ja_reference = read_text(JA_MODERN_MD)
    en_reference = read_text(EN_RAW)
    chapter_numbers: OrderedDict[str, int] = OrderedDict()
    chunks: list[dict[str, Any]] = []

    for path in source_chunk_paths():
        source = load_json(path)
        subsection = str((source.get("subsection") or {}).get("id") or node_title(source, "zh") or "main")
        if subsection not in chapter_numbers:
            chapter_numbers[subsection] = len(chapter_numbers) + 1
        number = chapter_numbers[subsection]
        chapter_title_wenyan = node_title(source, "zh") or subsection
        paragraphs = []
        for paragraph in source.get("paragraphs", []):
            source_units = build_existing_units(paragraph)
            wenyan = "".join(unit["source_wenyan"] for unit in source_units) or compact(paragraph.get("source_text"))
            if not wenyan:
                continue
            paragraphs.append(
                {
                    "id": str(paragraph.get("id")),
                    "wenyan": wenyan,
                    "source_units": source_units,
                }
            )
        if not paragraphs:
            continue
        if not has_book_spine(paragraphs):
            continue
        chunks.append(
            {
                "schema_version": 1,
                "task_type": "quadrilingual_wenyan_main",
                "book_id": BOOK_ID,
                "book_title_wenyan": "古事記",
                "chunk_id": source["chunk_id"],
                "chapter_id": f"{BOOK_ID}-{number:02d}",
                "chapter_number": number,
                "chapter_title_wenyan": chapter_title_wenyan,
                "chapter_title_zh_modern": chapter_title_wenyan,
                "chapter_title_ja_modern": chapter_ja(node_title(source, "ja") or chapter_title_wenyan),
                "chapter_title_en": chapter_en(chapter_title_wenyan, number),
                "section_title_wenyan": story_title(source, "zh") or chapter_title_wenyan,
                "source_spine_lang": "wenyan",
                "paragraphs": paragraphs,
                "reference": {
                    "scope": "Use exact source units as the spine. Existing_ja is the prior aligned Japanese layer. Broad references are for style and terminology, not for inserting unrelated text.",
                    "ja_modern": {
                        "source": "books/kojiki/markdown/ja_modern.md",
                        "excerpt": ja_reference,
                    },
                    "zh_modern": {
                        "source": "books/kojiki/markdown/zh_modern_ref.txt",
                        "excerpt": zh_reference,
                    },
                    "en": {
                        "source": "books/kojiki/markdown/en.raw.txt",
                        "excerpt": en_reference,
                    },
                },
            }
        )
    return chunks


def main() -> int:
    source_plan = load_json(SOURCE_PLAN)
    chunks = prepare_chunks()
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_JSONL.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": "古事記",
        "book_title_zh_modern": "古事记",
        "book_title_ja_modern": "古事記",
        "book_title_en": "Kojiki",
        "author": source_plan.get("author", "太安萬侶・稗田阿礼"),
        "author_reading_zh": source_plan.get("author_reading_zh", ""),
        "author_reading_ja": source_plan.get("author_reading_ja", ""),
        "chunk_count": len(chunks),
        "chunks": [
            {"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]}
            for chunk in chunks
        ],
        "source_paths": {
            "bilingual_base": "books/kojiki/work/bilingual/interlinear/chunks",
            "wenyan_markdown": str(ZH_MD.relative_to(ROOT)),
            "ja_modern_reference": str(JA_MODERN_MD.relative_to(ROOT)),
            "zh_modern_reference": str(ZH_MODERN_REF.relative_to(ROOT)),
            "english_text": str(EN_RAW.relative_to(ROOT)),
        },
        "source_sha256": {
            str(ZH_MD.relative_to(ROOT)): sha256(ZH_MD),
            str(JA_MODERN_MD.relative_to(ROOT)): sha256(JA_MODERN_MD),
            str(ZH_MODERN_REF.relative_to(ROOT)): sha256(ZH_MODERN_REF),
            str(EN_RAW.relative_to(ROOT)): sha256(EN_RAW),
        },
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(MANIFEST, manifest)
    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "launchable",
        "launchable": True,
        "task_mode": "quadrilingual_wenyan_main",
        "source_language": "wenyan",
        "book_title_wenyan": manifest["book_title_wenyan"],
        "book_title_zh": manifest["book_title_zh_modern"],
        "book_title_ja": manifest["book_title_ja_modern"],
        "book_title_en": manifest["book_title_en"],
        "author": manifest["author"],
        "author_reading_zh": manifest["author_reading_zh"],
        "author_reading_ja": manifest["author_reading_ja"],
        "book_description": "Kojiki with the existing wenyan/kanbun-aligned source as main text plus modern Japanese, modern Chinese, and English overlays.",
        "cover_image": "assets/covers/kojiki/cover.png",
        "source_paths": manifest["source_paths"],
        "chunks_jsonl": str(CHUNKS_JSONL.relative_to(ROOT)),
        "chunks_manifest": str(MANIFEST.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{BOOK_ID}/work/quadrilingual/interlinear/chunks",
        "assembled_json": f"books/{BOOK_ID}/work/quadrilingual/preview/{BOOK_ID}.partial.json",
        "build_root": f"build/{BOOK_ID}/wenyan-main-quadrilingual",
        "prepared_at": manifest["prepared_at"],
    }
    write_json(PLAN, plan)
    print(f"prepared {len(chunks)} chunks")
    print(PLAN.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
