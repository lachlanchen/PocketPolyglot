#!/usr/bin/env python3
"""Repair Byron Selected Poems chapter metadata after noisy PDF extraction.

The generated unit translations are expensive and mostly reusable.  The
problem with this book is that the source PDF extraction promoted running
headers, page numbers, and OCR-spaced headings into chapter titles.  This
script rewrites only chapter metadata in the task manifest, source chunks, and
generated chunk JSON files so assembly produces a readable poem-level TOC.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from assemble_trilingual_json import plain_title, tokenize_ja_title, tokenize_zh_title


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "byron-selected-poems"
CHUNKS_JSONL = ROOT / "books/byron-selected-poems/work/trilingual/chunks/chunks.jsonl"
MANIFEST = ROOT / "books/byron-selected-poems/work/trilingual/chunks/manifest.json"
CHUNK_DIR = ROOT / "books/byron-selected-poems/work/trilingual/interlinear/chunks"


@dataclass(frozen=True)
class ChapterRange:
    start: int
    end: int
    slug: str
    title_en: str
    title_zh: str
    title_ja: str

    @property
    def chapter_id(self) -> str:
        return f"{BOOK_ID}-{self.slug}"


RANGES: tuple[ChapterRange, ...] = (
    ChapterRange(1, 3, "front-matter", "Edition Front Matter", "版本前置资料", "版元資料"),
    ChapterRange(4, 6, "source-contents", "Source Contents", "原书目录", "原書目次"),
    ChapterRange(7, 19, "general-introduction", "General Introduction", "总导言", "総序"),
    ChapterRange(
        20,
        33,
        "intro-childe-harold-don-juan",
        "Introduction to Childe Harold's Pilgrimage and Don Juan",
        "《恰尔德・哈洛尔德游记》与《唐璜》导言",
        "『チャイルド・ハロルドの巡礼』と『ドン・ジュアン』序説",
    ),
    ChapterRange(
        34,
        65,
        "childe-harold",
        "Childe Harold's Pilgrimage",
        "《恰尔德・哈洛尔德游记》",
        "『チャイルド・ハロルドの巡礼』",
    ),
    ChapterRange(
        66,
        72,
        "notes-childe-harold",
        "Notes to Childe Harold's Pilgrimage",
        "《恰尔德・哈洛尔德游记》注释",
        "『チャイルド・ハロルドの巡礼』注",
    ),
    ChapterRange(73, 75, "don-juan-dedication", "Don Juan: Dedication", "《唐璜》题献", "『ドン・ジュアン』献辞"),
    ChapterRange(76, 519, "don-juan", "Don Juan", "《唐璜》", "『ドン・ジュアン』"),
    ChapterRange(520, 589, "notes-don-juan", "Notes to Don Juan", "《唐璜》注释", "『ドン・ジュアン』注"),
    ChapterRange(590, 598, "intro-tales", "Introduction to the Tales", "故事诗导言", "物語詩序説"),
    ChapterRange(599, 633, "the-giaour", "The Giaour", "《异教徒》", "『異教徒』"),
    ChapterRange(634, 654, "notes-the-giaour", "Notes to The Giaour", "《异教徒》注释", "『異教徒』注"),
    ChapterRange(655, 694, "the-corsair", "The Corsair", "《海盗》", "『海賊』"),
    ChapterRange(695, 698, "notes-the-corsair", "Notes to The Corsair", "《海盗》注释", "『海賊』注"),
    ChapterRange(699, 706, "intro-satires", "Introduction to the Satires", "讽刺诗导言", "諷刺詩序説"),
    ChapterRange(
        707,
        751,
        "english-bards",
        "English Bards and Scotch Reviewers",
        "《英国诗人与苏格兰评论家》",
        "『英国詩人とスコットランド評論家』",
    ),
    ChapterRange(
        752,
        779,
        "vision-of-judgment",
        "The Vision of Judgment",
        "《审判幻景》",
        "『審判の幻』",
    ),
    ChapterRange(
        780,
        782,
        "notes-vision-of-judgment",
        "Notes to The Vision of Judgment",
        "《审判幻景》注释",
        "『審判の幻』注",
    ),
    ChapterRange(
        783,
        788,
        "intro-lyrics",
        "Introduction to Lyrics and Shorter Poems",
        "抒情诗与短诗导言",
        "抒情詩と短詩序説",
    ),
    ChapterRange(789, 789, "to-caroline-1", "To Caroline (1)", "致卡罗琳（一）", "キャロラインへ（一）"),
    ChapterRange(790, 790, "to-caroline-2", "To Caroline (2)", "致卡罗琳（二）", "キャロラインへ（二）"),
    ChapterRange(791, 791, "to-caroline-3", "To Caroline (3)", "致卡罗琳（三）", "キャロラインへ（三）"),
    ChapterRange(792, 793, "lachin-y-gair", "Lachin y Gair", "勒钦伊盖", "ラヒン・イ・ゲール"),
    ChapterRange(794, 796, "darkness", "Darkness", "黑暗", "暗黒"),
    ChapterRange(797, 798, "to-thyrza", "To Thyrza", "致瑟莎", "サーザへ"),
    ChapterRange(799, 799, "the-cornelian", "The Cornelian", "红玉髓", "カーネリアン"),
    ChapterRange(800, 800, "when-we-two-parted", "When We Two Parted", "我们俩分手的时候", "ふたりが別れたとき"),
    ChapterRange(
        801,
        803,
        "late-short-poems",
        "Swimming from Sestos to Abydos / Thirty-Sixth Year",
        "游过塞斯托斯到阿拜多斯 / 三十六岁生日",
        "セストスからアビュドスへ泳いだあと / 三十六歳の日",
    ),
    ChapterRange(
        804,
        807,
        "notes-lyrics",
        "Notes to Lyrics and Shorter Poems",
        "抒情诗与短诗注释",
        "抒情詩と短詩注",
    ),
    ChapterRange(808, 834, "glossary", "Glossary", "词汇表", "用語集"),
    ChapterRange(835, 836, "index-first-lines", "Index of First Lines", "首行索引", "初行索引"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def range_for(index: int) -> tuple[int, ChapterRange]:
    for number, chapter_range in enumerate(RANGES, start=1):
        if chapter_range.start <= index <= chapter_range.end:
            return number, chapter_range
    raise ValueError(f"no Byron TOC range covers chunk index {index}")


def title_tokens(chapter_range: ChapterRange) -> dict[str, list[dict[str, str]]]:
    return {
        "en": plain_title(chapter_range.title_en),
        "zh": tokenize_zh_title(chapter_range.title_zh),
        "ja": tokenize_ja_title(chapter_range.title_ja),
    }


def backup(paths: list[Path], backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)


def repair_chunks_jsonl(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        chunk = json.loads(raw)
        number, chapter_range = range_for(int(chunk["chunk_index"]))
        chunk["chapter_id"] = chapter_range.chapter_id
        chunk["chapter_number"] = number
        chunk["chapter_title_en"] = chapter_range.title_en
        chunk["chapter_title_zh"] = chapter_range.title_zh
        chunk["chapter_title_ja"] = chapter_range.title_ja
        chunks.append(chunk)
    return chunks


def write_chunks_jsonl(path: Path, chunks: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")


def repair_manifest(path: Path, chunks_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = load_json(path)
    for item in manifest.get("chunks", []):
        chunk = chunks_by_id[str(item["chunk_id"])]
        item["chapter_id"] = chunk["chapter_id"]
        item["chapter_number"] = chunk["chapter_number"]
        item["chapter_title_en"] = chunk["chapter_title_en"]
        item["chapter_title_zh"] = chunk["chapter_title_zh"]
        item["chapter_title_ja"] = chunk["chapter_title_ja"]
    manifest["toc_repaired_at"] = datetime.now(timezone.utc).isoformat()
    manifest["toc_repair_note"] = (
        "Byron source PDF running headers and OCR-spaced page labels were "
        "collapsed into logical poem/work sections."
    )
    return manifest


def repair_generated_chunk(path: Path, source_chunk: dict[str, Any]) -> None:
    data = load_json(path)
    _, chapter_range = range_for(int(source_chunk["chunk_index"]))
    chapter = data.setdefault("chapter", {})
    chapter["id"] = chapter_range.chapter_id
    chapter["number"] = source_chunk["chapter_number"]
    chapter["title"] = title_tokens(chapter_range)
    write_json(path, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    chunks = repair_chunks_jsonl(CHUNKS_JSONL)
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    manifest = repair_manifest(MANIFEST, chunks_by_id)
    missing = [chunk["chunk_id"] for chunk in chunks if not (CHUNK_DIR / f"{chunk['chunk_id']}.json").exists()]
    if missing:
        raise FileNotFoundError(f"missing generated chunks: {missing[:10]}")

    print(f"book={BOOK_ID}")
    print(f"chunks={len(chunks)}")
    print(f"logical_chapters={len(RANGES)}")
    for number, chapter_range in enumerate(RANGES, start=1):
        print(f"{number:02d}: {chapter_range.start:04d}-{chapter_range.end:04d} {chapter_range.title_en}")

    if args.dry_run:
        return 0

    if not args.no_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = CHUNKS_JSONL.parent / f"backups-{stamp}-byron-toc-repair"
        backup([CHUNKS_JSONL, MANIFEST], backup_dir)

    write_chunks_jsonl(CHUNKS_JSONL, chunks)
    write_json(MANIFEST, manifest)
    for chunk in chunks:
        repair_generated_chunk(CHUNK_DIR / f"{chunk['chunk_id']}.json", chunk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
