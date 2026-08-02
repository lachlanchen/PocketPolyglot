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
    normalize_bold_greek_commands,
    relocate_nested_math_tags,
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
TEXT_SUPERSCRIPT_ACCIDENTAL_RE = re.compile(
    r"\\textsuperscript\{(?P<symbols>(?:\\(?:flat|sharp|natural)){1,2})\}"
)
GREEK_MATH_COMMANDS = {
    "Α": r"\mathrm{A}",
    "Β": r"\mathrm{B}",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Ε": r"\mathrm{E}",
    "Ζ": r"\mathrm{Z}",
    "Η": r"\mathrm{H}",
    "Θ": r"\Theta",
    "Ι": r"\mathrm{I}",
    "Κ": r"\mathrm{K}",
    "Λ": r"\Lambda",
    "Μ": r"\mathrm{M}",
    "Ν": r"\mathrm{N}",
    "Ξ": r"\Xi",
    "Ο": r"\mathrm{O}",
    "Π": r"\Pi",
    "Ρ": r"\mathrm{P}",
    "Σ": r"\Sigma",
    "Τ": r"\mathrm{T}",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Χ": r"\mathrm{X}",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    "ε": r"\epsilon",
    "ϵ": r"\epsilon",
    "ρ": r"\rho",
    "λ": r"\lambda",
    "χ": r"\chi",
    "σ": r"\sigma",
    "θ": r"\theta",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ζ": r"\zeta",
    "η": r"\eta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "ο": r"\mathrm{o}",
    "π": r"\pi",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "ϕ": r"\varphi",
    "ψ": r"\psi",
    "ω": r"\omega",
}
CYRILLIC_RUN_RE = re.compile(r"[\u0400-\u052f]+")
TEXT_SYMBOL_REPLACEMENTS = {
    "◇": r"\(\diamond\)",
}
HEADING_COMMAND_RE = re.compile(
    r"\\(?P<command>part|chapter|section|subsection|subsubsection|paragraph)\*?\s*\{"
)
LABEL_COMMAND_RE = re.compile(r"\\label\{[^{}]*\}")
SECONDARY_PAGE_CONTROL_RE = re.compile(
    r"\\(?:clearpage|newpage|pagebreak|nopagebreak|frontmatter|mainmatter|backmatter)"
    r"(?:\[[^\]]*\])?\s*"
)
JAPANESE_SCRIPT_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆〇ヶヵ]"
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
MATH_CONTENT_ENVIRONMENTS = {
    "align",
    "align*",
    "aligned",
    "alignedat",
    "alignedat*",
    "alignat",
    "alignat*",
    "array",
    "bmatrix",
    "Bmatrix",
    "cases",
    "dcases",
    "displaymath",
    "equation",
    "equation*",
    "flalign",
    "flalign*",
    "gather",
    "gather*",
    "gathered",
    "math",
    "matrix",
    "multline",
    "multline*",
    "pmatrix",
    "smallmatrix",
    "split",
    "subarray",
    "vmatrix",
    "Vmatrix",
}


def tex_sha256(tex: str) -> str:
    return hashlib.sha256(tex.encode("utf-8")).hexdigest()


def apply_segment_text_replacements(
    tex: str, replacements: list[dict[str, Any]], *, context: str
) -> str:
    """Apply cardinality-checked local edits inside one hash-locked segment."""

    if not replacements:
        raise ValueError(f"{context} needs at least one text replacement")
    seen: set[str] = set()
    for index, replacement in enumerate(replacements, start=1):
        before = replacement.get("before")
        after = replacement.get("after")
        expected_count = replacement.get("expected_count")
        if not isinstance(before, str) or not before:
            raise ValueError(f"{context} replacement {index} needs before text")
        if before in seen:
            raise ValueError(f"{context} has duplicate before text")
        seen.add(before)
        if not isinstance(after, str):
            raise ValueError(f"{context} replacement {index} needs after text")
        if not isinstance(expected_count, int) or expected_count < 1:
            raise ValueError(
                f"{context} replacement {index} needs expected_count >= 1"
            )
        found = tex.count(before)
        if found != expected_count:
            raise ValueError(
                f"{context} replacement {index} expected {expected_count} "
                f"occurrences, found {found}"
            )
        tex = tex.replace(before, after)
    return tex


