#!/usr/bin/env python3
"""Render a nonfigurative geometric cover for the Quran learner edition."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
AMIRI = Path("/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Regular.ttf")
CJK = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc")
LATIN = Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")


def star_points(cx: float, cy: float, r1: float, r2: float, n: int = 8) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(n * 2):
        angle = -math.pi / 2 + i * math.pi / n
        radius = r1 if i % 2 == 0 else r2
        pts.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return pts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="assets/covers/quran/cover.png")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=2256)
    args = parser.parse_args()

    out = ROOT / args.output
    w, h = args.width, args.height
    image = Image.new("RGB", (w, h), (12, 45, 50))
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(h):
        t = y / h
        color = (
            round(10 + 22 * t),
            round(42 + 20 * (1 - t)),
            round(48 + 52 * t),
            255,
        )
        draw.line((0, y, w, y), fill=color)

    gold = (214, 177, 91, 120)
    pale = (241, 228, 175, 70)
    step = 180
    for y in range(-step, h + step, step):
        for x in range(-step, w + step, step):
            offset = (y // step) % 2 * step / 2
            cx = x + offset
            pts = star_points(cx, y, 70, 28)
            draw.polygon(pts, outline=gold, fill=(0, 0, 0, 0))
            draw.ellipse((cx - 18, y - 18, cx + 18, y + 18), outline=pale, width=2)

    border = 82
    draw.rounded_rectangle((border, border, w - border, h - border), radius=28, outline=(235, 205, 119, 190), width=8)
    draw.rounded_rectangle(
        (border + 34, border + 34, w - border - 34, h - border - 34),
        radius=18,
        outline=(235, 205, 119, 105),
        width=3,
    )
    panel = (round(w * 0.16), round(h * 0.19), round(w * 0.84), round(h * 0.81))
    draw.rounded_rectangle(panel, radius=34, fill=(248, 238, 202, 118), outline=(235, 205, 119, 170), width=4)

    ar_font = ImageFont.truetype(str(AMIRI), size=118)
    en_font = ImageFont.truetype(str(LATIN), size=54)
    cjk_font = ImageFont.truetype(str(CJK), size=48)
    small_font = ImageFont.truetype(str(LATIN), size=30)
    cx = w / 2
    draw.text((cx, h * 0.34), "القرآن الكريم", font=ar_font, fill=(22, 37, 37, 245), anchor="mm", direction="rtl")
    draw.text((cx, h * 0.435), "The Quran", font=en_font, fill=(39, 49, 43, 235), anchor="mm")
    draw.text((cx, h * 0.492), "クルアーン  ·  古蘭經", font=cjk_font, fill=(44, 52, 46, 230), anchor="mm")
    draw.line((w * 0.32, h * 0.55, w * 0.68, h * 0.55), fill=(100, 82, 39, 150), width=3)
    draw.text((cx, h * 0.635), "Arabic · English · 日本語 · 中文", font=cjk_font, fill=(50, 59, 51, 225), anchor="mm")
    draw.text((cx, h * 0.715), "AgInTiFlow curated", font=small_font, fill=(50, 59, 51, 210), anchor="mm")
    draw.text((cx, h * 0.755), "https://flow.lazying.art", font=small_font, fill=(50, 59, 51, 210), anchor="mm")
    draw.text((cx, h * 0.795), "powered by LazyingArt", font=small_font, fill=(50, 59, 51, 210), anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, quality=94, optimize=True)
    print(out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
