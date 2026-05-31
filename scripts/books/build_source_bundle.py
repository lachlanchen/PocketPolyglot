#!/usr/bin/env python3
"""Build a multisource markdown bundle from EPUB/PDF/Wiki/JSON sources.

Converts source files to cleaned markdown, assigns source roles, generates
a source-bundle.json manifest and a multisource book plan.  Suitable for
bilingual/interlinear book pipelines.

Generic: accepts any book-id and source paths.  Not hard-coded for Sishu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# ---- boilerplate stripping ----

NOISE_PREFIXES = (
    "Source:", "https://", "http://", "Generated from", "Root source:",
    "姊妹计划", "姉妹プロジェクト", "作者：", "file://",
)
NOISE_EXACT = {"←", "→", "◄", "►", "版本", "目錄", "目录", "目次"}
PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
FOOTNOTE_RE = re.compile(r"\[[0-9０-９]+\]")
PD_NOTICE_RE = re.compile(
    r"\n此作品在全世界都属于 公有领域[^\n]*\n\nPublic domain Public domain false false\n"
)
PD_EN_RE = re.compile(r"\nPublic domain Public domain false false\n")
DATE_HEADER_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},?\s*\d{1,2}:\d{2}\s*[AP]M$")


def clean_text(text: str) -> str:
    text = FOOTNOTE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise(text: str) -> bool:
    stripped = clean_text(text)
    if not stripped:
        return True
    if stripped in NOISE_EXACT or PAGE_NUMBER_RE.match(stripped):
        return True
    if DATE_HEADER_RE.match(stripped):
        return True
    if any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True
    if len(stripped) <= 18 and any(c in stripped for c in ("←", "→", "◄", "►")):
        return True
    return False


def strip_boilerplate(text: str) -> tuple[str, int]:
    """Remove PD notices and other boilerplate. Returns (cleaned_text, blocks_removed)."""
    before = text.count("此作品在全世界都属于 公有领域")
    text = PD_NOTICE_RE.sub("\n", text)
    text = PD_EN_RE.sub("\n", text)
    after = text.count("此作品在全世界都属于 公有领域")
    blocks = before - after
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    if not text.endswith("\n"):
        text += "\n"
    return text, blocks


# ---- file utilities ----

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---- source detection ----

def detect_source_kind(path: Path) -> str:
    """Return source kind: html_json, pdf_text, pdf_scan, wikisource_json, iiif_json."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = read_json(path)
        mode = data.get("mode", "")
        if mode in ("wikisource-book", "wikisource-html"):
            return "html_json"
        if mode == "iiif-pdf":
            return "iiif_json"
        if "html" in data:
            return "html_json"
        return "unknown_json"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    return "unknown"


