#!/usr/bin/env python3
"""Create a Markdown inventory of PDFs under build/.

The report is intentionally about local build outputs.  It records PDF counts,
sizes, page counts, variant folders, and basic status without tracking the PDFs
themselves.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"


@dataclass(frozen=True)
class PdfInfo:
    path: Path
    book: str
    variant: str
    size: int
    pages: int | None
    status: str
    mtime: dt.datetime


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def mib(size: int) -> str:
    return f"{size / 1024 / 1024:.1f}"


def pdf_pages(path: Path) -> tuple[int | None, str]:
    try:
        result = subprocess.run(
            ["pdfinfo", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001 - report should survive bad PDFs.
        return None, f"pdfinfo-error:{type(exc).__name__}"
    if result.returncode != 0:
        return None, "pdfinfo-failed"
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            value = line.split(":", 1)[1].strip()
            if value.isdigit():
                return int(value), "ok"
    return None, "missing-pages"


def collect_pdfs() -> list[PdfInfo]:
    infos: list[PdfInfo] = []
    for path in sorted(BUILD.rglob("*.pdf")):
        parts = path.relative_to(BUILD).parts
        if not parts:
            continue
        book = parts[0]
        variant = "/".join(parts[1:-1]) or "."
        pages, status = pdf_pages(path)
        stat = path.stat()
        infos.append(
            PdfInfo(
                path=path,
                book=book,
                variant=variant,
                size=stat.st_size,
                pages=pages,
                status=status,
                mtime=dt.datetime.fromtimestamp(stat.st_mtime).astimezone(),
            )
        )
    return infos


def build_dirs() -> list[Path]:
    return sorted(path for path in BUILD.iterdir() if path.is_dir()) if BUILD.exists() else []


def status_for(book_dir: Path, pdfs: list[PdfInfo]) -> str:
    if not book_dir.exists():
        return "missing-dir"
    if not pdfs:
        tex_count = sum(1 for _ in book_dir.rglob("*.tex"))
        return "no-pdf-with-tex" if tex_count else "no-pdf"
    if any(pdf.status != "ok" for pdf in pdfs):
        return "pdfinfo-warning"
    has_color = any("/color" in f"/{pdf.variant}" for pdf in pdfs)
    has_bw = any("/blackwhite" in f"/{pdf.variant}" for pdf in pdfs)
    if has_color and has_bw:
        return "ok-color-bw"
    if has_color:
        return "ok-color-only"
    if has_bw:
        return "ok-bw-only"
    return "ok-other"


def render_markdown(pdfs: list[PdfInfo]) -> str:
    by_book: dict[str, list[PdfInfo]] = defaultdict(list)
    for pdf in pdfs:
        by_book[pdf.book].append(pdf)

    dirs = build_dirs()
    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    total_size = sum(pdf.size for pdf in pdfs)
    ok_count = sum(1 for pdf in pdfs if pdf.status == "ok")
    page_total = sum(pdf.pages or 0 for pdf in pdfs)
    lines: list[str] = [
        "# Build Book Status",
        "",
        f"Generated: {now}",
        "",
        "This report inventories local PDFs under `build/`. Paths are relative to the repository root. "
        "The PDFs themselves remain ignored build artifacts; this file records their current local status only.",
        "",
        "## Summary",
        "",
        f"- Top-level build folders: {len(dirs)}",
        f"- PDF files: {len(pdfs)}",
        f"- PDF files with readable page counts: {ok_count}",
        f"- Total PDF size: {mib(total_size)} MiB",
        f"- Total counted pages: {page_total}",
        "",
        "## Warnings",
        "",
    ]
    warning_dirs = [
        book_dir.name
        for book_dir in dirs
        if status_for(book_dir, by_book.get(book_dir.name, [])) in {"no-pdf", "no-pdf-with-tex"}
    ]
    warning_pdfs = [pdf for pdf in pdfs if pdf.status != "ok"]
    if not warning_dirs and not warning_pdfs:
        lines.append("- None.")
    for book in warning_dirs:
        lines.append(f"- `{book}` has no PDF under its build folder.")
    for pdf in warning_pdfs:
        lines.append(f"- `{rel(pdf.path)}`: {pdf.status}.")
    lines.extend(
        [
            "",
        "## Book Folders",
        "",
        "| Book | Status | PDFs | Color | Black-white | Other | Pages min-max | PDF size MiB | Variants |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for book_dir in dirs:
        book = book_dir.name
        items = by_book.get(book, [])
        color = sum(1 for pdf in items if "/color" in f"/{pdf.variant}")
        bw = sum(1 for pdf in items if "/blackwhite" in f"/{pdf.variant}")
        other = len(items) - color - bw
        pages = [pdf.pages for pdf in items if pdf.pages is not None]
        page_range = f"{min(pages)}-{max(pages)}" if pages else "-"
        variants = sorted({pdf.variant for pdf in items})
        variants_text = "<br>".join(f"`{variant}`" for variant in variants[:12])
        if len(variants) > 12:
            variants_text += f"<br>... +{len(variants) - 12}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{book}`",
                    status_for(book_dir, items),
                    str(len(items)),
                    str(color),
                    str(bw),
                    str(other),
                    page_range,
                    mib(sum(pdf.size for pdf in items)),
                    variants_text or "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Large PDFs",
            "",
            "| Size MiB | Pages | Status | Path |",
            "| ---: | ---: | --- | --- |",
        ]
    )
    for pdf in sorted(pdfs, key=lambda item: item.size, reverse=True)[:40]:
        lines.append(f"| {mib(pdf.size)} | {pdf.pages or '-'} | {pdf.status} | `{rel(pdf.path)}` |")

    lines.extend(
        [
            "",
            "## PDF Inventory",
            "",
            "| Book | Variant | Size MiB | Pages | Status | Modified | PDF |",
            "| --- | --- | ---: | ---: | --- | --- | --- |",
        ]
    )
    for pdf in sorted(pdfs, key=lambda item: rel(item.path)):
        mtime = pdf.mtime.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"| `{pdf.book}` | `{pdf.variant}` | {mib(pdf.size)} | {pdf.pages or '-'} | "
            f"{pdf.status} | {mtime} | `{rel(pdf.path)}` |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        default="references/BUILD_BOOK_STATUS_2026-06-26.md",
        help="Markdown output path",
    )
    args = parser.parse_args()

    pdfs = collect_pdfs()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(pdfs), encoding="utf-8")
    print(output.relative_to(ROOT))
    print(f"pdfs={len(pdfs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
