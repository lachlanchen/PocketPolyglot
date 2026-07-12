#!/usr/bin/env python3
"""Build exact and pocket TeX/PDF layers for technical and music books.

The pipeline has two intentionally separate source modes:

* ``mathpix`` consumes already-downloaded Mathpix whole-PDF TeX archives and
  writes new build artifacts without modifying the Mathpix cache.
* ``marker`` consumes local Marker/Surya Markdown output, generating it first
  when needed. This is used to test whether the local toolchain can approach
  Mathpix quality.

Each run writes both an exact-page review edition and a pocket-size edition:

``build/<book>-<mode>-exact-book/exact/source.tex``
``build/<book>-<mode>-exact-book/exact/<book>-<mode>-exact.pdf``
``build/<book>-<mode>-exact-book/pocket/source.tex``
``build/<book>-<mode>-exact-book/pocket/<book>-<mode>-pocket.pdf``
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compile_textbook_english_pocket import (
    apply_editable_fixes,
    find_mathpix_tex,
    resolve_image_paths,
    sanitize_mathpix_body,
    strip_mathpix_document,
)


ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
IMAGE_REF_RE = re.compile(r"(!\[[^\]]*\]\()([^)\n]+)(\))")
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
SUSPECT_RE = re.compile(
    r"\b(?:Wusic|rnusic|rnethod|teh|fascsiile|lntroduction|cornmon|rnodern)\b|"
    r"[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z]"
)


@dataclass(frozen=True)
class BookMeta:
    book_id: str
    title: str
    author: str
    source_pdf: Path | None
    cover_image: Path | None


LOCAL_FIXES: dict[str, dict[str, str]] = {
    "tom-kolb-music-theory-guitarists": {
        "Wusic notation": "Music notation",
        "rnusic": "music",
        "rnethod": "method",
        "cornmon": "common",
        "rnodern": "modern",
        "quitar speak": "guitar speak",
        "the quitar": "the guitar",
        "dvads": "dyads",
    }
}


def run(cmd: list[str], *, cwd: Path = ROOT, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def tex_path(path: Path) -> str:
    return r"\detokenize{" + rel(path) + "}"


def plan_for(book_id: str) -> dict[str, Any]:
    path = ROOT / "books" / book_id / "book-plan.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return load_json(path)


def meta_for(book_id: str) -> BookMeta:
    plan = plan_for(book_id)
    source_paths = plan.get("source_paths") or {}
    source_raw = source_paths.get("exact_source") or source_paths.get("en_primary")
    source_pdf = ROOT / source_raw if source_raw else None
    cover_image = None
    candidates: list[Path] = []
    if plan.get("cover_image"):
        candidates.append(ROOT / str(plan["cover_image"]))
    candidates.extend(
        [
            ROOT / "assets" / "covers" / book_id / "cover.png",
            ROOT / "assets" / "covers" / book_id / "background.png",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            cover_image = candidate
            break
    return BookMeta(
        book_id=book_id,
        title=str(plan.get("book_title_en") or plan.get("title_en") or book_id),
        author=str(plan.get("author") or ""),
        source_pdf=source_pdf,
        cover_image=cover_image,
    )


def output_root(book_id: str, mode: str) -> Path:
    return ROOT / "build" / f"{book_id}-{mode}-exact-book"


def copy_images(src_dir: Path, dst_dir: Path) -> dict[str, Path]:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    lookup: dict[str, Path] = {}
    for path in sorted(src_dir.glob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        target = dst_dir / path.name
        shutil.copy2(path, target)
        lookup[path.name] = target
        lookup[path.stem] = target
    return lookup


def apply_plain_fixes(book_id: str, text: str) -> str:
    for source, target in LOCAL_FIXES.get(book_id, {}).items():
        text = text.replace(source, target)
    fix_path = ROOT / "books" / book_id / "local-exact-fixes.json"
    if fix_path.exists():
        data = load_json(fix_path)
        for item in data.get("replacements", []):
            source = str(item.get("from") or "")
            target = str(item.get("to") or "")
            if not source:
                continue
            if item.get("regex"):
                text = re.sub(source, target, text, flags=re.DOTALL if item.get("dotall", True) else 0)
            else:
                text = text.replace(source, target)
    return text


def apply_tex_fixes(book_id: str, text: str) -> str:
    """Apply persistent post-Pandoc/post-Mathpix TeX repairs for one book.

    This is intentionally data-driven so the autorepair wrapper can add narrow
    fixes without editing the compiler for every one-off OCR defect.
    """

    fix_path = ROOT / "books" / book_id / "local-exact-tex-fixes.json"
    if not fix_path.exists():
        return text
    data = load_json(fix_path)
    for item in data.get("replacements", []):
        source = str(item.get("from") or "")
        target = str(item.get("to") or "")
        if not source:
            continue
        if item.get("regex"):
            flags = re.DOTALL if item.get("dotall", True) else 0
            text = re.sub(source, target, text, flags=flags)
        else:
            text = text.replace(source, target)
    return text


def strip_control_chars(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\r\t" or ord(ch) >= 32)


def rewrite_markdown_images(md: str, marker_dir: Path, image_dir: Path) -> str:
    lookup = copy_images(marker_dir, image_dir)

    def replace(match: re.Match[str]) -> str:
        prefix, raw, suffix = match.groups()
        name = raw.strip()
        path = lookup.get(Path(name).name) or lookup.get(Path(name).stem)
        if path is None:
            return match.group(0)
        return prefix + f"images/{path.name}" + suffix

    return IMAGE_REF_RE.sub(replace, md)


def normalize_latex_graphics(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        image = match.group(1).strip()
        # Keep this table-safe. A center environment inside tabular/multirow
        # cells breaks LaTeX, while a constrained includegraphics is valid both
        # in prose and inside cells.
        return rf"\includegraphics[max width=.96\linewidth,max totalheight=.66\textheight,keepaspectratio]{{{image}}}"

    return INCLUDEGRAPHICS_RE.sub(replace, body)


def absolutize_local_image_paths(body: str, body_dir: Path) -> str:
    """Make Pandoc-local ``images/foo`` paths compile from the repo root."""

    def replace(match: re.Match[str]) -> str:
        image = match.group(1).strip()
        if image.startswith("images/"):
            return rf"\includegraphics{{{rel(body_dir / image)}}}"
        return match.group(0)

    return INCLUDEGRAPHICS_RE.sub(replace, body)


def mathpix_body(book_id: str, body_dir: Path) -> Path:
    tex = find_mathpix_tex(book_id)
    if tex is None:
        raise FileNotFoundError(f"No Mathpix TeX archive is available for {book_id}")
    images_dir = body_dir / "images"
    src_images = tex.parent / "images"
    if src_images.exists():
        copy_images(src_images, images_dir)
    body = strip_mathpix_document(tex.read_text(encoding="utf-8", errors="replace"))
    body = strip_control_chars(body)
    body = resolve_image_paths(body, images_dir)
    body = sanitize_mathpix_body(body)
    body = apply_editable_fixes(book_id, body)
    body = normalize_latex_graphics(body)
    body = apply_tex_fixes(book_id, body)
    body_path = body_dir / "body.tex"
    body_path.write_text(body, encoding="utf-8")
    return body_path


def marker_output_dir(book_id: str) -> Path:
    return ROOT / "books" / book_id / "work/local-exact/marker"


def find_marker_markdown(marker_root: Path) -> Path | None:
    candidates = sorted(marker_root.glob("**/*.md"), key=lambda p: (len(p.parts), str(p)))
    return candidates[0] if candidates else None


def run_marker(book_id: str, source_pdf: Path, *, force: bool, page_range: str) -> Path:
    marker_root = marker_output_dir(book_id)
    existing = find_marker_markdown(marker_root)
    if existing and not force and not page_range:
        return existing
    if force and marker_root.exists():
        shutil.rmtree(marker_root)
    marker_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ROOT / ".venv/ocr/bin/marker_single"),
        str(source_pdf),
        "--output_dir",
        str(marker_root),
        "--output_format",
        "markdown",
        "--disable_multiprocessing",
        "--disable_tqdm",
        "--highres_image_dpi",
        "240",
    ]
    if page_range:
        cmd.extend(["--page_range", page_range])
    proc = run(cmd, check=False)
    (marker_root / "marker.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Marker failed for {book_id}; see {marker_root / 'marker.log'}")
    md = find_marker_markdown(marker_root)
    if md is None:
        raise FileNotFoundError(f"Marker produced no Markdown under {marker_root}")
    return md


def wrap_text_mode_music_commands(text: str) -> str:
    """Wrap math-only commands that local OCR sometimes emits in text cells."""

    commands = [r"\rightarrow", r"\leftarrow"]
    out: list[str] = []
    i = 0
    math_mode = False
    while i < len(text):
        pair = text[i : i + 2]
        if pair in {r"\(", r"\["}:
            math_mode = True
            out.append(pair)
            i += 2
            continue
        if pair in {r"\)", r"\]"}:
            math_mode = False
            out.append(pair)
            i += 2
            continue
        matched = False
        for command in commands:
            if text.startswith(command, i):
                out.append(command if math_mode else rf"\({command}\)")
                i += len(command)
                matched = True
                break
        if matched:
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def normalize_music_latex(body: str) -> str:
    """Repair common music-symbol OCR tokens after Markdown-to-LaTeX conversion."""

    body = body.translate(
        str.maketrans(
            {
                "А": "A",
                "В": "B",
                "С": "C",
                "Е": "E",
                "Н": "H",
                "О": "O",
                "Р": "P",
                "Х": "X",
                "Α": "A",
                "Β": "B",
                "Ε": "E",
                "Þ": "♭",
                "β": "♭",
                "а": "a",
                "в": "b",
                "с": "c",
                "е": "e",
                "о": "o",
                "р": "p",
                "х": "x",
                "þ": "♭",
                "₽": "♭",
                "‡": "#",
                "μ": "♭",
            }
        )
    )
    body = re.sub(r"([A-G])\(\^\{\}\\beta\)", r"\1\\(\\flat\\)", body)
    body = re.sub(r"([A-G])\(\^\{\}\\pe\)", r"\1\\(\\sharp\\)", body)
    body = body.replace(r"(\^{}\beta)", r"\(\flat\)")
    body = body.replace(r"(\^{}\pe)", r"\(\sharp\)")
    body = body.replace(r"( \beta )", r"\(\flat\)")
    body = re.sub(r"\(\s*\\bar\\\{b\\\}\s*\)", r"\(\\flat\)", body)
    body = re.sub(r"\\bar\\\{([0-9]+)\\\}", r"\\(\\flat \1\\)", body)
    body = body.replace(r"\$\frac{1}{2}\$", r"\(\flat\)")
    body = body.replace(r"\frac{1}{2}\$", r"\(\flat\)")
    body = body.replace(r"\$\frac{4}{4}\$", r"\(\sharp\)")
    body = body.replace(r"\frac{4}{4}\$", r"\(\sharp\)")
    body = body.replace(r"\textbackslash sqrt\{", r"\(\flat")
    body = body.replace(r"\textbackslash\$5", r"5\)")
    body = body.replace(r"\sqrt{5}", r"\(\flat5\)")
    body = body.replace(r"\sqrt{VImaj7-vii}\^{}7", r"\(\flat\)VImaj7-vii°7")
    body = re.sub(r"\\\(\\flat([IVX]+)", r"\\(\\flat\\)\1", body)
    body = body.replace(r"IIImaj75\)", r"IIImaj7\(\sharp5\)")
    body = body.replace(r"\$\display\$", r"\(\flat9\)")
    body = body.replace(r"\$\frac{\*}{9}\$7", r"\#°7")
    body = body.replace(r"\$\frac{\*}{9}\$", r"\#")
    body = body.replace(r"\$9th", r"\(\flat9\)th")
    body = body.replace(r"\$5th", r"\(\flat5\)th")
    body = body.replace(r"\$7th\$", r"\(\flat7\)")
    body = wrap_text_mode_music_commands(body)
    body = re.sub(r"(?<!\\)#", r"\\#", body)
    body = body.replace(r"\ni", "i")
    body = body.replace("quitar speak", "guitar speak")
    body = body.replace("the quitar", "the guitar")
    body = body.replace("dvads", "dyads")
    return body


LONGTABLE_RE = re.compile(r"\\begin\{longtable\}.*?\\end\{longtable\}", re.DOTALL)
CYRILLIC_RE = re.compile(r"[А-Яа-я]")


def plain_preview_from_latex(text: str, limit: int = 420) -> str:
    text = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", " ", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]+\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", text)
    text = re.sub(r"[{}\\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def sanitize_local_tables(body: str) -> str:
    """Downgrade OCR table blocks that are structurally unsafe for LaTeX.

    Local OCR often emits a readable figure image plus a speculative table.
    When that table includes malformed arrays or many tiny OCR columns, it is
    safer to keep the adjacent source image and replace the broken TeX table
    with a short audit note than to let it corrupt the whole book compile.
    """

    def replace(match: re.Match[str]) -> str:
        block = match.group(0)
        column_spec = block.split("\n", 1)[0]
        ampersands = block.count("&")
        bad = (
            r"\(\begin{array}" in block
            or r"\begin{array}" in block and "\\end{array}" not in block
            or "\\real{" in block and len(block) > 1400
            or CYRILLIC_RE.search(block) is not None
            or ampersands > 160
            or column_spec.count("l") + column_spec.count("c") + column_spec.count("r") > 14
        )
        if not bad:
            return block
        return rf"""
