#!/usr/bin/env python3
"""Prepare Japanese classical source trees as JP-spine trilingual tasks."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare_classical_quadrilingual_task import (
    clean_reference_text,
    clean_wiki_markup,
    extract_raw_wiki_header_section,
    sha256,
    split_paragraph,
    title_tail,
    zh_number_to_int,
)


ROOT = Path(__file__).resolve().parents[2]
HAN_OR_KANA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
MANYOSHU_VOLUME_RE = re.compile(r"第([一二三四五六七八九十百〇零]+)巻$")
KOKIN_VOLUME_RE = re.compile(r"巻([一二三四五六七八九十百〇零]+)$")
FIELD_RE = re.compile(r"^\[([^\]]+)\](.*)$")

BOOKS: dict[str, dict[str, Any]] = {
    "manyoshu": {
        "book_title_ja": "万葉集",
        "book_title_zh": "万叶集",
        "book_title_en": "Man'yoshu",
        "author": "大伴家持 等 編",
        "author_reading_ja": "おおとも の やかもち ほか へん",
        "source_dir": "sources/manyoshu/jp/wikisource",
        "english_refs": [
            "sources/manyoshu/en/wikisource-anthology-manyoshu",
            "sources/japanese-literature-anthology/en/wikisource",
        ],
        "missing_refs": [
            "sources/manyoshu/en/wikisource",
            "sources/manyoshu/zh/wikisource",
        ],
        "source_note": (
            "Japanese Wikisource kundoku is the preserved source spine. "
            "English uses the Anthology of Japanese Literature page only where it matches; "
            "Chinese is generated from the Japanese source."
        ),
    },
    "kokin-wakashu": {
        "book_title_ja": "古今和歌集",
        "book_title_zh": "古今和歌集",
        "book_title_en": "Kokin Wakashu",
        "author": "紀貫之 等 撰",
        "author_reading_ja": "き の つらゆき ほか せん",
        "source_dir": "sources/kokin-wakashu/jp/wikisource",
        "english_refs": [
            "sources/kokin-wakashu/en/wikisource-anthology-kokinshu",
            "sources/kokin-wakashu/en/wikisource-anthology-six-collections",
            "sources/japanese-literature-anthology/en/wikisource",
        ],
        "missing_refs": [
            "sources/kokin-wakashu/en/wikisource",
            "sources/kokin-wakashu/zh/wikisource",
        ],
        "extra_refs": [
            "sources/kokin-wakashu/jp/modern-translation-epub/古今和歌集（全現代語訳付）.epub",
        ],
        "source_note": (
            "Japanese Wikisource is the preserved source spine. The local modern-translation EPUB "
            "is a broad Japanese reference; English Wikisource anthology pages are partial references; "
            "Chinese is generated from the Japanese source."
        ),
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_url(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or "")


def read_raw(source_dir: Path, item: dict[str, Any]) -> str:
    raw = item.get("raw")
    if not raw:
        return ""
    return (source_dir / raw).read_text(encoding="utf-8", errors="replace")


def useful_line(line: str) -> str:
    line = clean_reference_text(clean_wiki_markup(line))
    line = line.strip()
    if not line:
        return ""
    if line in {"←", "→"}:
        return ""
    if line.startswith(("{|", "|}", "|", "{{", "}}")):
        return ""
    if line.startswith(("[[Category:", "Category:", "__")):
        return ""
    if line.startswith(("此作品", "この作品", "This work is in the public domain")):
        return ""
    return line


def manyoshu_sort_key(title: str, fallback: int) -> tuple[int, str]:
    tail = title_tail(title)
    match = MANYOSHU_VOLUME_RE.search(tail)
    if match:
        return (zh_number_to_int(match.group(1)), tail)
    return (9000 + fallback, tail)


def kokin_sort_key(title: str, fallback: int) -> tuple[int, str]:
    tail = title_tail(title)
    if tail == "古今和歌集仮名序":
        return (0, tail)
    if tail == "古今和歌集真名序":
        return (1, tail)
    match = KOKIN_VOLUME_RE.search(tail)
    if match:
        return (10 + zh_number_to_int(match.group(1)), tail)
    if tail == "墨滅歌":
        return (40, tail)
    return (9000 + fallback, tail)


def selected_items(book_id: str, source_dir: Path) -> list[dict[str, Any]]:
    manifest = load_json(source_dir / "manifest.json")
    items = [item for item in manifest.get("pages", []) if item.get("status") == "ok"]
    selected: list[dict[str, Any]] = []
    for fallback, item in enumerate(items, start=1):
        title = str(item.get("title") or "")
        tail = title_tail(title)
        if book_id == "manyoshu":
            if not MANYOSHU_VOLUME_RE.search(tail):
                continue
            item = {**item, "sort_key": manyoshu_sort_key(title, fallback)}
        elif book_id == "kokin-wakashu":
            if not (
                KOKIN_VOLUME_RE.search(tail)
                or tail in {"古今和歌集仮名序", "古今和歌集真名序", "墨滅歌"}
            ):
                continue
            item = {**item, "sort_key": kokin_sort_key(title, fallback)}
        selected.append(item)
    selected.sort(key=lambda item: item["sort_key"])
    return selected


def parse_manyoshu_records(raw: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    current_field = ""
    for raw_line in raw.splitlines():
        line = useful_line(raw_line)
        if not line:
            continue
        match = FIELD_RE.match(line)
        if match:
            field, rest = match.group(1).strip(), match.group(2).strip()
            current_field = field
            if field == "歌番号":
                if current:
                    records.append(current)
                current = {"歌番号": rest}
            elif current is not None:
                current[field] = rest
            continue
        if current is not None and current_field in {"題詞", "原文", "訓読", "仮名", "左注"}:
            current[current_field] = clean_reference_text((current.get(current_field, "") + " " + line).strip())
    if current:
        records.append(current)
    out: list[dict[str, str]] = []
    for record in records:
        kundoku = clean_reference_text(record.get("訓読", ""))
        if not kundoku or not HAN_OR_KANA_RE.search(kundoku):
            continue
        number = clean_reference_text(record.get("歌番号", ""))
        topic = clean_reference_text(record.get("題詞", ""))
        left_note = clean_reference_text(record.get("左注", ""))
        source = f"歌 {number}。"
        if topic and topic != "なし":
            source += f"題詞：{topic}。"
        source += f"訓読：{kundoku}。"
        if left_note and left_note != "なし":
            source += f"左注：{left_note}。"
        out.append(
            {
                "source_ja": source,
                "source_original": clean_reference_text(record.get("原文", "")),
                "source_kana": clean_reference_text(record.get("仮名", "")),
                "poem_number": number,
            }
        )
    return out


def parse_kokin_records(raw: str, *, prose_title: str) -> list[dict[str, str]]:
    lines = [line for line in (useful_line(line) for line in raw.splitlines()) if line]
    records: list[dict[str, str]] = []
    current: list[str] = []
    current_number = ""

    def flush() -> None:
        nonlocal current, current_number
        if current_number and current:
            content = [line for line in current if line != current_number]
            if content:
                source = f"{current_number}。"
                if content and content[0].startswith("[詞書]"):
                    source += "詞書：" + content.pop(0).removeprefix("[詞書]").strip() + "。"
                if content:
                    author = content.pop(0)
                    if not author.startswith("[") and "－" not in author:
                        source += f"作者：{author}。"
                    else:
                        content.insert(0, author)
                poem = next((line for line in content if "－" not in line and HAN_OR_KANA_RE.search(line)), "")
                if poem:
                    source += f"歌：{poem}。"
                records.append({"source_ja": source, "poem_number": current_number})
        current = []
        current_number = ""

    prose_lines: list[str] = []
    for line in lines:
        if re.fullmatch(r"\d{5}", line):
            flush()
            current_number = line
            current = [line]
            continue
        if current_number:
            if line.startswith("[") and not line.startswith("[詞書]"):
                continue
            current.append(line)
        else:
            if line not in {prose_title, "古今和歌集"}:
                prose_lines.append(line)
    flush()
    if records:
        return records
    prose = clean_reference_text("。".join(line.rstrip("。") for line in prose_lines if HAN_OR_KANA_RE.search(line)))
    return [{"source_ja": piece, "poem_number": ""} for piece in split_paragraph(prose, 700)]


def chapter_records(book_id: str, source_dir: Path, item: dict[str, Any]) -> list[dict[str, str]]:
    raw = read_raw(source_dir, item)
    if book_id == "manyoshu":
        return parse_manyoshu_records(raw)
    return parse_kokin_records(raw, prose_title=title_tail(str(item.get("title") or "")))


def chapter_title(book_id: str, item: dict[str, Any]) -> str:
    header = ""
    raw = item.get("raw")
    source_dir = ROOT / BOOKS[book_id]["source_dir"]
    if raw:
        header = extract_raw_wiki_header_section(source_dir / raw)
    tail = title_tail(str(item.get("title") or ""))
    return header or tail


def reference_for(book: dict[str, Any], item: dict[str, Any], record: dict[str, str]) -> dict[str, Any]:
    en_refs = []
    for ref_path in book.get("english_refs", []):
        path = ROOT / ref_path
        raw_text = ""
        if (path / "raw").exists():
            raw_text = "\n\n".join(
                clean_reference_text(clean_wiki_markup(p.read_text(encoding="utf-8", errors="replace")))
                for p in sorted((path / "raw").glob("*.wiki"))
            )
        en_refs.append(
            {
                "path": ref_path,
                "available": bool(raw_text.strip()),
                "excerpt": raw_text[:3200],
                "note": "Broad English Wikisource reference; use only where it clearly matches this poem/chapter.",
            }
        )
    return {
        "ja": {
            "available": True,
            "chapter": title_tail(str(item.get("title") or "")),
            "source_url": source_url(item),
            "source_original": record.get("source_original", ""),
            "source_kana": record.get("source_kana", ""),
        },
        "en": en_refs,
        "zh_primary": {
            "available": False,
            "chapter": title_tail(str(item.get("title") or "")),
            "note": "No matching Chinese Wikisource root was found; generate Chinese from the Japanese source.",
        },
    }


def write_markdown(book_id: str, book: dict[str, Any], chapters: list[dict[str, Any]]) -> Path:
    path = ROOT / "books" / book_id / "markdown" / "japanese-source.md"
    lines = [f"# {book['book_title_ja']}", ""]
    for chapter in chapters:
        lines.extend([f"## {chapter['title_ja']}", ""])
        for paragraph in chapter["paragraphs"]:
            lines.extend([paragraph["ja"], ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def prepare(book_id: str, *, max_chars: int, force: bool) -> None:
    if book_id not in BOOKS:
        raise KeyError(f"unknown Japanese classical book id: {book_id}")
    book = BOOKS[book_id]
    source_dir = ROOT / book["source_dir"]
    out_root = ROOT / "books" / book_id
    chunk_dir = out_root / "work" / "trilingual" / "chunks"
    chunks_jsonl = chunk_dir / "chunks.jsonl"
    manifest_path = chunk_dir / "manifest.json"
    plan_path = out_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print(f"{book_id}: already prepared")
        return

    chunks: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    chunk_counter = 0
    for chapter_number, item in enumerate(selected_items(book_id, source_dir), start=1):
        title_ja = chapter_title(book_id, item)
        title_en = f"{book['book_title_en']} {chapter_number}: {title_ja}"
        title_zh = title_ja
        chapter_paragraphs: list[dict[str, str]] = []
        for record in chapter_records(book_id, source_dir, item):
            source_ja = clean_reference_text(record["source_ja"])
            for piece in split_paragraph(source_ja, max_chars):
                chunk_counter += 1
                chunk_id = f"{book_id}-chunk-{chunk_counter:04d}"
                paragraph_id = f"{book_id}-p{chunk_counter:05d}"
                chapter_id = f"{book_id}-chapter-{chapter_number:02d}"
                chunk = {
                    "schema_version": 1,
                    "task_type": "trilingual_standard",
                    "book_id": book_id,
                    "chunk_id": chunk_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "chapter_title_en": title_en,
                    "chapter_title_zh": title_zh,
                    "chapter_title_ja": title_ja,
                    "chapter_part_en": record.get("poem_number") or f"part {chunk_counter}",
                    "source_spine_lang": "ja",
                    "paragraphs": [{"id": paragraph_id, "ja": piece}],
                    "reference": reference_for(book, item, record),
                }
                chunks.append(chunk)
                chapter_paragraphs.append({"id": paragraph_id, "ja": piece})
        if chapter_paragraphs:
            chapters.append({"title_ja": title_ja, "paragraphs": chapter_paragraphs})

    markdown = write_markdown(book_id, book, chapters)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    source_paths = {
        "japanese_wikisource": book["source_dir"],
        "japanese_markdown": str(markdown.relative_to(ROOT)),
    }
    for index, ref in enumerate(book.get("english_refs", []), start=1):
        source_paths[f"english_reference_{index}"] = ref
    for index, ref in enumerate(book.get("missing_refs", []), start=1):
        source_paths[f"missing_reference_manifest_{index}"] = ref
    for index, ref in enumerate(book.get("extra_refs", []), start=1):
        source_paths[f"extra_reference_{index}"] = ref
    prepared_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "task_mode": "trilingual_japanese_classical_main",
        "source_spine_lang": "ja",
        "book_title_en": book["book_title_en"],
        "book_title_zh": book["book_title_zh"],
        "book_title_ja": book["book_title_ja"],
        "author": book["author"],
        "author_reading_ja": book["author_reading_ja"],
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "chunks": [
            {"chunk_id": chunk["chunk_id"], "paragraph_ids": [p["id"] for p in chunk["paragraphs"]]}
            for chunk in chunks
        ],
        "source_paths": source_paths,
        "source_sha256": {str(markdown.relative_to(ROOT)): sha256(markdown)},
        "source_note": book["source_note"],
        "prepared_at": prepared_at,
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "launchable",
        "launchable": True,
        "task_mode": "trilingual_japanese_classical_main",
        "source_language": "ja",
        "book_title_en": book["book_title_en"],
        "book_title_zh": book["book_title_zh"],
        "book_title_ja": book["book_title_ja"],
        "author": book["author"],
        "author_reading_ja": book["author_reading_ja"],
        "book_description": f"{book['book_title_ja']} with Japanese source text and English/Chinese overlays.",
        "source_paths": source_paths,
        "source_note": book["source_note"],
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{book_id}/work/trilingual/interlinear/chunks",
        "assembled_json": f"books/{book_id}/work/trilingual/preview/{book_id}.partial.json",
        "build_root": f"build/{book_id}",
        "prepared_at": prepared_at,
    }
    write_json(plan_path, plan)
    print(f"{book_id}: chapters={len(chapters)} chunks={len(chunks)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True, choices=sorted(BOOKS))
    parser.add_argument("--max-chars", type=int, default=680)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for book_id in args.book_id:
        prepare(book_id, max_chars=args.max_chars, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
