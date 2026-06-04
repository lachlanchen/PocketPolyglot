#!/usr/bin/env python3
"""Build searchable OCR PDFs and review Markdown for the Sanxingdui sources."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "sanxingdui"

BOOKS: list[dict[str, str]] = [
    {
        "slug": "shenqi-gushu",
        "title": "神奇古蜀_三星堆和金沙遗址出土文物",
        "source": "sources/sanxingdui/神奇古蜀_三星堆和金沙遗址出土文物.pdf",
    },
    {
        "slug": "renjian-tianguo",
        "title": "人间天国_ 三星堆.金沙王都发现之谜",
        "source": "sources/sanxingdui/人间天国_ 三星堆.金沙王都发现之谜.pdf",
    },
    {
        "slug": "huaxia-shendu",
        "title": "华夏神都_ 全方位揭谜三星堆文明",
        "source": "sources/sanxingdui/华夏神都_ 全方位揭谜三星堆文明.pdf",
    },
    {
        "slug": "jisikeng",
        "title": "三星堆祭祀坑",
        "source": "sources/sanxingdui/三星堆祭祀坑.pdf",
    },
    {
        "slug": "wenwu-quanjilu",
        "title": "三星堆出土文物全记录（套装共3册）",
        "source": "sources/sanxingdui/三星堆出土文物全记录（套装共3册）.pdf",
    },
]


def run(cmd: list[str], *, log_path: Path) -> int:
    print("+ " + " ".join(cmd), flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        return process.wait()


def pdf_pages(path: Path) -> int:
    result = subprocess.check_output(["pdfinfo", str(path)], cwd=ROOT, text=True, stderr=subprocess.STDOUT)
    for line in result.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return 0


def content_chars(path: Path) -> int:
    try:
        text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], cwd=ROOT, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return 0
    return sum(1 for char in text.decode("utf-8", errors="replace") if not char.isspace())


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), **payload}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def convert_one(book: dict[str, str], args: argparse.Namespace) -> None:
    slug = book["slug"]
    title = book["title"]
    source = ROOT / book["source"]
    if not source.exists():
        raise FileNotFoundError(source)

    output_dir = ROOT / "build" / BOOK_ID / slug
    work_dir = ROOT / "books" / BOOK_ID / "work" / "ocr" / slug
    markdown_dir = ROOT / "books" / BOOK_ID / "markdown"
    output_pdf = output_dir / f"{title}（OCR文本版）.pdf"
    sidecar = work_dir / "sidecar.txt"
    stats = work_dir / "stats.json"
    status = work_dir / "status.json"
    markdown = markdown_dir / f"{slug}.ocr.md"
    log = work_dir / "ocrmypdf.log"

    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)

    source_pages = pdf_pages(source)
    write_status(
        status,
        {
            "status": "started",
            "slug": slug,
            "title": title,
            "source": str(source.relative_to(ROOT)),
            "source_pages": source_pages,
        },
    )

    if not args.force and output_pdf.exists() and sidecar.exists() and markdown.exists():
        print(f"skip_existing={slug} pdf={output_pdf}", flush=True)
        write_status(status, {"status": "skipped_existing", "slug": slug, "output_pdf": str(output_pdf.relative_to(ROOT))})
        return

    ocrmypdf = shutil.which("ocrmypdf") or str(Path.home() / ".local/bin/ocrmypdf")
    cmd = [
        ocrmypdf,
        "-l",
        args.lang,
        "--deskew",
        "--rotate-pages",
        "--output-type",
        "pdf",
        "--pdf-renderer",
        "hocr",
        "--tesseract-pagesegmode",
        str(args.psm),
        "--tesseract-timeout",
        str(args.tesseract_timeout),
        "--jobs",
        str(args.jobs),
        "--sidecar",
        str(sidecar.relative_to(ROOT)),
    ]
    if args.redo_ocr:
        cmd.append("--redo-ocr")
    if args.skip_text:
        cmd.append("--skip-text")
    if args.pages != "all":
        cmd.extend(["--pages", args.pages])
    cmd.extend([str(source.relative_to(ROOT)), str(output_pdf.relative_to(ROOT))])

    log.write_text("", encoding="utf-8")
    rc = run(cmd, log_path=log)
    if rc != 0 and not args.redo_ocr:
        print(f"ocrmypdf_failed={slug} rc={rc}; retrying_with_redo_ocr=1", flush=True)
        retry = cmd[:]
        retry.insert(-2, "--redo-ocr")
        rc = run(retry, log_path=log)
    if rc != 0:
        write_status(status, {"status": "failed", "slug": slug, "returncode": rc, "log": str(log.relative_to(ROOT))})
        raise SystemExit(rc)

    markdown_cmd = [
        sys.executable,
        "scripts/ocr/sidecar_to_markdown.py",
        "--sidecar",
        str(sidecar.relative_to(ROOT)),
        "--markdown",
        str(markdown.relative_to(ROOT)),
        "--stats",
        str(stats.relative_to(ROOT)),
        "--source-pdf",
        str(source.relative_to(ROOT)),
        "--title",
        title,
        "--slug",
        slug,
    ]
    subprocess.check_call(markdown_cmd, cwd=ROOT)
    out_pages = pdf_pages(output_pdf)
    chars = content_chars(output_pdf)
    write_status(
        status,
        {
            "status": "done",
            "slug": slug,
            "title": title,
            "source": str(source.relative_to(ROOT)),
            "source_pages": source_pages,
            "output_pdf": str(output_pdf.relative_to(ROOT)),
            "output_pages": out_pages,
            "output_content_chars": chars,
            "sidecar": str(sidecar.relative_to(ROOT)),
            "markdown": str(markdown.relative_to(ROOT)),
            "stats": str(stats.relative_to(ROOT)),
            "log": str(log.relative_to(ROOT)),
        },
    )
    print(f"done={slug} pages={out_pages} content_chars={chars} pdf={output_pdf}", flush=True)


def write_plan() -> None:
    plan = {
        "book_id": BOOK_ID,
        "status": "prepared_ocr",
        "description": "Sanxingdui scanned source OCR into searchable PDFs and review Markdown.",
        "books": BOOKS,
        "outputs": {
            "searchable_pdf_dir": f"build/{BOOK_ID}/<slug>/",
            "markdown_dir": f"books/{BOOK_ID}/markdown/",
            "work_dir": f"books/{BOOK_ID}/work/ocr/<slug>/",
        },
    }
    path = ROOT / "books" / BOOK_ID / "book-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", help="process only this slug; may be repeated")
    parser.add_argument("--jobs", type=int, default=max(1, min(4, (os.cpu_count() or 4) // 2)))
    parser.add_argument("--lang", default="chi_sim+eng")
    parser.add_argument("--psm", type=int, default=3)
    parser.add_argument("--pages", default="all")
    parser.add_argument("--tesseract-timeout", type=int, default=240)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--redo-ocr", action="store_true")
    parser.add_argument("--skip-text", action="store_true")
    args = parser.parse_args()

    write_plan()
    wanted = set(args.slug or [])
    unknown = wanted.difference(book["slug"] for book in BOOKS)
    if unknown:
        raise SystemExit(f"unknown slug(s): {', '.join(sorted(unknown))}")
    for book in BOOKS:
        if wanted and book["slug"] not in wanted:
            continue
        convert_one(book, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
