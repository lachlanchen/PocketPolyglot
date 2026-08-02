#!/usr/bin/env python3
"""OCR selected PDF pages column by column into source-auditable Markdown."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

import fitz


def parse_page_range(value: str) -> list[int]:
    pages: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise argparse.ArgumentTypeError(f"descending page range: {part}")
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    if not pages:
        raise argparse.ArgumentTypeError("at least one PDF page is required")
    return pages


def parse_columns(value: str) -> list[tuple[float, float]]:
    columns: list[tuple[float, float]] = []
    for part in value.split(","):
        try:
            left_text, right_text = part.strip().split(":", 1)
            left, right = float(left_text), float(right_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid column range: {part}") from exc
        if right <= left:
            raise argparse.ArgumentTypeError(f"empty column range: {part}")
        columns.append((left, right))
    if not columns:
        raise argparse.ArgumentTypeError("at least one column range is required")
    return columns


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_line(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()
    if not text:
        return ""
    if re.match(r"^(?:#{1,6}\s|[-+*]\s|\d+[.)]\s)", text):
        text = "\\" + text
    return text + "  "


def run_tesseract(image: Path, *, language: str, psm: int) -> str:
    env = os.environ.copy()
    env.setdefault("OMP_THREAD_LIMIT", "1")
    result = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", language, "--psm", str(psm)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Tesseract failed for {image} (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OCR dense multi-column PDF pages in deterministic reading order."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pages", required=True, type=parse_page_range)
    parser.add_argument("--columns", required=True, type=parse_columns)
    parser.add_argument("--top", type=float, required=True, help="Default crop top in PDF points.")
    parser.add_argument("--first-page-top", type=float, help="Optional top for the first selected page.")
    parser.add_argument("--bottom", type=float, required=True, help="Crop bottom in PDF points.")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--psm", type=int, default=6)
    parser.add_argument("--heading", default="INDEX")
    args = parser.parse_args()

    source = args.pdf.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.dpi < 150:
        raise ValueError("DPI below 150 is not suitable for audited OCR")

    document = fitz.open(source)
    output: list[str] = [
        f"## {args.heading}",
        "",
        (
            f"<!-- OCR source={source.name}; sha256={sha256_file(source)}; "
            f"pages={','.join(str(page) for page in args.pages)}; dpi={args.dpi}; "
            f"engine=tesseract; psm={args.psm} -->"
        ),
        "",
    ]
    matrix = fitz.Matrix(args.dpi / 72.0, args.dpi / 72.0)
    try:
        with tempfile.TemporaryDirectory(prefix="multicolumn-ocr-") as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            for page_index, page_number in enumerate(args.pages):
                if page_number < 1 or page_number > document.page_count:
                    raise ValueError(f"PDF page out of range: {page_number}")
                page = document.load_page(page_number - 1)
                top = args.first_page_top if page_index == 0 and args.first_page_top else args.top
                output.extend((f"<!-- source-page:{page_number} -->", ""))
                for column_index, (left, right) in enumerate(args.columns, start=1):
                    clip = fitz.Rect(left, top, right, args.bottom)
                    if clip.is_empty or not page.rect.contains(clip):
                        raise ValueError(
                            f"crop outside page {page_number}: {list(clip)} vs {list(page.rect)}"
                        )
                    image = temp_dir / f"page-{page_number:04d}-column-{column_index:02d}.png"
                    page.get_pixmap(matrix=matrix, clip=clip, alpha=False).save(image)
                    text = run_tesseract(image, language=args.language, psm=args.psm)
                    lines = [markdown_line(line) for line in text.splitlines()]
                    while lines and not lines[-1]:
                        lines.pop()
                    output.extend(lines)
                    output.append("")
    finally:
        document.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
