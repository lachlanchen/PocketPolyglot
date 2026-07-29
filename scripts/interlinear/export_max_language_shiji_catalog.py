#!/usr/bin/env python3
"""Export maximum-language large-font PocketPolyglot editions.

The script is deliberately additive:

* old build outputs are never removed or overwritten;
* new TeX/PDF builds live under ``build/<book>/maximum-language-large-font/``;
* source-repo PDF artifacts live under ``artifacts/lingualleaf/books/``;
* publishable PDFs are mirrored into ``../LinguaLeaf/docs/pocketpolyglot/books/``;
* first-page cover previews live under ``assets/max-language-previews/``.

Supported maximum-language families:

* ``wenyan-en-jp-zh`` from ``wenyan-main-quadrilingual`` source TeX;
* ``wenyan-jp-zh`` from classical three-layer source PDFs when English has not
  been backfilled yet;
* ``en-jp-zh`` from ``en-main-jp-zh`` source TeX;
* ``jp-zh`` from existing ``jp-main`` / ``zh-main`` source TeX when no richer
  trilingual or quadrilingual edition exists.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
PROFILE_DIR = "maximum-language-large-font"
LEGACY_PROFILE_DIR = "maximum-language-shiji-font"
ARTIFACT_ROOT = ROOT / "artifacts" / "lingualleaf"
LOCAL_EXPORT_ROOT = ARTIFACT_ROOT / "books"
PUBLIC_EXPORT_ROOT = ROOT.parent / "LinguaLeaf" / "docs" / "pocketpolyglot" / "books"
PREVIEW_ROOT = ROOT / "assets" / "max-language-previews"
LAZYLEARN = ROOT.parent / "LazyLearn"
LAZYLEARN_PREVIEW_ROOT = LAZYLEARN / "figs" / "pocketpolyglot"
LAZYLEARN_SITE_PREVIEW_ROOT = LAZYLEARN / "docs" / "figs" / "pocketpolyglot"
MANIFEST = ROOT / "references" / "MAX_LANGUAGE_LARGE_FONT_EXPORTS.md"
MANIFEST_JSON = ROOT / "references" / "max-language-large-font-exports.json"
GITHUB_MAX_BYTES = 95 * 1024 * 1024
COVER_ROOT = ROOT / "assets" / "covers"
BIG_BOOK_HINTS = (
    "hou-han-shu",
    "houhanshu",
    "zizhi-tongjian",
    "zizhitongjian",
    "zizhi",
)


FAMILY_PRIORITY = {
    "wenyan-en-jp-zh": 3,
    "wenyan-jp-zh": 2.5,
    "wayakana-en-jp-zh": 2.25,
    "en-jp-zh": 2,
    "jp-zh": 1,
}

JAPANESE_CLASSICAL_SOURCE_BOOKS = {
    "kokin-wakashu",
    "manyoshu",
}


@dataclass(frozen=True)
class Edition:
    book_id: str
    family: str
    edition: str
    mode: str
    source_tex: Path
    style_tex: str
    source_macro: str
    overrides: str
    original_pdf: Path | None
    strip_blackwhite: bool = False
    precompiled_pdf: Path | None = None
    output_name: str | None = None


def run(cmd: list[str], *, cwd: Path = ROOT, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "book"


def safe_filename(name: str) -> str:
    name = name.replace("/", "／").replace("\\", "＼")
    return re.sub(r"[\x00-\x1f]", "", name)


def clean_large_font_stem(stem: str) -> str:
    stem = stem.replace("・最大語種・史記字級", "")
    stem = stem.replace("・最大語種字級", "")
    stem = stem.replace("・最大語種・大字版", "")
    stem = stem.replace("・大字版", "")
    stem = stem.replace("・史記AgInTi字級", "")
    return stem.strip(" ・")


def pdfinfo(path: Path) -> dict[str, str]:
    result = run(["pdfinfo", str(path)], timeout=30)
    info: dict[str, str] = {}
    if result.returncode != 0:
        info["Status"] = "pdfinfo-failed"
        return info
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    info["Status"] = "ok"
    return info


def first_pdf(directory: Path) -> Path | None:
    pdfs = sorted(p for p in directory.glob("*.pdf") if p.is_file())
    return pdfs[0] if pdfs else None


def book_order_key(book_id: str) -> tuple[int, str]:
    normalized = book_id.lower().replace("_", "-")
    return (1 if any(hint in normalized for hint in BIG_BOOK_HINTS) else 0, normalized)


def edition_order_key(edition: Edition) -> tuple[int, str, str, str, int, str]:
    mode_rank = {"color": 0, "blackwhite": 1}
    return (
        *book_order_key(edition.book_id),
        edition.family,
        edition.edition,
        mode_rank.get(edition.mode, 9),
        edition.mode,
    )


def resolve_cover(book_id: str) -> Path | None:
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_cover = str(plan.get("cover_image") or "").strip()
            if plan_cover:
                path = Path(plan_cover)
                if not path.is_absolute():
                    path = ROOT / path
                if path.is_file():
                    return path
        except (OSError, json.JSONDecodeError):
            pass
    candidates = [COVER_ROOT / book_id]
    if book_id == "kokoro":
        candidates.append(COVER_ROOT / "kokoro-jp-main")
    for cover_dir in candidates:
        direct = cover_dir / "cover.png"
        if direct.exists():
            return direct
        for pattern in ("*cover*.png", "*cover*.jpg", "*cover*.jpeg"):
            found = sorted(path for path in cover_dir.glob(pattern) if path.is_file())
            if found:
                return found[0]
    return None


def first_page_has_image(pdf: Path) -> bool:
    try:
        reader = PdfReader(str(pdf))
        if not reader.pages:
            return False
        return bool(list(getattr(reader.pages[0], "images", []) or []))
    except Exception:
        return False


def make_cover_pdf(cover_image: Path, width: float, height: float, target: Path) -> None:
    c = canvas.Canvas(str(target), pagesize=(width, height))
    c.drawImage(
        ImageReader(str(cover_image)),
        0,
        0,
        width=width,
        height=height,
        preserveAspectRatio=False,
        anchor="c",
    )
    c.showPage()
    c.save()


def ensure_cover(pdf: Path, book_id: str, *, replace_existing: bool = True) -> bool:
    cover = resolve_cover(book_id)
    if cover is None:
        return False
    has_image_cover = first_page_has_image(pdf)
    if has_image_cover and not replace_existing:
        return False
    reader = PdfReader(str(pdf))
    if not reader.pages:
        return False
    box = reader.pages[0].mediabox
    width = float(box.width)
    height = float(box.height)
    with tempfile.TemporaryDirectory(prefix="cover-prepend-", dir=str(pdf.parent)) as tmp_name:
        tmp_dir = Path(tmp_name)
        cover_pdf = tmp_dir / "cover.pdf"
        output_pdf = tmp_dir / "output.pdf"
        make_cover_pdf(cover, width, height, cover_pdf)
        cover_reader = PdfReader(str(cover_pdf))
        writer = PdfWriter()
        writer.add_page(cover_reader.pages[0])
        start_index = 1 if has_image_cover and replace_existing else 0
        for page in reader.pages[start_index:]:
            writer.add_page(page)
        with output_pdf.open("wb") as handle:
            writer.write(handle)
        output_pdf.replace(pdf)
    return True


def quadrilingual_overrides() -> str:
    return r"""
