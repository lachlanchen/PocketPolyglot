#!/usr/bin/env python3
"""Prepare Nihon Shoki as a wenyan-main quadrilingual task."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "nihon-shoki"
WENYAN_MD = ROOT / "books" / BOOK_ID / "markdown" / "wenyan.md"
LEGACY_MD = ROOT / "books" / BOOK_ID / "markdown" / "ja.md"
EN_RAW = ROOT / "books" / BOOK_ID / "markdown" / "en.raw.txt"
CHUNK_DIR = ROOT / "books" / BOOK_ID / "work" / "quadrilingual" / "chunks"
MANIFEST = CHUNK_DIR / "manifest.json"
CHUNKS_JSONL = CHUNK_DIR / "chunks.jsonl"
PLAN = ROOT / "books" / BOOK_ID / "book-plan.json"

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
FOOTNOTE_DIGIT_RE = re.compile(r"(?<=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])\d{1,3}(?=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])")
SPACE_RE = re.compile(r"\s+")
SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]")
ROMAN_TO_INT = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
    "XXI": 21,
    "XXII": 22,
    "XXIII": 23,
    "XXIV": 24,
    "XXV": 25,
    "XXVI": 26,
    "XXVII": 27,
    "XXVIII": 28,
    "XXIX": 29,
    "XXX": 30,
}


def clean_text(text: str) -> str:
    text = text.strip()
    text = text[1:].strip() if text.startswith(">") else text
    text = FOOTNOTE_DIGIT_RE.sub("", text)
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_wenyan_markdown() -> None:
    if WENYAN_MD.exists():
        return
    if not LEGACY_MD.exists():
        raise FileNotFoundError(LEGACY_MD)
    text = LEGACY_MD.read_text(encoding="utf-8")
    # The EPUB converter originally named this ja.md, but the file is classical
    # Chinese/kanbun text. Keep a correctly named copy for all future tasks.
    WENYAN_MD.parent.mkdir(parents=True, exist_ok=True)
    WENYAN_MD.write_text(text, encoding="utf-8")


def english_book_windows() -> dict[int, dict[str, str]]:
    if not EN_RAW.exists():
        return {}
    lines = EN_RAW.read_text(encoding="utf-8", errors="replace").splitlines()
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = re.search(r"\bBOOK\s+([IVXLCDM]+)\b", line, flags=re.IGNORECASE)
        if not match:
            continue
        roman = match.group(1).upper()
        number = ROMAN_TO_INT.get(roman)
        if number and 1 <= number <= 30:
            starts.append((number, index))
    starts = sorted(dict(starts).items(), key=lambda item: item[0])
    windows: dict[int, dict[str, str]] = {}
    for offset, (number, start) in enumerate(starts):
        end = starts[offset + 1][1] if offset + 1 < len(starts) else min(len(lines), start + 1400)
        block = "\n".join(lines[start:end])
        block = re.sub(r"\n{3,}", "\n\n", block).strip()
        windows[number] = {
            "source": "Nihongi: Chronicles of Japan from the Earliest Times to A.D. 697",
            "book_number": number,
            "line_window": f"{start + 1}-{end}",
            "excerpt": block[:4500],
        }
    return windows


def parse_wenyan_sections() -> list[dict[str, Any]]:
    lines = WENYAN_MD.read_text(encoding="utf-8").splitlines()
    sections: list[dict[str, Any]] = []
    current_volume = ""
    current_section = ""
    started = False
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        paragraph = clean_text("".join(buffer))
        buffer = []
        if not paragraph or not started or not HAN_RE.search(paragraph):
            return
        sections.append(
            {
                "volume": current_volume,
                "section": current_section or current_volume,
                "text": paragraph,
            }
        )

    for raw in lines:
        line = raw.rstrip()
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            title = clean_text(heading.group(2))
            level = len(heading.group(1))
            if level == 1 and title.startswith("卷"):
                started = True
                current_volume = title
                current_section = ""
            elif started and level >= 2:
                current_section = title
            continue
        if not started:
            continue
        stripped = clean_text(line)
        if not stripped:
            flush()
            continue
        buffer.append(stripped)
        if len("".join(buffer)) >= 700 and SENTENCE_END_RE.search(stripped):
            flush()
    flush()
    return sections


def split_paragraph(text: str, max_chars: int = 520) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(text):
        end = match.end()
        if end - start >= max_chars:
            pieces.append(text[start:end])
            start = end
    if start < len(text):
        tail = text[start:]
        if len(tail) > max_chars * 1.6:
            for offset in range(0, len(tail), max_chars):
                pieces.append(tail[offset : offset + max_chars])
        else:
            pieces.append(tail)
    return [piece.strip() for piece in pieces if piece.strip()]


def prepare_chunks() -> list[dict[str, Any]]:
    windows = english_book_windows()
    source_sections = parse_wenyan_sections()
    chunks: list[dict[str, Any]] = []
    paragraph_counter = 0
    current_volume = ""
    volume_number = 0
    section_counter = 0
    for item in source_sections:
        if item["volume"] != current_volume:
            current_volume = item["volume"]
            volume_number += 1
            section_counter = 0
        section_counter += 1
        section = item["section"]
        for piece in split_paragraph(item["text"]):
            paragraph_counter += 1
            chunk_id = f"{BOOK_ID}-chunk-{paragraph_counter:04d}"
            paragraph_id = f"{chunk_id}-p001"
            chapter_id = f"{BOOK_ID}-book-{volume_number:02d}"
            chunks.append(
                {
                    "schema_version": 1,
                    "task_type": "quadrilingual_wenyan_main",
                    "book_id": BOOK_ID,
                    "chunk_id": chunk_id,
                    "chapter_id": chapter_id,
                    "chapter_number": volume_number,
                    "chapter_title_wenyan": current_volume,
                    "chapter_title_zh_modern": current_volume,
                    "chapter_title_ja_modern": current_volume.replace("卷", "巻"),
                    "chapter_title_en": f"Book {volume_number}",
                    "section_title_wenyan": section,
                    "source_spine_lang": "wenyan",
                    "paragraphs": [
                        {
                            "id": paragraph_id,
                            "wenyan": piece,
                        }
                    ],
                    "reference": {
                        "en": windows.get(volume_number, {}),
                        "scope": "English reference is broad book-level; generate aligned overlays from the wenyan source and cross-check with this reference where it matches.",
                    },
                }
            )
    return chunks


def main() -> int:
    ensure_wenyan_markdown()
    chunks = prepare_chunks()
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_JSONL.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": "日本書紀",
        "book_title_zh_modern": "日本书纪",
        "book_title_ja_modern": "日本書紀",
        "book_title_en": "Nihon Shoki",
        "author": "舍人親王 等",
        "author_reading_zh": "shè rén qīn wáng děng",
        "author_reading_ja": "とねりしんのう ほか",
        "chunk_count": len(chunks),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": {
            "wenyan_epub": "sources/日本書紀/日本書紀.epub",
            "english_pdf": "sources/日本書紀/Nihongi_ Chronicle of Japan From the Earliest Time to A.D. 697.pdf",
            "wenyan_markdown": str(WENYAN_MD.relative_to(ROOT)),
            "english_text": str(EN_RAW.relative_to(ROOT)) if EN_RAW.exists() else "",
        },
        "source_sha256": {
            str(WENYAN_MD.relative_to(ROOT)): sha256(WENYAN_MD),
            str(EN_RAW.relative_to(ROOT)): sha256(EN_RAW) if EN_RAW.exists() else "",
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
        "book_description": "Nihon Shoki with classical Chinese as the main text and modern Chinese, modern Japanese, and English overlays.",
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
