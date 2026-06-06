#!/usr/bin/env python3
"""Compose branded Sanxingdui pocket-book covers from generated backgrounds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "books" / "sanxingdui" / "book-plan.json"
WIDTH = 1536
HEIGHT = round(WIDTH * 148 / 105)
SERIF_REGULAR = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SANS_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def normalize_title(title: str) -> str:
    title = title.replace("_", "：").replace(".金沙", "、金沙")
    title = title.replace("： ", "：").strip()
    return title


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


def text_width(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    return bbox[2] - bbox[0]


def wrap_cjk(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if current and text_width(draw, trial, font_obj) > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    lines = rebalance_cjk_breaks(draw, lines, font_obj, max_width)
    return lines


def rebalance_cjk_breaks(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font_obj: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    openers = set("（《〈「『【〔")
    closers = set("），。、：；！？》〉」』】〕")
    changed = True
    while changed:
        changed = False
        for index in range(len(lines) - 1):
            if len(lines[index]) > 1 and lines[index][-1] in openers:
                lines[index + 1] = lines[index][-1] + lines[index + 1]
                lines[index] = lines[index][:-1]
                changed = True
        for index in range(1, len(lines)):
            if lines[index] and lines[index][0] in closers:
                trial = lines[index - 1] + lines[index][0]
                if text_width(draw, trial, font_obj) <= max_width:
                    lines[index - 1] = trial
                    lines[index] = lines[index][1:]
                    changed = True
        lines = [line for line in lines if line]
    return lines


def draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    font_obj: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    x = center[0] - (bbox[2] - bbox[0]) / 2
    y = center[1] - (bbox[3] - bbox[1]) / 2
    draw.text((x, y), text, font=font_obj, fill=fill)


def compose_one(slug: str, title: str, background: Path, output: Path) -> None:
    image = fit_cover(Image.open(background))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Quiet the generated background enough for long Chinese titles to read.
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(10, 8, 6, 70))
    panel_left = int(WIDTH * 0.075)
    panel_right = int(WIDTH * 0.925)
    panel_top = int(HEIGHT * 0.105)
    panel_bottom = int(HEIGHT * 0.885)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=28,
        fill=(245, 234, 210, 190),
        outline=(64, 43, 30, 220),
        width=5,
    )
    inset = 34
    draw.rounded_rectangle(
        (panel_left + inset, panel_top + inset, panel_right - inset, panel_bottom - inset),
        radius=14,
        outline=(64, 43, 30, 105),
        width=2,
    )

    title_font = font(SERIF_BOLD, 94, index=2)
    subtitle_font = font(SERIF_REGULAR, 43, index=2)
    label_font = font(SANS_REGULAR, 32, index=2)
    latin_font = font(SERIF_REGULAR, 28, index=2)
    seal_font = font(SERIF_BOLD, 50, index=2)

    title_text = normalize_title(title)
    lines = wrap_cjk(draw, title_text, title_font, int(WIDTH * 0.72))
    while len(lines) > 4:
        title_font = font(SERIF_BOLD, max(66, title_font.size - 8), index=2)
        lines = wrap_cjk(draw, title_text, title_font, int(WIDTH * 0.74))

    ink = (28, 21, 16, 255)
    muted = (72, 53, 40, 242)
    seal = (142, 42, 28, 242)
    title_line_height = int(title_font.size * 1.28)
    total_title_height = title_line_height * len(lines)
    y = int(HEIGHT * 0.285) - total_title_height // 2
    for line in lines:
        draw_centered(draw, line, (WIDTH // 2, y + title_line_height // 2), title_font, ink)
        y += title_line_height

    draw_centered(draw, "润色 TeX 图文口袋版", (WIDTH // 2, int(HEIGHT * 0.545)), subtitle_font, muted)
    draw_centered(draw, "Sanxingdui Archaeology Reader", (WIDTH // 2, int(HEIGHT * 0.595)), latin_font, muted)
    draw_centered(draw, "OCR 校读・图版保留・目录重排", (WIDTH // 2, int(HEIGHT * 0.655)), label_font, muted)

    draw_centered(draw, "AgInTiFlow curated", (WIDTH // 2, int(HEIGHT * 0.790)), latin_font, muted)
    draw_centered(draw, "https://flow.lazying.art", (WIDTH // 2, int(HEIGHT * 0.822)), latin_font, muted)
    draw_centered(draw, "powered by LazyingArt", (WIDTH // 2, int(HEIGHT * 0.854)), latin_font, muted)

    seal_size = int(WIDTH * 0.085)
    seal_x = int(WIDTH * 0.78)
    seal_y = int(HEIGHT * 0.70)
    draw.rounded_rectangle((seal_x, seal_y, seal_x + seal_size, seal_y + seal_size), radius=8, outline=seal, width=5)
    draw_centered(draw, "流", (seal_x + seal_size // 2, seal_y + seal_size // 2), seal_font, seal)

    composed = Image.alpha_composite(image, overlay)
    output.parent.mkdir(parents=True, exist_ok=True)
    composed.convert("RGB").save(output, quality=95)
    print(output.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--cover-root", type=Path, default=ROOT / "assets" / "covers" / "sanxingdui")
    parser.add_argument("--slug", action="append", help="only compose selected slug")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    selected = set(args.slug or [])
    for book in plan["books"]:
        slug = book["slug"]
        if selected and slug not in selected:
            continue
        cover_dir = args.cover_root / slug
        compose_one(slug, book["title"], cover_dir / "background.png", cover_dir / "cover.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
