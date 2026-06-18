#!/usr/bin/env python3
"""Prepare world literature EN/JP/ZH trilingual chunk tasks.

This is a preparation-only script. It converts available English and Chinese
sources to reviewed-start Markdown and chunk manifests so the standard
trilingual tmux queue can be started later.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import prepare_mars_fiction_trilingual as base
from pdf_text_or_ocr import content_chars, extract_pdf_text_checked


ROOT = Path(__file__).resolve().parents[2]

EN_HEADING_RE = re.compile(
    r"^(?:"
    r"PREFACE\.?|INTRODUCTION|EPILOGUE|PROLOGUE|"
    r"(?:VOLUME|Volume|BOOK|Book|PART|Part|CHAPTER|Chapter)\s+"
    r"(?:[IVXLCDM]+|\d+|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)"
    r"(?:[.:—\- ]+.*)?|"
    r"\d{1,3}\.?\s+[^.?!]{2,90}"
    r")$"
)
ZH_HEADING_RE = re.compile(
    r"^(?:"
    r"第\s*[一二三四五六七八九十百千〇零0-9]+\s*[部卷章节]\s*.*|"
    r"[一二三四五六七八九十百千〇零0-9]{1,4}[、.．]\s*.{1,40}"
    r")$"
)
JP_HEADING_RE = re.compile(
    r"^(?:"
    r"第\s*[一二三四五六七八九十百千〇零0-9]+\s*[部編文章巻章]\s*.*|"
    r"[一二三四五六七八九十百千〇零0-9]{1,4}[、.．　 ]\s*.{1,60}"
    r")$"
)
PAGE_NUMBER_RE = re.compile(r"^[\-—–]?\s*\d{1,5}\s*[\-—–]?$")
LATIN_ONLY_NOISE_RE = re.compile(r"^[A-Za-z0-9 .,:;!?'\-_/()]{1,18}$")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class PreparedBookConfig(base.BookConfig):
    pass


@dataclasses.dataclass(frozen=True)
class JapaneseReferenceConfig:
    source: Path
    start_marker: str | None = None
    end_marker: str | None = None
    coverage_ratio: float = 1.0
    quality: str = "published_japanese_translation_reference"
    note: str = "Japanese source converted to broad reference windows."


FORCE_OCR_MARKDOWN: set[tuple[str, str]] = {
    ("jane-eyre", "zh"),
}


BOOKS: dict[str, base.BookConfig] = {
    "one-hundred-years-of-solitude": base.BookConfig(
        book_id="one-hundred-years-of-solitude",
        title_en="One Hundred Years of Solitude",
        title_zh="百年孤独",
        title_ja="百年の孤独",
        title_zh_reading="bǎi nián gū dú",
        title_ja_reading="ひゃくねん の こどく",
        author="Gabriel García Márquez",
        author_reading_zh="jiā bù liè ěr jiā xī yà mǎ ěr kè sī",
        author_reading_ja="ガブリエル ガルシア マルケス",
        en_source=Path("sources/one-hundred-years-of-solitude/One Hundred Years of Solitude.pdf"),
        zh_source=Path("sources/one-hundred-years-of-solitude/百年孤独（范晔 译本）.epub"),
        en_start_marker="Chapter 1",
        zh_start_marker="多年以后",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja",
        book_description=(
            "Gabriel García Márquez, One Hundred Years of Solitude. English PDF is the "
            "alignment spine; Fan Ye's Chinese EPUB is a published translation reference; "
            "Japanese is generated in natural modern Japanese."
        ),
    ),
    "wuthering-heights": base.BookConfig(
        book_id="wuthering-heights",
        title_en="Wuthering Heights",
        title_zh="呼啸山庄",
        title_ja="嵐が丘",
        title_zh_reading="hū xiào shān zhuāng",
        title_ja_reading="あらし が おか",
        author="Emily Brontë",
        author_reading_zh="ài mǐ lì bó lǎng tè",
        author_reading_ja="エミリー ブロンテ",
        en_source=Path("sources/wuthering-heights/Wuthering Heights.epub"),
        zh_source=Path("sources/wuthering-heights/呼啸山庄.pdf"),
        en_start_marker="Chapter I",
        zh_start_marker="一八〇一年",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja",
        book_description=(
            "Emily Brontë, Wuthering Heights. English EPUB is the alignment spine; "
            "Chinese PDF is a broad published translation reference; Japanese is generated "
            "in natural modern Japanese."
        ),
    ),
    "jane-eyre": base.BookConfig(
        book_id="jane-eyre",
        title_en="Jane Eyre",
        title_zh="简·爱",
        title_ja="ジェイン・エア",
        title_zh_reading="jiǎn ài",
        title_ja_reading="ジェイン エア",
        author="Charlotte Brontë",
        author_reading_zh="xià luò dì bó lǎng tè",
        author_reading_ja="シャーロット ブロンテ",
        en_source=Path("sources/jane-eyre/Jane Eyre.pdf"),
        zh_source=Path("sources/jane-eyre/夏洛蒂·勃朗特-简·爱.pdf"),
        en_start_marker="Chapter I",
        zh_start_marker="那天不可能再去散步了",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_ja_sources",
        book_description=(
            "Charlotte Brontë, Jane Eyre. English PDF is the alignment spine; "
            "Chinese PDF is an OCR-polished published translation reference; "
            "Japanese EPUB is a partial published translation reference for the first volume."
        ),
    ),
    "the-count-of-monte-cristo": base.BookConfig(
        book_id="the-count-of-monte-cristo",
        title_en="The Count of Monte Cristo",
        title_zh="基督山伯爵",
        title_ja="モンテ・クリスト伯",
        title_zh_reading="jī dū shān bó jué",
        title_ja_reading="モンテ クリスト はく",
        author="Alexandre Dumas",
        author_reading_zh="yà lì shān dà zhòng mǎ",
        author_reading_ja="アレクサンドル デュマ",
        en_source=Path("sources/the-count-of-monte-cristo/The Count of Monte Cristo.epub"),
        zh_source=Path(
            "sources/the-count-of-monte-cristo/"
            "读客经典文库：基督山伯爵（余华不吃不喝不睡，疯了般读完《基督山伯爵》！人类全部的智慧尽在其中！全三册一字未删完整版！）.pdf"
        ),
        en_start_marker="Chapter 1 Marseilles",
        zh_start_marker="第一章 返航马赛",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja",
        book_description=(
            "Alexandre Dumas, The Count of Monte Cristo. English EPUB is the alignment "
            "spine; Chinese PDF is a broad published translation reference; Japanese is "
            "generated in natural modern Japanese."
        ),
    ),
    "notre-dame-de-paris": base.BookConfig(
        book_id="notre-dame-de-paris",
        title_en="Notre-Dame de Paris",
        title_zh="巴黎圣母院",
        title_ja="ノートルダム・ド・パリ",
        title_zh_reading="bā lí shèng mǔ yuàn",
        title_ja_reading="ノートルダム ド パリ",
        author="Victor Hugo",
        author_reading_zh="wéi kè duō yǔ guǒ",
        author_reading_ja="ヴィクトル ユーゴー",
        en_source=Path("sources/notre-dame-de-paris/Notre-dame de Paris, by Victor Hugo.pdf"),
        zh_source=Path("sources/notre-dame-de-paris/巴黎圣母院.pdf"),
        en_start_marker="CHAPTER I. THE GRAND HALL.",
        zh_start_marker="话说距今三百四十八年",
        zh_end_marker="责任编辑",
        source_spine_lang="en",
        task_mode="trilingual_en_source_generated_zh_ja_with_scanned_zh_reference",
        book_description=(
            "Victor Hugo, Notre-Dame de Paris. English PDF is the alignment spine. The "
            "Chinese PDF appears scanned or metadata-only in pdftotext, so the first run "
            "should generate Chinese from English unless an OCR reference is prepared."
        ),
    ),
    "les-miserables": base.BookConfig(
        book_id="les-miserables",
        title_en="Les Misérables",
        title_zh="悲惨世界",
        title_ja="レ・ミゼラブル",
        title_zh_reading="bēi cǎn shì jiè",
        title_ja_reading="レ ミゼラブル",
        author="Victor Hugo",
        author_reading_zh="wéi kè duō yǔ guǒ",
        author_reading_ja="ヴィクトル ユーゴー",
        en_source=Path("sources/les-miserables/Les Misérables.pdf"),
        zh_source=Path("sources/les-miserables/悲惨世界（上、下）【文字版】.pdf"),
        en_start_marker="VOLUME I—FANTINE",
        zh_start_marker="一八一五年，沙尔",
        source_spine_lang="en",
        task_mode="trilingual_en_zh_sources_generated_ja",
        book_description=(
            "Victor Hugo, Les Misérables. English Project Gutenberg PDF is the alignment "
            "spine; Chinese text PDF is a broad published translation reference; Japanese "
            "is generated in natural modern Japanese. This is very long and should run late."
        ),
    ),
}

JAPANESE_REFERENCES: dict[str, JapaneseReferenceConfig] = {
    "wuthering-heights": JapaneseReferenceConfig(
        source=Path("sources/wuthering-heights/嵐が丘（上）.epub"),
        start_marker="第一章",
        coverage_ratio=0.45,
        quality="partial_published_japanese_translation_reference",
        note=(
            "Japanese EPUB source is 嵐が丘（上）, so it is a partial published "
            "translation reference. Use it when the window matches the chunk; generate "
            "natural Japanese for unmatched later chunks."
        ),
    ),
    "jane-eyre": JapaneseReferenceConfig(
        source=Path("sources/jane-eyre/ジェイン・エア（上）.epub"),
        start_marker="その日、散歩",
        coverage_ratio=0.5,
        quality="partial_published_japanese_translation_reference",
        note=(
            "Japanese EPUB source is ジェイン・エア（上）, so it is a partial published "
            "translation reference. Use it when the window matches the first half; generate "
            "natural Japanese for unmatched later chunks."
        ),
    ),
    "les-miserables": JapaneseReferenceConfig(
        source=Path("sources/les-miserables/レ・ミゼラブル 全巻セット.epub"),
        start_marker="第一部ファンティーヌ",
        quality="published_japanese_translation_reference",
        note="Japanese EPUB source is レ・ミゼラブル 全巻セット and should be used as the main Japanese reference.",
    ),
}


def preferred_ocr_markdown(path: Path, *, lang: str) -> Path | None:
    """Return polished OCR Markdown for this PDF source when available."""

    if path.suffix.lower() != ".pdf":
        return None
    forced_candidate: Path | None = None
    for book_id, config in BOOKS.items():
        if lang == "en" and config.en_source == path:
            candidate = ROOT / "books" / book_id / "markdown" / "en.ocr-polished.md"
        elif lang == "zh" and config.zh_source == path:
            candidate = ROOT / "books" / book_id / "markdown" / "zh.ocr-polished.md"
        else:
            continue
        if (book_id, lang) in FORCE_OCR_MARKDOWN:
            forced_candidate = candidate
            break
    if forced_candidate is not None and forced_candidate.exists():
        return forced_candidate
    if lang == "en":
        # English PDFs usually have reliable embedded text and chapter markers.
        # Keep OCR as an evidence/deep-check sidecar unless explicitly enabled.
        import os

        if os.environ.get("POCKETPOLYGLOT_PREFER_EN_OCR", "0") != "1":
            return None
    if lang == "zh":
        import os

        if os.environ.get("POCKETPOLYGLOT_PREFER_ZH_OCR", "0") != "1" and embedded_pdf_content_chars(path) >= 2000:
            return None
    for book_id, config in BOOKS.items():
        if lang == "en" and config.en_source == path:
            candidate = ROOT / "books" / book_id / "markdown" / "en.ocr-polished.md"
        elif lang == "zh" and config.zh_source == path:
            candidate = ROOT / "books" / book_id / "markdown" / "zh.ocr-polished.md"
        else:
            continue
        if candidate.exists():
            return candidate
    return None


def embedded_pdf_content_chars(path: Path) -> int:
    try:
        raw = subprocess.check_output(
            ["pdftotext", "-layout", str(ROOT / path), "-"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
    except Exception:
        return 0
    return content_chars(raw)


def lines_from_ocr_markdown(path: Path) -> list[str]:
    lines: list[str] = []
    in_yaml = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if stripped == "---":
            in_yaml = not in_yaml
            continue
        if in_yaml:
            continue
        if not stripped:
            lines.append("")
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("# "):
            continue
        if re.match(r"^##\s+Page\s+\d+\s*$", stripped, re.IGNORECASE):
            lines.append("")
            continue
        if stripped.startswith("## "):
            lines.append(stripped.removeprefix("## ").strip())
            continue
        lines.append(stripped)
    return lines


def clean_world_line(raw_line: str, *, lang: str, from_ocr: bool = False) -> str:
    line = base.clean_line(raw_line)
    line = line.replace(" ,", "，").replace(" .", "。") if lang == "zh" else line
    line = base.compact(line)
    if not line or PAGE_NUMBER_RE.match(line):
        return ""
    if lang == "zh":
        if from_ocr:
            line = clean_zh_ocr_noise(line)
            if not line:
                return ""
            if ("本章节" in line or "本节重点" in line or "思维链接" in line) and "话说距今三百四十八年" not in line:
                return ""
            if re.match(r"^\d{1,2}[，,、.．]\s*.+(?:什么|为什么|说明|体现|如何|怎样|赏析|思考)", line):
                return ""
        if "图书在版编目" in line or "ISBN" in line or "版权所有" in line:
            return ""
        cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", line))
        if cjk_count == 0 and LATIN_ONLY_NOISE_RE.match(line):
            return ""
    else:
        if line in {
            "The Hunchback of Notre Dame by Victor Hugo",
            "Enjoy this wonderful eBook from All You Can Books audiobooks and ebooks service.",
        }:
            return ""
        if line.startswith("Visit us at AllYouCanBooks.com"):
            return ""
        if line.startswith("*** START OF") or line.startswith("*** END OF"):
            return ""
        if line.startswith("Produced by ") or line.startswith("This eBook is for the use"):
            return ""
    return line


def clean_zh_ocr_noise(line: str) -> str:
    """Remove recurring page/header fragments from Chinese OCR reference text."""

    body_marker = "话说距今三百四十八年"
    if body_marker in line:
        line = line[line.find(body_marker) :]
    line = re.sub(r"巴黎圣母院\s*\|\s*\d{1,4}", "", line)
    line = re.sub(r"巴[笋获歼]\s*圣母院\s*\|\s*\d{1,4}", "", line)
    line = re.sub(r"NOTRE[-\s]*DAME(?:\s*DE)?\s*PARIS", "", line, flags=re.IGNORECASE)
    line = re.sub(r"[A-Za-z]{2,}", "", line)
    line = re.sub(r"\s*\|\s*", "", line)
    line = re.split(
        r"(?:一部小说的开头|本[章节小童][^，。！？]{0,40}|"
        r"\d{1,2}[.，,、]\s*[^，。！？]{0,60}(?:什么|为什么|如何|怎样|目的|体现|说明))",
        line,
        maxsplit=1,
    )[0]
    if re.match(r"^(?:本[章节小童]|这一部分|精彩赏析|思维链接|推荐理由|卡西莫多披上|这里又是)", line):
        return ""
    return base.compact(line)


def source_lines(path: Path, *, lang: str, allow_scanned: bool = False) -> list[str]:
    ocr_markdown = preferred_ocr_markdown(path, lang=lang)
    if ocr_markdown:
        return [clean_world_line(line, lang=lang, from_ocr=True) for line in lines_from_ocr_markdown(ocr_markdown)]
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return base.epub_lines(path)
    if suffix == ".pdf":
        try:
            raw = extract_pdf_text_checked(ROOT / path, layout=True, min_content_chars=1000)
        except RuntimeError:
            if allow_scanned:
                return []
            raise
        return [clean_world_line(line, lang=lang) for line in raw.replace("\f", "\n\n").splitlines()]
    raise RuntimeError(f"unsupported source format for {path}")


def marker_start(lines: list[str], marker: str | None, *, lang: str) -> int:
    if not marker:
        return 0
    hits = [index for index, line in enumerate(lines) if line and base.marker_matches(line, marker)]
    if not hits:
        return 0
    for index in hits:
        window = lines[index : index + 20]
        if lang == "zh" and any(looks_like_zh_prose(item) for item in window):
            return index
        if lang == "en" and any(looks_like_en_prose(item) for item in window):
            return index
        if lang == "ja" and any(looks_like_ja_prose(item) for item in window):
            return index
    return hits[-1]


def looks_like_en_heading(line: str) -> bool:
    if not line or len(line) > 120:
        return False
    if EN_HEADING_RE.match(line):
        return True
    return False


def looks_like_zh_heading(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    return bool(ZH_HEADING_RE.match(line))


def looks_like_ja_heading(line: str) -> bool:
    if not line or len(line) > 100:
        return False
    if JP_HEADING_RE.match(line):
        return True
    return line in {"序", "序文", "あとがき", "解説", "目次"}


def looks_like_en_prose(line: str) -> bool:
    if not line or looks_like_en_heading(line):
        return False
    return len(line) >= 25 and bool(re.search(r"[A-Za-z]{3,}", line))


def looks_like_zh_prose(line: str) -> bool:
    if not line or looks_like_zh_heading(line):
        return False
    return len(CJK_RE.findall(line)) >= 6


def looks_like_ja_prose(line: str) -> bool:
    if not line or looks_like_ja_heading(line):
        return False
    return len(line) >= 8 and (bool(KANA_RE.search(line)) or len(CJK_RE.findall(line)) >= 6)


def normalize_en_paragraph(lines: list[str]) -> str:
    text = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if text.endswith("-"):
            text = text[:-1] + line
        else:
            text = f"{text} {line}".strip()
    return base.compact(text)


def normalize_zh_paragraph(lines: list[str]) -> str:
    text = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not text:
            text = line
        elif re.search(r"[，。！？；：、“‘（《—]$", text) or re.match(r"^[，。！？；：、”’）》]", line):
            text += line
        else:
            text += line
    return base.compact(text)


def parse_en_source(path: Path, *, preferred_start: str) -> list[base.Chapter]:
    lines = source_lines(path, lang="en")
    start = marker_start(lines, preferred_start, lang="en")
    chapters: list[base.Chapter] = []
    current: base.Chapter | None = None
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if current is None or not pending:
            pending = []
            return
        paragraph = normalize_en_paragraph(pending)
        pending = []
        if paragraph and looks_like_en_prose(paragraph):
            current.paragraphs.extend(base.split_english_units(paragraph, max_chars=900))

    for line in lines[start:]:
        if not line:
            flush()
            continue
        if looks_like_en_heading(line):
            flush()
            current = base.Chapter(number=len(chapters) + 1, title=line, part="")
            chapters.append(current)
            continue
        if current is None and looks_like_en_prose(line):
            current = base.Chapter(number=1, title="Text", part="")
            chapters.append(current)
        if current is not None:
            pending.append(line)
            if path.suffix.lower() == ".epub":
                flush()
    flush()
    return [chapter for chapter in chapters if chapter.paragraphs]


def parse_zh_source(path: Path | None, *, start_marker: str | None, end_marker: str | None) -> list[base.Chapter]:
    if path is None:
        return []
    lines = source_lines(path, lang="zh", allow_scanned=True)
    if not lines:
        return []
    start = marker_start(lines, start_marker, lang="zh")
    if start_marker and start < len(lines):
        marker_pos = lines[start].find(start_marker)
        if marker_pos > 0:
            lines[start] = lines[start][marker_pos:]
    end = len(lines)
    if end_marker:
        for index in range(start + 1, len(lines)):
            if lines[index] and base.marker_matches(lines[index], end_marker):
                end = index
                break
    lines = lines[start:end]

    chapters: list[base.Chapter] = []
    current: base.Chapter | None = None
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if current is None or not pending:
            pending = []
            return
        paragraph = normalize_zh_paragraph(pending)
        pending = []
        if paragraph and looks_like_zh_prose(paragraph):
            current.paragraphs.append(paragraph)

    for line in lines:
        if not line:
            flush()
            continue
        if looks_like_zh_heading(line):
            flush()
            current = base.Chapter(number=len(chapters) + 1, title=line, part="")
            chapters.append(current)
            continue
        if current is None and looks_like_zh_prose(line):
            current = base.Chapter(number=1, title="正文", part="")
            chapters.append(current)
        if current is not None:
            pending.append(line)
    flush()
    return [chapter for chapter in chapters if chapter.paragraphs]


def parse_ja_source(ref: JapaneseReferenceConfig | None) -> list[base.Chapter]:
    if ref is None or not (ROOT / ref.source).exists():
        return []
    lines = [base.clean_line(raw) for raw in base.epub_lines(ref.source)]
    lines = [line for line in lines if line]
    start = marker_start(lines, ref.start_marker, lang="ja")
    end = len(lines)
    if ref.end_marker:
        for index in range(start + 1, len(lines)):
            if lines[index] and base.marker_matches(lines[index], ref.end_marker):
                end = index
                break
    lines = lines[start:end]

    chapters: list[base.Chapter] = []
    current: base.Chapter | None = None
    for line in lines:
        if looks_like_ja_heading(line):
            current = base.Chapter(number=len(chapters) + 1, title=line, part="")
            chapters.append(current)
            continue
        if current is None and looks_like_ja_prose(line):
            current = base.Chapter(number=1, title="本文", part="")
            chapters.append(current)
        if current is not None and looks_like_ja_prose(line):
            current.paragraphs.append(line)
    return [chapter for chapter in chapters if chapter.paragraphs]


def inject_japanese_reference(book_id: str, ref: JapaneseReferenceConfig, ja_chapters: list[base.Chapter]) -> None:
    book_root = ROOT / "books" / book_id
    plan_path = book_root / "book-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    chunks_jsonl = ROOT / plan["chunks_jsonl"]
    manifest_path = ROOT / plan["chunks_manifest"]
    chunks = [json.loads(line) for line in chunks_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    ja_text = base.all_text(ja_chapters)
    total_chars = max(
        sum(
            len(str(paragraph.get(chunk.get("source_spine_lang") or plan.get("source_spine_lang") or "en", ""))) + 1
            for chunk in chunks
            for paragraph in chunk.get("paragraphs", [])
        ),
        1,
    )
    cursor = 0
    for chunk in chunks:
        spine_lang = str(chunk.get("source_spine_lang") or plan.get("source_spine_lang") or "en")
        chunk_chars = sum(len(str(paragraph.get(spine_lang, ""))) + 1 for paragraph in chunk.get("paragraphs", []))
        start_ratio = cursor / total_chars
        end_ratio = min(1.0, (cursor + chunk_chars) / total_chars)
        if start_ratio < ref.coverage_ratio:
            ja_start_ratio = min(1.0, start_ratio / max(ref.coverage_ratio, 0.001))
            ja_end_ratio = min(1.0, end_ratio / max(ref.coverage_ratio, 0.001))
            window = base.reference_window(ja_text, ja_start_ratio, ja_end_ratio, max_chars=plan.get("reference_chars", 9000) or 9000)
        else:
            window = ""
        chunk.setdefault("reference", {})["ja"] = {
            "available": bool(window),
            "chapter": "global-ratio-window",
            "text": window,
            "quality": ref.quality,
        }
        cursor += chunk_chars

    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("source_paths", {})["ja"] = str(ref.source)
    manifest.setdefault("source_sha256", {})["ja"] = base.sha256(ref.source)
    manifest["japanese_reference_chapter_count"] = len(ja_chapters)
    manifest["japanese_reference_note"] = ref.note
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    plan.setdefault("source_paths", {})["ja"] = str(ref.source)
    plan.setdefault("source_sha256", {})["ja"] = base.sha256(ref.source)
    plan.setdefault("markdown", {})["ja"] = str(Path("books") / book_id / "markdown/jp.md")
    plan["japanese_reference_chapter_count"] = len(ja_chapters)
    plan["japanese_reference_note"] = ref.note
    plan["task_mode"] = "trilingual_en_zh_ja_sources" if plan.get("task_mode") else "trilingual_en_zh_ja_sources"
    notes = plan.setdefault("preparation_notes", {})
    notes["japanese_reference"] = ref.note
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_selected(book_ids: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    original_en = base.parse_en_source
    original_zh = base.parse_zh_source
    base.parse_en_source = parse_en_source
    base.parse_zh_source = parse_zh_source
    try:
        results = []
        for book_id in book_ids:
            result = base.prepare_book(BOOKS[book_id], args)
            plan_path = ROOT / "books" / book_id / "book-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            zh_markdown = ROOT / "books" / book_id / "markdown" / "zh.md"
            ja_ref = JAPANESE_REFERENCES.get(book_id)
            ja_chapters = parse_ja_source(ja_ref)
            if ja_ref and ja_chapters:
                base.write_text(
                    ROOT / "books" / book_id / "markdown/jp.md",
                    base.markdown_for_chapters(BOOKS[book_id].title_ja, ja_chapters),
                )
                inject_japanese_reference(book_id, ja_ref, ja_chapters)
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["preparation_notes"] = {
                "script": "scripts/interlinear/prepare_world_literature_trilingual.py",
                "english_spine": "English source is the chunk spine.",
                "chinese_reference": (
                    "Chinese source converted to broad reference windows."
                    if zh_markdown.exists()
                    else "Chinese PDF has no usable embedded text; generate Chinese from English or prepare OCR before running."
                ),
                "japanese_reference": (
                    ja_ref.note if ja_ref and ja_chapters else "No published Japanese reference source configured; generate Japanese from source spine."
                ),
                "start_command": f"bash scripts/interlinear/start_trilingual_book_tmux.sh {book_id}",
            }
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results.append(result)
        return results
    finally:
        base.parse_en_source = original_en
        base.parse_zh_source = original_zh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--reference-chars", type=int, default=9000)
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
