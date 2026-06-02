#!/usr/bin/env python3
"""Prepare trilingual Gone With the Wind markdown, manifest, and chunk tasks."""

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


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "gone-with-the-wind"
BOOK_TITLE_EN = "Gone With the Wind"
BOOK_TITLE_ZH = "飘"
BOOK_TITLE_JA = "風と共に去りぬ"
AUTHOR = "Margaret Mitchell"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

EN_SOURCE = Path("sources/gone-with-the-wind/Gone With the Wind.pdf")
ZH_PRIMARY_SOURCE = Path("sources/gone-with-the-wind/飘.epub")
ZH_SECONDARY_SOURCE = Path("sources/gone-with-the-wind/乱世佳人.epub")
JA_SOURCES = [
    Path("sources/gone-with-the-wind/風と共に去りぬ（一）.epub"),
    Path("sources/gone-with-the-wind/風と共に去りぬ 第2巻（新潮文庫）.epub"),
]

LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
RT_RE = re.compile(r"<rt[^>]*>.*?</rt>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
CHAPTER_EN_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+)$")
PART_EN_RE = re.compile(r"^Part\s+(.+)$")
ZH_PART_RE = re.compile(r"^第[一二三四五六七八九十百〇零0-9]+部$")
ZH_CHAPTER_RE = re.compile(r"^第\s*([一二三四五六七八九十百〇零0-9]+)\s*章$")
JA_PART_RE = re.compile(r"^#?\s*第[一二三四五六七八九十百〇零0-9]+部(?:（承前）)?$")
JA_CHAPTER_RE = re.compile(r"^(?:#\s*)?([一二三四五六七八九十〇零0-9]{1,4})$")
NOTE_HEADING_RE = re.compile(r"^(?:本章)?注\s*释$|^注\s*釈$|^注$")

