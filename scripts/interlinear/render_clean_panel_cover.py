#!/usr/bin/env python3
"""Render a clean, single-title panel over a generated book cover image."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SERIF_CJK_BOLD = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc")
SERIF_CJK_REGULAR = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc")
SERIF_LATIN = Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def parse_box(value: str, width: int, height: int) -> tuple[int, int, int, int]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--panel-box must contain four comma-separated ratios")
    x1, y1, x2, y2 = parts
    return (round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height))


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
) -> None:
    w, h = text_size(draw, text, font)
    draw.text((xy[0] - w / 2, xy[1] - h / 2), text, font=font, fill=fill)


def draw_vertical(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    top_y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    line_gap: int,
) -> None:
    y = top_y
    for char in text:
        w, h = text_size(draw, char, font)
        draw.text((center_x - w / 2, y), char, font=font, fill=fill)
        y += h + line_gap


def vertical_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, line_gap: int) -> int:
    height = 0
    for index, char in enumerate(text):
        _, h = text_size(draw, char, font)
        height += h
        if index < len(text) - 1:
            height += line_gap
    return height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="existing cover image")
    parser.add_argument("--output", required=True, help="cleaned cover image")
    parser.add_argument("--title", required=True, help="main vertical title")
    parser.add_argument("--author", default="", help="author line")
    parser.add_argument("--subtitle", default="", help="subtitle line")
    parser.add_argument("--curated-by", default="AgInTiFlow curated")
    parser.add_argument("--url", default="https://flow.lazying.art")
    parser.add_argument("--powered-by", default="powered by LazyingArt")
    parser.add_argument(
        "--panel-box",
        default="0.285,0.075,0.690,0.955",
        help="panel box ratios: x1,y1,x2,y2",
    )
    args = parser.parse_args()

    source = ROOT / args.input
    output = ROOT / args.output
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    panel = parse_box(args.panel_box, width, height)
    x1, y1, x2, y2 = panel
    panel_w = x2 - x1
    panel_h = y2 - y1

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    radius = max(18, width // 70)
    fill = (242, 234, 205, 255)
    outline = (70, 61, 45, 230)
    draw.rounded_rectangle(panel, radius=radius, fill=fill, outline=outline, width=max(3, width // 420))
    inset = max(16, width // 90)
    draw.rounded_rectangle(
        (x1 + inset, y1 + inset, x2 - inset, y2 - inset),
        radius=max(10, radius - inset // 2),
        outline=(108, 96, 70, 130),
        width=max(1, width // 760),
    )

    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    title_size = max(58, min(104, round(panel_h * 0.068)))
    title_font = load_font(SERIF_CJK_BOLD, title_size)
    title_gap = max(2, round(title_size * 0.06))
    while vertical_height(draw, args.title, title_font, title_gap) > panel_h * 0.43 and title_size > 48:
        title_size -= 4
        title_font = load_font(SERIF_CJK_BOLD, title_size)
        title_gap = max(1, round(title_size * 0.05))
    draw_vertical(
        draw,
        x1 + panel_w * 0.50,
        y1 + panel_h * 0.15,
        args.title,
        title_font,
        fill=(24, 22, 18, 255),
        line_gap=title_gap,
    )

    footer_font = load_font(SERIF_LATIN, max(23, round(width * 0.021)))
    meta_font = load_font(SERIF_CJK_REGULAR, max(30, round(width * 0.029)))
    subtitle_font = load_font(SERIF_CJK_REGULAR, max(34, round(width * 0.032)))

    if args.author:
        draw_centered(
            draw,
            (x1 + panel_w / 2, y1 + panel_h * 0.70),
            args.author,
            meta_font,
            fill=(80, 67, 48, 255),
        )
    if args.subtitle:
        draw_centered(
            draw,
            (x1 + panel_w / 2, y1 + panel_h * 0.765),
            args.subtitle,
            subtitle_font,
            fill=(78, 66, 48, 255),
        )

    footer_lines = [args.curated_by, args.url, args.powered_by]
    footer_y = y1 + panel_h * 0.855
    for line in footer_lines:
        draw_centered(
            draw,
            (x1 + panel_w / 2, footer_y),
            line,
            footer_font,
            fill=(80, 67, 48, 235),
        )
        footer_y += footer_font.size * 1.45

    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, quality=95)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
