#!/usr/bin/env python3
"""OCR a scanned PDF into reviewable Markdown.

The script is tuned for scanned CJK books:
  * render each page with PyMuPDF
  * optionally crop large white margins
  * optionally binarize the page image
  * run Tesseract with a CJK language model
  * write page-by-page Markdown
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover - startup guard
    raise SystemExit(
        "Missing PyMuPDF. Install it with: python -m pip install pymupdf"
    ) from exc

try:
    import numpy as np
    from PIL import Image
except Exception as exc:  # pragma: no cover - startup guard
    raise SystemExit(
        "Missing image dependencies. Install them with: python -m pip install pillow numpy"
    ) from exc

try:
    import cv2
except Exception:  # pragma: no cover - optional
    cv2 = None


_DOC: fitz.Document | None = None
_OPTIONS: "OcrOptions | None" = None


@dataclass(frozen=True)
class OcrOptions:
    pdf: Path
    dpi: int
    lang: str
    psm: int
    crop: bool
    threshold: bool
    join_lines: bool
    drop_page_numbers: bool
    save_images_dir: Path | None


@dataclass(frozen=True)
class PageResult:
    page: int
    text: str
    warning: str = ""


def parse_pages(spec: str, total_pages: int) -> list[int]:
    if spec.strip().lower() == "all":
        return list(range(1, total_pages + 1))

    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if start > end:
                raise ValueError(f"Bad page range {part!r}: start is after end")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))

    bad = [p for p in pages if p < 1 or p > total_pages]
    if bad:
        raise ValueError(f"Page(s) outside 1..{total_pages}: {bad}")
    return sorted(pages)


def _init_worker(options: OcrOptions) -> None:
    global _DOC, _OPTIONS
    _OPTIONS = options
    _DOC = fitz.open(options.pdf)


def pil_from_page(page: fitz.Page, dpi: int) -> Image.Image:
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def crop_margins(gray: Image.Image, dpi: int) -> Image.Image:
    arr = np.asarray(gray)
    dark = arr < 245
    row_cutoff = max(8, int(arr.shape[1] * 0.002))
    col_cutoff = max(8, int(arr.shape[0] * 0.002))
    rows = np.where(dark.sum(axis=1) > row_cutoff)[0]
    cols = np.where(dark.sum(axis=0) > col_cutoff)[0]
    if len(rows) == 0 or len(cols) == 0:
        return gray

    pad = max(12, int(dpi * 0.08))
    top = max(0, int(rows[0]) - pad)
    bottom = min(arr.shape[0], int(rows[-1]) + pad)
    left = max(0, int(cols[0]) - pad)
    right = min(arr.shape[1], int(cols[-1]) + pad)
    return gray.crop((left, top, right, bottom))


def binarize(gray: Image.Image) -> Image.Image:
    arr = np.asarray(gray)
    if cv2 is not None:
        arr = cv2.GaussianBlur(arr, (3, 3), 0)
        _, arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(arr)
    return gray.point(lambda p: 255 if p > 180 else 0)


def preprocess(image: Image.Image, options: OcrOptions) -> Image.Image:
    gray = image.convert("L")
    if options.crop:
        gray = crop_margins(gray, options.dpi)
    if options.threshold:
        gray = binarize(gray)
    return gray


def cjk_join(lines: Iterable[str]) -> str:
    out = ""
    for raw in lines:
        line = re.sub(r"[ \t]+", " ", raw.strip())
        if not line:
            continue
        if not out:
            out = line
            continue

        prev = out[-1]
        cur = line[0]
        if (prev.isascii() and prev.isalnum()) and (cur.isascii() and cur.isalnum()):
            out += " " + line
        else:
            out += line
    return out


def drop_trailing_page_numbers(lines: list[str]) -> list[str]:
    while lines and re.fullmatch(r"\d{1,4}", lines[-1].strip()):
        lines.pop()
    return lines


def clean_text(text: str, join_lines: bool, drop_page_numbers: bool) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if drop_page_numbers:
        lines = drop_trailing_page_numbers(text.splitlines())
        text = "\n".join(lines).strip()
    if not join_lines:
        return text

    blocks = re.split(r"\n\s*\n", text)
    joined = []
    for block in blocks:
        lines = block.splitlines()
        if drop_page_numbers:
            lines = drop_trailing_page_numbers(lines)
        joined.append(cjk_join(lines))
    return "\n\n".join(block for block in joined if block).strip()


def filter_tesseract_warning(stderr: str) -> str:
    ignored = (
        "Error in boxClipToRectangle: box outside rectangle",
        "Error in pixScanForForeground: invalid box",
        "Empty page!!",
    )
    lines = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in ignored:
            continue
        if re.fullmatch(r"Detected \d+ diacritics", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def run_tesseract(image_path: Path, options: OcrOptions) -> tuple[str, str]:
    cmd = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        options.lang,
        "--psm",
        str(options.psm),
        "--dpi",
        str(options.dpi),
        "-c",
        "preserve_interword_spaces=1",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "tesseract failed")
    return proc.stdout, filter_tesseract_warning(proc.stderr)


def ocr_page(page_num: int) -> PageResult:
    assert _DOC is not None
    assert _OPTIONS is not None
    options = _OPTIONS

    page = _DOC.load_page(page_num - 1)
    image = preprocess(pil_from_page(page, options.dpi), options)

    if options.save_images_dir is not None:
        options.save_images_dir.mkdir(parents=True, exist_ok=True)
        image_path = options.save_images_dir / f"page-{page_num:04d}.png"
        image.save(image_path)
        text, warning = run_tesseract(image_path, options)
    else:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            image.save(tmp_path)
            text, warning = run_tesseract(tmp_path, options)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    return PageResult(
        page=page_num,
        text=clean_text(text, options.join_lines, options.drop_page_numbers),
        warning=warning,
    )


def markdown_header(args: argparse.Namespace, total_pages: int, pages: list[int]) -> str:
    page_spec = "all" if len(pages) == total_pages else f"{pages[0]}-{pages[-1]}"
    return "\n".join(
        [
            "---",
            f"source_pdf: {Path(args.pdf).name}",
            f"source_pages: {page_spec}",
            f"total_pdf_pages: {total_pages}",
            "ocr_engine: tesseract",
            f"ocr_language: {args.lang}",
            f"ocr_psm: {args.psm}",
            f"dpi: {args.dpi}",
            f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}",
            "notes: Raw OCR. Review against page images before publication.",
            "---",
            "",
            f"# OCR: {Path(args.pdf).stem}",
            "",
        ]
    )


def write_markdown(output: Path, args: argparse.Namespace, total_pages: int, results: list[PageResult]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    pages = [r.page for r in results]
    with output.open("w", encoding="utf-8") as fh:
        fh.write(markdown_header(args, total_pages, pages))
        for result in results:
            fh.write(f"## Page {result.page}\n\n")
            if result.warning:
                fh.write(f"<!-- tesseract: {result.warning} -->\n\n")
            fh.write(result.text.strip())
            fh.write("\n\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="source scanned PDF")
    parser.add_argument("--pages", default="all", help="page range: all, 12, 12-20, or 1,5,9-12")
    parser.add_argument("--output", default="ocr/book.md", help="Markdown output path")
    parser.add_argument("--lang", default="chi_sim", help="Tesseract language, e.g. chi_sim, chi_tra, jpn, jpn_vert")
    parser.add_argument("--psm", type=int, default=4, help="Tesseract page segmentation mode")
    parser.add_argument("--dpi", type=int, default=300, help="rendering DPI")
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--crop", action="store_true", help="enable automatic margin crop")
    parser.add_argument("--threshold", action="store_true", help="enable external binarization before OCR")
    parser.add_argument("--keep-linebreaks", action="store_true", help="keep OCR line breaks instead of joining paragraphs")
    parser.add_argument("--keep-page-numbers", action="store_true", help="keep isolated page numbers from the scan")
    parser.add_argument("--save-images-dir", help="save preprocessed page images for review")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if shutil.which("tesseract") is None:
        parser.error("tesseract is not installed or not on PATH")

    pdf = Path(args.pdf)
    if not pdf.exists():
        parser.error(f"PDF not found: {pdf}")

    with fitz.open(pdf) as doc:
        total_pages = doc.page_count
    pages = parse_pages(args.pages, total_pages)

    options = OcrOptions(
        pdf=pdf,
        dpi=args.dpi,
        lang=args.lang,
        psm=args.psm,
        crop=args.crop,
        threshold=args.threshold,
        join_lines=not args.keep_linebreaks,
        drop_page_numbers=not args.keep_page_numbers,
        save_images_dir=Path(args.save_images_dir) if args.save_images_dir else None,
    )

    workers = max(1, min(args.workers, len(pages)))
    print(
        f"OCR {pdf.name}: {len(pages)} page(s), lang={args.lang}, psm={args.psm}, "
        f"dpi={args.dpi}, workers={workers}",
        file=sys.stderr,
    )

    if workers == 1:
        _init_worker(options)
        results = [ocr_page(page) for page in pages]
    else:
        with Pool(processes=workers, initializer=_init_worker, initargs=(options,)) as pool:
            results = list(pool.imap(ocr_page, pages))

    write_markdown(Path(args.output), args, total_pages, results)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
