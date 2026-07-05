#!/usr/bin/env python3
"""Prepare Bhagavad Gita EN-main trilingual chunk tasks.

The local Sargeant PDF is a scholarly Sanskrit/English word-by-word edition.
This script extracts the English verse translation block from each verse page as
the stable source spine and keeps the full PDF plus the Chinese scan as
references.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "bhagavad-gita"
EN_SOURCE = Path("sources/bhagavad-gita/en/english-translation/The Bhagavad Gita.pdf")
ZH_SOURCE = Path("sources/bhagavad-gita/zh/chinese-translation/薄伽梵歌.pdf")
BODY_FIRST_PAGE = 73
BODY_LAST_PAGE = 773
SPACE_RE = re.compile(r"\s+")
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
}
CHAPTER_TITLES_EN = {
    1: "The Despondency of Arjuna",
    2: "The Yoga of Knowledge",
    3: "The Yoga of Action",
    4: "The Yoga of Renunciation of Action in Knowledge",
    5: "The Yoga of Renunciation",
    6: "The Yoga of Meditation",
    7: "The Yoga of Knowledge and Realization",
    8: "The Yoga of the Imperishable Brahman",
    9: "The Yoga of Royal Knowledge and Royal Secret",
    10: "The Yoga of Divine Manifestations",
    11: "The Yoga of the Vision of the Universal Form",
    12: "The Yoga of Devotion",
    13: "The Yoga of the Field and the Knower of the Field",
    14: "The Yoga of the Three Gunas",
    15: "The Yoga of the Supreme Person",
    16: "The Yoga of Divine and Demoniac Qualities",
    17: "The Yoga of the Threefold Faith",
    18: "The Yoga of Liberation and Renunciation",
}


@dataclass
class Line:
    y: float
    x_min: float
    x_max: float
    text: str


@dataclass
class Verse:
    page: int
    chapter: int
    verse: int
    text: str


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_bbox(en_source: Path, cache_path: Path, *, force: bool) -> None:
    src = ROOT / en_source
    if not src.exists():
        raise FileNotFoundError(src)
    if cache_path.exists() and not force and cache_path.stat().st_mtime >= src.stat().st_mtime:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pdftotext",
            "-bbox-layout",
            "-f",
            str(BODY_FIRST_PAGE),
            "-l",
            str(BODY_LAST_PAGE),
            str(src),
            str(cache_path),
        ],
        cwd=ROOT,
        check=True,
    )


def page_lines_and_blocks(page: Any) -> tuple[list[Line], list[list[Line]]]:
    lines: list[Line] = []
    blocks: list[list[Line]] = []
    for block in page.find_all("block"):
        block_lines: list[Line] = []
        for line in block.find_all("line"):
            words = line.find_all("word")
            if not words:
                continue
            text = " ".join(word.get_text() for word in words)
            x_min = min(float(word["xmin"]) for word in words)
            x_max = max(float(word["xmax"]) for word in words)
            y = min(float(word["ymin"]) for word in words)
            item = Line(y=y, x_min=x_min, x_max=x_max, text=text)
            block_lines.append(item)
            lines.append(item)
        if block_lines:
            blocks.append(block_lines)
    return lines, blocks


def page_chapter(lines: list[Line], current_chapter: int | None) -> int | None:
    for line in sorted((line for line in lines if line.y < 120), key=lambda line: line.y):
        text = line.text.strip()
        if text in ROMAN_TO_INT:
            return ROMAN_TO_INT[text]
        match = re.fullmatch(r"BOOK\s+([IVXLCDM]+)", text)
        if match and match.group(1) in ROMAN_TO_INT:
            return ROMAN_TO_INT[match.group(1)]
    return current_chapter


def page_verse(lines: list[Line]) -> int | None:
    candidates: list[tuple[float, int]] = []
    for line in lines:
        if line.y < 70 or line.y > 270:
            continue
        match = re.fullmatch(r"(\d{1,3}),?", line.text.strip())
        if match:
            candidates.append((line.y, int(match.group(1))))
    if not candidates:
        return None
    return sorted(candidates)[0][1]


def cleaned_translation_text(lines: list[Line]) -> str:
    text = "\n".join(line.text for line in sorted(lines, key=lambda line: line.y))
    text = text.replace("0 ", "O ")
    text = text.replace("Corne", "Come")
    text = text.replace("fonn", "form")
    text = text.replace("Krislma", "Krishna")
    text = text.replace(".Arjuna", "Arjuna")
    text = text.replace("Arjnna", "Arjuna")
    return compact(text.replace("\n", " / ")).replace(" / ", "\n")


def score_translation_block(block: list[Line]) -> tuple[int, float]:
    y_min = min(line.y for line in block)
    x_min = min(line.x_min for line in block)
    x_max = max(line.x_max for line in block)
    joined = " ".join(line.text for line in sorted(block, key=lambda line: line.y))
    first = joined.strip()
    if not (280 <= y_min <= 505 and x_min < 170 and x_max < 360):
        return (-1000, y_min)
    if first.startswith("•"):
        return (-1000, y_min)
    if sum(ch.isalpha() for ch in joined) < 12:
        return (-1000, y_min)
    score = 0
    if re.match(r'^[\"“‘(0A-Z]', first):
        score += 40
    if len(block) >= 2:
        score += 10
    if re.search(r"\b(?:nom|sg|pl|participle|gerund|acc|gen|loc|inst|voc|samdhi|cpd|imperative)\b", joined):
        score -= 25
    if re.search(r"\b(?:The|And|When|Wherever|Thus|Krishna|Arjuna|Sanjaya|Blessed|Lord|Self)\b", joined):
        score += 10
    score -= int(abs(y_min - 330) / 15)
    return (score, y_min)


def extract_translation(blocks: list[list[Line]], *, page_no: int) -> str:
    candidates = [(score_translation_block(block), block) for block in blocks]
    candidates = [(score, block) for score, block in candidates if score[0] > 0]
    if not candidates:
        raise RuntimeError(f"no translation block found on PDF page {page_no}")
    candidates.sort(key=lambda item: (-item[0][0], item[0][1]))
    return cleaned_translation_text(candidates[0][1])


def extract_verses(cache_path: Path) -> list[Verse]:
    soup = BeautifulSoup(cache_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    verses: list[Verse] = []
    current_chapter: int | None = None
    inferred_verse = 0
    for page_offset, page in enumerate(soup.find_all("page"), start=0):
        page_no = BODY_FIRST_PAGE + page_offset
        lines, blocks = page_lines_and_blocks(page)
        chapter = page_chapter(lines, current_chapter)
        if chapter is None:
            continue
        if chapter != current_chapter:
            current_chapter = chapter
            inferred_verse = 0
        verse = page_verse(lines)
        if verse is None or verse <= inferred_verse:
            verse = inferred_verse + 1
        text = extract_translation(blocks, page_no=page_no)
        verses.append(Verse(page=page_no, chapter=chapter, verse=verse, text=text))
        inferred_verse = verse
    return verses


def markdown_for_verses(verses: list[Verse]) -> str:
    parts = ["# The Bhagavad Gita", ""]
    current = 0
    for verse in verses:
        if verse.chapter != current:
            current = verse.chapter
            parts.extend(["", f"## Chapter {current}: {CHAPTER_TITLES_EN.get(current, '')}".strip(), ""])
        parts.append(f"### {verse.chapter}.{verse.verse}")
        parts.append("")
        parts.append(verse.text)
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def build_chunks(verses: list[Verse], *, reference_chars: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    manifest_chunks: list[dict[str, Any]] = []
    for index, verse in enumerate(verses, start=1):
        paragraph_id = f"{BOOK_ID}-s{verse.chapter:02d}-v{verse.verse:03d}"
        chunk_id = f"{BOOK_ID}-c{index:04d}"
        chapter_title = f"Chapter {verse.chapter}: {CHAPTER_TITLES_EN.get(verse.chapter, '')}".strip()
        chunk = {
            "schema_version": 1,
            "mode": "trilingual_standard",
            "book_id": BOOK_ID,
            "source_spine_lang": "en",
            "chunk_id": chunk_id,
            "chunk_index": index,
            "chapter_id": f"chapter-{verse.chapter:03d}",
            "chapter_number": verse.chapter,
            "chapter_title_en": chapter_title,
            "chapter_title_zh": f"第{verse.chapter}章",
            "chapter_title_ja": f"第{verse.chapter}章",
            "chapter_part_en": f"Bhagavad Gita {verse.chapter}.{verse.verse}",
            "paragraph_ids": [paragraph_id],
            "paragraphs": [{"id": paragraph_id, "en": verse.text}],
            "reference": {
                "english": {
                    "available": True,
                    "chapter": f"{verse.chapter}.{verse.verse}",
                    "text": verse.text[:reference_chars],
                    "quality": "Sargeant English verse translation extracted from the local Sanskrit/English PDF.",
                    "page": verse.page,
                    "source_path": str(EN_SOURCE),
                },
                "sanskrit_scholarly_pdf": {
                    "available": True,
                    "source_path": str(EN_SOURCE),
                    "note": "The same PDF contains Sanskrit, transliteration, word-by-word glosses, and grammatical notes. Use for meaning where helpful; do not copy glossary columns as prose.",
                    "page": verse.page,
                },
                "zh": {
                    "available": False,
                    "source_path": str(ZH_SOURCE),
                    "quality": "Chinese scan/reference PDF; embedded text is not sufficient for automatic chunk windows.",
                    "note": "Generate readable Chinese from the English verse spine unless a later OCR-polished Chinese layer is added.",
                },
                "ja": {
                    "available": False,
                    "note": "No local Japanese translation source was supplied; generate clear modern Japanese from the English verse spine and Sanskrit-aware reference.",
                },
            },
        }
        chunks.append(chunk)
        manifest_chunks.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": index,
                "chapter_number": verse.chapter,
                "chapter_part_en": f"Bhagavad Gita {verse.chapter}.{verse.verse}",
                "paragraph_ids": [paragraph_id],
            }
        )
    return chunks, manifest_chunks


def prepare(force_bbox: bool = False, reference_chars: int = 6000) -> dict[str, Any]:
    book_root = ROOT / "books" / BOOK_ID
    cache_path = book_root / "work/source/bhagavad-gita.bbox.html"
    ensure_bbox(EN_SOURCE, cache_path, force=force_bbox)
    verses = extract_verses(cache_path)
    if len(verses) < 690:
        raise RuntimeError(f"too few extracted Gita verse pages: {len(verses)}")

    chunks, manifest_chunks = build_chunks(verses, reference_chars=reference_chars)
    chunks_jsonl = book_root / "work/trilingual/chunks/chunks.jsonl"
    chunks_jsonl.parent.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    write_text(book_root / "markdown/en.md", markdown_for_verses(verses))

    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "task_mode": "trilingual_en_source_generated_zh_ja",
        "source_spine_lang": "en",
        "book_title_en": "The Bhagavad Gita",
        "book_title_zh": "薄伽梵歌",
        "book_title_ja": "バガヴァッド・ギーター",
        "author": "Vyasa",
        "chunk_count": len(chunks),
        "chapter_count": len({verse.chapter for verse in verses}),
        "source_paths": {
            "en": str(EN_SOURCE),
            "zh": str(ZH_SOURCE),
            "en_markdown": f"books/{BOOK_ID}/markdown/en.md",
        },
        "source_sha256": {
            "en": sha256(EN_SOURCE),
            "zh": sha256(ZH_SOURCE),
        },
        "chunks": manifest_chunks,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "preparation_note": "Verse translation blocks were extracted from Sargeant's Sanskrit/English PDF; Sanskrit glosses remain references, not prose spine.",
    }
    write_json(book_root / "work/trilingual/chunks/manifest.json", manifest)

    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": "trilingual_en_source_generated_zh_ja",
        "source_spine_lang": "en",
        "book_title_en": "The Bhagavad Gita",
        "book_title_zh": "薄伽梵歌",
        "book_title_ja": "バガヴァッド・ギーター",
        "title_zh_reading": "bó qié fàn gē",
        "title_ja_reading": "バガヴァッド ギーター",
        "author": "Vyasa",
        "author_reading_zh": "pí yē suō",
        "author_reading_ja": "ヴィヤーサ",
        "book_description": "The Bhagavad Gita. English verse translations from the Sargeant Sanskrit/English PDF form the source spine; Chinese and modern Japanese are generated for language-learning overlays.",
        "source_paths": manifest["source_paths"],
        "source_sha256": manifest["source_sha256"],
        "chunks_jsonl": f"books/{BOOK_ID}/work/trilingual/chunks/chunks.jsonl",
        "chunks_manifest": f"books/{BOOK_ID}/work/trilingual/chunks/manifest.json",
        "raw_chunk_dir": f"books/{BOOK_ID}/work/trilingual/interlinear/chunks",
        "assembled_json": f"books/{BOOK_ID}/work/trilingual/preview/{BOOK_ID}.partial.json",
        "markdown": {"en": f"books/{BOOK_ID}/markdown/en.md"},
        "reference_chars": reference_chars,
        "prepared_at": manifest["prepared_at"],
        "preparation_notes": {
            "script": "scripts/interlinear/prepare_bhagavad_gita_trilingual.py",
            "english_spine": "English verse translation blocks are extracted from the Sargeant PDF, one chunk per verse page.",
            "sanskrit_reference": "The Sargeant PDF includes Sanskrit, transliteration, word-by-word glosses, and grammar notes as reference only.",
            "chinese_reference": "The Chinese PDF is scanned and retained as a source reference; OCR-polished Chinese can be added later without replacing existing chunks.",
            "japanese_reference": "No Japanese source was supplied; generate natural modern Japanese.",
            "start_command": f"bash scripts/interlinear/start_trilingual_book_tmux.sh {BOOK_ID}",
        },
    }
    write_json(book_root / "book-plan.json", plan)
    return {
        "book_id": BOOK_ID,
        "chunks": len(chunks),
        "chapters": manifest["chapter_count"],
        "first": chunks[0]["chapter_part_en"],
        "last": chunks[-1]["chapter_part_en"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-bbox", action="store_true", help="Regenerate cached pdftotext bbox output.")
    parser.add_argument("--reference-chars", type=int, default=6000)
    args = parser.parse_args()
    result = prepare(force_bbox=args.force_bbox, reference_chars=args.reference_chars)
    print(
        f"prepared book_id={result['book_id']} chunks={result['chunks']} "
        f"chapters={result['chapters']} first={result['first']} last={result['last']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
