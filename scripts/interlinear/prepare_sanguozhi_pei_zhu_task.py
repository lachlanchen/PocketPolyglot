#!/usr/bin/env python3
"""Prepare a Sanguozhi Pei Songzhi commentary main-text task.

This task is intentionally additive.  It does not regenerate the existing
Chen Shou quadrilingual JSON; it extracts Pei Songzhi commentary paragraphs
from the local commented EPUB and prepares only those notes as new
quadrilingual wenyan-main chunks.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "sanguozhi-pei-zhu"
BASE_BOOK_ID = "sanguozhi"
SOURCE_EPUB = ROOT / "sources" / "sanguozhi" / "zh" / "pei-songzhi-source-epub" / "三国志（中华经典普及文库）.epub"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
NOTE_MARK_RE = re.compile(rf"^[{CIRCLED}0-9]+")
SOURCE_LIKE_RE = re.compile(
    r"^(?:又)?(?:臣\s*松之|裴松之|"
    r"魏书|魏略|吴书|蜀记|蜀书|晋阳秋|英雄记|献帝春秋|献帝起居注|"
    r"袁宏汉纪|汉纪|世语|典略|曹瞒传|续汉书|山阳公载记|江表传|"
    r"傅子|魏氏春秋|华阳国志|九州春秋|孙盛|习凿齿|虞溥|司马彪)"
    r"(?:曰|云|载|案|：)"
)
VOL_RE = re.compile(r"三国志卷([一二三四五六七八九十百〇零]+)")
SPACE_RE = re.compile(r"\s+")

ZH_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def zh_number_to_int(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    if text == "十":
        return 10
    if "百" in text:
        left, _, right = text.partition("百")
        return (ZH_DIGITS.get(left, 1) or 1) * 100 + zh_number_to_int(right)
    if "十" in text:
        left, _, right = text.partition("十")
        return (ZH_DIGITS.get(left, 1) or 1) * 10 + (ZH_DIGITS.get(right, 0) if right else 0)
    value = 0
    for char in text:
        value = value * 10 + ZH_DIGITS.get(char, 0)
    return value


def clean_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = SPACE_RE.sub(" ", text)
    text = text.replace(" / ", "")
    return text.strip()


def split_cjk_text(text: str, max_chars: int) -> list[str]:
    text = clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    pieces: list[str] = []
    current = ""
    for part in re.split(r"([。！？；;])", text):
        if not part:
            continue
        current += part
        if part in "。！？；;" and len(current) >= max_chars:
            pieces.append(current.strip())
            current = ""
        elif len(current) >= max_chars * 1.35:
            pieces.append(current.strip())
            current = ""
    if current.strip():
        pieces.append(current.strip())
    result: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chars * 1.5:
            result.append(piece)
            continue
        for start in range(0, len(piece), max_chars):
            result.append(piece[start : start + max_chars].strip())
    return [piece for piece in result if piece]


def paragraph_text(node: Any) -> str:
    return clean_text(node.get_text("", strip=True))


def is_note_paragraph(text: str, in_note_block: bool) -> bool:
    if not text:
        return False
    if NOTE_MARK_RE.match(text):
        return True
    if text.startswith(("臣松之案", "臣松之以为", "臣松之按", "臣松之")):
        return True
    return bool(in_note_block and SOURCE_LIKE_RE.match(text))


def iter_epub_notes(epub: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    stats = {
        "html_items": 0,
        "chapter_items": 0,
        "note_paragraphs": 0,
        "main_paragraphs_seen": 0,
    }
    with ZipFile(epub) as archive:
        names = sorted(name for name in archive.namelist() if name.lower().endswith((".html", ".htm", ".xhtml")))
        stats["html_items"] = len(names)
        for name in names:
            soup = BeautifulSoup(archive.read(name), "html.parser")
            h1 = soup.find("h1")
            h1_text = clean_text(h1.get_text("", strip=True)) if h1 else ""
            match = VOL_RE.search(h1_text)
            if not match:
                continue
            volume = zh_number_to_int(match.group(1))
            if not volume:
                continue
            stats["chapter_items"] += 1
            h2 = soup.find("h2")
            subtitle = clean_text(h2.get_text("", strip=True)) if h2 else ""
            current_main_index = 0
            current_note_index = 0
            in_note_block = False
            for node in soup.find_all(["p"], recursive=True):
                text = paragraph_text(node)
                if not text:
                    continue
                if is_note_paragraph(text, in_note_block):
                    current_note_index += 1
                    stats["note_paragraphs"] += 1
                    notes.append(
                        {
                            "epub_item": name,
                            "volume": volume,
                            "current_book_chapter_number": volume + 1,
                            "chapter_title_wenyan": f"卷 {volume:02d}",
                            "chapter_title_zh_modern": f"卷 {volume:02d}",
                            "chapter_title_ja_modern": f"巻 {volume:02d}",
                            "chapter_title_en": f"Records of the Three Kingdoms {volume}: Pei Songzhi commentary",
                            "subtitle": subtitle,
                            "main_paragraph_index": current_main_index,
                            "note_index": current_note_index,
                            "text": text,
                        }
                    )
                    in_note_block = True
                else:
                    current_main_index += 1
                    stats["main_paragraphs_seen"] += 1
                    in_note_block = False
    return notes, stats


def build_chunks(notes: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    counter = 0
    for note in notes:
        pieces = split_cjk_text(note["text"], max_chars=max_chars)
        for part_number, piece in enumerate(pieces, start=1):
            counter += 1
            chunk_id = f"{BOOK_ID}-chunk-{counter:04d}"
            paragraph_id = f"{chunk_id}-p001"
            section = (
                f"{note['chapter_title_wenyan']} 裴松之注 "
                f"main {note['main_paragraph_index']} note {note['note_index']}"
            )
            if len(pieces) > 1:
                section += f" part {part_number}"
            chunks.append(
                {
                    "schema_version": 1,
                    "task_type": "quadrilingual_wenyan_main",
                    "book_id": BOOK_ID,
                    "book_title_wenyan": "三國志裴松之注",
                    "chunk_id": chunk_id,
                    "chapter_id": f"{BOOK_ID}-chapter-{note['current_book_chapter_number']:02d}",
                    "chapter_number": note["current_book_chapter_number"],
                    "chapter_title_wenyan": note["chapter_title_wenyan"],
                    "chapter_title_zh_modern": note["chapter_title_zh_modern"],
                    "chapter_title_ja_modern": note["chapter_title_ja_modern"],
                    "chapter_title_en": note["chapter_title_en"],
                    "section_title_wenyan": section,
                    "source_spine_lang": "wenyan",
                    "source_layer": "pei_songzhi_zhu_maintext",
                    "paragraphs": [{"id": paragraph_id, "wenyan": piece}],
                    "reference": {
                        "scope": "Pei Songzhi commentary chunk. Generate only the commentary chunk; do not regenerate or duplicate the Chen Shou main text.",
                        "source": {
                            "role": "pei_songzhi_commentary_full_text",
                            "path": str(SOURCE_EPUB.relative_to(ROOT)),
                            "epub_item": note["epub_item"],
                            "volume": str(note["volume"]),
                            "subtitle": note["subtitle"],
                            "main_paragraph_index": str(note["main_paragraph_index"]),
                            "note_index": str(note["note_index"]),
                        },
                        "base_current_json": {
                            "book_id": BASE_BOOK_ID,
                            "chunk_dir": "books/sanguozhi/work/quadrilingual/interlinear/chunks",
                            "policy": "read-only reuse for Chen Shou text",
                        },
                    },
                }
            )
    return chunks


def write_markdown(notes: list[dict[str, Any]], path: Path) -> None:
    lines = ["# 三國志裴松之注", ""]
    current_volume = None
    for note in notes:
        if note["volume"] != current_volume:
            current_volume = note["volume"]
            lines.extend([f"## 卷 {current_volume:02d} {note['subtitle']}".rstrip(), ""])
        lines.extend([note["text"], ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chars", type=int, default=520)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not SOURCE_EPUB.exists():
        raise FileNotFoundError(SOURCE_EPUB)

    out_root = ROOT / "books" / BOOK_ID
    data_root = ROOT / "data" / "source-plan" / "sanguozhi-pei-zhu-maintext"
    chunks_jsonl = data_root / "chunks.jsonl"
    manifest_path = data_root / "manifest.json"
    plan_path = out_root / "book-plan.json"
    markdown_path = out_root / "markdown" / "pei-zhu.md"
    build_readme = ROOT / "build" / BOOK_ID / "README.md"

    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not args.force:
        print(f"{BOOK_ID}: already prepared")
        print(plan_path.relative_to(ROOT))
        return 0

    notes, stats = iter_epub_notes(SOURCE_EPUB)
    chunks = build_chunks(notes, max_chars=args.max_chars)
    if not chunks:
        raise RuntimeError("no Pei Songzhi commentary chunks were extracted")

    data_root.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    write_markdown(notes, markdown_path)

    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "base_book_id": BASE_BOOK_ID,
        "status": "prepared",
        "task_mode": "pei_songzhi_zhu_maintext_additive",
        "book_title_wenyan": "三國志裴松之注",
        "book_title_zh_modern": "三国志裴松之注",
        "book_title_ja_modern": "三国志裴松之注",
        "book_title_en": "Records of the Three Kingdoms with Pei Songzhi Commentary",
        "author": "陳壽／裴松之",
        "author_reading_zh": "chén shòu / péi sōng zhī",
        "author_reading_ja": "ちん じゅ／はい しょうし",
        "chunk_count": len(chunks),
        "note_paragraph_count": len(notes),
        "chapter_count": len({chunk["chapter_number"] for chunk in chunks}),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": {
            "base_chenshou_current_json": "books/sanguozhi/work/quadrilingual/interlinear/chunks",
            "base_chenshou_chunks_jsonl": "books/sanguozhi/work/quadrilingual/chunks/chunks.jsonl",
            "base_chenshou_manifest": "books/sanguozhi/work/quadrilingual/chunks/manifest.json",
            "pei_songzhi_commentary_epub": str(SOURCE_EPUB.relative_to(ROOT)),
            "pei_songzhi_markdown": str(markdown_path.relative_to(ROOT)),
        },
        "extraction_stats": stats,
        "prepared_at": now,
    }
    write_json(manifest_path, manifest)

    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "base_book_id": BASE_BOOK_ID,
        "status": "launchable",
        "launchable": True,
        "task_mode": "pei_songzhi_zhu_maintext_additive",
        "book_title_wenyan": manifest["book_title_wenyan"],
        "book_title_zh": manifest["book_title_zh_modern"],
        "book_title_ja": manifest["book_title_ja_modern"],
        "book_title_en": manifest["book_title_en"],
        "author": manifest["author"],
        "author_reading_zh": manifest["author_reading_zh"],
        "author_reading_ja": manifest["author_reading_ja"],
        "book_description": "A new Sanguozhi edition that reuses the existing Chen Shou quadrilingual JSON and adds Pei Songzhi commentary as additional main-text chunks.",
        "source_paths": manifest["source_paths"],
        "reuse_existing_json": True,
        "base_current_chunk_dir": "books/sanguozhi/work/quadrilingual/interlinear/chunks",
        "base_current_chunks_jsonl": "books/sanguozhi/work/quadrilingual/chunks/chunks.jsonl",
        "base_current_manifest": "books/sanguozhi/work/quadrilingual/chunks/manifest.json",
        "base_current_assembled_json": "books/sanguozhi/work/quadrilingual/preview/sanguozhi.partial.json",
        "pei_chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "pei_chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "pei_raw_chunk_dir": f"books/{BOOK_ID}/work/pei-zhu-maintext/interlinear/chunks",
        "pei_candidate_dir": f"books/{BOOK_ID}/work/pei-zhu-maintext/parallel-json",
        "assembled_json": f"books/{BOOK_ID}/work/pei-zhu-maintext/preview/{BOOK_ID}.partial.json",
        "build_root": f"build/{BOOK_ID}/wenyan-main-quadrilingual",
        "default_note_order": {
            "wenyan": ["en", "ja_modern", "zh_modern"],
            "en": ["wenyan", "ja_modern", "zh_modern"],
            "ja_modern": ["wenyan", "en", "zh_modern"],
            "zh_modern": ["wenyan", "en", "ja_modern"],
        },
        "prepared_at": now,
    }
    write_json(plan_path, plan)

    build_readme.parent.mkdir(parents=True, exist_ok=True)
    build_readme.write_text(
        "# Sanguozhi Pei Songzhi Commentary Edition\n\n"
        "This build folder is reserved for the additive edition `sanguozhi-pei-zhu`.\n"
        "It reuses `books/sanguozhi/work/quadrilingual/interlinear/chunks` for Chen Shou text "
        "and adds generated Pei Songzhi commentary chunks from `data/source-plan/sanguozhi-pei-zhu-maintext/chunks.jsonl`.\n",
        encoding="utf-8",
    )

    print(f"{BOOK_ID}: notes={len(notes)} chunks={len(chunks)} chapters={manifest['chapter_count']}")
    print(plan_path.relative_to(ROOT))
    print(manifest_path.relative_to(ROOT))
    print(build_readme.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
