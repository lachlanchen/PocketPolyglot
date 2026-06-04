#!/usr/bin/env python3
"""Prepare Spring Snow trilingual EN/JP/ZH chunk tasks."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pdf_text_or_ocr import extract_pdf_text_checked


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "spring-snow"
BOOK_TITLE_EN = "Spring Snow"
BOOK_TITLE_ZH = "春雪"
BOOK_TITLE_JA = "春の雪"
BOOK_TITLE_ZH_READING = "chūn xuě"
BOOK_TITLE_JA_READING = "はるのゆき"
AUTHOR = "三島由紀夫"
AUTHOR_READING_ZH = "sān dǎo yóu jì fū"
AUTHOR_READING_JA = "みしまゆきお"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

EN_SOURCE = Path("sources/春雪 - Spring Snow/Spring Snow.pdf")
ZH_SOURCE = Path("sources/春雪 - Spring Snow/丰饶之海之一·春雪 - 三岛由纪夫 陈德文译.epub")

SPACE_RE = re.compile(r"\s+")
IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)(?:\{[^}]+\})?")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)(?:\{[^}]+\})?")
RT_RE = re.compile(r"<rt[^>]*>.*?</rt>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
BRACED_ID_RE = re.compile(r"\{#[^}]+\}")
ZH_CHAPTER_RE = re.compile(r"^(?:#+\s*)?([一二三四五六七八九十百〇零0-9]{1,4})$")
NOTE_HEADING_RE = re.compile(r"^(?:#+\s*)?(?:注|注释|本章注释|Footnotes?)$")


@dataclass
class Chapter:
    number: int
    title: str
    paragraphs: list[str] = field(default_factory=list)


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT).decode("utf-8", errors="replace")


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


def normalize_paragraph(text: str) -> str:
    text = compact(text)
    text = text.replace(" .", ".").replace(" ,", ",").replace(" ;", ";").replace(" :", ":")
    text = text.replace(" ?", "?").replace(" !", "!")
    return text


def clean_epub_line(raw_line: str) -> str:
    line = raw_line.replace("\u00a0", " ").replace("\u3000", " ")
    line = IMAGE_LINK_RE.sub("", line)
    line = LINK_RE.sub(r"\1", line)
    line = RT_RE.sub("", line)
    line = TAG_RE.sub("", line)
    line = BRACED_ID_RE.sub("", line)
    line = html.unescape(line)
    line = line.replace("\\_", "_").replace("\\-", "-").replace("\\", "")
    return compact(line).strip()


def looks_like_english_prose(line: str) -> bool:
    return len(line) >= 35 and bool(re.search(r"[A-Za-z]", line))


def looks_like_zh_prose(line: str) -> bool:
    return len(line) >= 20 and bool(re.search(r"[\u4e00-\u9fff]", line))


def has_prose_after(lines: list[str], index: int) -> bool:
    for raw in lines[index + 1 : index + 12]:
        stripped = raw.replace("\f", "").strip()
        if looks_like_english_prose(stripped):
            return True
        if stripped and re.fullmatch(r"\d{1,3}", stripped):
            return False
    return False


def parse_english_pdf(path: Path) -> list[Chapter]:
    raw = extract_pdf_text_checked(path, layout=True)
    lines = raw.splitlines()
    chapters: list[Chapter] = []
    current: Chapter | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if current is None or not paragraph_lines:
            paragraph_lines = []
            return
        text = paragraph_lines[0].strip()
        for line in paragraph_lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if text.endswith("-"):
                text += stripped
            else:
                text += " " + stripped
        text = normalize_paragraph(text)
        if text:
            current.paragraphs.append(text)
        paragraph_lines = []

    for index, raw_line in enumerate(lines):
        line = raw_line.replace("\f", "")
        stripped = line.strip()
        if chapters and stripped == "Footnotes":
            break
        expected = len(chapters) + 1
        if re.fullmatch(r"\d{1,2}", stripped) and int(stripped) == expected and has_prose_after(lines, index):
            flush_paragraph()
            current = Chapter(number=expected, title=f"Chapter {expected}")
            chapters.append(current)
            continue
        if current is None:
            continue
        if not stripped:
            continue
        if re.fullmatch(r"\d{1,3}", stripped):
            continue
        if re.match(r"^\s{3,}\S", line) and paragraph_lines:
            flush_paragraph()
        paragraph_lines.append(line)
    flush_paragraph()
    return [chapter for chapter in chapters if chapter.paragraphs]


def cjk_num_to_int(text: str) -> int:
    text = text.strip()
    if text.isdigit():
        return int(text)
    digits = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "百" in text:
        left, _, right = text.partition("百")
        return (cjk_num_to_int(left) if left else 1) * 100 + cjk_num_to_int(right)
    if "十" in text:
        left, _, right = text.partition("十")
        return (cjk_num_to_int(left) if left else 1) * 10 + cjk_num_to_int(right)
    if len(text) > 1:
        value = 0
        for char in text:
            value = value * 10 + digits.get(char, 0)
        return value
    return digits.get(text, 0)


def parse_zh_epub(path: Path) -> list[Chapter]:
    raw = run_text(["pandoc", str(path), "-t", "gfm", "--wrap=none"])
    lines = [clean_epub_line(line) for line in raw.splitlines()]
    chapters: list[Chapter] = []
    current: Chapter | None = None
    in_notes = False
    started = False
    for line in lines:
        if not line:
            continue
        if line.startswith(("书籍信息", "书名：", "作者：", "译者：", "出版社：", "版次：", "ISBN", "一校、排版")):
            continue
        if re.match(r"^\d+[.)、]\s*", line):
            in_notes = True
            continue
        if NOTE_HEADING_RE.match(line):
            in_notes = True
            continue
        chapter_match = ZH_CHAPTER_RE.match(line)
        if chapter_match:
            number = cjk_num_to_int(chapter_match.group(1))
            if number <= 0:
                continue
            current = Chapter(number=number, title=line.lstrip("# ").strip())
            chapters.append(current)
            started = True
            in_notes = False
            continue
        if not started or current is None or in_notes:
            continue
        if line.startswith("chapter") or line.startswith("Text/"):
            continue
        if looks_like_zh_prose(line):
            current.paragraphs.append(line)
    return [chapter for chapter in chapters if chapter.paragraphs]


def markdown_for_chapters(title: str, chapters: list[Chapter]) -> str:
    out = [f"# {title}", ""]
    for chapter in chapters:
        out.extend([f"## {chapter.title}", ""])
        out.extend(chapter.paragraphs)
        out.append("")
    return "\n".join(out).strip() + "\n"


def chapter_text(chapter: Chapter | None) -> str:
    if chapter is None:
        return ""
    return "\n".join(chapter.paragraphs)


def reference_window(chapter: Chapter | None, start_ratio: float, end_ratio: float, *, max_chars: int) -> dict[str, Any]:
    if chapter is None or not chapter.paragraphs:
        return {"available": False, "chapter": "", "text": ""}
    text = chapter_text(chapter)
    if len(text) <= max_chars:
        return {"available": True, "chapter": chapter.title, "text": text}
    start = max(0, int(len(text) * start_ratio) - max_chars // 4)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        extra = max_chars - (end - start)
        start = max(0, start - extra // 2)
        end = min(len(text), end + extra // 2)
    return {"available": True, "chapter": chapter.title, "text": text[start:end]}


def make_chunks(
    en_chapters: list[Chapter],
    zh_by_number: dict[int, Chapter],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    paragraph_count = 0
    for chapter in en_chapters:
        char_offsets: list[int] = []
        cursor = 0
        for paragraph in chapter.paragraphs:
            char_offsets.append(cursor)
            cursor += len(paragraph) + 1
        chapter_total = max(cursor, 1)
        pending: list[dict[str, str]] = []
        pending_start = 0
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_start, pending_chars
            if not pending:
                return
            chunk_number = len(chunks) + 1
            chunk_id = f"{BOOK_ID}-c{chunk_number:04d}"
            start_ratio = pending_start / chapter_total
            end_ratio = min(1.0, (pending_start + pending_chars) / chapter_total)
            zh_ref = reference_window(zh_by_number.get(chapter.number), start_ratio, end_ratio, max_chars=reference_chars)
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": BOOK_ID,
                    "source_spine_lang": "en",
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_number,
                    "chapter_id": f"chapter-{chapter.number:03d}",
                    "chapter_number": chapter.number,
                    "chapter_title_en": chapter.title,
                    "chapter_part_en": "",
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": list(pending),
                    "reference": {
                        "english": {
                            "available": True,
                            "chapter": chapter.title,
                            "text": "\n".join(item["en"] for item in pending),
                        },
                        "zh_primary": zh_ref,
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": {
                            "available": False,
                            "chapter": "",
                            "text": "",
                            "note": "No local Japanese source is available; generate Japanese from English spine and Chinese reference.",
                        },
                    },
                }
            )
            pending = []
            pending_chars = 0

        for paragraph_index, paragraph in enumerate(chapter.paragraphs, start=1):
            paragraph_count += 1
            paragraph_id = f"{BOOK_ID}-c{chapter.number:03d}-p{paragraph_index:04d}"
            entry = {"id": paragraph_id, "en": paragraph}
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
            if not pending:
                pending_start = char_offsets[paragraph_index - 1]
            pending.append(entry)
            pending_chars += len(paragraph) + 1
        flush()

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
            "English PDF is the alignment spine. Chinese EPUB is the reference/meaning layer. "
            "Japanese is generated from the English spine and Chinese reference."
        ),
        "chapter_count": len(en_chapters),
        "paragraph_count": paragraph_count,
        "chunk_count": len(chunks),
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
    parser.add_argument("--reference-chars", type=int, default=7000)
    args = parser.parse_args()

    en_chapters = parse_english_pdf(EN_SOURCE)
    zh_chapters = parse_zh_epub(ZH_SOURCE)
    if not en_chapters:
        raise RuntimeError("no English chapters parsed")
    if not zh_chapters:
        raise RuntimeError("no Chinese chapters parsed")

    book_root = Path("books") / BOOK_ID
    markdown_dir = book_root / "markdown"
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"

    write_text(markdown_dir / "en.md", markdown_for_chapters(BOOK_TITLE_EN, en_chapters))
    write_text(markdown_dir / "zh.md", markdown_for_chapters(BOOK_TITLE_ZH, zh_chapters))

    manifest, chunks = make_chunks(
        en_chapters,
        {chapter.number: chapter for chapter in zh_chapters},
        max_chunk_chars=args.max_chunk_chars,
        reference_chars=args.reference_chars,
    )
    write_json(chunks_dir / "manifest.json", manifest)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": "trilingual_en_spine_generated_ja",
        "source_spine_lang": "en",
        "source_paths": {"en": str(EN_SOURCE), "zh": str(ZH_SOURCE)},
        "source_sha256": manifest["source_sha256"],
        "markdown": {"en": str(markdown_dir / "en.md"), "zh": str(markdown_dir / "zh.md")},
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
            "Yukio Mishima, Spring Snow. English source is the alignment spine; "
            "Chinese EPUB translation is used as a reference; Japanese is generated."
        ),
        "chunk_mode": "paragraph_group",
        "reference_scope": "chapter_ratio_window",
        "chunks_jsonl": str(chunks_dir / "chunks.jsonl"),
        "chunks_manifest": str(chunks_dir / "manifest.json"),
        "raw_chunk_dir": str(raw_chunk_dir),
        "preview_json": str(preview_dir / f"{BOOK_ID}.partial.json"),
        "assembled_json": str(preview_dir / f"{BOOK_ID}.partial.json"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "english_chapter_count": len(en_chapters),
        "chinese_chapter_count": len(zh_chapters),
    }
    write_json(book_root / "book-plan.json", plan)

    print(f"book_id={BOOK_ID}")
    print(f"english_chapters={len(en_chapters)} chinese_chapters={len(zh_chapters)}")
    print(f"chunks={len(chunks)}")
    print(f"manifest={chunks_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
