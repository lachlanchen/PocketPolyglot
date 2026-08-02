#!/usr/bin/env python3
"""Build real-TeX exact and pocket PDFs from the build-pocket queue.

This runner is deliberately conservative: a successful book must have a real
TeX body and PDFs compiled from that body. If local extraction cannot produce a
credible TeX path, the book is marked blocked with evidence instead of emitting
an image-only placeholder.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import fcntl
import hashlib
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
DEFAULT_MARKER_LOCK_DIR = Path("/tmp/pocketpolyglot-marker-slots")

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MARKDOWN_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)\n]+)(\))")
MARKDOWN_IMAGE_BLOCK_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$", re.S)
MARKER_SHARD_BOUNDARY_RE = re.compile(
    r"^\s*<!--\s*source-pages:\d+-\d+\s*-->\s*$",
    re.I,
)
SPACED_INLINE_MATH_RE = re.compile(
    r"(?<!\\)\$(?!\$)(?P<open>[ \t]*)(?P<body>[^$\n]*?)(?P<close>[ \t]*)\$(?!\$)"
)
ESCAPED_CLOSING_INLINE_MATH_RE = re.compile(
    r"(?<!\\)\$(?!\$)(?P<body>[^$\n]*?)\\\$(?!\$)"
)
ESCAPED_CLOSING_DISPLAY_MATH_RE = re.compile(
    r"^(?P<open>[ \t]*\$\$)(?P<body>.+?)\\\$\$(?P<tail>[ \t]*)$",
    re.M,
)
MARKER_ESCAPED_SUP_RE = re.compile(r"<sup>&</sup>lt;sup>(?P<value>\d+)</sup>")
MARKER_FOOTNOTE_MATH_RE = re.compile(
    r"\$<sup>\{\}\^(?P<footnote>\d+)\\</sup>"
    r"(?P<command>[A-Za-z]+)(?P<body>[^$]*)\$"
)
MARKDOWN_DISPLAY_MATH_RE = re.compile(
    r"(?<!\\)\$\$(?P<body>.*?)(?<!\\)\$\$",
    re.S,
)
OVERFULL_RE = re.compile(
    r"Overfull \\[hv]box \(([-0-9.]+)pt too (?:wide|high)\)"
)
OVERFULL_HOTSPOT_RE = re.compile(
    r"Overfull \\hbox \(([-0-9.]+)pt too wide\)"
    r"(?: in paragraph at lines (\d+)(?:--(\d+))?| detected at line (\d+))"
)
LATEX_ERROR_RE = re.compile(
    r"^! (?:LaTeX|Package|Class|File ended|Missing |Extra |Undefined |Emergency |Fatal )"
    r"|Fatal error|Emergency stop|Undefined control sequence",
    re.M,
)
MISSING_CHARACTER_RE = re.compile(r"^Missing character:.*$", re.M)
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?(\{[^}]+\})")
INCLUDEGRAPHICS_PATH_RE = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{"
    r"(?:\\detokenize\{(?P<detokenized>[^{}]+)\}|(?P<plain>[^{}]+))"
    r"\}"
)
LONGTABLE_SPEC_RE = re.compile(r"(\\begin\{longtable\}(?:\[[^\]]*\])?\{)([^{}]*(?:@\{\}[^{}]*)?)(\})")
SIMPLE_LONGTABLE_SPEC_RE = re.compile(
    r"(\\begin\{longtable\}(?:\[[^\]]*\])?\{@\{\})([lcrX]{2,})(@\{\}\})"
)
LONGTABLE_BLOCK_RE = re.compile(r"\\begin\{longtable\}.*?\\end\{longtable\}", re.S)
VERBATIM_BLOCK_RE = re.compile(
    r"(?P<begin>\\begin\{Verbatim\}\[[^\]]*\]\s*\n)"
    r"(?P<body>.*?)"
    r"(?P<end>\n\\end\{Verbatim\})",
    re.S,
)
SIMPLE_ARRAY_RE = re.compile(
    r"\\begin\{array\}\{(?P<spec>[lcr]+)\}(?P<body>.*?)\\end\{array\}",
    re.S,
)
PLAIN_URL_RE = re.compile(
    r"(?<!\\url\{)(?<!\\href\{)(?<![A-Za-z0-9/.:_-])"
    r"(?:https?://|www\.)"
    r"[A-Za-z0-9](?:(?:\\[_%#&])|[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-])*"
)
SOURCE_PAGE_HYPERLINK_RE = re.compile(
    r"\\protect\\hyperlink\{page-[^{}]+\}\{(?P<text>[^{}]*)\}"
)
DISPLAY_MATH_RE = re.compile(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", re.S)
DISPLAY_MATH_PUNCTUATION_RE = re.compile(
    r"(?<!\\)\\\[(?P<body>.*?)(?<!\\)\\\]\s*\n\s*(?P<punct>[.,;:])(?=\s*\n)",
    re.S,
)
INLINE_MATH_RE = re.compile(r"(?<!\\)\\\((.*?)(?<!\\)\\\)", re.S)
DESCRIPTION_DISPLAY_LABEL_RE = re.compile(
    r"\\item\[\s*\\\[(?P<body>.*?)\\\]\s*\]",
    re.S,
)
ADJUSTBOX_DISPLAY_MATH_RE = re.compile(
    r"\\begin\{adjustbox\}\{max width=\\linewidth\}\s*"
    r"\\begin\{minipage\}\{\\linewidth\}\s*"
    r"\\\[(.*?)\\\]\s*"
    r"\\end\{minipage\}\s*"
    r"\\end\{adjustbox\}",
    re.S,
)
DISPLAY_MATH_ENV_RE = re.compile(
    r"\\begin\{(?P<environment>equation\*?|align\*?|gather\*?|multline\*?)\}"
    r"(?P<body>.*?)"
    r"\\end\{(?P=environment)\}",
    re.S,
)
MATH_TAG_RE = re.compile(r"\\tag\{(?P<tag>[^{}]+)\}")
MATH_ENVIRONMENT_TOKEN_RE = re.compile(
    r"\\(?P<kind>begin|end)\{(?P<environment>[^{}]+)\}"
    r"|\\tag\{(?P<tag>[^{}]+)\}"
)
NESTED_UNTAGGABLE_MATH_ENVIRONMENTS = {
    "array",
    "matrix",
    "pmatrix",
    "bmatrix",
    "Bmatrix",
    "vmatrix",
    "Vmatrix",
    "smallmatrix",
    "cases",
    "dcases",
    "aligned",
    "alignedat",
    "gathered",
    "split",
    "subarray",
}
WIDE_MATH_BEGIN = "% BUILD_POCKET_WIDE_MATH_BEGIN"
WIDE_MATH_END = "% BUILD_POCKET_WIDE_MATH_END"
WIDE_MATH_WRAPPER_RE = re.compile(
    re.escape(WIDE_MATH_BEGIN) + r".*?" + re.escape(WIDE_MATH_END),
    re.S,
)
MOVING_ARGUMENT_RE = re.compile(
    r"\\(?:caption|chapter|section|subsection|subsubsection|footnote|footnotetext)"
    r"(?:\[[^\]]*\])?\{"
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
MARKER_MERGE_NORMALIZER_VERSION = 2
STRUCTURED_PDF_PROFILES = {"technical_exact", "illustrated_exact"}


def log(message: str) -> None:
    print(message, flush=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def portable_path(path: Path, *, base: Path = ROOT) -> str:
    """Return a repository-relative path when possible, otherwise an absolute path."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(base.resolve()))
    except ValueError:
        return str(resolved)


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_header() -> Path:
    DEFAULT_HEADER.parent.mkdir(parents=True, exist_ok=True)
    header = (
        r"""
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{graphicx}
\usepackage[export]{adjustbox}
\usepackage{booktabs}
\usepackage{bm}
\usepackage{longtable}
\usepackage{array}
\usepackage{ragged2e}
\usepackage{float}
\usepackage{caption}
\usepackage{pdflscape}
\usepackage{needspace}
\usepackage{titlesec}
\usepackage{fvextra}
\usepackage{xurl}
\setmainfont{TeX Gyre Pagella}
\setsansfont{TeX Gyre Heros}
\setmonofont{DejaVu Sans Mono}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{}
\setlength{\parindent}{1.2em}
\setlength{\parskip}{0.22em}
\setlength{\footskip}{6mm}
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


OCR_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        # Marker preserves the source PDF's private-use digit glyphs. They are
        # semantically ordinary digits but have no glyph in the book fonts.
        "\uf639": "0",
        "\uf6dc": "1",
        "\uf63a": "2",
        "\uf63b": "3",
        "\uf63c": "4",
        "\uf63d": "5",
        "\uf63e": "6",
        "\uf63f": "7",
        "\uf640": "8",
        "\uf641": "9",
        # OCR sometimes chooses visually identical Cyrillic glyphs in English
        # technical tables (for example "Туре" instead of "Type").
        "\u0412": "B",
        "\u0415": "E",
        "\u041d": "H",
        "\u0421": "C",
        "\u0422": "T",
        "\u0430": "a",
        "\u0435": "e",
        "\u0440": "p",
        "\u0443": "y",
        "\u0445": "x",
    }
)

UNICODE_MATH_GREEK = {
    "𝚯": r"\Theta",
    "𝛩": r"\Theta",
    "𝛬": r"\Lambda",
    "𝛷": r"\Phi",
    "𝛺": r"\Omega",
    "𝛼": r"\alpha",
    "𝛾": r"\gamma",
    "𝛿": r"\delta",
    "𝜀": r"\epsilon",
    "𝜂": r"\eta",
    "𝜃": r"\theta",
    "𝜅": r"\kappa",
    "𝜇": r"\mu",
    "𝜌": r"\rho",
    "𝜎": r"\sigma",
    "𝜏": r"\tau",
    "𝜒": r"\chi",
    "𝜔": r"\omega",
    "𝝎": r"\symbf{\omega}",
    "ф": r"\Phi",
    "ẋ": r"\dot{x}",
    "₃": r"{}_{3}",
}


def normalize_ocr_unicode_for_tex(text: str) -> str:
    """Map verified OCR-only glyphs to portable TeX without changing meaning."""

    text = text.translate(OCR_CONFUSABLE_TRANSLATION)

    def replace_symbols(value: str) -> str:
        for source, target in UNICODE_MATH_GREEK.items():
            value = value.replace(source, target)
        return value

    # Preserve the surrounding math mode so commands nested in \symbf,
    # \mathbf, arrays, or display equations remain true mathematical glyphs.
    text = DISPLAY_MATH_ENV_RE.sub(
        lambda match: (
            rf"\begin{{{match.group('environment')}}}"
            + replace_symbols(match.group("body"))
            + rf"\end{{{match.group('environment')}}}"
        ),
        text,
    )
    text = DISPLAY_MATH_RE.sub(
        lambda match: r"\[" + replace_symbols(match.group(1)) + r"\]",
        text,
    )
    text = INLINE_MATH_RE.sub(
        lambda match: r"\(" + replace_symbols(match.group(1)) + r"\)",
        text,
    )
    # Any remaining symbols came from OCR text or table labels rather than a
    # math span. Give each one an explicit local math context.
    for source, target in UNICODE_MATH_GREEK.items():
        text = text.replace(source, r"\(" + target + r"\)")
    return text


GREEK_COMMAND_PATTERN = (
    r"(?:alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|"
    r"iota|kappa|lambda|mu|nu|xi|pi|varpi|rho|varrho|sigma|varsigma|tau|"
    r"upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|"
    r"Sigma|Upsilon|Phi|Psi|Omega)"
)


def normalize_bold_greek_commands(text: str) -> str:
    r"""Keep bold Greek in math fonts instead of legacy text-font slots.

    Mathpix commonly inserts spaces between a command and its braces, for
    example ``\mathbf { \Omega }``.  ``\mathbf`` routes uppercase Greek
    through low OT1 slots, which XeTeX reports as U+0000/U+0008/U+000A.  Use
    ``\boldsymbol`` for Greek and normalize ``\bm`` to the same portable AMS
    command.  The patterns intentionally accept OCR-added whitespace.
    """

    text = re.sub(r"\\boldsymbol\s*\{", r"\\boldsymbol{", text)
    text = re.sub(r"\\bm\s*\{", r"\\boldsymbol{", text)
    return re.sub(
        rf"\\mathbf\s*\{{\s*(\\{GREEK_COMMAND_PATTERN})\s*\}}",
        r"\\boldsymbol{\1}",
        text,
    )


def normalize_escaped_html_fragments(text: str) -> str:
    """Restore simple superscripts that OCR escaped before Pandoc saw them."""

    return re.sub(
        r"\\&\s*lt;sup\\textgreater\s*([A-Za-z0-9]+)",
        r"\\textsuperscript{\1}",
        text,
    )


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
    "text",
    "operatorname",
    "displaystyle",
    "frac",
    "sqrt",
    "sum",
    "prod",
    "int",
    "lim",
    "log",
    "ln",
    "exp",
    "sin",
    "cos",
    "tan",
    "max",
    "min",
    "det",
    "tag",
    "overline",
    "underline",
    "vec",
    "hat",
    "bar",
    "dot",
    "ddot",
    "bra",
    "ket",
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "varepsilon",
    "zeta",
    "eta",
    "theta",
    "vartheta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "varpi",
    "rho",
    "varrho",
    "sigma",
    "varsigma",
    "tau",
    "upsilon",
    "phi",
    "varphi",
    "chi",
    "psi",
    "omega",
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Pi",
    "Sigma",
    "Upsilon",
    "Phi",
    "Psi",
    "Omega",
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
    for enum_label in ("labelenumi", "labelenumii", "labelenumiii", "labelenumiv"):
        text = text.replace("\\" + "def" + enum_label, "\\" + "def\\" + enum_label)
    text = re.sub(r"\bincludesemph\{", r"includes \\emph{", text)
    # Preserve unknown commands here. Technical OCR emits valid domain macros
    # such as \log, \operatorname, \tag, \text, \ket, and \bra. Removing a
    # command merely because it is absent from a hand-maintained allow-list can
    # silently change an equation while still producing a compilable PDF.
    # Concrete undefined commands are handled later from XeLaTeX evidence by
    # repair_undefined_word_command().
    return text


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
    count = len(cols)
    intercolumn_space = 2 * (count - 1)
    wrapped = "".join(
        [
            rf"p{{\dimexpr(\linewidth-{intercolumn_space}\tabcolsep)/{count}\relax}}"
            for _ in cols
        ]
    )
    prefix = "@{}" if spec.startswith("@{}") else ""
    suffix = "@{}" if spec.endswith("@{}") else ""
    return prefix + wrapped + suffix


def normalize_simple_longtable_specs(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        count = len(match.group(2))
        intercolumn_space = 2 * (count - 1)
        columns = "".join(
            rf"p{{\dimexpr(\linewidth-{intercolumn_space}\tabcolsep)/{count}\relax}}"
            for _ in range(count)
        )
        return match.group(1) + columns + match.group(3)

    return SIMPLE_LONGTABLE_SPEC_RE.sub(repl, text)


def add_longtable_break_opportunities(text: str) -> str:
    """Permit wrapping in OCR-concatenated table and index entries.

    Printed indexes are frequently recognized without spaces, for example
    ``polarcoordinates,140Ostrogradskytheorem``.  Adding a discretionary break
    after existing punctuation changes no visible text but prevents a single
    damaged index token from overflowing an otherwise valid technical book.
    """

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        head, marker, body = block.partition(r"\endhead")
        if not marker:
            return block
        body = re.sub(r"([,;/])(?=\S)", r"\1\\allowbreak{}", body)
        body = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", r"-\\allowbreak{}", body)
        return head + marker + body

    return LONGTABLE_BLOCK_RE.sub(repl, text)


def restore_longtable_linebreaks(text: str) -> str:
    """Restore reviewed table breaks after commonmark escapes raw TeX.

    ``normalize_marker_markdown_math`` replaces source ``<br>`` tags with a
    portable marker before Pandoc. Commonmark safely escapes that marker in a
    table cell, so restore it only inside the resulting longtable. This avoids
    interpreting matching prose outside tables as TeX.
    """

    escaped = r"\textbackslash linebreak\{\}"
    return LONGTABLE_BLOCK_RE.sub(
        lambda match: match.group(0).replace(escaped, r"\linebreak{}"),
        text,
    )


def repair_split_uppercase_table_words(text: str) -> str:
    """Rejoin OCR line breaks inserted inside an uppercase table word."""

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        return re.sub(
            r"(?P<left>[A-Z]{3,})\\linebreak\{\}(?P<right>[A-Z]{2,})",
            lambda word: (
                rf"\resizebox{{\linewidth}}{{!}}{{{word.group('left')}{word.group('right')}}}"
                if len(word.group("left") + word.group("right")) >= 12
                else word.group("left") + word.group("right")
            ),
            block,
        )

    return LONGTABLE_BLOCK_RE.sub(repl, text)


def rebalance_longtable_column_fractions(text: str) -> str:
    """Prevent OCR-derived Pandoc tables from assigning unusably thin columns."""

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        head, marker, body = block.partition(r"\toprule")
        values = [float(value) for value in re.findall(r"\\real\{([0-9.]+)\}", head)]
        if not values or len(values) > 6:
            return block
        floor = 0.12 if len(values) <= 4 else 0.08
        if len(values) == 2:
            first_cells = re.findall(r"(?m)^(?P<cell>[^&\n]+?)\s*&", body)
            first_cell_text = " ".join(first_cells).replace(r"\linebreak{}", "")
            first_cell_text = re.sub(r"\\[A-Za-z]+(?:\{[^{}]*\})?", "", first_cell_text)
            longest_label = max(
                (len(token) for token in re.findall(r"[A-Za-z]{2,}", first_cell_text)),
                default=0,
            )
            if longest_label >= 12:
                floor = 0.24
            elif longest_label >= 9:
                floor = 0.20
        if min(values) >= floor:
            return block
        total = sum(values)
        raised = [max(value, floor) for value in values]
        excess = sum(raised) - total
        reducible = sum(max(0.0, value - floor) for value in values)
        if excess <= 0 or reducible <= excess:
            return block
        balanced = [
            value - excess * max(0.0, value - floor) / reducible
            if value > floor
            else floor
            for value in raised
        ]
        iterator = iter(balanced)
        head = re.sub(
            r"\\real\{[0-9.]+\}",
            lambda _match: rf"\real{{{next(iterator):.4f}}}",
            head,
        )
        return head + marker + body

    return LONGTABLE_BLOCK_RE.sub(repl, text)


def normalize_index_verbatim_blocks(text: str, *, layout: str) -> str:
    """Remove scanned-column indentation from index-like literal blocks."""

    def repl(match: re.Match[str]) -> str:
        body = match.group("body")
        lines = body.splitlines()
        index_lines = sum(
            1
            for line in lines
            if re.search(r";\s*\d", line) or re.match(r"\s*[A-Z]\s*$", line)
        )
        if len(lines) < 20 or index_lines < 8:
            return match.group(0)
        normalized = "\n".join(line.lstrip(" \t") for line in lines)
        font_size = r"\footnotesize" if layout == "exact" else r"\scriptsize"
        begin = re.sub(
            r"\]$",
            lambda _match: f",fontsize={font_size}]",
            match.group("begin").rstrip("\n"),
        )
        return begin + "\n" + normalized + match.group("end")

    return VERBATIM_BLOCK_RE.sub(repl, text)


def stabilize_unnumbered_heading_toc_anchors(text: str) -> str:
    """Give each unnumbered Pandoc heading its own PDF destination.

    The template disables section numbering globally.  Hyperref can therefore
    leave ``section`` through ``paragraph`` TOC entries pointing at the most
    recent list item, table, or parent chapter.  Pandoc already wraps headings
    in a named ``hypertarget``; inserting ``phantomsection`` inside that wrapper
    refreshes Hyperref's current destination without changing visible text.
    Starred, explicitly unlisted headings are intentionally left alone.
    """

    pattern = re.compile(
        r"(\\hypertarget\{[^{}\n]+\}\{%\n)"
        r"(?=\\(?:section|subsection|subsubsection|paragraph)\{)"
    )
    return pattern.sub(r"\1\\phantomsection\n", text)


def landscape_wide_longtables(text: str) -> str:
    """Give wide or mathematically dense technical tables the long page edge."""

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        head = block.partition(r"\toprule")[0]
        columns = head.count(r"\arraybackslash")
        if not columns:
            columns = len(re.findall(r"p\{", head))
        math_heavy_five_column = columns == 5 and (
            block.count(r"\langle") >= 4
            or block.count(r"\left\langle") >= 4
            or block.count(r"\symbf{") >= 4
        )
        if columns < 5 and not math_heavy_five_column:
            return block
        return (
            "\n\\clearpage\n\\begin{landscape}\n"
            + block
            + "\n\\end{landscape}\n\\clearpage\n"
        )

    return LONGTABLE_BLOCK_RE.sub(repl, text)


def wrap_plain_urls(text: str) -> str:
    """Make extracted bare URLs break safely without changing their address."""

    def repl(match: re.Match[str]) -> str:
        value = match.group(0)
        trailing = ""
        while value and value[-1] in ".,;:)":
            trailing = value[-1] + trailing
            value = value[:-1]
        return rf"\url{{{value}}}" + trailing

    return PLAIN_URL_RE.sub(repl, text)


def merge_split_url_tildes(text: str) -> str:
    """Rejoin URLs that Pandoc split at a literal home-directory tilde."""

    pattern = re.compile(
        r"\\url\{(?P<base>https?://[^{}]+/)\}"
        r"\\textasciitilde\s*"
        r"(?P<path>[A-Za-z0-9][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%/-]*)"
    )

    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        trailing = ""
        while path and path[-1] in ".,;:)":
            trailing = path[-1] + trailing
            path = path[:-1]
        return rf"\url{{{match.group('base')}~{path}}}" + trailing

    return pattern.sub(repl, text)


def unwrap_source_page_hyperlinks(text: str) -> str:
    """Remove extraction-only page links without changing visible source text.

    Marker sometimes wraps a few letters from the source PDF in internal links,
    including the first letter of a URL. Those wrappers split ordinary words
    and prevent ``xurl`` from finding the complete address. Only generated
    ``page-*`` destinations are unwrapped; real external and document links are
    retained.
    """

    return SOURCE_PAGE_HYPERLINK_RE.sub(lambda match: match.group("text"), text)


def fit_chapter_opening_figures(text: str, *, layout: str) -> str:
    """Reserve room for a chapter title, opening figure, caption, and footer."""

    max_height = ".60" if layout == "exact" else ".55"
    lines = text.splitlines(keepends=True)
    after_chapter = 0
    for index, line in enumerate(lines):
        if r"\chapter{" in line or r"\chapter[" in line:
            after_chapter = 12
            continue
        if after_chapter <= 0:
            continue
        after_chapter -= 1
        if r"\includegraphics[" not in line:
            continue
        lines[index] = re.sub(
            r"max totalheight=\.[0-9]+\\textheight",
            lambda _match: f"max totalheight={max_height}" + r"\textheight",
            line,
            count=1,
        )
        after_chapter = 0
    return "".join(lines)


def normalize_simple_array_column_counts(text: str) -> str:
    """Reconcile simple OCR arrays whose declared column count lost columns."""

    def repl(match: re.Match[str]) -> str:
        body = match.group("body")
        if r"\begin{" in body or r"\multicolumn" in body:
            return match.group(0)
        rows = re.split(r"\\\\(?:\[[^\]]*\])?", body)
        actual_columns = max(
            (len(re.findall(r"(?<!\\)&", row)) + 1 for row in rows if row.strip()),
            default=0,
        )
        spec = match.group("spec")
        if actual_columns <= len(spec) or actual_columns > 24:
            return match.group(0)
        repaired_spec = spec + spec[-1] * (actual_columns - len(spec))
        return rf"\begin{{array}}{{{repaired_spec}}}" + body + r"\end{array}"

    return SIMPLE_ARRAY_RE.sub(repl, text)


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
        r"\n\\hypertarget\{(?:maps|tables|preface(?:-[a-z0-9-]+)?|introduction|prologue|chronology|part-|chapter-|section-|[a-z0-9-]+chapter)\}\{%",
        window[1:],
    )
    if not next_match:
        return text
    end = start + 1 + next_match.start()
    removed = text[start:end]
    preserved_illustration = ""
    table_end = removed.rfind(r"\end{longtable}")
    trailing = removed[table_end + len(r"\end{longtable}") :] if table_end >= 0 else ""
    image_matches = list(
        re.finditer(r"(?m)^\\includegraphics(?:\[[^]]*\])?\{[^}]+\}\s*$", trailing)
    )
    if image_matches:
        # OCR sometimes places real maps/plates between the printed contents
        # table and the first chapter. Preserve the complete trailing figure
        # section, not merely its final image. Start at the closest structural
        # heading before the first image when one exists; otherwise preserve
        # from that image so stray contents-page text is still discarded.
        first_image = image_matches[0].start()
        heading_matches = list(
            re.finditer(
                r"(?m)^\\hypertarget\{[^{}]+\}\{%\s*\n"
                r"\\(?:chapter|section|subsection|subsubsection)\{[^\n]+\}\s*$",
                trailing[:first_image],
            )
        )
        preserve_start = heading_matches[-1].start() if heading_matches else first_image
        preserved_illustration = trailing[preserve_start:].strip() + "\n"
    return (
        text[:start]
        + "\n% Removed source-extracted printed Contents block; Pandoc TOC is used instead.\n"
        + preserved_illustration
        + text[end:]
    )


def merge_display_math_punctuation(text: str) -> str:
    """Keep punctuation OCR placed after a display with that display."""

    def repl(match: re.Match[str]) -> str:
        body = match.group("body").rstrip()
        punct = match.group("punct")
        if body.endswith(tuple(".,;:")):
            punct = ""
        return "\\[" + body + punct + "\\]\n"

    return DISPLAY_MATH_PUNCTUATION_RE.sub(repl, text)


def normalize_description_math_labels(text: str) -> str:
    """Keep display-math definition terms valid inside item labels."""

    return DESCRIPTION_DISPLAY_LABEL_RE.sub(
        lambda match: r"\item[\(\displaystyle " + match.group("body").strip() + r"\)]",
        text,
    )


def display_math_scale_factor(body: str) -> float:
    rows = re.split(r"\\\\(?:\[[^\]]*\])?", body)
    compact_len = max((len(re.sub(r"\s+", "", row)) for row in rows), default=0)
    if compact_len < 100:
        return 1.55
    if compact_len < 180:
        return 2.30
    if compact_len < 300:
        return 3.40
    if compact_len < 450:
        return 4.80
    if compact_len < 700:
        return 6.50
    return 9.00


def transform_outside_wide_math_wrappers(text: str, transform: Any) -> str:
    """Apply a TeX transform without nesting generated width wrappers."""

    parts: list[str] = []
    cursor = 0
    for match in WIDE_MATH_WRAPPER_RE.finditer(text):
        parts.append(transform(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(transform(text[cursor:]))
    return "".join(parts)


def align_multiline_math_body(body: str) -> str:
    body = body.strip()
    # Split is valid only in display math. Width fitting uses a boxed math
    # expression, where aligned preserves the same row layout.
    body = body.replace(r"\begin{split}", r"\begin{aligned}")
    body = body.replace(r"\end{split}", r"\end{aligned}")
    if r"\\" in body and not re.search(
        r"\\begin\{(?:aligned|alignedat|array|bmatrix|Bmatrix|cases|gathered|matrix|pmatrix|smallmatrix|split|vmatrix|Vmatrix)\}",
        body,
    ):
        # OCR commonly preserves deliberate display row breaks but omits the
        # surrounding alignment environment. A bare ``\\`` is invalid inside
        # the inline math box used for width fitting.
        body = "\\begin{aligned}\n" + body + "\n\\end{aligned}"
    return body


def relocate_nested_math_tags(text: str) -> tuple[str, int]:
    """Move an OCR-displaced equation tag to the enclosing display.

    Mathpix-style TeX sometimes puts the number of an entire matrix on its
    first row, for example ``\\begin{array} ... \\tag{13}\\\\``.  AMSMath
    rejects ``\\tag`` inside nested arrays, matrices, cases, or aligned
    helpers.  A display with exactly one tag has an unambiguous repair: remove
    that tag from the nested helper and append it to the display body.  More
    than one nested tag is left as a hard error instead of guessing which rows
    the numbers belong to.
    """

    relocated = 0

    def repair_body(body: str) -> str:
        nonlocal relocated
        stack: list[str] = []
        nested_tags: list[re.Match[str]] = []
        all_tags: list[re.Match[str]] = []
        for token in MATH_ENVIRONMENT_TOKEN_RE.finditer(body):
            kind = token.group("kind")
            environment = token.group("environment")
            if kind == "begin" and environment:
                stack.append(environment)
                continue
            if kind == "end" and environment:
                if stack and stack[-1] == environment:
                    stack.pop()
                elif environment in stack:
                    # Preserve deterministic recovery for malformed OCR while
                    # allowing the structural validator to report the mismatch.
                    reverse_index = stack[::-1].index(environment)
                    del stack[len(stack) - 1 - reverse_index :]
                continue
            all_tags.append(token)
            if any(env in NESTED_UNTAGGABLE_MATH_ENVIRONMENTS for env in stack):
                nested_tags.append(token)

        if not nested_tags:
            return body
        if len(all_tags) != 1 or len(nested_tags) != 1:
            tags = ", ".join(match.group("tag") or "?" for match in nested_tags)
            raise ValueError(
                "cannot deterministically relocate multiple nested equation "
                f"tags: {tags}"
            )

        match = nested_tags[0]
        tag = match.group(0)
        repaired = (body[: match.start()] + body[match.end() :]).rstrip()
        relocated += 1
        return repaired + " " + tag

    def repair_display(match: re.Match[str]) -> str:
        return r"\[" + repair_body(match.group(1)) + r"\]"

    def repair_environment(match: re.Match[str]) -> str:
        environment = match.group("environment")
        return (
            f"\\begin{{{environment}}}"
            + repair_body(match.group("body"))
            + f"\\end{{{environment}}}"
        )

    text = DISPLAY_MATH_RE.sub(repair_display, text)
    text = DISPLAY_MATH_ENV_RE.sub(repair_environment, text)
    return text, relocated


def scaled_display_math(body: str) -> str:
    body = align_multiline_math_body(body)
    return (
        "\n"
        + WIDE_MATH_BEGIN
        + "\n\\Needspace{6\\baselineskip}\n\\begin{center}\n"
        "\\begin{adjustbox}{max width=.94\\linewidth}\n"
        "\\(\\displaystyle\n"
        + body
        + "\n\\)\n"
        "\\end{adjustbox}\n"
        "\\end{center}\n"
        + WIDE_MATH_END
        + "\n"
    )


def scaled_tagged_display_math(body: str, tag: str) -> str:
    body = align_multiline_math_body(body)
    return (
        "\n"
        + WIDE_MATH_BEGIN
        + "\n\\Needspace{6\\baselineskip}\n\\begin{equation}\n"
        "\\resizebox{.94\\linewidth}{!}{\\(\\displaystyle\n"
        + body
        + "\n\\)}\n"
        + rf"\tag{{{tag}}}"
        + "\n\\end{equation}\n"
        + WIDE_MATH_END
        + "\n"
    )


def tex_fragment_is_structurally_balanced(fragment: str) -> bool:
    """Return false when OCR left braces or environments structurally open."""

    depth = 0
    escaped = False
    for char in fragment:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    if depth:
        return False

    begins = collections.Counter(re.findall(r"\\begin\{([^{}]+)\}", fragment))
    ends = collections.Counter(re.findall(r"\\end\{([^{}]+)\}", fragment))
    return begins == ends


def wrap_wide_display_math(text: str, *, layout: str) -> str:
    """Constrain long display equations to the selected page width."""

    if layout not in {"exact", "pocket"}:
        return text
    minimum_length = 42 if layout == "pocket" else 60

    def transform(fragment: str) -> str:
        fragment = ADJUSTBOX_DISPLAY_MATH_RE.sub(
            lambda match: scaled_display_math(match.group(1)), fragment
        )

        def repl(match: re.Match[str]) -> str:
            body = match.group(1).strip()
            if not tex_fragment_is_structurally_balanced(body):
                return match.group(0)
            tag_match = re.search(r"\\tag\{(?P<tag>[^{}]+)\}\s*$", body)
            math_body = body[: tag_match.start()].rstrip() if tag_match else body
            compact = re.sub(r"\s+", "", math_body)
            # Multiline blocks are converted from split to aligned by the
            # width-fitting helper so their deliberate row breaks survive.
            if len(compact) < minimum_length:
                return match.group(0)
            if tag_match:
                return scaled_tagged_display_math(math_body, tag_match.group("tag"))
            return scaled_display_math(body)

        return DISPLAY_MATH_RE.sub(repl, fragment)

    wrapped = transform_outside_wide_math_wrappers(text, transform)
    # A source display often ends with ``\\\\`` because Mathpix treated it
    # like a prose line.  Once wrapped as a standalone centered display, that
    # break has no line to terminate and can stop XeLaTeX.  Consume only a
    # break immediately following a wrapper created by this function.
    return re.sub(
        rf"({re.escape(WIDE_MATH_END)})(?P<spacing>[ \t]*(?:\r?\n[ \t]*)*)"
        r"\\\\(?:\[[^\]]+\])?",
        lambda match: match.group(1) + match.group("spacing"),
        wrapped,
    )


def wrap_wide_math_environments(text: str, *, layout: str) -> tuple[str, int]:
    """Fit long equation/align/gather environments without changing their TeX."""

    if layout not in {"exact", "pocket"}:
        return text, 0
    minimum_length = 55 if layout == "pocket" else 95
    fitted = 0

    def transform(fragment: str) -> str:
        def repl(match: re.Match[str]) -> str:
            nonlocal fitted
            body = match.group("body")
            rows = re.split(r"\\\\(?:\[[^\]]*\])?", body)
            longest = max(
                (len(re.sub(r"\s+", "", row)) for row in rows),
                default=0,
            )
            if longest < minimum_length and r"\tag{" not in body:
                return match.group(0)
            fitted += 1
            factor = display_math_scale_factor(body)
            environment = match.group("environment")
            return (
                "\n"
                + WIDE_MATH_BEGIN
                + "\n\\Needspace{6\\baselineskip}\n\\begin{center}\n"
                + "\\begin{adjustbox}{max width=\\linewidth}\n"
                + f"\\begin{{minipage}}{{{factor:.2f}\\linewidth}}\n"
                + f"\\begin{{{environment}}}"
                + body
                + f"\\end{{{environment}}}\n"
                + "\\end{minipage}\n"
                + "\\end{adjustbox}\n"
                + "\\end{center}\n"
                + WIDE_MATH_END
                + "\n"
            )

        return DISPLAY_MATH_ENV_RE.sub(repl, fragment)

    return transform_outside_wide_math_wrappers(text, transform), fitted


def wrap_wide_inline_math(text: str, *, layout: str) -> tuple[str, int]:
    """Move oversized indivisible inline math atoms onto fitted lines."""

    if layout not in {"exact", "pocket"}:
        return text, 0
    text_atom_length = 120 if layout == "exact" else 90
    # Pocket lines cannot hold long decimal/index runs even when the atom is
    # slightly under 100 compact characters. Fit those predictably instead of
    # discovering them only after a costly full-book compile.
    absolute_length = 180 if layout == "exact" else 70
    # A break opportunity is inserted immediately before the fitted atom, so
    # a long formula can occupy its own line.  Restricting pocket equations to
    # 56% of that line made valid TeX look like a tiny raster thumbnail.
    fitted_width = ".94"
    fitted = 0
    moving_spans: list[tuple[int, int]] = []
    for command in MOVING_ARGUMENT_RE.finditer(text):
        depth = 1
        cursor = command.end()
        escaped = False
        while cursor < len(text) and depth:
            char = text[cursor]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            cursor += 1
        moving_spans.append((command.start(), cursor))
    generated_wrapper_spans = [
        (match.start(), match.end()) for match in WIDE_MATH_WRAPPER_RE.finditer(text)
    ]
    longtable_spans = [
        (match.start(), match.end()) for match in LONGTABLE_BLOCK_RE.finditer(text)
    ]

    def repl(match: re.Match[str]) -> str:
        nonlocal fitted
        if any(start <= match.start() < end for start, end in moving_spans):
            return match.group(0)
        if any(start <= match.start() < end for start, end in generated_wrapper_spans):
            return match.group(0)
        body = match.group(1).strip()
        if not tex_fragment_is_structurally_balanced(body):
            return match.group(0)
        compact_length = len(re.sub(r"\s+", "", body))
        inside_longtable = any(
            start <= match.start() < end for start, end in longtable_spans
        )
        effective_absolute_length = max(absolute_length, 180) if inside_longtable else absolute_length
        if compact_length < effective_absolute_length and not (
            r"\text" in body and compact_length >= text_atom_length
        ):
            return match.group(0)
        fitted += 1
        max_width = (
            r"\linewidth"
            if inside_longtable
            else fitted_width + r"\linewidth"
        )
        # ``adjustbox`` already creates a horizontal box, so an additional
        # ``\mbox`` and nested ``\(...\)`` wrapper are redundant and fragile.
        # Plain math shifts keep the fitted atom self-contained without
        # changing its mathematical content.
        return (
            f"\\penalty0\\hspace{{0pt}}\\adjustbox{{max width={max_width}}}{{$\\displaystyle "
            + body
            + "$}"
        )

    return INLINE_MATH_RE.sub(repl, text), fitted


def postprocess_tex(tex_path: Path, *, layout: str) -> None:
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    text = clean_text(text)
    text = normalize_ocr_unicode_for_tex(text)
    text = normalize_escaped_html_fragments(text)
    text = remove_text_backslash_artifacts(text)
    text = remove_source_contents_block(text)
    # Greek vectors need math bolding. \mathbf and unicode-math's \symbf can
    # select mathematical Unicode through the text font, leaving blank glyphs.
    text = normalize_bold_greek_commands(text)
    text = merge_display_math_punctuation(text)
    text = normalize_description_math_labels(text)
    text = normalize_simple_array_column_counts(text)
    text = INCLUDEGRAPHICS_RE.sub(
        r"\\includegraphics[max width=.94\\linewidth,max totalheight=.70\\textheight,keepaspectratio]\1",
        text,
    )
    text = fit_chapter_opening_figures(text, layout=layout)
    text = LONGTABLE_SPEC_RE.sub(
        lambda match: match.group(1) + normalize_longtable_spec(match.group(2)) + match.group(3),
        text,
    )
    text = normalize_simple_longtable_specs(text)
    text = rebalance_longtable_column_fractions(text)
    text = landscape_wide_longtables(text)
    # Pandoc's plain \raggedright disables hyphenation inside paragraph
    # columns. Ragged2e keeps the same visual alignment while allowing long
    # technical terms and chemical names to wrap on narrow pocket pages.
    text = text.replace(r"\raggedright\arraybackslash", r"\RaggedRight\arraybackslash")
    text = restore_longtable_linebreaks(text)
    text = add_longtable_break_opportunities(text)
    text = repair_split_uppercase_table_words(text)
    text = unwrap_source_page_hyperlinks(text)
    text = wrap_plain_urls(text)
    text = merge_split_url_tildes(text)
    # Pandoc emits literal blocks as the standard verbatim environment, whose
    # lines cannot wrap.  Technical prose frequently uses these blocks for
    # definitions and pseudocode, so keep the content literal while allowing
    # it to fit both the exact and pocket page widths.
    text = text.replace(
        r"\begin{verbatim}",
        r"\begin{Verbatim}[breaklines=true,breakanywhere=true]",
    )
    text = text.replace(r"\end{verbatim}", r"\end{Verbatim}")
    text = normalize_index_verbatim_blocks(text, layout=layout)
    text = stabilize_unnumbered_heading_toc_anchors(text)
    if layout == "pocket":
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\scriptsize\setlength{\tabcolsep}{1.5pt}\begin{longtable}",
        )
    else:
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
        )
    text = text.replace(r"\end{longtable}", r"\end{longtable}\endgroup")
    text, _ = wrap_wide_math_environments(text, layout=layout)
    text = wrap_wide_display_math(text, layout=layout)
    text, _ = wrap_wide_inline_math(text, layout=layout)
    if layout == "pocket":
        heading_style = (
            "\n"
            r"\titleformat{\chapter}[hang]{\normalfont\Large\bfseries\raggedright}"
            r"{\thechapter}{.7em}{}"
            "\n"
            r"\titlespacing*{\chapter}{0pt}{0pt}{1.2\baselineskip}"
            "\n"
        )
        text = text.replace(r"\begin{document}", heading_style + r"\begin{document}", 1)
        text = apply_pocket_footer_defaults(text)
    tex_path.write_text(text, encoding="utf-8")


def apply_pocket_footer_defaults(text: str) -> str:
    """Keep the A6 page number comfortably inside the physical page."""

    text = re.sub(
        r"(paperwidth=105mm,paperheight=148mm,inner=6\.5mm,outer=5\.5mm,top=8mm,)bottom=(?:9|10|11|12)mm",
        r"\1bottom=12mm",
        text,
    )
    page_style = r"\pagestyle{plain}"
    if page_style not in text:
        text = text.replace(r"\begin{document}", page_style + "\n" + r"\begin{document}", 1)
    footskip = r"\setlength{\footskip}{6mm}"
    if footskip not in text:
        marker = r"\pagestyle{plain}"
        if marker in text:
            text = text.replace(marker, marker + "\n" + footskip, 1)
        else:
            text = text.replace(r"\begin{document}", footskip + "\n" + r"\begin{document}", 1)
    return text


def inject_cover_page(tex_path: Path, cover_path: Path) -> bool:
    """Insert one full-page cover before the generated title page."""

    if not cover_path.exists():
        return False
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    package = r"\usepackage{pdfpages}"
    if package not in text:
        text = text.replace(r"\begin{document}", package + "\n" + r"\begin{document}", 1)
    begin = "% BUILD_POCKET_COVER_BEGIN"
    end = "% BUILD_POCKET_COVER_END"
    cover_block = (
        begin
        + "\n"
        + rf"\includepdf[pages=1,pagecommand={{}},width=\paperwidth,height=\paperheight]{{{cover_path.resolve().as_posix()}}}"
        + "\n"
        + end
    )
    block_re = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if block_re.search(text):
        text = block_re.sub(lambda _match: cover_block, text, count=1)
    else:
        text = text.replace(r"\begin{document}", r"\begin{document}" + "\n" + cover_block, 1)
    tex_path.write_text(text, encoding="utf-8")
    return True


def rewrite_markdown_image_paths(markdown: str, base: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix, raw, suffix = match.groups()
        target = raw.strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("/"):
            return match.group(0)
        path = (base / target).resolve()
        return f"{prefix}{path}{suffix}"

    return MARKDOWN_IMAGE_RE.sub(repl, markdown)


IMAGE_EXCLUSION_DIMENSION_KEYS = {
    "min_width",
    "max_width",
    "min_height",
    "max_height",
    "min_aspect_ratio",
    "max_aspect_ratio",
}


def exclude_source_evidenced_markdown_images(
    markdown: str,
    rules: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Remove reviewed scanner artifacts while retaining an auditable record.

    This is intentionally opt-in through a task's source-fix data. A rule must
    cite evidence and specify at least one dimension, digest, or filename
    condition. All configured conditions must match, which keeps broad global
    image heuristics out of the extraction pipeline.
    """

    if not rules:
        return markdown, []

    from PIL import Image

    normalized_rules: list[dict[str, Any]] = []
    for index, raw_rule in enumerate(rules, start=1):
        rule = dict(raw_rule)
        evidence = str(rule.get("source_evidence") or "").strip()
        if not evidence:
            raise RuntimeError(f"Markdown image exclusion rule {index} has no source evidence")
        has_condition = bool(
            IMAGE_EXCLUSION_DIMENSION_KEYS.intersection(rule)
            or str(rule.get("sha256") or "").strip()
            or str(rule.get("filename_regex") or "").strip()
        )
        if not has_condition:
            raise RuntimeError(
                f"Markdown image exclusion rule {index} has no matching condition"
            )
        normalized_rules.append(rule)

    excluded: list[dict[str, Any]] = []

    def replacement(match: re.Match[str]) -> str:
        target = match.group(2).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            return match.group(0)
        image_path = Path(target)
        if not image_path.is_file():
            return match.group(0)
        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except Exception:
            return match.group(0)
        aspect_ratio = width / height if height else 0.0
        digest = ""

        for index, rule in enumerate(normalized_rules, start=1):
            checks: list[bool] = []
            if "min_width" in rule:
                checks.append(width >= int(rule["min_width"]))
            if "max_width" in rule:
                checks.append(width <= int(rule["max_width"]))
            if "min_height" in rule:
                checks.append(height >= int(rule["min_height"]))
            if "max_height" in rule:
                checks.append(height <= int(rule["max_height"]))
            if "min_aspect_ratio" in rule:
                checks.append(aspect_ratio >= float(rule["min_aspect_ratio"]))
            if "max_aspect_ratio" in rule:
                checks.append(aspect_ratio <= float(rule["max_aspect_ratio"]))
            filename_pattern = str(rule.get("filename_regex") or "").strip()
            if filename_pattern:
                checks.append(bool(re.search(filename_pattern, image_path.name)))
            expected_digest = str(rule.get("sha256") or "").strip().lower()
            if expected_digest:
                digest = digest or sha256_file(image_path)
                checks.append(digest.lower() == expected_digest)
            if checks and all(checks):
                digest = digest or sha256_file(image_path)
                excluded.append(
                    {
                        "rule": index,
                        "path": portable_path(image_path),
                        "sha256": digest,
                        "width": width,
                        "height": height,
                        "aspect_ratio": round(aspect_ratio, 4),
                        "source_evidence": rule["source_evidence"],
                        "note": rule.get("note", ""),
                    }
                )
                return ""
        return match.group(0)

    filtered = MARKDOWN_IMAGE_RE.sub(replacement, markdown)
    filtered = re.sub(r"\n{4,}", "\n\n\n", filtered)
    return filtered, excluded


def normalize_marker_markdown_math(
    markdown: str,
    *,
    preserve_html_table_breaks: bool = False,
) -> str:
    """Normalize Marker math delimiters that Pandoc otherwise escapes in tables."""

    # Pandoc strips raw HTML line breaks inside pipe-table cells. Preserve the
    # source's row grouping as portable raw TeX before conversion; otherwise
    # entries such as MEC99<br>MFF98 become one overflowing token.
    def preserve_table_linebreaks(line: str) -> str:
        tag = r"<br\s*/?>"
        # A break at a cell boundary has no semantic line before/after it and
        # produces "There's no line here to end" in TeX. Internal runs denote
        # one visual row break, even when OCR emitted several adjacent tags.
        line = re.sub(rf"(?<=\|)\s*(?:{tag}\s*)+", " ", line, flags=re.I)
        line = re.sub(rf"(?:\s*{tag})+\s*(?=\|)", " ", line, flags=re.I)
        return re.sub(rf"(?:{tag}\s*)+", r"\\linebreak{}", line, flags=re.I)

    if preserve_html_table_breaks:
        markdown = "\n".join(
            preserve_table_linebreaks(line)
            if line.lstrip().startswith("|") and line.rstrip().endswith("|")
            else line
            for line in markdown.splitlines()
        )

    # Marker can nest an escaped HTML superscript inside a math span when a
    # footnote marker immediately precedes an equation.  Recover the footnote
    # marker and the TeX command separately; leaving the HTML inside math makes
    # Pandoc emit an undefined ``\</sup>nabla`` control sequence.
    markdown = MARKER_ESCAPED_SUP_RE.sub(
        lambda match: f"<sup>{match.group('value')}</sup>",
        markdown,
    )
    markdown = MARKER_FOOTNOTE_MATH_RE.sub(
        lambda match: (
            f"<sup>{match.group('footnote')}</sup> "
            f"$\\{match.group('command')}{match.group('body').strip()}$"
        ),
        markdown,
    )
    markdown = re.sub(r"</sup>(?=[A-Za-z])", "</sup> ", markdown)

    # Marker occasionally escapes the first dollar of a closing display
    # delimiter (``\$$``). Restrict the repair to lines that began with ``$$``
    # so prose currency and intentional ``\$`` remain unchanged.
    markdown = ESCAPED_CLOSING_DISPLAY_MATH_RE.sub(
        lambda match: match.group("open") + match.group("body") + "$$" + match.group("tail"),
        markdown,
    )

    def balance_display(match: re.Match[str]) -> str:
        body = match.group("body")
        # Inside an existing ``$$...$$`` display, nested ``\[``/``\]`` cannot
        # be delimiters. Marker uses them for literal commutator brackets;
        # retain those brackets as scalable TeX delimiters.
        body = body.replace(r"\[", r"\left[").replace(r"\]", r"\right]")
        left_count = len(re.findall(r"\\left\b", body))
        right_count = len(re.findall(r"\\right\b", body))
        if left_count == right_count + 1:
            body = body.rstrip() + r" \right."
        elif right_count == left_count + 1:
            body = r"\left. " + body.lstrip()
        return "$$" + body + "$$"

    # Marker sometimes splits one visually braced definition across several
    # numbered displays.  Invisible counterparts keep each display valid while
    # preserving the brace that is visible in the source.
    markdown = MARKDOWN_DISPLAY_MATH_RE.sub(balance_display, markdown)

    def repair_escaped_closer(match: re.Match[str]) -> str:
        body = match.group("body")
        if not re.search(r"[\\_^{}]", body):
            return match.group(0)
        return "$" + body + "$"

    # A frequent OCR artifact is a valid opening math dollar paired with an
    # escaped closing ``\$``.  Repair only TeX-looking spans, leaving ordinary
    # prose currency escapes untouched.
    markdown = ESCAPED_CLOSING_INLINE_MATH_RE.sub(repair_escaped_closer, markdown)

    def repl(match: re.Match[str]) -> str:
        body = match.group("body").strip()
        if not match.group("open") and not match.group("close"):
            return match.group(0)
        if not re.search(r"[\\_^{}]", body):
            return match.group(0)
        return "$" + body + "$"

    return SPACED_INLINE_MATH_RE.sub(repl, markdown)


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


def marker_executable() -> Path:
    candidates = [
        ROOT / ".venv/ocr/bin/marker_single",
        Path.home() / ".local/bin/marker_single",
    ]
    resolved = shutil.which("marker_single", path=f"{Path.home() / '.local/bin'}:{os.environ.get('PATH', '')}")
    if resolved:
        candidates.append(Path(resolved))
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("marker_single is not available; cannot run structured local PDF extraction")


@contextlib.contextmanager
def marker_execution_slot(source_name: str):
    """Serialize GPU-heavy Marker calls across independent queue processes.

    Marker loads the full Surya model set for every shard. Several otherwise
    independent book runners can therefore exhaust GPU memory before any one
    of them finishes a page. File locks keep orchestration parallel while
    bounding only the GPU-heavy section. Set ``POCKET_MARKER_GPU_SLOTS`` above
    one only after confirming the available GPU can hold that many model sets.
    """

    slot_count = max(1, env_int("POCKET_MARKER_GPU_SLOTS", 1))
    poll_seconds = max(0.1, float(os.environ.get("POCKET_MARKER_SLOT_POLL_SECONDS", "2")))
    timeout_seconds = max(0, env_int("POCKET_MARKER_SLOT_TIMEOUT_SECONDS", 0))
    lock_dir = Path(os.environ.get("POCKET_MARKER_LOCK_DIR", str(DEFAULT_MARKER_LOCK_DIR)))
    lock_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    wait_logged = False

    while True:
        for slot_index in range(slot_count):
            lock_path = lock_dir / f"slot-{slot_index + 1:02d}.lock"
            handle = lock_path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue

            waited = time.monotonic() - started
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "source": source_name,
                        "acquired": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            if waited >= poll_seconds:
                log(f"[marker-slot] acquired {slot_index + 1}/{slot_count} after {waited:.1f}s: {source_name}")
            try:
                yield slot_index + 1
            finally:
                handle.seek(0)
                handle.truncate()
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            return

        waited = time.monotonic() - started
        if timeout_seconds and waited >= timeout_seconds:
            raise RuntimeError(
                f"timed out after {waited:.1f}s waiting for a Marker GPU slot: {source_name}"
            )
        if not wait_logged:
            log(f"[marker-slot] waiting for an available GPU slot: {source_name}")
            wait_logged = True
        time.sleep(poll_seconds)


def source_pdf_pages(source: Path) -> int:
    result = run_capture(["pdfinfo", str(source)], check=True)
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.M)
    if not match:
        raise RuntimeError(f"cannot determine PDF page count: {source}")
    return int(match.group(1))


