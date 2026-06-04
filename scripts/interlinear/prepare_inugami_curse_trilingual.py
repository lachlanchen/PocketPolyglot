#!/usr/bin/env python3
"""Prepare The Inugami Curse trilingual EN/JP/ZH chunk tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "inugami-curse"
BOOK_TITLE_EN = "The Inugami Curse"
BOOK_TITLE_ZH = "犬神家族"
BOOK_TITLE_JA = "犬神家の一族"
BOOK_TITLE_ZH_READING = "quǎn shén jiā zú"
BOOK_TITLE_JA_READING = "いぬがみけのいちぞく"
AUTHOR = "横溝正史"
AUTHOR_READING_ZH = "héng gōu zhèng shǐ"
AUTHOR_READING_JA = "よこみぞせいし"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

EN_SOURCE = Path("sources/犬神家族 - The Inugami Curse/The Inugami Curse.epub")
ZH_SOURCE = Path("sources/犬神家族 - The Inugami Curse/《犬神家族》作者：[日]横沟正史.azw")
ZH_EXTRACT_DIR = Path("books/inugami-curse/work/source-extract/zh-mobi")
ZH_HTML = ZH_EXTRACT_DIR / "mobi7/book.html"

SPACE_RE = re.compile(r"\s+")
PAGE_MARK_RE = re.compile(r"\[\d+\]\{#[^}]+\}")
ANCHOR_RE = re.compile(r"^\[\]\{#[^}]+\}$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
BRACED_ID_RE = re.compile(r"\{#[^}]+\}")
EN_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?]["”’)]*\s+')
CJK_SENTENCE_END = set("。！？!?；;")
CJK_CLOSERS = set("”’」』）)]〉》")
ZH_CHAPTER_RE = re.compile(r"^(序章[—-].+|第\s*[0-9０-９一二三四五六七八九十百]+章\s+.+)$")

EN_START = "The Tale Begins"
EN_STOP_HEADINGS = {
    "TRANSLATOR'S ACKNOWLEDGMENTS",
    "AVAILABLE AND COMING SOON FROM PUSHKIN VERTIGO",
    "ABOUT THE AUTHOR",
    "COPYRIGHT",
}


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
    return SPACE_RE.sub(" ", str(text).replace("\u3000", " ").replace("\u00a0", " ")).strip()


def clean_markdown_line(line: str) -> str:
    line = PAGE_MARK_RE.sub("", line)
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    line = LINK_RE.sub(r"\1", line)
    line = BRACED_ID_RE.sub("", line)
    line = line.replace("\\_", "_").replace("\\-", "-").replace("\\", "")
    return compact(line)


def clean_heading(line: str) -> str:
    return clean_markdown_line(line.lstrip("#").strip()).strip("* ")


def split_english_units(text: str, *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in EN_SENTENCE_BOUNDARY_RE.finditer(text):
        end = match.end()
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


def split_cjk_units(text: str, *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in CJK_SENTENCE_END:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in CJK_CLOSERS:
            end += 1
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
        index = end
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
            pending = pending + piece if pending else piece
    if pending:
        out.append(pending)
    return out


def parse_en_epub(path: Path) -> list[Chapter]:
    raw = run_text(["pandoc", str(path), "-t", "markdown", "--wrap=none"])
    chapters: list[Chapter] = []
    current: Chapter | None = None
    in_body = False

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(":::") or ANCHOR_RE.match(line):
            continue
        if line.startswith("#"):
            heading = clean_heading(line)
            if heading == EN_START:
                in_body = True
            elif heading in EN_STOP_HEADINGS:
                break
            if in_body and heading and heading not in {"CONTENTS", "CHARACTER LIST"}:
                current = Chapter(number=len(chapters) + 1, title=heading)
                chapters.append(current)
            continue
        if not in_body or current is None:
            continue
        text = clean_markdown_line(line)
        if not text or text.startswith(("[", "]", "[]")):
            continue
        if text.lower().startswith("yumiko yamazaki"):
            break
        current.paragraphs.extend(split_english_units(text, max_chars=900))
    return [chapter for chapter in chapters if chapter.paragraphs]


def ensure_zh_html() -> Path:
    if ZH_HTML.exists():
        return ZH_HTML
    tool = shutil.which("mobiunpack") or str(Path.home() / ".local/bin/mobiunpack")
    if not Path(tool).exists() and shutil.which(tool) is None:
        raise RuntimeError("mobiunpack is required; install with `python -m pip install --user mobi`")
    ZH_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    run([tool, str(ZH_SOURCE), str(ZH_EXTRACT_DIR)])
    if not ZH_HTML.exists():
        raise FileNotFoundError(ZH_HTML)
    return ZH_HTML


def html_plain_text(path: Path) -> str:
    full_path = path if path.is_absolute() else ROOT / path
    html = full_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3", "p", "div"]):
        text = compact(tag.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return "\n".join(parts)


def normalize_zh_heading(line: str) -> str:
    line = re.sub(r"^-+\s*", "", compact(line))
    line = line.replace("——", "—")
    return line


def parse_zh_mobi() -> list[Chapter]:
    html = ensure_zh_html()
    raw = html_plain_text(html)
    chapters: list[Chapter] = []
    current: Chapter | None = None

    for raw_line in raw.splitlines():
        line = normalize_zh_heading(raw_line)
        if not line or line.startswith(("TXT电子书制作", "书籍相关", "内容简介", "目录")):
            continue
        if line.startswith("《犬神家族完》"):
            break
        if "序章—故事开端" in line:
            current = Chapter(number=len(chapters) + 1, title="序章—故事开端")
            chapters.append(current)
            continue
        if ZH_CHAPTER_RE.match(line):
            current = Chapter(number=len(chapters) + 1, title=line)
            chapters.append(current)
            continue
        if current is None:
            continue
        if set(line) <= {"-", "—", "―"}:
            continue
        current.paragraphs.extend(split_cjk_units(line, max_chars=900))
    return [chapter for chapter in chapters if chapter.paragraphs]


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
    start = max(0, int(len(text) * start_ratio) - max_chars // 4)
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
                        "zh_primary": {"available": bool(zh_ref), "chapter": "ratio-window", "text": zh_ref},
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
            "English is the alignment spine. Chinese is supplied as an extracted AZW reference window. "
            "Japanese is generated from the English spine and Chinese reference."
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
    parser.add_argument("--reference-chars", type=int, default=7000)
    args = parser.parse_args()

    en_chapters = parse_en_epub(EN_SOURCE)
    zh_chapters = parse_zh_mobi()
    if not en_chapters:
        raise RuntimeError("no English chapters parsed")
    if not zh_chapters:
        raise RuntimeError("no Chinese chapters parsed")

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
        "task_mode": "trilingual_en_spine_generated_ja",
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
            "Yokomizo Seishi, The Inugami Curse. English source is the alignment spine; "
            "Chinese AZW translation is used as a reference; Japanese is generated."
        ),
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": "global_ratio_window",
        "chunks_jsonl": str(chunks_dir / "chunks.jsonl"),
        "chunks_manifest": str(chunks_dir / "manifest.json"),
        "raw_chunk_dir": str(raw_chunk_dir),
        "preview_json": str(preview_dir / f"{BOOK_ID}.partial.json"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "english_chapter_count": len(en_chapters),
        "chinese_chapter_count": len(zh_chapters),
    }
    write_json(book_root / "book-plan.json", plan)
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    print(f"book_id={BOOK_ID}")
    print(f"english_chapters={len(en_chapters)} chinese_chapters={len(zh_chapters)}")
    print(f"chunks={len(chunks)}")
    print(f"manifest={chunks_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
