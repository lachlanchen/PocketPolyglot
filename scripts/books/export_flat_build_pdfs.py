#!/usr/bin/env python3
"""Export final build PDFs into a flat, consistently named book folder."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_DIR = ROOT / "build" / "books"
DEFAULT_NUTSTORE_DIR = Path.home() / "Nutstore Files" / "Projects" / "ZhJpBook" / "books"

FINAL_DIRECTIONS = {"zh-main", "jp-main"}
FINAL_VARIANTS = {"color", "blackwhite"}
SKIP_PARTS = {"writer-preview", "writer-preview-all"}


@dataclass(frozen=True)
class ExportItem:
    book_id: str
    direction: str
    variant: str
    title: str
    source: str
    filename: str
    size_bytes: int


def normalized_filename(book_id: str, direction: str, variant: str, title: str) -> str:
    title = title.strip().removesuffix(".pdf")
    title = title.replace("/", "／").replace("\\", "＼")
    return f"{book_id}__{direction}__{variant}__{title}.pdf"


def discover_pdfs(build_dir: Path) -> list[ExportItem]:
    items: list[ExportItem] = []
    for pdf in sorted(build_dir.glob("*/*/*/*.pdf")):
        rel = pdf.relative_to(build_dir)
        parts = rel.parts
        if any(part in SKIP_PARTS for part in parts):
            continue
        if pdf.name == "book.pdf":
            continue
        if len(parts) != 4:
            continue
        book_id, direction, variant, filename = parts
        if direction not in FINAL_DIRECTIONS or variant not in FINAL_VARIANTS:
            continue
        title = Path(filename).stem
        items.append(
            ExportItem(
                book_id=book_id,
                direction=direction,
                variant=variant,
                title=title,
                source=str(rel),
                filename=normalized_filename(book_id, direction, variant, title),
                size_bytes=pdf.stat().st_size,
            )
        )
    return sorted(items, key=lambda item: (item.book_id, item.direction, item.variant, item.title))


def clean_generated_files(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in target_dir.iterdir():
        if path.is_file() and (path.suffix == ".pdf" or path.name in {"README.md", "manifest.json"}):
            path.unlink()


def write_readme(target_dir: Path, items: list[ExportItem], source_root: Path) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Bilingual Book PDFs",
        "",
        f"Generated at: `{generated_at}`",
        f"Source: `{source_root}`",
        "",
        "This folder is a flat browsing/export view of final PDFs from `build/`.",
        "",
        "Filename pattern:",
        "",
        "```text",
        "book-slug__direction__variant__title.pdf",
        "```",
        "",
        "Directions: `zh-main` means Chinese main text with Japanese notes; `jp-main` means Japanese main text with Chinese notes.",
        "Variants: `color` and `blackwhite`.",
        "",
        f"PDF count: `{len(items)}`",
        "",
        "| Book | Direction | Variant | File |",
        "| --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(f"| `{item.book_id}` | `{item.direction}` | `{item.variant}` | `{item.filename}` |")
    target_dir.joinpath("README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_to(target_dir: Path, items: list[ExportItem], build_dir: Path, *, clean: bool) -> None:
    if clean:
        clean_generated_files(target_dir)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        shutil.copy2(build_dir / item.source, target_dir / item.filename)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_build_dir": str(build_dir),
        "count": len(items),
        "items": [asdict(item) for item in items],
    }
    target_dir.joinpath("manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(target_dir, items, build_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--nutstore-dir", type=Path, default=DEFAULT_NUTSTORE_DIR)
    parser.add_argument("--no-local", action="store_true", help="skip the local build/books export")
    parser.add_argument("--no-nutstore", action="store_true", help="skip the Nutstore export")
    parser.add_argument("--no-clean", action="store_true", help="do not remove old generated PDFs from target folders first")
    parser.add_argument("--dry-run", action="store_true", help="print planned filenames without copying")
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    items = discover_pdfs(build_dir)
    if not items:
        raise SystemExit(f"No final PDFs found under {build_dir}")

    if args.dry_run:
        for item in items:
            print(f"{item.source} -> {item.filename}")
        print(f"count={len(items)}")
        return 0

    clean = not args.no_clean
    targets: list[Path] = []
    if not args.no_local:
        targets.append(args.local_dir)
    if not args.no_nutstore:
        targets.append(args.nutstore_dir)
    for target in targets:
        export_to(target.expanduser().resolve(), items, build_dir, clean=clean)
        print(f"exported {len(items)} PDFs: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
