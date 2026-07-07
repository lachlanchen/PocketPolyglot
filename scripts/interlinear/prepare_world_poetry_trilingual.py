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
import sys
import zipfile
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
    "All rights reserved",
    "Library of Congress",
    "ISBN ",
    "DOI ",
    "Standard Ebooks",
    "Project Gutenberg",
    "source_pdf:",
    "source_pages:",
    "total_pdf_pages:",
    "ocr_engine:",
    "ocr_language:",
    "generated_at:",
    "Raw OCR",
    "Source: http",
    "Project: wikipedia",
    "Project: wikisource",
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
    references: dict[str, str] | None = None


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
    stripped = text.strip()
    if len(stripped) < 80:
        return False
    cjk = len(CJK_RE.findall(stripped))
    latin = len(LATIN_RE.findall(stripped))
    kana = len(re.findall(r"[\u3040-\u30ff]", stripped))
    if lang == "zh":
        return cjk >= 80
    if lang == "en":
        return latin >= 160 and latin >= cjk * 1.5
    if lang == "ja":
        return kana + cjk >= 80 and (kana >= 20 or cjk >= 80)
    return bool(stripped)


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


def poem_lines_from_node(node: Any) -> list[str]:
    node = BeautifulSoup(str(node), "html.parser")
    for selector in ("style", "script", "sup", ".pagenum", ".mw-editsection", ".variant-tooltip"):
        for child in node.select(selector):
            child.decompose()
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("\n")
    lines = [clean_line(line) for line in text.splitlines()]
    return clean_lines(lines)


def grouped_poem_paragraph(lines: list[str], *, title: str = "") -> str:
    clean: list[str] = []
    for line in lines:
        if not line:
            clean.append("")
            continue
        if title and line.strip("《》").strip() == title.strip("《》").strip() and not clean:
            continue
        if re.fullmatch(r"[0-9]{4}", line):
            continue
        clean.append(line)
    while clean and not clean[0]:
        clean.pop(0)
    while clean and not clean[-1]:
        clean.pop()
    return "\n".join(clean).strip()


def extract_xu_zhimo_wikisource_poems(manifest_path: Path) -> tuple[list[Section], dict[str, Any]]:
    """Extract Xu Zhimo poems from mirrored Wikisource pages.

    The local printed PDF is a useful reference scan, but its automatic OCR is
    too noisy. The mirrored Wikisource pages expose poem bodies in `.poem`
    nodes, which lets us prepare launchable chunks without importing author-page
    metadata or public-domain notices.
    """

    base = manifest_path.parent
    manifest_data = load_json(manifest_path)
    entries = manifest_data.get("pages", manifest_data if isinstance(manifest_data, list) else [])
    sections: list[Section] = []
    skipped: list[str] = []
    for entry in entries:
        if entry.get("status") != "ok":
            continue
        title = str(entry.get("actual_title") or entry.get("title") or "").strip()
        if not title:
            continue
        if title.startswith("Author:"):
            skipped.append("author metadata root")
            continue
        if title.endswith("/序"):
            skipped.append(title)
            continue
        rel_html = entry.get("html")
        if not isinstance(rel_html, str) or not (base / rel_html).exists():
            skipped.append(title)
            continue
        soup = BeautifulSoup((base / rel_html).read_text(encoding="utf-8", errors="ignore"), "html.parser")
        poem_nodes = soup.select(".prp-pages-output .poem") or soup.select(".poem")
        parts: list[str] = []
        for node in poem_nodes:
            paragraph = grouped_poem_paragraph(poem_lines_from_node(node), title=title)
            if paragraph:
                parts.append(paragraph)
        if not parts:
            lines = extract_html_lines(base / rel_html, section_title=title)
            content: list[str] = []
            in_source_work = False
            for line in lines:
                if line == "本作品收錄於《":
                    in_source_work = True
                    continue
                if in_source_work:
                    if line == "》":
                        in_source_work = False
                    continue
                if line in {title, "作者：", "徐志摩", "民國時期"}:
                    continue
                if re.search(r"版權期限|公有領域|Public domain|这部作品|這部作品", line):
                    break
                content.append(line)
            paragraph = grouped_poem_paragraph(content, title=title)
            # Avoid treating long prose prefaces as poems.
            if paragraph and (paragraph.count("\n") >= 3 or len(paragraph) <= 300):
                parts.append(paragraph)
        text = "\n\n".join(parts).strip()
        cjk_count = len(CJK_RE.findall(text))
        if cjk_count < 20:
            skipped.append(title)
            continue
        sections.append(Section(title=title.split("/")[-1], paragraphs=[text], number=len(sections) + 1))

    return sections, {
        "key": "zh_wikisource_poems_export",
        "path": rel(manifest_path),
        "method": "wikisource_poem_html",
        "poem_count": len(sections),
        "skipped_titles": skipped[:12],
    }


