#!/usr/bin/env python3
"""Prepare Zizhi Tongjian as a wenyan-main quadrilingual task.

The local source is a single full-text PDF of the Hu Sanxing annotated edition.
This preparer uses the PDF text layer, removes copyright/TOC front matter, keeps
the real prefaces/body/appendices in source order, and writes a resumable
quadrilingual manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "zizhi-tongjian"
SOURCE_PDF = ROOT / "sources/zizhi-tongjian/zh/資治通鑑·繁體橫排版（胡三省注）294卷全.pdf"
EN_REFS = [
    ROOT / "sources/zizhi-tongjian/en/A Hundred Years of Han vol.1 - Zizhi Tongjian Later Han 57-156.pdf",
    ROOT / "sources/zizhi-tongjian/en/Emperor Huan and Emperor Ling - Zizhi Tongjian Later Han 157-189.pdf",
    ROOT / "sources/zizhi-tongjian/en/To Establish Peace - Zizhi Tongjian Later Han 189-220.pdf",
]
EXTRACTED_TEXT = ROOT / "books/zizhi-tongjian/work/source-extract/zizhi-tongjian.pdftotext.txt"

SPACE_RE = re.compile(r"\s+")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
VOLUME_RE = re.compile(r"^資治通鑑卷第[一二三四五六七八九十百〇零]+$")
SUBTITLE_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{1,6}[紀記][一二三四五六七八九十百〇零]+$")
SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]")

PREFACE_TITLES = {
    "胡刻通鑑正文校宋記述略",
    "新註資治通鑑序",
    "興文署新刊資治通鑑序",
    "宋神宗資治通鑑序 禦製",
    "宋神宗資治通鑑序",
}
APPENDIX_TITLES = {
    "通鑑電子化校勘紀略",
    "《通鑑》電子化之用字說明",
    "《通鑑》電子化校勘人姓名",
}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_extracted_text(force_extract: bool = False) -> str:
    EXTRACTED_TEXT.parent.mkdir(parents=True, exist_ok=True)
    if force_extract or not EXTRACTED_TEXT.exists() or EXTRACTED_TEXT.stat().st_size == 0:
        result = run(["pdftotext", "-layout", str(SOURCE_PDF), str(EXTRACTED_TEXT)])
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return EXTRACTED_TEXT.read_text(encoding="utf-8", errors="replace")


def clean_line(line: str) -> str:
    line = line.replace("\ufeff", "").replace("\u3000", " ")
    line = SPACE_RE.sub(" ", line).strip()
    return line


def locate_source_start(lines: list[str]) -> int:
    """Return the first real source line, after copyright and generated TOC."""
    for index, line in enumerate(lines):
        if clean_line(line) == "胡刻通鑑正文校宋記述略" and index > 100:
            return index
    for index, line in enumerate(lines):
        if clean_line(line) == "資治通鑑卷第一" and index > 1000:
            return index
    raise RuntimeError("Cannot locate Zizhi Tongjian body start")


def is_heading(line: str) -> bool:
    return line in PREFACE_TITLES or line in APPENDIX_TITLES or bool(VOLUME_RE.fullmatch(line))


def append_text(current: dict[str, Any] | None, paragraphs: list[str], line: str) -> None:
    if current is None:
        return
    if not line or not HAN_RE.search(line):
        return
    paragraphs.append(line)


def flush_paragraph(current: dict[str, Any] | None, buffer: list[str]) -> None:
    if current is None or not buffer:
        buffer.clear()
        return
    text = "".join(buffer)
    text = SPACE_RE.sub(" ", text).strip()
    if text and HAN_RE.search(text):
        current.setdefault("paragraphs", []).append(text)
    buffer.clear()


def parse_chapters(text: str) -> list[dict[str, Any]]:
    raw_lines = text.replace("\f", "\n").splitlines()
    lines = [clean_line(line) for line in raw_lines]
    start = locate_source_start(lines)
    chapters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    buffer: list[str] = []
    volume_count = 0
    index = start

    def start_chapter(title: str, *, subtitle: str = "") -> None:
        nonlocal current
        flush_paragraph(current, buffer)
        chapter_title = f"{title} {subtitle}".strip()
        current = {
            "title": chapter_title,
            "heading": title,
            "subtitle": subtitle,
            "paragraphs": [],
        }
        chapters.append(current)

    while index < len(lines):
        line = lines[index]
        if not line or line.isdigit():
            flush_paragraph(current, buffer)
            index += 1
            continue
        if line == "宋神宗資治通鑑序 禦製":
            start_chapter(line)
            index += 1
            continue
        if line == "宋神宗資治通鑑序":
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if next_line == "禦製":
                start_chapter("宋神宗資治通鑑序 禦製")
                index += 2
            else:
                start_chapter(line)
                index += 1
            continue
        if line in PREFACE_TITLES or line in APPENDIX_TITLES:
            start_chapter(line)
            index += 1
            continue
        if VOLUME_RE.fullmatch(line):
            subtitle = ""
            probe = index + 1
            while probe < len(lines) and not lines[probe]:
                probe += 1
            if probe < len(lines) and SUBTITLE_RE.fullmatch(lines[probe]):
                subtitle = lines[probe]
                index = probe
            volume_count += 1
            start_chapter(line, subtitle=subtitle)
            index += 1
            continue
        if is_heading(line):
            start_chapter(line)
            index += 1
            continue
        append_text(current, buffer, line)
        index += 1

    flush_paragraph(current, buffer)
    chapters = [chapter for chapter in chapters if chapter.get("paragraphs")]
    if volume_count < 294:
        raise RuntimeError(f"Expected 294 body volumes, found {volume_count}")
    return chapters


def split_paragraph(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(text):
        if match.end() - start >= max_chars:
            pieces.append(text[start : match.end()].strip())
            start = match.end()
    if start < len(text):
        tail = text[start:].strip()
        if len(tail) > max_chars * 1.5:
            for offset in range(0, len(tail), max_chars):
                pieces.append(tail[offset : offset + max_chars].strip())
        else:
            pieces.append(tail)
    return [piece for piece in pieces if piece]


def chunk_paragraph_groups(paragraphs: list[str], max_chars: int) -> list[list[tuple[int, str]]]:
    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_len = 0
    for paragraph_number, paragraph in enumerate(paragraphs, start=1):
        pieces = split_paragraph(paragraph, max_chars)
        for piece in pieces:
            piece_len = len(piece)
            if current and current_len + piece_len > max_chars:
                groups.append(current)
                current = []
                current_len = 0
            current.append((paragraph_number, piece))
            current_len += piece_len
    if current:
        groups.append(current)
    return groups


def build_task(max_chars: int, force: bool, force_extract: bool) -> None:
    book_root = ROOT / "books" / BOOK_ID
    chunks_root = book_root / "work/quadrilingual/chunks"
    chunks_jsonl = chunks_root / "chunks.jsonl"
    manifest_path = chunks_root / "manifest.json"
    markdown_path = book_root / "markdown/wenyan.md"
    plan_path = book_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print(f"{BOOK_ID}: already prepared")
        return

    chapters = parse_chapters(ensure_extracted_text(force_extract=force_extract))
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    md_lines = ["# 資治通鑑", ""]
    for chapter in chapters:
        md_lines.extend([f"## {chapter['title']}", ""])
        for paragraph in chapter["paragraphs"]:
            md_lines.extend([paragraph, ""])
    markdown_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    ref_paths = [path for path in EN_REFS if path.exists()]
    chunks: list[dict[str, Any]] = []
    chunk_counter = 0
    for chapter_number, chapter in enumerate(chapters, start=1):
        chapter_id = f"{BOOK_ID}-chapter-{chapter_number:03d}"
        for group_number, group in enumerate(chunk_paragraph_groups(chapter["paragraphs"], max_chars), start=1):
            chunk_counter += 1
            chunk_id = f"{BOOK_ID}-chunk-{chunk_counter:05d}"
            first_para = group[0][0]
            last_para = group[-1][0]
            section_title = f"{chapter['title']} {first_para}"
            if last_para != first_para:
                section_title += f"-{last_para}"
            chunks.append(
                {
                    "schema_version": 1,
                    "task_type": "quadrilingual_wenyan_main",
                    "book_id": BOOK_ID,
                    "book_title_wenyan": "資治通鑑",
                    "chunk_id": chunk_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "chapter_title_wenyan": chapter["title"],
                    "chapter_title_zh_modern": chapter["title"],
                    "chapter_title_ja_modern": chapter["title"],
                    "chapter_title_en": f"Zizhi Tongjian: {chapter['title']}",
                    "section_title_wenyan": section_title,
                    "source_spine_lang": "wenyan",
                    "paragraphs": [
                        {"id": f"{chunk_id}-p{paragraph_index:03d}", "wenyan": piece}
                        for paragraph_index, (_paragraph_number, piece) in enumerate(group, start=1)
                    ],
                    "reference": {
                        "zh_modern": {
                            "source": "司馬光《資治通鑑》胡三省注本",
                            "path": str(SOURCE_PDF.relative_to(ROOT)),
                            "note": "The supplied wenyan source includes the main text, Hu Sanxing annotation, and校勘 material in reading order. Preserve meaning and do not omit notes.",
                        },
                        "en": {
                            "source": "partial English Later Han Zizhi Tongjian references",
                            "paths": [str(path.relative_to(ROOT)) for path in ref_paths],
                            "note": "Use only where the chapter window clearly matches; otherwise translate from the verified wenyan and modern Chinese meaning bridge.",
                        },
                        "ja_modern": {
                            "source": "generated",
                            "note": "Generate natural modern Japanese from the wenyan and modern Chinese meaning bridge; do not output kanbun or pure Chinese.",
                        },
                    },
                }
            )

    chunks_root.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    source_paths = {
        "commented_classical_source": str(SOURCE_PDF.relative_to(ROOT)),
        "wenyan_markdown": str(markdown_path.relative_to(ROOT)),
        "extracted_text": str(EXTRACTED_TEXT.relative_to(ROOT)),
        "partial_english_references": [str(path.relative_to(ROOT)) for path in ref_paths],
    }
    prepared_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": "資治通鑑",
        "book_title_zh_modern": "资治通鉴",
        "book_title_ja_modern": "資治通鑑",
        "book_title_en": "Zizhi Tongjian",
        "author": "司馬光",
        "author_reading_zh": "sī mǎ guāng",
        "author_reading_ja": "しば こう",
        "commentator": "胡三省",
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": source_paths,
        "source_sha256": {
            str(SOURCE_PDF.relative_to(ROOT)): sha256(SOURCE_PDF),
            str(markdown_path.relative_to(ROOT)): sha256(markdown_path),
        },
        "prepared_at": prepared_at,
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "launchable",
        "launchable": True,
        "task_mode": "quadrilingual_wenyan_main",
        "source_language": "wenyan",
        "default_note_order": {
            "wenyan": ["en", "ja_modern", "zh_modern"],
            "en": ["wenyan", "ja_modern", "zh_modern"],
            "ja_modern": ["wenyan", "en", "zh_modern"],
            "zh_modern": ["wenyan", "en", "ja_modern"],
        },
        "book_title_wenyan": "資治通鑑",
        "book_title_zh": "资治通鉴",
        "book_title_ja": "資治通鑑",
        "book_title_en": "Zizhi Tongjian",
        "author": "司馬光",
        "author_reading_zh": "sī mǎ guāng",
        "author_reading_ja": "しば こう",
        "commentator": "胡三省",
        "book_description": "資治通鑑 with the Hu Sanxing annotated classical Chinese source stream as main text and English, modern Japanese, and modern Chinese overlays.",
        "source_paths": source_paths,
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{BOOK_ID}/work/quadrilingual/interlinear/chunks",
        "assembled_json": f"books/{BOOK_ID}/work/quadrilingual/preview/{BOOK_ID}.partial.json",
        "build_root": f"build/{BOOK_ID}/wenyan-main-quadrilingual",
        "cover_image": "assets/covers/zizhi-tongjian/cover.png",
        "prepared_at": prepared_at,
    }
    write_json(plan_path, plan)
    skip_marker = book_root / "work/quadrilingual/queue/skipped-source-prep-required.ok"
    skip_marker.unlink(missing_ok=True)
    print(f"{BOOK_ID}: chapters={len(chapters)} chunks={len(chunks)} max_chars={max_chars}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chars", type=int, default=1600)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args()
    build_task(args.max_chars, args.force, args.force_extract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
