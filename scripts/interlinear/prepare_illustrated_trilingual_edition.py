#!/usr/bin/env python3
"""Create an additive illustrated edition plan from completed trilingual JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def prepare(
    source_book_id: str,
    output_book_id: str,
    *,
    figure_manifest_override: str = "",
    keep_title: bool = False,
) -> Path:
    source_plan_path = ROOT / "books" / source_book_id / "book-plan.json"
    if not source_plan_path.exists():
        raise FileNotFoundError(source_plan_path)
    source_plan = read_json(source_plan_path)

    configured_manifest = (
        figure_manifest_override or str(source_plan.get("figure_manifest") or "")
    )
    figure_manifest_path = ROOT / configured_manifest
    if not figure_manifest_path.exists():
        raise FileNotFoundError(
            f"{source_book_id} has no usable figure manifest: {figure_manifest_path}"
        )
    figure_manifest = read_json(figure_manifest_path)
    figure_count = int(figure_manifest.get("figure_count") or 0)
    if figure_count <= 0:
        raise ValueError(f"{source_book_id} figure manifest is empty")

    output_root = ROOT / "books" / output_book_id
    preview = output_root / "work/trilingual/preview" / f"{output_book_id}.partial.json"
    source_cover = str(source_plan.get("cover_image") or "")
    if not source_cover:
        candidate = ROOT / "assets" / "covers" / source_book_id / "cover.png"
        if candidate.is_file():
            source_cover = relative(candidate)
    illustrated_cover = ROOT / "assets" / "covers" / output_book_id / "cover.png"
    cover_image = (
        relative(illustrated_cover)
        if illustrated_cover.is_file()
        else source_cover
    )

    title_en = str(source_plan.get("book_title_en", source_book_id))
    title_ja = str(source_plan.get("book_title_ja", source_book_id))
    title_zh = str(source_plan.get("book_title_zh", source_book_id))
    if not keep_title:
        title_en = f"{title_en} — Illustrated Edition"
        title_ja = f"{title_ja}・図版収録版"
        title_zh = f"{title_zh}・图文版"
    output_plan = dict(source_plan)
    output_plan.update(
        {
            "book_id": output_book_id,
            "source_book_id": source_book_id,
            "status": "prepared_illustrated_from_complete_trilingual",
            "launchable": False,
            "task_mode": "trilingual_illustrated_edition_reusing_validated_json",
            "assembled_json": relative(preview),
            "preview_json": relative(preview),
            "figure_count": figure_count,
            "figure_manifest": relative(figure_manifest_path),
            "cover_image": cover_image,
            "cover_background_source": source_plan.get("cover_image")
            or f"assets/covers/{source_book_id}/cover.png",
            "book_title_en": title_en,
            "book_title_ja": title_ja,
            "book_title_zh": title_zh,
            "cover_title_en": title_en,
            "cover_title_ja": title_ja,
            "cover_title_zh": title_zh,
            "edition": {
                "kind": "illustrated",
                "label_en": "Illustrated Edition",
                "label_ja": "図版収録版",
                "label_zh": "图文版",
                "output_layout": "en-main-jp-zh",
                "font_profile": "large-font",
                "translation_reuse": True,
                "source_ordered_figures": True,
                "label_in_filename": not keep_title,
            },
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "preparation_notes": {
                **dict(source_plan.get("preparation_notes") or {}),
                "illustrated_edition": (
                    "Reuses the completed source-book chunks without model calls. "
                    "Figures are rendered from paragraph anchors already retained in "
                    "the assembled JSON."
                ),
                "source_plan": relative(source_plan_path),
            },
        }
    )

    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "book-plan.json"
    output_path.write_text(
        json.dumps(output_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-book-id", required=True)
    parser.add_argument("--output-book-id")
    parser.add_argument(
        "--figure-manifest",
        default="",
        help="Use an additive figure manifest instead of the source plan manifest.",
    )
    parser.add_argument(
        "--keep-title",
        action="store_true",
        help="Keep the source title and public filename while adding figures.",
    )
    args = parser.parse_args()
    output_book_id = args.output_book_id or f"{args.source_book_id}-illustrated"
    path = prepare(
        args.source_book_id,
        output_book_id,
        figure_manifest_override=args.figure_manifest,
        keep_title=args.keep_title,
    )
    print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
