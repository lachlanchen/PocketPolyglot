#!/usr/bin/env python3
"""Convert a PDF source to Markdown, using OCR when embedded text is insufficient."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPACE_RE = re.compile(r"\s+")
CONTENT_RE = re.compile(r"[\w\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff]")


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, stderr=subprocess.STDOUT).decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.replace("\f", "\n").splitlines():
        line = SPACE_RE.sub(" ", raw.replace("\u3000", " ").replace("\u00a0", " ")).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def content_chars(text: str) -> int:
    return len(CONTENT_RE.findall(text))


def markdown_from_text(pdf: Path, text: str, title: str) -> str:
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    return (
        "---\n"
        f"source_pdf: {pdf.name}\n"
        "conversion: pdftotext\n"
        f"generated_at: {generated_at}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{text.strip()}\n"
    )


def run_ocr(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "scripts/ocr/pdf_to_markdown.py",
        str(args.pdf),
        "--output",
        str(args.output),
        "--lang",
        args.ocr_lang,
        "--psm",
        str(args.ocr_psm),
        "--dpi",
        str(args.ocr_dpi),
        "--workers",
        str(args.ocr_workers),
        "--pages",
        args.ocr_pages,
    ]
    if args.ocr_crop:
        cmd.append("--crop")
    if args.ocr_threshold:
        cmd.append("--threshold")
    if args.keep_linebreaks:
        cmd.append("--keep-linebreaks")
    if args.keep_page_numbers:
        cmd.append("--keep-page-numbers")
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--min-content-chars", type=int, default=2000)
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--ocr-lang", default="chi_sim")
    parser.add_argument("--ocr-psm", type=int, default=4)
    parser.add_argument("--ocr-dpi", type=int, default=220)
    parser.add_argument("--ocr-workers", type=int, default=8)
    parser.add_argument("--ocr-pages", default="all")
    parser.add_argument("--ocr-crop", action="store_true")
    parser.add_argument("--ocr-threshold", action="store_true")
    parser.add_argument("--keep-linebreaks", action="store_true")
    parser.add_argument("--keep-page-numbers", action="store_true")
    args = parser.parse_args()

    pdf = args.pdf
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    if not pdf.exists():
        parser.error(f"PDF not found: {args.pdf}")

    title = args.title or pdf.stem
    text = ""
    chars = 0
    if not args.force_ocr:
        try:
            text = normalize_text(run_text(["pdftotext", "-layout", str(pdf), "-"]))
            chars = content_chars(text)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"pdftotext_failed={exc}", flush=True)

    if not args.force_ocr and chars >= args.min_content_chars:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown_from_text(pdf, text, title), encoding="utf-8")
        print(f"conversion=pdftotext content_chars={chars} output={args.output}", flush=True)
        return 0

    reason = "forced" if args.force_ocr else f"insufficient_text content_chars={chars} min={args.min_content_chars}"
    print(f"conversion=ocr reason={reason}", flush=True)
    run_ocr(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