def marker_markdown(root: Path) -> Path | None:
    candidates = sorted(root.glob("**/*.md"), key=lambda path: path.stat().st_size, reverse=True)
    return candidates[0] if candidates else None


def merge_marker_shard(
    markdown: str,
    *,
    markdown_dir: Path,
    media_dir: Path,
    shard_id: str,
) -> tuple[str, int]:
    copied = 0
    media_dir.mkdir(parents=True, exist_ok=True)

    def repl(match: re.Match[str]) -> str:
        nonlocal copied
        prefix, raw, suffix = match.groups()
        target = raw.strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            return match.group(0)
        source_image = Path(target)
        if not source_image.is_absolute():
            source_image = (markdown_dir / source_image).resolve()
        if not source_image.is_file():
            return match.group(0)
        safe_basename = re.sub(r"[^A-Za-z0-9._-]+", "-", source_image.name).strip("-")
        destination = media_dir / f"{shard_id}-{safe_basename}"
        if not destination.exists() or destination.stat().st_size != source_image.stat().st_size:
            shutil.copy2(source_image, destination)
        copied += 1
        return f"{prefix}{destination.resolve().as_posix()}{suffix}"

    return MARKDOWN_IMAGE_RE.sub(repl, markdown), copied


def marker_block_kind(block: str) -> str:
    stripped = block.strip()
    if MARKER_SHARD_BOUNDARY_RE.fullmatch(stripped):
        return "boundary"
    if MARKDOWN_IMAGE_BLOCK_RE.fullmatch(stripped):
        return "image"
    if (
        stripped.startswith(("#", "```", "~~~", "|", "- ", "* ", "+ ", "> "))
        or re.match(r"^\d+[.)]\s", stripped)
        or re.search(r"^\s*\|?[-:]{3,}(?:\|[-: ]{3,})+\|?\s*$", stripped, re.M)
    ):
        return "structure"
    return "text"


