#!/usr/bin/env python3
"""Refresh LingualLeaf/PocketPolyglot catalog docs from uploaded PDFs.

This script is intentionally documentation-only. It scans the PDF artifact
repository, syncs preview images, and rewrites the catalog blocks in:

* PocketPolyglot README.md
* LingualLeaf README.md
* LazyLearn README.md
* LazyLearn docs/index.html

It does not compile or compress PDFs.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
LEAF = ROOT.parent / "LingualLeaf"
LAZYLEARN = ROOT.parent / "LazyLearn"
PDF_ROOT = LEAF / "docs" / "pocketpolyglot" / "books"
LOCAL_PREVIEW_ROOT = ROOT / "assets" / "max-language-previews"
LEAF_PREVIEW_ROOT = LEAF / "assets" / "max-language-previews"
LAZYLEARN_PREVIEW_ROOT = LAZYLEARN / "figs" / "pocketpolyglot"
LAZYLEARN_SITE_PREVIEW_ROOT = LAZYLEARN / "docs" / "figs" / "pocketpolyglot"

GITHUB_BLOB_BASE = "https://github.com/lachlanchen/LingualLeaf/blob/main/"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/lachlanchen/LingualLeaf/main/"
LAZYLEARN_READER_BASE = "https://learn.lazying.art/pdf-reader.html"

FAMILY_ORDER = {
    "en-jp-zh": 1,
    "jp-zh": 2,
    "wenyan-en-jp-zh": 3,
    "wenyan-jp-zh": 4,
}

EDITION_LABELS = {
    "en-main-jp-zh": "English main · 日本語 · 中文",
    "jp-main": "日本語 main · 中文",
    "zh-main": "中文 main · 日本語",
    "wenyan-main-quadrilingual": "文言文 main · English · 日本語 · 中文",
    "wenyan-main-jp-zh": "文言文 main · 日本語 · 中文",
}


@dataclass(frozen=True)
class CatalogRow:
    family: str
    book_id: str
    edition: str
    title: str
    color_rel: str
    bw_rel: str


def sync_previews() -> None:
    for target in (LEAF_PREVIEW_ROOT, LAZYLEARN_PREVIEW_ROOT, LAZYLEARN_SITE_PREVIEW_ROOT):
        target.mkdir(parents=True, exist_ok=True)
    for preview in sorted(LOCAL_PREVIEW_ROOT.glob("*.png")):
        shutil.copy2(preview, LEAF_PREVIEW_ROOT / preview.name)
        shutil.copy2(preview, LAZYLEARN_PREVIEW_ROOT / preview.name)
        shutil.copy2(preview, LAZYLEARN_SITE_PREVIEW_ROOT / preview.name)


def clean_title(stem: str) -> str:
    stem = stem.replace("・最大語種・史記字級", "")
    stem = stem.replace("・黑白", "")
    stem = stem.replace("・最大語種・大字版", "")
    stem = stem.replace("・大字版", "")
    stem = stem.replace("（黑白）", "")
    return stem.strip()


def scan_rows() -> list[CatalogRow]:
    grouped: dict[tuple[str, str, str], dict[str, str]] = {}
    for pdf in sorted(PDF_ROOT.rglob("*.pdf")):
        rel = pdf.relative_to(LEAF).as_posix()
        parts = rel.split("/")
        if len(parts) < 8:
            continue
        family, book_id, edition, mode = parts[3], parts[4], parts[5], parts[6]
        if mode not in {"color", "blackwhite"}:
            continue
        grouped.setdefault((family, book_id, edition), {})[mode] = rel

    rows: list[CatalogRow] = []
    for (family, book_id, edition), modes in grouped.items():
        color_rel = modes.get("color", "")
        bw_rel = modes.get("blackwhite", "")
        sample_rel = color_rel or bw_rel
        title = clean_title(Path(sample_rel).stem) if sample_rel else book_id
        rows.append(CatalogRow(family, book_id, edition, title, color_rel, bw_rel))
    rows.sort(key=lambda row: (FAMILY_ORDER.get(row.family, 99), row.book_id, row.edition))
    return rows


def url_for(rel: str, *, raw: bool = False) -> str:
    base = GITHUB_RAW_BASE if raw else GITHUB_BLOB_BASE
    return base + quote(rel, safe="/")


def reader_url(rel: str, title: str, *, absolute: bool = False) -> str:
    base = LAZYLEARN_READER_BASE if absolute else "pdf-reader.html"
    return f"{base}?path={quote(rel, safe='/')}&title={quote(title, safe='')}"


def preview_path(book_id: str, prefix: str) -> str:
    name = f"{book_id}.png"
    if not (LOCAL_PREVIEW_ROOT / name).exists() and not (LEAF_PREVIEW_ROOT / name).exists():
        return ""
    return f"{prefix}/{name}"


def markdown_table(rows: list[CatalogRow], *, preview_prefix: str, link_mode: str) -> str:
    lines = [
        "| Preview | Book | Edition | Color | Black-white |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        preview = preview_path(row.book_id, preview_prefix)
        preview_md = f'<img src="{preview}" width="120" alt="{row.book_id} preview">' if preview else ""
        edition = EDITION_LABELS.get(row.edition, row.edition)
        if link_mode == "relative":
            color = f"[Read]({quote(row.color_rel, safe='/()（）・.:-_')})" if row.color_rel else "-"
            bw = f"[Read]({quote(row.bw_rel, safe='/()（）・.:-_')})" if row.bw_rel else "-"
        elif link_mode == "reader":
            color = f"[Read]({reader_url(row.color_rel, row.title, absolute=True)})" if row.color_rel else "-"
            bw = f"[Read]({reader_url(row.bw_rel, row.title + ' black-white', absolute=True)})" if row.bw_rel else "-"
        else:
            color = f"[PDF]({url_for(row.color_rel)})" if row.color_rel else "-"
            bw = f"[PDF]({url_for(row.bw_rel)})" if row.bw_rel else "-"
        lines.append(f"| {preview_md} | `{row.book_id}` | {edition} | {color} | {bw} |")
    return "\n".join(lines)


def html_gallery(rows: list[CatalogRow]) -> str:
    cards = [
        '<section class="published-books pocket-polyglot-showcase pocketpolyglot-showcase" id="pocketpolyglot">',
        '  <div class="section-header">',
        "    <h2>PocketPolyglot Maximum-Language Editions</h2>",
        "    <p>",
        "      Pocket-size interlinear readers with JP-ZH, EN-JP-ZH, and classical-language editions.",
        "      PDFs are rendered in-browser with PDF.js from GitHub raw URLs.",
        "    </p>",
        "  </div>",
        '  <div class="pocketpolyglot-grid">',
    ]
    for row in rows:
        preview = preview_path(row.book_id, "figs/pocketpolyglot")
        title = html.escape(row.title)
        edition = html.escape(EDITION_LABELS.get(row.edition, row.edition))
        cards.extend(
            [
                '    <article class="pocketpolyglot-card">',
                f'      <img src="{html.escape(preview)}" alt="{title} first-page preview" loading="lazy" />',
                '      <div class="pocketpolyglot-card-body">',
                f"        <p>{html.escape(row.family)} · {edition}</p>",
                f"        <h3>{title}</h3>",
                '        <div class="hero-actions">',
            ]
        )
        if row.color_rel:
            cards.append(
                '          <a class="primary" '
                f'href="{html.escape(reader_url(row.color_rel, row.title))}" '
                'target="_blank" rel="noopener">Read color</a>'
            )
        if row.bw_rel:
            cards.append(
                '          <a class="secondary" '
                f'href="{html.escape(reader_url(row.bw_rel, row.title + " black-white"))}" '
                'target="_blank" rel="noopener">Read black-white</a>'
            )
        cards.extend(["        </div>", "      </div>", "    </article>"])
    cards.extend(["  </div>", "</section>"])
    return "\n".join(cards)


def replace_section(path: Path, marker: str, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    replacement = f"{start}\n{body.rstrip()}\n{end}"
    if start not in text or end not in text:
        raise RuntimeError(f"missing marker block in {path}")
    text = re.sub(re.escape(start) + r".*?" + re.escape(end), replacement, text, flags=re.S)
    path.write_text(text, encoding="utf-8")


def update_lingualleaf_intro(rows: list[CatalogRow]) -> None:
    path = LEAF / "README.md"
    text = path.read_text(encoding="utf-8")
    pdf_count = len([rel for row in rows for rel in (row.color_rel, row.bw_rel) if rel])
    preview_count = len(list(LEAF_PREVIEW_ROOT.glob("*.png")))
    families = ", ".join(f"`{item}`" for item in sorted({row.family for row in rows}, key=lambda x: FAMILY_ORDER.get(x, 99)))
    text = re.sub(r"- \d+ compressed final PDFs under `docs/pocketpolyglot/books/`\.", f"- {pdf_count} compressed final PDFs under `docs/pocketpolyglot/books/`.", text)
    text = re.sub(r"- \d+ first-page preview images under `assets/max-language-previews/`\.", f"- {preview_count} first-page preview images under `assets/max-language-previews/`.", text)
    text = re.sub(r"- Maximum available language families: .*?\.", f"- Maximum available language families: {families}.", text)
    path.write_text(text, encoding="utf-8")


def build_sections(rows: list[CatalogRow]) -> None:
    leaf_section = "\n".join(
        [
            "## Maximum-Language Pocket Editions",
            "",
            "These are the richest available local editions for each completed book. The PDF files are stored in this artifact repository; source text, JSON, TeX, and scripts stay in PocketPolyglot.",
            "",
            markdown_table(rows, preview_prefix="assets/max-language-previews", link_mode="relative"),
            "",
            "Source/tooling repository: [lachlanchen/PocketPolyglot](https://github.com/lachlanchen/PocketPolyglot).",
        ]
    )
    replace_section(LEAF / "README.md", "POCKETPOLYGLOT_MAX_LANGUAGE", leaf_section)
    update_lingualleaf_intro(rows)

    pocket_section = "\n".join(
        [
            "## Maximum-Language Pocket Editions",
            "",
            "The final compressed PDFs live in [lachlanchen/LingualLeaf](https://github.com/lachlanchen/LingualLeaf). The links below point to the uploaded PDF artifacts while this repository keeps the source text, JSON, TeX, scripts, and generation workflow.",
            "",
            markdown_table(rows, preview_prefix="assets/max-language-previews", link_mode="blob"),
            "",
            "Website reader: [learn.lazying.art](https://learn.lazying.art).",
        ]
    )
    replace_section(ROOT / "README.md", "POCKETPOLYGLOT_MAX_LANGUAGE", pocket_section)

    lazy_section = "\n".join(
        [
            "## PocketPolyglot Maximum-Language Editions",
            "",
            "PocketPolyglot/LinguaLeaf builds pocket-size interlinear readers with ruby, pinyin, grammar coloring, and maximum available language layers.",
            "",
            "The `Read` links open the LazyLearn PDF.js reader with PDFs streamed from GitHub raw URLs.",
            "",
            markdown_table(rows, preview_prefix="figs/pocketpolyglot", link_mode="reader"),
            "",
            "PDF repository: [lachlanchen/LingualLeaf](https://github.com/lachlanchen/LingualLeaf) · Source repository: [lachlanchen/PocketPolyglot](https://github.com/lachlanchen/PocketPolyglot)",
        ]
    )
    replace_section(LAZYLEARN / "README.md", "POCKETPOLYGLOT_MAX_LANGUAGE", lazy_section)
    replace_section(LAZYLEARN / "docs" / "index.html", "POCKETPOLYGLOT_MAX_LANGUAGE", html_gallery(rows))


def main() -> int:
    sync_previews()
    rows = scan_rows()
    if not rows:
        raise RuntimeError(f"no PDFs found under {PDF_ROOT}")
    build_sections(rows)
    pdf_count = len([rel for row in rows for rel in (row.color_rel, row.bw_rel) if rel])
    print(f"rows={len(rows)} pdfs={pdf_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