def has_text_layer(pdf_path: Path) -> bool:
    proc = subprocess.run(
        ["pdftotext", "-f", "1", "-l", "2", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def pdf_page_count(pdf_path: Path) -> int:
    proc = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True
    )
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return 0


# ---- markdown generation ----

def pdf_text_to_markdown(pdf_path: Path, output_path: Path, title: str) -> str:
    """Extract text from a text-layer PDF and write cleaned markdown. Returns sha256."""
    proc = subprocess.run(
        ["pdftotext", "-raw", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    raw = proc.stdout.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = [f"# {title}", ""]
    current_heading = ""
    buffer: list[str] = []

    def flush():
        nonlocal buffer
        text = clean_text("".join(buffer))
        buffer = []
        if text and not is_noise(text):
            lines.extend([text, ""])

    for raw_line in raw.splitlines():
        stripped = clean_text(raw_line)
        if not stripped:
            flush()
            continue
        # Heuristic chapter detection: short line with 章/篇/卷/序 followed by longer text
        if re.match(r"^.{2,30}[章篇卷序](?:[一二三四五六七八九十百千]+)?\s*$", stripped):
            flush()
            current_heading = stripped
            lines.extend([f"## {stripped}", ""])
            continue
        if is_noise(stripped):
            continue
        buffer.append(stripped)
    flush()

    text, blocks = strip_boilerplate(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return sha256(output_path), blocks


def html_json_to_markdown(json_path: Path, output_path: Path, title: str) -> str:
    """Extract text from a wikisource/html JSON manifest and write cleaned markdown."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise SystemExit("Missing beautifulsoup4. Install: python -m pip install beautifulsoup4")

    data = read_json(json_path)
    html_path = Path(data.get("html", ""))
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path} (from {json_path})")

    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    lines: list[str] = [f"# {title}", ""]
    for section in soup.select("section.chapter"):
        heading = section.find("h2")
        chapter_title = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        if chapter_title and chapter_title.startswith(title):
            chapter_title = chapter_title[len(title):].strip("/")
        chapter_title = chapter_title or "未題"
        lines.extend([f"## {chapter_title}", ""])
        for node in section.find_all(["p", "li"], recursive=True):
            text = clean_text(node.get_text(" ", strip=True))
            if is_noise(text):
                continue
            lines.extend([text, ""])

    text, blocks = strip_boilerplate(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return sha256(output_path), blocks


# ---- source bundle and plan ----

def count_chapters(md_path: Path) -> int:
    if not md_path.exists():
        return 0
    text = md_path.read_text(encoding="utf-8")
    return len(re.findall(r"^## ", text, re.MULTILINE))


def count_text_chars(md_path: Path) -> int:
    if not md_path.exists():
        return 0
    text = md_path.read_text(encoding="utf-8")
    return len(re.sub(r"[#\s\n\-*_>`|]", "", text))


def build_source_entry(
    role: str, language: str, title: str, author: str,
    source_path: str, source_sha256: str,
    markdown_path: str, markdown_sha256: str,
    extraction_method: str, extraction_status: str,
    page_count: int, notes: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "role": role, "language": language, "title": title, "author": author,
        "source_path": source_path, "source_sha256": source_sha256,
        "markdown_path": markdown_path, "markdown_sha256": markdown_sha256,
        "extraction_method": extraction_method, "extraction_status": extraction_status,
        "chapter_count": count_chapters(ROOT / markdown_path) if markdown_path else 0,
        "text_chars": count_text_chars(ROOT / markdown_path) if markdown_path else 0,
        "notes": notes,
    }
    if page_count:
        entry["page_count"] = page_count
    return entry


# ---- CLI ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-id", required=True, help="e.g. sishu-jizhu-aginti")
    p.add_argument("--output-dir", required=True, help="e.g. books/<book-id>/sources")
    p.add_argument("--book-title-zh", default="", help="Chinese book title")
    p.add_argument("--book-title-ja", default="", help="Japanese book title")
    p.add_argument("--author", default="", help="Author name")
    p.add_argument("--author-ja", default="", help="Author name (Japanese)")
    p.add_argument("--main-zh", help="Path to main Chinese source (JSON or PDF)")
    p.add_argument("--reference-zh", help="Path to reference Chinese source")
    p.add_argument("--reference-ja", help="Path to reference Japanese source")
    p.add_argument("--reference-en", help="Path to reference English source")
    p.add_argument("--book-description", default="", help="Book description for plans")
    p.add_argument("--validate", action="store_true", help="Validate and report without writing")
    p.add_argument("--force", action="store_true", help="Overwrite existing markdown")
    return p


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    md_dir = output_dir / "markdown"
    md_dir.mkdir(parents=True, exist_ok=True)

    sources: dict[str, Any] = {}
    results: list[dict[str, Any]] = []

    # Predefined role configs
    role_configs = [
        ("main_zh", args.main_zh, "zh", args.book_title_zh or "Main Chinese", args.author or ""),
        ("reference_zh", args.reference_zh, "zh", args.book_title_zh or "Reference Chinese", args.author or ""),
        ("reference_ja", args.reference_ja, "ja", args.book_title_ja or "Reference Japanese", args.author_ja or args.author or ""),
        ("reference_en", args.reference_en, "en", "Reference English", ""),
    ]

    ROLE_STEMS = {"main_zh": "main", "reference_zh": "reference", "reference_ja": "reference", "reference_en": "reference"}

    for role, src_path, lang, title, author in role_configs:
        if not src_path:
            continue
        src = ROOT / src_path
        if not src.exists():
            print(f"WARNING: source not found: {src}", file=sys.stderr)
            continue

        kind = detect_source_kind(src)
        stem = ROLE_STEMS.get(role, role)
        md_path = (ROOT / output_dir / "markdown" / f"{lang}_{stem}.md").resolve()
        md_rel = str(md_path.relative_to(ROOT))
        src_sha = sha256(src)
        md_sha = ""
        extraction_status = "pending"
        extraction_method = kind
        page_count = 0
        notes = ""
        blocks_removed = 0

        if kind == "html_json":
            if args.force or not md_path.exists():
                try:
                    md_sha, blocks_removed = html_json_to_markdown(src, md_path, title)
                    extraction_status = "complete"
                    extraction_method = "html"
                    notes = f"HTML extraction via BeautifulSoup. Removed {blocks_removed} PD boilerplate blocks."
                except Exception as exc:
                    extraction_status = "failed"
                    notes = f"HTML extraction failed: {exc}"
            else:
                md_sha = sha256(md_path)
                extraction_status = "complete"
                extraction_method = "html"
                notes = "Markdown already exists (use --force to regenerate)."
        elif kind == "pdf":
            page_count = pdf_page_count(src)
            if has_text_layer(src):
                if args.force or not md_path.exists():
                    try:
                        md_sha, blocks_removed = pdf_text_to_markdown(src, md_path, title)
                        extraction_status = "complete"
                        extraction_method = "pdf_text"
                        notes = f"pdftotext extraction, {page_count} pages. Removed {blocks_removed} boilerplate blocks."
                    except Exception as exc:
                        extraction_status = "failed"
                        notes = f"PDF text extraction failed: {exc}"
                else:
                    md_sha = sha256(md_path)
                    extraction_status = "complete"
                    extraction_method = "pdf_text"
                    notes = "Markdown already exists (use --force to regenerate)."
            else:
                extraction_status = "requires_ocr"
                extraction_method = "ocr"
                notes = f"Scanned image PDF ({page_count} pages). No text layer. Requires OCR."
        elif kind == "iiif_json":
            page_count = read_json(src).get("page_count", 0)
            # Check the referenced PDF
            pdf_path_str = read_json(src).get("pdf", "")
            if pdf_path_str:
                pdf_path = Path(pdf_path_str)
                if pdf_path.exists() and has_text_layer(pdf_path):
                    # Has text layer in the PDF
                    if args.force or not md_path.exists():
                        try:
                            md_sha, blocks_removed = pdf_text_to_markdown(pdf_path, md_path, title)
                            extraction_status = "complete"
                            extraction_method = "pdf_text"
                            notes = f"pdftotext from IIIF PDF, {page_count} pages."
                        except Exception as exc:
                            extraction_status = "failed"
                            notes = f"PDF text extraction failed: {exc}"
                    else:
                        md_sha = sha256(md_path)
                        extraction_status = "complete"
                        extraction_method = "pdf_text"
                else:
                    extraction_status = "requires_ocr"
                    extraction_method = "ocr"
                    notes = f"IIIF scanned PDF ({page_count} pages). No text layer. Requires OCR."
            else:
                extraction_status = "requires_ocr"
                extraction_method = "ocr"
                notes = f"IIIF source ({page_count} pages). PDF not accessible. Requires OCR."
        elif kind == "epub":
            extraction_status = "pending"
            extraction_method = "epub"
            notes = "EPUB source. Use scripts/books/epub_to_markdown.py for extraction."
        else:
            extraction_status = "failed"
            notes = f"Unknown source kind: {kind}"

        entry = build_source_entry(
            role=role, language=lang, title=title, author=author,
            source_path=src_path, source_sha256=src_sha,
            markdown_path=md_rel if extraction_status == "complete" else "",
            markdown_sha256=md_sha,
            extraction_method=extraction_method,
            extraction_status=extraction_status,
            page_count=page_count, notes=notes,
        )
        sources[role] = entry

    # Build source-bundle.json
    bundle = {
        "schema_version": 1,
        "book_id": args.book_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "validation": {
            f"chapter_headings_{k.replace('_', '_') if '_' in k else k}": v.get("chapter_count", 0)
            for k, v in sources.items()
        },
    }
    # Add text char counts
    bundle["validation"]["main_text_chars"] = sources.get("main_zh", {}).get("text_chars", 0)
    for role_key, label in [("reference_zh", "reference_zh_text_chars"), ("reference_ja", "reference_ja_text_chars")]:
        bundle["validation"][label] = sources.get(role_key, {}).get("text_chars", 0)

    bundle["validation"]["notes"] = [
        f"{role}: {entry.get('extraction_status', 'unknown')} - {entry.get('notes', '')[:120]}"
        for role, entry in sources.items()
    ]

    bundle_path = (ROOT / output_dir / "source-bundle.json").resolve()
    validation_path = (ROOT / output_dir / "validation-report.json").resolve()

    if args.validate:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        print(f"\nValidation report would be written to: {validation_path.relative_to(ROOT)}")
        return 0

    write_json(bundle_path, bundle)
    write_json(validation_path, bundle["validation"])
    print(f"Source bundle: {bundle_path.relative_to(ROOT)}", file=sys.stderr)
    print(f"Validation:    {validation_path.relative_to(ROOT)}", file=sys.stderr)

    # Print summary
    for role, entry in sources.items():
        status = entry["extraction_status"]
        ch = entry.get("chapter_count", 0)
        chars = entry.get("text_chars", 0)
        md = entry.get("markdown_path", "(none)")
        print(f"  {role}: {status} ch={ch} chars={chars} md={md}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