def looks_like_marker_caption(block: str) -> bool:
    text = re.sub(r"\s+", " ", block).strip()
    if not text or len(text) > 180:
        return False
    if re.match(r"^(?:fig(?:ure)?|plate|map|table|photo(?:graph)?|source|credit)\b", text, re.I):
        return True
    words = re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ'’-]+", text)
    return len(words) <= 10 and not re.search(r"[.!?][\"'”’)\]]?\s*$", text)


def marker_text_continues(previous: str, following: str) -> bool:
    """Return true only for boundary-evidenced prose continuations."""

    left = re.sub(r"\s+", " ", previous).strip()
    right = re.sub(r"\s+", " ", following).strip()
    if not left or not right:
        return False
    if re.search(r"[.!?:;][\"'”’)\]]?\s*$", left):
        return False
    if marker_block_kind(following) != "text":
        return False
    if right[0].islower() or right[0] in ",.;:!?)]}”’":
        return True
    dangling = re.search(
        r"\b(?:a|an|and|as|at|because|but|by|for|from|if|in|into|nor|of|on|or|"
        r"over|than|that|the|their|then|through|to|under|upon|when|where|which|"
        r"while|who|whose|with|without)\s*$",
        left,
        re.I,
    )
    return dangling is not None


def join_marker_text(previous: str, following: str) -> str:
    left = previous.rstrip()
    right = following.lstrip()
    if re.search(r"[A-Za-z]-$", left) and right[:1].islower():
        return left[:-1] + right
    return left + " " + right


