#!/usr/bin/env python3
"""Assemble validated polished chunks into English/Japanese exact and pocket PDFs."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_pocket_tex_queue import (
    apply_pocket_footer_defaults,
    compile_tex,
    inject_cover_page,
    wrap_wide_display_math,
)
from pocket_polished_common import (
    INLINE_MATH_RE,
    MATH_ENV_RE,
    OUTPUT_ROOT,
    ROOT,
    compare_inventory,
    inventory,
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


def normalize_unwrapped_math_fragments(tex: str) -> tuple[str, int]:
    """Typeset evidence-clear plain OCR math without rewriting prose.

    A grounded repair can restore a subscript or Greek symbol while leaving
    the resulting expression outside math mode (for example
    ``u_o = log ε``).  Such text is invalid TeX because of the underscore.
    This narrow pass recognizes only a variable-with-subscript logarithm
    relation and preserves its exact symbols in proper TeX math.
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
        plain, changed = re.subn(r"(?<=[})∞])\.(?=[A-Z])", ". ", plain)
        count += changed
        return plain, count

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
    count = 0
    for start, end in merged:
        plain, replacements = replace_plain(tex[cursor:start])
        parts.extend((plain, tex[start:end]))
        count += replacements
        cursor = end
    plain, replacements = replace_plain(tex[cursor:])
    parts.append(plain)
    count += replacements
    return "".join(parts), count


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
) -> dict[str, Any]:
    variant_root = book_root / layout / language
    tex_path = variant_root / "tex/book.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(tex, encoding="utf-8")
    injected_cover_count = 0
    if cover and cover.exists():
        injected_cover_count = int(inject_cover_page(tex_path, cover))
    report = compile_tex(tex_path, variant_root / "book.pdf")
    rendered_expected = expected_graphics
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

    centered_figures: dict[str, int] = {"en": 0, "ja": 0}
    normalized_full_bleed: dict[str, int] = {"en": 0, "ja": 0}
    if validation_profile == "technical_exact":
        for language in ("en", "ja"):
            assembled[language], centered_figures[language] = center_standalone_figures(
                assembled[language]
            )
            assembled[language], normalized_full_bleed[language] = normalize_full_bleed_images(
                assembled[language]
            )
            assembled[language] = wrap_wide_display_math(
                assembled[language], layout="exact"
            )

    figure_root = book_root / "assets/figures"
    assembled = {
        language: copy_and_rewrite_figures(tex, figure_root)
        for language, tex in assembled.items()
    }
    source_cover = ROOT / "build-pocket" / book_id / "cover/cover.png"
    cover: Path | None = None
    if source_cover.exists():
        cover = book_root / "cover/cover.png"
        cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_cover, cover)

    reports: dict[str, Any] = {}
    if compile_pdfs:
        for language in ("en", "ja"):
            reports[f"exact_{language}"] = compile_variant(
                book_root,
                language,
                "exact",
                assembled[language],
                cover,
                expected_graphics=source_inventory["includegraphics"],
            )
            reports[f"pocket_{language}"] = compile_variant(
                book_root,
                language,
                "pocket-large-font",
                pocket_layout(assembled[language]),
                cover,
                expected_graphics=source_inventory["includegraphics"],
            )
    else:
        for language in ("en", "ja"):
            exact_tex = book_root / "exact" / language / "tex/book.tex"
            pocket_tex = book_root / "pocket-large-font" / language / "tex/book.tex"
            exact_tex.parent.mkdir(parents=True, exist_ok=True)
            pocket_tex.parent.mkdir(parents=True, exist_ok=True)
            exact_tex.write_text(assembled[language], encoding="utf-8")
            pocket_tex.write_text(pocket_layout(assembled[language]), encoding="utf-8")

    layout_issues = [key for key, report in reports.items() if not report.get("layout_clean")]
    status = {
        "book_id": book_id,
        "status": "complete" if compile_pdfs and not layout_issues else "needs_layout_review" if layout_issues else "assembled",
        "chunk_count": len(tasks),
        "segment_count": len(segments),
        "languages": ["en", "ja"],
        "reports": reports,
        "layout_issues": layout_issues,
        "source_inventory_verified": True,
        "source_inventory": source_inventory,
        "validation_profile": validation_profile,
        "centered_standalone_figures": centered_figures,
        "normalized_full_bleed_images": normalized_full_bleed,
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
