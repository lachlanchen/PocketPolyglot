#!/usr/bin/env python3
"""Render one book page across four edition variants and compose a comparison row."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


EDITION_ORDER = [
    ("zh-main", "color", "ZH main · color"),
    ("zh-main", "blackwhite", "ZH main · black/white"),
    ("jp-main", "color", "JP main · color"),
    ("jp-main", "blackwhite", "JP main · black/white"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", default="kokoro", help="Book ID from build/books/manifest.json.")
    parser.add_argument("--page", type=int, default=20, help="True PDF page number to render.")
    parser.add_argument("--dpi", type=int, default=300, help="pdftoppm render DPI.")
    parser.add_argument(
        "--panel-width",
        type=int,
        default=760,
        help="Width of each page panel in the composed comparison image.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/books/manifest.json"),
        help="Flat PDF export manifest.",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("build/books"),
        help="Directory containing flat PDF exports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/edition-comparisons"),
        help="Directory for comparison assets.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not isinstance(items, list):
        raise SystemExit(f"{path} does not contain an items list")
    return items


def find_edition(
    items: list[dict[str, object]], book_id: str, direction: str, variant: str
) -> dict[str, object]:
    matches = [
        item
        for item in items
        if item.get("book_id") == book_id
        and item.get("direction") == direction
        and item.get("variant") == variant
    ]
    if not matches:
        raise SystemExit(f"missing {book_id} {direction} {variant} in manifest")
    return matches[0]


def render_page(pdf: Path, page: int, dpi: int, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pocketpolyglot-page-") as tmp:
        prefix = Path(tmp) / output.stem
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-singlefile",
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                str(dpi),
                str(pdf),
                str(prefix),
            ],
            check=True,
        )
        shutil.move(str(prefix.with_suffix(".png")), output)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def resize_panel(image: Image.Image, panel_width: int) -> Image.Image:
    scale = panel_width / image.width
    return image.resize((panel_width, round(image.height * scale)), Image.Resampling.LANCZOS)


def compose_row(panels: list[tuple[str, Path]], output: Path, panel_width: int) -> None:
    label_font = font(26)
    small_font = font(18)
    gap = 28
    margin = 28
    label_height = 54
    footer_height = 36
    rendered: list[tuple[str, Image.Image]] = []

    for label, path in panels:
        rendered.append((label, resize_panel(Image.open(path).convert("RGB"), panel_width)))

    panel_height = max(image.height for _, image in rendered)
    width = margin * 2 + panel_width * len(rendered) + gap * (len(rendered) - 1)
    height = margin * 2 + label_height + panel_height + footer_height
    canvas = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(canvas)

    x = margin
    for label, image in rendered:
        text_width = draw.textlength(label, font=label_font)
        draw.text((x + (panel_width - text_width) / 2, margin), label, fill="#0f172a", font=label_font)
        y = margin + label_height
        draw.rounded_rectangle(
            (x - 3, y - 3, x + panel_width + 3, y + panel_height + 3),
            radius=12,
            fill="#ffffff",
            outline="#cbd5e1",
            width=2,
        )
        canvas.paste(image, (x, y))
        x += panel_width + gap

    footer = "Same Kokoro interior page rendered as four PocketPolyglot editions; other language pairs can use the same model."
    footer_width = draw.textlength(footer, font=small_font)
    draw.text(
        ((width - footer_width) / 2, height - margin - 8),
        footer,
        fill="#475569",
        font=small_font,
    )
    canvas.save(output, optimize=True)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    items = load_manifest(args.manifest)
    panels: list[tuple[str, Path]] = []
    manifest_items = []

    for direction, variant, label in EDITION_ORDER:
        item = find_edition(items, args.book_id, direction, variant)
        pdf = args.pdf_dir / str(item["filename"])
        if not pdf.exists():
            raise SystemExit(f"missing PDF: {pdf}")
        image_path = args.output_dir / f"{args.book_id}-{direction}-{variant}-page-{args.page}.png"
        render_page(pdf, args.page, args.dpi, image_path)
        panels.append((label, image_path))
        manifest_items.append(
            {
                "book_id": args.book_id,
                "direction": direction,
                "variant": variant,
                "label": label,
                "page": args.page,
                "source_pdf": item["filename"],
                "image": image_path.name,
            }
        )

    comparison = args.output_dir / f"{args.book_id}-four-editions-page-{args.page}.png"
    compose_row(panels, comparison, args.panel_width)
    (args.output_dir / f"{args.book_id}-four-editions-page-{args.page}.json").write_text(
        json.dumps({"comparison": comparison.name, "items": manifest_items}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {comparison}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