ROMAN = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}
CN_DIGITS = {
    "〇": 0,
    "零": 0,
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


@dataclass
class Chapter:
    number: int
    title: str
    part: str = ""
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


def roman_to_int(text: str) -> int:
    total = 0
    prev = 0
    for char in reversed(text.upper()):
        value = ROMAN[char]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def cjk_num_to_int(text: str) -> int:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text:
        return 0
    if "〇" in text or "零" in text:
        value = 0
        for char in text:
            value = value * 10 + CN_DIGITS.get(char, 0)
        return value
    if "百" in text:
        left, _, right = text.partition("百")
        hundreds = cjk_num_to_int(left) if left else 1
        return hundreds * 100 + cjk_num_to_int(right)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = cjk_num_to_int(left) if left else 1
        return tens * 10 + cjk_num_to_int(right)
    if len(text) > 1:
        value = 0
        for char in text:
            value = value * 10 + CN_DIGITS.get(char, 0)
        return value
    return CN_DIGITS.get(text, 0)


def clean_epub_line(raw_line: str) -> str:
    line = raw_line.replace("\u00a0", " ").replace("\u3000", " ")
    line = LINK_RE.sub(r"\1", line)
    line = RT_RE.sub("", line)
    line = TAG_RE.sub("", line)
    line = html.unescape(line)
    line = re.sub(r"\s+", " ", line).strip()
    line = line.strip("　 ")
    if line.startswith(">"):
        line = line.lstrip("> ").strip()
    return line


def epub_lines(path: Path) -> list[str]:
    raw = run_text(["pandoc", str(path), "-t", "gfm", "--wrap=none"])
    lines: list[str] = []
    for raw_line in raw.splitlines():
        line = clean_epub_line(raw_line)
        if not line:
            continue
        if line.startswith("![]("):
            continue
        if line in {"目次", "目录", "CONTENTS·目 录", "CONTENTS·目　录"}:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            continue
        lines.append(line)
    return lines


def looks_like_prose(line: str, lang: str) -> bool:
    if lang == "zh":
        return len(line) >= 30 and bool(re.search(r"[\u4e00-\u9fff]", line))
    if lang == "ja":
        return len(line) >= 25 and bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", line))
    return len(line) >= 40


def find_body_start(lines: list[str], heading_re: re.Pattern[str], lang: str) -> int:
    for index, line in enumerate(lines):
        if not heading_re.match(line):
            continue
        window = lines[index + 1 : index + 35]
        if sum(1 for item in window if looks_like_prose(item, lang)) >= 1:
            return index
    return 0


def is_heading_line(line: str, lang: str) -> bool:
    if lang == "zh":
        return bool(ZH_PART_RE.match(line) or ZH_CHAPTER_RE.match(line) or NOTE_HEADING_RE.match(line))
    if lang == "ja":
        return bool(JA_PART_RE.match(line) or (len(line) <= 4 and JA_CHAPTER_RE.match(line)))
    return False


def is_chapter_heading_line(line: str, lang: str) -> bool:
    if lang == "zh":
        return bool(ZH_CHAPTER_RE.match(line))
    if lang == "ja":
        return bool(len(line) <= 4 and JA_CHAPTER_RE.match(line))
    return False


def find_body_chapter_start(lines: list[str], chapter_re: re.Pattern[str], lang: str) -> int:
    """Find the first real body chapter, not the table-of-contents copy."""

    for index, line in enumerate(lines):
        if lang == "ja" and len(line) > 4:
            continue
        if not chapter_re.match(line):
            continue
        if index > 0 and is_chapter_heading_line(lines[index - 1], lang):
            continue
        for following in lines[index + 1 : index + 10]:
            if is_heading_line(following, lang):
                break
            if looks_like_prose(following, lang):
                return index
    return find_body_start(lines, chapter_re, lang)


def nearest_previous_part(lines: list[str], start: int, lang: str) -> str:
    part_re = ZH_PART_RE if lang == "zh" else JA_PART_RE
    for index in range(start - 1, max(-1, start - 20), -1):
        if part_re.match(lines[index]):
            return lines[index].lstrip("# ").strip()
    return ""


def normalize_paragraph(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" .", ".").replace(" ,", ",").replace(" ;", ";").replace(" :", ":")
    text = text.replace(" ?", "?").replace(" !", "!")
    return text


def parse_english_pdf(path: Path) -> list[Chapter]:
    raw = run_text(["pdftotext", "-layout", str(path), "-"])
    chapters: list[Chapter] = []
    current: Chapter | None = None
    current_part = ""
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

    started = False
    for raw_line in raw.splitlines():
        line = raw_line.replace("\f", "")
        stripped = line.strip()
        part_match = PART_EN_RE.match(stripped)
        if part_match:
            started = True
            flush_paragraph()
            current_part = f"Part {part_match.group(1)}"
            continue
        chapter_match = CHAPTER_EN_RE.match(stripped)
        if chapter_match:
            started = True
            flush_paragraph()
            number = roman_to_int(chapter_match.group(1))
            current = Chapter(number=number, title=f"Chapter {number}", part=current_part)
            chapters.append(current)
            continue
        if not started or current is None:
            continue
        if not stripped:
            continue
        if re.match(r"^\s{4,}\S", line) and paragraph_lines:
            flush_paragraph()
        paragraph_lines.append(line)
    flush_paragraph()
    return chapters


def parse_zh_epub(path: Path, *, numeric: bool = False) -> list[Chapter]:
    lines = epub_lines(path)
    start = find_body_chapter_start(lines, ZH_CHAPTER_RE, "zh")
    chapters: list[Chapter] = []
    current: Chapter | None = None
    current_part = nearest_previous_part(lines, start, "zh")
    in_notes = False
    for line in lines[start:]:
        if NOTE_HEADING_RE.match(line):
            in_notes = True
            continue
        if ZH_PART_RE.match(line):
            current_part = line
            in_notes = False
            continue
        chapter_match = ZH_CHAPTER_RE.match(line)
        if chapter_match:
            number = cjk_num_to_int(chapter_match.group(1))
            current = Chapter(number=number, title=line, part=current_part)
            chapters.append(current)
            in_notes = False
            continue
        if current is None or in_notes:
            continue
        if "本章注释" in line or line in {"注 释", "注释", "注　释"}:
            in_notes = True
            continue
        if line.startswith("第") and "章" in line and len(line) < 16:
            continue
        if looks_like_prose(line, "zh"):
            current.paragraphs.append(line.strip())
    return dedupe_nonempty_chapters(chapters)


def parse_ja_epubs(paths: list[Path]) -> list[Chapter]:
    chapters: list[Chapter] = []
    current_part = ""
    for path in paths:
        lines = epub_lines(path)
        start = find_body_chapter_start(lines, JA_CHAPTER_RE, "ja")
        current: Chapter | None = None
        current_part = nearest_previous_part(lines, start, "ja")
        for line in lines[start:]:
            if "本作品には現在の観点から見て" in line:
                break
            if JA_PART_RE.match(line):
                current_part = line.lstrip("# ").strip()
                continue
            chapter_match = JA_CHAPTER_RE.match(line)
            if chapter_match and len(line) <= 4:
                number = cjk_num_to_int(chapter_match.group(1))
                if number <= 0:
                    continue
                current = Chapter(number=number, title=line.lstrip("# ").strip(), part=current_part)
                chapters.append(current)
                continue
            if current is None:
                continue
            if looks_like_prose(line, "ja"):
                current.paragraphs.append(line.strip())
    return dedupe_nonempty_chapters(chapters)


def dedupe_nonempty_chapters(chapters: list[Chapter]) -> list[Chapter]:
    deduped: dict[int, Chapter] = {}
    for chapter in chapters:
        existing = deduped.get(chapter.number)
        if existing is None:
            deduped[chapter.number] = chapter
        elif not existing.paragraphs and chapter.paragraphs:
            deduped[chapter.number] = chapter
    return [deduped[number] for number in sorted(deduped)]


def markdown_for_chapters(title: str, chapters: list[Chapter]) -> str:
    out = [f"# {title}", ""]
    last_part = ""
    for chapter in chapters:
        if chapter.part and chapter.part != last_part:
            out.extend([f"## {chapter.part}", ""])
            last_part = chapter.part
        out.extend([f"### {chapter.title}", ""])
        out.extend(chapter.paragraphs)
        out.append("")
    return "\n".join(out).strip() + "\n"


def chapter_by_number(chapters: list[Chapter]) -> dict[int, Chapter]:
    return {chapter.number: chapter for chapter in dedupe_nonempty_chapters(chapters)}


def chapter_text(chapter: Chapter | None) -> str:
    if chapter is None:
        return ""
    return "\n".join(chapter.paragraphs)


def reference_window(chapter: Chapter | None, start_ratio: float, end_ratio: float, *, max_chars: int) -> dict[str, Any]:
    if chapter is None or not chapter.paragraphs:
        return {"available": False, "chapter": "", "text": ""}
    text = chapter_text(chapter)
    if len(text) <= max_chars:
        return {"available": True, "chapter": chapter.title, "part": chapter.part, "text": text}
    start = max(0, int(len(text) * start_ratio) - max_chars // 4)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        extra = max_chars - (end - start)
        start = max(0, start - extra // 2)
        end = min(len(text), end + extra // 2)
    return {"available": True, "chapter": chapter.title, "part": chapter.part, "text": text[start:end]}


def make_chunks(
    en_chapters: list[Chapter],
    zh_primary: dict[int, Chapter],
    zh_secondary: dict[int, Chapter],
    ja: dict[int, Chapter],
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
            start_ratio = pending_start / chapter_total
            end_ratio = min(1.0, (pending_start + pending_chars) / chapter_total)
            chunk_id = f"{BOOK_ID}-c{chunk_number:04d}"
            item = {
                "schema_version": 1,
                "mode": "trilingual_standard",
                "book_id": BOOK_ID,
                "chunk_id": chunk_id,
                "chunk_index": chunk_number,
                "chapter_id": f"chapter-{chapter.number:03d}",
                "chapter_number": chapter.number,
                "chapter_title_en": chapter.title,
                "chapter_part_en": chapter.part,
                "paragraph_ids": [paragraph["id"] for paragraph in pending],
                "paragraphs": list(pending),
                "reference": {
                    "english_standard_note": "English is the alignment spine. Preserve and reconstruct these English paragraphs exactly.",
                    "zh_primary": reference_window(zh_primary.get(chapter.number), start_ratio, end_ratio, max_chars=reference_chars),
                    "zh_secondary": reference_window(zh_secondary.get(chapter.number), start_ratio, end_ratio, max_chars=reference_chars),
                    "ja": reference_window(ja.get(chapter.number), start_ratio, end_ratio, max_chars=reference_chars),
                },
            }
            chunks.append(item)
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
            pending_chars += len(paragraph)
        flush()

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "author": AUTHOR,
        "source_paths": {
            "en": str(EN_SOURCE),
            "zh_primary": str(ZH_PRIMARY_SOURCE),
            "zh_secondary": str(ZH_SECONDARY_SOURCE),
            "ja": [str(path) for path in JA_SOURCES],
        },
        "source_sha256": {
            "en": sha256(EN_SOURCE),
            "zh_primary": sha256(ZH_PRIMARY_SOURCE),
            "zh_secondary": sha256(ZH_SECONDARY_SOURCE),
            "ja": [sha256(path) for path in JA_SOURCES],
        },
        "chapter_count": len(en_chapters),
        "paragraph_count": paragraph_count,
        "chunk_count": len(chunks),
        "japanese_reference_chapters": sorted(ja),
        "japanese_reference_note": "Only supplied Japanese volumes are referenced. Later chapters without Japanese source are generated from English standard plus Chinese references.",
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
    parser.add_argument("--max-chunk-chars", type=int, default=1600)
    parser.add_argument("--reference-chars", type=int, default=4200)
    args = parser.parse_args()

    markdown_dir = ROOT / "books" / BOOK_ID / "markdown"
    work_chunk_dir = ROOT / "books" / BOOK_ID / "work" / "trilingual" / "chunks"

    en_chapters = parse_english_pdf(EN_SOURCE)
    zh_primary_chapters = parse_zh_epub(ZH_PRIMARY_SOURCE)
    zh_secondary_chapters = parse_zh_epub(ZH_SECONDARY_SOURCE, numeric=True)
    ja_chapters = parse_ja_epubs(JA_SOURCES)

    write_text(markdown_dir / "en.md", markdown_for_chapters(BOOK_TITLE_EN, en_chapters))
    write_text(markdown_dir / "zh.md", markdown_for_chapters(BOOK_TITLE_ZH, zh_primary_chapters))
    write_text(markdown_dir / "zh.reference.md", markdown_for_chapters("乱世佳人", zh_secondary_chapters))
    write_text(markdown_dir / "ja.md", markdown_for_chapters(BOOK_TITLE_JA, ja_chapters))

    manifest, chunks = make_chunks(
        en_chapters,
        chapter_by_number(zh_primary_chapters),
        chapter_by_number(zh_secondary_chapters),
        chapter_by_number(ja_chapters),
        max_chunk_chars=args.max_chunk_chars,
        reference_chars=args.reference_chars,
    )
    write_json(work_chunk_dir / "manifest.json", manifest)
    work_chunk_dir.mkdir(parents=True, exist_ok=True)
    (work_chunk_dir / "chunks.jsonl").write_text(
        "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )

    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "launchable": True,
        "task_mode": "trilingual_standard",
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "book_title_zh_reading": "piāo",
        "book_title_ja_reading": "かぜ と とも に さ り ぬ",
        "author": AUTHOR,
        "author_reading_ja": "マーガレット ミッチェル",
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "markdown": {
            "en": f"books/{BOOK_ID}/markdown/en.md",
            "zh": f"books/{BOOK_ID}/markdown/zh.md",
            "zh_reference": f"books/{BOOK_ID}/markdown/zh.reference.md",
            "ja": f"books/{BOOK_ID}/markdown/ja.md",
        },
        "chunks_manifest": f"books/{BOOK_ID}/work/trilingual/chunks/manifest.json",
        "chunks_jsonl": f"books/{BOOK_ID}/work/trilingual/chunks/chunks.jsonl",
        "raw_chunk_dir": f"books/{BOOK_ID}/work/trilingual/interlinear/chunks",
        "assembled_json": f"books/{BOOK_ID}/work/trilingual/preview/{BOOK_ID}.partial.json",
        "build_root": f"build/{BOOK_ID}",
        "source_paths": manifest["source_paths"],
        "source_sha256": manifest["source_sha256"],
        "chapter_count": manifest["chapter_count"],
        "paragraph_count": manifest["paragraph_count"],
        "chunk_count": manifest["chunk_count"],
    }
    write_json(ROOT / "books" / BOOK_ID / "book-plan.json", plan)

    print(f"book_id={BOOK_ID}")
    print(f"chapters={manifest['chapter_count']}")
    print(f"paragraphs={manifest['paragraph_count']}")
    print(f"chunks={manifest['chunk_count']}")
    print(f"japanese_reference_chapters={manifest['japanese_reference_chapters']}")
    print(f"manifest={plan['chunks_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
