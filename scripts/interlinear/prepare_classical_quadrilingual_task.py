#!/usr/bin/env python3
"""Prepare classical Chinese source trees as quadrilingual wenyan-main tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PLAN = ROOT / "data" / "source-plan" / "classical-quadrilingual-source-batch.json"

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SPACE_RE = re.compile(r"\s+")
SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]")
TRAILING_PAGE_CHROME_RE = re.compile(r"(NewPP limit report|Transclusion expansion time report|Saved in parser cache)", re.I)
SANGUOZHI_VOLUME_RE = re.compile(r"卷\s*0*(\d+)")
CHAPTER_ORDINAL_RE = re.compile(r"([一二三四五六七八九十百〇零]+)$")

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
    "XIX": 19,
    "XX": 20,
    "XXI": 21,
    "XXII": 22,
    "XXIII": 23,
    "XXIV": 24,
    "XXV": 25,
    "XXVI": 26,
    "XXVII": 27,
    "XXVIII": 28,
    "XXIX": 29,
    "XXX": 30,
    "XXXI": 31,
    "XXXII": 32,
    "XXXIII": 33,
}

ZHUANGZI_CANONICAL_ORDER = {
    "逍遙遊": 1,
    "齊物論": 2,
    "養生主": 3,
    "人間世": 4,
    "德充符": 5,
    "大宗師": 6,
    "應帝王": 7,
    "駢拇": 8,
    "馬蹄": 9,
    "胠篋": 10,
    "在宥": 11,
    "天地": 12,
    "天道": 13,
    "天運": 14,
    "刻意": 15,
    "繕性": 16,
    "秋水": 17,
    "至樂": 18,
    "達生": 19,
    "山木": 20,
    "田子方": 21,
    "知北遊": 22,
    "庚桑楚": 23,
    "徐無鬼": 24,
    "則陽": 25,
    "外物": 26,
    "寓言": 27,
    "讓王": 28,
    "盜跖": 29,
    "說劍": 30,
    "漁父": 31,
    "列禦寇": 32,
    "天下": 33,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    if not path.exists() or path.is_dir():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\u3000", "").replace("\xa0", "")
    text = SPACE_RE.sub("", text)
    text = text.strip()
    if TRAILING_PAGE_CHROME_RE.search(text):
        return ""
    return text


def zh_number_to_int(text: str) -> int:
    values = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if not text:
        return 0
    if text == "十":
        return 10
    if "百" in text:
        left, _, right = text.partition("百")
        return (values.get(left, 1) if left else 1) * 100 + zh_number_to_int(right)
    if "十" in text:
        left, _, right = text.partition("十")
        return (values.get(left, 1) if left else 1) * 10 + (values.get(right, 0) if right else 0)
    total = 0
    for char in text:
        total = total * 10 + values.get(char, 0)
    return total


def title_tail(title: str) -> str:
    return title.split("/")[-1].strip()


def normalize_chapter_title(book_id: str, title: str) -> str:
    tail = title_tail(title)
    if book_id == "sanguozhi":
        return tail.replace("卷", "卷 ")
    return tail


def chapter_sort_key(book_id: str, title: str, html_name: str, header_text: str) -> tuple[int, str]:
    tail = title_tail(title)
    if book_id == "zhuangzi":
        number = ZHUANGZI_CANONICAL_ORDER.get(tail)
        if not number:
            match = CHAPTER_ORDINAL_RE.search(header_text)
            number = zh_number_to_int(match.group(1)) if match else 0
        return (number or 9999, tail)
    if book_id == "sanguozhi":
        if "上三国志註表" in tail or "上三國志註表" in tail:
            return (0, tail)
        match = SANGUOZHI_VOLUME_RE.search(tail) or SANGUOZHI_VOLUME_RE.search(html_name)
        return (int(match.group(1)) if match else 9999, tail)
    return (9999, tail)


def clean_soup_for_source(content: BeautifulSoup, *, drop_small: bool) -> None:
    selectors = [
        "style",
        "script",
        "table",
        "ul#plainSister",
        ".noprint",
        ".sisitem",
        ".variant-tooltip",
        "sup",
        "link",
        "figure",
    ]
    for selector in selectors:
        for tag in content.select(selector):
            tag.decompose()
    if drop_small:
        for tag in content.find_all("small"):
            tag.decompose()


def extract_html_paragraphs(path: Path, *, drop_small: bool) -> tuple[str, list[str]]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    content = soup.select_one(".mw-parser-output") or soup
    clean_soup_for_source(content, drop_small=drop_small)
    header_text = clean_text("".join(item.get_text("", strip=True) for item in soup.find_all("title")[:1]))
    paragraphs: list[str] = []
    for node in content.find_all("p"):
        text = clean_text(node.get_text("", strip=False))
        if not text or not HAN_RE.search(text):
            continue
        if text.startswith("Source:") or text in {"←", "→"}:
            continue
        paragraphs.append(text)
    return header_text, paragraphs


def remove_balanced_templates(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            depth = 1
            end = index + 2
            while end < len(text) and depth:
                if text.startswith("{{", end):
                    depth += 1
                    end += 2
                elif text.startswith("}}", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            body = text[index + 2 : end - 2] if depth == 0 else text[index + 2 :]
            name, _, rest = body.partition("|")
            name = name.strip()
            if name in {"YL", "lang", "j", "zh"}:
                out.append(rest.split("|", 1)[0].strip())
            elif name == "另":
                out.append(rest.split("|", 1)[0].strip())
            elif name in {"*"}:
                pass
            else:
                pass
            index = end
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def clean_wiki_markup(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = remove_balanced_templates(text)
    text = re.sub(r"\[\[([^]|\n]+)\|([^]\n]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^]\n]+)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    return text


def extract_raw_wiki_paragraphs(path: Path) -> tuple[str, list[str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = clean_wiki_markup(raw)
    header_text = ""
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = clean_text("".join(buffer))
        buffer = []
        if text and HAN_RE.search(text):
            paragraphs.append(text)

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("[[Category:") or stripped.startswith("__"):
            continue
        heading = re.fullmatch(r"=+\s*(.+?)\s*=+", stripped)
        if heading:
            flush()
            if not header_text:
                header_text = clean_text(heading.group(1))
            continue
        if stripped.startswith("|"):
            continue
        buffer.append(stripped)
    flush()
    return header_text, paragraphs


def split_paragraph(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    last_break = 0
    for match in SENTENCE_END_RE.finditer(text):
        last_break = match.end()
        if last_break - start >= max_chars:
            pieces.append(text[start:last_break])
            start = last_break
    if start < len(text):
        tail = text[start:]
        if len(tail) > max_chars * 1.5:
            offset = 0
            while offset < len(tail):
                end = min(len(tail), offset + max_chars)
                pieces.append(tail[offset:end])
                offset = end
        else:
            pieces.append(tail)
    return [piece.strip() for piece in pieces if piece.strip()]


def source_plan_by_id() -> dict[str, dict[str, Any]]:
    data = load_json(SOURCE_PLAN)
    return {book["book_id"]: book for book in data["books"]}


def manifest_items(book: dict[str, Any]) -> list[dict[str, Any]]:
    source = next(layer for layer in book["source_layers"] if layer["layer"] == "wenyan" and layer["role"] == "classical_source")
    source_dir = ROOT / source["path"]
    manifest_path = source_dir / "manifest.json"
    items = [item for item in load_json(manifest_path) if item.get("status") == "ok"]
    prepared = []
    for item in items:
        title = str(item.get("title", ""))
        if "/" not in title:
            continue
        html_rel = item.get("html")
        raw_rel = item.get("raw")
        html_path = source_dir / html_rel if html_rel else Path()
        raw_path = source_dir / raw_rel if raw_rel else Path()
        if html_rel and html_path.exists():
            source_path = html_path
            header_text, paragraphs = extract_html_paragraphs(html_path, drop_small=book["book_id"] == "sanguozhi")
        elif raw_rel and raw_path.exists():
            source_path = raw_path
            header_text, paragraphs = extract_raw_wiki_paragraphs(raw_path)
        else:
            continue
        if not paragraphs:
            continue
        prepared.append(
            {
                **item,
                "source_path": source_path,
                "header_text": header_text,
                "paragraphs": paragraphs,
                "sort_key": chapter_sort_key(book["book_id"], title, source_path.name, header_text),
            }
        )
    prepared.sort(key=lambda item: item["sort_key"])
    return prepared


def load_zhuangzi_giles_windows() -> dict[int, dict[str, str]]:
    path = ROOT / "sources" / "zhuangzi" / "en" / "gutenberg-giles" / "Chuang-Tzu-Giles-59709.txt"
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\s*CHAPTER\s+([IVXLCDM]+)\.\s*", line)
        if match:
            number = ROMAN_TO_INT.get(match.group(1))
            if number:
                starts.append((number, index))
    windows: dict[int, dict[str, str]] = {}
    for offset, (number, start) in enumerate(starts):
        end = starts[offset + 1][1] if offset + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        block = re.sub(r"\n{3,}", "\n\n", block).strip()
        windows[number] = {
            "source": "Giles Project Gutenberg Chuang Tzu",
            "chapter_number": str(number),
            "line_window": f"{start + 1}-{end}",
            "excerpt": block[:4200],
        }
    return windows


def load_sanguozhi_open_en_windows() -> dict[int, dict[str, str]]:
    raw_dir = ROOT / "sources" / "sanguozhi" / "en" / "wikisource-open-license" / "raw"
    if not raw_dir.exists():
        return {}
    windows: dict[int, dict[str, str]] = {}
    for path in sorted(raw_dir.glob("*.wiki")):
        match = re.search(r"Volume[ _](\d+)", path.name)
        if not match:
            continue
        number = int(match.group(1))
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
        text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
        text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        windows[number] = {
            "source": "English Wikisource open-license Sanguozhi excerpt",
            "chapter_number": str(number),
            "path": str(path.relative_to(ROOT)),
            "excerpt": text[:4200],
        }
    return windows


def broad_references(book: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    layers = book["source_layers"]
    paths_by_layer: dict[str, list[dict[str, str]]] = OrderedDict()
    for layer in layers:
        paths_by_layer.setdefault(layer["layer"], []).append(
            {
                "role": layer["role"],
                "path": layer["path"],
                "quality": layer["quality"],
            }
        )
    reference: dict[str, Any] = {
        "scope": "References are broad chapter/source references. Preserve the wenyan source exactly and only use references when they clearly match.",
        "paths": paths_by_layer,
    }
    if book["book_id"] == "zhuangzi":
        reference["en"] = load_zhuangzi_giles_windows().get(chapter_number, {})
        reference["zh_modern"] = {
            "source": "sources/zhuangzi/zh/modern-annotated/庄子_ 中华经典名著全本全注全译丛书.pdf",
            "note": "Scanned/metadata-only under pdftotext; use as source reference for later OCR, not as direct text in this chunk.",
        }
        reference["ja_modern"] = {
            "source": "sources/zhuangzi/jp/modern-translation-scan",
            "note": "Public-domain Japanese modern translation scan; use as broad reference when OCR is prepared.",
        }
    elif book["book_id"] == "sanguozhi":
        reference["en"] = load_sanguozhi_open_en_windows().get(chapter_number, {})
        reference["zh_modern"] = {
            "source": "sources/sanguozhi/zh/pei-songzhi-source-epub/三国志（中华经典普及文库）.epub",
            "note": "Chinese source edition with Pei Songzhi commentary; keep commentary out of the main wenyan spine unless explicitly represented as notes later.",
        }
        reference["ja_modern"] = {
            "source": "sources/sanguozhi/jp/wikisource-index",
            "note": "Index-only Japanese source. Generate natural modern Japanese where no matching source exists.",
        }
    return reference


def write_markdown(book: dict[str, Any], chapters: list[dict[str, Any]]) -> Path:
    markdown = ROOT / "books" / book["book_id"] / "markdown" / "wenyan.md"
    lines = [f"# {book['book_title_wenyan']}", ""]
    for chapter in chapters:
        lines.extend([f"## {chapter['chapter_title']}", ""])
        for paragraph in chapter["paragraphs"]:
            lines.extend([paragraph, ""])
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return markdown


def prepare(book_id: str, *, max_chars: int, force: bool) -> None:
    plans = source_plan_by_id()
    if book_id not in plans:
        raise KeyError(f"unknown book id: {book_id}")
    book = plans[book_id]
    out_root = ROOT / "books" / book_id
    chunk_dir = out_root / "work" / "quadrilingual" / "chunks"
    chunks_jsonl = chunk_dir / "chunks.jsonl"
    manifest_path = chunk_dir / "manifest.json"
    plan_path = out_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print(f"{book_id}: already prepared")
        return

    source_items = manifest_items(book)
    chapters: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    chunk_counter = 0
    for chapter_number, item in enumerate(source_items, start=1):
        chapter_title = normalize_chapter_title(book_id, str(item["title"]))
        chapter_paragraphs = item["paragraphs"]
        chapters.append({"chapter_title": chapter_title, "paragraphs": chapter_paragraphs})
        chapter_id = f"{book_id}-chapter-{chapter_number:02d}"
        for paragraph_number, paragraph in enumerate(chapter_paragraphs, start=1):
            for part_number, piece in enumerate(split_paragraph(paragraph, max_chars), start=1):
                chunk_counter += 1
                chunk_id = f"{book_id}-chunk-{chunk_counter:04d}"
                paragraph_id = f"{chunk_id}-p001"
                section_suffix = f" paragraph {paragraph_number}"
                if part_number > 1:
                    section_suffix += f" part {part_number}"
                chunks.append(
                    {
                        "schema_version": 1,
                        "task_type": "quadrilingual_wenyan_main",
                        "book_id": book_id,
                        "book_title_wenyan": book["book_title_wenyan"],
                        "chunk_id": chunk_id,
                        "chapter_id": chapter_id,
                        "chapter_number": chapter_number,
                        "chapter_title_wenyan": chapter_title,
                        "chapter_title_zh_modern": book.get("book_title_zh", book["book_title_wenyan"]) if chapter_number == 0 else chapter_title,
                        "chapter_title_ja_modern": book.get("book_title_ja", book["book_title_wenyan"]) if chapter_number == 0 else chapter_title,
                        "chapter_title_en": f"{book['book_title_en']} {chapter_number}: {chapter_title}",
                        "section_title_wenyan": f"{chapter_title}{section_suffix}",
                        "source_spine_lang": "wenyan",
                        "paragraphs": [{"id": paragraph_id, "wenyan": piece}],
                        "reference": broad_references(book, chapter_number),
                    }
                )

    markdown = write_markdown(book, chapters)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    source_paths = {
        layer["role"]: layer["path"]
        for layer in book["source_layers"]
    }
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": book["book_title_wenyan"],
        "book_title_zh_modern": book["book_title_zh"],
        "book_title_ja_modern": book["book_title_ja"],
        "book_title_en": book["book_title_en"],
        "author": book["author"],
        "author_reading_zh": book["author_reading_zh"],
        "author_reading_ja": book["author_reading_ja"],
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": source_paths | {"wenyan_markdown": str(markdown.relative_to(ROOT))},
        "source_sha256": {str(markdown.relative_to(ROOT)): sha256(markdown)},
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": book_id,
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
        "book_title_wenyan": manifest["book_title_wenyan"],
        "book_title_zh": manifest["book_title_zh_modern"],
        "book_title_ja": manifest["book_title_ja_modern"],
        "book_title_en": manifest["book_title_en"],
        "author": manifest["author"],
        "author_reading_zh": manifest["author_reading_zh"],
        "author_reading_ja": manifest["author_reading_ja"],
        "book_description": f"{book['book_title_wenyan']} with classical Chinese as the main text and English, modern Japanese, and modern Chinese overlays.",
        "source_paths": manifest["source_paths"],
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{book_id}/work/quadrilingual/interlinear/chunks",
        "assembled_json": f"books/{book_id}/work/quadrilingual/preview/{book_id}.partial.json",
        "build_root": f"build/{book_id}/wenyan-main-quadrilingual",
        "prepared_at": manifest["prepared_at"],
    }
    write_json(plan_path, plan)
    print(f"{book_id}: chapters={len(chapters)} chunks={len(chunks)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True)
    parser.add_argument("--max-chars", type=int, default=520)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for book_id in args.book_id:
        prepare(book_id, max_chars=args.max_chars, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