def normalize_marker_merged_markdown(markdown: str) -> tuple[str, dict[str, Any]]:
    """Repair only page/shard-evidenced paragraph splits around figures.

    The raw Marker output is retained separately. This pass never rewrites
    ordinary paragraph boundaries: it joins prose only when a shard marker or
    a floating image demonstrably interrupted an unfinished sentence.
    """

    blocks = [block.strip() for block in re.split(r"\n\s*\n+", markdown) if block.strip()]
    output: list[str] = []
    pending_text = ""
    deferred_figures: list[str] = []
    boundary_seen = False
    figure_seen = False
    joins: list[dict[str, Any]] = []
    moved_figure_blocks = 0
    boundaries_removed = 0

    def flush() -> None:
        nonlocal pending_text, deferred_figures, boundary_seen, figure_seen
        if pending_text:
            output.append(pending_text)
        if deferred_figures:
            output.extend(deferred_figures)
        pending_text = ""
        deferred_figures = []
        boundary_seen = False
        figure_seen = False

    index = 0
    while index < len(blocks):
        block = blocks[index]
        kind = marker_block_kind(block)
        if kind == "boundary":
            boundary_seen = True
            boundaries_removed += 1
            index += 1
            continue
        if kind == "image":
            deferred_figures.append(block)
            figure_seen = True
            if index + 1 < len(blocks) and looks_like_marker_caption(blocks[index + 1]):
                deferred_figures.append(blocks[index + 1])
                index += 1
            index += 1
            continue
        if kind == "structure":
            flush()
            output.append(block)
            index += 1
            continue

        if not pending_text:
            pending_text = block
            index += 1
            continue
        if (boundary_seen or figure_seen) and marker_text_continues(pending_text, block):
            before_tail = re.sub(r"\s+", " ", pending_text)[-120:]
            after_head = re.sub(r"\s+", " ", block)[:120]
            pending_text = join_marker_text(pending_text, block)
            joins.append(
                {
                    "reason": (
                        "shard-boundary-and-figure"
                        if boundary_seen and figure_seen
                        else "shard-boundary"
                        if boundary_seen
                        else "floating-figure"
                    ),
                    "before_tail": before_tail,
                    "after_head": after_head,
                    "deferred_figure_blocks": len(deferred_figures),
                }
            )
            moved_figure_blocks += len(deferred_figures)
            boundary_seen = False
            figure_seen = bool(deferred_figures)
            index += 1
            continue
        flush()
        pending_text = block
        index += 1
    flush()

    normalized = "\n\n".join(output).strip() + "\n"
    return normalized, {
        "version": MARKER_MERGE_NORMALIZER_VERSION,
        "input_blocks": len(blocks),
        "output_blocks": len(output),
        "boundaries_removed": boundaries_removed,
        "joined_continuations": len(joins),
        "moved_figure_blocks": moved_figure_blocks,
        "joins": joins,
    }