\begin{{center}}
\begin{{minipage}}{{0.92\linewidth}}
\small\emph{{The source figure above preserves this exercise/table.}}
\end{{minipage}}
\end{{center}}
"""

    return LONGTABLE_RE.sub(replace, body)


def marker_body(book_id: str, body_dir: Path, *, force_marker: bool, page_range: str) -> Path:
    meta = meta_for(book_id)
    if meta.source_pdf is None or not meta.source_pdf.exists():
        raise FileNotFoundError(f"source PDF missing for {book_id}: {meta.source_pdf}")
    md_path = run_marker(book_id, meta.source_pdf, force=force_marker, page_range=page_range)
    image_dir = body_dir / "images"
    md = md_path.read_text(encoding="utf-8", errors="replace")
    md = strip_control_chars(md)
    md = apply_plain_fixes(book_id, md)
    md = rewrite_markdown_images(md, md_path.parent, image_dir)
    normalized_md = body_dir / "source.md"
    normalized_md.parent.mkdir(parents=True, exist_ok=True)
    normalized_md.write_text(md, encoding="utf-8")
    body_path = body_dir / "body.tex"
    proc = run(
        [
            "pandoc",
            "--from",
            "markdown+tex_math_dollars+raw_tex",
            "--to",
            "latex",
            "--resource-path",
            str(body_dir),
            str(normalized_md),
            "-o",
            str(body_path),
        ],
        check=False,
    )
    (body_dir / "pandoc.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Pandoc failed for {book_id}; see {body_dir / 'pandoc.log'}")
    body = body_path.read_text(encoding="utf-8", errors="replace")
    body = absolutize_local_image_paths(body, body_dir)
    body = normalize_latex_graphics(body)
    body = normalize_music_latex(body)
    body = sanitize_local_tables(body)
    body = apply_tex_fixes(book_id, body)
    body_path.write_text(body, encoding="utf-8")
    return body_path


def common_preamble(meta: BookMeta, *, pocket: bool) -> str:
    geometry = (
        "paperwidth=105mm,paperheight=148mm,inner=7mm,outer=7mm,top=8mm,bottom=10mm,footskip=6mm"
        if pocket
        else "paperwidth=210mm,paperheight=297mm,inner=18mm,outer=18mm,top=18mm,bottom=20mm,footskip=10mm"
    )
    scale = (
        r"\fontsize{7.8pt}{10.1pt}\selectfont\setlength{\parindent}{0pt}\setlength{\parskip}{0.22em}\setlength{\tabcolsep}{2pt}\renewcommand{\arraystretch}{1.12}"
        if pocket
        else r"\normalsize\setlength{\parindent}{0pt}\setlength{\parskip}{0.42em}\setlength{\tabcolsep}{4pt}\renewcommand{\arraystretch}{1.12}\linespread{1.06}\selectfont"
    )
    cover_block = ""
    if meta.cover_image is not None and meta.cover_image.exists():
        cover_block = rf"""
