#!/usr/bin/env python3
"""Reject cover backgrounds that already contain a book title.

Generated cover art must be textless because typography is applied later by
``compose_book_cover.py``.  This audit uses the locally installed CJK
Tesseract models to catch the most damaging failure mode: a title embedded in
the art and then printed a second time by the compositor.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from compose_book_cover import ROOT, canonical_title, equivalent_title, load_plan


OCR_LANGUAGES = "chi_tra+chi_sim+jpn_vert+jpn+eng"


def resolve_plan(book_id: str) -> Path | None:
    candidates = (
        ROOT / "books" / book_id / "book-plan.json",
        ROOT / "data" / "source-plan" / book_id / "book-plan.json",
    )
    return next((path for path in candidates if path.exists()), None)


def ocr_background(path: Path) -> str:
    result = subprocess.run(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            OCR_LANGUAGES,
            "--psm",
            "11",
        ],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tesseract exited {result.returncode}")
    return result.stdout


def title_values(plan: dict) -> list[str]:
    values: list[str] = []
    for key in ("book_title_wenyan", "book_title_ja", "book_title_zh", "book_title_en"):
        value = str(plan.get(key) or "").strip()
        if value and not any(equivalent_title(value, existing) for existing in values):
            values.append(value)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", dest="books")
    parser.add_argument("--assets-dir", type=Path, default=ROOT / "assets" / "covers")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    assets_dir = args.assets_dir.resolve()
    books = args.books or sorted(path.name for path in assets_dir.iterdir() if path.is_dir())
    records: list[dict[str, object]] = []
    failures = 0

    for book_id in books:
        background = assets_dir / book_id / "background.png"
        plan_path = resolve_plan(book_id)
        if not background.exists() or plan_path is None:
            records.append({"book_id": book_id, "status": "skipped", "reason": "missing background or plan"})
            continue
        try:
            ocr_text = ocr_background(background)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            records.append({"book_id": book_id, "status": "error", "reason": str(exc)})
            failures += 1
            print(f"error {book_id}: {exc}")
            continue

        normalized_ocr = canonical_title(ocr_text)
        matched = [
            title
            for title in title_values(load_plan(plan_path))
            if len(canonical_title(title)) >= 2 and canonical_title(title) in normalized_ocr
        ]
        status = "embedded-title" if matched else "ok"
        if matched:
            failures += 1
            print(f"embedded title: {book_id}: {', '.join(matched)}")
        else:
            print(f"ok: {book_id}")
        records.append(
            {
                "book_id": book_id,
                "status": status,
                "background": str(background),
                "matched_titles": matched,
                "ocr_text": " ".join(ocr_text.split()),
            }
        )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"checked={len(books)} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
