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
    OUTPUT_ROOT,
    ROOT,
    compare_inventory,
    read_json,
    read_jsonl,
    restored_segment_output,
    validate_chunk_output,
    write_json,
)


INCLUDEGRAPHICS_RE = re.compile(
    r"(?P<prefix>\\includegraphics(?:\[[^\]]*\])?\{)(?P<path>[^{}]+)(?P<suffix>\})"
)
EXACT_GEOMETRY_RE = re.compile(
    r"\\usepackage\[paperwidth=148mm,paperheight=210mm,inner=14mm,outer=12mm,top=14mm,bottom=16mm\]\{geometry\}"
)


def copy_and_rewrite_figures(tex: str, destination: Path) -> str:
    destination.mkdir(parents=True, exist_ok=True)
    copied: dict[Path, Path] = {}

    def replace(match: re.Match[str]) -> str:
        raw = match.group("path")
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
        return match.group("prefix") + copied[source].resolve().as_posix() + match.group("suffix")

    return INCLUDEGRAPHICS_RE.sub(replace, tex)


def pocket_layout(tex: str) -> str:
    pocket_geometry = (
        r"\usepackage[paperwidth=105mm,paperheight=148mm,inner=6.5mm,"
        r"outer=5.5mm,top=8mm,bottom=12mm]{geometry}"
    )
    text, count = EXACT_GEOMETRY_RE.subn(lambda _match: pocket_geometry, tex, count=1)
    if not count:
        text = re.sub(
            r"\\usepackage\[[^\]]*paperwidth=[^\]]+\]\{geometry\}",
            lambda _match: pocket_geometry,
            text,
            count=1,
        )
    text = re.sub(r"\\setstretch\{1\.0?8\}", lambda _match: r"\setstretch{1.12}", text)
    text = text.replace(
        r"\begingroup\small\setlength{\tabcolsep}{3pt}\begin{longtable}",
        r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
    )
    text = wrap_wide_display_math(text, layout="pocket")
    return apply_pocket_footer_defaults(text)


def compile_variant(book_root: Path, language: str, layout: str, tex: str, cover: Path | None) -> dict[str, Any]:
    variant_root = book_root / layout / language
    tex_path = variant_root / "tex/book.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(tex, encoding="utf-8")
    if cover and cover.exists():
        inject_cover_page(tex_path, cover)
    report = compile_tex(tex_path, variant_root / "book.pdf")
    report["layout_clean"] = not report.get("latex_error_markers") and report.get("worst_overfull_pt", 0) <= 2.0
    return report


def assemble(book_id: str, *, compile_pdfs: bool) -> dict[str, Any]:
    book_root = OUTPUT_ROOT / book_id
    manifest = read_json(book_root / "tasks/manifest.json")
    segments = read_jsonl(book_root / "source/segments.jsonl")
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    source_tex = Path(ROOT / manifest["source_exact_tex"]).read_text(encoding="utf-8")
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
            row.update(
                {
                    "source_tex": segment["source_tex"],
                    "en_tex": restored_segment_output(task_segment, output, "en"),
                    "ja_tex": restored_segment_output(task_segment, output, "ja"),
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
            )
            reports[f"pocket_{language}"] = compile_variant(
                book_root,
                language,
                "pocket-large-font",
                pocket_layout(assembled[language]),
                cover,
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
