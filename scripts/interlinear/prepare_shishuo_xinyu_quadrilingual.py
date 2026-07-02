#!/usr/bin/env python3
"""Prepare Shishuo Xinyu as a wenyan-main quadrilingual task."""

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
BOOK_ID = "shishuo-xinyu"
SOURCE_PDF = ROOT / "sources/shishuo-xinyu/zh/世說新語.pdf"
ZH_COMMENTARY = ROOT / "sources/shishuo-xinyu/zh/世说新语笺疏.pdf"
EN_REFERENCE = ROOT / "sources/shishuo-xinyu/en/Shih-shuo hsin-yü - A New Account of Tales of the World.pdf"

CHAPTER_HEADING_RE = re.compile(
    r"^(?P<title>[^\s\d，。、；：！？]{1,8}第[一二三四五六七八九十百]+)\s*(?P<rest>.*)$"
)
ITEM_RE = re.compile(r"^(?P<num>\d{1,4})[.．、]\s*(?P<text>.*)$")
SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]")
SPACE_RE = re.compile(r"\s+")

PREFACE_TITLES = ("世說新語序目", "刻世說新語序")
EXPECTED_SECTION_TITLES = {
    "德行第一",
    "言語第二",
    "政事第三",
    "文學第四",
    "方正第五",
    "雅量第六",
    "識鑒第七",
    "賞譽第八",
    "品藻第九",
    "規箴第十",
    "捷悟第十一",
    "夙惠第十二",
    "豪爽第十三",
    "容止第十四",
    "自新第十五",
    "企羡第十六",
    "企羨第十六",
    "傷逝第十七",
    "棲逸第十八",
    "栖逸第十八",
    "賢媛第十九",
    "術解第二十",
    "巧蓺第二十一",
    "巧藝第二十一",
    "寵禮第二十二",
    "任誕第二十三",
    "簡傲第二十四",
    "排調第二十五",
    "輕詆第二十六",
    "假譎第二十七",
    "黜免第二十八",
    "儉嗇第二十九",
    "汰侈第三十",
    "忿狷第三十一",
    "讒險第三十二",
    "尤悔第三十三",
    "紕漏第三十四",
    "惑溺第三十五",
    "仇隟第三十六",
    "仇隙第三十六",
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


def pdftotext(path: Path) -> str:
    result = run(["pdftotext", "-layout", str(path), "-"])
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {path}: {result.stderr}")
    return result.stdout


def clean_line(line: str) -> str:
    line = line.replace("\u3000", " ")
    line = SPACE_RE.sub(" ", line).strip()
    return line


def source_body(text: str) -> list[str]:
    start = text.find("世說新語序目")
    if start < 0:
        start = text.find("德行第一")
    if start < 0:
        raise RuntimeError("Cannot locate Shishuo Xinyu body start")
    end_markers = [
        "*** END OF THIS PROJECT GUTENBERG",
        "End of the Project Gutenberg",
        "Produced by",
    ]
    end = len(text)
    for marker in end_markers:
        pos = text.find(marker, start + 1000)
        if pos > 0:
            end = min(end, pos)
    lines = []
    for raw in text[start:end].replace("\f", "\n").splitlines():
        line = clean_line(raw)
        if not line:
            continue
        if line.isdigit():
            continue
        if line.startswith(("Title:", "Author:", "Release Date:", "Language:", "***")):
            continue
        lines.append(line)
    return lines


def split_heading_and_item(line: str) -> list[str]:
    match = CHAPTER_HEADING_RE.match(line)
    if not match or match.group("title") not in EXPECTED_SECTION_TITLES:
        return [line]
    title = match.group("title")
    rest = match.group("rest").strip()
    if rest and ITEM_RE.match(rest):
        return [title, rest]
    return [line]


def flush_item(chapters: list[dict[str, Any]], current: dict[str, Any] | None, item: dict[str, Any] | None) -> None:
    if current is None or item is None:
        return
    text = "".join(item["lines"])
    text = SPACE_RE.sub("", text).strip()
    if text:
        current.setdefault("items", []).append(
            {
                "number": item.get("number"),
                "text": text,
            }
        )


def parse_chapters(lines: list[str]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    item: dict[str, Any] | None = None

    def start_chapter(title: str) -> None:
        nonlocal current, item
        flush_item(chapters, current, item)
        item = None
        current = {"title": title, "items": []}
        chapters.append(current)

    start_chapter("世說新語序目")
    for raw in lines:
        for line in split_heading_and_item(raw):
            if line in PREFACE_TITLES:
                if line == "刻世說新語序":
                    start_chapter(line)
                continue
            for title in PREFACE_TITLES:
                if line.startswith(title) and len(line) > len(title):
                    if title == "刻世說新語序" and current and current.get("title") != title:
                        start_chapter(title)
                    line = line[len(title) :].strip()
                    break
            heading = CHAPTER_HEADING_RE.match(line)
            if (
                heading
                and heading.group("title") in EXPECTED_SECTION_TITLES
                and not ITEM_RE.match(heading.group("rest").strip())
            ):
                start_chapter(heading.group("title"))
                rest = heading.group("rest").strip()
                if rest:
                    item = {"number": None, "lines": [rest]}
                continue
            item_match = ITEM_RE.match(line)
            if item_match:
                flush_item(chapters, current, item)
                item = {"number": item_match.group("num"), "lines": [item_match.group("text")]}
                continue
            if item is None:
                item = {"number": None, "lines": [line]}
            else:
                item["lines"].append(line)
    flush_item(chapters, current, item)
    return [chapter for chapter in chapters if chapter.get("items")]


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


def build_task(max_chars: int, force: bool) -> None:
    book_root = ROOT / "books" / BOOK_ID
    chunks_root = book_root / "work/quadrilingual/chunks"
    chunks_jsonl = chunks_root / "chunks.jsonl"
    manifest_path = chunks_root / "manifest.json"
    plan_path = book_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print(f"{BOOK_ID}: already prepared")
        return

    text = pdftotext(SOURCE_PDF)
    chapters = parse_chapters(source_body(text))
    markdown = book_root / "markdown/wenyan.md"
    markdown.parent.mkdir(parents=True, exist_ok=True)
    md_lines = ["# 世說新語", ""]
    for chapter in chapters:
        md_lines.extend([f"## {chapter['title']}", ""])
        for item in chapter["items"]:
            prefix = f"{item['number']}. " if item.get("number") else ""
            md_lines.extend([prefix + item["text"], ""])
    markdown.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    chunks: list[dict[str, Any]] = []
    chunk_counter = 0
    for chapter_number, chapter in enumerate(chapters, start=1):
        chapter_id = f"{BOOK_ID}-chapter-{chapter_number:02d}"
        for item in chapter["items"]:
            item_number = item.get("number")
            section_base = chapter["title"]
            if item_number:
                section_base += f" {item_number}"
            for part_number, piece in enumerate(split_paragraph(item["text"], max_chars), start=1):
                chunk_counter += 1
                section_title = section_base
                if part_number > 1:
                    section_title += f" part {part_number}"
                chunk_id = f"{BOOK_ID}-chunk-{chunk_counter:04d}"
                chunks.append(
                    {
                        "schema_version": 1,
                        "task_type": "quadrilingual_wenyan_main",
                        "book_id": BOOK_ID,
                        "book_title_wenyan": "世說新語",
                        "chunk_id": chunk_id,
                        "chapter_id": chapter_id,
                        "chapter_number": chapter_number,
                        "chapter_title_wenyan": chapter["title"],
                        "chapter_title_zh_modern": chapter["title"],
                        "chapter_title_ja_modern": chapter["title"],
                        "chapter_title_en": f"A New Account of Tales of the World: {chapter['title']}",
                        "section_title_wenyan": section_title,
                        "source_spine_lang": "wenyan",
                        "paragraphs": [{"id": f"{chunk_id}-p001", "wenyan": piece}],
                        "reference": {
                            "zh_modern": {
                                "source": "余嘉錫《世說新語箋疏》",
                                "path": str(ZH_COMMENTARY.relative_to(ROOT)),
                                "note": "Use as broad meaning/commentary reference. Do not merge commentary into the source line.",
                            },
                            "en": {
                                "source": "Richard B. Mather, A New Account of Tales of the World",
                                "path": str(EN_REFERENCE.relative_to(ROOT)),
                                "note": "Use where the numbered anecdote clearly matches; otherwise translate from the verified wenyan.",
                            },
                            "ja_modern": {
                                "source": "generated",
                                "note": "Generate natural modern Japanese from the wenyan and modern Chinese meaning bridge.",
                            },
                        },
                    }
                )

    chunks_root.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    source_paths = {
        "classical_source": str(SOURCE_PDF.relative_to(ROOT)),
        "modern_chinese_commentary": str(ZH_COMMENTARY.relative_to(ROOT)),
        "english_reference": str(EN_REFERENCE.relative_to(ROOT)),
        "wenyan_markdown": str(markdown.relative_to(ROOT)),
    }
    prepared_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "book_id": BOOK_ID,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": "世說新語",
        "book_title_zh_modern": "世说新语",
        "book_title_ja_modern": "世説新語",
        "book_title_en": "A New Account of Tales of the World",
        "author": "劉義慶",
        "author_reading_zh": "liú yì qìng",
        "author_reading_ja": "りゅう ぎけい",
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": source_paths,
        "source_sha256": {
            str(SOURCE_PDF.relative_to(ROOT)): sha256(SOURCE_PDF),
            str(markdown.relative_to(ROOT)): sha256(markdown),
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
        "book_title_wenyan": "世說新語",
        "book_title_zh": "世说新语",
        "book_title_ja": "世説新語",
        "book_title_en": "A New Account of Tales of the World",
        "author": "劉義慶",
        "author_reading_zh": "liú yì qìng",
        "author_reading_ja": "りゅう ぎけい",
        "book_description": "世說新語 with classical Chinese as the main text and English, modern Japanese, and modern Chinese overlays.",
        "source_paths": source_paths,
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{BOOK_ID}/work/quadrilingual/interlinear/chunks",
        "assembled_json": f"books/{BOOK_ID}/work/quadrilingual/preview/{BOOK_ID}.partial.json",
        "build_root": f"build/{BOOK_ID}/wenyan-main-quadrilingual",
        "cover_image": "assets/covers/shishuo-xinyu/cover.png",
        "prepared_at": prepared_at,
    }
    write_json(plan_path, plan)
    print(f"{BOOK_ID}: chapters={len(chapters)} chunks={len(chunks)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chars", type=int, default=520)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build_task(args.max_chars, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
