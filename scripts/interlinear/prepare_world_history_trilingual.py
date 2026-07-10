#!/usr/bin/env python3
"""Prepare world-history EN/JP/ZH trilingual chunk tasks from PDF sources.

This is a preparation-only workflow. It copies no source files by itself; source
PDFs should already be in ``sources/world-history/<book>/...``. The script builds
text/OCR caches, reviewed-start Markdown, chunk manifests, and book plans for the
standard PocketPolyglot trilingual queue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from english_sentence_splitter import sentence_boundary_ends


ROOT = Path(__file__).resolve().parents[2]
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

SPACE_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]{3,}")
PAGE_HEADING_RE = re.compile(r"^##\s+Page\s+\d+\s*$", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^(?:\d{1,5}|[ivxlcdm]{1,8})$", re.IGNORECASE)
PDF_PAGE_HEADER_RE = re.compile(r"^(?:\d+\s+.+|.+\s+\d+)$")
EN_SENTENCE_END_RE = re.compile(r'[.!?]["”’)\]]*$')


@dataclass(frozen=True)
class HistoryBook:
    book_id: str
    title_en: str
    title_zh: str
    title_ja: str
    title_zh_reading: str
    title_ja_reading: str
    author: str
    author_reading_zh: str
    author_reading_ja: str
    en_source: Path
    zh_source: Path | None
    body_start_marker: str
    body_start_title: str
    chapter_titles: tuple[str, ...]
    chapter_aliases: tuple[tuple[str, str], ...] = ()
    stop_markers: tuple[str, ...] = ()
    zh_body_start_marker: str | None = None
    zh_stop_marker: str | None = None
    task_mode: str = "trilingual_en_zh_sources_generated_ja"
    description: str = ""


SILK_ROADS_CHAPTERS = (
    "Preface",
    "The Creation of the Silk Road",
    "The Road of Faiths",
    "The Road to a Christian East",
    "The Road to Revolution",
    "The Road to Concord",
    "The Road of Furs",
    "The Slave Road",
    "The Road to Heaven",
    "The Road to Hell",
    "The Road of Death and Destruction",
    "The Road of Gold",
    "The Road of Silver",
    "The Road to Northern Europe",
    "The Road to Empire",
    "The Road to Crisis",
    "The Road to War",
    "The Road of Black Gold",
    "The Road to Compromise",
    "The Wheat Road",
    "The Road to Genocide",
    "The Road of Cold Warfare",
    "The American Silk Road",
    "The Road of Superpower Rivalry",
    "The Road to Catastrophe",
    "The Road to Tragedy",
    "Conclusion: The New Silk Road",
)

NEW_ROMAN_EMPIRE_CHAPTERS = (
    "Introduction",
    "New Rome and the New Romans",
    "Government and the Social Order",
    "From Christian Nation to Roman Religion",
    "The First Christian Emperors (324-361)",
    "Competing Religions of Empire (337-363)",
    "Toward an Independent East (364-395)",
    "City and Desert: Cultures Old and New",
    "The Political Class Ascendant (395-441)",
    "Barbarian Terrors and Military Mobilization (441-491)",
    "Political Consolidation and Religious Polarization (491-518)",
    "Chalcedonian Repression and the Eastern Axis (518-531)",
    "The Sleepless Emperor (527-540)",
    "Death Has Entered Our Gates (540-565)",
    "The Cost of Overextension (565-602)",
    "The Great War with Persia (602-630)",
    "Commanders of the Faithful (632-644)",
    "Holding the Line (641-685)",
    "Life and Taxes among the Ruins",
    "An Empire of Outposts (685-717)",
    "The Lion and the Dragon (717-775)",
    "Reform and Consolidation (775-814)",
    "Growing Confidence (815-867)",
    "A New David and Solomon (867-912)",
    "A Game of Crowns (912-950)",
    "The Triumph of Roman Arms (950-1025)",
    "A Brief Hegemony (1025-1048)",
    "The End of Italy and the East (1048-1081)",
    "Komnenian Crisis Management (1081-1118)",
    "Good John and the Sun King (1118-1180)",
    "Disintegration and Betrayal (1180-1204)",
    "A New France: Colonial Occupation",
    "Romans West and Romans East (1204-1261)",
    "Union with Rome and Roman Disunity (1261-1282)",
    "Territorial Retrenchment and Cultural Innovation (1282-1328)",
    "Military Failure and Mystical Refuge (1328-1354)",
    "The Noose Tightens (1354-1402)",
    "The Cusp of a New World (1402-1461)",
)

BOOKS: dict[str, HistoryBook] = {
    "silk-roads": HistoryBook(
        book_id="silk-roads",
        title_en="The Silk Roads: A New History of the World",
        title_zh="丝绸之路：一部全新的世界史",
        title_ja="シルクロード：新しい世界史",
        title_zh_reading="sī chóu zhī lù yī bù quán xīn de shì jiè shǐ",
        title_ja_reading="シルクロード あたらしい せかいし",
        author="Peter Frankopan",
        author_reading_zh="bǐ dé fú lán kē pān",
        author_reading_ja="ピーター フランコパン",
        en_source=Path("sources/world-history/silk-roads/en/The Silk Roads - A New History of the World.pdf"),
        zh_source=Path("sources/world-history/silk-roads/zh/丝绸之路：一部全新的世界史.pdf"),
        body_start_marker="As a child, one of my most prized possessions",
        body_start_title="Preface",
        chapter_titles=SILK_ROADS_CHAPTERS,
        chapter_aliases=(("Conclusion", "Conclusion: The New Silk Road"),),
        stop_markers=("Acknowledgements", "Notes", "Illustrations"),
        zh_body_start_marker="小的时候，我最珍贵的宝贝之一",
        zh_stop_marker="| 致谢",
        description=(
            "Peter Frankopan, The Silk Roads. English PDF is the alignment spine; "
            "Chinese scanned PDF is converted to OCR Markdown and used as a broad "
            "published translation reference; Japanese is generated in natural modern Japanese."
        ),
    ),
    "new-roman-empire": HistoryBook(
        book_id="new-roman-empire",
        title_en="The New Roman Empire: A History of Byzantium",
        title_zh="新罗马帝国：拜占庭史",
        title_ja="新ローマ帝国：ビザンツの歴史",
        title_zh_reading="xīn luó mǎ dì guó bài zhàn tíng shǐ",
        title_ja_reading="しんローマていこく ビザンツ の れきし",
        author="Anthony Kaldellis",
        author_reading_zh="ān dōng ní kǎ ěr dé lì sī",
        author_reading_ja="アンソニー カルデリス",
        en_source=Path("sources/world-history/byzantium-new-roman-empire/en/The New Roman Empire - A History of Byzantium.pdf"),
        zh_source=None,
        body_start_marker="The end was inevitable",
        body_start_title="Introduction",
        chapter_titles=NEW_ROMAN_EMPIRE_CHAPTERS,
        stop_markers=("State Revenues and Payments", "Emperors of the Romans", "Glossary", "Abbreviations", "Notes", "Bibliography", "Index"),
        task_mode="trilingual_en_source_generated_zh_ja",
        description=(
            "Anthony Kaldellis, The New Roman Empire. English PDF is the complete "
            "alignment spine. No published Chinese or Japanese source is configured yet, "
            "so Chinese and Japanese are generated as readable modern translations."
        ),
    ),
}


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, cwd=ROOT)


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def normalize_title(text: str) -> str:
    text = text.replace("\u00ad", "").replace("–", "-").replace("—", "-")
    text = text.replace("“", "").replace("”", "").replace('"', "")
    text = re.sub(r"^\d{1,2}[.)]\s*", "", text)
    return compact(text).casefold()


def sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_pdf_markdown(config: HistoryBook, source: Path, *, lang: str, force_ocr: bool = False) -> Path:
    output = ROOT / "books" / config.book_id / "work/source-extraction" / f"{lang}.raw.md"
    if output.exists():
        return output.relative_to(ROOT)
    cmd = [
        "python",
        "scripts/interlinear/pdf_text_or_ocr.py",
        str(source),
        "--output",
        str(output.relative_to(ROOT)),
        "--title",
        config.title_zh if lang == "zh" else config.title_en,
        "--min-content-chars",
        "5000",
        "--ocr-lang",
        "chi_sim+HanS" if lang == "zh" else "eng",
        "--ocr-psm",
        "4",
        "--ocr-dpi",
        "240" if lang == "zh" else "220",
        "--ocr-workers",
        "8",
        "--ocr-pages",
        "all",
        "--ocr-crop",
        "--ocr-threshold",
    ]
    if force_ocr:
        cmd.append("--force-ocr")
    run(cmd)
    return output.relative_to(ROOT)


def markdown_lines(path: Path) -> list[str]:
    full = ROOT / path
    lines: list[str] = []
    in_yaml = False
    for raw in full.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if stripped == "---":
            in_yaml = not in_yaml
            continue
        if in_yaml:
            continue
        if PAGE_HEADING_RE.match(stripped):
            lines.append("")
            continue
        if stripped.startswith("# "):
            continue
        if stripped.startswith("<!--"):
            continue
        lines.append(stripped)
    return lines


def clean_en_line(line: str, config: HistoryBook) -> str:
    line = compact(line.replace("\f", " ").replace("\u00ad", ""))
    line = re.sub(r"\b(\w+)-\s+(\w+)\b", r"\1\2", line)
    if not line:
        return ""
    if PAGE_NUMBER_RE.fullmatch(line):
        return ""
    if line in {"Cover", "Title Page", "Copyright", "Contents", "The New Roman Empire", "The Silk Roads"}:
        return ""
    if line.startswith(("Copyright ", "All rights reserved", "ISBN ", "DOI:", "Printed by ")):
        return ""
    if "www.vintagebooks.com" in line or "Penguin Random" in line:
        return ""
    allowed_heading_norms = {normalize_title(title) for title in config.chapter_titles}
    allowed_heading_norms.update(normalize_title(alias) for alias, _ in config.chapter_aliases)
    if re.fullmatch(r"[A-Z][A-Z .]{2,}", line) and len(line) <= 28 and normalize_title(line) not in allowed_heading_norms:
        return ""
    # Drop running headers like "2 Introduction" or "Contents vii".
    if PDF_PAGE_HEADER_RE.match(line):
        left = re.sub(r"^\d+\s+", "", line)
        left = re.sub(r"\s+\d+$", "", left)
        if normalize_title(left) in {normalize_title(t) for t in config.chapter_titles} or left == "Contents":
            return ""
    return line


def clean_zh_line(line: str) -> str:
    line = compact(line.replace("\f", " "))
    if not line or PAGE_NUMBER_RE.fullmatch(line):
        return ""
    if line.startswith(("OCR:", "source_pdf:", "generated_at:", "conversion:", "total_pdf_pages:")):
        return ""
    if any(token in line for token in ("图书在版编目", "版权所有", "ISBN", "责任编辑")):
        return ""
    # Remove Latin garbage while preserving meaningful names if mixed with CJK.
    if not CJK_RE.search(line):
        return ""
    line = re.sub(r"[A-Za-z]{3,}", "", line)
    line = compact(line)
    return line


def find_body_start(lines: list[str], marker: str) -> int:
    marker_norm = normalize_title(marker)
    hits = [idx for idx, line in enumerate(lines) if marker_norm in normalize_title(line)]
    if hits:
        return hits[-1]
    return 0


def looks_like_en_prose(line: str) -> bool:
    return len(line) >= 30 and bool(LATIN_RE.search(line))


def is_complete_sentence(text: str) -> bool:
    return bool(EN_SENTENCE_END_RE.search(text.rstrip()))


def split_english_units(text: str, *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    for end in sentence_boundary_ends(text):
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
        if pending and len(pending) + 1 + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = f"{pending} {piece}".strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def parse_en_chapters(config: HistoryBook, markdown_path: Path) -> list[dict[str, Any]]:
    raw_lines = [clean_en_line(line, config) for line in markdown_lines(markdown_path)]
    chapter_lookup = {normalize_title(title): title for title in config.chapter_titles}
    for alias, title in config.chapter_aliases:
        chapter_lookup[normalize_title(alias)] = title
    raw_lines = combine_split_heading_lines(raw_lines, chapter_lookup)
    raw_lines = raw_lines[find_body_start(raw_lines, config.body_start_marker) :]
    stop_norms = tuple(normalize_title(marker) for marker in config.stop_markers)
    chapters: list[dict[str, Any]] = []
    current = {"number": 1, "title": config.body_start_title, "paragraphs": []}
    paragraph_lines: list[str] = []

    def flush() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = compact(" ".join(paragraph_lines))
        paragraph_lines = []
        if looks_like_en_prose(text):
            current["paragraphs"].extend(split_english_units(text, max_chars=900))

    for line in raw_lines:
        if not line:
            flush()
            continue
        norm = normalize_title(line)
        if any(is_stop_heading(norm, marker) for marker in stop_norms):
            flush()
            break
        if norm in chapter_lookup:
            flush()
            if current["paragraphs"]:
                chapters.append(current)
            current = {"number": len(chapters) + 1, "title": chapter_lookup[norm], "paragraphs": []}
            continue
        if looks_like_en_prose(line) or (paragraph_lines and bool(LATIN_RE.search(line))):
            paragraph_lines.append(line)
            if is_complete_sentence(line) and len(" ".join(paragraph_lines)) > 450:
                flush()
    flush()
    if current["paragraphs"]:
        chapters.append(current)
    return chapters


def is_stop_heading(norm: str, marker: str) -> bool:
    return norm == marker or norm.startswith(f"{marker} ") or norm.startswith(f"{marker}:")


def combine_split_heading_lines(lines: list[str], chapter_lookup: dict[str, str]) -> list[str]:
    """Merge PDF headings that pdftotext split over two or three lines."""

    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            out.append(line)
            index += 1
            continue
        merged = line
        consumed = 1
        for span in (2, 3):
            if index + span > len(lines):
                continue
            candidate = " ".join(item for item in lines[index : index + span] if item)
            if normalize_title(candidate) in chapter_lookup:
                merged = candidate
                consumed = span
                break
        out.append(merged)
        index += consumed
    return out


def parse_zh_reference(config: HistoryBook, markdown_path: Path | None) -> list[str]:
    if markdown_path is None:
        return []
    raw_lines = markdown_lines(markdown_path)
    if config.zh_body_start_marker:
        hits = [idx for idx, raw in enumerate(raw_lines) if config.zh_body_start_marker in raw]
        if hits:
            raw_lines = raw_lines[hits[0] :]
    if config.zh_stop_marker:
        hits = [idx for idx, raw in enumerate(raw_lines) if config.zh_stop_marker in raw]
        if hits:
            raw_lines = raw_lines[: hits[-1]]
    paragraphs: list[str] = []
    pending = ""
    for raw in raw_lines:
        line = clean_zh_line(raw)
        if not line:
            if pending:
                paragraphs.append(pending)
                pending = ""
            continue
        if not pending:
            pending = line
        elif re.search(r"[，。！？；：、“‘（《]$", pending) or re.match(r"^[，。！？；：、”’）》]", line):
            pending += line
        else:
            pending += line
        if len(pending) > 500 and re.search(r"[。！？]$", pending):
            paragraphs.append(pending)
            pending = ""
    if pending:
        paragraphs.append(pending)
    return [p for p in paragraphs if len(CJK_RE.findall(p)) >= 12]


def markdown_for_en(config: HistoryBook, chapters: list[dict[str, Any]]) -> str:
    out = [f"# {config.title_en}", ""]
    for chapter in chapters:
        out.extend([f"## {chapter['title']}", ""])
        out.extend(chapter["paragraphs"])
        out.append("")
    return "\n".join(out).strip() + "\n"


def markdown_for_zh(config: HistoryBook, paragraphs: list[str]) -> str:
    out = [f"# {config.title_zh}", "", "## OCR reference", ""]
    out.extend(paragraphs)
    return "\n".join(out).strip() + "\n"


def reference_window(text: str, start_ratio: float, end_ratio: float, *, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    start = max(0, int(len(text) * start_ratio) - max_chars // 3)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        extra = max_chars - (end - start)
        start = max(0, start - extra // 2)
        end = min(len(text), end + extra // 2)
    return text[start:end]


def make_chunks(
    config: HistoryBook,
    chapters: list[dict[str, Any]],
    zh_paragraphs: list[str],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    total_chars = max(sum(len(p) + 1 for c in chapters for p in c["paragraphs"]), 1)
    zh_text = "\n".join(zh_paragraphs)
    chunks: list[dict[str, Any]] = []
    global_cursor = 0
    paragraph_count = 0

    for chapter in chapters:
        pending: list[dict[str, str]] = []
        pending_start = global_cursor
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_start, pending_chars
            if not pending:
                return
            index = len(chunks) + 1
            start_ratio = pending_start / total_chars
            end_ratio = min(1.0, (pending_start + pending_chars) / total_chars)
            en_ref = "\n".join(item["en"] for item in pending)
            zh_ref = reference_window(zh_text, start_ratio, end_ratio, max_chars=reference_chars)
            chunk_id = f"{config.book_id}-c{index:04d}"
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": config.book_id,
                    "source_spine_lang": "en",
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "chapter_id": f"chapter-{chapter['number']:03d}",
                    "chapter_number": chapter["number"],
                    "chapter_title_en": chapter["title"],
                    "chapter_title_zh": "",
                    "chapter_part_en": "",
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": {
                        "english": {"available": True, "chapter": chapter["title"], "text": en_ref},
                        "zh_primary": {
                            "available": bool(zh_ref),
                            "chapter": "global-ratio-window",
                            "text": zh_ref,
                            "quality": "ocr_published_translation_reference" if zh_ref else "generate_from_english_spine",
                        },
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": {"available": False, "chapter": "", "text": ""},
                    },
                }
            )
            pending = []
            pending_chars = 0

        for paragraph in chapter["paragraphs"]:
            paragraph_count += 1
            paragraph_id = f"{config.book_id}-s{chapter['number']:03d}-p{paragraph_count:05d}"
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
                pending_start = global_cursor
            if not pending:
                pending_start = global_cursor
            pending.append({"id": paragraph_id, "en": paragraph})
            pending_chars += len(paragraph) + 1
            global_cursor += len(paragraph) + 1
        flush()

    source_paths = {"en": str(config.en_source)}
    source_sha256 = {"en": sha256(config.en_source)}
    if config.zh_source:
        source_paths["zh"] = str(config.zh_source)
        source_sha256["zh"] = sha256(config.zh_source)
    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": config.book_id,
        "book_title_en": config.title_en,
        "book_title_zh": config.title_zh,
        "book_title_ja": config.title_ja,
        "book_title_zh_reading": config.title_zh_reading,
        "book_title_ja_reading": config.title_ja_reading,
        "author": config.author,
        "author_reading_zh": config.author_reading_zh,
        "author_reading_ja": config.author_reading_ja,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": "en",
        "source_paths": source_paths,
        "source_sha256": source_sha256,
        "source_note": config.description,
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


def prepare_book(config: HistoryBook, args: argparse.Namespace) -> dict[str, Any]:
    en_cache = ensure_pdf_markdown(config, config.en_source, lang="en", force_ocr=False)
    zh_cache = ensure_pdf_markdown(config, config.zh_source, lang="zh", force_ocr=False) if config.zh_source else None

    chapters = parse_en_chapters(config, en_cache)
    if not chapters:
        raise RuntimeError(f"no English body chapters parsed for {config.book_id}")
    zh_paragraphs = parse_zh_reference(config, zh_cache)

    book_root = ROOT / "books" / config.book_id
    write_text(book_root / "markdown/en.md", markdown_for_en(config, chapters))
    if zh_paragraphs:
        write_text(book_root / "markdown/zh.md", markdown_for_zh(config, zh_paragraphs))

    manifest, chunks = make_chunks(
        config,
        chapters,
        zh_paragraphs,
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
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    markdown = {"en": str(Path("books") / config.book_id / "markdown/en.md")}
    if zh_paragraphs:
        markdown["zh"] = str(Path("books") / config.book_id / "markdown/zh.md")
    plan = {
        "schema_version": 1,
        "book_id": config.book_id,
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": config.task_mode,
        "source_spine_lang": "en",
        "source_paths": manifest["source_paths"],
        "source_sha256": manifest["source_sha256"],
        "source_extraction": {
            "en_cache": str(en_cache),
            "zh_cache": str(zh_cache) if zh_cache else "",
            "note": "PDF cache uses embedded text when sufficient and OCR when not.",
        },
        "markdown": markdown,
        "book_title_en": config.title_en,
        "book_title_zh": config.title_zh,
        "book_title_ja": config.title_ja,
        "book_title_zh_reading": config.title_zh_reading,
        "book_title_ja_reading": config.title_ja_reading,
        "author": config.author,
        "author_reading_zh": config.author_reading_zh,
        "author_reading_ja": config.author_reading_ja,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "book_description": config.description,
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": "global_ratio_window",
        "chunks_jsonl": str(chunks_dir.relative_to(ROOT) / "chunks.jsonl"),
        "chunks_manifest": str(chunks_dir.relative_to(ROOT) / "manifest.json"),
        "raw_chunk_dir": str(raw_chunk_dir.relative_to(ROOT)),
        "preview_json": str((preview_dir / f"{config.book_id}.partial.json").relative_to(ROOT)),
        "assembled_json": str((preview_dir / f"{config.book_id}.partial.json").relative_to(ROOT)),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "english_chapter_count": len(chapters),
        "chinese_reference_paragraph_count": len(zh_paragraphs),
        "preparation_notes": {
            "script": "scripts/interlinear/prepare_world_history_trilingual.py",
            "english_spine": "English PDF text is the chunk spine.",
            "chinese_reference": (
                "Chinese PDF was converted through text/OCR cache and is used as a broad ratio-window reference."
                if zh_paragraphs
                else "No Chinese source configured; generate Chinese from English."
            ),
            "japanese_reference": "No published Japanese source configured; generate natural modern Japanese from English.",
        },
    }
    write_json(book_root / "book-plan.json", plan)
    return {
        "book_id": config.book_id,
        "chunks": len(chunks),
        "english_chapters": len(chapters),
        "chinese_reference_paragraphs": len(zh_paragraphs),
        "manifest": str(chunks_dir.relative_to(ROOT) / "manifest.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--reference-chars", type=int, default=9000)
    args = parser.parse_args()

    selected = args.book_id or list(BOOKS)
    for book_id in selected:
        result = prepare_book(BOOKS[book_id], args)
        print(
            "prepared "
            f"book_id={result['book_id']} chunks={result['chunks']} "
            f"en_chapters={result['english_chapters']} "
            f"zh_ref_paragraphs={result['chinese_reference_paragraphs']} "
            f"manifest={result['manifest']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
