#!/usr/bin/env python3
"""Sync one trilingual pair-book build into Nutstore Projects.

This handles the 12 pair PDFs produced by
``scripts/interlinear/compile_trilingual_book_12_previews.sh``:
``jp-en``, ``zh-en``, and ``zh-jp`` in both main directions and both variants.
It is intentionally book-scoped so a sequential queue run can export only the
book that just finished. By default it does not write to Nutstore Share:
`Share/LinguaLeaf` is reserved for maximum-language public editions.
"""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = Path("/home/lachlan/Nutstore Files/Projects/LinguaLeaf")
DEFAULT_SHARE = Path("/home/lachlan/Nutstore Files/Share/LinguaLeaf")

PAIR_LABELS = {
    "jp-en": "日本語-English",
    "en-jp": "English-日本語",
    "zh-en": "中文-English",
    "en-zh": "English-中文",
    "zh-jp": "中文-日本語",
    "jp-zh": "日本語-中文",
}

VARIANT_LABELS = {
    "color": "彩色",
    "blackwhite": "黑白",
}


def clean_title(filename: str, variant: str) -> str:
    title = filename.removesuffix(".pdf")
    title = title.replace("・最大語種・大字版", "")
    if variant == "blackwhite":
        title = title.replace("・黑白）", "）").replace("・黑白", "")
    return title.strip(" ・")


def discover(book_id: str, build_root: Path) -> list[dict[str, str | Path]]:
    records: list[dict[str, str | Path]] = []
    book_root = build_root / book_id
    for pdf in sorted(book_root.glob("*/*/*/*.pdf")):
        if pdf.name == "book.pdf":
            continue
        rel = pdf.relative_to(book_root)
        if len(rel.parts) != 4:
            continue
        pair, main_dir, variant, filename = rel.parts
        if pair not in PAIR_LABELS:
            continue
        if variant not in VARIANT_LABELS:
            continue
        label = PAIR_LABELS.get(pair, pair)
        records.append(
            {
                "source": pdf,
                "book_id": book_id,
                "pair": pair,
                "main_dir": main_dir,
                "variant": variant,
                "language_label": label,
                "title": clean_title(filename, variant),
            }
        )
    return records


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def target_name(record: dict[str, str | Path], title_counts: Counter[str]) -> str:
    title = str(record["title"])
    label = str(record["language_label"])
    variant = str(record["variant"])
    variant_label = VARIANT_LABELS[variant]
    key = f"{title}｜{label}｜{variant_label}"
    stem = key
    if title_counts[key] > 1:
        stem = f"{stem}｜{record['pair']}-{record['main_dir']}"
    return f"{stem}.pdf"


def write_manifest(path: Path, copied: list[tuple[Path, Path]], source_root: Path) -> None:
    lines = [
        "# LinguaLeaf Trilingual Pair Sync",
        "",
        f"Generated from `{source_root}`.",
        "",
        f"PDF count: {len(copied)}",
        "",
    ]
    for src, dst in copied:
        lines.append(f"- `{dst.name}` <- `{src}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--build-root", type=Path, default=ROOT / "build")
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--share", type=Path, default=DEFAULT_SHARE)
    parser.add_argument(
        "--include-share",
        action="store_true",
        help="also copy pair editions to Share; normally avoid this because Share is max-language only",
    )
    args = parser.parse_args()

    records = discover(args.book_id, args.build_root)
    if not records:
        raise SystemExit(f"No trilingual pair PDFs found for {args.book_id}")

    title_counts = Counter(
        f"{record['title']}｜{record['language_label']}｜{VARIANT_LABELS[str(record['variant'])]}"
        for record in records
    )

    project_copied: list[tuple[Path, Path]] = []
    share_copied: list[tuple[Path, Path]] = []
    for record in records:
        src = Path(record["source"])
        name = target_name(record, title_counts)
        label = str(record["language_label"])
        book_id = str(record["book_id"])
        edition = f"{record['pair']}-{record['main_dir']}"
        variant = str(record["variant"])

        project_dst = args.project / "final-pdfs" / label / book_id / edition / variant / name
        copy_file(src, project_dst)
        project_copied.append((src, project_dst))
        if args.include_share:
            share_dst = args.share / variant / name
            copy_file(src, share_dst)
            share_copied.append((src, share_dst))

    source_root = args.build_root / args.book_id
    write_manifest(args.project / "final-pdfs" / "MANIFEST-trilingual-pairs.md", project_copied, source_root)
    if args.include_share:
        write_manifest(args.share / "MANIFEST-trilingual-pairs.md", share_copied, source_root)
    print(f"copied_project={len(project_copied)}")
    print(f"copied_share={len(share_copied)}")
    print(f"project_root={args.project / 'final-pdfs'}")
    print(f"share_root={args.share}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
