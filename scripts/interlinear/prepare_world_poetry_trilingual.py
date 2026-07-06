#!/usr/bin/env python3
"""Prepare world-poetry trilingual chunk manifests.

This is a preparation-only script. It converts the best available poetry source
into reviewed Markdown-like text, then writes the standard trilingual chunk
schema consumed by ``codex_trilingual_plain_json_worker.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = ROOT / "data/source-plan/world-poetry-source-batch.json"
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

SPACE_RE = re.compile(r"[ \t\u00a0]+")
HEADING_RE = re.compile(r"^#{1,6}\s+")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
NUMERIC_SECTION_RE = re.compile(r"/(\d+)$")
BOILERPLATE_PARTS = (
    "Public domain",
    "This work is in the public domain",
    "This is a disambiguation page",
    "Search for titles containing",
    "sister projects",
    "姊妹计划",
    "姊妹計劃",
    "版本信息",
    "版权状况",
    "版權狀況",
    "公有领域",
    "公有領域",
    "Wikidata item",
    "维基百科",
    "維基百科",
)
SECTION_START_MARKERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("gibran-the-prophet", "en"): ("THE PROPHET",),
}
SECTION_END_MARKERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("gibran-the-prophet", "en"): ("*** END OF", "PLEASE READ THIS BEFORE"),
    ("tagore-stray-birds", "en"): ("THE WORKS OF RABINDRANATH TAGORE", "RABINDRANATH TAGORE'S NEW POEMS"),
}


@dataclass
class Section:
    title: str
    paragraphs: list[str]
    number: int
    part: str = ""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_stem(path: Path) -> str:
    cleaned = re.sub(r"[^\w\u3400-\u9fff\u3040-\u30ff.-]+", "-", path.stem, flags=re.UNICODE).strip("-")
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    if len(cleaned) > 56:
        cleaned = cleaned[:56].rstrip("-")
    return f"{cleaned or 'source'}-{digest}"


def clean_line(line: str) -> str:
    line = html.unescape(line)
    line = line.replace("\u200b", "").replace("\ufeff", "")
    line = line.replace("\u3000", " ")
    line = SPACE_RE.sub(" ", line).strip()
    return line


def is_boilerplate(line: str) -> bool:
    if not line:
        return True
    if line in {"|", "—", "←", "→", "Layout 2"}:
        return True
    if line.startswith(("#REDIRECT", "{{", "[[Category:")):
        return True
    if any(part in line for part in BOILERPLATE_PARTS):
        return True
    if re.fullmatch(r"[0-9]{6,}\s+.*", line):
        return True
    if re.fullmatch(r"[\d ivxlcdmIVXLCDM]+", line) and len(line) > 4:
        return True
    return False


def clean_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    blank = False
    for raw in lines:
        line = clean_line(raw)
        if is_boilerplate(line):
            if not blank and out:
                out.append("")
                blank = True
            continue
        if not line:
            if not blank and out:
                out.append("")
                blank = True
            continue
        out.append(line)
        blank = False
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def meaningful_text(text: str, lang: str) -> bool:
    if len(text.strip()) < 80:
        return False
    if lang == "zh":
        return bool(CJK_RE.search(text))
    if lang == "en":
        return bool(LATIN_RE.search(text))
    if lang == "ja":
        return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    return bool(text.strip())


def natural_title_key(title: str) -> tuple[int, str]:
    match = NUMERIC_SECTION_RE.search(title)
    if match:
        return (int(match.group(1)), title)
    return (10_000_000, title)


def strip_links_and_markup(text: str) -> str:
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    return text


def extract_html_lines(path: Path, *, section_title: str = "") -> list[str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for selector in (
        ".ws-header",
        ".ws-noexport",
        ".licenseContainer",
        ".licensetpl",
        ".printfooter",
        ".mw-editsection",
        "style",
        "script",
        "table",
        "sup",
    ):
        for node in soup.select(selector):
            node.decompose()
    root = soup.select_one(".mw-parser-output") or soup.body or soup
    raw_text = root.get_text("\n")
    if "disambiguation page" in raw_text or "may refer to:" in raw_text:
        return []
    lines = [line for line in raw_text.splitlines()]
    lines = clean_lines(lines)
    if not lines:
        return []

    numeric = NUMERIC_SECTION_RE.search(section_title)
    if numeric:
        wanted = numeric.group(1)
        for idx, line in enumerate(lines[:40]):
            if line == wanted or line == f"{wanted}.":
                lines = lines[idx + 1 :]
                break
    else:
        for idx, line in enumerate(lines[:120]):
            if line in {"1", "I"}:
                lines = lines[idx:]
                break
    return clean_lines(lines)


def extract_raw_wiki_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "{{disambiguation" in text.lower() or "may refer to" in text:
        return []
    text = re.sub(r"\{\{header.*?\}\}", " ", text, flags=re.S | re.I)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = strip_links_and_markup(text)
    lines = text.splitlines()
    return clean_lines(lines)


def split_lines_to_sections(book_title: str, lines: list[str], *, lang: str) -> list[Section]:
    sections: list[Section] = []
    current_title = book_title
    current: list[str] = []
    number = 1

    def flush() -> None:
        nonlocal current, number, current_title
        paragraphs = [p for p in paragraphs_from_lines(current, lang=lang) if meaningful_text(p, lang)]
        if paragraphs:
            sections.append(Section(current_title or f"Section {number}", paragraphs, len(sections) + 1))
        current = []

    for line in lines:
        normalized_heading = line.lstrip("#").strip() if HEADING_RE.match(line) else line.strip()
        is_heading = False
        if HEADING_RE.match(line):
            is_heading = True
        elif re.fullmatch(r"第?[一二三四五六七八九十百千\d]+[章卷首篇部]?", normalized_heading) and len(normalized_heading) <= 12:
            is_heading = True
        elif re.fullmatch(r"\d{1,4}", normalized_heading):
            is_heading = True
        elif lang == "en" and normalized_heading.isupper() and 3 <= len(normalized_heading) <= 80:
            is_heading = True

        if is_heading:
            flush()
            current_title = normalized_heading
            number += 1
            continue
        current.append(line)
    flush()
    if not sections and lines:
        paragraphs = paragraphs_from_lines(lines, lang=lang)
        sections = [Section(book_title, paragraphs, 1)]
    return sections


def paragraphs_from_lines(lines: list[str], *, lang: str) -> list[str]:
    paragraphs: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        if lang in {"zh", "ja"}:
            text = "\n".join(pending).strip()
        else:
            text = "\n".join(pending).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text and not is_boilerplate(text):
            paragraphs.append(text)
        pending = []

    for line in lines:
        if not line:
            flush()
            continue
        if re.fullmatch(r"\d{1,4}", line) and pending:
            flush()
            pending.append(line)
            flush()
            continue
        pending.append(line)
        if len("\n".join(pending)) > 900:
            flush()
    flush()
    return paragraphs


def extract_wikisource_export(manifest_path: Path, *, title: str, lang: str) -> list[Section]:
    base = manifest_path.parent
    entries = [entry for entry in load_json(manifest_path) if entry.get("status") == "ok"]
    numeric_entries = [entry for entry in entries if NUMERIC_SECTION_RE.search(str(entry.get("title") or ""))]
    selected = numeric_entries if numeric_entries else entries
    selected.sort(key=lambda entry: natural_title_key(str(entry.get("title") or "")))

    sections: list[Section] = []
    for entry in selected:
        entry_title = str(entry.get("title") or title)
        rel_html = entry.get("html")
        rel_raw = entry.get("raw")
        lines: list[str] = []
        if isinstance(rel_html, str) and (base / rel_html).exists():
            lines = extract_html_lines(base / rel_html, section_title=entry_title)
        if not meaningful_text("\n".join(lines), lang) and isinstance(rel_raw, str) and (base / rel_raw).exists():
            lines = extract_raw_wiki_lines(base / rel_raw)
        text = "\n".join(lines)
        if not meaningful_text(text, lang):
            continue
        if not numeric_entries and len(selected) == 1:
            nested = split_lines_to_sections(title, lines, lang=lang)
            for section in nested:
                section.number = len(sections) + 1
                sections.append(section)
            continue
        section_number = len(sections) + 1
        short_title = entry_title.split("/")[-1] if "/" in entry_title else entry_title
        if re.fullmatch(r"\d+", short_title):
            display_title = f"{title} {short_title}"
        else:
            display_title = short_title or title
        paragraphs = paragraphs_from_lines(lines, lang=lang)
        if paragraphs:
            sections.append(Section(display_title, paragraphs, section_number))
    return sections


def run_pandoc(epub: Path, output: Path) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["pandoc", str(epub), "-t", "gfm", "--wrap=none", "-o", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode == 0 and output.exists()


def extract_epub(epub: Path, *, title: str, lang: str, work_dir: Path) -> list[Section]:
    raw = work_dir / f"{cache_stem(epub)}.raw.md"
    if not raw.exists():
        run_pandoc(epub, raw)
    if not raw.exists():
        return []
    text = raw.read_text(encoding="utf-8", errors="ignore")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = strip_links_and_markup(line)
        line = clean_line(line)
        lines.append(line)
    lines = clean_lines(lines)
    return split_lines_to_sections(title, lines, lang=lang)


def extract_pdf(pdf: Path, *, title: str, lang: str, work_dir: Path, max_pages: int = 0) -> list[Section]:
    txt = work_dir / f"{cache_stem(pdf)}.pdftotext.txt"
    if not txt.exists():
        txt.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["pdftotext", "-layout"]
        if max_pages > 0:
            cmd.extend(["-l", str(max_pages)])
        cmd.extend([str(pdf), str(txt)])
        subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not txt.exists():
        return []
    lines = txt.read_text(encoding="utf-8", errors="ignore").splitlines()
    cleaned: list[str] = []
    for line in lines:
        line = clean_line(line)
        line = re.sub(r"^\s*\d+\s*$", "", line)
        if len(line) > 160 and line.count(" ") < 2 and lang == "en":
            continue
        cleaned.append(line)
    cleaned = clean_lines(cleaned)
    return split_lines_to_sections(title, cleaned, lang=lang)


def sections_to_markdown(title: str, sections: list[Section]) -> str:
    out = [f"# {title}", ""]
    for section in sections:
        out.extend([f"## {section.title}", ""])
        for paragraph in section.paragraphs:
            out.append(paragraph)
            out.append("")
    return "\n".join(out).strip() + "\n"


def trim_sections(book_id: str, lang: str, sections: list[Section]) -> list[Section]:
    start_markers = SECTION_START_MARKERS.get((book_id, lang), ())
    end_markers = SECTION_END_MARKERS.get((book_id, lang), ())
    start = 0
    end = len(sections)
    if start_markers:
        for idx, section in enumerate(sections):
            title = section.title.strip().replace("\\*", "*").strip("* ").strip()
            if any(title == marker for marker in start_markers):
                start = idx
                break
    if end_markers:
        for idx, section in enumerate(sections[start:], start=start):
            haystack = (f"{section.title}\n" + "\n".join(section.paragraphs[:2])).replace("\\*", "*")
            if any(marker in haystack for marker in end_markers):
                end = idx
                break
    trimmed = sections[start:end]
    for idx, section in enumerate(trimmed, start=1):
        section.number = idx
    return trimmed


def all_text(sections: list[Section]) -> str:
    return "\n\n".join(paragraph for section in sections for paragraph in section.paragraphs)


def reference_window(text: str, start_ratio: float, end_ratio: float, *, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    start = max(0, int(len(text) * start_ratio) - max_chars // 3)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        pad = max_chars - (end - start)
        start = max(0, start - pad // 2)
        end = min(len(text), end + pad // 2)
    return text[start:end]


def best_sources_for_lang(plan: dict[str, Any], lang: str) -> list[tuple[str, Path, str]]:
    paths = plan.get("source_paths") or {}
    ranked: list[tuple[int, str, Path, str]] = []
    for key, value in paths.items():
        path = ROOT / str(value)
        if not path.exists():
            continue
        lower_key = key.lower()
        suffix = path.suffix.lower()
        key_lang = ""
        if lower_key.startswith("en") or "_en" in lower_key or "english" in lower_key:
            key_lang = "en"
        elif lower_key.startswith(("zh", "cn")) or "_zh" in lower_key or "chinese" in lower_key:
            key_lang = "zh"
        elif lower_key.startswith(("ja", "jp")) or "_ja" in lower_key or "_jp" in lower_key or "japanese" in lower_key:
            key_lang = "ja"
        elif lang == "en" and any(token in lower_key for token in ("byron", "keats", "shelley", "yeats", "wilde")):
            key_lang = "en"
        if key_lang and key_lang != lang:
            continue
        priority = 100
        if "wikisource_export" in lower_key and suffix == ".json":
            priority = 0
        elif suffix == ".epub":
            priority = 10
        elif suffix == ".pdf":
            priority = 20
        if lang == "zh" and "bilingual" in lower_key:
            priority = 15
        ranked.append((priority, key, path, suffix))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [(key, path, suffix) for _, key, path, suffix in ranked]


def extract_lang_sections(
    plan: dict[str, Any],
    lang: str,
    *,
    work_dir: Path,
    required: bool = False,
) -> tuple[list[Section], dict[str, Any] | None]:
    title = plan.get(f"book_title_{lang}") or plan.get("book_title_en") or plan["book_id"]
    for key, path, suffix in best_sources_for_lang(plan, lang):
        sections: list[Section] = []
        if suffix == ".json" and "wikisource_export" in key:
            sections = extract_wikisource_export(path, title=str(title), lang=lang)
        elif suffix == ".epub":
            sections = extract_epub(path, title=str(title), lang=lang, work_dir=work_dir)
        elif suffix == ".pdf":
            sections = extract_pdf(path, title=str(title), lang=lang, work_dir=work_dir, max_pages=0)
        text = all_text(sections)
        if meaningful_text(text, lang):
            sections = trim_sections(plan["book_id"], lang, sections)
            if meaningful_text(all_text(sections), lang):
                return sections, {"key": key, "path": rel(path), "method": suffix.lstrip(".")}
    if required:
        raise RuntimeError(f"no usable {lang} source extracted for {plan['book_id']}")
    return [], None


def split_long_paragraph(paragraph: str, *, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    lines = [line for line in paragraph.splitlines() if line.strip()]
    if len(lines) > 1:
        out: list[str] = []
        pending = ""
        for line in lines:
            if pending and len(pending) + len(line) + 1 > max_chars:
                out.append(pending)
                pending = line
            else:
                pending = f"{pending}\n{line}" if pending else line
        if pending:
            out.append(pending)
        return out
    parts = re.split(r"(?<=[.!?。！？；;])\s+", paragraph)
    out = []
    pending = ""
    for part in parts:
        if pending and len(pending) + len(part) + 1 > max_chars:
            out.append(pending)
            pending = part
        else:
            pending = f"{pending} {part}".strip() if pending else part
    if pending:
        out.append(pending)
    return out


def make_chunks(
    plan: dict[str, Any],
    spine_sections: list[Section],
    extracted: dict[str, list[Section]],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    book_id = plan["book_id"]
    spine_lang = plan.get("source_spine_lang") or "en"
    reference_texts = {lang: all_text(sections) for lang, sections in extracted.items()}
    total_chars = max(sum(len(p) + 1 for s in spine_sections for p in s.paragraphs), 1)
    global_cursor = 0
    paragraph_counter = 0
    chunks: list[dict[str, Any]] = []

    for section in spine_sections:
        pending: list[dict[str, str]] = []
        pending_chars = 0
        pending_start = global_cursor

        def flush() -> None:
            nonlocal pending, pending_chars, pending_start
            if not pending:
                return
            chunk_index = len(chunks) + 1
            chunk_id = f"{book_id}-c{chunk_index:04d}"
            source_ref = "\n\n".join(item[spine_lang] for item in pending)
            start_ratio = pending_start / total_chars
            end_ratio = min(1.0, (pending_start + pending_chars) / total_chars)

            def ref_for(lang: str) -> dict[str, Any]:
                if lang == spine_lang:
                    return {
                        "available": True,
                        "chapter": section.title,
                        "text": source_ref,
                        "quality": "source_spine_poetry_text",
                    }
                text = reference_window(reference_texts.get(lang, ""), start_ratio, end_ratio, max_chars=reference_chars)
                return {
                    "available": bool(text),
                    "chapter": "global-ratio-poetry-window" if text else "",
                    "text": text,
                    "quality": "published_or_source_reference_window" if text else "generate_from_source_spine",
                }

            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": book_id,
                    "source_spine_lang": spine_lang,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "chapter_id": f"poem-{section.number:04d}",
                    "chapter_number": section.number,
                    "chapter_title_en": section.title if spine_lang == "en" else plan.get("book_title_en", ""),
                    "chapter_title_zh": section.title if spine_lang == "zh" else plan.get("book_title_zh", ""),
                    "chapter_part_en": section.part,
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": {
                        "english": ref_for("en"),
                        "zh_primary": ref_for("zh"),
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": ref_for("ja"),
                    },
                    "poetry_note": "Preserve intentional poem line/stanza grouping. Do not copy PDF/OCR accidental line wraps.",
                }
            )
            pending = []
            pending_chars = 0

        for paragraph in section.paragraphs:
            for piece in split_long_paragraph(paragraph, max_chars=max_chunk_chars):
                paragraph_counter += 1
                item = {"id": f"{book_id}-s{section.number:04d}-p{paragraph_counter:05d}", spine_lang: piece}
                piece_len = len(piece) + 1
                if pending and pending_chars + piece_len > max_chunk_chars:
                    flush()
                    pending_start = global_cursor
                if not pending:
                    pending_start = global_cursor
                pending.append(item)
                pending_chars += piece_len
                global_cursor += piece_len
        flush()

    source_paths = plan.get("source_paths") or {}
    source_sha256 = {}
    for key, value in source_paths.items():
        path = ROOT / str(value)
        if path.exists() and path.is_file() and path.stat().st_size < 200 * 1024 * 1024:
            source_sha256[key] = sha256(path)
    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": book_id,
        "book_title_en": plan.get("book_title_en", ""),
        "book_title_zh": plan.get("book_title_zh", ""),
        "book_title_ja": plan.get("book_title_ja", ""),
        "book_title_zh_reading": plan.get("book_title_zh_reading", ""),
        "book_title_ja_reading": plan.get("book_title_ja_reading", ""),
        "author": plan.get("author", ""),
        "author_reading_zh": plan.get("author_reading_zh", ""),
        "author_reading_ja": plan.get("author_reading_ja", ""),
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": spine_lang,
        "source_paths": source_paths,
        "source_sha256": source_sha256,
        "source_note": "World-poetry preparation; source spine is split by poem/stanza groups and references are broad ratio windows.",
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


def prepare_book(book_id: str, *, max_chunk_chars: int, reference_chars: int) -> dict[str, Any]:
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    plan = load_json(plan_path)
    book_root = ROOT / "books" / book_id
    work_source_dir = book_root / "work/source-extraction"
    markdown_dir = book_root / "markdown"
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"

    spine_lang = plan.get("source_spine_lang") or "en"
    extracted: dict[str, list[Section]] = {}
    extraction_meta: dict[str, Any] = {}
    for lang in ("en", "zh", "ja"):
        sections, meta = extract_lang_sections(plan, lang, work_dir=work_source_dir, required=(lang == spine_lang))
        if sections:
            extracted[lang] = sections
            write_text(markdown_dir / f"{lang}.md", sections_to_markdown(str(plan.get(f"book_title_{lang}") or plan["book_id"]), sections))
        if meta:
            extraction_meta[lang] = meta

    spine_sections = extracted.get(spine_lang) or []
    if not spine_sections:
        raise RuntimeError(f"no source spine sections for {book_id}")

    manifest, chunks = make_chunks(
        plan,
        spine_sections,
        extracted,
        max_chunk_chars=max_chunk_chars,
        reference_chars=reference_chars,
    )
    write_json(chunks_dir / "manifest.json", manifest)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    plan.update(
        {
            "status": "prepared_trilingual",
            "launchable": True,
            "curated_by": CURATED_BY,
            "curated_url": CURATED_URL,
            "powered_by": POWERED_BY,
            "chunk_mode": "poem_stanza_line_group",
            "reference_scope": "global_ratio_poetry_window",
            "chunks_jsonl": rel(chunks_dir / "chunks.jsonl"),
            "chunks_manifest": rel(chunks_dir / "manifest.json"),
            "raw_chunk_dir": rel(raw_chunk_dir),
            "preview_json": rel(preview_dir / f"{book_id}.partial.json"),
            "assembled_json": rel(preview_dir / f"{book_id}.partial.json"),
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "chunk_count": len(chunks),
            "source_extraction": extraction_meta,
            "preparation_notes": {
                "status": "Chunk manifest prepared and launchable.",
                "chunking": "poem/stanza/line groups; no generated translations are overwritten.",
                "quality_rule": "Wikisource/EPUB preferred; PDF text used only when no better spine source exists.",
            },
        }
    )
    plan["markdown"] = {
        lang: rel(markdown_dir / f"{lang}.md")
        for lang in ("en", "zh", "ja")
        if (markdown_dir / f"{lang}.md").exists()
    }
    write_json(plan_path, plan)
    return {
        "book_id": book_id,
        "spine": spine_lang,
        "chunks": len(chunks),
        "sections": len(spine_sections),
        "extracted_langs": sorted(extracted),
    }


def update_batch_status(batch_path: Path, results: list[dict[str, Any]]) -> None:
    batch = load_json(batch_path)
    by_id = {item["book_id"]: item for item in results}
    for task in batch.get("tasks", []):
        book_id = task.get("book_id")
        if book_id in by_id:
            task["status"] = "chunked_launchable"
            task["chunk_count"] = by_id[book_id]["chunks"]
            task["prepared_chunks_at"] = datetime.now(timezone.utc).isoformat()
    batch["status"] = "poetry_chunks_prepared"
    batch["last_chunk_preparation_at"] = datetime.now(timezone.utc).isoformat()
    write_json(batch_path, batch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", default=rel(DEFAULT_BATCH))
    parser.add_argument("--book-id", action="append", help="Prepare one book id; repeatable. Defaults to the batch.")
    parser.add_argument("--max-chunk-chars", type=int, default=1800)
    parser.add_argument("--reference-chars", type=int, default=9000)
    parser.add_argument("--no-batch-update", action="store_true")
    args = parser.parse_args()

    batch_path = ROOT / args.batch
    batch = load_json(batch_path)
    selected = args.book_id or [task["book_id"] for task in batch.get("tasks", [])]
    results = []
    for book_id in selected:
        result = prepare_book(book_id, max_chunk_chars=args.max_chunk_chars, reference_chars=args.reference_chars)
        results.append(result)
        print(
            f"prepared={result['book_id']} spine={result['spine']} "
            f"sections={result['sections']} chunks={result['chunks']} "
            f"langs={','.join(result['extracted_langs'])}",
            flush=True,
        )
    if not args.no_batch_update:
        update_batch_status(batch_path, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
