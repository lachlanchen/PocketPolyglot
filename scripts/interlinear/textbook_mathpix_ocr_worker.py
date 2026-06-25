#!/usr/bin/env python3
"""Render textbook pages and run Mathpix OCR for exact-TeX conversion.

This worker only creates evidence artifacts: page PNGs plus Mathpix JSON/MMD.
It deliberately does not claim to produce final TeX. A later review step must
compare each page image with the OCR output and write reviewed TeX fragments.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
MATHPIX_URL = "https://api.mathpix.com/v3/text"


def load_tasks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def page_in_range(page: int, ranges: list[tuple[int, int]]) -> bool:
    if not ranges:
        return True
    return any(start <= page <= end for start, end in ranges)


def parse_page_ranges(values: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                ranges.append((int(start), int(end)))
            else:
                page = int(part)
                ranges.append((page, page))
    return ranges


def render_page(task: dict[str, Any], *, dpi: int, force: bool) -> Path:
    image = ROOT / task["render_image"]
    if image.exists() and not force:
        return image
    image.parent.mkdir(parents=True, exist_ok=True)
    prefix = image.with_suffix("")
    cmd = [
        "pdftocairo",
        "-png",
        "-singlefile",
        "-r",
        str(dpi),
        "-f",
        str(task["physical_page"]),
        "-l",
        str(task["physical_page"]),
        str(ROOT / task["source_pdf"]),
        str(prefix),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    if not image.exists():
        raise FileNotFoundError(image)
    return image


def mathpix_request(image: Path, *, timeout: int) -> dict[str, Any]:
    app_id = os.environ.get("MATHPIX_APP_ID")
    app_key = os.environ.get("MATHPIX_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError("MATHPIX_APP_ID and MATHPIX_APP_KEY are required for Mathpix OCR")
    data = base64.b64encode(image.read_bytes()).decode("ascii")
    payload = {
        "src": f"data:image/png;base64,{data}",
        "formats": ["text", "latex_styled"],
        "math_inline_delimiters": ["\\(", "\\)"],
        "math_display_delimiters": ["\\[", "\\]"],
        "rm_spaces": False,
        "include_line_data": True,
        "include_word_data": False,
    }
    response = requests.post(
        MATHPIX_URL,
        headers={
            "app_id": app_id,
            "app_key": app_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Mathpix OCR failed status={response.status_code}: {response.text[:500]}")
    return response.json()


def write_mathpix_outputs(task: dict[str, Any], result: dict[str, Any]) -> None:
    json_path = ROOT / task["mathpix_json"]
    mmd_path = ROOT / task["mathpix_mmd"]
    json_path.parent.mkdir(parents=True, exist_ok=True)
    mmd_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mmd = str(result.get("text") or result.get("latex_styled") or "")
    mmd_path.write_text(mmd.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-jsonl", required=True)
    parser.add_argument("--pages", action="append", default=[], help="Page or range, e.g. 1,5-9. Repeatable.")
    parser.add_argument("--dpi", type=int, default=240)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--skip-non-content", action="store_true")
    args = parser.parse_args()

    tasks_path = ROOT / args.tasks_jsonl
    tasks = load_tasks(tasks_path)
    ranges = parse_page_ranges(args.pages)
    processed = 0
    skipped = 0
    for task in tasks:
        page = int(task["physical_page"])
        if not page_in_range(page, ranges):
            skipped += 1
            continue
        if args.skip_non_content and not task.get("is_content_page"):
            skipped += 1
            continue
        image = render_page(task, dpi=args.dpi, force=args.force)
        if args.render_only or not task.get("requires_mathpix"):
            processed += 1
            continue
        json_path = ROOT / task["mathpix_json"]
        if json_path.exists() and not args.force:
            processed += 1
            continue
        result = mathpix_request(image, timeout=args.timeout)
        write_mathpix_outputs(task, result)
        processed += 1
        time.sleep(args.sleep)
    print(f"processed={processed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
