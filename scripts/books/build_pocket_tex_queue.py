#!/usr/bin/env python3
"""Build real-TeX exact and pocket PDFs from the build-pocket queue.

This runner is deliberately conservative: a successful book must have a real
TeX body and PDFs compiled from that body. If local extraction cannot produce a
credible TeX path, the book is marked blocked with evidence instead of emitting
an image-only placeholder.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "build-pocket/tasks/source-queue-2026-07-12.json"
DEFAULT_HEADER = ROOT / "build-pocket/_common/pandoc-pocket-header.tex"

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MARKDOWN_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)\n]+)(\))")
OVERFULL_RE = re.compile(r"Overfull \\hbox \(([-0-9.]+)pt too wide\)")
OVERFULL_HOTSPOT_RE = re.compile(
    r"Overfull \\hbox \(([-0-9.]+)pt too wide\)"
    r"(?: in paragraph at lines (\d+)(?:--(\d+))?| detected at line (\d+))"
)
LATEX_ERROR_RE = re.compile(r"^! |Fatal error|Emergency stop|Undefined control sequence", re.M)
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?(\{[^}]+\})")
LONGTABLE_SPEC_RE = re.compile(r"(\\begin\{longtable\}(?:\[[^\]]*\])?\{)([^{}]*(?:@\{\}[^{}]*)?)(\})")
SIMPLE_LONGTABLE_SPEC_RE = re.compile(
    r"(\\begin\{longtable\}(?:\[[^\]]*\])?\{@\{\})([lcrX]{2,})(@\{\}\})"
)
DISPLAY_MATH_RE = re.compile(r"\\\[(.*?)\\\]", re.S)
ADJUSTBOX_DISPLAY_MATH_RE = re.compile(
    r"\\begin\{adjustbox\}\{max width=\\linewidth\}\s*"
    r"\\begin\{minipage\}\{\\linewidth\}\s*"
    r"\\\[(.*?)\\\]\s*"
    r"\\end\{minipage\}\s*"
    r"\\end\{adjustbox\}",
    re.S,
)
SERVER_UNSAFE_FILENAME_CHARS = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "／",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)


def log(message: str) -> None:
    print(message, flush=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_name(name: str) -> str:
    safe = name.translate(SERVER_UNSAFE_FILENAME_CHARS)
    safe = re.sub(r"[\x00-\x1f\x7f]", "", safe)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe.rstrip(" .") or "untitled"


def run_stream(cmd: list[str], *, cwd: Path = ROOT, log_file: Path | None = None) -> int:
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / '.local/bin'}:{env.get('PATH', '')}"
    with subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    ) as proc:
        handle = log_file.open("a", encoding="utf-8") if log_file else None
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if handle:
                    handle.write(line)
        finally:
            if handle:
                handle.close()
        return proc.wait()


def run_capture(cmd: list[str], *, cwd: Path = ROOT, check: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / '.local/bin'}:{env.get('PATH', '')}"
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout)
    return result


def env_int(name: str, default: int = 0) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def ensure_header() -> Path:
    DEFAULT_HEADER.parent.mkdir(parents=True, exist_ok=True)
    header = (
        r"""
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{graphicx}
\usepackage[export]{adjustbox}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{float}
\usepackage{caption}
\usepackage{needspace}
\setmainfont{TeX Gyre Pagella}
\setsansfont{TeX Gyre Heros}
\setmonofont{DejaVu Sans Mono}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{}
\setlength{\parindent}{1.2em}
\setlength{\parskip}{0.22em}
\emergencystretch=3em
\sloppy
\pagestyle{plain}
\captionsetup{font=small,labelfont=bf}
\makeatletter
\def\maxwidth{\ifdim\Gin@nat@width>\linewidth\linewidth\else\Gin@nat@width\fi}
\def\maxheight{\ifdim\Gin@nat@height>.72\textheight .72\textheight\else\Gin@nat@height\fi}
\renewcommand{\@pnumwidth}{3.2em}
\renewcommand{\@tocrmarg}{3.8em}
\makeatother
\setkeys{Gin}{width=\maxwidth,height=\maxheight,keepaspectratio}
""".strip()
        + "\n"
    )
    if not DEFAULT_HEADER.exists() or DEFAULT_HEADER.read_text(encoding="utf-8", errors="replace") != header:
        DEFAULT_HEADER.write_text(header, encoding="utf-8")
    return DEFAULT_HEADER


def clean_text(text: str) -> str:
    return CONTROL_RE.sub("", text).replace("\ufeff", "").replace("\ufffd", "")


KNOWN_LATEX_COMMANDS = {
    "PassOptionsToPackage",
    "RequirePackage",
    "IfFileExists",
    "documentclass",
    "LaTeX",
    "XeLaTeX",
    "TeX",
    "XeTeX",
    "usepackage",
    "ifPDFTeX",
    "else",
    "fi",
    "ifLuaTeX",
    "ifXeTeX",
    "setmainfont",
    "setsansfont",
    "setmonofont",
    "newcommand",
    "renewcommand",
    "providecommand",
    "DeclareUnicodeCharacter",
    "makeatletter",
    "makeatother",
    "def",
    "let",
    "setkeys",
    "begin",
    "end",
    "frontmatter",
    "mainmatter",
    "backmatter",
    "maketitle",
    "tableofcontents",
    "part",
    "chapter",
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
    "label",
    "hypertarget",
    "texorpdfstring",
    "hyperdef",
    "phantomsection",
    "addcontentsline",
    "bookmarksetup",
    "includegraphics",
    "caption",
    "footnote",
    "href",
    "url",
    "emph",
    "textbf",
    "textit",
    "textsc",
    "texttt",
    "textsuperscript",
    "textsubscript",
    "textgreater",
    "textless",
    "textbar",
    "textbackslash",
    "textasciicircum",
    "textasciitilde",
    "ldots",
    "dots",
    "qquad",
    "quad",
    "hspace",
    "vspace",
    "noindent",
    "par",
    "smallskip",
    "medskip",
    "bigskip",
    "centering",
    "raggedright",
    "raggedleft",
    "arraybackslash",
    "linewidth",
    "textheight",
    "columnwidth",
    "real",
    "begingroup",
    "endgroup",
    "small",
    "footnotesize",
    "scriptsize",
    "normalsize",
    "setlength",
    "setcounter",
    "arabic",
    "deflabelenumi",
    "labelenumi",
    "labelenumii",
    "labelenumiii",
    "labelenumiv",
    "tabcolsep",
    "toprule",
    "midrule",
    "bottomrule",
    "endhead",
    "tightlist",
    "item",
    "sloppy",
    "emergencystretch",
    "pagestyle",
    "captionsetup",
    "maxwidth",
    "maxheight",
    "Gin",
    "ifdim",
    "else",
    "fi",
    "nat",
    "width",
    "height",
    "mathbb",
    "mathbf",
    "mathrm",
    "mathit",
    "mathcal",
    "frac",
    "sqrt",
    "sum",
    "prod",
    "int",
    "lim",
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "varepsilon",
    "theta",
    "lambda",
    "mu",
    "pi",
    "sigma",
    "phi",
    "varphi",
    "omega",
    "infty",
    "partial",
    "nabla",
    "times",
    "cdot",
    "leq",
    "geq",
    "neq",
    "approx",
    "left",
    "right",
}


MALFORMED_SUP_RE = re.compile(r"\\\(<sup>\^\{\\</sup>rm\s*([^}]+)\}\\,?\\\)")
MALFORMED_SUP_SIMPLE_RE = re.compile(r"\\\(<sup>\^?\{?\s*([^<>{}]+?)\s*\}?</sup>\\\)")
MALFORMED_SUP_RM_RE = re.compile(r"\\\(<sup>\^\{\\?</sup>rm\s*([^}]+?)\}\\\)")
MALFORMED_SUP_COMMAND_RE = re.compile(
    r"\\\(<sup>\\</sup>(dagger|ast)\\,\s*mathrm\{([^}]+)\}\\\)"
)
ESCAPED_SUP_RE = re.compile(r"\\&lt;sup\\textgreater\s*([A-Za-z0-9]+)")
HTML_SUP_RE = re.compile(r"<sup>\s*([A-Za-z0-9]+)\s*</sup>")
LATEX_WORD_COMMAND_RE = re.compile(r"\\([A-Za-z]{2,})(?![A-Za-z])")
WORD_BACKSLASH_ARTIFACT_RE = re.compile(
    r"(?<=[^\W\d_])\\"
    r"(?!(?:arraybackslash|allowbreak|linewidth|textheight|columnwidth|"
    r"textgreater|textless|textasciicircum|textasciitilde|textbackslash)\b)"
    r"(?=[^\W\d_])"
)


def normalize_malformed_superscripts(text: str) -> str:
    symbols = {"dagger": "†", "ast": "*"}
    text = MALFORMED_SUP_COMMAND_RE.sub(
        lambda match: rf"\textsuperscript{{{symbols[match.group(1)]}}} {match.group(2)}",
        text,
    )
    text = MALFORMED_SUP_RE.sub(lambda match: rf"\textsuperscript{{{match.group(1).strip()}}}", text)
    text = MALFORMED_SUP_RM_RE.sub(lambda match: rf"\textsuperscript{{{match.group(1).strip()}}}", text)
    text = MALFORMED_SUP_SIMPLE_RE.sub(lambda match: rf"\textsuperscript{{{match.group(1).strip()}}}", text)
    text = ESCAPED_SUP_RE.sub(lambda match: rf"\textsuperscript{{{match.group(1).strip()}}}", text)
    text = HTML_SUP_RE.sub(lambda match: rf"\textsuperscript{{{match.group(1).strip()}}}", text)
    text = text.replace(r"\&lt;/sup\textgreater", "")
    text = text.replace(r"\&lt;sup\textgreater", "")
    return text


def strip_unknown_text_commands(text: str) -> str:
    """Strip OCR-created word commands in already-isolated document text."""

    def repl(match: re.Match[str]) -> str:
        command = match.group(1)
        if command in KNOWN_LATEX_COMMANDS:
            return match.group(0)
        if len(command) >= 2:
            return command
        return match.group(0)

    return LATEX_WORD_COMMAND_RE.sub(repl, text)


def repair_body_backslash_artifacts(text: str) -> str:
    text = text.replace(
        r">{raggedrightarraybackslash}",
        r">{\raggedright\arraybackslash}",
    )
    text = re.sub(r"(?m)^hypersetup\{", r"\\hypersetup{", text)
    text = re.sub(r"(?m)^setstretch\{", r"\\setstretch{", text)
    text = re.sub(r"\\Vi\s+thin\b", "Within", text)
    text = WORD_BACKSLASH_ARTIFACT_RE.sub("", text)
    text = re.sub(r"(?<=[^\W\d_])\?\\(?=[^\W\d_])", "", text)
    text = re.sub(r"(?<=[,;:.!?])\\(?=[a-z])", " ", text)
    for enum_label in ("labelenumi", "labelenumii", "labelenumiii", "labelenumiv"):
        text = text.replace("\\" + "def" + enum_label, "\\" + "def\\" + enum_label)
    text = re.sub(r"\bincludesemph\{", r"includes \\emph{", text)
    return strip_unknown_text_commands(text)


def remove_text_backslash_artifacts(text: str) -> str:
    r"""Repair OCR backslashes inside ordinary words.

    Local PDF extraction sometimes turns a letter into a stray backslash inside a
    word, for example ``sla\es``. That must not become a TeX command. The rule is
    deliberately narrow so real commands such as ``\alpha`` and ``\section`` are
    left alone.
    """

    text = normalize_malformed_superscripts(text)
    marker = r"\begin{document}"
    if marker in text:
        before, after = text.split(marker, 1)
        return before + marker + repair_body_backslash_artifacts(after)
    return repair_body_backslash_artifacts(text)


def normalize_longtable_spec(spec: str) -> str:
    """Convert unwrapped Pandoc table columns to paragraph columns.

    EPUB/PDF-derived tables often arrive as ``llll`` columns. That preserves
    semantics but cannot wrap on a pocket page. Convert simple column specs to
    equal-width paragraph columns while preserving outer ``@{}`` suppressors.
    """

    body = spec.replace("@{}", "")
    cols = re.findall(r"[lcrX]", body)
    if len(cols) < 2:
        return spec
    width = max(0.10, min(0.44, 0.92 / len(cols)))
    wrapped = "".join([rf"p{{{width:.3f}\linewidth}}" for _ in cols])
    prefix = "@{}" if spec.startswith("@{}") else ""
    suffix = "@{}" if spec.endswith("@{}") else ""
    return prefix + wrapped + suffix


def normalize_simple_longtable_specs(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        count = len(match.group(2))
        width = max(0.08, min(0.44, 0.92 / count))
        columns = "".join(rf"p{{{width:.3f}\linewidth}}" for _ in range(count))
        return match.group(1) + columns + match.group(3)

    return SIMPLE_LONGTABLE_SPEC_RE.sub(repl, text)


def remove_source_contents_block(text: str) -> str:
    """Remove OCR/Pandoc-extracted printed contents when Pandoc creates a TOC."""

    marker = r"\hypertarget{contents}{%"
    start = text.find(marker)
    if start < 0:
        return text
    window = text[start : start + 100000]
    if "Contents" not in window or r"\begin{longtable}" not in window:
        return text
    # Only accept a nearby structural boundary. Searching the entire remaining
    # document can delete real front matter and early chapters when OCR assigns
    # those headings unexpected identifiers.
    next_match = re.search(
        r"\n\\hypertarget\{(?:maps|tables|preface(?:-[a-z0-9-]+)?|part-|chapter-|section-|[a-z0-9-]+chapter)\}\{%",
        window[1:],
    )
    if not next_match:
        return text
    end = start + 1 + next_match.start()
    return text[:start] + "\n% Removed source-extracted printed Contents block; Pandoc TOC is used instead.\n" + text[end:]


def display_math_scale_factor(body: str) -> float:
    compact_len = len(re.sub(r"\s+", "", body))
    if compact_len < 130:
        return 1.55
    if compact_len < 220:
        return 2.20
    if compact_len < 340:
        return 2.90
    return 3.60


def scaled_display_math(body: str) -> str:
    body = body.strip()
    factor = display_math_scale_factor(body)
    return (
        "\n\\begin{center}\n"
        "\\begin{adjustbox}{max width=\\linewidth}\n"
        f"\\begin{{minipage}}{{{factor:.2f}\\linewidth}}\n"
        "\\[\n"
        + body
        + "\n\\]\n"
        "\\end{minipage}\n"
        "\\end{adjustbox}\n"
        "\\end{center}\n"
    )


def wrap_wide_display_math(text: str, *, layout: str) -> str:
    """Constrain long display equations to pocket page width."""

    if layout != "pocket":
        return text
    text = ADJUSTBOX_DISPLAY_MATH_RE.sub(lambda match: scaled_display_math(match.group(1)), text)

    def repl(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        compact = re.sub(r"\s+", "", body)
        if len(compact) < 55 and not any(token in body for token in [r"\begin{split}", r"\begin{aligned}", r"\tag{"]):
            return match.group(0)
        return scaled_display_math(body)

    return DISPLAY_MATH_RE.sub(repl, text)


def postprocess_tex(tex_path: Path, *, layout: str) -> None:
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    text = clean_text(text)
    text = remove_text_backslash_artifacts(text)
    text = remove_source_contents_block(text)
    text = INCLUDEGRAPHICS_RE.sub(
        r"\\includegraphics[max width=.94\\linewidth,max totalheight=.70\\textheight,keepaspectratio]\1",
        text,
    )
    text = LONGTABLE_SPEC_RE.sub(
        lambda match: match.group(1) + normalize_longtable_spec(match.group(2)) + match.group(3),
        text,
    )
    text = normalize_simple_longtable_specs(text)
    if layout == "pocket":
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
        )
    else:
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\small\setlength{\tabcolsep}{3pt}\begin{longtable}",
        )
    text = text.replace(r"\end{longtable}", r"\end{longtable}\endgroup")
    text = wrap_wide_display_math(text, layout=layout)
    tex_path.write_text(text, encoding="utf-8")


def rewrite_markdown_image_paths(markdown: str, base: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix, raw, suffix = match.groups()
        target = raw.strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("/"):
            return match.group(0)
        path = (base / target).resolve()
        return f"{prefix}{path}{suffix}"

    return MARKDOWN_IMAGE_RE.sub(repl, markdown)


def pdftotext_to_markdown(source: Path, task_dir: Path) -> Path:
    """Fallback real-text extraction when Marker cannot finish a large PDF.

    This deliberately produces Markdown/TeX, not page images. It is less rich
    than Marker because figures and tables may need later manual recovery, but
    it keeps the exact workflow on a real text path instead of blocking on OOM.
    """

    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext is not available for real-text fallback")
    review_dir = task_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    log_file = review_dir / "pdftotext.log"
    result = run_capture(["pdftotext", "-layout", "-enc", "UTF-8", str(source), "-"], check=False)
    log_file.write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"pdftotext failed with exit code {result.returncode}; see {log_file}")
    text = clean_text(result.stdout)
    text = re.sub(r"\n\s*\f\s*\n", "\n\n", text)
    pages = [page.strip() for page in text.split("\f") if page.strip()]
    paragraphs: list[str] = []
    for page in pages:
        page = re.sub(r"[ \t]+$", "", page, flags=re.M)
        page = re.sub(r"\n{3,}", "\n\n", page)
        paragraphs.append(page)
    markdown = "\n\n".join(paragraphs).strip() + "\n"
    prepared = review_dir / "source-from-pdftotext.md"
    prepared.write_text(markdown, encoding="utf-8")
    if len(re.sub(r"\s+", "", markdown)) < 500:
        raise RuntimeError(f"pdftotext output too short to trust: {prepared}")
    log(f"[fallback] {source.relative_to(ROOT)} -> {prepared.relative_to(ROOT)} using pdftotext real text")
    return prepared


def marker_pdf_to_markdown(source: Path, task_dir: Path, *, force: bool) -> Path:
    marker_root = task_dir / "work/marker"
    marker_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(marker_root.glob("**/*.md"))
    if existing and not force:
        return existing[0]

    extraction_mode = os.environ.get("POCKET_PDF_EXTRACTION", "").strip().lower()
    if extraction_mode in {"pdftotext", "text"} or os.environ.get("POCKET_SKIP_MARKER") == "1":
        return pdftotext_to_markdown(source, task_dir)

    if shutil.which("marker_single", path=f"{Path.home() / '.local/bin'}:{os.environ.get('PATH', '')}") is None:
        raise RuntimeError("marker_single is not available; cannot run local PDF-to-TeX extraction")

    log_file = task_dir / "review/marker.log"
    if log_file.exists():
        log_file.unlink()
    cmd = [
        "marker_single",
        str(source),
        "--output_dir",
        str(marker_root),
        "--output_format",
        "markdown",
        "--disable_multiprocessing",
    ]
    marker_timeout_seconds = env_int("POCKET_MARKER_TIMEOUT_SECONDS", 0)
    if marker_timeout_seconds > 0 and shutil.which("timeout") is not None:
        cmd = ["timeout", f"{marker_timeout_seconds}s", *cmd]
    code = run_stream(cmd, log_file=log_file)
    if code != 0:
        log(f"[warn] marker_single failed with exit code {code}; trying pdftotext real-text fallback")
        return pdftotext_to_markdown(source, task_dir)

    candidates = sorted(marker_root.glob("**/*.md"), key=lambda path: path.stat().st_size, reverse=True)
    if not candidates:
        raise RuntimeError(f"marker_single produced no Markdown under {marker_root}")
    raw_md = candidates[0]
    text = clean_text(raw_md.read_text(encoding="utf-8", errors="replace"))
    text = rewrite_markdown_image_paths(text, raw_md.parent)
    prepared = task_dir / "review/source-from-marker.md"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(text, encoding="utf-8")
    if len(re.sub(r"\s+", "", text)) < 500:
        raise RuntimeError(f"marker output too short to trust: {prepared}")
    return prepared


def latex_escape_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "<": r"\textless{}",
        ">": r"\textgreater{}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def looks_like_plain_heading(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact or len(compact) > 120:
        return False
    if re.match(r"^(part|chapter|book)\s+([ivxlcdm]+|\d+)\b", compact, re.I):
        return True
    letters = re.sub(r"[^A-Za-z]", "", compact)
    if len(letters) >= 8 and compact.upper() == compact and not compact.endswith("."):
        return True
    return False


def plain_text_markdown_to_tex(
    source: Path,
    tex_path: Path,
    *,
    title: str,
    author: str,
    layout: str,
) -> None:
    """Build standalone TeX directly from pdftotext output.

    This path is for very large PDFs where Marker/Pandoc can consume tens of GB.
    It keeps a real text TeX body and intentionally avoids page-image facsimiles.
    """

    raw = clean_text(source.read_text(encoding="utf-8", errors="replace"))
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n\s*\f\s*\n", "\n\n", raw)
    raw = re.sub(r"[ \t]+$", "", raw, flags=re.M)
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", raw) if block.strip()]
    if len("".join(blocks)) < 500:
        raise RuntimeError(f"pdftotext source too short to build TeX: {source}")

    header = ensure_header().read_text(encoding="utf-8")
    if layout == "exact":
        geometry = "paperwidth=148mm,paperheight=210mm,inner=14mm,outer=12mm,top=14mm,bottom=16mm"
        line_stretch = "1.08"
    elif layout == "pocket":
        geometry = "paperwidth=105mm,paperheight=148mm,inner=6.5mm,outer=5.5mm,top=8mm,bottom=9mm"
        line_stretch = "1.12"
    else:
        raise ValueError(layout)

    body_lines: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        joined = re.sub(r"\s+", " ", " ".join(lines)).strip()
        joined = re.sub(r"([A-Za-z])-\s+([a-z])", r"\1\2", joined)
        if not joined:
            continue
        escaped = latex_escape_text(joined)
        if looks_like_plain_heading(joined):
            heading = escaped[:180]
            body_lines.append(rf"\chapter*{{{heading}}}")
            body_lines.append(rf"\addcontentsline{{toc}}{{chapter}}{{{heading}}}")
        elif joined.startswith(("http://", "https://")):
            body_lines.append(rf"\noindent \url{{{joined}}}\par")
        else:
            body_lines.append(escaped + "\n\n")

    tex = (
        "\\documentclass[oneside,10pt]{book}\n"
        f"\\usepackage[{geometry}]{{geometry}}\n"
        "\\usepackage[hidelinks]{hyperref}\n"
        "\\usepackage{xurl}\n"
        + header
        + f"\\linespread{{{line_stretch}}}\\selectfont\n"
        + f"\\title{{{latex_escape_text(title)}}}\n"
        + f"\\author{{{latex_escape_text(author)}}}\n"
        "\\date{}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\tableofcontents\n"
        "\\mainmatter\n"
        + "\n".join(body_lines)
        + "\n\\end{document}\n"
    )
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(tex, encoding="utf-8")
    postprocess_tex(tex_path, layout=layout)


def repair_epub_for_pandoc(source: Path, task_dir: Path, *, force: bool) -> Path:
    """Create a Pandoc-friendly EPUB copy without parent-relative manifest hrefs."""

    repaired = task_dir / "work/repaired-for-pandoc.epub"
    if repaired.exists() and not force:
        return repaired

    with zipfile.ZipFile(source) as zin:
        names = set(zin.namelist())
        container = zin.read("META-INF/container.xml")
        root = ET.fromstring(container)
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            return source
        opf_path = rootfile.attrib.get("full-path", "")
        if not opf_path or opf_path not in names:
            return source
        opf_dir = posixpath.dirname(opf_path)
        opf_text = zin.read(opf_path).decode("utf-8", errors="replace")
        extra_entries: dict[str, bytes] = {}

        def href_repl(match: re.Match[str]) -> str:
            href = match.group(1)
            if not href.startswith("../"):
                return match.group(0)
            normalized = posixpath.normpath(posixpath.join(opf_dir, href))
            if normalized not in names:
                return match.group(0)
            clean_name = posixpath.basename(normalized)
            target = posixpath.join(opf_dir, clean_name) if opf_dir else clean_name
            extra_entries[target] = zin.read(normalized)
            return f'href="{clean_name}"'

        fixed_opf = re.sub(r'href="([^"]+)"', href_repl, opf_text)
        if fixed_opf == opf_text and not extra_entries:
            return source

        repaired.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(repaired, "w") as zout:
            if "mimetype" in names:
                zout.writestr("mimetype", zin.read("mimetype"), compress_type=zipfile.ZIP_STORED)
            for info in zin.infolist():
                if info.filename == "mimetype":
                    continue
                data = fixed_opf.encode("utf-8") if info.filename == opf_path else zin.read(info.filename)
                zout.writestr(info, data)
            for name, data in extra_entries.items():
                if name not in names:
                    zout.writestr(name, data)
    log(f"[repair] {source.relative_to(ROOT)} -> {repaired.relative_to(ROOT)} for Pandoc EPUB paths")
    return repaired


def extract_mobi_to_source(source: Path, task_dir: Path, *, force: bool) -> tuple[Path, str]:
    """Extract MOBI/AZW3 to a real EPUB or HTML source using KindleUnpack."""

    extract_root = task_dir / "work/mobi-extract"
    marker = extract_root / ".source.json"
    if marker.exists() and not force:
        data = read_json(marker)
        candidate = ROOT / data["path"]
        if candidate.exists():
            return candidate, data["format"]
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    try:
        from mobi.extract import extract as mobi_extract
    except Exception as exc:  # pragma: no cover - depends on local optional tool
        raise RuntimeError("Python mobi/KindleUnpack is not available for real MOBI extraction") from exc

    temp_dir, extracted = mobi_extract(str(source))
    temp_path = Path(temp_dir)
    extracted_path = Path(extracted)
    shutil.copytree(temp_path, extract_root, dirs_exist_ok=True)
    local_extracted = extract_root / extracted_path.relative_to(temp_path)
    if local_extracted.suffix.lower() == ".epub":
        source_format = "epub"
    elif local_extracted.suffix.lower() in {".html", ".htm"}:
        source_format = "html"
    elif local_extracted.suffix.lower() == ".pdf":
        raise RuntimeError("MOBI extraction yielded PDF only; refusing page-image-only fallback")
    else:
        raise RuntimeError(f"MOBI extraction yielded unsupported source: {local_extracted}")
    write_json(marker, {"path": str(local_extracted.relative_to(ROOT)), "format": source_format})
    shutil.rmtree(temp_path, ignore_errors=True)
    log(f"[extract] {source.relative_to(ROOT)} -> {local_extracted.relative_to(ROOT)}")
    return local_extracted, source_format


def pandoc_layout_args(layout: str) -> list[str]:
    common = [
        "-V",
        "documentclass=book",
        "-V",
        "classoption=oneside",
        "-V",
        "colorlinks=true",
        "-V",
        "linkcolor=blue",
        "-V",
        "urlcolor=blue",
    ]
    if layout == "exact":
        return common + [
            "-V",
            "fontsize=10pt",
            "-V",
            "geometry:paperwidth=148mm",
            "-V",
            "geometry:paperheight=210mm",
            "-V",
            "geometry:inner=14mm",
            "-V",
            "geometry:outer=12mm",
            "-V",
            "geometry:top=14mm",
            "-V",
            "geometry:bottom=16mm",
            "-V",
            "linestretch=1.08",
        ]
    if layout == "pocket":
        return common + [
            "-V",
            "fontsize=10pt",
            "-V",
            "geometry:paperwidth=105mm",
            "-V",
            "geometry:paperheight=148mm",
            "-V",
            "geometry:inner=6.5mm",
            "-V",
            "geometry:outer=5.5mm",
            "-V",
            "geometry:top=8mm",
            "-V",
            "geometry:bottom=9mm",
            "-V",
            "linestretch=1.12",
        ]
    raise ValueError(layout)


def pandoc_to_tex(
    source: Path,
    tex_path: Path,
    *,
    title: str,
    author: str,
    layout: str,
    source_format: str,
) -> None:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    header = ensure_header()
    figures_dir = tex_path.parents[1] / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        str(source),
        "--standalone",
        "--toc",
        "--top-level-division=chapter",
        "--wrap=preserve",
        "--metadata",
        f"title={title}",
        "--metadata",
        f"author={author}",
        "--include-in-header",
        str(header),
        "--extract-media",
        str(figures_dir),
        "--resource-path",
        f"{source.parent}:{ROOT}",
        "-o",
        str(tex_path),
    ]
    if source_format == "markdown":
        cmd[1:1] = ["--from", "markdown+tex_math_dollars+tex_math_single_backslash+raw_tex"]
    elif source_format == "html":
        cmd[1:1] = ["--from", "html"]
    cmd.extend(pandoc_layout_args(layout))
    result = run_capture(cmd)
    if result.returncode:
        (tex_path.parent / "pandoc.log").write_text(result.stdout, encoding="utf-8")
        raise RuntimeError(f"pandoc failed for {source}; see {tex_path.parent / 'pandoc.log'}")
    postprocess_tex(tex_path, layout=layout)


def repair_undefined_word_command(tex_path: Path, log_file: Path) -> bool:
    """Repair one OCR-created backslash-in-word after a concrete XeLaTeX error."""

    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    if "Undefined control sequence" not in log_text:
        return False
    matches = list(re.finditer(r"\nl\.(\d+)\s", log_text))
    if matches:
        line_no = int(matches[-1].group(1))
    else:
        path_pattern = re.escape(str(tex_path))
        matches = list(re.finditer(rf"{path_pattern}:(\d+): Undefined control sequence\.", log_text))
        if not matches:
            return False
        line_no = int(matches[-1].group(1))
    lines = tex_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if line_no < 1 or line_no > len(lines):
        return False
    begin_document_line = next(
        (index + 1 for index, line in enumerate(lines) if r"\begin{document}" in line),
        None,
    )
    if begin_document_line is not None and line_no < begin_document_line:
        return False
    old = lines[line_no - 1]
    new = remove_text_backslash_artifacts(old)
    if new == old:
        return False
    lines[line_no - 1] = new
    tex_path.write_text("".join(lines), encoding="utf-8")
    display_path = tex_path.resolve()
    try:
        display_path = display_path.relative_to(ROOT)
    except ValueError:
        pass
    log(f"[repair] {display_path}:{line_no} removed OCR backslash artifact")
    return True


def compile_tex(tex_path: Path, out_pdf: Path) -> dict[str, Any]:
    build_dir = tex_path.parent / "latex-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".aux", ".toc", ".out", ".log", ".lof", ".lot"):
        stale = build_dir / f"{tex_path.stem}{suffix}"
        if stale.exists():
            stale.unlink()
    log_file = build_dir / "xelatex.log"
    if log_file.exists():
        log_file.unlink()
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-output-directory",
        str(build_dir),
        str(tex_path),
    ]
    passes = 0
    attempts = 0
    while passes < 2 and attempts < 6:
        attempts += 1
        code = run_stream(cmd, log_file=log_file)
        if code != 0:
            if repair_undefined_word_command(tex_path, log_file):
                continue
            raise RuntimeError(f"xelatex failed for {tex_path}; see {log_file}")
        passes += 1
    if passes < 2:
        raise RuntimeError(f"xelatex did not finish two clean passes for {tex_path}; see {log_file}")
    produced = build_dir / f"{tex_path.stem}.pdf"
    if not produced.exists():
        raise RuntimeError(f"xelatex did not produce {produced}")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(produced, out_pdf)
    return validate_pdf(out_pdf, build_dir / f"{tex_path.stem}.log", tex_path)


def pdf_info(pdf: Path) -> dict[str, str]:
    result = run_capture(["pdfinfo", str(pdf)])
    info: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return info


def pdf_text_chars(pdf: Path) -> int:
    result = run_capture(["pdftotext", "-layout", str(pdf), "-"])
    return len(re.sub(r"\s+", "", result.stdout))


def validate_pdf(pdf: Path, log_path: Path, tex_path: Path) -> dict[str, Any]:
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    overfull = [float(match.group(1)) for match in OVERFULL_RE.finditer(log_text)]
    tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
    return {
        "pdf": str(pdf.relative_to(ROOT)),
        "pdfinfo": pdf_info(pdf),
        "text_chars": pdf_text_chars(pdf),
        "tex": str(tex_path.relative_to(ROOT)),
        "includegraphics_count": tex_text.count("\\includegraphics"),
        "overfull_count": len(overfull),
        "worst_overfull_pt": max(overfull) if overfull else 0,
        "latex_error_markers": LATEX_ERROR_RE.findall(log_text)[:20],
    }


def tex_context(tex_path: Path, line_no: int, *, radius: int = 4) -> str:
    lines = tex_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return ""
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(f"{idx:05d}: {lines[idx - 1]}" for idx in range(start, end + 1))


def collect_overfull_hotspots(
    tex_path: Path,
    log_path: Path,
    *,
    threshold_pt: float,
    max_hotspots: int,
) -> list[dict[str, Any]]:
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    hotspots: list[dict[str, Any]] = []
    for match in OVERFULL_HOTSPOT_RE.finditer(log_text):
        width = float(match.group(1))
        if width < threshold_pt:
            continue
        line_no = int(match.group(2) or match.group(4) or 1)
        hotspots.append(
            {
                "width_pt": width,
                "line": line_no,
                "context": tex_context(tex_path, line_no),
            }
        )
    hotspots.sort(key=lambda item: item["width_pt"], reverse=True)
    return hotspots[:max_hotspots]


def run_codex_agent_optimizer(
    task_dir: Path,
    tex_path: Path,
    log_path: Path,
    *,
    model: str,
    reasoning: str,
    threshold_pt: float,
    max_hotspots: int,
) -> dict[str, Any]:
    if shutil.which("codex") is None:
        return {"ran": False, "reason": "codex CLI not found"}
    hotspots = collect_overfull_hotspots(
        tex_path,
        log_path,
        threshold_pt=threshold_pt,
        max_hotspots=max_hotspots,
    )
    packet_path = task_dir / "review/final-agent-pocket-optimization-packet.md"
    result_log = task_dir / "review/final-agent-pocket-optimization.log"
    if not hotspots:
        packet_path.write_text("No overfull hotspots above threshold.\n", encoding="utf-8")
        return {"ran": False, "reason": "no hotspots above threshold", "packet": str(packet_path.relative_to(ROOT))}

    hotspot_text = "\n\n".join(
        [
            f"## Hotspot {idx}: {item['width_pt']:.2f}pt too wide near line {item['line']}\n\n"
            "```tex\n"
            f"{item['context']}\n"
            "```"
            for idx, item in enumerate(hotspots, 1)
        ]
    )
    prompt = f"""You are optimizing a generated TeX pocket book in this repository.

