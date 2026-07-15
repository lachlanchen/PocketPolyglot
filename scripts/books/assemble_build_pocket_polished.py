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
)
from japanese_tex_furigana import FuriganaStats, annotate_japanese_tex
from pocket_polished_common import (
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
    r"^(?P<indent>[ \t]*)(?:\\noindent[ \t]*)?"
    r"(?P<image>\\includegraphics(?:\[[^\]]*\])?\{[^{}]+\})"
    r"(?P<tail>(?:[ \t]*\\(?:par|smallskip|medskip|bigskip))*)[ \t]*$"
)
SIMPLE_LONGTABLE_RE = re.compile(
    r"\\begin\{longtable\}\[\]\{@\{\}(?P<columns>[lcr]+)@\{\}\}"
    r"(?P<body>.*?)"
    r"\\end\{longtable\}",
    re.S,
)
PLAIN_LOG_EXPRESSION_RE = re.compile(
    r"(?<![\\$A-Za-z0-9_])(?P<lhs>[A-Za-z]+_[A-Za-z0-9]+)\s*=\s*"
    r"(?P<sign>[+-]?)log\s*(?P<argument>[ερλχσθαβγδA-Za-z][A-Za-z0-9_]*)"
)
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
ENVIRONMENT_COMMAND_RE = re.compile(
    r"\\(?P<action>begin|end)\{(?P<environment>[A-Za-z*@]+)\}"
)
SHARED_CONTROL_MARKERS = (
    r"\tableofcontents",
    r"\frontmatter",
    r"\mainmatter",
    r"\backmatter",
    r"\maketitle",
)
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
    if r"\usepackage{tikz}" not in text:
        text = text.replace(
            r"\begin{document}",
            r"\usepackage{tikz}" + "\n" + r"\begin{document}",
            1,
        )
    begin = "% BUILD_POCKET_COVER_BEGIN"
    end = "% BUILD_POCKET_COVER_END"
    safe_title = latex_escape_text(title)
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
        + rf"{{\sffamily\bfseries\fontsize{{18pt}}{{22pt}}\selectfont {safe_title}}}\\[3mm]"
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
    ja_lines = [
        line
        for line in ja_lines
        if line not in shared_source_lines
        and not (
            r"\includegraphics" in line and line.strip() in shared_source_stripped
        )
    ]
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
    environments = [
        match.group("environment")
        for match in ENVIRONMENT_COMMAND_RE.finditer(en_tex)
        if match.group("action") == "begin"
        and match.group("environment") in {"itemize", "enumerate", "description"}
    ]
    if len(environments) != 1:
        return ja_tex
    environment = environments[0]
    if re.search(rf"\\begin\{{{re.escape(environment)}\}}", ja_tex):
        return ja_tex
    return f"\\begin{{{environment}}}\n{ja_tex.strip()}\n\\end{{{environment}}}"


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


def fuse_english_main_japanese_secondary(
    segments: list[dict[str, Any]],
) -> tuple[str, FuriganaStats]:
    parts: list[str] = []
    furigana = FuriganaStats()
    pending_en: list[str] = []
    pending_ja: list[str] = []
    open_environments: list[str] = []
    pending_crosses_environment = False

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
            annotated, current = annotate_japanese_tex(heading)
            furigana.merge(current)
            parts.append(f"\n\\JpSecondaryHeading{{{annotated}}}\n")
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
        if secondary:
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
            crosses_environment_boundary = bool(open_environments) or bool(
                any(match.group("environment") != "document" for match in environment_commands)
            )
            if crosses_environment_boundary:
                pending_crosses_environment = True
                pending_en.append(source_tex)
                # Protected structural/object rows belong only to the source
                # stream. The secondary stream receives translated text rows;
                # shared closing scaffolds are removed before insertion.
                pending_ja.append("")
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
    return inject_fusion_preamble(restore_split_optional_linebreaks("".join(parts))), furigana


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
        return f"{indent}\\noindent\\makebox[\\textwidth][c]{{{image}}}"

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
    text = re.sub(r"\\setstretch\{1\.0?8\}", lambda _match: r"\setstretch{1.12}", text)
    text = re.sub(r"\\linespread\{1\.0[0-9]\}", lambda _match: r"\linespread{1.10}", text)
    text = text.replace(
        r"\begingroup\small\setlength{\tabcolsep}{3pt}\begin{longtable}",
        r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
    )
    text = wrap_wide_display_math(text, layout="pocket")
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
    report = compile_tex(tex_path, variant_root / "book.pdf")
    rendered_expected = expected_graphics + injected_cover_count
    report["source_includegraphics_count"] = expected_graphics
    report["injected_cover_count"] = injected_cover_count
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

    fused, furigana = fuse_english_main_japanese_secondary(merged_rows)
    centered_figures: dict[str, int] = {"en-main-ja": 0}
    normalized_full_bleed: dict[str, int] = {"en-main-ja": 0}
    fitted_short_tables: dict[str, int] = {"en-main-ja": 0}
    if validation_profile == "technical_exact":
        fused, centered_figures["en-main-ja"] = center_standalone_figures(fused)
        fused, normalized_full_bleed["en-main-ja"] = normalize_full_bleed_images(fused)
        fused, fitted_short_tables["en-main-ja"] = fit_short_simple_longtables(fused)
        fused = wrap_wide_display_math(fused, layout="exact")

    figure_root = book_root / "assets/figures"
    fused = copy_and_rewrite_figures(fused, figure_root)
    source_cover = ROOT / "build-pocket" / book_id / "cover/cover.png"
    cover: Path | None = None
    if source_cover.exists():
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
        "normalized_unwrapped_math_fragments": normalized_math_fragments,
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