\renewcommand{\RubyFont}{\fontsize{3.6pt}{4pt}\selectfont}
\renewcommand{\QuadMainWenyan}[1]{{\zhfont\fontsize{11.6pt}{17.2pt}\selectfont\color{BookInk}#1}}
\renewcommand{\QuadMainZhModern}[1]{{\zhfont\fontsize{11.2pt}{16.8pt}\selectfont\color{BookInk}#1}}
\renewcommand{\QuadMainJaModern}[1]{{\jpfont\fontsize{11.2pt}{16.8pt}\selectfont\color{BookInk}#1}}
\renewcommand{\QuadMainEn}[1]{{\enfont\fontsize{10.8pt}{14.2pt}\selectfont\color{BookInk}#1}}
\renewcommand{\QuadNoteWenyan}[1]{{\zhfont\fontsize{9.6pt}{12.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\QuadNoteJaModern}[1]{{\jpfont\fontsize{9.6pt}{12.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\QuadNoteZhModern}[1]{{\zhfont\fontsize{8.25pt}{10.9pt}\selectfont\color{BookNote}#1}}
\renewcommand{\QuadNoteEn}[1]{{\enfont\fontsize{8.9pt}{11.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\TinyLabel}[1]{{\sffamily\bfseries\fontsize{5.8pt}{5.8pt}\selectfont\textcolor{BookRed}{#1}}}
""".strip()


def trilingual_overrides() -> str:
    return r"""
\renewcommand{\RubyFont}{\fontsize{3.6pt}{4pt}\selectfont}
\renewcommand{\TriMainZh}[1]{{\zhfont\fontsize{11.2pt}{16.8pt}\selectfont\color{BookInk}#1}}
\renewcommand{\TriMainJa}[1]{{\jpfont\fontsize{11.2pt}{16.8pt}\selectfont\color{BookInk}#1}}
\renewcommand{\TriMainEn}[1]{{\enfont\fontsize{10.8pt}{14.2pt}\selectfont\color{BookInk}#1}}
\renewcommand{\TriCommentZh}[1]{{\zhfont\fontsize{8.25pt}{10.9pt}\selectfont\color{BookNote}#1}}
\renewcommand{\TriCommentJa}[1]{{\jpfont\fontsize{9.6pt}{12.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\TriCommentEn}[1]{{\enfont\fontsize{8.9pt}{11.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\TinyLabel}[1]{{\sffamily\bfseries\fontsize{5.8pt}{5.8pt}\selectfont\textcolor{BookRed}{#1}}}
""".strip()


def bilingual_zh_overrides() -> str:
    return r"""
\renewcommand{\RubyFont}{\fontsize{3.6pt}{4pt}\selectfont}
\renewcommand{\ZHMain}[1]{{\zhfont\fontsize{11.6pt}{17.2pt}\selectfont\color{BookInk}#1}}
\renewcommand{\JAGloss}[1]{{\jpfont\fontsize{9.6pt}{12.7pt}\selectfont\color{BookNote}#1}}
\renewcommand{\JAExplain}[1]{{\jpfont\addfontfeatures{FakeSlant=0.08}\fontsize{8.25pt}{10.9pt}\selectfont\color{BookNote}#1}}
\renewcommand{\JAExplainLabel}{{\jpfont\bfseries\fontsize{5.8pt}{7pt}\selectfont\textcolor{BookRed}{解}}}
\renewcommand{\TinyLabel}[1]{{\sffamily\bfseries\fontsize{5.8pt}{5.8pt}\selectfont\textcolor{BookRed}{#1}}}
""".strip()


def bilingual_jp_overrides() -> str:
    return r"""
\renewcommand{\RubyFont}{\fontsize{3.6pt}{4pt}\selectfont}
\renewcommand{\JPMainText}[1]{{\jpfont\fontsize{11.6pt}{17.2pt}\selectfont\color{BookInk}#1}}
\renewcommand{\JPGlossText}[1]{\JPMainText{#1}}
\renewcommand{\JPCommentText}[1]{{\jpfont\addfontfeatures{FakeSlant=0.08}\fontsize{9pt}{12pt}\selectfont\color{BookNote}#1}}
\renewcommand{\ZHCommentText}[1]{{\zhfont\fontsize{8.25pt}{10.9pt}\selectfont\color{BookNote}#1}}
\renewcommand{\JPCommentLabel}{{\jpfont\bfseries\fontsize{5.8pt}{7pt}\selectfont\textcolor{BookRed}{解}}}
\renewcommand{\TinyLabel}[1]{{\sffamily\bfseries\fontsize{5.8pt}{5.8pt}\selectfont\textcolor{BookRed}{#1}}}
""".strip()


def candidate_for(book_dir: Path, rel_edition: str, family: str, style: str, macro: str, overrides: str) -> list[Edition]:
    out: list[Edition] = []
    for mode in ("color", "blackwhite"):
        large_font_pdf = first_pdf(book_dir / rel_edition / "large-font" / mode)
        if large_font_pdf is not None:
            out.append(
                Edition(
                    book_id=book_dir.name,
                    family=family,
                    edition=rel_edition,
                    mode=mode,
                    source_tex=large_font_pdf,
                    style_tex="",
                    source_macro="",
                    overrides="",
                    original_pdf=large_font_pdf,
                    precompiled_pdf=large_font_pdf,
                    output_name=large_font_pdf.name,
                )
            )
            continue
        source = book_dir / rel_edition / mode / "source.tex"
        if not source.exists():
            continue
        out.append(
            Edition(
                book_id=book_dir.name,
                family=family,
                edition=rel_edition,
                mode=mode,
                source_tex=source,
                style_tex=style,
                source_macro=macro,
                overrides=overrides,
                original_pdf=first_pdf(source.parent),
            )
        )
    if not any(item.mode == "color" for item in out):
        blackwhite_source = book_dir / rel_edition / "blackwhite" / "source.tex"
        if blackwhite_source.exists():
            out.append(
                Edition(
                    book_id=book_dir.name,
                    family=family,
                    edition=rel_edition,
                    mode="color",
                    source_tex=blackwhite_source,
                    style_tex=style,
                    source_macro=macro,
                    overrides=overrides,
                    original_pdf=first_pdf(blackwhite_source.parent),
                    strip_blackwhite=True,
                )
            )
    return out


def discover_editions() -> list[Edition]:
    editions: list[Edition] = []
    for book_dir in sorted(p for p in BUILD.iterdir() if p.is_dir()):
        if book_dir.name in {"books", "interlinear-block", "interlinear-jp-main", "interlinear-run"}:
            continue
        if book_dir.name == "sanguozhi-pei-zhu":
            continue
        family_editions: list[Edition] = []
        family_editions.extend(
            candidate_for(
                book_dir,
                "wenyan-main-quadrilingual",
                "wenyan-en-jp-zh",
                "tex/interlinear-quadrilingual/style.tex",
                "QuadSource",
                quadrilingual_overrides(),
            )
        )
        if book_dir.name in JAPANESE_CLASSICAL_SOURCE_BOOKS:
            family_editions.extend(
                candidate_for(
                    book_dir,
                    "wayakana-main-en-zh",
                    "wayakana-en-jp-zh",
                    "tex/interlinear-trilingual-pair/style.tex",
                    "TriSourceNotesSource",
                    trilingual_overrides(),
                )
            )
        else:
            family_editions.extend(
                candidate_for(
                    book_dir,
                    "en-main-jp-zh",
                    "en-jp-zh",
                    "tex/interlinear-trilingual-pair/style.tex",
                    "TriAllSource",
                    trilingual_overrides(),
                )
            )
        if not family_editions:
            family_editions.extend(
                candidate_for(
                    book_dir,
                    "jp-main",
                    "jp-zh",
                    "tex/interlinear-jp-main/style.tex",
                    "JpMainSource",
                    bilingual_jp_overrides(),
                )
            )
            family_editions.extend(
                candidate_for(
                    book_dir,
                    "zh-main",
                    "jp-zh",
                    "tex/interlinear-block/style.tex",
                    "InterlinearSource",
                    bilingual_zh_overrides(),
                )
            )
        if not family_editions:
            continue
        best = max(FAMILY_PRIORITY[item.family] for item in family_editions)
        editions.extend(item for item in family_editions if FAMILY_PRIORITY[item.family] == best)
    editions.extend(discover_precompiled_quadrilingual_editions())
    editions.extend(discover_precompiled_three_layer_editions())
    return editions


def discover_precompiled_quadrilingual_editions() -> list[Edition]:
    """Discover completed quadrilingual PDFs that should be exported as-is."""

    out: list[Edition] = []
    specs = {
        "sanguozhi-pei-zhu": {
            "color": (
                BUILD
                / "sanguozhi-pei-zhu"
                / "wenyan-main-quadrilingual"
                / "large-font"
                / "color"
                / "三國志裴松之注（英文・現代日本語・現代中文注）・大字版.pdf",
                "三國志裴松之注（英文・現代日本語・現代中文注）・最大語種・大字版.pdf",
            ),
            "blackwhite": (
                BUILD
                / "sanguozhi-pei-zhu"
                / "wenyan-main-quadrilingual"
                / "large-font"
                / "blackwhite"
                / "三國志裴松之注（英文・現代日本語・現代中文注・黑白）・大字版.pdf",
                "三國志裴松之注（英文・現代日本語・現代中文注・黑白）・最大語種・大字版.pdf",
            ),
        }
    }
    for book_id, modes in specs.items():
        for mode, (pdf, name) in modes.items():
            if not pdf.exists():
                continue
            out.append(
                Edition(
                    book_id=book_id,
                    family="wenyan-en-jp-zh",
                    edition="wenyan-main-quadrilingual",
                    mode=mode,
                    source_tex=pdf,
                    style_tex="",
                    source_macro="",
                    overrides="",
                    original_pdf=pdf,
                    precompiled_pdf=pdf,
                    output_name=name,
                )
            )
    return out


def discover_precompiled_three_layer_editions() -> list[Edition]:
    """Discover completed classical three-layer PDFs without an English layer.

    Shiji was generated by the AgInTi three-layer pipeline before the later
    quadrilingual renderer existed. Treat it as a maximum-language export with
    the languages it genuinely has: wenyan, modern Japanese, and modern Chinese.
    """

    out: list[Edition] = []
    specs = {
        "color": (
            BUILD / "shiji-aginti" / "zh-main" / "color" / "book.pdf",
            "史記（現代日本語・現代中文注）・最大語種・大字版.pdf",
        ),
        "blackwhite": (
            BUILD / "shiji-aginti" / "zh-main" / "blackwhite" / "book.pdf",
            "史記（現代日本語・現代中文注・黑白）・最大語種・大字版.pdf",
        ),
    }
    for mode, (pdf, name) in specs.items():
        if not pdf.exists():
            continue
        out.append(
            Edition(
                book_id="shiji-aginti",
                family="wenyan-jp-zh",
                edition="wenyan-main-jp-zh",
                mode=mode,
                source_tex=pdf,
                style_tex="",
                source_macro="",
                overrides="",
                original_pdf=pdf,
                precompiled_pdf=pdf,
                output_name=name,
            )
        )
    return out


def write_wrapper(edition: Edition, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    local_source = out_dir / "source.tex"
    if edition.strip_blackwhite:
        source_text = edition.source_tex.read_text(encoding="utf-8")
        source_text = re.sub(r"(?m)^\\BlackWhiteMode\s*\n", "", source_text, count=1)
        local_source.write_text(source_text, encoding="utf-8")
    else:
        shutil.copy2(edition.source_tex, local_source)
    wrapper = out_dir / "book.tex"
    source_arg = local_source.relative_to(ROOT).as_posix()
    wrapper.write_text(
        "\n".join(
            [
                r"\documentclass[UTF8,fontset=none,10pt,openany]{ctexbook}",
                rf"\input{{{edition.style_tex}}}",
                "",
                "% Large-font profile. Generated wrapper; source text is reused unchanged.",
                edition.overrides,
                "",
                r"\begin{document}",
                rf"\def\{edition.source_macro}{{{source_arg}}}",
                rf"\input{{\{edition.source_macro}}}",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return wrapper


def output_pdf_name(edition: Edition) -> str:
    if edition.output_name:
        stem = Path(edition.output_name).stem
        return safe_filename(f"{clean_large_font_stem(stem)}・最大語種・大字版.pdf")
    if edition.original_pdf:
        stem = edition.original_pdf.stem
    else:
        stem = f"{edition.book_id}-{edition.family}-{edition.edition.replace('/', '-')}-{edition.mode}"
    stem = clean_large_font_stem(stem)
    if edition.strip_blackwhite:
        stem = stem.replace("・黑白", "").replace("黑白", "")
        stem = re.sub(r"(?i)[・ _-]*(?:black[-_ ]?white|blackwhite|bw)\b", "", stem)
        stem = stem.replace("・）", "）").replace("（・", "（")
        stem = re.sub(r"[（(]\s*[）)]", "", stem)
        stem = stem.strip("・ _-")
    return safe_filename(f"{stem}・最大語種・大字版.pdf")


def compile_edition(edition: Edition, *, force: bool = False) -> Path:
    out_dir = BUILD / edition.book_id / PROFILE_DIR / edition.edition / edition.mode
    pdf_path = out_dir / output_pdf_name(edition)
    if pdf_path.exists() and not force:
        return pdf_path
    if edition.precompiled_pdf:
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(edition.precompiled_pdf, pdf_path)
        ensure_cover(pdf_path, edition.book_id)
        return pdf_path
    wrapper = write_wrapper(edition, out_dir)
    for pattern in ("book.aux", "book.log", "book.out", "book.toc", "book.pdf"):
        try:
            (out_dir / pattern).unlink()
        except FileNotFoundError:
            pass
    for pass_number in (1, 2):
        log = out_dir / f"xelatex-pass{pass_number}.log"
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                [
                    "xelatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-jobname=book",
                    f"-output-directory={out_dir}",
                    str(wrapper),
                ],
                cwd=ROOT,
                text=True,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        if result.returncode != 0:
            raise RuntimeError(f"XeLaTeX failed for {edition.book_id} {edition.edition} {edition.mode}; see {log}")
    generated = out_dir / "book.pdf"
    if not generated.exists():
        raise RuntimeError(f"XeLaTeX did not create {generated}")
    generated.replace(pdf_path)
    ensure_cover(pdf_path, edition.book_id)
    return pdf_path


def compress_pdf(source: Path, public_pdf: Path, local_pdf: Path) -> tuple[Path, str]:
    local_pdf.parent.mkdir(parents=True, exist_ok=True)
    tmp = local_pdf.with_suffix(".tmp.pdf")
    cmd = [
        "gs",
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        "-dPDFSETTINGS=/ebook",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dColorImageResolution=180",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dGrayImageResolution=180",
        "-dMonoImageResolution=300",
        f"-sOutputFile={tmp}",
        str(source),
    ]
    result = run(cmd, timeout=None)
    if result.returncode != 0 or not tmp.exists():
        shutil.copy2(source, local_pdf)
        return local_pdf, "compression-failed-copied-original"
    if tmp.stat().st_size > source.stat().st_size:
        tmp.unlink(missing_ok=True)
        shutil.copy2(source, local_pdf)
        status = "compressed-larger-copied-original"
    else:
        tmp.replace(local_pdf)
        status = "compressed"
    if local_pdf.stat().st_size <= GITHUB_MAX_BYTES:
        public_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_pdf, public_pdf)
        return public_pdf, status
    public_pdf.unlink(missing_ok=True)
    return local_pdf, status + "-local-only-oversize"


def extract_preview(pdf: Path, preview: Path) -> None:
    preview.parent.mkdir(parents=True, exist_ok=True)
    tmp_prefix = preview.with_suffix("")
    run(["pdftoppm", "-png", "-f", "1", "-singlefile", "-r", "130", str(pdf), str(tmp_prefix)], timeout=120)
    produced = tmp_prefix.with_suffix(".png")
    if not produced.exists():
        return
    produced.replace(preview)
    quant = run(["pngquant", "--force", "--skip-if-larger", "--output", str(preview), "96", str(preview)], timeout=120)
    if quant.returncode not in {0, 98, 99}:
        pass


def bytes_mib(value: int) -> str:
    return f"{value / 1024 / 1024:.1f}"


def markdown_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Preview | Book | Family | Color PDF | Black-white PDF |",
        "| --- | --- | --- | --- | --- |",
    ]
    by_book: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_book.setdefault(str(row["book_id"]), []).append(row)
    for book_id, items in sorted(by_book.items(), key=lambda item: book_order_key(item[0])):
        color = next((item for item in items if item["mode"] == "color" and item.get("tracked_pdf")), None)
        bw = next((item for item in items if item["mode"] == "blackwhite" and item.get("tracked_pdf")), None)
        any_item = color or bw or items[0]
        preview = any_item.get("preview") or ""
        preview_md = f'<img src="{preview}" width="120" alt="{book_id} cover preview">' if preview else ""
        color_md = f"[color]({color['tracked_pdf']})" if color else "local only"
        bw_md = f"[black-white]({bw['tracked_pdf']})" if bw else "local only"
        lines.append(f"| {preview_md} | `{book_id}` | `{any_item['family']}` | {color_md} | {bw_md} |")
    return "\n".join(lines)


def html_gallery(rows: list[dict[str, object]]) -> str:
    by_book: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_book.setdefault(str(row["book_id"]), []).append(row)
    cards: list[str] = [
        '<section class="published-books pocket-polyglot-showcase pocketpolyglot-showcase" id="pocketpolyglot">',
        '  <div class="section-header">',
        "    <h2>PocketPolyglot Maximum-Language Editions</h2>",
        "    <p>",
        "      Pocket-size interlinear readers with the richest available language layers:",
        "      JP-ZH, EN-JP-ZH, and classical WENYAN-EN-JP-ZH editions.",
        "      Each card links to compressed color and black-white PDFs.",
        "    </p>",
        "  </div>",
        '  <div class="pocketpolyglot-grid">',
    ]
    for book_id, items in sorted(by_book.items(), key=lambda item: book_order_key(item[0])):
        color = next((item for item in items if item["mode"] == "color" and item.get("tracked_pdf")), None)
        bw = next((item for item in items if item["mode"] == "blackwhite" and item.get("tracked_pdf")), None)
        any_item = color or bw or items[0]
        preview_name = Path(str(any_item.get("preview", ""))).name
        preview = f"figs/pocketpolyglot/{preview_name}" if preview_name else ""
        title = escape(book_id.replace("-", " ").title())
        family = escape(str(any_item["family"]))
        cards.extend(
            [
                '    <article class="pocketpolyglot-card">',
                f'      <img src="{escape(preview)}" alt="{title} first-page preview" loading="lazy" />',
                '      <div class="pocketpolyglot-card-body">',
                f"        <p>{family}</p>",
                f"        <h3>{title}</h3>",
                '        <div class="hero-actions">',
            ]
        )
        if color:
            cards.append(
                '          <a class="primary" '
                f'href="https://github.com/lachlanchen/LinguaLeaf/blob/main/{escape(str(color["tracked_pdf"]))}" '
                'target="_blank" rel="noopener">Color PDF</a>'
            )
        if bw:
            cards.append(
                '          <a class="secondary" '
                f'href="https://github.com/lachlanchen/LinguaLeaf/blob/main/{escape(str(bw["tracked_pdf"]))}" '
                'target="_blank" rel="noopener">Black-white PDF</a>'
            )
        cards.extend(
            [
                "        </div>",
                "      </div>",
                "    </article>",
            ]
        )
    cards.extend(["  </div>", "</section>"])
    return "\n".join(cards)


def replace_section(path: Path, title: str, body: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    start_marker = f"<!-- {title}:START -->"
    end_marker = f"<!-- {title}:END -->"
    section = f"{start_marker}\n{body.rstrip()}\n{end_marker}"
    if start_marker in text and end_marker in text:
        text = re.sub(re.escape(start_marker) + r".*?" + re.escape(end_marker), section, text, flags=re.S)
    else:
        insert_after = "\n## One Sentence In Full Width\n" if path.name == "README.md" and path.parent == ROOT else "\n## Featured Books\n"
        if insert_after in text:
            text = text.replace(insert_after, "\n" + section + "\n" + insert_after, 1)
        elif path.name == "index.html" and 'id="pocketpolyglot"' in text:
            text = re.sub(
                r'\n\s*<section class="[^"]*pocket-polyglot-showcase[^"]*" id="pocketpolyglot">.*?\n\s*</section>',
                "\n\n" + section,
                text,
                count=1,
                flags=re.S,
            )
        elif path.name == "index.html" and "</header>" in text:
            text = text.replace("</header>", "</header>\n\n" + section, 1)
        else:
            text += "\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8")


def render_report(rows: list[dict[str, object]], skipped: list[str]) -> str:
    pushed = sum(1 for row in rows if row.get("tracked_pdf"))
    local = len(rows)
    lines = [
        "# Maximum-Language Large-Font Exports",
        "",
        "This catalog is generated from local build outputs. It selects the richest available language family per book:",
        "",
        "- `wenyan-en-jp-zh` for classical text editions;",
        "- `wenyan-jp-zh` for classical text editions whose English backfill is not complete yet;",
        "- `en-jp-zh` for trilingual modern editions;",
        "- `jp-zh` for bilingual editions where no English layer exists.",
        "",
        "All compiled editions use the larger PocketPolyglot font profile. Existing source PDFs and JSON are not modified.",
        "",
        f"- Local compressed/exported PDFs: {local}",
        f"- GitHub-tracked PDFs under size cap: {pushed}",
        f"- Skipped source folders: {len(skipped)}",
        "",
        "## Gallery",
        "",
        markdown_table(rows),
        "",
        "## Inventory",
        "",
        "| Book | Family | Edition | Mode | Pages | Source MiB | Export MiB | GitHub | Local PDF |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['book_id']}` | `{row['family']}` | `{row['edition']}` | `{row['mode']}` | "
            f"{row.get('pages') or '-'} | {row['source_mib']} | {row['export_mib']} | "
            f"{'yes' if row.get('tracked_pdf') else 'no'} | `{row['local_pdf']}` |"
        )
    if skipped:
        lines.extend(["", "## Skipped", ""])
        lines.extend(f"- {item}" for item in skipped)
    return "\n".join(lines).rstrip() + "\n"


def sort_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    mode_rank = {"color": 0, "blackwhite": 1}
    return sorted(
        rows,
        key=lambda row: (
            *book_order_key(str(row.get("book_id", ""))),
            str(row.get("family", "")),
            str(row.get("edition", "")),
            mode_rank.get(str(row.get("mode", "")), 9),
            str(row.get("mode", "")),
        ),
    )


def merge_scoped_catalog(
    rows: list[dict[str, object]],
    skipped: list[str],
    wanted_books: set[str],
) -> tuple[list[dict[str, object]], list[str]]:
    if not wanted_books or not MANIFEST_JSON.exists():
        return sort_rows(rows), skipped
    try:
        existing = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sort_rows(rows), skipped

    kept_rows = [
        row
        for row in existing.get("rows", [])
        if str(row.get("book_id", "")) not in wanted_books
    ]
    kept_skipped = [
        item
        for item in existing.get("skipped", [])
        if not any(str(item).startswith(f"{book_id} ") for book_id in wanted_books)
    ]
    return sort_rows([*kept_rows, *rows]), [*kept_skipped, *skipped]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-compile", action="store_true")
    parser.add_argument("--force-compress", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--book", action="append", default=[])
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--no-readme", action="store_true")
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()

    editions = discover_editions()
    editions = sorted(editions, key=edition_order_key)
    if args.book:
        wanted = set(args.book)
        editions = [edition for edition in editions if edition.book_id in wanted]
    if args.limit:
        editions = editions[: args.limit]

    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    for index, edition in enumerate(editions, start=1):
        print(f"[{index}/{len(editions)}] {edition.book_id} {edition.edition} {edition.mode}", flush=True)
        try:
            if args.no_compile:
                build_pdf = (
                    edition.precompiled_pdf
                    or first_pdf(BUILD / edition.book_id / PROFILE_DIR / edition.edition / edition.mode)
                    or first_pdf(BUILD / edition.book_id / LEGACY_PROFILE_DIR / edition.edition / edition.mode)
                )
                if not build_pdf:
                    skipped.append(f"{edition.book_id} {edition.edition} {edition.mode}: no compiled PDF")
                    continue
            else:
                build_pdf = compile_edition(edition, force=args.force_compile)
            ensure_cover(build_pdf, edition.book_id)
            info = pdfinfo(build_pdf)
            export_name = output_pdf_name(edition)
            local_pdf = LOCAL_EXPORT_ROOT / edition.family / edition.book_id / edition.edition / edition.mode / export_name
            public_pdf = PUBLIC_EXPORT_ROOT / edition.family / edition.book_id / edition.edition / edition.mode / export_name
            if args.no_compress:
                local_pdf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(build_pdf, local_pdf)
                if local_pdf.stat().st_size <= GITHUB_MAX_BYTES:
                    public_pdf.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local_pdf, public_pdf)
                    exported = public_pdf
                else:
                    exported = local_pdf
                compress_status = "not-compressed"
            elif local_pdf.exists() and not args.force_compress:
                exported = public_pdf if public_pdf.exists() else local_pdf
                compress_status = "existing"
            else:
                exported, compress_status = compress_pdf(build_pdf, public_pdf, local_pdf)
            tracked_pdf = exported if exported.is_relative_to(PUBLIC_EXPORT_ROOT) else None
            preview_rel = ""
            if not args.no_preview and edition.mode == "color":
                preview = PREVIEW_ROOT / f"{edition.book_id}.png"
                extract_preview(build_pdf, preview)
                if preview.exists():
                    preview_rel = preview.relative_to(ROOT).as_posix()
                    LAZYLEARN_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview, LAZYLEARN_PREVIEW_ROOT / preview.name)
                    LAZYLEARN_SITE_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview, LAZYLEARN_SITE_PREVIEW_ROOT / preview.name)
            elif edition.mode == "color":
                preview = PREVIEW_ROOT / f"{edition.book_id}.png"
                if preview.exists():
                    preview_rel = preview.relative_to(ROOT).as_posix()
                    LAZYLEARN_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview, LAZYLEARN_PREVIEW_ROOT / preview.name)
                    LAZYLEARN_SITE_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview, LAZYLEARN_SITE_PREVIEW_ROOT / preview.name)
            rows.append(
                {
                    "book_id": edition.book_id,
                    "family": edition.family,
                    "edition": edition.edition,
                    "mode": edition.mode,
                    "source_pdf": build_pdf.relative_to(ROOT).as_posix(),
                    "source_mib": bytes_mib(build_pdf.stat().st_size),
                    "export_pdf": exported.relative_to(ROOT).as_posix() if exported.is_relative_to(ROOT) else str(exported),
                    "export_mib": bytes_mib(exported.stat().st_size),
                    "local_pdf": local_pdf.relative_to(ROOT).as_posix(),
                    "tracked_pdf": tracked_pdf.relative_to(ROOT.parent / "LinguaLeaf").as_posix() if tracked_pdf else "",
                    "preview": preview_rel,
                    "pages": info.get("Pages"),
                    "status": info.get("Status"),
                    "compress_status": compress_status,
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep the batch moving.
            skipped.append(f"{edition.book_id} {edition.edition} {edition.mode}: {exc}")
            print(f"WARNING: {skipped[-1]}", file=sys.stderr, flush=True)

    manifest_rows = rows
    manifest_skipped = skipped
    if args.book and not args.limit:
        manifest_rows, manifest_skipped = merge_scoped_catalog(rows, skipped, set(args.book))

    if not args.no_manifest:
        MANIFEST_JSON.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_JSON.write_text(
            json.dumps({"rows": manifest_rows, "skipped": manifest_skipped}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        MANIFEST.write_text(render_report(manifest_rows, manifest_skipped), encoding="utf-8")

    if not args.no_readme:
        section = "\n".join(
            [
                "## Maximum-Language Pocket Editions",
                "",
                "These are the richest available local editions for each completed book, rebuilt with a larger font profile and compressed for GitHub when the result stays under normal GitHub file limits.",
                "",
                markdown_table(
                    [
                        {
                            **row,
                            "tracked_pdf": f"https://github.com/lachlanchen/LinguaLeaf/blob/main/{row['tracked_pdf']}" if row.get("tracked_pdf") else "",
                        }
                        for row in manifest_rows
                    ]
                ),
                "",
                f"Full local manifest: [{MANIFEST.relative_to(ROOT).as_posix()}]({MANIFEST.relative_to(ROOT).as_posix()}).",
            ]
        )
        replace_section(ROOT / "README.md", "POCKETPOLYGLOT_MAX_LANGUAGE", section)
        lazy_section = "\n".join(
            [
                "## PocketPolyglot Maximum-Language Editions",
                "",
                "PocketPolyglot/LinguaLeaf builds pocket-size interlinear readers with ruby, pinyin, grammar coloring, and maximum available language layers.",
                "",
                markdown_table(
                    [
                        {
                            **row,
                            "preview": f"figs/pocketpolyglot/{Path(str(row.get('preview', ''))).name}" if row.get("preview") else "",
                            "tracked_pdf": f"https://github.com/lachlanchen/LinguaLeaf/blob/main/{row['tracked_pdf']}" if row.get("tracked_pdf") else "",
                        }
                        for row in manifest_rows
                    ]
                ),
                "",
                "PDF repository: [lachlanchen/LinguaLeaf](https://github.com/lachlanchen/LinguaLeaf) · Source repository: [lachlanchen/PocketPolyglot](https://github.com/lachlanchen/PocketPolyglot)",
            ]
        )
        replace_section(LAZYLEARN / "README.md", "POCKETPOLYGLOT_MAX_LANGUAGE", lazy_section)
        replace_section(LAZYLEARN / "docs" / "index.html", "POCKETPOLYGLOT_MAX_LANGUAGE", html_gallery(manifest_rows))

    print(MANIFEST.relative_to(ROOT))
    print(f"rows={len(manifest_rows)} skipped={len(manifest_skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
