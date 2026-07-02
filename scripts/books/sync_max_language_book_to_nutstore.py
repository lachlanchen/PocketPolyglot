#!/usr/bin/env python3
"""Sync one maximum-language LinguaLeaf book into Nutstore.

Nutstore Share is a public browsing folder. It should contain only maximum
language public editions such as ``wenyan-en-jp-zh``, ``wayakana-en-jp-zh``,
``en-jp-zh``, ``jp-zh``, and Arabic ``ar-en-jp-zh``. Pair-only editions belong
in Projects, not Share.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "artifacts" / "lingualleaf" / "books"
DEFAULT_PROJECT = Path("/home/lachlan/Nutstore Files/Projects/LinguaLeaf")
DEFAULT_SHARE = Path("/home/lachlan/Nutstore Files/Share/LinguaLeaf")

LANGUAGE_LABELS = {
    "wenyan-en-jp-zh": "文言文-English-日本語-中文",
    "wenyan-jp-zh": "文言文-日本語-中文",
    "wayakana-en-jp-zh": "和歌仮名-English-日本語-中文",
    "ar-en-jp-zh": "العربية-English-日本語-中文",
    "arabic-en-jp-zh": "العربية-English-日本語-中文",
    "en-jp-zh": "English-日本語-中文",
    "jp-zh": "日本語-中文",
}

VARIANT_LABELS = {
    "color": "彩色",
    "blackwhite": "黑白",
}

FAMILY_PRIORITY = {
    "wenyan-en-jp-zh": 5,
    "wenyan-jp-zh": 4,
    "wayakana-en-jp-zh": 3,
    "ar-en-jp-zh": 3,
    "arabic-en-jp-zh": 3,
    "en-jp-zh": 2,
    "jp-zh": 1,
}


def edition_priority(family: str, edition: str) -> int:
    if family == "wayakana-en-jp-zh":
        return 10 if edition.startswith("wayakana-main") else 0
    if family == "wenyan-en-jp-zh":
        return 10 if edition.startswith("wenyan-main") else 0
    if family == "en-jp-zh":
        return 10 if edition.startswith("en-main") else 0
    return 0


def clean_title(filename: str, variant: str) -> str:
    title = filename.removesuffix(".pdf")
    title = title.replace("・最大語種・史記字級", "")
    title = title.replace("・最大語種・大字版", "")
    if variant == "blackwhite":
        title = title.replace("・黑白）", "）").replace("・黑白", "")
    return title.strip(" ・")


def discover(source_root: Path, book_id: str) -> list[dict[str, str | Path]]:
    records: list[dict[str, str | Path]] = []
    for pdf in sorted(source_root.rglob("*.pdf")):
        rel = pdf.relative_to(source_root)
        if len(rel.parts) < 5:
            continue
        family, current_book_id, edition, variant = rel.parts[:4]
        if current_book_id != book_id or variant not in VARIANT_LABELS:
            continue
        if family not in LANGUAGE_LABELS:
            continue
        records.append(
            {
                "source": pdf,
                "family": family,
                "book_id": current_book_id,
                "edition": edition,
                "variant": variant,
                "language_label": LANGUAGE_LABELS[family],
                "title": clean_title(pdf.name, variant),
            }
        )
    if not records:
        return records
    best = max(FAMILY_PRIORITY.get(str(record["family"]), 0) for record in records)
    records = [record for record in records if FAMILY_PRIORITY.get(str(record["family"]), 0) == best]
    best_edition = max(edition_priority(str(record["family"]), str(record["edition"])) for record in records)
    return [
        record
        for record in records
        if edition_priority(str(record["family"]), str(record["edition"])) == best_edition
    ]


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def target_name(record: dict[str, str | Path], title_counts: Counter[str]) -> str:
    title = str(record["title"])
    label = str(record["language_label"])
    variant_label = VARIANT_LABELS[str(record["variant"])]
    key = f"{title}｜{label}｜{variant_label}"
    stem = key
    if title_counts[key] > 1:
        stem = f"{stem}｜{record['book_id']}"
    return f"{stem}.pdf"


def clean_share(share: Path, patterns: list[str]) -> list[Path]:
    removed: list[Path] = []
    for variant in VARIANT_LABELS:
        variant_dir = share / variant
        if not variant_dir.exists():
            continue
        for pdf in variant_dir.glob("*.pdf"):
            if any(fnmatch.fnmatch(pdf.name, pattern) for pattern in patterns):
                pdf.unlink()
                removed.append(pdf)
    return removed


def write_manifest(path: Path, copied: list[tuple[Path, Path]], removed: list[Path], source_root: Path) -> None:
    lines = [
        "# LinguaLeaf Maximum-Language Sync",
        "",
        f"Generated from `{source_root}`.",
        "",
        f"PDF count: {len(copied)}",
        f"Removed old Share PDFs: {len(removed)}",
        "",
    ]
    for _, dst in copied:
        lines.append(f"- `{dst.name}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--share", type=Path, default=DEFAULT_SHARE)
    parser.add_argument("--clean-share-glob", action="append", default=[])
    args = parser.parse_args()

    records = discover(args.source, args.book_id)
    if not records:
        raise SystemExit(f"No maximum-language PDFs found for {args.book_id}")

    removed = clean_share(args.share, args.clean_share_glob)
    title_counts = Counter(
        f"{record['title']}｜{record['language_label']}｜{VARIANT_LABELS[str(record['variant'])]}"
        for record in records
    )

    copied: list[tuple[Path, Path]] = []
    for record in records:
        src = Path(record["source"])
        name = target_name(record, title_counts)
        family_label = str(record["language_label"])
        book_id = str(record["book_id"])
        variant = str(record["variant"])
        edition = str(record["edition"])

        project_dst = args.project / "final-pdfs" / family_label / book_id / edition / variant / name
        share_dst = args.share / variant / name
        copy_file(src, project_dst)
        copy_file(src, share_dst)
        copied.append((src, project_dst))
        copied.append((src, share_dst))

    write_manifest(args.project / "final-pdfs" / "MANIFEST-max-language.md", copied, removed, args.source)
    write_manifest(args.share / "MANIFEST-max-language.md", copied, removed, args.source)
    print(f"copied={len(copied)}")
    print(f"removed_share={len(removed)}")
    print(f"project_root={args.project / 'final-pdfs'}")
    print(f"share_root={args.share}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