def marker_pdf_to_markdown_sharded(
    source: Path,
    task_dir: Path,
    *,
    force: bool,
    shard_pages: int,
) -> Path:
    marker_bin = marker_executable()
    source_hash = sha256_file(source)
    page_count = source_pdf_pages(source)
    shard_root = task_dir / "work/marker-shards"
    media_dir = task_dir / "work/marker-merged/media"
    prepared = task_dir / "review/source-from-marker.md"
    raw_prepared = task_dir / "review/source-from-marker.raw.md"
    normalization_report_path = task_dir / "review/marker-normalization-report.json"
    merged_status_path = task_dir / "review/marker-merge-status.json"

    if force:
        shutil.rmtree(shard_root, ignore_errors=True)
        shutil.rmtree(media_dir.parent, ignore_errors=True)
        prepared.unlink(missing_ok=True)
        raw_prepared.unlink(missing_ok=True)
        normalization_report_path.unlink(missing_ok=True)
        merged_status_path.unlink(missing_ok=True)
    elif prepared.exists() and merged_status_path.exists():
        status = read_json(merged_status_path)
        if (
            status.get("source_sha256") == source_hash
            and status.get("page_count") == page_count
            and status.get("shard_pages") == shard_pages
            and status.get("status") == "complete"
            and status.get("normalizer_version") == MARKER_MERGE_NORMALIZER_VERSION
        ):
            return prepared

    shard_root.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    shard_reports: list[dict[str, Any]] = []
    total_images = 0
    for page_start in range(1, page_count + 1, shard_pages):
        page_end = min(page_count, page_start + shard_pages - 1)
        shard_id = f"pages-{page_start:04d}-{page_end:04d}"
        shard_dir = shard_root / shard_id
        status_path = shard_dir / "status.json"
        markdown_path = marker_markdown(shard_dir)
        reusable = False
        if status_path.exists() and markdown_path is not None:
            prior = read_json(status_path)
            reusable = (
                prior.get("status") == "complete"
                and prior.get("source_sha256") == source_hash
                and prior.get("page_start") == page_start
                and prior.get("page_end") == page_end
            )
        if not reusable:
            shutil.rmtree(shard_dir, ignore_errors=True)
            shard_dir.mkdir(parents=True, exist_ok=True)
            log_file = shard_dir / "marker.log"
            command = [
                str(marker_bin),
                str(source),
                "--page_range",
                f"{page_start - 1}-{page_end - 1}",
                "--output_dir",
                str(shard_dir),
                "--output_format",
                "markdown",
                "--disable_multiprocessing",
                "--disable_tqdm",
                "--highres_image_dpi",
                "240",
            ]
            marker_timeout_seconds = env_int("POCKET_MARKER_SHARD_TIMEOUT_SECONDS", 1800)
            if marker_timeout_seconds > 0 and shutil.which("timeout") is not None:
                command = ["timeout", f"{marker_timeout_seconds}s", *command]
            log(f"[marker] {source.name} pages {page_start}-{page_end}/{page_count}")
            with marker_execution_slot(source.name):
                code = run_stream(command, log_file=log_file)
            markdown_path = marker_markdown(shard_dir)
            if code != 0 or markdown_path is None:
                write_json(
                    status_path,
                    {
                        "status": "blocked",
                        "source_sha256": source_hash,
                        "page_start": page_start,
                        "page_end": page_end,
                        "exit_code": code,
                    },
                )
                raise RuntimeError(
                    f"Marker failed for source pages {page_start}-{page_end}; see {log_file}"
                )
            write_json(
                status_path,
                {
                    "status": "complete",
                    "source_sha256": source_hash,
                    "page_start": page_start,
                    "page_end": page_end,
                    "exit_code": code,
                    "markdown": str(markdown_path.relative_to(ROOT)),
                },
            )

        assert markdown_path is not None
        shard_text = clean_text(markdown_path.read_text(encoding="utf-8", errors="replace"))
        shard_text, image_count = merge_marker_shard(
            shard_text,
            markdown_dir=markdown_path.parent,
            media_dir=media_dir,
            shard_id=shard_id,
        )
        if len(re.sub(r"\s+", "", shard_text)) < 20 and page_end - page_start >= 2:
            raise RuntimeError(f"Marker shard is unexpectedly empty: {shard_id}")
        total_images += image_count
        parts.append(f"<!-- source-pages:{page_start}-{page_end} -->\n\n{shard_text.strip()}")
        shard_reports.append(
            {
                "shard": shard_id,
                "page_start": page_start,
                "page_end": page_end,
                "markdown": str(markdown_path.relative_to(ROOT)),
                "text_chars": len(re.sub(r"\s+", "", shard_text)),
                "image_references": image_count,
            }
        )

    raw_merged = "\n\n".join(parts).strip() + "\n"
    merged, normalization_report = normalize_marker_merged_markdown(raw_merged)
    prepared.parent.mkdir(parents=True, exist_ok=True)
    raw_prepared.write_text(raw_merged, encoding="utf-8")
    prepared.write_text(merged, encoding="utf-8")
    write_json(normalization_report_path, normalization_report)
    if len(re.sub(r"\s+", "", merged)) < max(500, page_count * 80):
        raise RuntimeError(f"merged Marker output too short to trust: {prepared}")
    write_json(
        merged_status_path,
        {
            "status": "complete",
            "engine": "marker-surya-local-sharded",
            "source_sha256": source_hash,
            "page_count": page_count,
            "shard_pages": shard_pages,
            "normalizer_version": MARKER_MERGE_NORMALIZER_VERSION,
            "shards": shard_reports,
            "raw_merged_markdown": str(raw_prepared.relative_to(ROOT)),
            "merged_markdown": str(prepared.relative_to(ROOT)),
            "normalization_report": str(normalization_report_path.relative_to(ROOT)),
            "text_chars": len(re.sub(r"\s+", "", merged)),
            "image_references": total_images,
        },
    )
    return prepared


