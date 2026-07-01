#!/usr/bin/env python3
"""Prepare a Wikisource Bible EN/ZH/JA trilingual task.

The Bible is prepared by verse reference instead of prose paragraphs. English
KJV is the source spine, Chinese Union Version is an exact source layer, and
modern Japanese is generated because the Japanese Wikisource Kougo pages are
currently metadata/redaction pages rather than usable verse text.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from prepare_classical_quadrilingual_task import clean_reference_text, clean_wiki_markup, sha256


ROOT = Path(__file__).resolve().parents[2]
SPACE_RE = re.compile(r"\s+")
ZH_VERSE_RE = re.compile(r"\{\{verse\|(\d+)\|(\d+)\}\}")
EN_RAW_VERSE_RE = re.compile(r"\{\{verse\|chapter=(\d+)\|verse=(\d+)\}\}", re.I)
WIKI_TEMPLATE_RE = re.compile(r"\{\{([^{}|]+)\|([^{}]+)\}\}")


@dataclass(frozen=True)
class BibleBook:
    order: int
    en: str
    zh: str
    ja: str
    chapters: int
    en_wiki: str | None = None

    @property
    def en_page(self) -> str:
        return self.en_wiki or self.en


BOOKS: list[BibleBook] = [
    BibleBook(1, "Genesis", "創世記", "創世記", 50),
    BibleBook(2, "Exodus", "出埃及記", "出エジプト記", 40),
    BibleBook(3, "Leviticus", "利未記", "レビ記", 27),
    BibleBook(4, "Numbers", "民數記", "民数記", 36),
    BibleBook(5, "Deuteronomy", "申命記", "申命記", 34),
    BibleBook(6, "Joshua", "約書亞記", "ヨシュア記", 24),
    BibleBook(7, "Judges", "士師記", "士師記", 21),
    BibleBook(8, "Ruth", "路得記", "ルツ記", 4),
    BibleBook(9, "1 Samuel", "撒母耳記上", "サムエル記上", 31),
    BibleBook(10, "2 Samuel", "撒母耳記下", "サムエル記下", 24),
    BibleBook(11, "1 Kings", "列王紀上", "列王紀上", 22),
    BibleBook(12, "2 Kings", "列王紀下", "列王紀下", 25),
    BibleBook(13, "1 Chronicles", "歷代志上", "歴代志上", 29),
    BibleBook(14, "2 Chronicles", "歷代志下", "歴代志下", 36),
    BibleBook(15, "Ezra", "以斯拉記", "エズラ記", 10),
    BibleBook(16, "Nehemiah", "尼希米記", "ネヘミヤ記", 13),
    BibleBook(17, "Esther", "以斯帖記", "エステル記", 10),
    BibleBook(18, "Job", "約伯記", "ヨブ記", 42),
    BibleBook(19, "Psalms", "詩篇", "詩篇", 150),
    BibleBook(20, "Proverbs", "箴言", "箴言", 31),
    BibleBook(21, "Ecclesiastes", "傳道書", "伝道の書", 12),
    BibleBook(22, "Song of Solomon", "雅歌", "雅歌", 8),
    BibleBook(23, "Isaiah", "以賽亞書", "イザヤ書", 66),
    BibleBook(24, "Jeremiah", "耶利米書", "エレミヤ書", 52),
    BibleBook(25, "Lamentations", "耶利米哀歌", "哀歌", 5),
    BibleBook(26, "Ezekiel", "以西結書", "エゼキエル書", 48),
    BibleBook(27, "Daniel", "但以理書", "ダニエル書", 12),
    BibleBook(28, "Hosea", "何西阿書", "ホセア書", 14),
    BibleBook(29, "Joel", "約珥書", "ヨエル書", 3),
    BibleBook(30, "Amos", "阿摩司書", "アモス書", 9),
    BibleBook(31, "Obadiah", "俄巴底亞書", "オバデヤ書", 1),
    BibleBook(32, "Jonah", "約拿書", "ヨナ書", 4),
    BibleBook(33, "Micah", "彌迦書", "ミカ書", 7),
    BibleBook(34, "Nahum", "那鴻書", "ナホム書", 3),
    BibleBook(35, "Habakkuk", "哈巴谷書", "ハバクク書", 3),
    BibleBook(36, "Zephaniah", "西番雅書", "ゼパニヤ書", 3),
    BibleBook(37, "Haggai", "哈該書", "ハガイ書", 2),
    BibleBook(38, "Zechariah", "撒迦利亞書", "ゼカリヤ書", 14),
    BibleBook(39, "Malachi", "瑪拉基書", "マラキ書", 4),
    BibleBook(40, "Matthew", "馬太福音", "マタイによる福音書", 28),
    BibleBook(41, "Mark", "馬可福音", "マルコによる福音書", 16),
    BibleBook(42, "Luke", "路加福音", "ルカによる福音書", 24),
    BibleBook(43, "John", "約翰福音", "ヨハネによる福音書", 21),
    BibleBook(44, "Acts", "使徒行傳", "使徒行伝", 28, "Acts of the Apostles"),
    BibleBook(45, "Romans", "羅馬書", "ローマ人への手紙", 16),
    BibleBook(46, "1 Corinthians", "哥林多前書", "コリント人への第一の手紙", 16),
    BibleBook(47, "2 Corinthians", "哥林多後書", "コリント人への第二の手紙", 13),
    BibleBook(48, "Galatians", "加拉太書", "ガラテヤ人への手紙", 6),
    BibleBook(49, "Ephesians", "以弗所書", "エペソ人への手紙", 6),
    BibleBook(50, "Philippians", "腓立比書", "ピリピ人への手紙", 4),
    BibleBook(51, "Colossians", "歌羅西書", "コロサイ人への手紙", 4),
    BibleBook(52, "1 Thessalonians", "帖撒羅尼迦前書", "テサロニケ人への第一の手紙", 5),
    BibleBook(53, "2 Thessalonians", "帖撒羅尼迦後書", "テサロニケ人への第二の手紙", 3),
    BibleBook(54, "1 Timothy", "提摩太前書", "テモテへの第一の手紙", 6),
    BibleBook(55, "2 Timothy", "提摩太後書", "テモテへの第二の手紙", 4),
    BibleBook(56, "Titus", "提多書", "テトスへの手紙", 3),
    BibleBook(57, "Philemon", "腓利門書", "ピレモンへの手紙", 1),
    BibleBook(58, "Hebrews", "希伯來書", "ヘブル人への手紙", 13),
    BibleBook(59, "James", "雅各書", "ヤコブの手紙", 5),
    BibleBook(60, "1 Peter", "彼得前書", "ペテロの第一の手紙", 5),
    BibleBook(61, "2 Peter", "彼得後書", "ペテロの第二の手紙", 3),
    BibleBook(62, "1 John", "約翰一書", "ヨハネの第一の手紙", 5),
    BibleBook(63, "2 John", "約翰二書", "ヨハネの第二の手紙", 1),
    BibleBook(64, "3 John", "約翰三書", "ヨハネの第三の手紙", 1),
    BibleBook(65, "Jude", "猶大書", "ユダの手紙", 1),
    BibleBook(66, "Revelation", "啟示錄", "ヨハネの黙示録", 22),
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


def strip_templates(text: str) -> str:
    text = re.sub(r"\{\{LORD\}\}", "LORD", text)
    text = re.sub(r"\{\{[Uu]dots\|([^{}|]+)\}\}", r"\1", text)
    text = re.sub(r"\{\{\*\|[^{}]*\}\}", "", text)
    while True:
        replaced = WIKI_TEMPLATE_RE.sub(lambda m: m.group(2).split("|")[-1], text)
        if replaced == text:
            break
        text = replaced
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[[^]|]+\|([^]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    return compact(clean_wiki_markup(text))


def manifest_pages(source_dir: Path) -> list[dict[str, Any]]:
    manifest = load_json(source_dir / "manifest.json")
    return [page for page in manifest.get("pages", []) if page.get("status") == "ok"]


def page_maps(source_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for page in manifest_pages(source_dir):
        for key in ("title", "actual_title"):
            title = page.get(key)
            if title:
                out[str(title)] = page
    return out


def read_page(source_dir: Path, page: dict[str, Any], kind: str) -> str:
    rel = page.get(kind) or page.get(f"{kind}_path")
    if not rel:
        return ""
    path = source_dir / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_zh_book(raw: str) -> dict[tuple[int, int], str]:
    matches = list(ZH_VERSE_RE.finditer(raw))
    verses: dict[tuple[int, int], str] = {}
    for index, match in enumerate(matches):
        chapter = int(match.group(1))
        verse = int(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        text = raw[start:end]
        text = re.split(r"\{\{gototop\}\}|==\s*<span|==\s*\{\{Chapter", text)[0]
        text = strip_templates(text)
        if text:
            verses[(chapter, verse)] = text
    return verses


def parse_en_raw(raw: str) -> dict[tuple[int, int], str]:
    matches = list(EN_RAW_VERSE_RE.finditer(raw))
    verses: dict[tuple[int, int], str] = {}
    for index, match in enumerate(matches):
        chapter = int(match.group(1))
        verse = int(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        text = raw[start:end]
        text = re.split(r"^==\s*Chapter|\{\{smallrefs|\{\{page break", text, flags=re.M)[0]
        text = strip_templates(text)
        if text:
            verses[(chapter, verse)] = text
    return verses


def clean_kjv_html_text(text: str) -> str:
    text = text.replace("¶", "")
    text = re.sub(r"^[A-Z]\s+[A-Z]{1,4}\s*P?\.\s*[IVXLCDM]+\.\s*", "", text)
    text = re.sub(
        r"^([A-Z])\s+([A-Z]{1,10})(\b)",
        lambda match: (match.group(1) + match.group(2)).capitalize() + match.group(3),
        text,
        count=1,
    )
    text = re.sub(r"^([A-Z])\s+([a-z])\b", r"\1\2", text)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    return compact(text)


def parse_en_html_verses(html: str, *, default_chapter: int | None = None) -> dict[tuple[int, int], str]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one(".prp-pages-output") or soup.select_one(".mw-parser-output") or soup
    verses: dict[tuple[int, int], str] = {}
    for paragraph in container.find_all("p"):
        marker = paragraph.find("span", class_=re.compile(r"wst-verse"), id=re.compile(r"^\d+(?::\d+)?$"))
        if marker is None:
            marker = paragraph.find("span", id=re.compile(r"^\d+:\d+$"))
        if marker is None:
            marker = paragraph.find("span", id=re.compile(r"^\d+$"), class_=re.compile(r"(anchor|wst-anchor)"))
        if marker is None:
            marker = paragraph.find("span", id=re.compile(r"^\d+$"))
        if marker is None:
            continue
        marker_id = str(marker.get("id") or "")
        if ":" in marker_id:
            chapter_s, verse_s = marker_id.split(":", 1)
            chapter = int(chapter_s)
            verse = int(verse_s)
        elif default_chapter is not None:
            chapter = default_chapter
            verse = int(marker_id)
        else:
            continue
        paragraph_copy = BeautifulSoup(str(paragraph), "html.parser")
        for selector in [
            "sup.reference",
            ".reference",
            ".wst-verse",
            ".wst-sidenote",
            ".wst-marginnote",
            ".pagenum",
            ".ws-noexport",
            "style",
            "link",
            ".anchor",
            ".wst-anchor",
        ]:
            for tag in paragraph_copy.select(selector):
                tag.decompose()
        text = paragraph_copy.get_text(" ", strip=True)
        text = clean_kjv_html_text(text)
        if text:
            verses[(chapter, verse)] = text
    return verses


def parse_en_book(book: BibleBook, en_dir: Path, en_pages: dict[str, dict[str, Any]]) -> dict[tuple[int, int], str]:
    verses: dict[tuple[int, int], str] = {}
    book_title = f"Bible (King James)/{book.en_page}"
    page = en_pages.get(book_title)
    if page:
        verses.update(parse_en_raw(read_page(en_dir, page, "raw")))
        verses.update(parse_en_html_verses(read_page(en_dir, page, "html")))
    for chapter in range(1, book.chapters + 1):
        for title in (
            f"Bible (King James)/{book.en_page}/Chapter {chapter}",
            f"Bible (King James)/{book.en}/Chapter {chapter}",
        ):
            chapter_page = en_pages.get(title)
            if not chapter_page:
                continue
            verses.update(parse_en_html_verses(read_page(en_dir, chapter_page, "html"), default_chapter=chapter))
            break
    return verses


def parse_zh_sources(zh_dir: Path, zh_pages: dict[str, dict[str, Any]]) -> dict[str, dict[tuple[int, int], str]]:
    out: dict[str, dict[tuple[int, int], str]] = {}
    for book in BOOKS:
        title = f"聖經 (和合本)/{book.zh}"
        combined: dict[tuple[int, int], str] = {}
        for page in zh_pages.values():
            page_title = str(page.get("actual_title") or page.get("title") or "")
            if page_title == title or page_title.startswith(f"{title}/"):
                combined.update(parse_zh_book(read_page(zh_dir, page, "raw")))
        out[book.zh] = combined
    return out


def group_units(units: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [units[index : index + size] for index in range(0, len(units), size)]


def prepare(*, max_verses_per_chunk: int, force: bool) -> None:
    book_id = "bible"
    en_dir = ROOT / "sources/bible/en/wikisource-kjv"
    zh_dir = ROOT / "sources/bible/zh/wikisource-union"
    ja_ot_dir = ROOT / "sources/bible/ja/wikisource-kougo-ot"
    ja_nt_dir = ROOT / "sources/bible/ja/wikisource-kougo-nt"
    for required in (en_dir / "manifest.json", zh_dir / "manifest.json"):
        if not required.exists():
            raise FileNotFoundError(required)

    out_root = ROOT / "books" / book_id
    chunk_dir = out_root / "work" / "trilingual" / "chunks"
    chunks_jsonl = chunk_dir / "chunks.jsonl"
    manifest_path = chunk_dir / "manifest.json"
    plan_path = out_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print("bible: already prepared")
        return

    en_pages = page_maps(en_dir)
    zh_pages = page_maps(zh_dir)
    zh_sources = parse_zh_sources(zh_dir, zh_pages)

    chunks: list[dict[str, Any]] = []
    markdown_lines = ["# The Holy Bible", ""]
    missing: list[dict[str, Any]] = []
    chunk_counter = 0
    source_sha_paths = [
        en_dir / "manifest.json",
        zh_dir / "manifest.json",
    ]
    if (ja_ot_dir / "manifest.json").exists():
        source_sha_paths.append(ja_ot_dir / "manifest.json")
    if (ja_nt_dir / "manifest.json").exists():
        source_sha_paths.append(ja_nt_dir / "manifest.json")

    for book in BOOKS:
        en_verses = parse_en_book(book, en_dir, en_pages)
        zh_verses = zh_sources.get(book.zh, {})
        markdown_lines.extend([f"## {book.en} / {book.zh}", ""])
        for chapter in range(1, book.chapters + 1):
            verse_numbers = sorted({v for c, v in en_verses if c == chapter} | {v for c, v in zh_verses if c == chapter})
            units: list[dict[str, str]] = []
            for verse in verse_numbers:
                en = en_verses.get((chapter, verse), "")
                zh = zh_verses.get((chapter, verse), "")
                if not en or not zh:
                    missing.append(
                        {
                            "book": book.en,
                            "chapter": chapter,
                            "verse": verse,
                            "missing_en": not bool(en),
                            "missing_zh": not bool(zh),
                        }
                    )
                    continue
                ref = f"{book.en} {chapter}:{verse}"
                units.append({"unit_id": f"{book.order:02d}-{chapter:03d}-{verse:03d}", "en": en, "zh": zh, "ref": ref})
                markdown_lines.append(f"{ref} {en}")
                markdown_lines.append(f"{book.zh} {chapter}:{verse} {zh}")
                markdown_lines.append("")
            for group_index, group in enumerate(group_units(units, max_verses_per_chunk), start=1):
                chunk_counter += 1
                chunk_id = f"bible-chunk-{chunk_counter:05d}"
                paragraph_id = f"bible-p{chunk_counter:05d}"
                chapter_id = f"bible-{book.order:02d}-{chapter:03d}"
                en_text = " ".join(unit["en"] for unit in group)
                zh_text = "".join(unit["zh"] for unit in group)
                first_ref = group[0]["ref"]
                last_ref = group[-1]["ref"]
                chunk = {
                    "schema_version": 1,
                    "task_type": "trilingual_standard",
                    "book_id": book_id,
                    "chunk_id": chunk_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chunk_counter,
                    "chapter_title_en": f"{book.en} {chapter}",
                    "chapter_title_zh": f"{book.zh} 第{chapter}章",
                    "chapter_title_ja": f"{book.ja} {chapter}章",
                    "chapter_part_en": first_ref if first_ref == last_ref else f"{first_ref} - {last_ref}",
                    "source_spine_lang": "en",
                    "paragraphs": [
                        {
                            "id": paragraph_id,
                            "en": en_text,
                            "zh": zh_text,
                            "units": [
                                {"unit_id": unit["unit_id"], "en": unit["en"], "zh": unit["zh"]}
                                for unit in group
                            ],
                        }
                    ],
                    "reference": {
                        "en": {
                            "available": True,
                            "chapter": f"{book.en} {chapter}",
                            "verse_range": first_ref if first_ref == last_ref else f"{first_ref} - {last_ref}",
                            "source": "Wikisource King James Version",
                        },
                        "zh_primary": {
                            "available": True,
                            "chapter": f"{book.zh} 第{chapter}章",
                            "verse_range": first_ref if first_ref == last_ref else f"{first_ref} - {last_ref}",
                            "source": "Wikisource Chinese Union Version",
                        },
                        "ja": {
                            "available": False,
                            "chapter": f"{book.ja} {chapter}章",
                            "note": "Japanese Wikisource Kougo pages are currently metadata/redaction pages; generate natural modern Japanese from exact English and Chinese verse sources.",
                        },
                    },
                }
                chunks.append(chunk)

    markdown_path = out_root / "markdown" / "bible-wikisource.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(markdown_lines).strip() + "\n", encoding="utf-8")
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")

    prepared_at = datetime.now(timezone.utc).isoformat()
    source_paths = {
        "english_kjv_wikisource": "sources/bible/en/wikisource-kjv",
        "chinese_union_wikisource": "sources/bible/zh/wikisource-union",
        "japanese_kougo_old_testament_attempted": "sources/bible/ja/wikisource-kougo-ot",
        "japanese_kougo_new_testament_attempted": "sources/bible/ja/wikisource-kougo-nt",
        "markdown": str(markdown_path.relative_to(ROOT)),
    }
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "task_mode": "trilingual_bible_wikisource",
        "source_spine_lang": "en",
        "book_title_en": "The Holy Bible",
        "book_title_zh": "聖經",
        "book_title_ja": "聖書",
        "author": "",
        "author_reading_ja": "",
        "chunk_count": len(chunks),
        "chapter_count": sum(book.chapters for book in BOOKS),
        "verse_missing_count": len(missing),
        "missing_verses": missing[:500],
        "chunks": [
            {"chunk_id": chunk["chunk_id"], "paragraph_ids": [p["id"] for p in chunk["paragraphs"]]}
            for chunk in chunks
        ],
        "source_paths": source_paths,
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in source_sha_paths + [markdown_path]
            if path.exists()
        },
        "source_note": (
            "English KJV from Wikisource is the alignment spine. Chinese Union Version from Wikisource "
            "is preserved as exact verse text. Japanese is generated in natural modern Japanese because "
            "Japanese Kougo Wikisource pages currently expose metadata/redaction pages rather than usable verse text."
        ),
        "prepared_at": prepared_at,
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "launchable",
        "launchable": True,
        "task_mode": "trilingual_bible_wikisource",
        "source_language": "en",
        "book_title_en": "The Holy Bible",
        "book_title_zh": "聖經",
        "book_title_ja": "聖書",
        "author": "",
        "author_reading_ja": "",
        "book_description": "The Holy Bible with KJV English, Chinese Union Version, and generated modern Japanese aligned by verse.",
        "source_paths": source_paths,
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": "books/bible/work/trilingual/interlinear/chunks",
        "assembled_json": "books/bible/work/trilingual/preview/bible.partial.json",
        "build_root": "build/bible",
        "prepared_at": prepared_at,
    }
    write_json(plan_path, plan)
    print(f"bible: books={len(BOOKS)} chapters={manifest['chapter_count']} chunks={len(chunks)} missing_verses={len(missing)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-verses-per-chunk", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    prepare(max_verses_per_chunk=args.max_verses_per_chunk, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
