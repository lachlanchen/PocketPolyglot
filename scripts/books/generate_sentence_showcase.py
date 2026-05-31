#!/usr/bin/env python3
"""Render and crop a single high-resolution JP-main sentence block for README display."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("build/books/kokoro__jp-main__color__こころ（心）.pdf"),
        help="JP-main color PDF to render.",
    )
    parser.add_argument("--page", type=int, default=20, help="True PDF page number.")
    parser.add_argument("--dpi", type=int, default=600, help="pdftoppm render DPI.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png"),
        help="Output PNG path.",
    )
    parser.add_argument(
        "--crop",
        default="0.055,0.045,0.955,0.152",
        help="Crop box as left,top,right,bottom fractions of the rendered page.",
    )
    return parser.parse_args()


def render_page(pdf: Path, page: int, dpi: int, target: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pocketpolyglot-sentence-") as tmp:
        prefix = Path(tmp) / target.stem
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
        shutil.move(str(prefix.with_suffix(".png")), target)


def parse_crop(crop: str, width: int, height: int) -> tuple[int, int, int, int]:
    parts = [float(part.strip()) for part in crop.split(",")]
    if len(parts) != 4:
        raise SystemExit("--crop must contain four comma-separated fractions")
    left, top, right, bottom = parts
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise SystemExit("--crop fractions must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
    return (
        round(left * width),
        round(top * height),
        round(right * width),
        round(bottom * height),
    )


def add_frame(image: Image.Image) -> Image.Image:
    pad_x = 64
    pad_y = 44
    radius = 28
    framed = Image.new("RGB", (image.width + pad_x * 2, image.height + pad_y * 2), "#f8fafc")
    draw = ImageDraw.Draw(framed)
    box = (22, 22, framed.width - 22, framed.height - 22)
    draw.rounded_rectangle(box, radius=radius, fill="#ffffff", outline="#cbd5e1", width=3)
    framed.paste(image.convert("RGB"), (pad_x, pad_y))
    return framed


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pocketpolyglot-sentence-page-") as tmp:
        rendered = Path(tmp) / "page.png"
        render_page(args.pdf, args.page, args.dpi, rendered)
        page = Image.open(rendered).convert("RGB")
        crop_box = parse_crop(args.crop, page.width, page.height)
        crop = page.crop(crop_box)
        add_frame(crop).save(args.output, optimize=True)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