def marker_pdf_to_markdown(
    source: Path,
    task_dir: Path,
    *,
    force: bool,
    shard_pages: int = 0,
    allow_text_fallback: bool = True,
) -> Path:
    if shard_pages > 0:
        return marker_pdf_to_markdown_sharded(
            source,
            task_dir,
            force=force,
            shard_pages=shard_pages,
        )
    marker_root = task_dir / "work/marker"
    marker_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(marker_root.glob("**/*.md"))
    if existing and not force:
        return existing[0]

    extraction_mode = os.environ.get("POCKET_PDF_EXTRACTION", "").strip().lower()
    if extraction_mode in {"pdftotext", "text"} or os.environ.get("POCKET_SKIP_MARKER") == "1":
        if not allow_text_fallback:
            raise RuntimeError(
                "structured PDF tasks require local layout extraction; "
                "pdftotext is not sufficient"
            )
        return pdftotext_to_markdown(source, task_dir)

    marker_bin = marker_executable()

    log_file = task_dir / "review/marker.log"
    if log_file.exists():
        log_file.unlink()
    cmd = [
        str(marker_bin),
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
    with marker_execution_slot(source.name):
        code = run_stream(cmd, log_file=log_file)
    if code != 0:
        if not allow_text_fallback:
            raise RuntimeError(f"marker_single failed with exit code {code}; see {log_file}")
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
        geometry = "paperwidth=105mm,paperheight=148mm,inner=6.5mm,outer=5.5mm,top=8mm,bottom=12mm"
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
            "geometry:bottom=12mm",
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
    markdown_reader: str = "",
) -> None:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    header = ensure_header()
    figures_dir = tex_path.parents[1] / "figures"
    prepare_generated_media_directory(figures_dir)
    pandoc_source = source
    if source_format == "markdown":
        source_text = source.read_text(encoding="utf-8", errors="replace")
        if source_text.startswith("---\n"):
            closing = source_text.find("\n---\n", 4, 8192)
            if closing >= 0:
                source_text = source_text[closing + 5 :]
        normalized_markdown = normalize_marker_markdown_math(
            source_text,
            preserve_html_table_breaks=markdown_reader.startswith(("commonmark", "gfm")),
        )
        pandoc_source = tex_path.parent / "source-normalized.md"
        pandoc_source.write_text(normalized_markdown, encoding="utf-8")
    cmd = [
        "pandoc",
        str(pandoc_source),
        "--standalone",
        "--toc",
        "--top-level-division=chapter",
        "--wrap=preserve",
        "--metadata",
        f"title={title}",
        "--metadata",
        f"author={author}",
        "--metadata",
        "date=",
        "--include-in-header",
        str(header),
        "--extract-media",
        str(figures_dir),
        "--resource-path",
        f"{source.parent}:{pandoc_source.parent}:{ROOT}",
        "-o",
        str(tex_path),
    ]
    if source_format == "markdown":
        reader = markdown_reader or "markdown+tex_math_dollars+tex_math_single_backslash+raw_tex"
        cmd[1:1] = ["--from", reader]
    elif source_format == "html":
        cmd[1:1] = ["--from", "html"]
    cmd.extend(pandoc_layout_args(layout))
    result = run_capture(cmd)
    if result.returncode:
        (tex_path.parent / "pandoc.log").write_text(result.stdout, encoding="utf-8")
        raise RuntimeError(f"pandoc failed for {source}; see {tex_path.parent / 'pandoc.log'}")
    postprocess_tex(tex_path, layout=layout)


def prepare_generated_media_directory(figures_dir: Path) -> None:
    """Reset one renderer-owned media directory before Pandoc extraction."""

    figures_dir.mkdir(parents=True, exist_ok=True)
    for path in figures_dir.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def task_fix_path(task: dict[str, Any]) -> Path | None:
    """Resolve optional source/TeX correction data with backward compatibility."""

    raw_path = str(task.get("source_fixes") or task.get("tex_fixes") or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else ROOT / path


def apply_task_tex_fixes(tex_path: Path, task: dict[str, Any], *, layout: str) -> None:
    """Apply narrow, source-evidenced repairs after deterministic conversion."""

    fix_path = task_fix_path(task)
    if fix_path is None:
        return
    data = read_json(fix_path)
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    report_rows: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("replacements", []), start=1):
        source = str(item.get("from") or "")
        target = str(item.get("to") or "")
        target = target.replace("{{TASK_DIR}}", tex_path.parents[2].resolve().as_posix())
        if not source:
            continue
        if item.get("regex"):
            flags = re.DOTALL if item.get("dotall", True) else 0
            text, count = re.subn(source, lambda _match: target, text, flags=flags)
        elif item.get("flexible_whitespace"):
            # Pandoc formats the same display differently between full-size
            # and pocket templates. Match the source-evidenced TeX tokens
            # exactly while allowing only whitespace to vary.
            pattern = r"\s*".join(re.escape(token) for token in source.split())
            text, count = re.subn(pattern, lambda _match: target, text, flags=re.DOTALL)
        else:
            count = text.count(source)
            text = text.replace(source, target)
        expected_min = int(item.get("expected_min", 1))
        if count < expected_min:
            raise RuntimeError(
                f"required TeX fix {index} matched {count} times (expected at least {expected_min}): {fix_path}"
            )
        report_rows.append(
            {
                "index": index,
                "matches": count,
                "source_evidence": item.get("source_evidence", ""),
                "note": item.get("note", ""),
            }
        )
    # A source-evidenced repair may insert display math after the normal Pandoc
    # post-processing pass. Inline math has already been fitted, so do not run
    # that pass again and create nested adjustboxes around existing content.
    text = normalize_simple_array_column_counts(text)
    text, _ = wrap_wide_math_environments(text, layout=layout)
    text = wrap_wide_display_math(text, layout=layout)
    tex_path.write_text(text, encoding="utf-8")
    task_dir = tex_path.parents[2]
    report_path = task_dir / "review/tex-fix-report.json"
    report = read_json(report_path) if report_path.exists() else {}
    report[layout] = {
        "fix_file": portable_path(fix_path),
        "replacements": report_rows,
    }
    write_json(report_path, report)


