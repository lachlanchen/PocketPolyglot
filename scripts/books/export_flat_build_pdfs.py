#!/usr/bin/env python3
"""Export final build PDFs into local and Nutstore browsing folders."""

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
NUTSTORE_LAYOUT = "grouped"
LOCAL_LAYOUT = "flat"
EDITION_DIRS = {
    ("zh-main", "color"): "zh-main-color",
    ("zh-main", "blackwhite"): "zh-main-blackwhite",
    ("jp-main", "color"): "jp-main-color",
    ("jp-main", "blackwhite"): "jp-main-blackwhite",
}


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


def clean_title_filename(title: str) -> str:
    title = title.strip().removesuffix(".pdf")
    title = title.replace("/", "／").replace("\\", "＼")
    return f"{title}.pdf"


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


def output_path_for_item(item: ExportItem, layout: str) -> Path:
    if layout == "flat":
        return Path(item.filename)
    if layout == "grouped":
        edition_dir = EDITION_DIRS[(item.direction, item.variant)]
        return Path(edition_dir) / clean_title_filename(item.title)
    raise ValueError(f"unsupported layout: {layout}")


def resolve_output_paths(items: list[ExportItem], layout: str) -> dict[ExportItem, Path]:
    planned: dict[ExportItem, Path] = {}
    used: set[Path] = set()
    for item in items:
        path = output_path_for_item(item, layout)
        if path not in used:
            planned[item] = path
            used.add(path)
            continue

        stem = path.stem
        suffix = path.suffix
        for number in range(1, 1000):
            suffix_text = f" - {item.book_id}" if number == 1 else f" - {item.book_id}-{number}"
            candidate = path.with_name(f"{stem}{suffix_text}{suffix}")
            if candidate not in used:
                planned[item] = candidate
                used.add(candidate)
                break
        else:
            raise RuntimeError(f"Could not resolve duplicate output path for {path}")
    return planned


def previous_manifest_paths(target_dir: Path) -> list[Path]:
    manifest_path = target_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    paths = []
    for item in manifest.get("items", []):
        output_path = item.get("output_path") or item.get("filename")
        if output_path:
            paths.append(target_dir / output_path)
    return paths


def clean_generated_files(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    candidates = set(previous_manifest_paths(target_dir))
    candidates.update(path for path in target_dir.glob("*__*__*__*.pdf"))
    for edition_dir in EDITION_DIRS.values():
        candidates.update((target_dir / edition_dir).glob("*.pdf"))
    for path in sorted(candidates):
        if path.is_file() and path.suffix == ".pdf":
            path.unlink()
    for name in ("README.md", "manifest.json"):
        path = target_dir / name
        if path.exists():
            path.unlink()
    for edition_dir in EDITION_DIRS.values():
        path = target_dir / edition_dir
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def write_readme(target_dir: Path, items: list[ExportItem], source_root: Path, output_paths: dict[ExportItem, Path], layout: str) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Bilingual Book PDFs",
        "",
        f"Generated at: `{generated_at}`",
        f"Source: `{source_root}`",
        "",
        "This folder is a browsing/export view of final PDFs from `build/`.",
        "",
        "Directions: `zh-main` means Chinese main text with Japanese notes; `jp-main` means Japanese main text with Chinese notes.",
        "Variants: `color` and `blackwhite`.",
        "",
        f"Layout: `{layout}`",
        "",
        f"PDF count: `{len(items)}`",
        "",
        "| Book | Direction | Variant | File |",
        "| --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(f"| `{item.book_id}` | `{item.direction}` | `{item.variant}` | `{output_paths[item]}` |")
    target_dir.joinpath("README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_to(target_dir: Path, items: list[ExportItem], build_dir: Path, *, clean: bool, layout: str) -> None:
    if clean:
        clean_generated_files(target_dir)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
    output_paths = resolve_output_paths(items, layout)
    for item in items:
        output_path = output_paths[item]
        (target_dir / output_path.parent).mkdir(parents=True, exist_ok=True)
        shutil.copy2(build_dir / item.source, target_dir / output_path)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_build_dir": str(build_dir),
        "layout": layout,
        "count": len(items),
        "items": [
            {
                **asdict(item),
                "output_path": str(output_paths[item]),
            }
            for item in items
        ],
    }
    target_dir.joinpath("manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(target_dir, items, build_dir, output_paths, layout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--nutstore-dir", type=Path, default=DEFAULT_NUTSTORE_DIR)
    parser.add_argument("--no-local", action="store_true", help="skip the local build/books export")
    parser.add_argument("--no-nutstore", action="store_true", help="skip the Nutstore export")
    parser.add_argument("--no-clean", action="store_true", help="do not remove old generated PDFs from target folders first")
    parser.add_argument("--local-layout", choices=("flat", "grouped"), default=LOCAL_LAYOUT)
    parser.add_argument("--nutstore-layout", choices=("flat", "grouped"), default=NUTSTORE_LAYOUT)
    parser.add_argument("--dry-run", action="store_true", help="print planned filenames without copying")
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    items = discover_pdfs(build_dir)
    if not items:
        raise SystemExit(f"No final PDFs found under {build_dir}")

    if args.dry_run:
        dry_run_targets = []
        if not args.no_local:
            dry_run_targets.append(("local", args.local_layout))
        if not args.no_nutstore:
            dry_run_targets.append(("nutstore", args.nutstore_layout))
        for name, layout in dry_run_targets:
            print(f"{name}: layout={layout}")
            output_paths = resolve_output_paths(items, layout)
            for item in items:
                print(f"{item.source} -> {output_paths[item]}")
        print(f"count={len(items)}")
        return 0

    clean = not args.no_clean
    if not args.no_local:
        export_to(args.local_dir.expanduser().resolve(), items, build_dir, clean=clean, layout=args.local_layout)
        print(f"exported {len(items)} PDFs: {args.local_dir}")
    if not args.no_nutstore:
        export_to(args.nutstore_dir.expanduser().resolve(), items, build_dir, clean=clean, layout=args.nutstore_layout)
        print(f"exported {len(items)} PDFs: {args.nutstore_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
