#!/usr/bin/env python3
"""Submit, poll, and download Mathpix whole-PDF textbook OCR jobs.

The exact textbook workflow should prefer Mathpix's document endpoint for
formula-heavy PDFs, because it can return Mathpix Markdown, line JSON, LaTeX
archives, and embedded figure assets for the whole source document.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = "https://api.mathpix.com/v3"
DEFAULT_EXTENSIONS = ["mmd", "md", "tex.zip", "mmd.zip", "lines.json"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def headers() -> dict[str, str]:
    app_id = os.environ.get("MATHPIX_APP_ID")
    app_key = os.environ.get("MATHPIX_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError("MATHPIX_APP_ID and MATHPIX_APP_KEY are required")
    return {"app_id": app_id, "app_key": app_key}


def plan_for(book_id: str) -> dict[str, Any]:
    plan = ROOT / "books" / book_id / "book-plan.json"
    if not plan.exists():
        raise FileNotFoundError(plan)
    return load_json(plan)


def job_dir(book_id: str) -> Path:
    return ROOT / "books" / book_id / "work/exact-tex/mathpix-pdf"


def job_file(book_id: str) -> Path:
    return job_dir(book_id) / "job.json"


def status_file(book_id: str) -> Path:
    return job_dir(book_id) / "status.json"


def source_pdf_from_plan(plan: dict[str, Any]) -> Path:
    source = plan.get("source_paths", {}).get("exact_source")
    if not source:
        raise RuntimeError("book-plan.json does not contain source_paths.exact_source")
    path = ROOT / source
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def mathpix_options(page_ranges: str, *, improve_mathpix: bool) -> dict[str, Any]:
    options: dict[str, Any] = {
        "conversion_formats": {
            "tex.zip": True,
            "mmd.zip": True,
            "md.zip": True,
        },
        "include_equation_tags": True,
        "include_page_breaks": True,
        "include_page_info": False,
        "include_diagram_text": True,
        "preserve_section_numbering": True,
        "enable_tables_fallback": True,
        "rm_spaces": False,
        "rm_fonts": False,
        "math_inline_delimiters": ["\\(", "\\)"],
        "math_display_delimiters": ["\\[", "\\]"],
        "metadata": {
            "improve_mathpix": improve_mathpix,
            "workflow": "pocketpolyglot-exact-textbook-tex",
        },
    }
    if page_ranges:
        options["page_ranges"] = page_ranges
    return options


def submit(book_id: str, *, page_ranges: str, improve_mathpix: bool) -> dict[str, Any]:
    plan = plan_for(book_id)
    source_pdf = source_pdf_from_plan(plan)
    options = mathpix_options(page_ranges, improve_mathpix=improve_mathpix)
    job_dir(book_id).mkdir(parents=True, exist_ok=True)
    with source_pdf.open("rb") as handle:
        response = requests.post(
            f"{API_ROOT}/pdf",
            headers=headers(),
            files={"file": (source_pdf.name, handle, "application/pdf")},
            data={"options_json": json.dumps(options)},
            timeout=120,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Mathpix submit failed status={response.status_code}: {response.text[:800]}")
    payload = response.json()
    record = {
        "book_id": book_id,
        "source_pdf": str(source_pdf.relative_to(ROOT)),
        "page_ranges": page_ranges,
        "options": options,
        "response": payload,
        "pdf_id": payload.get("pdf_id"),
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not record["pdf_id"]:
        raise RuntimeError(f"Mathpix submit response missing pdf_id: {payload}")
    write_json(job_file(book_id), record)
    return record


def read_pdf_id(book_id: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    job = job_file(book_id)
    if not job.exists():
        raise FileNotFoundError(f"no Mathpix job file: {job}")
    pdf_id = load_json(job).get("pdf_id")
    if not pdf_id:
        raise RuntimeError(f"job file has no pdf_id: {job}")
    return str(pdf_id)


def status(book_id: str, *, pdf_id: str = "") -> dict[str, Any]:
    resolved = read_pdf_id(book_id, pdf_id)
    response = requests.get(f"{API_ROOT}/pdf/{resolved}", headers=headers(), timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"Mathpix status failed status={response.status_code}: {response.text[:800]}")
    payload = response.json()
    write_json(status_file(book_id), payload)
    return payload


def conversions_done(payload: dict[str, Any], required: set[str]) -> bool:
    if not required:
        return True
    conversion_status = payload.get("conversion_status") or {}
    for name in required:
        status = conversion_status.get(name, {}).get("status")
        if status != "completed":
            return False
    return True


def wait(
    book_id: str,
    *,
    pdf_id: str = "",
    interval: int,
    timeout: int,
    required_conversions: set[str],
) -> dict[str, Any]:
    start = time.time()
    while True:
        payload = status(book_id, pdf_id=pdf_id)
        state = payload.get("status")
        done = payload.get("percent_done")
        conversion_status = payload.get("conversion_status") or {}
        conversion_summary = ",".join(
            f"{name}:{conversion_status.get(name, {}).get('status', 'missing')}"
            for name in sorted(required_conversions)
        )
        print(
            f"status={state} percent_done={done} "
            f"completed={payload.get('num_pages_completed')}/{payload.get('num_pages')} "
            f"conversions={conversion_summary}",
            flush=True,
        )
        if state == "completed" and conversions_done(payload, required_conversions):
            return payload
        if state == "error":
            raise RuntimeError(json.dumps(payload, ensure_ascii=False, indent=2))
        if timeout and time.time() - start > timeout:
            raise TimeoutError(f"timed out waiting for {book_id} Mathpix job")
        time.sleep(interval)


def download(book_id: str, *, pdf_id: str = "", extensions: list[str]) -> list[Path]:
    resolved = read_pdf_id(book_id, pdf_id)
    out_dir = job_dir(book_id) / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for ext in extensions:
        clean_ext = ext.lstrip(".")
        response = requests.get(f"{API_ROOT}/pdf/{resolved}.{clean_ext}", headers=headers(), timeout=180)
        if response.status_code >= 400:
            raise RuntimeError(f"Mathpix download .{clean_ext} failed status={response.status_code}: {response.text[:800]}")
        output = out_dir / f"{book_id}.{clean_ext}"
        output.write_bytes(response.content)
        outputs.append(output)
        print(f"downloaded={output}", flush=True)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--book-id", required=True)
    submit_parser.add_argument("--page-ranges", default="")
    submit_parser.add_argument("--improve-mathpix", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--book-id", required=True)
    status_parser.add_argument("--pdf-id", default="")

    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("--book-id", required=True)
    wait_parser.add_argument("--pdf-id", default="")
    wait_parser.add_argument("--interval", type=int, default=60)
    wait_parser.add_argument("--timeout", type=int, default=0)
    wait_parser.add_argument(
        "--required-conversion",
        action="append",
        default=["tex.zip", "md.zip", "mmd.zip"],
        help="Conversion status that must be completed before wait exits. Repeatable.",
    )

    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--book-id", required=True)
    download_parser.add_argument("--pdf-id", default="")
    download_parser.add_argument("--extension", action="append", default=[])

    args = parser.parse_args()
    if args.cmd == "submit":
        record = submit(args.book_id, page_ranges=args.page_ranges, improve_mathpix=args.improve_mathpix)
        print(json.dumps(record, ensure_ascii=False, indent=2))
    elif args.cmd == "status":
        print(json.dumps(status(args.book_id, pdf_id=args.pdf_id), ensure_ascii=False, indent=2))
    elif args.cmd == "wait":
        wait(
            args.book_id,
            pdf_id=args.pdf_id,
            interval=args.interval,
            timeout=args.timeout,
            required_conversions=set(args.required_conversion),
        )
    elif args.cmd == "download":
        download(args.book_id, pdf_id=args.pdf_id, extensions=args.extension or DEFAULT_EXTENSIONS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