def extract_task_source_crops(source: Path, task: dict[str, Any], task_dir: Path) -> None:
    """Render narrow, source-evidenced PDF regions used to repair lost figures/tables."""

    crops = task.get("source_crops") or []
    if not crops:
        return
    if source.suffix.lower() != ".pdf":
        raise RuntimeError("source_crops are supported only for PDF sources")
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for source-evidenced PDF crops") from exc

    source_hash = sha256_file(source)
    report_rows: list[dict[str, Any]] = []
    document = fitz.open(source)
    try:
        for index, item in enumerate(crops, start=1):
            page_number = int(item["page"])
            if page_number < 1 or page_number > document.page_count:
                raise RuntimeError(f"source crop {index} page out of range: {page_number}")
            clip_values = item.get("clip_points") or []
            if len(clip_values) != 4:
                raise RuntimeError(f"source crop {index} requires four clip_points")
            page = document.load_page(page_number - 1)
            clip = fitz.Rect(*(float(value) for value in clip_values))
            if clip.is_empty or not page.rect.contains(clip):
                raise RuntimeError(
                    f"source crop {index} clip {list(clip)} is outside page {page_number} bounds {list(page.rect)}"
                )
            relative_output = Path(str(item["output"]))
            if relative_output.is_absolute() or ".." in relative_output.parts:
                raise RuntimeError(f"source crop {index} output must stay inside the task directory")
            output = task_dir / relative_output
            output.parent.mkdir(parents=True, exist_ok=True)
            dpi = int(item.get("dpi") or 300)
            rotation = int(item.get("rotate_degrees") or 0)
            if rotation % 90:
                raise RuntimeError(f"source crop {index} rotation must be a multiple of 90 degrees")
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0).prerotate(rotation)
            pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            pixmap.save(output)
            if output.stat().st_size < 1024:
                raise RuntimeError(f"source crop {index} produced an implausibly small asset: {output}")
            report_rows.append(
                {
                    "index": index,
                    "page": page_number,
                    "clip_points": [float(value) for value in clip_values],
                    "dpi": dpi,
                    "rotate_degrees": rotation,
                    "output": str(output.relative_to(task_dir)),
                    "bytes": output.stat().st_size,
                    "source_evidence": item.get("source_evidence", ""),
                }
            )
    finally:
        document.close()
    write_json(
        task_dir / "review/source-crop-report.json",
        {
            "source": str(source.relative_to(ROOT)),
            "source_sha256": source_hash,
            "crops": report_rows,
        },
    )


def flatten_markdown_tables_after_heading(
    markdown: str,
    *,
    heading_pattern: str,
) -> tuple[str, int]:
    """Flatten OCR-created index tables while retaining every cell's text.

    Scanned two- and three-column indexes are visual columns, not semantic
    tables. Marker can join an entire page into one enormous table row, which
    cannot break across a TeX page. Once the configured heading is reached,
    emit each table column in source order as ordinary paragraphs.
    """

    heading_re = re.compile(heading_pattern)
    lines = markdown.splitlines()
    output: list[str] = []
    in_target_section = False
    flattened = 0
    index = 0
    separator_re = re.compile(r"^\s*:?-{3,}:?\s*$")
    break_re = re.compile(r"<br\s*/?>", re.I)
    while index < len(lines):
        line = lines[index]
        if heading_re.search(line):
            in_target_section = True
        is_table_line = line.lstrip().startswith("|") and line.rstrip().endswith("|")
        if not in_target_section or not is_table_line:
            output.append(line)
            index += 1
            continue

        table_lines: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            if not (candidate.lstrip().startswith("|") and candidate.rstrip().endswith("|")):
                break
            table_lines.append(candidate)
            index += 1

        rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in table_lines]
        column_count = max((len(row) for row in rows), default=0)
        columns: list[list[str]] = [[] for _ in range(column_count)]
        for row in rows:
            if row and all(not cell or separator_re.fullmatch(cell) for cell in row):
                continue
            for column_index, cell in enumerate(row):
                cell = break_re.sub(" ", cell)
                cell = re.sub(r"\s+", " ", cell).strip()
                if cell:
                    columns[column_index].append(cell)
        output.append("")
        for column in columns:
            for cell in column:
                output.extend((cell, ""))
        flattened += 1

    return "\n".join(output).rstrip() + "\n", flattened


def apply_task_markdown_fixes(source: Path, task: dict[str, Any], task_dir: Path) -> Path:
    """Create the immutable-to-reviewed source boundary used by later stages.

    The normalized extractor output is never edited in place. Task-specific
    corrections must live in a JSON data file and cite their source evidence.
    Even tasks without corrections receive ``source-reviewed.md`` so exact TeX
    and multilingual generation consume one explicit, auditable contract.
    """

    text = source.read_text(encoding="utf-8", errors="replace")
    fix_path = task_fix_path(task)
    data = read_json(fix_path) if fix_path is not None else {}
    replacements = data.get("markdown_replacements") or []
    report_rows: list[dict[str, Any]] = []
    for index, item in enumerate(replacements, start=1):
        pattern = str(item.get("from") or "")
        target_file = str(item.get("to_file") or "").strip()
        target_path: Path | None = None
        if target_file:
            target_path = Path(target_file)
            if not target_path.is_absolute():
                target_path = ROOT / target_path
            if not target_path.exists():
                raise RuntimeError(
                    f"Markdown fix {index} replacement file does not exist: {target_path}"
                )
            target = target_path.read_text(encoding="utf-8", errors="replace")
        else:
            target = str(item.get("to") or "")
        target = target.replace("{{TASK_DIR}}", task_dir.resolve().as_posix())
        if not pattern:
            continue
        if item.get("regex"):
            flags = re.DOTALL if item.get("dotall", True) else 0
            text, count = re.subn(pattern, lambda _match: target, text, flags=flags)
        elif item.get("flexible_whitespace"):
            flexible = r"\s*".join(re.escape(token) for token in pattern.split())
            text, count = re.subn(flexible, lambda _match: target, text, flags=re.DOTALL)
        else:
            count = text.count(pattern)
            text = text.replace(pattern, target)
        expected_min = int(item.get("expected_min", 1))
        if count < expected_min:
            raise RuntimeError(
                f"required Markdown fix {index} matched {count} times "
                f"(expected at least {expected_min}): {fix_path}"
            )
        report_rows.append(
            {
                "index": index,
                "matches": count,
                "target_file": portable_path(target_path) if target_path is not None else "",
                "target_sha256": sha256_file(target_path) if target_path is not None else "",
                "source_evidence": item.get("source_evidence", ""),
                "note": item.get("note", ""),
            }
        )

    flattened_index_tables = 0
    flatten_after = str(task.get("flatten_markdown_tables_after_heading") or "").strip()
    if flatten_after:
        text, flattened_index_tables = flatten_markdown_tables_after_heading(
            text,
            heading_pattern=flatten_after,
        )

    # The reviewed copy lives in another directory. Rebase local image paths
    # first so copying the Markdown cannot silently detach its figure assets.
    text = rewrite_markdown_image_paths(text, source.parent)
    text, excluded_images = exclude_source_evidenced_markdown_images(
        text,
        data.get("markdown_image_exclusions") or [],
    )
    local_images: list[str] = []
    missing_images: list[str] = []
    for match in MARKDOWN_IMAGE_RE.finditer(text):
        target = match.group(2).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        image_path = Path(target)
        if image_path.is_file():
            local_images.append(str(image_path))
        else:
            missing_images.append(target)
    if missing_images and str(task.get("validation_profile") or "") in STRUCTURED_PDF_PROFILES:
        raise RuntimeError(
            "reviewed Markdown has missing local figure assets: "
            + ", ".join(missing_images[:10])
        )

    prepared = task_dir / "review/source-reviewed.md"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(text, encoding="utf-8")
    write_json(
        task_dir / "review/markdown-fix-report.json",
        {
            "source": portable_path(source),
            "source_sha256": sha256_file(source),
            "reviewed_markdown": portable_path(prepared),
            "reviewed_sha256": sha256_file(prepared),
            "fix_file": portable_path(fix_path) if fix_path is not None else "",
            "replacements": report_rows,
            "flattened_index_tables": flattened_index_tables,
            "excluded_image_references": len(excluded_images),
            "excluded_unique_images": len(
                {str(item.get("sha256") or "") for item in excluded_images}
            ),
            "excluded_images": excluded_images,
            "local_image_references": len(local_images),
            "missing_image_references": missing_images,
        },
    )
    return prepared


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
        # Repair only an OCR-created command embedded inside a word, and only
        # after XeLaTeX has proved the line contains an undefined control
        # sequence. Adjacent valid commands such as ``\log\frac`` are retained
        # because ``frac`` is in the command set.
        for candidate in re.finditer(r"(?<=[^\W_])\\([A-Za-z]{2,})", old):
            if candidate.group(1) in KNOWN_LATEX_COMMANDS:
                continue
            new = old[: candidate.start()] + old[candidate.start() + 1 :]
            break
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


def tex_figure_inventory(tex_path: Path) -> dict[str, Any]:
    """Return ordered, source-verifiable evidence for every TeX figure.

    A nonzero ``\includegraphics`` count is not enough for figure-rich books:
    one surviving image could otherwise let a mostly stripped conversion pass.
    Record each path, verify it exists, and hash the ordered content so exact
    and pocket layouts can prove that they contain the same figure sequence.
    """

    tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
    figures: list[dict[str, Any]] = []
    missing: list[str] = []
    ordered_hashes: list[str] = []
    for match in INCLUDEGRAPHICS_PATH_RE.finditer(tex_text):
        raw_path = (match.group("detokenized") or match.group("plain") or "").strip()
        # Pandoc normally emits plain paths. Handle its common TeX escapes
        # conservatively without interpreting arbitrary TeX commands.
        filesystem_path = (
            raw_path.replace(r"\_", "_")
            .replace(r"\%", "%")
            .replace(r"\#", "#")
            .replace(r"\&", "&")
        )
        candidate = Path(filesystem_path)
        if not candidate.is_absolute():
            candidate = (tex_path.parent / candidate).resolve()
        exists = candidate.is_file()
        row: dict[str, Any] = {
            "index": len(figures) + 1,
            "tex_path": raw_path,
            "exists": exists,
        }
        if exists:
            digest = sha256_file(candidate)
            ordered_hashes.append(digest)
            row.update(
                {
                    "resolved_path": str(candidate),
                    "size_bytes": candidate.stat().st_size,
                    "sha256": digest,
                }
            )
        else:
            missing.append(raw_path)
        figures.append(row)
    sequence_sha256 = hashlib.sha256(
        "\n".join(ordered_hashes).encode("ascii")
    ).hexdigest()
    return {
        "referenced_count": len(figures),
        "existing_count": len(figures) - len(missing),
        "missing_count": len(missing),
        "missing_paths": missing,
        "unique_content_count": len(set(ordered_hashes)),
        "sequence_sha256": sequence_sha256,
        "figures": figures,
    }


def validate_pdf(pdf: Path, log_path: Path, tex_path: Path) -> dict[str, Any]:
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    overfull = [float(match.group(1)) for match in OVERFULL_RE.finditer(log_text)]
    figure_inventory = tex_figure_inventory(tex_path)
    return {
        "pdf": str(pdf.relative_to(ROOT)),
        "pdfinfo": pdf_info(pdf),
        "text_chars": pdf_text_chars(pdf),
        "tex": str(tex_path.relative_to(ROOT)),
        "includegraphics_count": figure_inventory["referenced_count"],
        "figure_inventory": figure_inventory,
        "overfull_count": len(overfull),
        "worst_overfull_pt": max(overfull) if overfull else 0,
        "latex_error_markers": LATEX_ERROR_RE.findall(log_text)[:20],
        "missing_character_markers": MISSING_CHARACTER_RE.findall(log_text)[:20],
    }


