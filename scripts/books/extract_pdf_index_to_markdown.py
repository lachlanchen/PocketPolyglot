#!/usr/bin/env python3
"""Extract a clean, semantic Markdown index from a born-digital PDF region."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import fitz


RUNNING_HEADER_RE = re.compile(
    r"^(?:index|round heads:\s+the earliest rock paintings in the sahara)$",
    re.I,
)
SECTION_RE = re.compile(r"^[A-Z]$")
CONTINUATION_RE = re.compile(r"^[\d;,:–—-]")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def ordered_body_blocks(page: fitz.Page, *, top_margin_points: float) -> list[str]:
    """Return left-column then right-column text blocks in reading order."""

    midpoint = page.rect.width / 2
    blocks = [
        block
        for block in page.get_text("blocks", sort=False)
        if float(block[1]) >= top_margin_points and str(block[4]).strip()
    ]
    blocks.sort(key=lambda block: (0 if float(block[0]) < midpoint else 1, float(block[1])))
    return [str(block[4]) for block in blocks]


def source_lines(blocks: Iterable[str]) -> Iterable[str]:
    for block in blocks:
        for raw_line in block.replace("\f", "\n").splitlines():
            line = compact(raw_line)
            if not line or RUNNING_HEADER_RE.fullmatch(line):
                continue
            yield line


def parse_index_entries(lines: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Parse section letters and entries while preserving source order."""

    sections: list[str] = []
    entries: list[tuple[str, str]] = []
    current_section = ""
    current_entry = ""

    def flush() -> None:
        nonlocal current_entry
        if current_entry:
            entries.append((current_section, compact(current_entry)))
            current_entry = ""

    for line in lines:
        if SECTION_RE.fullmatch(line):
            flush()
            current_section = line
            if line not in sections:
                sections.append(line)
            continue
        if CONTINUATION_RE.match(line) and current_entry:
            current_entry = f"{current_entry} {line}"
            continue
        if ";" in line:
            flush()
            current_entry = line
            continue
        if current_entry:
            current_entry = f"{current_entry} {line}"
    flush()
    return sections, entries


def render_markdown(title: str, sections: list[str], entries: list[tuple[str, str]]) -> str:
    grouped: dict[str, list[str]] = {section: [] for section in sections}
    for section, entry in entries:
        grouped.setdefault(section or "Other", []).append(entry)

    out = [
        f"## {title}",
        "",
        "<!-- Reconstructed from the source PDF text layer; entry order and page references are preserved. -->",
        "",
    ]
    for section, section_entries in grouped.items():
        if not section_entries:
            continue
        out.extend([f"### {section}", ""])
        for entry in section_entries:
            term, separator, references = entry.partition(";")
            if separator:
                out.append(f"- **{term.strip()}**; {references.strip()}")
            else:
                out.append(f"- {entry}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--start-page", type=int, required=True)
    parser.add_argument("--end-page", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--title", default="INDEX")
    parser.add_argument("--top-margin-points", type=float, default=65.0)
    parser.add_argument("--minimum-entries", type=int, default=20)
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.exists():
        raise SystemExit(f"missing source PDF: {source}")

    document = fitz.open(source)
    try:
        if args.start_page < 1 or args.end_page > document.page_count:
            raise SystemExit(
                f"page range {args.start_page}-{args.end_page} is outside 1-{document.page_count}"
            )
        blocks: list[str] = []
        for page_number in range(args.start_page, args.end_page + 1):
            blocks.extend(
                ordered_body_blocks(
                    document.load_page(page_number - 1),
                    top_margin_points=args.top_margin_points,
                )
            )
    finally:
        document.close()

    sections, entries = parse_index_entries(source_lines(blocks))
    if len(entries) < args.minimum_entries:
        raise SystemExit(
            f"index extraction found only {len(entries)} entries; "
            f"expected at least {args.minimum_entries}"
        )
    if not sections:
        raise SystemExit("index extraction found no alphabetical sections")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(args.title, sections, entries), encoding="utf-8")

    report_path = args.report.resolve() if args.report else output.with_suffix(".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "source": portable_path(source),
                "source_sha256": source_sha256(source),
                "page_range": [args.start_page, args.end_page],
                "sections": sections,
                "section_count": len(sections),
                "entry_count": len(entries),
                "output": portable_path(output),
                "output_sha256": source_sha256(output),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"output={output} sections={len(sections)} entries={len(entries)} "
        f"pages={args.start_page}-{args.end_page}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
