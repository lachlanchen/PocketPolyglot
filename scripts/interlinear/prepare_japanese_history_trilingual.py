#!/usr/bin/env python3
"""Prepare A Concise History of Japan trilingual EN/JP/ZH chunk tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from english_sentence_splitter import sentence_boundary_ends


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "japanese-history"
BOOK_TITLE_EN = "A Concise History of Japan"
BOOK_TITLE_ZH = "日本史"
BOOK_TITLE_JA = "日本史"
BOOK_TITLE_ZH_READING = "rì běn shǐ"
BOOK_TITLE_JA_READING = "にほんし"
AUTHOR = "Brett L. Walker"
AUTHOR_READING_ZH = "bù léi tè L. wò kè"
AUTHOR_READING_JA = "ブレット L. ウォーカー"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

EN_SOURCE = Path("sources/japanese-history/A Concise History of Japan.epub")
ZH_SOURCE = Path("sources/japanese-history/[美]布雷特 L 沃克.日本史.pdf")
ZH_OCR_MARKDOWN = Path("books/japanese-history/work/ocr/zh.raw.md")

SPACE_RE = re.compile(r"\s+")
BRACKET_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)(?:\{[^}]+\})?")
BRACED_ID_RE = re.compile(r"\{#[^}]+\}")
RT_RE = re.compile(r"<rt[^>]*>.*?</rt>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
EN_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?]["”’)]*\s+')
PAGE_HEADING_RE = re.compile(r"^## Page \d+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

CHAPTER_TITLES = {
    1: "The Birth of the Yamato State, 14,500 BCE – 710 CE",
    2: "The Courtly Age, 710–1185",
    3: "The Rise of Samurai Rule, 1185–1336",
    4: "Medieval Japan and the Warring States Period, 1336–1573",
    5: "Japan’s Encounter with Europe, 1543–1640",
    6: "Unifying the Realm, 1560–1603",
    7: "Early Modern Japan, 1600–1800",
    8: "The Rise of Imperial Nationalism, 1770–1854",
    9: "Meiji Enlightenment, 1868–1912",
    10: "Meiji’s Discontents, 1868–1920",
    11: "The Birth of Japan’s Imperial State, 1800–1910",
    12: "Empire and Imperial Democracy, 1905–1931",
    13: "The Pacific War, 1931–1945",
    14: "Japan’s Post-War History, 1945–Present",
    15: "Natural Disasters and the Edge of History",
}
ASCII_CHAPTER_TITLES = {number: title.replace("–", "-").replace("’", "'") for number, title in CHAPTER_TITLES.items()}
STOP_HEADINGS = {"Glossary", "Further Reading", "Index"}
DROP_HEADINGS = {"Preface", "Chronology", "List of Illustrations", "List of Maps", "Contents"}
OCR_NOISE_PREFIXES = (
    "OCR:",
    "source_pdf:",
    "source_pages:",
    "total_pdf_pages:",
    "ocr_engine:",
    "ocr_language:",
    "ocr_psm:",
    "dpi:",
    "generated_at:",
    "conversion:",
    "notes:",
)


@dataclass
class Chapter:
    number: int
    title: str
    paragraphs: list[str] = field(default_factory=list)


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT).decode("utf-8", errors="replace")


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, cwd=ROOT)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", str(text).replace("\u00a0", " ").replace("\u3000", " ")).strip()


def clean_epub_line(line: str) -> str:
    line = line.replace("\\_", "_").replace("\\-", "-").replace("\\", "")
    line = BRACKET_LINK_RE.sub(r"\1", line)
    line = BRACED_ID_RE.sub("", line)
    line = RT_RE.sub("", line)
    line = TAG_RE.sub("", line)
    line = line.strip("> ")
    return compact(line)


def normalize_title(text: str) -> str:
    return compact(text).replace("–", "-").replace("’", "'")


def chapter_match(line: str) -> tuple[int, str] | None:
    normalized = normalize_title(line)
    normalized = re.sub(r"^\[?([0-9]{1,2})\s*\]?\s+", r"\1 ", normalized)
    match = re.match(r"^([0-9]{1,2})\s+(.+)$", normalized)
    if not match:
        return None
    number = int(match.group(1))
    expected = ASCII_CHAPTER_TITLES.get(number)
    if expected and normalize_title(match.group(2)) == expected:
        return number, CHAPTER_TITLES[number]
    return None


def split_english_units(text: str, *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    for end in sentence_boundary_ends(text):
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    if not pieces:
        pieces = [text]

    out: list[str] = []
    pending = ""
    for piece in pieces:
        if pending and len(pending) + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = f"{pending} {piece}".strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def parse_en_epub(path: Path) -> list[Chapter]:
    raw = run_text(["pandoc", str(path), "-t", "plain", "--wrap=none"])
    chapters: list[Chapter] = []
    current: Chapter | None = None
    in_body = False
    expecting_intro_subtitle = False
    skip_possible_caption = False

    for raw_line in raw.splitlines():
        line = clean_epub_line(raw_line)
        if not line:
            continue
        if line == "[]":
            skip_possible_caption = True
            continue
        if line in DROP_HEADINGS and not in_body:
            current = None
            continue
        if line == "Introduction":
            in_body = True
            expecting_intro_subtitle = True
            current = Chapter(number=0, title="Introduction: Writing Japanese History")
            chapters.append(current)
            continue
        if expecting_intro_subtitle and line == "Writing Japanese History":
            expecting_intro_subtitle = False
            continue
        if not in_body:
            continue
        if line in STOP_HEADINGS:
            break
        match = chapter_match(line)
        if match:
            number, title = match
            current = Chapter(number=number, title=title)
            chapters.append(current)
            skip_possible_caption = False
            continue
        if skip_possible_caption and re.match(r"^\d{1,2}\s+.+", line):
            skip_possible_caption = False
            continue
        skip_possible_caption = False
        if current is None:
            continue
        if line.startswith(("+---", "|")):
            continue
        if len(line) <= 2:
            continue
        current.paragraphs.extend(split_english_units(line, max_chars=900))
    return [chapter for chapter in chapters if chapter.paragraphs]


def ensure_zh_ocr() -> Path:
    if (ROOT / ZH_OCR_MARKDOWN).exists():
        return ZH_OCR_MARKDOWN
    run(
        [
            "python",
            "scripts/interlinear/pdf_text_or_ocr.py",
            str(ZH_SOURCE),
            "--output",
            str(ZH_OCR_MARKDOWN),
            "--title",
            BOOK_TITLE_ZH,
            "--ocr-lang",
            "chi_sim",
            "--ocr-psm",
            "4",
            "--ocr-dpi",
            "220",
            "--ocr-workers",
            "8",
            "--ocr-pages",
            "all",
        ]
    )
    return ZH_OCR_MARKDOWN


def clean_ocr_line(line: str) -> str:
    line = compact(line.strip("- "))
    if not line or line == "---" or line.startswith("#"):
        return ""
    if PAGE_HEADING_RE.match(line):
        return ""
    if any(line.startswith(prefix) for prefix in OCR_NOISE_PREFIXES):
        return ""
    if re.fullmatch(r"\d{1,4}", line):
        return ""
    if line in {"日 本 史", "日本史"}:
        return ""
    if line.startswith(("@", "印 ", "四 ", "图 ", "国 ", "回 ", "加”", "D ")):
        return ""
    line = re.sub(r"^\d{1,3}\s+(?=[\u4e00-\u9fff])", "", line)
    if len(line) < 4 and not CJK_RE.search(line):
        return ""
    return line


def parse_zh_ocr(path: Path) -> list[Chapter]:
    full_path = ROOT / path
    lines: list[str] = []
    started = False
    for raw_line in full_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = clean_ocr_line(raw_line)
        if not line:
            continue
        if not started:
            if line.startswith("导论") and "书写日本" in line and "/" not in line:
                started = True
                lines.append("导论：书写日本历史")
            continue
        if line == "索引":
            break
        lines.append(line)
    if not lines:
        raise RuntimeError(f"no usable OCR lines parsed from {path}")
    return [Chapter(number=1, title="OCR reference", paragraphs=lines)]


def markdown_for_chapters(title: str, chapters: list[Chapter]) -> str:
    out = [f"# {title}", ""]
    for chapter in chapters:
        out.extend([f"## {chapter.title}", ""])
        out.extend(chapter.paragraphs)
        out.append("")
    return "\n".join(out).strip() + "\n"


def all_text(chapters: list[Chapter]) -> str:
    return "\n".join(paragraph for chapter in chapters for paragraph in chapter.paragraphs)


def reference_window(text: str, start_ratio: float, end_ratio: float, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    start = max(0, int(len(text) * start_ratio) - max_chars // 3)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        extra = max_chars - (end - start)
        start = max(0, start - extra // 2)
        end = min(len(text), end + extra // 2)
    return text[start:end]


def make_chunks(
    en_chapters: list[Chapter],
    zh_chapters: list[Chapter],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    zh_text = all_text(zh_chapters)
    total_en_chars = max(sum(len(p) + 1 for c in en_chapters for p in c.paragraphs), 1)
    global_cursor = 0
    paragraph_count = 0

    for chapter in en_chapters:
        pending: list[dict[str, str]] = []
        pending_start = global_cursor
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_start, pending_chars
            if not pending:
                return
            chunk_number = len(chunks) + 1
            chunk_id = f"{BOOK_ID}-c{chunk_number:04d}"
            start_ratio = pending_start / total_en_chars
            end_ratio = min(1.0, (pending_start + pending_chars) / total_en_chars)
            zh_ref = reference_window(zh_text, start_ratio, end_ratio, max_chars=reference_chars)
            en_ref = "\n".join(item["en"] for item in pending)
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": BOOK_ID,
                    "source_spine_lang": "en",
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_number,
                    "chapter_id": f"chapter-{chapter.number:02d}",
                    "chapter_number": chapter.number,
                    "chapter_title_en": chapter.title,
                    "chapter_part_en": "",
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": {
                        "english": {"available": True, "chapter": chapter.title, "text": en_ref},
                        "zh_primary": {
                            "available": bool(zh_ref),
                            "chapter": "ocr-ratio-window",
                            "text": zh_ref,
                            "quality": "scanned_ocr_noisy",
                        },
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": {"available": False, "chapter": "", "text": ""},
                    },
                }
            )
            pending = []
            pending_chars = 0

        for paragraph in chapter.paragraphs:
            paragraph_count += 1
            paragraph_id = f"{BOOK_ID}-s{chapter.number:02d}-p{paragraph_count:04d}"
            piece = {"id": paragraph_id, "en": paragraph}
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
                pending_start = global_cursor
            if not pending:
                pending_start = global_cursor
            pending.append(piece)
            pending_chars += len(paragraph) + 1
            global_cursor += len(paragraph) + 1
        flush()

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "book_title_zh_reading": BOOK_TITLE_ZH_READING,
        "book_title_ja_reading": BOOK_TITLE_JA_READING,
        "author": AUTHOR,
        "author_reading_zh": AUTHOR_READING_ZH,
        "author_reading_ja": AUTHOR_READING_JA,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": "en",
        "source_paths": {"en": str(EN_SOURCE), "zh": str(ZH_SOURCE)},
        "source_sha256": {"en": sha256(EN_SOURCE), "zh": sha256(ZH_SOURCE)},
        "source_note": (
            "English is the alignment spine. Chinese is supplied as a scanned PDF OCR reference window; "
            "Japanese is generated from the English spine with the Chinese reference. Treat OCR as helpful but noisy."
        ),
        "chunk_count": len(chunks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "chapter_id": chunk["chapter_id"],
                "chapter_number": chunk["chapter_number"],
                "paragraph_ids": chunk["paragraph_ids"],
            }
            for chunk in chunks
        ],
    }
    return manifest, chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--reference-chars", type=int, default=8000)
    args = parser.parse_args()

    en_chapters = parse_en_epub(EN_SOURCE)
    zh_chapters = parse_zh_ocr(ensure_zh_ocr())
    if not en_chapters:
        raise RuntimeError("no English chapters parsed")
    if not zh_chapters:
        raise RuntimeError("no Chinese OCR reference parsed")

    book_root = Path("books") / BOOK_ID
    write_text(book_root / "markdown/en.md", markdown_for_chapters(BOOK_TITLE_EN, en_chapters))
    write_text(book_root / "markdown/zh.md", markdown_for_chapters(BOOK_TITLE_ZH, zh_chapters))

    manifest, chunks = make_chunks(
        en_chapters,
        zh_chapters,
        max_chunk_chars=args.max_chunk_chars,
        reference_chars=args.reference_chars,
    )
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"
    write_json(chunks_dir / "manifest.json", manifest)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )

    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": "trilingual_en_spine_generated_ja_with_ocr_zh_reference",
        "source_spine_lang": "en",
        "source_paths": {"en": str(EN_SOURCE), "zh": str(ZH_SOURCE)},
        "source_sha256": manifest["source_sha256"],
        "markdown": {"en": str(book_root / "markdown/en.md"), "zh": str(book_root / "markdown/zh.md")},
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "book_title_zh_reading": BOOK_TITLE_ZH_READING,
        "book_title_ja_reading": BOOK_TITLE_JA_READING,
        "author": AUTHOR,
        "author_reading_zh": AUTHOR_READING_ZH,
        "author_reading_ja": AUTHOR_READING_JA,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "book_description": (
            "Brett L. Walker, A Concise History of Japan. English EPUB is the alignment spine; "
            "Chinese scanned PDF OCR is a noisy reference; Japanese is generated."
        ),
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": "global_ratio_window",
        "chunks_jsonl": str(chunks_dir / "chunks.jsonl"),
        "chunks_manifest": str(chunks_dir / "manifest.json"),
        "raw_chunk_dir": str(raw_chunk_dir),
        "preview_json": str(preview_dir / f"{BOOK_ID}.partial.json"),
        "assembled_json": str(preview_dir / f"{BOOK_ID}.partial.json"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "english_chapter_count": len(en_chapters),
        "chinese_reference_chapter_count": len(zh_chapters),
    }
    write_json(book_root / "book-plan.json", plan)
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    print(f"book_id={BOOK_ID}")
    print(f"english_chapters={len(en_chapters)} chinese_reference_sections={len(zh_chapters)}")
    print(f"chunks={len(chunks)}")
    print(f"manifest={chunks_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