def pdf_embedded_image_count(pdf: Path) -> int:
    result = run_capture(["pdfimages", "-list", str(pdf)], check=False)
    if result.returncode:
        return -1
    return sum(1 for line in result.stdout.splitlines() if re.match(r"^\s*\d+\s+\d+\s+", line))


def generated_structure_report(source: Path, exact_report: dict[str, Any]) -> dict[str, Any]:
    tex_path = ROOT / exact_report["tex"]
    tex = tex_path.read_text(encoding="utf-8", errors="replace")
    source_report: dict[str, Any] = {
        "kind": classify_source(source),
        "sha256": sha256_file(source),
        "size_bytes": source.stat().st_size,
    }
    if source.suffix.lower() == ".pdf":
        source_report.update(
            {
                "pages": source_pdf_pages(source),
                "text_chars": pdf_text_chars(source),
                "embedded_images": pdf_embedded_image_count(source),
            }
        )
    return {
        "source": source_report,
        "generated": {
            "text_chars": exact_report.get("text_chars", 0),
            "includegraphics_count": exact_report.get("includegraphics_count", 0),
            "display_math_count": len(DISPLAY_MATH_RE.findall(tex))
            + len(DISPLAY_MATH_ENV_RE.findall(tex)),
            "inline_math_count": len(INLINE_MATH_RE.findall(tex)),
            "has_toc": r"\tableofcontents" in tex,
        },
    }


def completion_issues(
    task: dict[str, Any],
    source: Path,
    exact_report: dict[str, Any],
    pocket_report: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    profile = str(task.get("validation_profile") or "basic")
    structure = generated_structure_report(source, exact_report)
    generated = structure["generated"]
    source_report = structure["source"]
    issues: list[str] = []

    for layer_name, report in (("exact", exact_report), ("pocket", pocket_report)):
        if report.get("latex_error_markers"):
            issues.append(f"{layer_name} TeX log contains LaTeX error markers")
        if report.get("missing_character_markers"):
            issues.append(f"{layer_name} TeX log contains missing-character warnings")
        max_overfull = float(task.get("max_overfull_pt", 18.0))
        if float(report.get("worst_overfull_pt", 0)) > max_overfull:
            issues.append(
                f"{layer_name} worst overfull line is {report.get('worst_overfull_pt')}pt "
                f"(limit {max_overfull}pt)"
            )
    if not generated["has_toc"]:
        issues.append("generated exact TeX has no table of contents")

    minimum_chars = int(task.get("minimum_generated_text_chars", 5000))
    structured_pdf = profile in STRUCTURED_PDF_PROFILES
    if structured_pdf and source_report.get("pages"):
        minimum_chars = max(minimum_chars, int(source_report["pages"]) * 80)
    if int(generated["text_chars"]) < minimum_chars:
        issues.append(
            f"generated text is too short: {generated['text_chars']} chars (minimum {minimum_chars})"
        )

    if structured_pdf:
        source_text_chars = int(source_report.get("text_chars") or 0)
        if source_text_chars >= 5000:
            ratio = int(generated["text_chars"]) / source_text_chars
            structure["generated"]["source_text_coverage_ratio"] = round(ratio, 4)
            minimum_ratio = float(task.get("minimum_source_text_coverage_ratio", 0.55))
            if ratio < minimum_ratio:
                issues.append(
                    f"generated/source text coverage is {ratio:.3f} (minimum {minimum_ratio:.3f})"
                )
        if int(source_report.get("embedded_images") or 0) > 0 and int(generated["includegraphics_count"]) == 0:
            issues.append("illustrated source has embedded images but generated TeX references none")
        exact_figures = exact_report.get("figure_inventory") or {}
        pocket_figures = pocket_report.get("figure_inventory") or {}
        for layer_name, inventory in (("exact", exact_figures), ("pocket", pocket_figures)):
            if int(inventory.get("missing_count") or 0):
                issues.append(
                    f"{layer_name} TeX has {inventory.get('missing_count')} missing figure paths"
                )
        if (
            exact_figures.get("sequence_sha256")
            and pocket_figures.get("sequence_sha256")
            and exact_figures["sequence_sha256"] != pocket_figures["sequence_sha256"]
        ):
            issues.append("exact and pocket TeX do not preserve the same ordered figure sequence")

        task_dir = (ROOT / exact_report["tex"]).parents[2]
        marker_status_path = task_dir / "review/marker-merge-status.json"
        if marker_status_path.exists():
            marker_status = read_json(marker_status_path)
            raw_extracted_references = int(marker_status.get("image_references") or 0)
            fix_report_path = task_dir / "review/markdown-fix-report.json"
            fix_report = read_json(fix_report_path) if fix_report_path.exists() else {}
            excluded_references = int(fix_report.get("excluded_image_references") or 0)
            if excluded_references > raw_extracted_references:
                issues.append(
                    "review excludes more image references than Marker extracted: "
                    f"{excluded_references}/{raw_extracted_references}"
                )
            extracted_references = max(0, raw_extracted_references - excluded_references)
            structure["marker_extraction"] = {
                "status": marker_status.get("status", ""),
                "raw_image_references": raw_extracted_references,
                "source_evidenced_exclusions": excluded_references,
                "image_references": extracted_references,
                "text_chars": marker_status.get("text_chars", 0),
                "shards": len(marker_status.get("shards") or []),
            }
            minimum_figure_ratio = float(task.get("minimum_extracted_figure_retention_ratio", 1.0))
            for layer_name, inventory in (("exact", exact_figures), ("pocket", pocket_figures)):
                retained = int(inventory.get("existing_count") or 0)
                ratio = retained / extracted_references if extracted_references else 1.0
                inventory["marker_reference_retention_ratio"] = round(ratio, 4)
                if extracted_references and ratio < minimum_figure_ratio:
                    issues.append(
                        f"{layer_name} retains {retained}/{extracted_references} Marker figure "
                        f"references ({ratio:.3f}; minimum {minimum_figure_ratio:.3f})"
                    )

        minimum_figures = int(task.get("minimum_generated_figure_count", 0))
        for layer_name, inventory in (("exact", exact_figures), ("pocket", pocket_figures)):
            retained = int(inventory.get("existing_count") or 0)
            if retained < minimum_figures:
                issues.append(
                    f"{layer_name} TeX retains only {retained} figures "
                    f"(minimum {minimum_figures})"
                )

        required_figure_files = task.get("required_generated_figure_files") or []
        required_hashes: dict[str, str] = {}
        for raw_path in required_figure_files:
            required_path = Path(str(raw_path))
            if not required_path.is_absolute():
                required_path = task_dir / required_path
            if not required_path.is_file():
                issues.append(f"required source-evidenced figure is missing: {required_path}")
                continue
            required_hashes[str(raw_path)] = sha256_file(required_path)
        structure["required_figures"] = {
            "count": len(required_hashes),
            "files": required_hashes,
        }
        for layer_name, inventory in (("exact", exact_figures), ("pocket", pocket_figures)):
            generated_hashes = {
                str(item.get("sha256") or "") for item in inventory.get("figures") or []
            }
            for raw_path, digest in required_hashes.items():
                if digest not in generated_hashes:
                    issues.append(
                        f"{layer_name} TeX omits required source-evidenced figure: {raw_path}"
                    )

    if profile == "technical_exact":
        minimum_math = int(task.get("minimum_math_blocks", 5))
        math_count = int(generated["display_math_count"]) + int(generated["inline_math_count"])
        if math_count < minimum_math:
            issues.append(f"technical TeX has only {math_count} math blocks (minimum {minimum_math})")

    return issues, structure


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


def resolve_prepared_markdown(task: dict[str, Any]) -> Path | None:
    """Resolve an optional reviewed Markdown transcription for a PDF task."""

    raw_path = str(task.get("prepared_markdown") or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise RuntimeError(f"prepared_markdown must be Markdown: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    if len(re.sub(r"\s+", "", path.read_text(encoding="utf-8", errors="replace"))) < 500:
        raise RuntimeError(f"prepared_markdown is too short to trust: {path}")
    return path


def build_one(
    task: dict[str, Any],
    *,
    force: bool,
    rebuild_complete: bool,
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
    if status_path.exists() and not force and not rebuild_complete:
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
            validation_profile = str(task.get("validation_profile") or "basic")
            body_source = resolve_prepared_markdown(task)
            if body_source is None:
                body_source = marker_pdf_to_markdown(
                    source,
                    task_dir,
                    force=force,
                    shard_pages=int(task.get("marker_shard_pages") or 0),
                    allow_text_fallback=validation_profile not in STRUCTURED_PDF_PROFILES,
                )
            else:
                log(f"[reuse] {book_id} reviewed Markdown: {portable_path(body_source)}")
            pandoc_format = "pdftotext" if body_source.name == "source-from-pdftotext.md" else "markdown"
        elif source_kind == "epub":
            body_source = repair_epub_for_pandoc(source, task_dir, force=force)
            pandoc_format = "epub"
        elif source_kind in {"mobi", "azw3"}:
            body_source, pandoc_format = extract_mobi_to_source(source, task_dir, force=force)
        else:
            raise RuntimeError(f"Unsupported source format: {source.suffix}")

        extract_task_source_crops(source, task, task_dir)
        if pandoc_format == "markdown":
            body_source = apply_task_markdown_fixes(body_source, task, task_dir)

        exact_tex = task_dir / "exact/tex/book.tex"
        pocket_tex = task_dir / "pocket-large-font/tex/book.tex"
        if pandoc_format == "pdftotext":
            plain_text_markdown_to_tex(body_source, exact_tex, title=title, author=author, layout="exact")
            plain_text_markdown_to_tex(body_source, pocket_tex, title=title, author=author, layout="pocket")
        else:
            markdown_reader = str(task.get("markdown_reader") or "")
            pandoc_to_tex(
                body_source,
                exact_tex,
                title=title,
                author=author,
                layout="exact",
                source_format=pandoc_format,
                markdown_reader=markdown_reader,
            )
            pandoc_to_tex(
                body_source,
                pocket_tex,
                title=title,
                author=author,
                layout="pocket",
                source_format=pandoc_format,
                markdown_reader=markdown_reader,
            )
        apply_task_tex_fixes(exact_tex, task, layout="exact")
        apply_task_tex_fixes(pocket_tex, task, layout="pocket")
        cover_path = task_dir / "cover/cover.png"
        if cover_path.exists():
            inject_cover_page(exact_tex, cover_path)
            inject_cover_page(pocket_tex, cover_path)
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

        validation_issues, structure_report = completion_issues(
            task,
            source,
            exact_report,
            pocket_report,
        )

        synced_to = ""
        if sync and not validation_issues:
            share_root.mkdir(parents=True, exist_ok=True)
            filename = safe_name(f"{title} - pocket large font.pdf")
            dest = share_root / filename
            shutil.copy2(task_dir / "pocket-large-font/book.pdf", dest)
            synced_to = str(dest)

        status = {
            "book_id": book_id,
            "status": "blocked" if validation_issues else "complete",
            "source": str(source.relative_to(ROOT)),
            "source_kind": source_kind,
            "reviewed_source": portable_path(body_source) if pandoc_format == "markdown" else "",
            "reviewed_source_sha256": (
                sha256_file(body_source) if pandoc_format == "markdown" else ""
            ),
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "exact": exact_report,
            "pocket": pocket_report,
            "validation_profile": task.get("validation_profile", "basic"),
            "validation_issues": validation_issues,
            "structure_evidence": structure_report,
            "final_agent_optimization": agent_report,
            "synced_to": synced_to,
            "policy": "real TeX body only; no page-image-only output",
        }
        if validation_issues:
            status["reason"] = "; ".join(validation_issues)
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
    defaults = dict(queue.get("task_defaults") or {})
    tasks = [{**defaults, **task} for task in queue.get("tasks", [])]
    if book_ids:
        tasks = [task for task in tasks if task.get("book_id") in book_ids]
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--rebuild-complete",
        action="store_true",
        help="Rebuild TeX/PDF for completed tasks while reusing cached extraction.",
    )
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
            rebuild_complete=args.rebuild_complete,
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
