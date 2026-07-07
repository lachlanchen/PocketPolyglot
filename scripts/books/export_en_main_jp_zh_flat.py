#!/usr/bin/env python3
"""Export English-main Japanese/Chinese-note PDFs to Nutstore."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from nutstore_paths import lingualeaf_project_root


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = lingualeaf_project_root() / "en-main-jp-zh"


def clean_name(text: str) -> str:
    return text.strip().replace("/", "／").replace("\\", "＼")


def discover(build_dir: Path) -> list[tuple[str, str, Path]]:
    items: list[tuple[str, str, Path]] = []
    for pdf in sorted(build_dir.glob("*/en-main-jp-zh/*/*.pdf")):
        if pdf.name == "book.pdf":
            continue
        parts = pdf.relative_to(build_dir).parts
        if len(parts) != 4:
            continue
        book_id, _, variant, _ = parts
        if variant not in {"color", "blackwhite"}:
            continue
        items.append((book_id, variant, pdf))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Keep the older single-folder export layout with variant suffixes.",
    )
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    target_dir = args.target_dir.expanduser().resolve()
    items = discover(build_dir)
    if not items:
        raise SystemExit(f"No English-main JP/ZH note PDFs found under {build_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_clean:
        for path in target_dir.glob("*.pdf"):
            path.unlink()
        for variant in ("color", "blackwhite"):
            variant_dir = target_dir / variant
            if variant_dir.exists():
                for path in variant_dir.glob("*.pdf"):
                    path.unlink()
        for name in ("README.md", "manifest.json"):
            path = target_dir / name
            if path.exists():
                path.unlink()

    manifest_items = []
    used: set[str] = set()
    for book_id, variant, pdf in items:
        variant_dir = target_dir if args.flat else target_dir / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        name = f"{clean_name(pdf.stem)}.pdf"
        if args.flat:
            suffix = "color" if variant == "color" else "blackwhite"
            name = f"{clean_name(pdf.stem)} [{suffix}].pdf"
        if name in used:
            suffix = "color" if variant == "color" else "blackwhite"
            name = f"{clean_name(pdf.stem)} [{book_id} {suffix}].pdf"
        used.add(name)
        output = variant_dir / name
        shutil.copy2(pdf, output)
        rel_output = output.relative_to(target_dir)
        manifest_items.append(
            {
                "book_id": book_id,
                "variant": variant,
                "source": str(pdf.relative_to(build_dir)),
                "output": str(rel_output),
                "size_bytes": output.stat().st_size,
            }
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_build_dir": str(build_dir),
        "count": len(manifest_items),
        "items": manifest_items,
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# English Main with Japanese and Chinese Notes",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        f"PDF count: `{len(manifest_items)}`",
        "",
        "Each PDF uses English as the main reading line, with indented Japanese and Chinese note lines under each aligned unit.",
        "",
        "Files are separated by variant:",
        "",
        "- `color/` for grammar-colored editions",
        "- `blackwhite/` for monochrome editions",
        "",
        "| Book | Variant | File |",
        "| --- | --- | --- |",
    ]
    for item in manifest_items:
        lines.append(f"| `{item['book_id']}` | `{item['variant']}` | `{item['output']}` |")
    (target_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"exported {len(manifest_items)} PDFs: {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
