#!/usr/bin/env python3
"""Compose a pocket-book cover from a generated textless background."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
WIDTH = 1536
HEIGHT = round(WIDTH * 148 / 105)
SERIF_REGULAR = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"


def font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def fit_cover(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    src_w, src_h = image.size
    src_ratio = src_w / src_h
    target_ratio = WIDTH / HEIGHT
    if src_ratio > target_ratio:
        new_w = round(src_h * target_ratio)
        left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = round(src_w / target_ratio)
        top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font_obj: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    x = xy[0] - (bbox[2] - bbox[0]) / 2
    y = xy[1] - (bbox[3] - bbox[1]) / 2
    draw.text((x, y), text, font=font_obj, fill=fill)


def draw_vertical(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font_obj: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    gap: int,
    max_bottom: int,
) -> None:
    chars = list(text)
    heights = []
    for ch in chars:
        bbox = draw.textbbox((0, 0), ch, font=font_obj)
        heights.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
    total = sum(h for _, h in heights) + gap * max(0, len(chars) - 1)
    if y + total > max_bottom:
        y = max(int(HEIGHT * 0.095), max_bottom - total)
    cursor = y
    for ch, (w, h) in zip(chars, heights):
        draw.text((x - w / 2, cursor), ch, font=font_obj, fill=fill)
        cursor += h + gap


def load_plan(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--book-id", default="")
    args = parser.parse_args()

    plan = load_plan(args.plan)
    title_ja = plan.get("book_title_ja") or plan.get("book_title_zh") or args.book_id
    title_zh = plan.get("book_title_zh") or title_ja
    author = plan.get("author") or ""
    author_reading = plan.get("author_reading_ja") or plan.get("author_reading_zh") or ""

    image = fit_cover(Image.open(args.background))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    panel_left = int(WIDTH * 0.29)
    panel_right = int(WIDTH * 0.71)
    panel_top = int(HEIGHT * 0.065)
    panel_bottom = int(HEIGHT * 0.93)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=18,
        fill=(246, 235, 210, 172),
        outline=(42, 31, 24, 210),
        width=5,
    )
    inset = 28
    draw.rounded_rectangle(
        (panel_left + inset, panel_top + inset, panel_right - inset, panel_bottom - inset),
        radius=8,
        outline=(42, 31, 24, 115),
        width=2,
    )

    title_font = font(SERIF_BOLD, int(HEIGHT * 0.061), index=0)
    side_font = font(SERIF_REGULAR, int(HEIGHT * 0.024), index=2)
    small_font = font(SERIF_REGULAR, int(HEIGHT * 0.020), index=0)
    latin_font = font(SERIF_REGULAR, int(HEIGHT * 0.015), index=2)
    seal_font = font(SERIF_BOLD, int(HEIGHT * 0.020), index=2)

    ink = (28, 22, 17, 255)
    muted = (70, 54, 43, 238)
    seal = (150, 42, 30, 238)

    draw_vertical(
        draw,
        title_ja,
        WIDTH // 2,
        int(HEIGHT * 0.13),
        title_font,
        fill=ink,
        gap=max(3, int(HEIGHT * 0.006)),
        max_bottom=int(HEIGHT * 0.67),
    )
    if title_zh != title_ja:
        draw_vertical(
            draw,
            title_zh,
            int(WIDTH * 0.36),
            int(HEIGHT * 0.20),
            side_font,
            fill=muted,
            gap=5,
            max_bottom=int(HEIGHT * 0.66),
        )

    author_line = author
    if author_reading:
        author_line = f"{author}（{author_reading}）"
    draw_centered(draw, author_line, (WIDTH // 2, int(HEIGHT * 0.715)), small_font, muted)
    draw_centered(draw, "中文・日本語 対照注解", (WIDTH // 2, int(HEIGHT * 0.765)), side_font, muted)
    draw_centered(draw, "AgInTiFlow curated", (WIDTH // 2, int(HEIGHT * 0.830)), latin_font, muted)
    draw_centered(draw, "https://flow.lazying.art", (WIDTH // 2, int(HEIGHT * 0.858)), latin_font, muted)
    draw_centered(draw, "powered by LazyingArt", (WIDTH // 2, int(HEIGHT * 0.886)), latin_font, muted)

    seal_size = int(WIDTH * 0.075)
    seal_x = int(WIDTH * 0.61)
    seal_y = int(HEIGHT * 0.70)
    draw.rounded_rectangle(
        (seal_x, seal_y, seal_x + seal_size, seal_y + seal_size),
        radius=7,
        outline=seal,
        width=4,
    )
    draw_centered(draw, "流", (seal_x + seal_size // 2, seal_y + seal_size // 2), seal_font, seal)

    composed = Image.alpha_composite(image, overlay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    composed.convert("RGB").save(args.output, quality=94)
    print(args.output.resolve().relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