\thispagestyle{{empty}}
\noindent\includegraphics[width=\paperwidth,height=\paperheight]{{{tex_path(meta.cover_image)}}}
\clearpage
"""
    return rf"""\documentclass[10pt,openany]{{book}}
\usepackage{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\usepackage{{xcolor}}
\usepackage{{graphicx}}
\usepackage[export]{{adjustbox}}
\usepackage{{amsmath,amsfonts,amssymb,mathtools}}
\usepackage{{yhmath}}
\usepackage{{booktabs,array,multirow,tabularx,longtable}}
\usepackage{{caption}}
\usepackage{{fvextra}}
\usepackage{{csquotes}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\usepackage{{hyperref}}
\usepackage{{float}}
\geometry{{{geometry}}}
\pagestyle{{plain}}
\raggedbottom
\setmainfont{{TeX Gyre Pagella}}
\setsansfont{{Noto Sans}}
\setmonofont{{TeX Gyre Cursor}}
\setCJKmainfont{{Noto Serif CJK SC}}
\setCJKsansfont{{Noto Sans CJK SC}}
\hypersetup{{colorlinks=true,linkcolor=black,urlcolor=black,pdftitle={{{tex_escape(meta.title)}}},pdfauthor={{{tex_escape(meta.author)}}}}}
\setcounter{{secnumdepth}}{{0}}
\renewcommand{{\contentsname}}{{Contents}}
\renewcommand{{\chaptername}}{{Chapter}}
\setkeys{{Gin}}{{max width=\linewidth,max totalheight=.70\textheight,keepaspectratio}}
\captionsetup{{font=scriptsize,skip=0.25em}}
\titleformat{{\chapter}}[block]{{\normalfont\Large\bfseries}}{{\thechapter}}{{0.55em}}{{}}
\titlespacing*{{\chapter}}{{0pt}}{{0.45em}}{{0.55em}}
\titleformat{{\section}}[block]{{\normalfont\large\bfseries}}{{\thesection}}{{0.5em}}{{}}
\titlespacing*{{\section}}{{0pt}}{{0.65em}}{{0.35em}}
\titleformat{{\subsection}}[block]{{\normalfont\normalsize\bfseries}}{{\thesubsection}}{{0.45em}}{{}}
\titlespacing*{{\subsection}}{{0pt}}{{0.45em}}{{0.25em}}
\emergencystretch=4em
\sloppy
\allowdisplaybreaks
\providecommand{{\tightlist}}{{\setlength{{\itemsep}}{{0pt}}\setlength{{\parskip}}{{0pt}}}}
\newenvironment{{Shaded}}{{}}{{}}
\newenvironment{{abstract}}{{\par\small\noindent\ignorespaces}}{{\par\normalsize}}
\providecommand{{\wideparen}}[1]{{\widehat{{#1}}}}
\newcommand{{\pandocbounded}}[1]{{#1}}
\begin{{document}}
\frontmatter
{cover_block}
\thispagestyle{{empty}}
\vspace*{{0.16\textheight}}
\begin{{center}}
{{\Large {tex_escape(meta.title)}\par}}
\vspace{{0.8em}}
{{\normalsize {tex_escape(meta.author)}\par}}
\vfill
{{\sffamily\fontsize{{6.2pt}}{{8pt}}\selectfont AgInTiFlow curated\par https://flow.lazying.art\par powered by LazyingArt\par}}
\vspace{{0.7em}}
{{\sffamily\fontsize{{5.8pt}}{{7.2pt}}\selectfont {"Pocket-size local exact TeX edition" if pocket else "Local exact TeX review edition"}.\par}}
\end{{center}}
\clearpage
% The source conversion usually preserves the book's original front matter and
% contents page. Avoid injecting a duplicate wrapper TOC, which also caused
% localized Chinese headings in technical English books.
\mainmatter
\begingroup
{scale}
"""


def write_wrapper(meta: BookMeta, body_path: Path, out_dir: Path, *, pocket: bool) -> Path:
    source = out_dir / "source.tex"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        common_preamble(meta, pocket=pocket)
        + "\n"
        + rf"\graphicspath{{{{{rel(out_dir / 'images')}/}}{{{rel(body_path.parent / 'images')}/}}}}"
        + "\n"
        + rf"\input{{{rel(body_path)}}}"
        + "\n\\endgroup\n\\end{document}\n",
        encoding="utf-8",
    )
    return source


def compile_latex(source: Path, out_dir: Path, jobname: str, *, passes: int) -> Path:
    last = ""
    for index in range(1, passes + 1):
        proc = run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-jobname",
                jobname,
                "-output-directory",
                str(out_dir),
                str(source),
            ],
            check=False,
        )
        last = proc.stdout
        (out_dir / f"compile-pass-{index}.log").write_text(last, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"XeLaTeX failed for {jobname}; see {out_dir / f'compile-pass-{index}.log'}")
    pdf = out_dir / f"{jobname}.pdf"
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    return pdf


def pdf_pages(pdf: Path) -> int | None:
    proc = run(["pdfinfo", str(pdf)], check=False)
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return None


def count_pdf_text_chars(pdf: Path) -> int:
    proc = run(["pdftotext", str(pdf), "-"], check=False)
    return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", proc.stdout))


def log_counts(out_dir: Path, jobname: str) -> dict[str, int]:
    log = out_dir / f"{jobname}.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    return {
        "overfull_hbox_count": text.count("Overfull \\hbox"),
        "underfull_hbox_count": text.count("Underfull \\hbox"),
        "missing_file_marker_count": len(re.findall(r"File `[^']+' not found|Unable to load picture", text)),
    }


def suspect_lines(body_path: Path) -> list[dict[str, Any]]:
    lines = body_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for idx, line in enumerate(lines, start=1):
        if SUSPECT_RE.search(line):
            out.append({"line": idx, "text": line[:240]})
    return out[:100]


def build(book_id: str, mode: str, *, force_marker: bool, page_range: str, passes: int) -> dict[str, Any]:
    meta = meta_for(book_id)
    root = output_root(book_id, mode)
    work_dir = root / "work"
    if mode == "mathpix":
        body = mathpix_body(book_id, work_dir)
    elif mode == "local":
        body = marker_body(book_id, work_dir, force_marker=force_marker, page_range=page_range)
    else:
        raise ValueError(mode)

    results: dict[str, Any] = {
        "book_id": book_id,
        "mode": mode,
        "title": meta.title,
        "author": meta.author,
        "source_pdf": rel(meta.source_pdf) if meta.source_pdf and meta.source_pdf.exists() else None,
        "body_tex": rel(body),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "suspect_ocr": suspect_lines(body),
    }
    for layer, pocket in [("exact", False), ("pocket", True)]:
        out_dir = root / layer
        if out_dir.exists():
            for old in out_dir.glob("*"):
                if old.is_file() and old.suffix.lower() in {".aux", ".log", ".out", ".toc", ".pdf", ".tex"}:
                    old.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)
        image_src = body.parent / "images"
        if image_src.exists():
            copy_images(image_src, out_dir / "images")
        source = write_wrapper(meta, body, out_dir, pocket=pocket)
        jobname = f"{book_id}-{mode}-{layer}"
        pdf = compile_latex(source, out_dir, jobname, passes=passes)
        layer_summary = {
            "source_tex": rel(source),
            "pdf": rel(pdf),
            "pages": pdf_pages(pdf),
            "text_chars": count_pdf_text_chars(pdf),
            "image_count": len(list((out_dir / "images").glob("*"))) if (out_dir / "images").exists() else 0,
            **log_counts(out_dir, jobname),
        }
        write_json(out_dir / "summary.json", layer_summary)
        results[layer] = layer_summary
    write_json(root / "summary.json", results)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True)
    parser.add_argument("--mode", choices=["mathpix", "local"], required=True)
    parser.add_argument("--force-marker", action="store_true")
    parser.add_argument("--page-range", default="", help="Marker page range for smoke tests, using Marker page numbering.")
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()

    summaries = []
    for book_id in args.book_id:
        summary = build(
            book_id,
            args.mode,
            force_marker=args.force_marker,
            page_range=args.page_range,
            passes=args.passes,
        )
        summaries.append(summary)
        exact = summary["exact"]
        pocket = summary["pocket"]
        print(
            f"built {book_id} mode={args.mode} "
            f"exact_pages={exact['pages']} pocket_pages={pocket['pages']} "
            f"pocket_overfull={pocket['overfull_hbox_count']} suspects={len(summary['suspect_ocr'])}",
            flush=True,
        )
    print(json.dumps({"built": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
