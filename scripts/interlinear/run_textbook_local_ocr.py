#!/usr/bin/env python3
"""Run local OCR engines for exact textbook page ranges.

The runner is deliberately page-range oriented. It slices a source PDF with
qpdf, sends the slice to Marker/Surya, and records logs beside the book's
local-OCR work directory. Full-book runs should only start after smoke ranges
show that formulas, tables, figures, and captions are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required tool not found: {name}")


def parse_range(raw: str) -> tuple[int, int]:
    if "-" not in raw:
        page = int(raw)
        return page, page
    start, end = raw.split("-", 1)
    return int(start), int(end)


def local_manifest(book_id: str) -> dict[str, Any]:
    path = ROOT / "books" / book_id / "tasks/local-ocr-en-zh/manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"prepare local OCR tasks first: {path}")
    return load_json(path)


def first_content_range(book_id: str, count: int) -> tuple[int, int]:
    path = ROOT / "books" / book_id / "tasks/local-ocr-en-zh/pages.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise RuntimeError(f"no local OCR page tasks: {path}")
    pages = [int(row["physical_page"]) for row in rows[:count]]
    return min(pages), max(pages)


def slice_pdf(source_pdf: Path, output_pdf: Path, start: int, end: int) -> None:
    require_tool("qpdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "qpdf",
        str(source_pdf),
        "--pages",
        str(source_pdf),
        f"{start}-{end}",
        "--",
        str(output_pdf),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"qpdf failed:\n{result.stdout}")


def marker_command(python: str, input_pdf: Path, output_dir: Path) -> list[str]:
    marker_bin = Path(python).with_name("marker_single")
    if marker_bin.exists():
        return [
            str(marker_bin),
            str(input_pdf),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "json",
            "--disable_multiprocessing",
            "--disable_tqdm",
        ]
    return [
        python,
        "-c",
        "from marker.scripts.convert_single import convert_single_cli; convert_single_cli()",
        str(input_pdf),
        "--output_dir",
        str(output_dir),
        "--output_format",
        "json",
        "--disable_multiprocessing",
        "--disable_tqdm",
    ]


def run_marker(book_id: str, source_pdf: Path, start: int, end: int, python: str) -> dict[str, Any]:
    work_root = ROOT / "books" / book_id / "work/exact-tex/local-ocr"
    range_dir = work_root / "ranges"
    output_dir = work_root / "marker" / f"pages-{start:04d}-{end:04d}"
    range_pdf = range_dir / f"{book_id}-pages-{start:04d}-{end:04d}.pdf"
    slice_pdf(source_pdf, range_pdf, start, end)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    cmd = marker_command(python, range_pdf, output_dir)
    started = datetime.now(timezone.utc)
    result = run(cmd, env=env)
    finished = datetime.now(timezone.utc)
    log_path = output_dir / "marker.log"
    log_path.write_text(result.stdout, encoding="utf-8", errors="replace")
    report = {
        "book_id": book_id,
        "engine": "marker-surya",
        "source_pdf": str(source_pdf.relative_to(ROOT)),
        "range_pdf": str(range_pdf.relative_to(ROOT)),
        "page_start": start,
        "page_end": end,
        "output_dir": str(output_dir.relative_to(ROOT)),
        "log": str(log_path.relative_to(ROOT)),
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "command": cmd,
        "next_validation": [
            "inspect generated markdown/json/html files in output_dir",
            "compare formulas and tables against range_pdf/source images",
            "if output loses equations, crop those equation regions and run pix2tex fallback",
        ],
    }
    write_json(output_dir / "run-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--engine", choices=["marker"], default="marker")
    parser.add_argument("--page-range", default="", help="Physical source page range, e.g. 12-15.")
    parser.add_argument("--smoke", action="store_true", help="Use the first three content pages.")
    parser.add_argument("--smoke-pages", type=int, default=3)
    parser.add_argument("--venv-python", default=".venv/ocr/bin/python")
    args = parser.parse_args()

    manifest = local_manifest(args.book_id)
    source_pdf = ROOT / manifest["source_pdf"]
    if not source_pdf.exists():
        raise FileNotFoundError(source_pdf)
    if args.smoke:
        start, end = first_content_range(args.book_id, args.smoke_pages)
    elif args.page_range:
        start, end = parse_range(args.page_range)
    else:
        start, end = 1, int(manifest["source_pages"])

    python_path = Path(args.venv_python)
    python = str((ROOT / python_path).absolute()) if not python_path.is_absolute() else str(python_path)
    if not Path(python).exists():
        raise FileNotFoundError(f"OCR venv python not found: {python}")
    report = run_marker(args.book_id, source_pdf, start, end, python)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["returncode"] == 0 else report["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
