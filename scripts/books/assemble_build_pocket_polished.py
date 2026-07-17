#!/usr/bin/env python3
"""Assemble validated polished chunks into English/Japanese exact and pocket PDFs."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_pocket_tex_queue import (
    apply_pocket_footer_defaults,
    compile_tex,
    latex_escape_text,
    wrap_wide_display_math,
    wrap_wide_inline_math,
    wrap_wide_math_environments,
)
from japanese_tex_furigana import FuriganaStats, annotate_japanese_tex
from pocket_polished_common import (
    apply_exact_text_replacements,
    ENVIRONMENT_COMMAND_RE,
    INLINE_MATH_RE,
    MATH_ENV_RE,
    OUTPUT_ROOT,
    ROOT,
    compare_inventory,
    inventory,
    normalize_transport_formatting,
    read_json,
    read_jsonl,
    restored_segment_output,
    validate_chunk_output,
    write_json,
)


INCLUDEGRAPHICS_RE = re.compile(
    r"(?P<prefix>\\includegraphics(?:\[[^\]]*\])?\{)"
    r"(?:(?P<detokenize>\\detokenize\{(?P<detokenized_path>[^{}]+)\})|(?P<path>[^{}]+))"
    r"(?P<suffix>\})"
)
EXACT_GEOMETRY_RE = re.compile(
    r"\\usepackage\[paperwidth=148mm,paperheight=210mm,inner=14mm,outer=12mm,top=14mm,bottom=16mm\]\{geometry\}"
)
GEOMETRY_COMMAND_RE = re.compile(r"\\geometry\{[^{}]*paperwidth=[^{}]+\}")
GEOMETRY_PACKAGE_RE = re.compile(
    r"\\usepackage\[[^\]]*paperwidth=[^\]]+\]\{geometry\}"
)
FULL_BLEED_IMAGE_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)\\noindent"
    r"(?P<image>\\includegraphics\[[^\]]*\\paperwidth[^\]]*\]\{(?:\\detokenize\{)?[^\n]+\})[ \t]*$"
)
STANDALONE_IMAGE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:~[ \t]*)*(?:\\noindent[ \t]*)?"
    r"(?P<image>\\includegraphics(?:\[[^\]]*\])?\{[^{}]+\})"
    r"(?P<tail>(?:[ \t]*\\(?:par|smallskip|medskip|bigskip))*)[ \t]*$"
)
SIMPLE_LONGTABLE_RE = re.compile(
    r"\\begin\{longtable\}\[\]\{@\{\}(?P<columns>[lcr]+)@\{\}\}"
    r"(?P<body>.*?)"
    r"\\end\{longtable\}",
    re.S,
)
SELF_LABELED_HREF_RE = re.compile(
    r"\\href\{(?P<target>https?://[^{}\s]+)\}"
    r"\{(?P<label>https?://[^{}\s]+)\}"
)
PLAIN_LOG_EXPRESSION_RE = re.compile(
    r"(?<![\\$A-Za-z0-9_])(?P<lhs>[A-Za-z]+_[A-Za-z0-9]+)\s*=\s*"
    r"(?P<sign>[+-]?)log\s*(?P<argument>[ερλχσθαβγδA-Za-z][A-Za-z0-9_]*)"
)

TECHNICAL_BOOK_ID_SUFFIXES = (
    "-mathpix-exact-book",
    "-local-exact-book",
    "-exact-book",
)


def resolve_cover_source(book_id: str, manifest: dict[str, Any]) -> Path | None:
    """Find an explicit or reusable project cover for a polished book."""
    candidates: list[Path] = []
    configured_cover = manifest.get("cover_image") or manifest.get("cover")
    if configured_cover:
        configured_path = Path(str(configured_cover)).expanduser()
        candidates.append(
            configured_path if configured_path.is_absolute() else ROOT / configured_path
        )

    cover_ids = [book_id]
    for suffix in TECHNICAL_BOOK_ID_SUFFIXES:
        if book_id.endswith(suffix):
            cover_ids.append(book_id[: -len(suffix)])
            break
    for cover_id in cover_ids:
        candidates.extend(
            (
                ROOT / "build-pocket" / cover_id / "cover/background.png",
                ROOT / "build-pocket" / cover_id / "cover/cover.png",
                ROOT / "assets/covers" / cover_id / "background.png",
                ROOT / "assets/covers" / cover_id / "cover.png",
            )
        )

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None
PLAIN_POWER_INEQUALITY_RE = re.compile(
    r"(?P<left>[A-Za-z]+\^\{[^{}\n]+\})\s*"
    r"\\textless\{\}\s*(?P<right>[A-Za-z]+\^\{[^{}\n]+\})"
)
PLAIN_SCALE_FACTOR_RE = re.compile(r"a\(t\)\s*=\s*a₀tᵖ")
PLAIN_GREEK_POWER_RE = re.compile(r"φ\(r\)\s*∼\s*r\^\{(?P<exponent>[^{}\n]+)\}Φ")
PLAIN_NUMERIC_POWER_RE = re.compile(
    r"(?<![\\$A-Za-z0-9_])"
    r"(?:(?P<coefficient>\d+(?:\.\d+)?)\s*(?:×|[xX]|\\times)\s*)?"
    r"10\^(?P<exponent>[+-]?\d+|[A-Za-z]+)(?![A-Za-z0-9_])"
)
PLAIN_BRACED_NUMERIC_POWER_RE = re.compile(
    r"(?<![\\$A-Za-z0-9_])"
    r"(?:(?P<coefficient>\d+(?:\.\d+)?)\s*(?:×|[xX]|\\times)\s*)?"
    r"10\^\{(?P<exponent>[+-]?\d+|[A-Za-z]+)\}"
)
SUPERSCRIPT_VALUE = str.maketrans(
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻",
    "0123456789+-",
)
SUBSCRIPT_VALUE = str.maketrans(
    "₀₁₂₃₄₅₆₇₈₉₊₋ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ",
    "0123456789+-aehijklmnoprstuvx",
)
PLAIN_SCIENTIFIC_SUPERSCRIPT_RE = re.compile(
    r"(?<![\\A-Za-z0-9])"
    r"(?P<coefficient>\d+(?:\.\d+)?)\s*(?:×|[xX])\s*10"
    r"(?P<superscript>[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)"
)
PLAIN_SHORT_POWER_RE = re.compile(
    r"(?<![A-Za-z0-9Α-Ωα-ω])"
    r"(?P<base>(?:\d+(?:\.\d+)?|[A-Za-zΑ-Ωα-ω]{1,3}))"
    r"(?P<superscript>[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)"
)
PLAIN_SHORT_SUBSCRIPT_RE = re.compile(
    r"(?<![A-Za-z0-9Α-Ωα-ω])"
    r"(?P<base>[A-Za-zΑ-Ωα-ω]{1,3})"
    r"(?P<subscript>[₀₁₂₃₄₅₆₇₈₉₊₋ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ]+)"
)
PLAIN_ASCII_SHORT_POWER_RE = re.compile(
    r"(?<![A-Za-z0-9\\])"
    r"(?P<base>[A-Za-zΑ-Ωα-ω]{1,3})\^(?P<exponent>[+-]?\d+)"
    r"(?![A-Za-z0-9{}])"
)
REMAINING_SUPERSCRIPT_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+")
REMAINING_SUBSCRIPT_RE = re.compile(r"[₀₁₂₃₄₅₆₇₈₉₊₋ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ]+")
GREEK_MATH_COMMANDS = {
    "ε": r"\epsilon",
    "ρ": r"\rho",
    "λ": r"\lambda",
    "χ": r"\chi",
    "σ": r"\sigma",
    "θ": r"\theta",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
}
HEADING_COMMAND_RE = re.compile(
    r"\\(?P<command>part|chapter|section|subsection|subsubsection|paragraph)\*?\s*\{"
)
SHARED_CONTROL_MARKERS = (
    r"\tableofcontents",
    r"\frontmatter",
    r"\mainmatter",
    r"\backmatter",
    r"\maketitle",
)
TABLE_ENVIRONMENTS = {"table", "table*", "longtable", "tabular", "tabularx"}
LIST_ENVIRONMENTS = {"itemize", "enumerate", "description"}
FUSION_PREAMBLE = r"""
% BUILD_POCKET_POLISHED_FUSION_BEGIN
\definecolor{JpSecondaryInk}{RGB}{62,68,76}
\IfFontExistsTF{Noto Serif CJK JP}{%
  \newCJKfontfamily\JpSecondaryFont{Noto Serif CJK JP}%
}{%
  \newcommand{\JpSecondaryFont}{}%
}
\newcommand{\JpRubyReadingFont}{\fontsize{4.1pt}{4.4pt}\selectfont}
\NewDocumentCommand{\JpRuby}{m m}{%
  \leavevmode
  \begingroup
    \setbox0=\hbox{{\JpSecondaryFont #1}}%
    \setbox1=\hbox{{\JpSecondaryFont\JpRubyReadingFont #2}}%
    \dimen0=\wd0
    \ifdim\wd1>\dimen0 \dimen0=\wd1\fi
    \vbox{%
      \offinterlineskip
      \hbox to \dimen0{\hss\box1\hss}%
      \kern0.10ex
      \hbox to \dimen0{\hss\box0\hss}%
    }%
  \endgroup
  \allowbreak{}%
}
\newenvironment{JpSecondary}{%
  \par\nopagebreak[2]\vspace{0.12em}%
  \begingroup\JpSecondaryFont\fontsize{8.6pt}{14.2pt}\selectfont\color{JpSecondaryInk}%
  \leftskip=1.25em\relax\rightskip=0pt plus .6em\relax
  \parindent=0pt\relax
}{%
  \par\endgroup\vspace{0.38em}%
}
\newcommand{\JpSecondaryHeading}[1]{%
  \par\nopagebreak[4]\vspace{0.08em}%
  {\JpSecondaryFont\fontsize{9pt}{14.5pt}\selectfont\color{JpSecondaryInk}\leftskip=1.25em\relax
   \noindent #1\par}\vspace{0.35em}%
}
% BUILD_POCKET_POLISHED_FUSION_END
"""


def inject_polished_cover_page(
    tex_path: Path,
    cover_path: Path,
    *,
    title: str,
    author: str,
) -> bool:
    """Insert a textless bitmap with a deterministic English/Japanese overlay."""

    if not cover_path.is_file():
        return False
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    text, _ = remove_legacy_full_page_cover(text)
    if r"\usepackage{tikz}" not in text:
        text = text.replace(
            r"\begin{document}",
            r"\usepackage{tikz}" + "\n" + r"\begin{document}",
            1,
        )
    begin = "% BUILD_POCKET_COVER_BEGIN"
    end = "% BUILD_POCKET_COVER_END"
    safe_title = latex_escape_text(title)
    wrapped_title = " ".join(rf"\mbox{{{word}}}" for word in safe_title.split())
    safe_author = latex_escape_text(author)
    author_line = (
        rf"{{\fontsize{{9.4pt}}{{12pt}}\selectfont {safe_author}}}\\[2.4mm]"
        if safe_author
        else ""
    )
    cover_block = (
        begin
        + "\n"
        + r"\clearpage\thispagestyle{empty}%"
        + "\n"
        + r"\begin{tikzpicture}[remember picture,overlay]"
        + "\n"
        + rf"\node[inner sep=0pt] at (current page.center) "
        + rf"{{\includegraphics[width=\paperwidth,height=\paperheight]"
        + rf"{{\detokenize{{{cover_path.resolve().as_posix()}}}}}}};"
        + "\n"
        + r"\node[align=center,text=white,fill=black,fill opacity=.42,text opacity=1,"
        + r"inner xsep=4mm,inner ysep=4mm,text width=.80\paperwidth] "
        + r"at ([yshift=-.04\paperheight]current page.center) {"
        + "\n"
        + rf"{{\sffamily\bfseries\hyphenpenalty=10000\exhyphenpenalty=10000"
        + rf"\fontsize{{16pt}}{{20pt}}\selectfont {wrapped_title}}}\\[3mm]"
        + "\n"
        + author_line
        + r"{\sffamily\fontsize{8.6pt}{11pt}\selectfont English $\cdot$ 日本語}"
        + "\n};\n"
        + r"\end{tikzpicture}\null\clearpage"
        + "\n"
        + end
    )
    block_re = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if block_re.search(text):
        text = block_re.sub(lambda _match: cover_block, text, count=1)
    else:
        text = text.replace(
            r"\begin{document}",
            r"\begin{document}" + "\n" + cover_block,
            1,
        )
    tex_path.write_text(text, encoding="utf-8")
    return True


def remove_legacy_full_page_cover(tex: str) -> tuple[str, int]:
    """Replace, rather than duplicate, a legacy full-page frontmatter cover."""

    frontmatter = re.search(r"\\frontmatter\s*", tex)
    if frontmatter is None:
        return tex, 0
    clearpage = tex.find(r"\clearpage", frontmatter.end())
    if clearpage < 0 or clearpage - frontmatter.end() > 2400:
        return tex, 0
    candidate = tex[frontmatter.end() : clearpage]
    if candidate.count(r"\includegraphics") != 1:
        return tex, 0
    if not all(
        marker in candidate
        for marker in (r"\thispagestyle{empty}", r"\paperwidth", r"\paperheight")
    ):
        return tex, 0
    return tex[: frontmatter.end()] + tex[clearpage + len(r"\clearpage") :], 1


def normalize_unwrapped_math_fragments(tex: str) -> tuple[str, int]:
    """Typeset evidence-clear plain OCR math without rewriting prose.

    A grounded repair can restore a subscript or Greek symbol while leaving
    the resulting expression outside math mode (for example
    ``u_o = log ε``).  Such text is invalid TeX because of the underscore.
    This narrow pass recognizes only a variable-with-subscript logarithm
    relation and preserves its exact symbols in proper TeX math. It also
    normalizes Unicode super/subscripts and short ``unit^-2`` fragments outside
    existing math spans. Longer prose words retain residual superscripts as
    text footnote markers rather than being reinterpreted as equations.
    """

    def replace(match: re.Match[str]) -> str:
        argument = GREEK_MATH_COMMANDS.get(
            match.group("argument"), match.group("argument")
        )
        return (
            rf"\({match.group('lhs')} = {match.group('sign')}\log {argument}\)"
        )

    def replace_plain(plain: str) -> tuple[str, int]:
        count = 0
        plain, changed = PLAIN_LOG_EXPRESSION_RE.subn(replace, plain)
        count += changed
        plain, changed = PLAIN_POWER_INEQUALITY_RE.subn(
            lambda match: rf"\({match.group('left')} < {match.group('right')}\)",
            plain,
        )
        count += changed
        plain, changed = PLAIN_SCALE_FACTOR_RE.subn(
            lambda _match: r"\(a(t) = a_0 t^p\)", plain
        )
        count += changed
        plain, changed = PLAIN_GREEK_POWER_RE.subn(
            lambda match: rf"\(\phi(r) \sim r^{{{match.group('exponent')}}}\Phi\)",
            plain,
        )
        count += changed
        plain, changed = PLAIN_BRACED_NUMERIC_POWER_RE.subn(
            lambda match: (
                r"\("
                + (
                    rf"{match.group('coefficient')} \times "
                    if match.group("coefficient")
                    else ""
                )
                + "10^{"
                + (
                    match.group("exponent")
                    if re.fullmatch(r"[+-]?\d+", match.group("exponent"))
                    else rf"\mathrm{{{match.group('exponent')}}}"
                )
                + r"}\)"
            ),
            plain,
        )
        count += changed
        plain, changed = PLAIN_NUMERIC_POWER_RE.subn(
            lambda match: (
                r"\("
                + (
                    rf"{match.group('coefficient')} \times "
                    if match.group("coefficient")
                    else ""
                )
                + "10^{"
                + (
                    match.group("exponent")
                    if re.fullmatch(r"[+-]?\d+", match.group("exponent"))
                    else rf"\mathrm{{{match.group('exponent')}}}"
                )
                + r"}\)"
            ),
            plain,
        )
        count += changed
        plain, changed = PLAIN_SCIENTIFIC_SUPERSCRIPT_RE.subn(
            lambda match: (
                rf"\({match.group('coefficient')} \times 10^{{"
                + match.group("superscript").translate(SUPERSCRIPT_VALUE)
                + r"}\)"
            ),
            plain,
        )
        count += changed
        plain, changed = PLAIN_SHORT_POWER_RE.subn(
            lambda match: (
                rf"\({match.group('base')}^{{"
                + match.group("superscript").translate(SUPERSCRIPT_VALUE)
                + r"}\)"
            ),
            plain,
        )
        count += changed
        plain, changed = PLAIN_SHORT_SUBSCRIPT_RE.subn(
            lambda match: (
                rf"\({match.group('base')}_{{"
                + match.group("subscript").translate(SUBSCRIPT_VALUE)
                + r"}\)"
            ),
            plain,
        )
        count += changed
        plain, changed = PLAIN_ASCII_SHORT_POWER_RE.subn(
            lambda match: rf"\({match.group('base')}^{{{match.group('exponent')}}}\)",
            plain,
        )
        count += changed
        plain, changed = REMAINING_SUPERSCRIPT_RE.subn(
            lambda match: (
                r"\textsuperscript{"
                + match.group(0).translate(SUPERSCRIPT_VALUE)
                + "}"
            ),
            plain,
        )
        count += changed
        plain, changed = REMAINING_SUBSCRIPT_RE.subn(
            lambda match: (
                r"\textsubscript{"
                + match.group(0).translate(SUBSCRIPT_VALUE)
                + "}"
            ),
            plain,
        )
        count += changed
        plain, changed = re.subn(r"(?<=[})∞])\.(?=[A-Z])", ". ", plain)
        count += changed
        return plain, count

    tex, transport_changes = normalize_transport_formatting(tex)
    spans = [
        (match.start(), match.end())
        for pattern in (INLINE_MATH_RE, MATH_ENV_RE)
        for match in pattern.finditer(tex)
    ]
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    parts: list[str] = []
    cursor = 0
    count = transport_changes
    for start, end in merged:
        plain, replacements = replace_plain(tex[cursor:start])
        parts.extend((plain, tex[start:end]))
        count += replacements
        cursor = end
    plain, replacements = replace_plain(tex[cursor:])
    parts.append(plain)
    count += replacements
    return "".join(parts), count


def braced_argument(tex: str, opening_brace: int) -> tuple[str, int]:
    if opening_brace >= len(tex) or tex[opening_brace] != "{":
        raise ValueError("expected opening brace")
    depth = 0
    escaped = False
    for index in range(opening_brace, len(tex)):
        char = tex[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return tex[opening_brace + 1 : index], index + 1
    raise ValueError("unbalanced TeX argument")


def unwrap_texorpdfstring(tex: str) -> str:
    stripped = tex.strip()
    command = r"\texorpdfstring"
    if not stripped.startswith(command):
        return stripped
    cursor = len(command)
    while cursor < len(stripped) and stripped[cursor].isspace():
        cursor += 1
    display, _ = braced_argument(stripped, cursor)
    return display.strip()


def translated_heading_title(tex: str) -> str | None:
    match = HEADING_COMMAND_RE.search(tex)
    if not match:
        return None
    title, _ = braced_argument(tex, match.end() - 1)
    return unwrap_texorpdfstring(title)


def strip_shared_document_controls(en_tex: str, ja_tex: str) -> str:
    common = os.path.commonprefix((en_tex, ja_tex))
    if not common or not any(marker in common for marker in SHARED_CONTROL_MARKERS):
        return ja_tex
    newline = common.rfind("\n")
    if newline < 0:
        return ja_tex
    return ja_tex[newline + 1 :]


def split_shared_environment_scaffold(en_tex: str, ja_tex: str) -> tuple[str, str, str]:
    """Separate translated inner rows from identical environment closing rows."""

    source_graphics = {
        match.group("detokenized_path") or match.group("path")
        for match in INCLUDEGRAPHICS_RE.finditer(en_tex)
    }
    if source_graphics:
        ja_tex = INCLUDEGRAPHICS_RE.sub(
            lambda match: ""
            if (match.group("detokenized_path") or match.group("path"))
            in source_graphics
            else match.group(0),
            ja_tex,
        )
    en_lines = en_tex.splitlines(keepends=True)
    ja_lines = ja_tex.splitlines(keepends=True)
    while en_lines and ja_lines and en_lines[0] == ja_lines[0]:
        en_lines.pop(0)
        ja_lines.pop(0)
    shared_suffix: list[str] = []
    while en_lines and ja_lines and en_lines[-1] == ja_lines[-1]:
        shared_suffix.insert(0, en_lines.pop())
        ja_lines.pop()
    shared_source_lines = set(en_lines)
    shared_source_stripped = {line.strip() for line in en_lines}
    filtered_ja_lines: list[str] = []
    for line in ja_lines:
        if r"\includegraphics" in line and line.strip() in shared_source_stripped:
            continue
        if line not in shared_source_lines:
            filtered_ja_lines.append(line)
            continue
        # Remove shared environment scaffolding without discarding adjacent
        # syntax that closes a translated command argument. Mathpix commonly
        # emits ``}\begin{itemize}`` on one line after a sidenote; dropping
        # the whole line leaves the translated ``\footnotetext{...`` open.
        residual = ENVIRONMENT_COMMAND_RE.sub("", line)
        if residual.strip():
            filtered_ja_lines.append(residual)
    ja_lines = filtered_ja_lines
    suffix = "".join(shared_suffix)
    if suffix:
        en_body = en_tex[: -len(suffix)]
    else:
        en_body = en_tex
    return en_body, suffix, "".join(ja_lines)


def restore_secondary_list_scaffold(en_tex: str, ja_tex: str) -> str:
    """Wrap translated list items when source-only structural rows were filtered."""

    if not re.search(r"(?m)^\s*\\item\b", ja_tex):
        return ja_tex
    for existing in ("itemize", "enumerate", "description"):
        begin = rf"\begin{{{existing}}}"
        end = rf"\end{{{existing}}}"
        if begin not in ja_tex or end not in ja_tex:
            continue
        prefix, body = ja_tex.split(begin, 1)
        inner, suffix = body.split(end, 1)
        if inner.strip() and not inner.lstrip().startswith(r"\item"):
            inner = "\n\\item " + inner.lstrip()
        return prefix + begin + inner + end + suffix
    environments = [
        match.group("environment")
        for match in ENVIRONMENT_COMMAND_RE.finditer(en_tex)
        if match.group("action") == "begin"
        and match.group("environment") in {"itemize", "enumerate", "description"}
    ]
    if len(environments) != 1:
        return ja_tex
    environment = environments[0]
    begin = rf"\begin{{{environment}}}"
    end = rf"\end{{{environment}}}"
    first_item = re.search(r"(?m)^\s*\\item\b", ja_tex)
    if first_item is None:
        return ja_tex
    prefix = ja_tex[: first_item.start()].rstrip()
    items = ja_tex[first_item.start() :].strip()
    wrapped = f"{begin}\n{items}\n{end}"
    return f"{prefix}\n{wrapped}" if prefix else wrapped


def demote_secondary_captions(tex: str) -> str:
    """Keep translated caption text without emitting a second float caption."""

    tex = re.sub(
        r"\\captionsetup(?:\[[^\]]*\])?\{[^{}]*\}\s*",
        "",
        tex,
    )
    marker = r"\caption{"
    cursor = 0
    parts: list[str] = []
    while True:
        start = tex.find(marker, cursor)
        if start < 0:
            parts.append(tex[cursor:])
            break
        parts.append(tex[cursor:start])
        caption, end = braced_argument(tex, start + len(r"\caption"))
        parts.append(r"\textit{" + caption + "}")
        cursor = end
    return "".join(parts)


def inject_fusion_preamble(tex: str) -> str:
    marker = r"\begin{document}"
    if FUSION_PREAMBLE.strip() in tex or "BUILD_POCKET_POLISHED_FUSION_BEGIN" in tex:
        return tex
    if marker not in tex:
        raise ValueError("cannot add bilingual fusion macros: missing document start")
    return tex.replace(marker, FUSION_PREAMBLE + "\n" + marker, 1)


def restore_split_optional_linebreaks(tex: str) -> str:
    """Restore caption boundaries split immediately before ``\\[dimension]``."""

    tex = re.sub(
        r"(?m)(?P<prefix>\\end\{JpSecondary\}[ \t]*\n)"
        r"[ \t]*\\\\\[\d+(?:\.\d+)?(?:pt|mm|cm|em|ex)\][ \t]*$",
        lambda match: match.group("prefix") + r"\par",
        tex,
    )
    tex = re.sub(
        r"(?<!\\)\\\[(?P<space>\d+(?:\.\d+)?(?:pt|mm|cm|em|ex))\]",
        lambda match: rf"\\[{match.group('space')}]",
        tex,
    )
    tex = re.sub(
        r"(?P<caption>\\caption\{[^{}\n]*)\}"
        r"(?P<break>\\\\\[\d+(?:\.\d+)?(?:pt|mm|cm|em|ex)\])",
        lambda match: match.group("caption") + match.group("break"),
        tex,
    )
    return re.sub(
        r"\\\\(?P<space>\s*)\[(?!\d+(?:\.\d+)?(?:pt|mm|cm|em|ex)\])",
        lambda match: r"\\{}" + match.group("space") + "[",
        tex,
    )


def update_open_environments(tex: str, stack: list[str]) -> None:
    """Track source environments that cross translation-segment boundaries."""

    for match in ENVIRONMENT_COMMAND_RE.finditer(tex):
        environment = match.group("environment")
        if match.group("action") == "begin":
            stack.append(environment)
            continue
        if not stack or stack[-1] != environment:
            current = stack[-1] if stack else "none"
            raise ValueError(
                f"malformed source environment: closing {environment} while {current} is open"
            )
        stack.pop()


def has_balanced_complete_environment(tex: str, environments: set[str]) -> bool:
    """Return true when ``tex`` contains and balances a target environment."""

    if not any(rf"\begin{{{environment}}}" in tex for environment in environments):
        return False
    stack: list[str] = []
    try:
        update_open_environments(tex, stack)
    except ValueError:
        return False
    return not stack


def fuse_english_main_japanese_secondary(
    segments: list[dict[str, Any]],
    *,
    furigana_overrides: dict[str, str] | None = None,
) -> tuple[str, FuriganaStats]:
    parts: list[str] = []
    furigana = FuriganaStats()
    pending_en: list[str] = []
    pending_ja: list[str] = []
    open_environments: list[str] = []
    pending_crosses_environment = False
    furigana_overrides = furigana_overrides or {}

    def apply_furigana_overrides(tex: str) -> str:
        for surface, reading in furigana_overrides.items():
            if not isinstance(surface, str) or not surface:
                raise ValueError("furigana override has an empty surface form")
            if not isinstance(reading, str) or not reading:
                raise ValueError(f"furigana override has no reading: {surface}")
            tex = tex.replace(surface, rf"\JpRuby{{{surface}}}{{{reading}}}")
        return tex

    def emit_pending() -> None:
        nonlocal pending_crosses_environment
        if not pending_en:
            return
        en_tex = "".join(pending_en)
        ja_tex = "".join(pending_ja)
        crosses_environment = pending_crosses_environment
        pending_crosses_environment = False
        pending_en.clear()
        pending_ja.clear()
        if en_tex.strip() == ja_tex.strip() or not ja_tex.strip():
            parts.append(en_tex)
            return
        heading = translated_heading_title(ja_tex)
        if heading is not None:
            parts.append(en_tex)
            heading = apply_furigana_overrides(heading)
            annotated, current = annotate_japanese_tex(heading)
            furigana.merge(current)
            parts.append(f"\n\\JpSecondaryHeading{{{annotated}}}\n")
            return
        # A paragraph-style secondary environment cannot begin between table
        # rows: its leading \par/\nopagebreak expands to \noalign and XeTeX
        # rejects it. Keep each language as a complete table instead. This also
        # covers Mathpix tables whose protected opening scaffold and translated
        # closing rows were split into adjacent source segments.
        has_complete_en_table = any(
            rf"\begin{{{environment}}}" in en_tex
            for environment in TABLE_ENVIRONMENTS
        )
        has_complete_ja_table = any(
            rf"\begin{{{environment}}}" in ja_tex
            for environment in TABLE_ENVIRONMENTS
        )
        if has_complete_en_table and has_complete_ja_table:
            parts.append(en_tex)
            secondary = apply_furigana_overrides(ja_tex.strip())
            secondary, current = annotate_japanese_tex(secondary)
            furigana.merge(current)
            parts.append(
                "\n\\begingroup\n"
                "\\JpSecondaryFont\\fontsize{8.6pt}{14.2pt}\\selectfont"
                "\\color{JpSecondaryInk}\n"
                f"{secondary}\n"
                "\\endgroup\n"
            )
            return
        # Lists that span source segments must be emitted as two complete,
        # sibling structures. Filtering shared list commands line by line can
        # remove a nested ``\begin{enumerate}`` while retaining its closing
        # command, and inserting the secondary prose before the source list
        # closes creates illegal cross-environment nesting.
        if (
            crosses_environment
            and has_balanced_complete_environment(en_tex, LIST_ENVIRONMENTS)
            and has_balanced_complete_environment(ja_tex, LIST_ENVIRONMENTS)
        ):
            parts.append(en_tex)
            secondary = demote_secondary_captions(ja_tex.strip())
            secondary = apply_furigana_overrides(secondary)
            secondary, current = annotate_japanese_tex(secondary)
            furigana.merge(current)
            parts.append(
                f"\n\\begin{{JpSecondary}}\n{secondary}\n\\end{{JpSecondary}}\n"
            )
            return
        secondary = strip_shared_document_controls(en_tex, ja_tex)
        trailing_scaffold = ""
        if crosses_environment:
            en_tex, trailing_scaffold, secondary = split_shared_environment_scaffold(
                en_tex, secondary
            )
            secondary = restore_secondary_list_scaffold(
                en_tex + trailing_scaffold, secondary
            )
        parts.append(en_tex)
        secondary = secondary.strip()
        # A translated caption is useful prose but must not enlarge the
        # source figure float. Close a figure before emitting its Japanese
        # secondary block; this keeps the image/caption float bounded while
        # preserving reading order immediately below it. Tables retain their
        # existing in-environment translation structure.
        if trailing_scaffold and r"\end{figure}" in trailing_scaffold:
            parts.append(trailing_scaffold)
            trailing_scaffold = ""
        if secondary:
            secondary = restore_secondary_list_scaffold(en_tex, secondary)
            secondary = demote_secondary_captions(secondary)
            secondary = apply_furigana_overrides(secondary)
            secondary, current = annotate_japanese_tex(secondary)
            furigana.merge(current)
            parts.append(
                f"\n\\begin{{JpSecondary}}\n{secondary}\n\\end{{JpSecondary}}\n"
            )
        parts.append(trailing_scaffold)

    for segment in segments:
        if segment["kind"] == "protected":
            source_tex = segment["source_tex"]
            environment_commands = list(ENVIRONMENT_COMMAND_RE.finditer(source_tex))
            table_scaffold = any(
                environment in TABLE_ENVIRONMENTS for environment in open_environments
            ) or any(
                match.group("action") == "begin"
                and match.group("environment") in TABLE_ENVIRONMENTS
                for match in environment_commands
            )
            crosses_environment_boundary = bool(open_environments) or bool(
                any(match.group("environment") != "document" for match in environment_commands)
            )
            if crosses_environment_boundary:
                pending_crosses_environment = True
                pending_en.append(source_tex)
                # Figures and other protected objects remain source-only. Table
                # scaffolds must exist in both streams so translated alignment
                # rows are never emitted outside a tabular/longtable context.
                pending_ja.append(source_tex if table_scaffold else "")
                update_open_environments(source_tex, open_environments)
                if not open_environments:
                    emit_pending()
            else:
                emit_pending()
                parts.append(source_tex)
            continue
        en_tex = segment["en_tex"]
        ja_tex = segment["ja_tex"]
        if ENVIRONMENT_COMMAND_RE.search(en_tex) or r"\includegraphics" in en_tex:
            pending_crosses_environment = True
        pending_en.append(en_tex)
        pending_ja.append(ja_tex)
        update_open_environments(en_tex, open_environments)
        if not open_environments:
            emit_pending()
    if open_environments:
        raise ValueError(
            "unclosed source environments at fusion end: "
            + ", ".join(open_environments)
        )
    emit_pending()
    if furigana.unknown_tokens:
        examples = ", ".join(dict.fromkeys(furigana.unknown_tokens[:12]))
        raise ValueError(f"Japanese furigana missing for: {examples}")
    fused = restore_split_optional_linebreaks("".join(parts))
    fused = inject_fusion_preamble(fused)
    # Environment fusion can move a formerly inline optional line break onto
    # its own line when the Japanese secondary block is inserted. Normalize
    # once more against the final structure so XeLaTeX never sees a bare
    # ``\\[0pt]`` command.
    return restore_split_optional_linebreaks(fused), furigana


def copy_and_rewrite_figures(tex: str, destination: Path) -> str:
    destination.mkdir(parents=True, exist_ok=True)
    copied: dict[Path, Path] = {}

    def replace(match: re.Match[str]) -> str:
        raw = match.group("detokenized_path") or match.group("path")
        source = Path(raw)
        if not source.is_absolute():
            source = (ROOT / source).resolve()
        if not source.exists():
            raise FileNotFoundError(f"referenced figure does not exist: {raw}")
        if source not in copied:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
            target = destination / f"{digest}-{source.name}"
            if not target.exists():
                shutil.copy2(source, target)
            copied[source] = target
        rendered = copied[source].resolve().as_posix()
        if match.group("detokenize"):
            rendered = rf"\detokenize{{{rendered}}}"
        return match.group("prefix") + rendered + match.group("suffix")

    return INCLUDEGRAPHICS_RE.sub(replace, tex)


def center_standalone_figures(tex: str) -> tuple[str, int]:
    lines = tex.splitlines(keepends=True)
    centered = 0
    protected_depth = 0
    result: list[str] = []
    protected_environments = ("center", "figure", "figure*", "table", "table*", "longtable", "tabular", "tabularx")
    for line in lines:
        depth_before = protected_depth
        for environment in protected_environments:
            protected_depth += line.count(rf"\begin{{{environment}}}")
            protected_depth -= line.count(rf"\end{{{environment}}}")
        match = STANDALONE_IMAGE_RE.match(line.rstrip("\r\n"))
        if (
            match
            and depth_before == 0
            and r"\paperwidth" not in line
            and r"\paperheight" not in line
            and "assets/covers/" not in line
        ):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            indent = match.group("indent")
            result.extend(
                [
                    f"{indent}\\begin{{center}}{newline}",
                    f"{indent}{match.group('image')}{match.group('tail')}{newline}",
                    f"{indent}\\end{{center}}{newline}",
                ]
            )
            centered += 1
        else:
            result.append(line)
    return "".join(result), centered


def normalize_full_bleed_images(tex: str) -> tuple[str, int]:
    """Keep intentional cover bleed centered without an overfull-box warning."""

    def replace(match: re.Match[str]) -> str:
        indent = match.group("indent")
        image = match.group("image")
        return (
            f"{indent}\\newgeometry{{margin=0pt}}\n"
            f"{indent}\\thispagestyle{{empty}}\n"
            f"{indent}\\noindent{image}\n"
            f"{indent}\\restoregeometry"
        )

    return FULL_BLEED_IMAGE_RE.subn(replace, tex)


def fit_short_simple_longtables(tex: str, *, max_rows: int = 12) -> tuple[str, int]:
    """Width-fit compact OCR tables that do not need page breaking.

    Pandoc emits even small tables as ``longtable``. On A6 paper, simple
    multi-column tables with long cells can overflow badly because ``l/c/r``
    columns never wrap. Compact tables are safe to render as ``tabular`` in an
    fixed-width ``tabular``; larger tables stay as ``longtable`` so they can
    span pages.
    """

    converted = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal converted
        body = match.group("body")
        row_count = body.count(r"\\")
        if row_count > max_rows:
            return match.group(0)
        body = re.sub(r"(?m)^\s*\\endhead\s*$\n?", "", body)
        columns = match.group("columns")
        converted += 1
        return (
            "\\begin{center}\n"
            "\\resizebox{.84\\paperwidth}{!}{%\n"
            f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}"
            f"{body}"
            "\\end{tabular}%\n"
            "}\n"
            "\\end{center}"
        )

    return SIMPLE_LONGTABLE_RE.sub(replace, tex), converted


def fit_short_complex_longtables(tex: str, *, max_rows: int = 12) -> tuple[str, int]:
    """Width-fit compact longtables whose column spec contains nested braces."""

    marker = r"\begin{longtable}[]"
    end_marker = r"\end{longtable}"
    converted = 0
    cursor = 0
    parts: list[str] = []

    def column_count(spec: str) -> int:
        count = 0
        depth = 0
        escaped = False
        for index, char in enumerate(spec):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth = max(0, depth - 1)
                continue
            if depth == 0 and char in "lcr":
                count += 1
            elif (
                depth == 0
                and char in "pmb"
                and index + 1 < len(spec)
                and spec[index + 1] == "{"
            ):
                count += 1
        return count

    while True:
        start = tex.find(marker, cursor)
        if start < 0:
            parts.append(tex[cursor:])
            break
        parts.append(tex[cursor:start])
        spec_start = start + len(marker)
        while spec_start < len(tex) and tex[spec_start].isspace():
            spec_start += 1
        if spec_start >= len(tex) or tex[spec_start] != "{":
            parts.append(tex[start : start + len(marker)])
            cursor = start + len(marker)
            continue
        try:
            spec, body_start = braced_argument(tex, spec_start)
        except ValueError:
            parts.append(tex[start : start + len(marker)])
            cursor = start + len(marker)
            continue
        end = tex.find(end_marker, body_start)
        if end < 0:
            parts.append(tex[start:])
            break
        body = tex[body_start:end]
        row_count = body.count(r"\\")
        if row_count > max_rows or re.fullmatch(r"@\{\}[lcr]+@\{\}", spec):
            parts.append(tex[start : end + len(end_marker)])
        else:
            body = re.sub(r"(?m)^\s*\\endhead\s*$\n?", "", body)
            columns = column_count(spec)
            fitted_spec = (
                "@{}" + "l" + "c" * (columns - 1) + "@{}"
                if columns > 0
                else spec
            )
            parts.append(
                "\\begin{center}\n"
                "\\resizebox{.84\\paperwidth}{!}{%\n"
                f"\\begin{{tabular}}{{{fitted_spec}}}"
                f"{body}"
                "\\end{tabular}%\n"
                "}\n"
                "\\end{center}"
            )
            converted += 1
        cursor = end + len(end_marker)
    return "".join(parts), converted


def wrap_long_simple_longtables(tex: str, *, min_rows: int = 13) -> tuple[str, int]:
    """Give long simple tables wrapping columns while retaining page breaks."""

    wrapped = 0

    def visible_length(cell: str) -> int:
        cell = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", "", cell)
        cell = re.sub(r"[{}~]", "", cell)
        return len(re.sub(r"\s+", " ", cell).strip())

    def widths_for(body: str, column_count: int) -> list[float]:
        maxima = [1] * column_count
        for row in re.split(r"\\\\(?:\[[^\]]*\])?\s*(?:\n|$)", body):
            if row.count("&") != column_count - 1:
                continue
            cells = re.split(r"(?<!\\)&", row)
            for index, cell in enumerate(cells):
                maxima[index] = max(maxima[index], visible_length(cell))
        total_width = 0.92 if column_count == 2 else 0.88 if column_count == 3 else 0.84
        minimum = 0.10 if column_count == 2 else 0.07
        flexible = total_width - minimum * column_count
        weight_sum = sum(maxima)
        widths = [minimum + flexible * value / weight_sum for value in maxima]
        if column_count == 2:
            dominant = 0 if maxima[0] >= maxima[1] else 1
            if maxima[dominant] >= 2.5 * maxima[1 - dominant]:
                widths[dominant] = 0.80
                widths[1 - dominant] = total_width - 0.80
        return widths

    def replace(match: re.Match[str]) -> str:
        nonlocal wrapped
        body = match.group("body")
        row_count = body.count(r"\\")
        columns = match.group("columns")
        if row_count < min_rows or len(columns) < 2:
            return match.group(0)
        widths = widths_for(body, len(columns))
        alignments = {
            "l": r">{\raggedright\arraybackslash}",
            "c": r">{\centering\arraybackslash}",
            "r": r">{\raggedleft\arraybackslash}",
        }
        specification = "".join(
            f"{alignments[column]}p{{{width:.3f}\\linewidth}}"
            for column, width in zip(columns, widths)
        )
        wrapped += 1
        return (
            f"\\begin{{longtable}}[]{{@{{}}{specification}@{{}}}}"
            f"{body}"
            "\\end{longtable}"
        )

    return SIMPLE_LONGTABLE_RE.sub(replace, tex), wrapped


def pocket_layout(tex: str) -> str:
    pocket_geometry_package = (
        r"\usepackage[paperwidth=105mm,paperheight=148mm,inner=6.5mm,"
        r"outer=5.5mm,top=8mm,bottom=12mm]{geometry}"
    )
    pocket_geometry_command = (
        r"\geometry{paperwidth=105mm,paperheight=148mm,inner=6.5mm,"
        r"outer=5.5mm,top=8mm,bottom=12mm}"
    )
    text, count = GEOMETRY_COMMAND_RE.subn(
        lambda _match: pocket_geometry_command,
        tex,
        count=1,
    )
    if not count:
        text, count = EXACT_GEOMETRY_RE.subn(
            lambda _match: pocket_geometry_package,
            text,
            count=1,
        )
    if not count:
        text, count = GEOMETRY_PACKAGE_RE.subn(
            lambda _match: pocket_geometry_package,
            text,
            count=1,
        )
    if not count:
        raise ValueError("cannot derive pocket layout: source geometry was not recognized")
    text = SELF_LABELED_HREF_RE.sub(
        lambda match: rf"\url{{{match.group('target')}}}"
        if match.group("target") == match.group("label")
        else match.group(0),
        text,
    )
    if r"\usepackage{xurl}" not in text:
        if r"\usepackage{hyperref}" in text:
            text = text.replace(
                r"\usepackage{hyperref}",
                r"\usepackage{xurl}" + "\n" + r"\usepackage{hyperref}",
                1,
            )
        else:
            text = text.replace(
                r"\begin{document}",
                r"\usepackage{xurl}" + "\n" + r"\begin{document}",
                1,
            )
    if r"\usepackage{seqsplit}" not in text:
        text = text.replace(
            r"\begin{document}",
            r"\usepackage{seqsplit}" + "\n" + r"\begin{document}",
            1,
        )
    # Preserve every source digit while allowing extreme exact decimals to
    # wrap on A6 pages.  Scientific re-expression would change the source;
    # seqsplit changes only line-breaking behavior.
    text = re.sub(
        r"(?<![\\\w])(?P<number>\.\d{40,}|\d{50,})(?!\d)",
        lambda match: rf"\seqsplit{{{match.group('number')}}}",
        text,
    )
    text = re.sub(r"\\setstretch\{1\.0?8\}", lambda _match: r"\setstretch{1.12}", text)
    text = re.sub(r"\\linespread\{1\.0[0-9]\}", lambda _match: r"\linespread{1.10}", text)
    text = text.replace(
        r"\begin{adjustbox}{max width=\linewidth}\begin{tabular}",
        r"\begin{adjustbox}{max width=\linewidth,max totalheight=.92\textheight,"
        r"keepaspectratio}\begin{tabular}",
    )
    text = text.replace(
        r"\begingroup\small\setlength{\tabcolsep}{3pt}\begin{longtable}",
        r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
    )
    text = wrap_wide_display_math(text, layout="pocket")
    text, _ = wrap_wide_math_environments(text, layout="pocket")
    if r"\Needspace" in text and r"\usepackage{needspace}" not in text:
        text = text.replace(
            r"\begin{document}",
            r"\usepackage{needspace}" + "\n" + r"\begin{document}",
            1,
        )
    return apply_pocket_footer_defaults(text)


def compile_variant(
    book_root: Path,
    language: str,
    layout: str,
    tex: str,
    cover: Path | None,
    *,
    expected_graphics: int,
    title: str,
    author: str,
) -> dict[str, Any]:
    variant_root = book_root / layout / language
    tex_path = variant_root / "tex/book.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(tex, encoding="utf-8")
    graphics_before_cover = tex.count(r"\includegraphics")
    injected_cover_count = 0
    if cover and cover.exists():
        injected_cover_count = int(
            inject_polished_cover_page(
                tex_path,
                cover,
                title=title,
                author=author,
            )
        )
    rendered_tex = tex_path.read_text(encoding="utf-8", errors="replace")
    cover_graphics_delta = rendered_tex.count(r"\includegraphics") - graphics_before_cover
    report = compile_tex(tex_path, variant_root / "book.pdf")
    rendered_expected = expected_graphics + cover_graphics_delta
    report["source_includegraphics_count"] = expected_graphics
    report["injected_cover_count"] = injected_cover_count
    report["cover_graphics_delta"] = cover_graphics_delta
    report["expected_includegraphics_count"] = rendered_expected
    report["objects_complete"] = report.get("includegraphics_count") == rendered_expected
    report["searchable_text_present"] = report.get("text_chars", 0) >= 1000
    report["layout_clean"] = (
        not report.get("latex_error_markers")
        and report.get("worst_overfull_pt", 0) <= 2.0
        and report["objects_complete"]
        and report["searchable_text_present"]
    )
    return report


def assemble(book_id: str, *, compile_pdfs: bool) -> dict[str, Any]:
    book_root = OUTPUT_ROOT / book_id
    manifest = read_json(book_root / "tasks/manifest.json")
    segments = read_jsonl(book_root / "source/segments.jsonl")
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    source_tex = Path(ROOT / manifest["source_exact_tex"]).read_text(encoding="utf-8")
    validation_profile = manifest.get("validation_profile", "prose_exact")
    source_inventory = inventory(source_tex)
    task_segment_map: dict[str, dict[str, Any]] = {}
    output_segment_map: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for task in tasks:
        output_path = book_root / "json" / f"{task['chunk_id']}.json"
        if not output_path.exists():
            missing.append(task["chunk_id"])
            continue
        output = read_json(output_path)
        errors = validate_chunk_output(task, output)
        if errors:
            raise ValueError(f"{task['chunk_id']} failed revalidation: {'; '.join(errors[:8])}")
        for task_segment, output_segment in zip(task["segments"], output["segments"]):
            segment_id = task_segment["segment_id"]
            task_segment_map[segment_id] = task_segment
            output_segment_map[segment_id] = output_segment
    if missing:
        return {
            "book_id": book_id,
            "status": "waiting_for_chunks",
            "complete_chunks": len(tasks) - len(missing),
            "chunk_count": len(tasks),
            "missing": missing,
        }

    assembled: dict[str, str] = {}
    normalized_math_fragments: dict[str, int] = {"en": 0, "ja": 0}
    merged_rows: list[dict[str, Any]] = []
    for language in ("en", "ja"):
        parts: list[str] = []
        for segment in segments:
            segment_id = segment["segment_id"]
            if segment["kind"] == "protected":
                rendered = segment["source_tex"]
            else:
                rendered = restored_segment_output(
                    task_segment_map[segment_id],
                    output_segment_map[segment_id],
                    language,
                )
                rendered, count = normalize_unwrapped_math_fragments(rendered)
                normalized_math_fragments[language] += count
            parts.append(rendered)
        assembled[language] = "".join(parts)
        differences = compare_inventory(source_tex, assembled[language])
        if differences:
            raise ValueError(f"{book_id}/{language} protected inventory mismatch: {'; '.join(differences[:8])}")

    for segment in segments:
        segment_id = segment["segment_id"]
        row = {
            "segment_id": segment_id,
            "kind": segment["kind"],
            "source_sha256": segment["source_sha256"],
        }
        if segment["kind"] == "protected":
            row.update({"source_tex": segment["source_tex"], "en_tex": segment["source_tex"], "ja_tex": segment["source_tex"]})
        else:
            output = output_segment_map[segment_id]
            task_segment = task_segment_map[segment_id]
            en_tex, _ = normalize_unwrapped_math_fragments(
                restored_segment_output(task_segment, output, "en")
            )
            ja_tex, _ = normalize_unwrapped_math_fragments(
                restored_segment_output(task_segment, output, "ja")
            )
            row.update(
                {
                    "source_tex": segment["source_tex"],
                    "en_tex": en_tex,
                    "ja_tex": ja_tex,
                    "changes": output["changes"],
                    "unresolved": output["unresolved"],
                }
            )
        merged_rows.append(row)
    write_json(
        book_root / "data/book.json",
        {
            "schema_version": 1,
            "book_id": book_id,
            "title": manifest["title"],
            "source": manifest["source"],
            "source_exact_tex_sha256": manifest["source_tex_sha256"],
            "languages": ["en", "ja"],
            "segments": merged_rows,
        },
    )

    fused, furigana = fuse_english_main_japanese_secondary(
        merged_rows,
        furigana_overrides=manifest.get("furigana_overrides", {}),
    )
    layout_replacement_plan = manifest.get("layout_replacement_plan")
    layout_replacement_count = 0
    if layout_replacement_plan:
        plan_path = ROOT / str(layout_replacement_plan)
        plan = read_json(plan_path)
        rules = plan.get("replacements") if isinstance(plan, dict) else None
        if not isinstance(rules, list):
            raise ValueError(f"layout replacement plan has no replacements array: {plan_path}")
        fused, layout_changes = apply_exact_text_replacements(fused, rules)
        layout_replacement_count = len(layout_changes)
    centered_figures: dict[str, int] = {"en-main-ja": 0}
    normalized_full_bleed: dict[str, int] = {"en-main-ja": 0}
    fitted_short_tables: dict[str, int] = {"en-main-ja": 0}
    wrapped_long_tables: dict[str, int] = {"en-main-ja": 0}
    fitted_inline_math: dict[str, int] = {"en-main-ja": 0}
    if validation_profile == "technical_exact":
        fused, centered_figures["en-main-ja"] = center_standalone_figures(fused)
        fused, normalized_full_bleed["en-main-ja"] = normalize_full_bleed_images(fused)
        fused, fitted_short_tables["en-main-ja"] = fit_short_simple_longtables(fused)
        fused, complex_short_tables = fit_short_complex_longtables(fused)
        fitted_short_tables["en-main-ja"] += complex_short_tables
        fused, wrapped_long_tables["en-main-ja"] = wrap_long_simple_longtables(fused)
        fused, fitted_inline_math["en-main-ja"] = wrap_wide_inline_math(
            fused, layout="pocket"
        )

    figure_root = book_root / "assets/figures"
    fused = copy_and_rewrite_figures(fused, figure_root)
    source_cover = resolve_cover_source(book_id, manifest)
    cover: Path | None = None
    if source_cover is not None:
        cover = book_root / "cover/cover.png"
        cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_cover, cover)

    reports: dict[str, Any] = {}
    if compile_pdfs:
        reports["pocket_en_main_ja"] = compile_variant(
            book_root,
            "en-main-ja",
            "pocket-large-font",
            pocket_layout(fused),
            cover,
            expected_graphics=source_inventory["includegraphics"],
            title=manifest["title"],
            author=manifest.get("author", ""),
        )
    else:
        pocket_tex = book_root / "pocket-large-font/en-main-ja/tex/book.tex"
        pocket_tex.parent.mkdir(parents=True, exist_ok=True)
        pocket_tex.write_text(pocket_layout(fused), encoding="utf-8")

    layout_issues = [key for key, report in reports.items() if not report.get("layout_clean")]
    status = {
        "book_id": book_id,
        "status": "complete" if compile_pdfs and not layout_issues else "needs_layout_review" if layout_issues else "assembled",
        "chunk_count": len(tasks),
        "segment_count": len(segments),
        "languages": ["en", "ja"],
        "main_language": "en",
        "secondary_languages": ["ja"],
        "edition": "english_main_japanese_secondary",
        "furigana": {
            "ruby_count": furigana.ruby_count,
            "fallback_count": furigana.fallback_count,
            "unknown_count": len(furigana.unknown_tokens),
            "method": "fugashi-unidic-lite-local-word-level",
        },
        "reports": reports,
        "layout_issues": layout_issues,
        "source_inventory_verified": True,
        "source_inventory": source_inventory,
        "validation_profile": validation_profile,
        "centered_standalone_figures": centered_figures,
        "normalized_full_bleed_images": normalized_full_bleed,
        "fitted_short_simple_longtables": fitted_short_tables,
        "wrapped_long_simple_longtables": wrapped_long_tables,
        "fitted_oversized_inline_math": fitted_inline_math,
        "normalized_unwrapped_math_fragments": normalized_math_fragments,
        "evidence_backed_layout_replacements": layout_replacement_count,
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(book_root / "status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--no-compile", action="store_true")
    args = parser.parse_args()
    status = assemble(args.book_id, compile_pdfs=not args.no_compile)
    print(status)
    return 0 if status["status"] in {"complete", "assembled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
