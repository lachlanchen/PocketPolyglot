#!/usr/bin/env python3
"""Compose a clean A6 cover from textless art and queue metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
WIDTH = 1536
HEIGHT = round(WIDTH * 148 / 105)
SERIF = "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"
INK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
HALO = (0, 0, 0, 155)


def fit_cover(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    source_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT
    if source_ratio > target_ratio:
        width = round(image.height * target_ratio)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    else:
        height = round(image.width / target_ratio)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def wrapped_lines(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), candidate, font=font_obj)
        if current and box[2] - box[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_lines(draw: ImageDraw.ImageDraw, text: str, size: int, width: int, max_lines: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    while size >= 38:
        candidate = font(SERIF_BOLD, size)
        lines = wrapped_lines(draw, text, candidate, width)
        if len(lines) <= max_lines:
            return candidate, lines
        size -= 2
    candidate = font(SERIF_BOLD, size)
    return candidate, wrapped_lines(draw, text, candidate, width)


def fit_title_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: int,
    width: int,
    max_lines: int,
    max_height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int, list[int]]:
    """Fit title typography inside a reserved box above the author line."""

    while size >= 38:
        candidate = font(SERIF_BOLD, size)
        lines = wrapped_lines(draw, text, candidate, width)
        heights = [
            draw.textbbox((0, 0), line, font=candidate)[3]
            - draw.textbbox((0, 0), line, font=candidate)[1]
            for line in lines
        ]
        line_gap = int(candidate.size * 0.28)
        total_height = sum(heights) + line_gap * max(0, len(lines) - 1)
        if len(lines) <= max_lines and total_height <= max_height:
            return candidate, lines, line_gap, heights
        size -= 2
    candidate = font(SERIF_BOLD, size)
    lines = wrapped_lines(draw, text, candidate, width)
    heights = [
        draw.textbbox((0, 0), line, font=candidate)[3]
        - draw.textbbox((0, 0), line, font=candidate)[1]
        for line in lines
    ]
    return candidate, lines, int(candidate.size * 0.28), heights


def fit_single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: int,
    width: int,
    *,
    minimum: int = 24,
) -> ImageFont.FreeTypeFont:
    while size > minimum:
        candidate = font(SERIF, size)
        box = draw.textbbox((0, 0), text, font=candidate)
        if box[2] - box[0] <= width:
            return candidate
        size -= 2
    return font(SERIF, minimum)


def draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    font_obj: ImageFont.FreeTypeFont,
    *,
    stroke_width: int,
) -> None:
    box = draw.textbbox((0, 0), text, font=font_obj, stroke_width=stroke_width)
    x = center[0] - (box[2] - box[0]) / 2 - box[0]
    y = center[1] - (box[3] - box[1]) / 2 - box[1]
    radius = stroke_width + 2
    for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius), (-radius, -radius), (radius, radius)):
        draw.text((x + dx, y + dy), text, font=font_obj, fill=HALO)
    draw.text((x, y), text, font=font_obj, fill=INK, stroke_width=stroke_width, stroke_fill=WHITE)


def compose(background: Path, output: Path, *, title: str, author: str) -> None:
    image = fit_cover(Image.open(background))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_width = int(WIDTH * 0.82)
    title_top = int(HEIGHT * 0.48)
    title_bottom = int(HEIGHT * 0.78)
    title_font, lines, line_gap, heights = fit_title_block(
        draw,
        title,
        int(HEIGHT * 0.052),
        max_width,
        5,
        title_bottom - title_top,
    )
    total_height = sum(heights) + line_gap * max(0, len(lines) - 1)
    center_y = (title_top + title_bottom) // 2
    cursor = center_y - total_height // 2
    for line, height in zip(lines, heights):
        draw_centered(
            draw,
            line,
            (WIDTH // 2, cursor + height // 2),
            title_font,
            stroke_width=max(4, int(title_font.size * 0.055)),
        )
        cursor += height + line_gap

    author_font = fit_single_line(draw, author, int(HEIGHT * 0.024), max_width)
    draw_centered(
        draw,
        author,
        (WIDTH // 2, int(HEIGHT * 0.835)),
        author_font,
        stroke_width=max(3, int(author_font.size * 0.05)),
    )
    credit_font = font(SERIF, int(HEIGHT * 0.013))
    draw_centered(draw, "LinguaLeaf Pocket Edition", (WIDTH // 2, int(HEIGHT * 0.925)), credit_font, stroke_width=2)
    draw_centered(draw, "learn.lazying.art", (WIDTH // 2, int(HEIGHT * 0.952)), credit_font, stroke_width=2)

    output.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(output, quality=95, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--background", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--queue", type=Path, default=ROOT / "build-pocket/tasks/source-queue-2026-07-12.json")
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    task = next(item for item in queue["tasks"] if item["book_id"] == args.book_id)
    background = args.background or ROOT / "build-pocket" / args.book_id / "cover/background.png"
    output = args.output or ROOT / "build-pocket" / args.book_id / "cover/cover.png"
    compose(background, output, title=task["title"], author=task.get("author", ""))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
