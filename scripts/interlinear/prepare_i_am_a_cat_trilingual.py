#!/usr/bin/env python3
"""Prepare I Am a Cat markdown, manifest, and trilingual chunk tasks."""

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


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "i-am-a-cat"
BOOK_TITLE_EN = "I Am a Cat"
BOOK_TITLE_ZH = "我是猫"
BOOK_TITLE_JA = "吾輩は猫である"
BOOK_TITLE_ZH_READING = "wǒ shì māo"
BOOK_TITLE_JA_READING = "わがはいはねこである"
AUTHOR = "夏目漱石"
AUTHOR_READING_JA = "なつめそうせき"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

ZH_SOURCE = Path("sources/I-am-a-cat/我是猫【上海译文出品！影响鲁迅、老舍、钱锺书的日本国民作家夏目漱石的传世神作；用毒舌开启了人类吸猫文学先河】.epub")
JA_SOURCE = Path("books/natsume-complete/markdown/book.md")
JA_RESERVOIR_SOURCE = Path("sources/夏目 漱石 作品全集.epub")
SCAN_SOURCE = Path("sources/I-am-a-cat/我是貓 吾輩は猫である.pdf")

SECTION_RE = re.compile(r"^(一|二|三|四|五|六|七|八|九|十|十一)$")
NOTE_RE = re.compile(r"^〔\d+〕")
ZH_NOTE_MARK_RE = re.compile(r"\^\(〔\d+〕\)")
SPACE_RE = re.compile(r"\s+")
CJK_SENTENCE_END = set("。！？!?；;")
CJK_CLOSERS = set("”’」』）)]〉》")


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
    return SPACE_RE.sub(" ", text.replace("\u3000", " ").replace("\u00a0", " ")).strip()


def split_sentences(text: str, *, max_chars: int) -> list[str]:
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


def parse_zh_epub(path: Path) -> list[Chapter]:
    raw = run_text(["pandoc", str(path), "-t", "plain", "--wrap=none"])
    chapters: list[Chapter] = []
    current: Chapter | None = None
    started = False
    in_notes = False

    for raw_line in raw.splitlines():
        line = compact(raw_line)
        if not line:
            continue
        if not started:
            if line.startswith("我是只猫儿。要说名字嘛"):
                started = True
                current = Chapter(number=1, title="一")
                chapters.append(current)
            else:
                continue
        elif SECTION_RE.match(line):
            current = Chapter(number=len(chapters) + 1, title=line)
            chapters.append(current)
            in_notes = False
            continue
        if current is None:
            continue
        if line == "注释":
            in_notes = True
            continue
        if in_notes or NOTE_RE.match(line):
            continue
        if line.startswith(("读累了", "公众号", "网站：", "新浪微博", "诚邀关注")):
            continue
        line = compact(ZH_NOTE_MARK_RE.sub("", line))
        if line:
            current.paragraphs.extend(split_sentences(line, max_chars=900))
    return chapters


def parse_ja_markdown(path: Path) -> list[Chapter]:
    lines = path.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    in_body = False
    for line in lines:
        if line.startswith("# 第104章 吾輩は猫である"):
            in_body = True
            continue
        if in_body and line.startswith("# 第105章"):
            break
        if in_body:
            body.append(line)

    chapters: list[Chapter] = []
    current: Chapter | None = None
    for raw_line in body:
        line = compact(raw_line)
        if not line:
            continue
        if SECTION_RE.match(line):
            current = Chapter(number=len(chapters) + 1, title=line)
            chapters.append(current)
            continue
        if current is None:
            continue
        for paragraph in [part.strip() for part in re.split(r"\s{1,}", line) if part.strip()]:
            current.paragraphs.extend(split_sentences(paragraph, max_chars=900))
    return chapters


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


