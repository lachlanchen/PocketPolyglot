#!/usr/bin/env python3
"""Compose the Sishu Jizhu cover from an AgInTi-generated background."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
COVER_DIR = ROOT / "assets" / "covers" / "sishu-jizhu-aginti"
BACKGROUND = COVER_DIR / "background.png"
OUTPUT = COVER_DIR / "cover.png"

SERIF_REGULAR = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"


def font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def draw_vertical(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font_obj: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    gap: int,
) -> None:
    cursor = y
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font_obj)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text((x - w / 2, cursor), ch, font=font_obj, fill=fill)
        cursor += h + gap


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


def main() -> None:
    image = Image.open(BACKGROUND).convert("RGBA")
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    ink = (32, 24, 18, 255)
    muted = (76, 57, 42, 235)
    seal = (132, 45, 29, 235)
    panel_fill = (246, 232, 200, 86)
    panel_line = (44, 34, 27, 190)

    panel_left = int(width * 0.27)
    panel_right = int(width * 0.73)
    panel_top = int(height * 0.07)
    panel_bottom = int(height * 0.92)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=14,
        fill=panel_fill,
        outline=panel_line,
        width=4,
    )
    inset = 24
    draw.rounded_rectangle(
        (panel_left + inset, panel_top + inset, panel_right - inset, panel_bottom - inset),
        radius=8,
        outline=(44, 34, 27, 105),
        width=2,
    )

    title_font = font(SERIF_BOLD, int(height * 0.070), index=2)
    side_font = font(SERIF_REGULAR, int(height * 0.024), index=2)
    small_font = font(SERIF_REGULAR, int(height * 0.025), index=2)
    jp_font = font(SERIF_REGULAR, int(height * 0.020), index=0)
    latin_font = font(SERIF_REGULAR, int(height * 0.017), index=2)

    draw_vertical(
        draw,
        "四書章句集註",
        width // 2,
        int(height * 0.135),
        title_font,
        fill=ink,
        gap=int(height * 0.010),
    )
    draw_vertical(
        draw,
        "中文主文・日本語注",
        int(width * 0.35),
        int(height * 0.20),
        side_font,
        fill=muted,
        gap=4,
    )
    draw_vertical(
        draw,
        "日本語主文・中文注",
        int(width * 0.65),
        int(height * 0.20),
        side_font,
        fill=muted,
        gap=4,
    )

    draw_centered(draw, "朱熹（しゅき） 集註", (width // 2, int(height * 0.715)), jp_font, muted)
    draw_centered(draw, "AgInTiFlow curated", (width // 2, int(height * 0.805)), latin_font, muted)
    draw_centered(draw, "https://flow.lazying.art", (width // 2, int(height * 0.835)), latin_font, muted)
    draw_centered(draw, "powered by LazyingArt", (width // 2, int(height * 0.865)), latin_font, muted)

    composed = Image.alpha_composite(image, overlay)
    composed.save(OUTPUT)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