def epub_text_by_file(epub: Path, src: str) -> list[str]:
    with zipfile.ZipFile(epub) as archive:
        name = src.split("#", 1)[0]
        if not name.startswith("OEBPS/"):
            name = f"OEBPS/{name}"
        soup = BeautifulSoup(archive.read(name), "html.parser")
    for selector in ("style", "script", "sup", "table", ".mbp_pagebreak"):
        for node in soup.select(selector):
            node.decompose()
    stop = False
    lines: list[str] = []
    for node in soup.body.find_all(["p", "blockquote"], recursive=True) if soup.body else []:
        line = clean_line(node.get_text(" ", strip=True))
        if not line:
            continue
        if line in {"注释", "Notes", "本书相关"}:
            stop = True
        if stop:
            continue
        if re.fullmatch(r"[①②③④⑤⑥⑦⑧⑨⑩]+", line):
            continue
        lines.append(line)
    return clean_lines(lines)


def extract_whitman_bilingual_anthology(plan: dict[str, Any]) -> tuple[dict[str, list[Section]], dict[str, Any]]:
    """Extract the local bilingual anthology as its actual Whitman volume.

    The EPUB metadata says it belongs to a 23-volume anthology, but the file
    present here contains one alternating English/Chinese Whitman volume. Pairing
    adjacent TOC entries avoids a mixed-language fallback and gives exact source
    translations for each poem.
    """

    epub_value = (plan.get("source_paths") or {}).get("zh_en_anthology_epub")
    if not epub_value:
        return {}, {}
    epub = ROOT / str(epub_value)
    if not epub.exists():
        return {}, {}
    with zipfile.ZipFile(epub) as archive:
        toc = BeautifulSoup(archive.read("OEBPS/toc.ncx"), "xml")
    top = toc.find("navMap").find("navPoint") if toc.find("navMap") else None
    children = top.find_all("navPoint", recursive=False) if top else []
    content_points: list[tuple[str, str]] = []
    started = False
    for node in children:
        label_node = node.find("navLabel")
        content_node = node.find("content")
        if not label_node or not content_node:
            continue
        label = clean_line(label_node.get_text(" ", strip=True))
        src = str(content_node.get("src") or "")
        if label == "插图":
            started = True
            continue
        if label == "本书相关":
            break
        if started:
            content_points.append((label, src))

    en_sections: list[Section] = []
    zh_sections: list[Section] = []
    skipped_pairs: list[str] = []
    index = 0
    while index + 1 < len(content_points):
        en_title, en_src = content_points[index]
        zh_title, zh_src = content_points[index + 1]
        if not LATIN_RE.search(en_title) or not CJK_RE.search(zh_title):
            skipped_pairs.append(f"{en_title} / {zh_title}")
            index += 1
            continue
        en_lines = epub_text_by_file(epub, en_src)
        zh_lines = epub_text_by_file(epub, zh_src)
        if en_lines and en_lines[0].strip() == en_title.strip():
            en_lines = en_lines[1:]
        if zh_lines and zh_lines[0].strip() == zh_title.strip():
            zh_lines = zh_lines[1:]
        en_text = grouped_poem_paragraph(en_lines, title=en_title)
        zh_text = grouped_poem_paragraph(zh_lines, title=zh_title)
        if len(LATIN_RE.findall(en_text)) < 40 or len(CJK_RE.findall(zh_text)) < 20:
            skipped_pairs.append(f"{en_title} / {zh_title}")
            index += 2
            continue
        number = len(en_sections) + 1
        en_sections.append(Section(en_title, [en_text], number, references={"zh": zh_text}))
        zh_sections.append(Section(zh_title, [zh_text], number, references={"en": en_text}))
        index += 2

    extracted = {"en": en_sections, "zh": zh_sections}
    return extracted, {
        "en": {
            "key": "zh_en_anthology_epub",
            "path": rel(epub),
            "method": "epub_toc_alternating_english_chinese",
            "actual_volume": "Walt Whitman selected poems",
            "paired_poem_count": len(en_sections),
            "skipped_pairs": skipped_pairs[:12],
        },
        "zh": {
            "key": "zh_en_anthology_epub",
            "path": rel(epub),
            "method": "epub_toc_alternating_english_chinese",
            "actual_volume": "惠特曼诗选",
            "paired_poem_count": len(zh_sections),
        },
    }


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