def chapter_by_number(chapters: list[Chapter]) -> dict[int, Chapter]:
    return {chapter.number: chapter for chapter in chapters}


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
    zh_chapters: list[Chapter],
    ja_chapters: dict[int, Chapter],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    paragraph_count = 0
    for chapter in zh_chapters:
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
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": BOOK_ID,
                    "source_spine_lang": "zh",
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_number,
                    "chapter_id": f"chapter-{chapter.number:02d}",
                    "chapter_number": chapter.number,
                    "chapter_title_en": f"Chapter {chapter.number}",
                    "chapter_part_en": "",
                    "paragraph_ids": [paragraph["id"] for paragraph in pending],
                    "paragraphs": list(pending),
                    "reference": {
                        "english": {"available": False, "chapter": "", "text": ""},
                        "zh_primary": {
                            "available": True,
                            "chapter": chapter.title,
                            "text": "\n".join(paragraph["zh"] for paragraph in pending),
                        },
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": reference_window(ja_chapters.get(chapter.number), start_ratio, end_ratio, max_chars=reference_chars),
                    },
                }
            )
            pending = []
            pending_chars = 0

        for paragraph_index, paragraph in enumerate(chapter.paragraphs, start=1):
            paragraph_count += 1
            paragraph_id = f"{BOOK_ID}-s{chapter.number:02d}-p{paragraph_index:04d}"
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
            if not pending:
                pending_start = char_offsets[paragraph_index - 1]
            pending.append({"id": paragraph_id, "zh": paragraph})
            pending_chars += len(paragraph)
        flush()

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "source_spine_lang": "zh",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "book_title_zh_reading": BOOK_TITLE_ZH_READING,
        "book_title_ja_reading": BOOK_TITLE_JA_READING,
        "author": AUTHOR,
        "author_reading_ja": AUTHOR_READING_JA,
        "source_paths": {
            "zh_primary": str(ZH_SOURCE),
            "ja": str(JA_SOURCE),
            "ja_reservoir": str(JA_RESERVOIR_SOURCE),
            "scan_reference": str(SCAN_SOURCE),
        },
        "source_sha256": {
            "zh_primary": sha256(ZH_SOURCE),
            "ja": sha256(JA_SOURCE),
            "ja_reservoir": sha256(JA_RESERVOIR_SOURCE),
            "scan_reference": sha256(SCAN_SOURCE),
        },
        "source_note": (
            "Chinese is the alignment spine because no clean English source is present locally. "
            "Chinese uses the supplied 我是猫 EPUB translation. Japanese uses the 吾輩は猫である chapter "
            "from the local 夏目漱石作品全集 markdown reservoir. English is generated from the Chinese spine "
            "with Japanese reference windows."
        ),
        "chapter_count": len(zh_chapters),
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
    parser.add_argument("--max-chunk-chars", type=int, default=1400)
    parser.add_argument("--reference-chars", type=int, default=4200)
    args = parser.parse_args()

    markdown_dir = ROOT / "books" / BOOK_ID / "markdown"
    work_chunk_dir = ROOT / "books" / BOOK_ID / "work" / "trilingual" / "chunks"

    zh_chapters = parse_zh_epub(ZH_SOURCE)
    ja_chapters = parse_ja_markdown(JA_SOURCE)

    write_text(markdown_dir / "zh.md", markdown_for_chapters(BOOK_TITLE_ZH, zh_chapters))
    write_text(markdown_dir / "ja.md", markdown_for_chapters(BOOK_TITLE_JA, ja_chapters))

    manifest, chunks = make_chunks(
        zh_chapters,
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
        "source_spine_lang": "zh",
        "book_title_en": BOOK_TITLE_EN,
        "book_title_zh": BOOK_TITLE_ZH,
        "book_title_ja": BOOK_TITLE_JA,
        "book_title_zh_reading": BOOK_TITLE_ZH_READING,
        "book_title_ja_reading": BOOK_TITLE_JA_READING,
        "author": AUTHOR,
        "author_reading_ja": AUTHOR_READING_JA,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "markdown": {
            "zh": f"books/{BOOK_ID}/markdown/zh.md",
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
        "target_outputs": "12 PDFs: zh-en/en-zh, zh-ja/ja-zh, ja-en/en-ja; color and blackwhite",
    }
    write_json(ROOT / "books" / BOOK_ID / "book-plan.json", plan)

    print(f"book_id={BOOK_ID}")
    print(f"chapters_zh={len(zh_chapters)} ja={len(ja_chapters)}")
    print(f"paragraphs={manifest['paragraph_count']}")
    print(f"chunks={manifest['chunk_count']}")
    print(f"manifest={plan['chunks_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
