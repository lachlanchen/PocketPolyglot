#!/usr/bin/env python3
"""Generate first-page PNG previews from the flat PDF export manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/books/manifest.json"),
        help="Flat PDF export manifest written by export_flat_build_pdfs.py.",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("build/books"),
        help="Directory that contains the flat PDF files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/readme-previews"),
        help="Directory for generated PNG previews.",
    )
    parser.add_argument(
        "--direction",
        default="zh-main",
        choices=("zh-main", "jp-main"),
        help="Preferred edition direction to use for previews.",
    )
    parser.add_argument(
        "--variant",
        default="color",
        choices=("color", "blackwhite"),
        help="Preferred edition variant to use for previews.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=115,
        help="pdftoppm render DPI.",
    )
    return parser.parse_args()


def choose_preview_items(items: list[dict[str, object]], direction: str, variant: str) -> list[dict[str, object]]:
    by_book: dict[str, list[dict[str, object]]] = {}
    for item in items:
        by_book.setdefault(str(item["book_id"]), []).append(item)

    chosen: list[dict[str, object]] = []
    for book_id in sorted(by_book):
        editions = by_book[book_id]
        preferred = [
            item
            for item in editions
            if item.get("direction") == direction and item.get("variant") == variant
        ]
        fallback = sorted(editions, key=lambda item: (str(item.get("direction")), str(item.get("variant"))))
        chosen.append((preferred or fallback)[0])
    return chosen


def main() -> int:
    args = parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not isinstance(items, list):
        raise SystemExit(f"{args.manifest} does not contain an items list")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    previews = []
    for item in choose_preview_items(items, args.direction, args.variant):
        book_id = str(item["book_id"])
        pdf_path = args.pdf_dir / str(item["filename"])
        if not pdf_path.exists():
            raise SystemExit(f"missing PDF for {book_id}: {pdf_path}")

        prefix = args.output_dir / book_id
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-singlefile",
                "-f",
                "1",
                "-l",
                "1",
                "-r",
                str(args.dpi),
                str(pdf_path),
                str(prefix),
            ],
            check=True,
        )
        previews.append(
            {
                "book_id": book_id,
                "title": item.get("title", book_id),
                "direction": item.get("direction"),
                "variant": item.get("variant"),
                "pdf": item.get("filename"),
                "preview": f"{book_id}.png",
            }
        )

    (args.output_dir / "manifest.json").write_text(
        json.dumps({"count": len(previews), "items": previews}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(previews)} previews in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