def apply_evidence_segment_repairs(
    segments: list[dict[str, Any]], rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply project-local structural repairs without invalidating model work.

    Repairs are locked to a segment id plus source and accepted-output hashes.
    This permits an OCR table or equation to be reconstructed after semantic
    review while preventing a stale repair from touching newly generated text.
    """

    by_id = {row.get("segment_id"): row for row in segments}
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        segment_id = rule.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError(f"segment repair {index} has no segment_id")
        if segment_id in seen:
            raise ValueError(f"duplicate segment repair for {segment_id}")
        seen.add(segment_id)
        row = by_id.get(segment_id)
        if row is None:
            raise ValueError(f"segment repair target does not exist: {segment_id}")

        expected_source = rule.get("source_sha256")
        if expected_source != row.get("source_sha256"):
            raise ValueError(
                f"segment repair source hash mismatch for {segment_id}: "
                f"expected {expected_source}, found {row.get('source_sha256')}"
            )
        replacement_kind = rule.get("kind")
        if replacement_kind is not None:
            expected_kind = rule.get("expected_kind")
            if expected_kind != row.get("kind"):
                raise ValueError(
                    f"segment repair kind mismatch for {segment_id}: "
                    f"expected {expected_kind}, found {row.get('kind')}"
                )
            if replacement_kind not in {"text", "table"}:
                raise ValueError(
                    f"segment repair {segment_id} has unsupported kind "
                    f"{replacement_kind!r}"
                )
            row["kind"] = replacement_kind
        for language in ("en", "ja"):
            current = row.get(f"{language}_tex")
            replacement = rule.get(f"{language}_tex")
            text_replacements = rule.get(f"{language}_replacements")
            expected_hash = rule.get(f"expected_{language}_sha256")
            if not isinstance(current, str):
                raise ValueError(
                    f"segment repair {segment_id} needs a current {language}_tex string"
                )
            if expected_hash != tex_sha256(current):
                raise ValueError(
                    f"segment repair accepted {language} hash mismatch for {segment_id}"
                )
            has_full_replacement = isinstance(replacement, str)
            has_text_replacements = isinstance(text_replacements, list)
            if has_full_replacement == has_text_replacements:
                raise ValueError(
                    f"segment repair {segment_id} needs exactly one of "
                    f"{language}_tex or {language}_replacements"
                )
            if has_full_replacement:
                row[f"{language}_tex"] = replacement
            else:
                row[f"{language}_tex"] = apply_segment_text_replacements(
                    current,
                    text_replacements,
                    context=f"segment repair {segment_id}/{language}",
                )

        if "source_tex" in rule:
            source_replacement = rule.get("source_tex")
            if not isinstance(source_replacement, str):
                raise ValueError(
                    f"segment repair {segment_id} source_tex must be a string"
                )
            row["source_tex"] = source_replacement
        changes.append(
            {
                "segment_id": segment_id,
                "kind": row.get("kind"),
                "reason": str(rule.get("reason", "Evidence-backed structural repair.")),
                "evidence": rule.get("evidence", []),
            }
        )
    return changes


MATH_REFLOW_RELATION_RE = re.compile(
    r"(?<!\\)="
    r"|\\(?:geq|leq|neq|approx|sim|simeq|equiv|propto|in|notin|subseteq|supseteq)\b"
    r"|(?<!\\)[<>]"
)


def is_strategy_profile_math(row: str) -> bool:
    """Return whether angle brackets delimit a strategy profile, not an inequality."""

    compact = row.strip().lstrip("&").strip()
    return (
        compact.startswith("<")
        and compact.endswith(">")
        or compact.startswith(r"\langle")
        and compact.endswith(r"\rangle")
    )


def normalized_math_token_stream(tex: str) -> str:
    """Return the immutable token stream used by layout-only math repairs."""

    return re.sub(r"\s+", "", tex)


def normalized_math_block_token_stream(tex: str) -> str:
    """Return math tokens after removing only source layout delimiters."""

    tex = tex.replace(r"\(", "").replace(r"\)", "")
    tex = re.sub(r"\\\\(?:\[[^\]]+\])?", "", tex)
    return normalized_math_token_stream(tex)


def align_math_reflow_row(row: str) -> str:
    """Add one visual alignment point without changing mathematical tokens."""

    relation = MATH_REFLOW_RELATION_RE.search(row)
    if relation is not None:
        return row[: relation.start()] + "&" + row[relation.start() :]
    if row.lstrip().startswith(("+", "-")):
        return r"&\quad {}" + row.lstrip()
    return r"&\quad " + row


def apply_evidence_math_block_reflows(
    tex: str, rules: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Join OCR-split math spans into native aligned display blocks.

    Unlike a normal equation reflow, these rules may span several ``\(...\)``
    atoms and short math fragments that Mathpix accidentally emitted as prose.
    The source span is hash-locked and its complete token stream must equal the
    concatenated output rows after removing only math delimiters, forced line
    breaks, and whitespace.
    """

    changes: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        before = rule.get("before")
        rows = rule.get("rows")
        expected_count = rule.get("expected_count")
        expected_sha256 = rule.get("source_sha256")
        if not isinstance(before, str) or not before:
            raise ValueError(f"math block reflow {index} needs a non-empty before string")
        if before in seen_sources:
            raise ValueError(f"duplicate math block reflow source at rule {index}")
        seen_sources.add(before)
        if expected_sha256 != tex_sha256(before):
            raise ValueError(f"math block reflow {index} source hash mismatch")
        if not isinstance(expected_count, int) or expected_count < 1:
            raise ValueError(f"math block reflow {index} needs expected_count >= 1")
        if not isinstance(rows, list) or not rows or not all(
            isinstance(row, str) and row.strip() for row in rows
        ):
            raise ValueError(f"math block reflow {index} needs non-empty string rows")
        for row in rows:
            if any(marker in row for marker in (r"\\", r"\[", r"\]", r"\begin", r"\end", "&")):
                raise ValueError(
                    f"math block reflow {index} row contains caller-owned layout syntax"
                )
        if normalized_math_block_token_stream(before) != normalized_math_token_stream(
            "".join(rows)
        ):
            raise ValueError(f"math block reflow {index} changes mathematical tokens")
        found = tex.count(before)
        if found != expected_count:
            raise ValueError(
                f"math block reflow {index} expected {expected_count} occurrences, found {found}"
            )
        aligned_rows = " \\\\\n".join(align_math_reflow_row(row.strip()) for row in rows)
        replacement = (
            "\n\\[\n\\begin{aligned}\n"
            + aligned_rows
            + "\n\\end{aligned}\n\\]\n"
        )
        tex = tex.replace(before, replacement)
        changes.append(
            {
                "source_sha256": expected_sha256,
                "occurrences": found,
                "rows": len(rows),
                "reason": str(rule.get("reason", "Evidence-backed equation block reflow.")),
                "evidence": rule.get("evidence", []),
            }
        )
    return tex, changes


def apply_evidence_math_reflows(
    tex: str, rules: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Reflow fused inline derivations while preserving every math token.

    The project-local plan supplies only row boundaries.  A rule is accepted
    when its source hash and occurrence count match and concatenating its rows
    reproduces the exact non-whitespace token stream.  This lets narrow-page
    books repair Mathpix line fusion without silently rewriting equations.
    """

    changes: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        before = rule.get("before")
        rows = rule.get("rows")
        expected_count = rule.get("expected_count")
        expected_sha256 = rule.get("source_sha256")
        if not isinstance(before, str) or not before:
            raise ValueError(f"math reflow {index} needs a non-empty before string")
        if before in seen_sources:
            raise ValueError(f"duplicate math reflow source at rule {index}")
        seen_sources.add(before)
        if expected_sha256 != tex_sha256(before):
            raise ValueError(f"math reflow {index} source hash mismatch")
        if not isinstance(expected_count, int) or expected_count < 1:
            raise ValueError(f"math reflow {index} needs expected_count >= 1")
        if not isinstance(rows, list) or not rows or not all(
            isinstance(row, str) and row.strip() for row in rows
        ):
            raise ValueError(f"math reflow {index} needs non-empty string rows")
        for row in rows:
            if any(marker in row for marker in (r"\\", r"\[", r"\]", r"\begin", r"\end", "&")):
                raise ValueError(
                    f"math reflow {index} row contains caller-owned layout syntax"
                )
        if normalized_math_token_stream(before) != normalized_math_token_stream(
            "".join(rows)
        ):
            raise ValueError(f"math reflow {index} changes mathematical tokens")

        target = r"\(" + before + r"\)"
        found = tex.count(target)
        if found != expected_count:
            raise ValueError(
                f"math reflow {index} expected {expected_count} occurrences, found {found}"
            )
        aligned_rows = " \\\\\n".join(align_math_reflow_row(row.strip()) for row in rows)
        replacement = (
            "\n\\[\n\\begin{aligned}\n"
            + aligned_rows
            + "\n\\end{aligned}\n\\]\n"
        )
        # A source inline equation often ends with ``\\\\``.  Once promoted
        # to display math that forced break is redundant; leaving it after a
        # centered/boxed display creates an empty-line ``\\\\`` and can make
        # XeLaTeX fail with "There's no line here to end."  Consume only the
        # break immediately attached to this exact, hash-locked equation.
        target_with_break = re.compile(
            re.escape(target) + r"[ \t]*\\\\(?:\[[^\]]+\])?"
        )
        tex, replaced_with_break = target_with_break.subn(
            lambda _match: replacement, tex
        )
        tex, replaced_without_break = re.subn(
            re.escape(target), lambda _match: replacement, tex
        )
        if replaced_with_break + replaced_without_break != found:
            raise ValueError(
                f"math reflow {index} replacement cardinality changed during application"
            )
        changes.append(
            {
                "source_sha256": expected_sha256,
                "occurrences": found,
                "rows": len(rows),
                "reason": str(rule.get("reason", "Evidence-backed equation reflow.")),
                "evidence": rule.get("evidence", []),
            }
        )
    return tex, changes


def suspicious_run_on_inline_math(tex: str) -> list[str]:
    """Return inline derivations that would become illegibly scaled boxes."""

    eu_symbol = re.compile(
        r"(?:\\mathrm\s*\{\s*EU\s*\}|E\s*U)\s*_\s*"
        r"(?:\{(?:[^{}]|\{[^{}]*\})*\}|[A-Za-z0-9]+)",
        flags=re.I,
    )
    eu_lhs = re.compile(
        eu_symbol.pattern
        + r"\s*&?\s*(?:=|\\(?:geq|leq|neq|approx|sim|simeq|equiv)\b|[<>])",
        flags=re.I,
    )

    def is_simple_eu_equality_chain(row: str) -> bool:
        compact = row.replace("&", "").strip()
        if any(token in compact for token in ("<", ">", r"\geq", r"\leq")):
            return False
        terms = re.split(r"(?<!\\)=", compact)
        return len(terms) >= 3 and all(
            eu_symbol.fullmatch(term.strip()) is not None for term in terms
        )

    findings: list[str] = []
    for match in INLINE_MATH_RE.finditer(tex):
        body = match.group("display") or match.group("paren") or match.group("dollar")
        if body is None:
            continue
        aligned = re.search(
            r"\\begin\{aligned\*?\}(?P<body>.*?)\\end\{aligned\*?\}",
            body,
            flags=re.S,
        )
        rows = (
            re.split(r"\\\\(?:\[[^\]]+\])?", aligned.group("body"))
            if aligned is not None
            else [body]
        )
        for row in rows:
            if is_strategy_profile_math(row) or is_simple_eu_equality_chain(row):
                continue
            relation_count = len(MATH_REFLOW_RELATION_RE.findall(row))
            eu_lhs_count = len(eu_lhs.findall(row))
            compact_length = len(normalized_math_token_stream(row))
            if relation_count >= 2 and compact_length >= 70:
                findings.append(row)
            elif eu_lhs_count >= 2 and relation_count >= 1 and compact_length >= 70:
                findings.append(row)
    return findings


DANGLING_MATH_TAIL_RE = re.compile(
    r"(?:=|\+|-|<|>|\\(?:geq|leq|neq|approx|sim|simeq|equiv|propto))\s*$"
)
ALIGNED_BODY_RE = re.compile(
    r"\\begin\{aligned\*?\}(?P<body>.*?)\\end\{aligned\*?\}", re.S
)


def suspicious_dangling_math_rows(tex: str) -> list[str]:
    """Return math atoms or aligned rows ending in an unfinished operation."""

    findings: list[str] = []
    seen: set[str] = set()

    def inspect(body: str) -> None:
        aligned_matches = list(ALIGNED_BODY_RE.finditer(body))
        candidates: list[str] = []
        if aligned_matches:
            for aligned in aligned_matches:
                candidates.extend(
                    re.split(r"\\\\(?:\[[^\]]+\])?", aligned.group("body"))
                )
        else:
            candidates.append(body)
        for candidate in candidates:
            candidate = re.sub(r"%[^\n]*", "", candidate).strip()
            candidate = candidate.rstrip("&").strip()
            if is_strategy_profile_math(candidate):
                continue
            if not candidate or not DANGLING_MATH_TAIL_RE.search(candidate):
                continue
            compact = " ".join(candidate.split())
            if compact not in seen:
                seen.add(compact)
                findings.append(compact)

    for match in INLINE_MATH_RE.finditer(tex):
        body = match.group("display") or match.group("paren") or match.group("dollar")
        if body is not None:
            inspect(body)
    for match in MATH_ENV_RE.finditer(tex):
        inspect(match.group("body"))
    return findings


def validate_layout_plan_assertions(tex: str, plan: dict[str, Any]) -> dict[str, int]:
    """Reject known malformed constructs after evidence repairs are applied."""

    forbidden = plan.get("forbidden_substrings", [])
    required = plan.get("required_substrings", [])
    if not isinstance(forbidden, list) or not isinstance(required, list):
        raise ValueError("layout repair assertions must be arrays")
    for marker in forbidden:
        if not isinstance(marker, str) or not marker:
            raise ValueError("forbidden layout markers must be non-empty strings")
        if marker in tex:
            raise ValueError(f"forbidden malformed layout remains: {marker!r}")
    for marker in required:
        if not isinstance(marker, str) or not marker:
            raise ValueError("required layout markers must be non-empty strings")
        if marker not in tex:
            raise ValueError(f"required repaired layout is missing: {marker!r}")
    return {
        "forbidden_markers_absent": len(forbidden),
        "required_markers_present": len(required),
    }
FUSION_PREAMBLE = r"""
% BUILD_POCKET_POLISHED_FUSION_BEGIN
\definecolor{JpSecondaryInk}{RGB}{62,68,76}
\IfFontExistsTF{Noto Serif}{%
  \newfontfamily\PocketUnicodeTextFont{Noto Serif}%
}{%
  \newcommand{\PocketUnicodeTextFont}{\rmfamily}%
}
\DeclareRobustCommand{\PocketUnicodeText}[1]{{\PocketUnicodeTextFont #1}}
\pdfstringdefDisableCommands{\def\PocketUnicodeText#1{#1}}
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
        # Music writers sometimes emit math-only accidental commands inside a
        # text superscript.  XeLaTeX rejects ``\textsuperscript{\flat}``
        # because ``\flat`` requires math mode.  Preserve the visible
        # accidental and its ordering by moving only that symbol into inline
        # math; no source wording or musical fact changes.
        plain, changed = TEXT_SUPERSCRIPT_ACCIDENTAL_RE.subn(
            lambda match: rf"\({match.group('symbols')}\)", plain
        )
        count += changed
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


def normalize_unicode_math_symbols(tex: str) -> tuple[str, int]:
    """Replace raw Unicode Greek only inside existing TeX math spans."""

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
    changed = 0
    for start, end in merged:
        parts.append(tex[cursor:start])
        math = tex[start:end]
        for symbol, command in GREEK_MATH_COMMANDS.items():
            count = math.count(symbol)
            if count:
                math = math.replace(symbol, command)
                changed += count
        parts.append(math)
        cursor = end
    parts.append(tex[cursor:])
    return "".join(parts), changed


def normalize_unicode_text_fallbacks(tex: str) -> tuple[str, int]:
    """Use deterministic TeX/font fallbacks outside existing math spans."""

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

    def replace_plain(plain: str) -> tuple[str, int]:
        changed = 0
        plain, count = CYRILLIC_RUN_RE.subn(
            lambda match: rf"\PocketUnicodeText{{{match.group(0)}}}", plain
        )
        changed += count
        for symbol, replacement in TEXT_SYMBOL_REPLACEMENTS.items():
            count = plain.count(symbol)
            if count:
                plain = plain.replace(symbol, replacement)
                changed += count
        return plain, changed

    parts: list[str] = []
    cursor = 0
    changed = 0
    for start, end in merged:
        plain, count = replace_plain(tex[cursor:start])
        parts.extend((plain, tex[start:end]))
        changed += count
        cursor = end
    plain, count = replace_plain(tex[cursor:])
    parts.append(plain)
    changed += count
    return "".join(parts), changed


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


def unwrap_heading_hypertargets(tex: str) -> str:
    """Remove Pandoc navigation wrappers while preserving translated headings.

    Pandoc commonly emits ``\\hypertarget{id}{% \\section{...}\\label{id}}``.
    The English heading already owns the PDF destination, so repeating that
    wrapper in the Japanese secondary stream creates duplicate anchors.  The
    visible heading and any adjacent translated prose must nevertheless remain.
    """

    marker = r"\hypertarget"
    cursor = 0
    parts: list[str] = []
    while True:
        start = tex.find(marker, cursor)
        if start < 0:
            parts.append(tex[cursor:])
            break
        parts.append(tex[cursor:start])
        first_open = start + len(marker)
        while first_open < len(tex) and tex[first_open].isspace():
            first_open += 1
        try:
            _, first_end = braced_argument(tex, first_open)
            second_open = first_end
            while second_open < len(tex) and tex[second_open].isspace():
                second_open += 1
            inner, second_end = braced_argument(tex, second_open)
        except ValueError:
            parts.append(marker)
            cursor = start + len(marker)
            continue
        if HEADING_COMMAND_RE.search(inner):
            inner = LABEL_COMMAND_RE.sub("", inner)
            inner = re.sub(r"(?m)^\s*%\s*$\n?", "", inner)
            parts.append(inner)
        else:
            parts.append(tex[start:second_end])
        cursor = second_end
    return "".join(parts)


def split_translated_heading_blocks(tex: str) -> list[tuple[str, str]]:
    """Split translated TeX into ordered ``heading`` and ``body`` blocks.

    A generated segment can contain several headings followed by prose, lists,
    captions, or exercises.  Returning only the first title silently discarded
    that content.  This parser consumes balanced heading arguments and retains
    every byte outside the heading commands for secondary rendering.
    """

    tex = unwrap_heading_hypertargets(tex)
    blocks: list[tuple[str, str]] = []
    cursor = 0
    while True:
        match = HEADING_COMMAND_RE.search(tex, cursor)
        if match is None:
            if tex[cursor:]:
                blocks.append(("body", tex[cursor:]))
            break
        if match.start() > cursor:
            blocks.append(("body", tex[cursor : match.start()]))
        title, end = braced_argument(tex, match.end() - 1)
        blocks.append(("heading", unwrap_texorpdfstring(title)))
        cursor = end
    return blocks


def remove_shared_graphics(en_tex: str, secondary_tex: str) -> tuple[str, int]:
    """Remove source graphics repeated verbatim in a secondary-language block."""

    source_graphics = {
        match.group("detokenized_path") or match.group("path")
        for match in INCLUDEGRAPHICS_RE.finditer(en_tex)
    }
    removed_graphics = 0

    def remove_shared_graphic(match: re.Match[str]) -> str:
        nonlocal removed_graphics
        path = match.group("detokenized_path") or match.group("path")
        if path not in source_graphics:
            return match.group(0)
        removed_graphics += 1
        return ""

    return INCLUDEGRAPHICS_RE.sub(remove_shared_graphic, secondary_tex), removed_graphics


def clean_heading_secondary_body(en_tex: str, body: str) -> tuple[str, int]:
    """Remove only source-owned scaffolding from a translated heading body."""

    body, removed_graphics = remove_shared_graphics(en_tex, body)
    body = re.sub(r"(?m)^\s*\\graphicspath\{.*\}\s*$\n?", "", body)
    body = re.sub(
        r"\\captionsetup(?:\[[^\]]*\])?\{[^{}]*\}\s*",
        "",
        body,
    )
    body = LABEL_COMMAND_RE.sub("", body)
    body = SECONDARY_PAGE_CONTROL_RE.sub("", body)
    body = re.sub(
        r"(?m)^\s*\\noindent\s*(?:\\par\s*)?(?:\\smallskip\s*)?$\n?",
        "",
        body,
    )
    # A translated caption belongs below the already-emitted source figure. If
    # every shared graphic was removed, retain the caption text but not an empty
    # duplicate float or its centering scaffold.
    if removed_graphics and r"\includegraphics" not in body:
        body = re.sub(r"\\begin\{figure\*?\}(?:\[[^\]]*\])?", "", body)
        body = re.sub(r"\\end\{figure\*?\}", "", body)
        body = re.sub(r"\\begin\{center\}|\\end\{center\}", "", body)
    body = re.sub(r"(?m)^\s*%\s*$\n?", "", body)
    return body.strip(), removed_graphics


def japanese_surface_stream(tex: str) -> str:
    """Return visible Japanese script while excluding generated ruby readings."""

    previous = None
    while tex != previous:
        previous = tex
        tex = re.sub(r"\\JpRuby\{([^{}]*)\}\{[^{}]*\}", r"\1", tex)
    return "".join(JAPANESE_SCRIPT_RE.findall(tex))


def validate_heading_secondary_coverage(
    segments: list[dict[str, Any]], fused: str
) -> dict[str, int]:
    """Prove that Japanese outside translated heading commands reached output."""

    rendered = japanese_surface_stream(fused)
    cursor = 0
    expected = 0
    matched = 0
    for segment in segments:
        if segment.get("kind") == "protected":
            continue
        en_tex = segment.get("en_tex", "")
        ja_tex = segment.get("ja_tex", "")
        blocks = split_translated_heading_blocks(ja_tex)
        if not any(kind == "heading" for kind, _ in blocks):
            continue
        for kind, value in blocks:
            if kind != "body":
                continue
            secondary, _ = clean_heading_secondary_body(en_tex, value)
            signature = japanese_surface_stream(secondary)
            if not signature:
                continue
            expected += 1
            found = rendered.find(signature, cursor)
            if found < 0:
                raise ValueError(
                    "missing Japanese post-heading content after fusion: "
                    f"{segment.get('segment_id', 'unknown')}"
                )
            matched += 1
            cursor = found + len(signature)
    return {
        "expected_japanese_heading_bodies": expected,
        "matched_japanese_heading_bodies": matched,
    }


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

    def remove_layout_environment_commands(line: str) -> str:
        return ENVIRONMENT_COMMAND_RE.sub(
            lambda match: (
                match.group(0)
                if match.group("environment") in MATH_CONTENT_ENVIRONMENTS
                else ""
            ),
            line,
        )

    def contains_math_content_environment(line: str) -> bool:
        return any(
            match.group("environment") in MATH_CONTENT_ENVIRONMENTS
            for match in ENVIRONMENT_COMMAND_RE.finditer(line)
        )

    ja_tex, _ = remove_shared_graphics(en_tex, ja_tex)
    en_lines = en_tex.splitlines(keepends=True)
    ja_lines = ja_tex.splitlines(keepends=True)
    while (
        en_lines
        and ja_lines
        and en_lines[0] == ja_lines[0]
        and not contains_math_content_environment(en_lines[0])
    ):
        en_lines.pop(0)
        ja_lines.pop(0)
    shared_suffix: list[str] = []
    while (
        en_lines
        and ja_lines
        and en_lines[-1] == ja_lines[-1]
        and not contains_math_content_environment(en_lines[-1])
    ):
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
        # Mathematical environments are semantic content, not page scaffolds.
        # Removing ``cases``/``matrix`` while retaining their ``&`` cells
        # creates invalid TeX and silently drops structure from the Japanese
        # stream. Preserve those commands byte-for-byte.
        residual = remove_layout_environment_commands(line)
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


def contains_only_captions(tex: str) -> bool:
    """Return true when a translated table remainder contains only captions."""

    residual = re.sub(
        r"\\captionsetup(?:\[[^\]]*\])?\{[^{}]*\}\s*",
        "",
        tex,
    )
    marker = r"\caption{"
    cursor = 0
    found = False
    while True:
        start = residual.find(marker, cursor)
        if start < 0:
            return found and not residual[cursor:].strip()
        if residual[cursor:start].strip():
            return False
        try:
            _, cursor = braced_argument(residual, start + len(r"\caption"))
        except ValueError:
            return False
        found = True


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


def update_secondary_open_environments(tex: str, stack: list[str]) -> None:
    """Track wrappers emitted into the secondary stream.

    Source-only floats can end inside a translated caption even though their
    opening commands were deliberately not copied into the secondary stream.
    Ignore those unmatched closers, but keep strict nesting for wrappers that
    the secondary stream actually opened.
    """

    for match in ENVIRONMENT_COMMAND_RE.finditer(tex):
        environment = match.group("environment")
        if match.group("action") == "begin":
            stack.append(environment)
            continue
        if not stack:
            continue
        if stack[-1] != environment:
            if environment not in stack:
                continue
            raise ValueError(
                "malformed secondary environment: closing "
                f"{environment} while {stack[-1]} is open"
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


def tables_are_semantically_identical(en_tex: str, ja_tex: str) -> bool:
    """Return true when both streams carry the same source-owned table.

    Segment boundaries can leave ``center`` in the source stream while the
    secondary stream contains only the protected ``tabular`` object.  Those
    wrappers do not make a second table useful.  Compare after removing only
    presentation wrappers; translated labels or cells still make the tables
    distinct and therefore render in both languages.
    """

    if not has_balanced_complete_environment(en_tex, TABLE_ENVIRONMENTS):
        return False
    if not has_balanced_complete_environment(ja_tex, TABLE_ENVIRONMENTS):
        return False

    def canonical(tex: str) -> str:
        tex = re.sub(r"\\begin\{center\}|\\end\{center\}", "", tex)
        return re.sub(r"\s+", "", tex)

    return canonical(en_tex) == canonical(ja_tex)


def fuse_english_main_japanese_secondary(
    segments: list[dict[str, Any]],
    *,
    furigana_overrides: dict[str, str] | None = None,
    fusion_metrics: dict[str, int] | None = None,
) -> tuple[str, FuriganaStats]:
    parts: list[str] = []
    furigana = FuriganaStats()
    pending_en: list[str] = []
    pending_ja: list[str] = []
    open_environments: list[str] = []
    secondary_open_environments: list[str] = []
    pending_crosses_environment = False
    furigana_overrides = furigana_overrides or {}
    heading_segment_count = 0
    translated_heading_count = 0
    rendered_heading_body_count = 0
    stripped_heading_graphics = 0

    def apply_furigana_overrides(tex: str) -> str:
        for surface, reading in furigana_overrides.items():
            if not isinstance(surface, str) or not surface:
                raise ValueError("furigana override has an empty surface form")
            if not isinstance(reading, str) or not reading:
                raise ValueError(f"furigana override has no reading: {surface}")
            tex = tex.replace(surface, rf"\JpRuby{{{surface}}}{{{reading}}}")
        return tex

    def append_heading_secondary_body(en_tex: str, body: str) -> None:
        nonlocal rendered_heading_body_count, stripped_heading_graphics
        raw_has_japanese = bool(JAPANESE_SCRIPT_RE.search(body))
        secondary, removed_graphics = clean_heading_secondary_body(en_tex, body)
        stripped_heading_graphics += removed_graphics
        if raw_has_japanese and not JAPANESE_SCRIPT_RE.search(secondary):
            raise ValueError(
                "heading-adjacent Japanese content was removed with source scaffolding"
            )
        if not secondary:
            return
        secondary = restore_secondary_list_scaffold(en_tex, secondary)
        secondary = demote_secondary_captions(secondary)
        secondary = apply_furigana_overrides(secondary)
        secondary, current = annotate_japanese_tex(secondary)
        furigana.merge(current)
        if has_balanced_complete_environment(secondary, TABLE_ENVIRONMENTS):
            parts.append(
                "\n\\begingroup\n"
                "\\JpSecondaryFont\\fontsize{8.6pt}{14.2pt}\\selectfont"
                "\\color{JpSecondaryInk}\n"
                f"{secondary}\n"
                "\\endgroup\n"
            )
        else:
            parts.append(
                f"\n\\begin{{JpSecondary}}\n{secondary}\n\\end{{JpSecondary}}\n"
            )
        rendered_heading_body_count += 1

    def emit_pending() -> None:
        nonlocal pending_crosses_environment
        nonlocal heading_segment_count, translated_heading_count
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
        heading_blocks = split_translated_heading_blocks(ja_tex)
        if any(kind == "heading" for kind, _ in heading_blocks):
            parts.append(en_tex)
            heading_segment_count += 1
            for kind, value in heading_blocks:
                if kind == "body":
                    append_heading_secondary_body(en_tex, value)
                    continue
                heading = apply_furigana_overrides(value)
                annotated, current = annotate_japanese_tex(heading)
                furigana.merge(current)
                parts.append(f"\n\\JpSecondaryHeading{{{annotated}}}\n")
                translated_heading_count += 1
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
            if tables_are_semantically_identical(en_tex, ja_tex):
                parts.append(en_tex)
                return
            en_body, trailing_scaffold, caption_secondary = (
                split_shared_environment_scaffold(en_tex, ja_tex)
            )
            if trailing_scaffold and contains_only_captions(caption_secondary):
                parts.append(en_body)
                secondary = demote_secondary_captions(caption_secondary.strip())
                secondary = apply_furigana_overrides(secondary)
                secondary, current = annotate_japanese_tex(secondary)
                furigana.merge(current)
                parts.append(
                    "\n\\par\\smallskip\n"
                    "\\begingroup\n"
                    "\\JpSecondaryFont\\fontsize{8.6pt}{14.2pt}\\selectfont"
                    "\\color{JpSecondaryInk}\n"
                    f"{secondary}\\par\n"
                    "\\endgroup\n"
                )
                parts.append(trailing_scaffold)
                return
            parts.append(en_tex)
            secondary, _ = remove_shared_graphics(en_tex, ja_tex)
            secondary = apply_furigana_overrides(secondary.strip())
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
            secondary, _ = remove_shared_graphics(en_tex, ja_tex)
            secondary = demote_secondary_captions(secondary.strip())
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
                # Also copy a protected closing wrapper when its opening was
                # emitted by a translated segment.  Without this, a common
                # ``text: \\begin{center}`` + protected table + protected
                # ``\\end{center}`` split leaves the Japanese table unclosed.
                closes_secondary_wrapper = any(
                    match.group("action") == "end"
                    and match.group("environment") in secondary_open_environments
                    for match in environment_commands
                )
                secondary_source = (
                    source_tex if table_scaffold or closes_secondary_wrapper else ""
                )
                pending_ja.append(secondary_source)
                if secondary_source:
                    update_secondary_open_environments(
                        secondary_source, secondary_open_environments
                    )
                update_open_environments(source_tex, open_environments)
                if not open_environments:
                    if secondary_open_environments:
                        raise ValueError(
                            "unclosed secondary environments before fusion: "
                            + ", ".join(secondary_open_environments)
                        )
                    emit_pending()
            else:
                emit_pending()
                parts.append(source_tex)
            continue
        en_tex = segment["en_tex"]
        ja_tex = segment["ja_tex"]
        has_layout_environment = any(
            match.group("environment") not in MATH_CONTENT_ENVIRONMENTS
            for match in ENVIRONMENT_COMMAND_RE.finditer(en_tex)
        )
        if has_layout_environment or r"\includegraphics" in en_tex:
            pending_crosses_environment = True
        pending_en.append(en_tex)
        pending_ja.append(ja_tex)
        update_open_environments(en_tex, open_environments)
        update_secondary_open_environments(ja_tex, secondary_open_environments)
        if not open_environments:
            if secondary_open_environments:
                raise ValueError(
                    "unclosed secondary environments before fusion: "
                    + ", ".join(secondary_open_environments)
                )
            emit_pending()
    if open_environments:
        raise ValueError(
            "unclosed source environments at fusion end: "
            + ", ".join(open_environments)
        )
    if secondary_open_environments:
        raise ValueError(
            "unclosed secondary environments at fusion end: "
            + ", ".join(secondary_open_environments)
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
    if fusion_metrics is not None:
        fusion_metrics.update(
            {
                "heading_segments": heading_segment_count,
                "translated_headings": translated_heading_count,
                "rendered_heading_bodies": rendered_heading_body_count,
                "stripped_duplicate_heading_graphics": stripped_heading_graphics,
            }
        )
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


CHORD_TABLE_SEPARATOR_RE = re.compile(
    r"(?<=[A-G0-9♭♯°#])(?P<separator>--|[-−])"
    r"(?=(?:[A-G0-9♭♯°#]|\\#))"
)


def add_chord_table_breakpoints(body: str) -> tuple[str, int]:
    """Add invisible line-break opportunities inside pitch/formula lists."""

    return CHORD_TABLE_SEPARATOR_RE.subn(
        lambda match: match.group("separator") + r"\allowbreak{}",
        body,
    )


def longtable_content_widths(body: str, column_count: int) -> list[float]:
    """Allocate wrapping columns from visible cell content on pocket pages."""

    def visible_length(cell: str) -> int:
        cell = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", "", cell)
        cell = re.sub(r"[{}~]", "", cell)
        return len(re.sub(r"\s+", " ", cell).strip())

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


def compact_longtable(body: str, columns: str, *, widths: list[float]) -> str:
    """Render a page-breaking table with explicit A6-safe spacing."""

    alignments = {
        "l": r">{\raggedright\arraybackslash}",
        "c": r">{\centering\arraybackslash}",
        "r": r">{\raggedleft\arraybackslash}",
    }
    body, _ = add_chord_table_breakpoints(body)
    cells = [
        f"{alignments[column]}p{{{width:.3f}\\linewidth}}"
        for column, width in zip(columns, widths)
    ]
    specification = "@{}" + r"@{\hspace{1pt}}".join(cells) + "@{}"
    size = r"\scriptsize" if len(columns) >= 6 else r"\footnotesize"
    return (
        f"\\begingroup{size}\\setlength{{\\tabcolsep}}{{1pt}}"
        f"\\begin{{longtable}}[]{{{specification}}}"
        f"{body}"
        "\\end{longtable}\\endgroup"
    )


def wrap_long_simple_longtables(tex: str, *, min_rows: int = 13) -> tuple[str, int]:
    """Give long simple tables wrapping columns while retaining page breaks."""

    wrapped = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal wrapped
        body = match.group("body")
        row_count = body.count(r"\\")
        columns = match.group("columns")
        if row_count < min_rows or len(columns) < 2:
            return match.group(0)
        widths = longtable_content_widths(body, len(columns))
        wrapped += 1
        return compact_longtable(body, columns, widths=widths)

    return SIMPLE_LONGTABLE_RE.sub(replace, tex), wrapped


def wrap_long_complex_longtables(tex: str, *, min_rows: int = 13) -> tuple[str, int]:
    """Reflow long Pandoc p-column tables without losing page breaks."""

    marker = r"\begin{longtable}[]"
    end_marker = r"\end{longtable}"
    wrapped = 0
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
        columns = column_count(spec)
        if (
            row_count < min_rows
            or columns < 2
            or re.fullmatch(r"@\{\}[lcr]+@\{\}", spec)
        ):
            parts.append(tex[start : end + len(end_marker)])
        else:
            widths = longtable_content_widths(body, columns)
            parts.append(compact_longtable(body, "l" * columns, widths=widths))
            wrapped += 1
        cursor = end + len(end_marker)
    return "".join(parts), wrapped


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
    # Exact-book wrappers scope body typography with a document-spanning
    # \begingroup immediately after \mainmatter. Nothing follows the body, and
    # carrying that group through thousands of translated blocks can leave
    # XeTeX reporting it at \end{document}. Remove only this exact outer pair;
    # all local table/ruby groups remain untouched.
    text = re.sub(
        r"(\\mainmatter\s*)\\begingroup\s*",
        r"\1",
        text,
        count=1,
    )
    text = re.sub(
        r"\\endgroup\s*(\\end\{document\}\s*)$",
        r"\1",
        text,
        count=1,
    )
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
        and not report.get("missing_character_markers")
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
    layout_replacement_plan = manifest.get("layout_replacement_plan")
    layout_plan: dict[str, Any] = {}
    if layout_replacement_plan:
        plan_path = ROOT / str(layout_replacement_plan)
        loaded_plan = read_json(plan_path)
        if not isinstance(loaded_plan, dict):
            raise ValueError(f"layout replacement plan is not an object: {plan_path}")
        layout_plan = loaded_plan
    segment_repair_rules = layout_plan.get("segment_repairs", [])
    if not isinstance(segment_repair_rules, list):
        raise ValueError("layout replacement plan segment_repairs must be an array")
    segment_repair_changes = apply_evidence_segment_repairs(
        merged_rows, segment_repair_rules
    )

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

    fusion_metrics: dict[str, int] = {}
    fused, furigana = fuse_english_main_japanese_secondary(
        merged_rows,
        furigana_overrides=manifest.get("furigana_overrides", {}),
        fusion_metrics=fusion_metrics,
    )
    heading_coverage = validate_heading_secondary_coverage(merged_rows, fused)
    fused, unicode_math_symbol_count = normalize_unicode_math_symbols(fused)
    fused = normalize_bold_greek_commands(fused)
    fused, unicode_text_fallback_count = normalize_unicode_text_fallbacks(fused)
    layout_replacement_count = 0
    layout_rules = layout_plan.get("replacements", [])
    if not isinstance(layout_rules, list):
        raise ValueError("layout replacement plan replacements must be an array")
    if layout_rules:
        fused, layout_changes = apply_exact_text_replacements(fused, layout_rules)
        layout_replacement_count = len(layout_changes)
    math_block_reflow_rules = layout_plan.get("math_block_reflows", [])
    if not isinstance(math_block_reflow_rules, list):
        raise ValueError("layout replacement plan math_block_reflows must be an array")
    fused, math_block_reflow_changes = apply_evidence_math_block_reflows(
        fused, math_block_reflow_rules
    )
    math_reflow_rules = layout_plan.get("math_reflows", [])
    if not isinstance(math_reflow_rules, list):
        raise ValueError("layout replacement plan math_reflows must be an array")
    fused, math_reflow_changes = apply_evidence_math_reflows(
        fused, math_reflow_rules
    )
    unresolved_run_on_math = suspicious_run_on_inline_math(fused)
    if unresolved_run_on_math:
        preview = "; ".join(
            " ".join(body.split())[:180] for body in unresolved_run_on_math[:4]
        )
        raise ValueError(
            f"{book_id} still has {len(unresolved_run_on_math)} fused inline "
            f"derivations after evidence reflow: {preview}"
        )
    dangling_math = suspicious_dangling_math_rows(fused)
    if dangling_math:
        preview = "; ".join(dangling_math[:6])
        raise ValueError(
            f"{book_id} still has {len(dangling_math)} dangling equation "
            f"rows after evidence repair: {preview}"
        )
    expected_graphics_delta = layout_plan.get("expected_includegraphics_delta", 0)
    if not isinstance(expected_graphics_delta, int):
        raise ValueError("expected_includegraphics_delta must be an integer")
    expected_content_graphics = (
        source_inventory["includegraphics"] + expected_graphics_delta
    )
    actual_content_graphics = len(list(INCLUDEGRAPHICS_RE.finditer(fused)))
    if actual_content_graphics != expected_content_graphics:
        raise ValueError(
            f"{book_id} repaired figure inventory mismatch: expected "
            f"{expected_content_graphics}, found {actual_content_graphics}"
        )
    layout_assertions = validate_layout_plan_assertions(fused, layout_plan)
    centered_figures: dict[str, int] = {"en-main-ja": 0}
    normalized_full_bleed: dict[str, int] = {"en-main-ja": 0}
    fitted_short_tables: dict[str, int] = {"en-main-ja": 0}
    wrapped_long_tables: dict[str, int] = {"en-main-ja": 0}
    fitted_inline_math: dict[str, int] = {"en-main-ja": 0}
    relocated_nested_math_tags = 0
    if validation_profile == "technical_exact":
        fused, relocated_nested_math_tags = relocate_nested_math_tags(fused)
        fused, centered_figures["en-main-ja"] = center_standalone_figures(fused)
        fused, normalized_full_bleed["en-main-ja"] = normalize_full_bleed_images(fused)
        fused, fitted_short_tables["en-main-ja"] = fit_short_simple_longtables(fused)
        fused, complex_short_tables = fit_short_complex_longtables(fused)
        fitted_short_tables["en-main-ja"] += complex_short_tables
        fused, wrapped_long_tables["en-main-ja"] = wrap_long_simple_longtables(fused)
        fused, complex_long_tables = wrap_long_complex_longtables(fused)
        wrapped_long_tables["en-main-ja"] += complex_long_tables
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
            expected_graphics=expected_content_graphics,
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
        "fusion_metrics": fusion_metrics,
        "heading_secondary_coverage": heading_coverage,
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
        "relocated_nested_math_tags": relocated_nested_math_tags,
        "normalized_unwrapped_math_fragments": normalized_math_fragments,
        "normalized_unicode_math_symbols": unicode_math_symbol_count,
        "normalized_unicode_text_fallbacks": unicode_text_fallback_count,
        "evidence_backed_segment_repairs": len(segment_repair_changes),
        "evidence_backed_layout_replacements": layout_replacement_count,
        "evidence_backed_math_block_reflows": len(math_block_reflow_changes),
        "reflowed_math_block_occurrences": sum(
            int(change["occurrences"]) for change in math_block_reflow_changes
        ),
        "evidence_backed_math_reflows": len(math_reflow_changes),
        "reflowed_math_occurrences": sum(
            int(change["occurrences"]) for change in math_reflow_changes
        ),
        "expected_includegraphics_delta": expected_graphics_delta,
        "repaired_content_includegraphics": actual_content_graphics,
        "layout_plan_assertions": layout_assertions,
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