Goal: reduce visible overflow and obvious layout mess in the generated pocket TeX while preserving real TeX text, math, tables, figures, diagrams, captions, and source meaning.

Hard rules:
- Edit only this generated TeX file: {tex_path.relative_to(ROOT)}
- Do not edit source PDFs/EPUBs/MOBIs.
- Do not replace text/math/figures with page screenshots or page-image-only output.
- Do not remove real content just to silence warnings.
- This is the single final Codex optimization call for this book. Do not spawn or invoke nested Codex/agent sessions, and do not design a loop.
- Prefer deterministic TeX fixes: remove redundant printed source TOC blocks when Pandoc already provides TOC, wrap/scalebox very wide equations/tables, add sensible manual line breaks in long extracted headings, and preserve equations as TeX.
- Keep the document compilable with XeLaTeX. The runner will recompile after your edits.

Evidence from the latest XeLaTeX log follows. Fix as many hotspots as practical across the whole book, focusing on the worst visible layout problems first.

{hotspot_text}
"""
    packet_path.write_text(prompt, encoding="utf-8")
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "-C",
        str(ROOT),
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "--dangerously-bypass-approvals-and-sandbox",
        "-",
    ]
    result = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=ROOT,
        check=False,
    )
    result_log.write_text(result.stdout, encoding="utf-8", errors="replace")
    return {
        "ran": True,
        "exit_code": result.returncode,
        "model": model,
        "reasoning": reasoning,
        "threshold_pt": threshold_pt,
        "hotspots": len(hotspots),
        "packet": str(packet_path.relative_to(ROOT)),
        "log": str(result_log.relative_to(ROOT)),
    }


def classify_source(source: Path) -> str:
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    if suffix in {".mobi", ".azw3"}:
        return suffix[1:]
    return "unknown"


def build_one(
    task: dict[str, Any],
    *,
    force: bool,
    sync: bool,
    share_root: Path,
    agent_optimize: bool,
    agent_model: str,
    agent_reasoning: str,
    agent_threshold_pt: float,
    agent_max_hotspots: int,
) -> dict[str, Any]:
    book_id = task["book_id"]
    task_dir = ROOT / "build-pocket" / book_id
    review_dir = task_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    status_path = review_dir / "status.json"
    if status_path.exists() and not force:
        prior = read_json(status_path)
        if prior.get("status") == "complete":
            log(f"[skip] {book_id} already complete")
            return prior

    source = (ROOT / task["source"]).resolve()
    title = task.get("title") or book_id
    author = task.get("author") or ""
    source_kind = classify_source(source)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    log(f"[start] {book_id} ({source_kind})")

    try:
        if not source.exists():
            raise FileNotFoundError(source)
        if source_kind == "pdf":
            body_source = marker_pdf_to_markdown(source, task_dir, force=force)
            pandoc_format = "pdftotext" if body_source.name == "source-from-pdftotext.md" else "markdown"
        elif source_kind == "epub":
            body_source = repair_epub_for_pandoc(source, task_dir, force=force)
            pandoc_format = "epub"
        elif source_kind in {"mobi", "azw3"}:
            body_source, pandoc_format = extract_mobi_to_source(source, task_dir, force=force)
        else:
            raise RuntimeError(f"Unsupported source format: {source.suffix}")

        exact_tex = task_dir / "exact/tex/book.tex"
        pocket_tex = task_dir / "pocket-large-font/tex/book.tex"
        if pandoc_format == "pdftotext":
            plain_text_markdown_to_tex(body_source, exact_tex, title=title, author=author, layout="exact")
            plain_text_markdown_to_tex(body_source, pocket_tex, title=title, author=author, layout="pocket")
        else:
            pandoc_to_tex(body_source, exact_tex, title=title, author=author, layout="exact", source_format=pandoc_format)
            pandoc_to_tex(
                body_source,
                pocket_tex,
                title=title,
                author=author,
                layout="pocket",
                source_format=pandoc_format,
            )
        exact_report = compile_tex(exact_tex, task_dir / "exact/book.pdf")
        pocket_report = compile_tex(pocket_tex, task_dir / "pocket-large-font/book.pdf")
        agent_report: dict[str, Any] = {"ran": False, "mode": "single-final-call"}
        if agent_optimize and pocket_report.get("worst_overfull_pt", 0) >= agent_threshold_pt:
            agent_report = run_codex_agent_optimizer(
                task_dir,
                pocket_tex,
                pocket_tex.parent / "latex-build/book.log",
                model=agent_model,
                reasoning=agent_reasoning,
                threshold_pt=agent_threshold_pt,
                max_hotspots=agent_max_hotspots,
            )
            if agent_report.get("exit_code") == 0:
                pocket_report = compile_tex(pocket_tex, task_dir / "pocket-large-font/book.pdf")

        synced_to = ""
        if sync:
            share_root.mkdir(parents=True, exist_ok=True)
            filename = safe_name(f"{title} - pocket large font.pdf")
            dest = share_root / filename
            shutil.copy2(task_dir / "pocket-large-font/book.pdf", dest)
            synced_to = str(dest)

        status = {
            "book_id": book_id,
            "status": "complete",
            "source": str(source.relative_to(ROOT)),
            "source_kind": source_kind,
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "exact": exact_report,
            "pocket": pocket_report,
            "final_agent_optimization": agent_report,
            "synced_to": synced_to,
            "policy": "real TeX body only; no page-image-only output",
        }
    except Exception as exc:
        status = {
            "book_id": book_id,
            "status": "blocked",
            "source": str(source.relative_to(ROOT)) if source.exists() else str(source),
            "source_kind": source_kind,
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "reason": str(exc),
            "policy": "blocked instead of producing page-image-only output",
        }
        log(f"[blocked] {book_id}: {exc}")

    write_json(status_path, status)
    return status


def iter_tasks(queue: dict[str, Any], book_ids: set[str] | None) -> list[dict[str, Any]]:
    tasks = list(queue.get("tasks", []))
    if book_ids:
        tasks = [task for task in tasks if task.get("book_id") in book_ids]
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--continue-on-blocked", action="store_true")
    parser.add_argument("--share-root", type=Path, default=Path("/home/lachlan/Nutstore Files/Share/PocketBooks"))
    parser.add_argument("--agent-optimize", action="store_true", help="Run one final Codex optimization call after deterministic compile validation.")
    parser.add_argument("--agent-model", default="gpt-5.5")
    parser.add_argument("--agent-reasoning", default="xhigh")
    parser.add_argument("--agent-threshold-pt", type=float, default=24.0)
    parser.add_argument("--agent-max-hotspots", type=int, default=24)
    args = parser.parse_args()

    queue = read_json(args.queue)
    tasks = iter_tasks(queue, set(args.book_id) if args.book_id else None)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        log("No tasks selected.")
        return 0

    complete = 0
    blocked = 0
    for task in tasks:
        status = build_one(
            task,
            force=args.force,
            sync=args.sync,
            share_root=args.share_root,
            agent_optimize=args.agent_optimize,
            agent_model=args.agent_model,
            agent_reasoning=args.agent_reasoning,
            agent_threshold_pt=args.agent_threshold_pt,
            agent_max_hotspots=args.agent_max_hotspots,
        )
        if status.get("status") == "complete":
            complete += 1
        else:
            blocked += 1
            if not args.continue_on_blocked:
                break

    summary = {
        "queue": str(args.queue),
        "selected": len(tasks),
        "complete": complete,
        "blocked": blocked,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    summary_path = ROOT / "build-pocket/last-run-summary.json"
    write_json(summary_path, summary)
    log(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if blocked == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
