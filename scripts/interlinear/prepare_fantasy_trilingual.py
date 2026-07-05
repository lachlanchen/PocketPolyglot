#!/usr/bin/env python3
"""Prepare fantasy EN/JP/ZH trilingual chunk tasks.

This script is preparation-only. It uses the standard trilingual chunk schema
from ``prepare_mars_fiction_trilingual.py`` but adds tolerant EPUB extraction
for malformed or multi-volume fantasy bundles.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

import prepare_mars_fiction_trilingual as base


ROOT = Path(__file__).resolve().parents[2]
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


WORD_NUMBERS = {
    "ONE": "1",
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
    "TEN": "10",
    "ELEVEN": "11",
    "TWELVE": "12",
    "THIRTEEN": "13",
    "FOURTEEN": "14",
    "FIFTEEN": "15",
    "SIXTEEN": "16",
    "SEVENTEEN": "17",
    "EIGHTEEN": "18",
    "NINETEEN": "19",
    "TWENTY": "20",
}


class SegmentConfig(dict[str, Any]):
    pass


EPUB_SEGMENTS: dict[str, SegmentConfig] = {
    "sources/lord-of-the-rings/en/The Lord of the Rings.epub": {
        "start_marker": "THE FELLOWSHIP OF THE RING",
        "end_marker": "THE TWO TOWERS",
        "start_occurrence": "last_before_end",
    },
    "sources/lord-of-the-rings/zh/魔戒全集.epub": {
        "start_marker": "第一节 期待已久的宴会",
        "end_marker": "《魔戒》二部曲--《双城奇谋》",
        "start_occurrence": "last_before_end",
    },
    "sources/harry-potter/en/Harry Potter Series.epub": {
        "opf_filter": lambda name: name.startswith("1/"),
        "start_marker": "CHAPTER ONE",
        "start_occurrence": "first",
        "normalize_chapter_words": True,
        "combine_following_title_for_chapter": True,
        "drop_repeated_title": "HP 1 - Harry Potter and the Sorcerer's Stone",
    },
    "sources/harry-potter/zh/哈利·波特.epub": {
        "start_marker": "第一章 大难不死的男孩",
        "end_marker": "第一章 最糟糕的生日",
        "start_occurrence": "first",
    },
    "sources/a-song-of-ice-and-fire/en/individual-volumes/01 - A Game of Thrones.epub": {
        "start_marker": "Prologue",
        "start_occurrence": "last",
        "drop_repeated_title": "A Game of Thrones",
        "pov_headings": {
            "Prologue",
            "Bran",
            "Catelyn",
            "Daenerys",
            "Eddard",
            "Jon",
            "Arya",
            "Tyrion",
            "Sansa",
        },
    },
}


MOBI_SEGMENTS: dict[str, SegmentConfig] = {
    "sources/a-song-of-ice-and-fire/zh/乔治·R R 马丁经典奇幻系列（套装共22册）.mobi": {
        "start_marker": "序幕",
        "end_marker": "序幕",
        "start_hit_ordinal": 1,
        "merge_cjk_continuations": True,
    },
}


BOOKS: dict[str, base.BookConfig] = {
    "fellowship-of-the-ring": base.BookConfig(
        book_id="fellowship-of-the-ring",
        title_en="The Fellowship of the Ring",
        title_zh="魔戒现身",
        title_ja="指輪物語 旅の仲間",
        title_zh_reading="mó jiè xiàn shēn",
        title_ja_reading="ゆびわものがたり たび の なかま",
        author="J. R. R. Tolkien",
        author_reading_zh="tuō ěr jīn",
        author_reading_ja="トールキン",
        en_source=Path("sources/lord-of-the-rings/en/The Lord of the Rings.epub"),
        zh_source=Path("sources/lord-of-the-rings/zh/魔戒全集.epub"),
        en_start_marker="THE FELLOWSHIP OF THE RING",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja_with_image_only_ja_reference",
        book_description=(
            "J. R. R. Tolkien, The Fellowship of the Ring. English EPUB is the "
            "alignment spine; Chinese EPUB bundle is trimmed to the first Lord of "
            "the Rings volume and used as a published translation reference. The "
            "local Japanese PDF is image-only, so Japanese is generated in natural "
            "modern Japanese unless an OCR cache is prepared later."
        ),
    ),
    "harry-potter-1": base.BookConfig(
        book_id="harry-potter-1",
        title_en="Harry Potter and the Sorcerer's Stone",
        title_zh="哈利·波特与魔法石",
        title_ja="ハリー・ポッターと賢者の石",
        title_zh_reading="hā lì bō tè yǔ mó fǎ shí",
        title_ja_reading="ハリー ポッター と けんじゃ の いし",
        author="J. K. Rowling",
        author_reading_zh="luó lín",
        author_reading_ja="ローリング",
        en_source=Path("sources/harry-potter/en/Harry Potter Series.epub"),
        zh_source=Path("sources/harry-potter/zh/哈利·波特.epub"),
        en_start_marker="Chapter 1",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja_with_image_only_ja_reference",
        book_description=(
            "J. K. Rowling, Harry Potter and the Sorcerer's Stone. English series "
            "EPUB is trimmed to volume one and used as the alignment spine; Chinese "
            "EPUB is trimmed to volume one and used as a published translation "
            "reference. The local Japanese PDF is image-only, so Japanese is "
            "generated in natural modern Japanese unless OCR is prepared later."
        ),
    ),
    "a-game-of-thrones": base.BookConfig(
        book_id="a-game-of-thrones",
        title_en="A Game of Thrones",
        title_zh="权力的游戏",
        title_ja="七王国の玉座",
        title_zh_reading="quán lì de yóu xì",
        title_ja_reading="しちおうこく の ぎょくざ",
        author="George R. R. Martin",
        author_reading_zh="qiáo zhì mǎ dīng",
        author_reading_ja="ジョージ アール アール マーティン",
        en_source=Path("sources/a-song-of-ice-and-fire/en/individual-volumes/01 - A Game of Thrones.epub"),
        zh_source=Path("sources/a-song-of-ice-and-fire/zh/乔治·R R 马丁经典奇幻系列（套装共22册）.mobi"),
        en_start_marker="Prologue",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja",
        book_description=(
            "George R. R. Martin, A Game of Thrones. English volume-one EPUB is the "
            "alignment spine; Chinese MOBI anthology is trimmed to the first book "
            "and used as a broad published translation reference. No Japanese "
            "volume source is staged, so Japanese is generated in natural modern "
            "Japanese."
        ),
    ),
}


IMAGE_ONLY_JAPANESE_REFERENCES: dict[str, str] = {
    "fellowship-of-the-ring": "sources/lord-of-the-rings/jp/指輪物語 旅の仲間 上1.pdf",
    "harry-potter-1": "sources/harry-potter/jp/ハリー・ポッターと賢者の石.pdf",
}


def normalize_key(path: Path) -> str:
    return str(path).replace("\\", "/")


def clean_html_text(raw: str) -> list[str]:
    soup = BeautifulSoup(raw, "lxml")
    for node in soup(["script", "style", "nav"]):
        node.decompose()
    return [base.clean_line(line) for line in soup.get_text("\n").splitlines()]


def opf_spine_htmls(zip_file: zipfile.ZipFile, opf_name: str) -> list[str]:
    root = ET.fromstring(zip_file.read(opf_name))
    manifest: dict[str, str] = {}
    for item in root.findall(".//{*}manifest/{*}item"):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if not item_id or not href:
            continue
        manifest[item_id] = posixpath.normpath(posixpath.join(posixpath.dirname(opf_name), href))
    htmls: list[str] = []
    for itemref in root.findall(".//{*}spine/{*}itemref"):
        href = manifest.get(itemref.attrib.get("idref", ""))
        if href:
            htmls.append(href)
    return htmls


def read_epub_lines(path: Path, opf_filter: Callable[[str], bool] | None = None) -> list[str]:
    full_path = ROOT / path
    with zipfile.ZipFile(full_path) as zip_file:
        names = set(zip_file.namelist())
        opfs = sorted(name for name in names if name.endswith(".opf"))
        if opf_filter:
            opfs = [name for name in opfs if opf_filter(name)]
        htmls: list[str] = []
        for opf in opfs:
            htmls.extend(opf_spine_htmls(zip_file, opf))
        if not htmls:
            htmls = sorted(name for name in names if re.search(r"\.(?:xhtml|html|htm)$", name, re.IGNORECASE))

        lines: list[str] = []
        seen: set[str] = set()
        for html_name in htmls:
            if html_name not in names or html_name in seen:
                continue
            seen.add(html_name)
            if not re.search(r"\.(?:xhtml|html|htm)$", html_name, re.IGNORECASE):
                continue
            lines.extend(line for line in clean_html_text(zip_file.read(html_name).decode("utf-8", errors="replace")) if line)
            lines.append("")
    return lines


def marker_matches(line: str, marker: str) -> bool:
    return base.marker_matches(line, marker)


def find_segment_bounds(lines: list[str], config: SegmentConfig) -> tuple[int, int]:
    start_marker = config.get("start_marker")
    end_marker = config.get("end_marker")
    start_hits = [index for index, line in enumerate(lines) if start_marker and marker_matches(line, str(start_marker))]
    end_hits = [index for index, line in enumerate(lines) if end_marker and marker_matches(line, str(end_marker))]
    start = 0
    if start_hits:
        ordinal = config.get("start_hit_ordinal")
        if isinstance(ordinal, int) and 0 <= ordinal < len(start_hits):
            start = start_hits[ordinal]
        else:
            occurrence = config.get("start_occurrence", "first")
            if occurrence == "last":
                start = start_hits[-1]
            elif occurrence == "last_before_end" and end_hits:
                eligible = [hit for hit in start_hits if any(end > hit for end in end_hits)]
                start = eligible[-1] if eligible else start_hits[-1]
            else:
                start = start_hits[0]
    end = len(lines)
    if end_hits:
        later = [hit for hit in end_hits if hit > start]
        if later:
            end = later[0]
    return start, end


def normalize_fantasy_lines(lines: list[str], config: SegmentConfig) -> list[str]:
    drop_repeated_title = config.get("drop_repeated_title")
    cleaned: list[str] = []
    for line in lines:
        if not line:
            continue
        if drop_repeated_title and line == drop_repeated_title:
            continue
        if line.startswith("r. and Mrs. Dursley, of number four, Privet Drive"):
            line = "M" + line
        if config.get("normalize_chapter_words"):
            match = re.fullmatch(r"CHAPTER\s+([A-Z]+)", line)
            if match and match.group(1) in WORD_NUMBERS:
                line = f"Chapter {WORD_NUMBERS[match.group(1)]}"
        if re.fullmatch(r"\[\d{1,4}\]", line):
            continue
        cleaned.append(line)

    out: list[str] = []
    index = 0
    while index < len(cleaned):
        line = cleaned[index]
        if config.get("combine_following_title_for_chapter"):
            match = re.fullmatch(r"Chapter\s+(\d{1,3})", line)
            if match and index + 1 < len(cleaned):
                title = cleaned[index + 1]
                if 2 <= len(title) <= 90 and not re.search(r"[.!?。！？]$", title):
                    out.append(f"Chapter {match.group(1)}: {title.title() if title.isupper() else title}")
                    index += 2
                    continue
        pov_headings = config.get("pov_headings")
        if isinstance(pov_headings, set) and line in pov_headings:
            if line == "Prologue":
                out.append("Prologue")
            else:
                count = 1 + sum(1 for item in out if re.match(r"^\d{1,3}:\s+", item))
                out.append(f"{count}: {line}")
            index += 1
            continue
        out.append(line)
        index += 1
    return out


def merge_cjk_continuations(lines: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    terminal = re.compile(r"[。！？.!?」』”’）)]$")
    continuation_start = re.compile(r"^[，、。！？；：」』”’）)]")
    cjk_heading_like = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff・•·A-Za-z0-9]{1,10}$")
    while index < len(lines):
        line = lines[index]
        if line in {"序幕", "正文"}:
            out.append(line)
            index += 1
            continue
        if index + 1 < len(lines):
            nxt = lines[index + 1]
            if continuation_start.search(nxt):
                out.append(line + nxt)
                index += 2
                continue
            if line.startswith("“") and len(line) < 18 and not terminal.search(line):
                out.append(line + nxt)
                index += 2
                continue
            if (
                len(line) > 20
                and base.CJK_RE.search(line)
                and base.CJK_RE.search(nxt)
                and not terminal.search(line)
                and not cjk_heading_like.fullmatch(nxt)
            ):
                out.append(line + nxt)
                index += 2
                continue
        out.append(line)
        index += 1
    return out


def segmented_epub_lines(path: Path) -> list[str]:
    key = normalize_key(path)
    config = EPUB_SEGMENTS.get(key)
    lines = read_epub_lines(path, config.get("opf_filter") if config else None)
    if config:
        start, end = find_segment_bounds(lines, config)
        lines = lines[start:end]
        lines = normalize_fantasy_lines(lines, config)
        if config.get("merge_cjk_continuations"):
            lines = merge_cjk_continuations(lines)
    return [line for line in lines if line]


def segmented_mobi_lines(original_mobi_lines: Callable[[Path], list[str]], path: Path) -> list[str]:
    key = normalize_key(path)
    lines = original_mobi_lines(path)
    config = MOBI_SEGMENTS.get(key)
    if config:
        start, end = find_segment_bounds(lines, config)
        lines = lines[start:end]
        lines = normalize_fantasy_lines(lines, config)
        if config.get("merge_cjk_continuations"):
            lines = merge_cjk_continuations(lines)
    return [line for line in lines if line]


def inject_image_only_japanese_reference(book_id: str) -> None:
    source = IMAGE_ONLY_JAPANESE_REFERENCES.get(book_id)
    if not source:
        return
    source_path = Path(source)
    book_root = ROOT / "books" / book_id
    for rel in (book_root / "book-plan.json", book_root / "work/trilingual/chunks/manifest.json"):
        data = json.loads(rel.read_text(encoding="utf-8"))
        data.setdefault("source_paths", {})["ja"] = source
        data.setdefault("source_sha256", {})["ja"] = base.sha256(source_path)
        notes = data.setdefault("preparation_notes", {})
        notes["japanese_reference"] = (
            "Japanese source exists locally but is image-only in pdftotext; "
            "prepare OCR later if exact Japanese-source alignment is required."
        )
        rel.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_selected(book_ids: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    original_epub_lines = base.epub_lines
    original_mobi_lines = base.mobi_lines
    base.epub_lines = segmented_epub_lines
    base.mobi_lines = lambda path: segmented_mobi_lines(original_mobi_lines, path)
    try:
        results: list[dict[str, Any]] = []
        for book_id in book_ids:
            result = base.prepare_book(BOOKS[book_id], args)
            inject_image_only_japanese_reference(book_id)
            plan_path = ROOT / "books" / book_id / "book-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["preparation_notes"] = {
                **plan.get("preparation_notes", {}),
                "script": "scripts/interlinear/prepare_fantasy_trilingual.py",
                "english_spine": "English source is the chunk spine.",
                "chinese_reference": "Chinese source is trimmed to the requested first book and used as a compact ratio reference window.",
                "start_command": f"WORKERS=10 MODEL=gpt-5.5 REASONING=low bash scripts/interlinear/start_trilingual_book_tmux.sh {book_id}",
            }
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results.append(result)
        return results
    finally:
        base.epub_lines = original_epub_lines
        base.mobi_lines = original_mobi_lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--reference-chars", type=int, default=2200)
    args = parser.parse_args()

    selected = args.book_id or list(BOOKS)
    for result in prepare_selected(selected, args):
        print(
            "prepared "
            f"book_id={result['book_id']} chunks={result['chunks']} "
            f"en_chapters={result['english_chapters']} zh_chapters={result['chinese_chapters']} "
            f"spine={result['spine']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
