#!/usr/bin/env python3
"""Create page-level review tasks from editable textbook validation reports."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def source_pdf(book_id: str) -> Path:
    plan = load_json(ROOT / "books" / book_id / "book-plan.json")
    source = plan.get("source_paths", {}).get("exact_source")
    if not source:
        raise RuntimeError(f"{book_id} has no source_paths.exact_source")
    return ROOT / source


def source_page_text(pdf: Path, page: int) -> str:
    return run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"]).strip()


def line_to_source_page_map(source_tex: Path) -> dict[int, int]:
    lines = source_tex.read_text(encoding="utf-8", errors="replace").splitlines()
    page = 1
    mapping: dict[int, int] = {}
    for idx, line in enumerate(lines, start=1):
        mapping[idx] = page
        if "\\clearpage" in line:
            page += 1
    return mapping


def collect_lines(report: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    collected: list[tuple[str, int, dict[str, Any]]] = []
    for item in report.get("worst_overfull", []):
        collected.append(("overfull", int(item["line_start"]), item))
    for item in report.get("worst_float_too_large", []):
        collected.append(("float_too_large", int(item["line"]), item))
    for item in report.get("suspect_ocr", []):
        collected.append(("suspect_ocr", int(item["line"]), item))
    return collected


def prepare(book_id: str, build_dir: Path, *, render_images: bool) -> dict[str, Any]:
    report_path = build_dir / "validation-report.json"
    source_tex = build_dir / "source.tex"
    report = load_json(report_path)
    mapping = line_to_source_page_map(source_tex)
    pdf = source_pdf(book_id)
    task_root = ROOT / "books" / book_id / "tasks/editable-review"
    image_root = ROOT / "books" / book_id / "work/exact-tex/review-page-images"

    by_page: dict[int, dict[str, Any]] = {}
    for issue_type, line, item in collect_lines(report):
        page = mapping.get(line, 1)
        task = by_page.setdefault(
            page,
            {
                "schema_version": 1,
                "task_type": "textbook_editable_tex_page_review",
                "book_id": book_id,
                "source_page_estimate": page,
                "source_pdf": str(pdf.relative_to(ROOT)),
                "source_page_image": str((image_root / f"page-{page:04d}.png").relative_to(ROOT)),
                "generated_source_tex": str(source_tex.relative_to(ROOT)),
                "issues": [],
                "source_page_text_preview": source_page_text(pdf, page)[:2500],
                "requirements": [
                    "compare generated TeX against source page image and source embedded text",
                    "repair OCR prose errors without deleting formulas",
                    "repair formula/table TeX so it compiles and matches the source meaning",
                    "avoid overfull lines in pocket layout",
                ],
            },
        )
        task["issues"].append({"type": issue_type, "line": line, "detail": item})

    rows = [by_page[key] for key in sorted(by_page)]
    write_jsonl(task_root / "tasks.jsonl", rows)
    write_json(
        task_root / "manifest.json",
        {
            "schema_version": 1,
            "book_id": book_id,
            "status": "prepared_review_not_started",
            "task_count": len(rows),
            "source_validation_report": str(report_path.relative_to(ROOT)),
            "tasks_jsonl": str((task_root / "tasks.jsonl").relative_to(ROOT)),
        },
    )

    if render_images and rows:
        image_root.mkdir(parents=True, exist_ok=True)
        for row in rows:
            page = int(row["source_page_estimate"])
            output_prefix = image_root / f"page-{page:04d}"
            if not (image_root / f"page-{page:04d}.png").exists():
                run(["pdftocairo", "-png", "-f", str(page), "-l", str(page), "-singlefile", "-r", "180", str(pdf), str(output_prefix)])

    return {"book_id": book_id, "review_task_count": len(rows), "tasks_jsonl": str((task_root / "tasks.jsonl").relative_to(ROOT))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--render-images", action="store_true")
    args = parser.parse_args()
    summary = prepare(args.book_id, ROOT / args.build_dir, render_images=args.render_images)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