def ocr_lang_for(lang: str) -> str:
    if lang == "zh":
        return "chi_sim+chi_tra"
    if lang == "ja":
        return "jpn+Japanese"
    return "eng"


def extract_ocr_markdown(pdf: Path, *, lang: str, work_dir: Path) -> Path | None:
    output = work_dir / f"{cache_stem(pdf)}.{lang}.ocr.md"
    if output.exists() and output.stat().st_size > 1000:
        return output
    cmd = [
        sys.executable,
        "scripts/interlinear/pdf_text_or_ocr.py",
        str(pdf),
        "--output",
        str(output),
        "--force-ocr",
        "--ocr-lang",
        ocr_lang_for(lang),
        "--ocr-psm",
        "4",
        "--ocr-dpi",
        "260",
        "--ocr-workers",
        "6",
        "--ocr-crop",
        "--ocr-threshold",
        "--keep-linebreaks",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        log = output.with_suffix(".ocr.log")
        log.write_text(proc.stdout, encoding="utf-8")
        return None
    return output if output.exists() else None


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
    if not meaningful_text("\n".join(cleaned), lang) and pdf.suffix.lower() == ".pdf":
        ocr_md = extract_ocr_markdown(pdf, lang=lang, work_dir=work_dir)
        if ocr_md is not None:
            ocr_lines = []
            for line in ocr_md.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = clean_line(strip_links_and_markup(line))
                ocr_lines.append(line)
            ocr_cleaned = clean_lines(ocr_lines)
            if meaningful_text("\n".join(ocr_cleaned), lang):
                cleaned = ocr_cleaned
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
        descriptor = f"{lower_key} {path.as_posix().lower()}"
        suffix = path.suffix.lower()
        key_langs: set[str] = set()
        if re.search(r"(^|[/_.-])en([/_.-]|$)", descriptor) or "english" in descriptor:
            key_langs.add("en")
        if re.search(r"(^|[/_.-])(zh|cn)([/_.-]|$)", descriptor) or "chinese" in descriptor:
            key_langs.add("zh")
        if re.search(r"(^|[/_.-])(ja|jp)([/_.-]|$)", descriptor) or "japanese" in descriptor:
            key_langs.add("ja")
        if lang == "en" and any(token in lower_key for token in ("byron", "keats", "shelley", "yeats", "wilde")):
            key_langs.add("en")
        if not key_langs or lang not in key_langs:
            continue
        is_author_or_metadata = (
            "wiki_author" in lower_key
            or "wikipedia" in lower_key
            or "author" in lower_key
            or "en-author" in lower_key
            or "zh-author" in lower_key
            or "ja-author" in lower_key
            or "/author-" in descriptor
            or "/author/" in descriptor
        )
        if is_author_or_metadata:
            continue
        is_reference = "reference" in lower_key or lower_key.endswith("_ref")
        is_wikisource_text = "wikisource_export" in lower_key and suffix == ".json" and not is_author_or_metadata
        explicit_lang_source = (
            lower_key.startswith(lang)
            or f"{lang}_" in lower_key
            or f"_{lang}" in lower_key
            or (lang == "ja" and (lower_key.startswith("jp") or "_jp" in lower_key))
        )

        priority = 100
        if suffix == ".epub" and explicit_lang_source and not is_reference:
            priority = 0
        elif suffix == ".pdf" and explicit_lang_source and not is_reference:
            priority = 5
        elif is_wikisource_text:
            priority = 15
        elif suffix == ".epub":
            priority = 25
        elif suffix == ".pdf":
            priority = 35
        if is_reference:
            priority += 25
        if is_author_or_metadata:
            priority += 60
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
                exact_section_ref = (section.references or {}).get(lang, "").strip()
                if lang == spine_lang:
                    return {
                        "available": True,
                        "chapter": section.title,
                        "text": source_ref,
                        "quality": "source_spine_poetry_text",
                    }
                if exact_section_ref:
                    return {
                        "available": True,
                        "chapter": section.title,
                        "text": exact_section_ref,
                        "quality": "paired_source_poetry_text",
                    }
                text = reference_window(reference_texts.get(lang, ""), start_ratio, end_ratio, max_chars=reference_chars)
                return {
                    "available": bool(text),
                    "chapter": "source-edition-poetry-window" if text else "",
                    "text": text,
                    "quality": "source_edition_reference_window" if text else "generate_from_source_spine",
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
        "source_note": "World-poetry preparation; source spine is split by poem/stanza groups. Exact paired poem references are used when available; otherwise the writer generates missing languages from the clean source spine.",
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
    if book_id == "xu-zhimo-poems":
        poems_manifest = ROOT / (plan.get("source_paths") or {}).get(
            "zh_wikisource_poems_export",
            "resources/curated-books/world-poetry/xu-zhimo/poems-zh-wikisource/manifest.json",
        )
        if poems_manifest.exists():
            sections, meta = extract_xu_zhimo_wikisource_poems(poems_manifest)
            if sections:
                extracted["zh"] = sections
                extraction_meta["zh"] = meta
                plan.setdefault("source_paths", {})["zh_wikisource_poems_export"] = rel(poems_manifest)
    elif book_id == "english-poetry-anthology":
        extracted, extraction_meta = extract_whitman_bilingual_anthology(plan)
        if extracted.get("en"):
            plan["book_title_en"] = "Walt Whitman: Selected Poems"
            plan["book_title_zh"] = "惠特曼诗选"
            plan["book_title_ja"] = "ホイットマン詩選"
            plan["author"] = "Walt Whitman"
            plan["author_reading_ja"] = "ウォルト・ホイットマン"

    for lang in ("en", "zh", "ja"):
        if lang not in extracted:
            sections, meta = extract_lang_sections(plan, lang, work_dir=work_source_dir, required=(lang == spine_lang))
            if sections:
                extracted[lang] = sections
            if meta:
                extraction_meta[lang] = meta
        if lang in extracted:
            write_text(
                markdown_dir / f"{lang}.md",
                sections_to_markdown(str(plan.get(f"book_title_{lang}") or plan["book_id"]), extracted[lang]),
            )

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
            "reference_scope": "paired_or_clean_poem_source",
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
                "quality_rule": "Use provided poem PDFs/EPUBs first. Wikisource text is allowed when it is a real poem text source. Wikipedia and author pages are metadata only, not poem chunks.",
            },
        }
    )
    plan["markdown"] = {
        lang: rel(markdown_dir / f"{lang}.md")
        for lang in ("en", "zh", "ja")
        if lang in extracted
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
            plan_path = ROOT / str(task.get("book_plan", ""))
            if plan_path.exists():
                plan = load_json(plan_path)
                task["title_en"] = plan.get("book_title_en", task.get("title_en", ""))
                task["title_zh"] = plan.get("book_title_zh", task.get("title_zh", ""))
                task["title_ja"] = plan.get("book_title_ja", task.get("title_ja", ""))
                task["author"] = plan.get("author", task.get("author", ""))
            task["status"] = "chunked_launchable"
            task["chunk_count"] = by_id[book_id]["chunks"]
            task["prepared_chunks_at"] = datetime.now(timezone.utc).isoformat()
            task.pop("blocked_reason", None)
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
