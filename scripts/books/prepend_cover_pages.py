#!/usr/bin/env python3
"""Prepend generated cover images to finished color PDFs.

This is a fast post-processing path for large books whose TeX sources already
use `assets/covers/<book-id>/cover.png`, but where a full rebuild would be
unnecessarily slow.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOOKS = [
    "red-rising-1",
    "red-rising-2",
    "red-rising-3",
    "japanese-history",
    "spring-snow",
    "inugami-curse",
    "i-am-a-cat",
    "botchan",
    "gone-with-the-wind",
]


def color_pdfs(build_dir: Path, book_id: str) -> list[Path]:
    book_dir = build_dir / book_id
    if not book_dir.exists():
        return []
    return sorted(
        pdf
        for pdf in book_dir.glob("**/color/*.pdf")
        if pdf.name != "book.pdf" and pdf.is_file()
    )


def source_has_current_cover(pdf: Path, book_id: str) -> bool:
    source = pdf.with_name("source.tex")
    if not source.exists():
        return False
    cover_rel = f"assets/covers/{book_id}/cover.png"
    try:
        return cover_rel in source.read_text(encoding="utf-8")
    except OSError:
        return False


def has_fresh_marker(pdf: Path, cover: Path) -> bool:
    marker = pdf.with_suffix(pdf.suffix + ".cover.json")
    if not marker.exists():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        data.get("cover") == str(cover)
        and marker.stat().st_mtime >= pdf.stat().st_mtime
        and marker.stat().st_mtime >= cover.stat().st_mtime
    )


def first_page_has_image(pdf: Path) -> bool:
    try:
        reader = PdfReader(str(pdf))
        if not reader.pages:
            return False
        return bool(list(getattr(reader.pages[0], "images", []) or []))
    except Exception as exc:  # pragma: no cover - defensive for malformed PDFs.
        print(f"warn: could not inspect first page images for {pdf}: {exc}")
        return False


def make_cover_pdf(cover_image: Path, width: float, height: float, target: Path) -> None:
    c = canvas.Canvas(str(target), pagesize=(width, height))
    c.drawImage(
        ImageReader(str(cover_image)),
        0,
        0,
        width=width,
        height=height,
        preserveAspectRatio=False,
        anchor="c",
    )
    c.showPage()
    c.save()


def prepend_cover(pdf: Path, cover_image: Path) -> None:
    reader = PdfReader(str(pdf))
    if not reader.pages:
        raise RuntimeError(f"{pdf} has no pages")
    box = reader.pages[0].mediabox
    width = float(box.width)
    height = float(box.height)

    with tempfile.TemporaryDirectory(prefix="cover-prepend-", dir=str(pdf.parent)) as tmp_name:
        tmp_dir = Path(tmp_name)
        cover_pdf = tmp_dir / "cover.pdf"
        output_pdf = tmp_dir / "output.pdf"
        make_cover_pdf(cover_image, width, height, cover_pdf)

        cover_reader = PdfReader(str(cover_pdf))
        writer = PdfWriter()
        writer.add_page(cover_reader.pages[0])
        for page in reader.pages:
            writer.add_page(page)
        with output_pdf.open("wb") as handle:
            writer.write(handle)
        output_pdf.replace(pdf)

    marker = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cover": str(cover_image),
        "pdf": str(pdf),
    }
    pdf.with_suffix(pdf.suffix + ".cover.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--assets-dir", type=Path, default=ROOT / "assets" / "covers")
    parser.add_argument("--book", action="append", dest="books", help="book id to process")
    parser.add_argument("--force", action="store_true", help="prepend even if a fresh marker exists")
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    assets_dir = args.assets_dir.resolve()
    books = args.books or DEFAULT_BOOKS

    processed = 0
    skipped = 0
    missing = 0
    for book_id in books:
        cover = assets_dir / book_id / "cover.png"
        pdfs = color_pdfs(build_dir, book_id)
        if not cover.exists():
            print(f"missing cover: {book_id} -> {cover}")
            missing += 1
            continue
        if not pdfs:
            print(f"missing color pdfs: {book_id}")
            missing += 1
            continue
        for pdf in pdfs:
            if not args.force and has_fresh_marker(pdf, cover):
                print(f"skip marker: {pdf}")
                skipped += 1
                continue
            if not args.force and first_page_has_image(pdf):
                print(f"skip image-cover: {pdf}")
                skipped += 1
                continue
            if not args.force and source_has_current_cover(pdf, book_id):
                print(f"source has cover but pdf has no first-page image: {pdf}")
            print(f"prepend cover: {pdf}")
            prepend_cover(pdf, cover)
            processed += 1

    print(f"processed={processed} skipped={skipped} missing={missing}")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
