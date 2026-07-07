#!/usr/bin/env python3
"""Sync final LinguaLeaf PDFs into Nutstore project and share folders."""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path

from nutstore_paths import lingualeaf_project_root, lingualeaf_share_root


DEFAULT_SOURCE = Path("/home/lachlan/ProjectsLFS/ZhJpBook/artifacts/lingualleaf/books")
DEFAULT_PROJECT = lingualeaf_project_root()
DEFAULT_SHARE = lingualeaf_share_root()

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


def pdf_records(source_root: Path) -> list[dict[str, str | Path]]:
    candidates: list[dict[str, str | Path]] = []
    for pdf in sorted(source_root.rglob("*.pdf")):
        rel = pdf.relative_to(source_root)
        if len(rel.parts) < 5:
            continue
        family, book_id, edition, variant = rel.parts[:4]
        if variant not in VARIANT_LABELS:
            continue
        language_label = LANGUAGE_LABELS.get(family, family)
        title = clean_title(pdf.name, variant)
        candidates.append(
            {
                "source": pdf,
                "family": family,
                "book_id": book_id,
                "edition": edition,
                "variant": variant,
                "language_label": language_label,
                "title": title,
            }
        )
    best_family: dict[str, int] = {}
    for record in candidates:
        book_id = str(record["book_id"])
        priority = FAMILY_PRIORITY.get(str(record["family"]), 0)
        best_family[book_id] = max(best_family.get(book_id, 0), priority)
    best_edition: dict[str, int] = {}
    for record in candidates:
        book_id = str(record["book_id"])
        if FAMILY_PRIORITY.get(str(record["family"]), 0) != best_family.get(book_id, 0):
            continue
        priority = edition_priority(str(record["family"]), str(record["edition"]))
        best_edition[book_id] = max(best_edition.get(book_id, 0), priority)
    return [
        record
        for record in candidates
        if FAMILY_PRIORITY.get(str(record["family"]), 0) == best_family.get(str(record["book_id"]), 0)
        and edition_priority(str(record["family"]), str(record["edition"])) == best_edition.get(str(record["book_id"]), 0)
    ]


def target_name(record: dict[str, str | Path], title_counts: Counter[str]) -> str:
    title = str(record["title"])
    language_label = str(record["language_label"])
    variant_label = VARIANT_LABELS[str(record["variant"])]
    stem = f"{title}｜{language_label}｜{variant_label}"
    collision_key = f"{title}｜{language_label}｜{variant_label}"
    if title_counts[collision_key] > 1:
        stem = f"{stem}｜{record['book_id']}"
    return f"{stem}.pdf"


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_manifest(path: Path, copied: list[tuple[Path, Path]], source_root: Path) -> None:
    lines = [
        "# LinguaLeaf Nutstore Sync",
        "",
        f"Generated from `{source_root}`.",
        "",
        f"PDF count: {len(copied)}",
        "",
    ]
    for _, dst in copied:
        lines.append(f"- `{dst.name}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--share", type=Path, default=DEFAULT_SHARE)
    args = parser.parse_args()

    records = pdf_records(args.source)
    title_counts = Counter(
        f"{record['title']}｜{record['language_label']}｜{VARIANT_LABELS[str(record['variant'])]}"
        for record in records
    )

    project_copied: list[tuple[Path, Path]] = []
    share_copied: list[tuple[Path, Path]] = []

    for record in records:
        src = Path(record["source"])
        name = target_name(record, title_counts)
        family_label = str(record["language_label"])
        book_id = str(record["book_id"])
        variant = str(record["variant"])

        project_dst = args.project / "final-pdfs" / family_label / book_id / variant / name
        share_dst = args.share / variant / name

        copy_file(src, project_dst)
        copy_file(src, share_dst)
        project_copied.append((src, project_dst))
        share_copied.append((src, share_dst))

    write_manifest(args.project / "final-pdfs" / "MANIFEST.md", project_copied, args.source)
    write_manifest(args.share / "MANIFEST.md", share_copied, args.source)

    print(f"copied_project={len(project_copied)}")
    print(f"copied_share={len(share_copied)}")
    print(f"project_root={args.project / 'final-pdfs'}")
    print(f"share_root={args.share}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
