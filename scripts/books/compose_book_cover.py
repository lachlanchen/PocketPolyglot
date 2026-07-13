#!/usr/bin/env python3
"""Compose a pocket-book cover from a generated textless background."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
WIDTH = 1536
HEIGHT = round(WIDTH * 148 / 105)
SERIF_REGULAR = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SYMBOL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TEXT_INK = (0, 0, 0, 255)
TEXT_OUTLINE = (255, 255, 255, 255)
TEXT_HALO = (0, 0, 0, 150)

# Cover titles often differ only by simplified/traditional orthography.  This
# compact canonicalization prevents the compositor from printing both forms as
# if they were distinct titles.  It is intentionally limited to common title
# characters rather than changing the displayed text.
TITLE_CANONICAL_MAP = str.maketrans(
    {
        "國": "国",
        "學": "学",
        "書": "书",
        "經": "经",
        "傳": "传",
        "記": "记",
        "誌": "志",
        "註": "注",
        "釋": "释",
        "義": "义",
        "詩": "诗",
        "禮": "礼",
        "樂": "乐",
        "漢": "汉",
        "晉": "晋",
        "後": "后",
        "戰": "战",
        "錄": "录",
        "說": "说",
        "語": "语",
        "選": "选",
        "編": "编",
        "譯": "译",
        "續": "续",
        "體": "体",
        "總": "总",
        "集": "集",
    }
)


def canonical_title(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).translate(TITLE_CANONICAL_MAP)
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]", "", normalized).casefold()


def equivalent_title(left: str, right: str) -> bool:
    return bool(left and right and canonical_title(left) == canonical_title(right))


def draw_halo_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    font_obj: ImageFont.FreeTypeFont,
    *,
    halo_fill: tuple[int, int, int, int],
    radius: int,
) -> None:
    """Draw a restrained subtitle-style dark halo behind crisp outlined text."""
    if radius <= 0:
        return
    x, y = position
    offsets = (
        (-radius, 0),
        (radius, 0),
        (0, -radius),
        (0, radius),
        (-radius, -radius),
        (-radius, radius),
        (radius, -radius),
        (radius, radius),
    )
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, font=font_obj, fill=halo_fill)


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
    *,
    shadow_fill: tuple[int, int, int, int] | None = None,
    shadow_offset: int = 2,
    stroke_fill: tuple[int, int, int, int] | None = None,
    stroke_width: int = 0,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    x = xy[0] - (bbox[2] - bbox[0]) / 2
    y = xy[1] - (bbox[3] - bbox[1]) / 2
    if shadow_fill:
        draw_halo_text(
            draw,
            (x, y),
            text,
            font_obj,
            halo_fill=shadow_fill,
            radius=max(shadow_offset, stroke_width + 1),
        )
    draw.text(
        (x, y),
        text,
        font=font_obj,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill or fill,
    )


def draw_centered_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font_path: str,
    size: int,
    index: int,
    fill: tuple[int, int, int, int],
    *,
    max_width: int,
    min_size: int,
    shadow_fill: tuple[int, int, int, int] | None = None,
    stroke_fill: tuple[int, int, int, int] | None = None,
    stroke_width: int | None = None,
) -> None:
    fitted = font(font_path, size, index=index)
    while size > min_size:
        bbox = draw.textbbox((0, 0), text, font=fitted)
        if bbox[2] - bbox[0] <= max_width:
            break
        size -= 1
        fitted = font(font_path, size, index=index)
    if stroke_width is None:
        stroke_width = max(2, int(size * 0.055)) if stroke_fill else 0
    draw_centered(
        draw,
        text,
        xy,
        fitted,
        fill,
        shadow_fill=shadow_fill,
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )


def wrap_latin_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_obj: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = " ".join(text.split()).split()
    if not words:
        return []
    lines: list[str] = []
    line = words[0]
    for index, word in enumerate(words[1:], start=1):
        candidate = f"{line} {word}"
        if text_width(draw, candidate, font_obj) <= max_width:
            line = candidate
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            lines[-1] = f"{lines[-1]} {' '.join(words[index:])}"
            return lines
    lines.append(line)
    return lines


def draw_centered_multiline_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font_path: str,
    size: int,
    index: int,
    fill: tuple[int, int, int, int],
    *,
    max_width: int,
    max_height: int,
    min_size: int,
    max_lines: int,
    shadow_fill: tuple[int, int, int, int] | None = None,
    stroke_fill: tuple[int, int, int, int] | None = None,
    stroke_width: int | None = None,
) -> None:
    if not text:
        return
    fitted = font(font_path, size, index=index)
    lines = wrap_latin_lines(draw, text, fitted, max_width, max_lines)
    while size > min_size:
        fitted = font(font_path, size, index=index)
        lines = wrap_latin_lines(draw, text, fitted, max_width, max_lines)
        line_boxes = [draw.textbbox((0, 0), line, font=fitted) for line in lines]
        widths = [box[2] - box[0] for box in line_boxes]
        heights = [box[3] - box[1] for box in line_boxes]
        total_height = sum(heights) + max(0, len(lines) - 1) * max(4, int(size * 0.25))
        if widths and max(widths) <= max_width and total_height <= max_height:
            break
        size -= 1
    gap = max(4, int(size * 0.25))
    line_boxes = [draw.textbbox((0, 0), line, font=fitted) for line in lines]
    heights = [box[3] - box[1] for box in line_boxes]
    total_height = sum(heights) + max(0, len(lines) - 1) * gap
    y = xy[1] - total_height / 2
    if stroke_width is None:
        stroke_width = max(2, int(size * 0.055)) if stroke_fill else 0
    for line, height in zip(lines, heights):
        draw_centered(
            draw,
            line,
            (xy[0], int(y + height / 2)),
            fitted,
            fill,
            shadow_fill=shadow_fill,
            stroke_fill=stroke_fill,
            stroke_width=stroke_width,
        )
        y += height + gap


def text_width(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    return bbox[2] - bbox[0]


def vertical_text_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_obj: ImageFont.FreeTypeFont,
    gap: int,
) -> int:
    total = 0
    chars = list(text)
    for ch in chars:
        bbox = draw.textbbox((0, 0), ch, font=font_obj)
        total += bbox[3] - bbox[1]
    return total + gap * max(0, len(chars) - 1)


def fit_vertical_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    size: int,
    index: int,
    *,
    max_height: int,
    min_size: int,
) -> tuple[ImageFont.FreeTypeFont, int]:
    while size > min_size:
        gap = max(2, int(size * 0.10))
        fitted = font(font_path, size, index=index)
        if vertical_text_height(draw, text, fitted, gap) <= max_height:
            return fitted, gap
        size -= 2
    gap = max(2, int(size * 0.10))
    return font(font_path, size, index=index), gap


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
    shadow_fill: tuple[int, int, int, int] | None = None,
    shadow_offset: int = 2,
    stroke_fill: tuple[int, int, int, int] | None = None,
    stroke_width: int = 0,
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
        if shadow_fill:
            draw_halo_text(
                draw,
                (x - w / 2, cursor),
                ch,
                font_obj,
                halo_fill=shadow_fill,
                radius=max(shadow_offset, stroke_width + 1),
            )
        draw.text(
            (x - w / 2, cursor),
            ch,
            font=font_obj,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill or fill,
        )
        cursor += h + gap


def draw_yijing_trigrams(draw: ImageDraw.ImageDraw, *, fill: tuple[int, int, int, int]) -> None:
    symbol_font = ImageFont.truetype(SYMBOL_FONT, size=int(HEIGHT * 0.034))
    trigrams = ["☰", "☱", "☲", "☳", "☴", "☵", "☶", "☷"]
    positions = [
        (int(WIDTH * 0.19), int(HEIGHT * 0.18)),
        (int(WIDTH * 0.81), int(HEIGHT * 0.18)),
        (int(WIDTH * 0.18), int(HEIGHT * 0.34)),
        (int(WIDTH * 0.82), int(HEIGHT * 0.34)),
        (int(WIDTH * 0.18), int(HEIGHT * 0.52)),
        (int(WIDTH * 0.82), int(HEIGHT * 0.52)),
        (int(WIDTH * 0.19), int(HEIGHT * 0.70)),
        (int(WIDTH * 0.81), int(HEIGHT * 0.70)),
    ]
    for trigram, position in zip(trigrams, positions):
        draw_centered(draw, trigram, position, symbol_font, fill)


def load_plan(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def edition_label(plan: dict) -> str:
    labels = []
    if plan.get("source_language") == "wenyan" or plan.get("book_title_wenyan"):
        labels.append("文言文")
    if plan.get("book_title_en"):
        labels.append("English")
    if plan.get("book_title_ja"):
        labels.append("日本語")
    if plan.get("book_title_zh"):
        labels.append("中文")
    if len(labels) >= 3:
        return "・".join(labels[:4]) + " interlinear"
    if len(labels) == 2:
        return "・".join(labels) + " 対照注解"
    return "PocketPolyglot annotated edition"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--book-id", default="")
    parser.add_argument("--title-suffix", default="", help="Optional suffix appended to the displayed book titles, e.g. 第二部.")
    args = parser.parse_args()

    plan = load_plan(args.plan)
    title_suffix = args.title_suffix.strip()
    title_en = (plan.get("book_title_en") or "").strip()
    title_ja = (plan.get("book_title_ja") or "").strip()
    title_zh = (plan.get("book_title_zh") or "").strip()
    title_wenyan = (plan.get("book_title_wenyan") or "").strip()
    if title_suffix:
        title_en = f"{title_en}{title_suffix}" if title_en else ""
        title_ja = f"{title_ja}{title_suffix}" if title_ja else ""
        title_zh = f"{title_zh}{title_suffix}" if title_zh else ""
        title_wenyan = f"{title_wenyan}{title_suffix}" if title_wenyan else ""
    if plan.get("source_language") == "wenyan" and title_wenyan:
        primary_cjk = title_wenyan
    else:
        primary_cjk = title_ja or title_zh or title_wenyan or title_en or args.book_id
    side_cjk = ""
    for candidate in (title_zh, title_ja, title_wenyan):
        if candidate and not equivalent_title(candidate, primary_cjk):
            side_cjk = candidate
            break
    author = plan.get("author") or ""
    author_reading = plan.get("author_reading_ja") or plan.get("author_reading_zh") or ""

    image = fit_cover(Image.open(args.background))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    panel_left = int(WIDTH * 0.355)
    panel_right = int(WIDTH * 0.645)
    panel_top = int(HEIGHT * 0.080)
    panel_bottom = int(HEIGHT * 0.710)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=26,
        fill=(255, 255, 255, 24),
        outline=(255, 255, 255, 48),
        width=1,
    )

    title_max_height = int(HEIGHT * 0.510)
    title_font, title_gap = fit_vertical_font(
        draw,
        primary_cjk,
        SERIF_BOLD,
        int(HEIGHT * 0.061),
        0,
        max_height=title_max_height,
        min_size=int(HEIGHT * 0.030),
    )
    side_font = font(SERIF_REGULAR, int(HEIGHT * 0.024), index=2)
    small_font = font(SERIF_REGULAR, int(HEIGHT * 0.020), index=0)

    ink = TEXT_INK
    muted = TEXT_INK
    soft_shadow = TEXT_HALO
    text_outline = TEXT_OUTLINE

    if args.book_id == "yijing":
        draw_yijing_trigrams(draw, fill=(28, 22, 17, 185))

    draw_vertical(
        draw,
        primary_cjk,
        WIDTH // 2,
        int(HEIGHT * 0.122),
        title_font,
        fill=ink,
        gap=title_gap,
        max_bottom=int(HEIGHT * 0.665),
        shadow_fill=soft_shadow,
        stroke_fill=text_outline,
        stroke_width=max(4, int(title_font.size * 0.065)),
    )
    if side_cjk:
        draw_vertical(
            draw,
            side_cjk,
            int(WIDTH * 0.36),
            int(HEIGHT * 0.20),
            side_font,
            fill=muted,
            gap=5,
            max_bottom=int(HEIGHT * 0.66),
            shadow_fill=soft_shadow,
            stroke_fill=text_outline,
            stroke_width=max(3, int(side_font.size * 0.055)),
        )

    text_width_limit = int(WIDTH * 0.72)
    if title_en:
        draw_centered_multiline_fit(
            draw,
            title_en,
            (WIDTH // 2, int(HEIGHT * 0.735)),
            SERIF_BOLD,
            int(HEIGHT * 0.029),
            0,
            ink,
            max_width=text_width_limit,
            max_height=int(HEIGHT * 0.090),
            min_size=int(HEIGHT * 0.014),
            max_lines=3,
            shadow_fill=soft_shadow,
            stroke_fill=text_outline,
        )

    author_line = f"{author}（{author_reading}）" if author_reading else author
    author_y = int(HEIGHT * 0.812 if title_en else HEIGHT * 0.750)
    if author and author_reading and text_width(draw, author_line, small_font) > text_width_limit:
        draw_centered_fit(
            draw,
            author,
            (WIDTH // 2, author_y - int(HEIGHT * 0.011)),
            SERIF_REGULAR,
            int(HEIGHT * 0.018),
            0,
            muted,
            max_width=text_width_limit,
            min_size=int(HEIGHT * 0.011),
            shadow_fill=soft_shadow,
            stroke_fill=text_outline,
        )
        draw_centered_fit(
            draw,
            author_reading,
            (WIDTH // 2, author_y + int(HEIGHT * 0.014)),
            SERIF_REGULAR,
            int(HEIGHT * 0.013),
            0,
            muted,
            max_width=text_width_limit,
            min_size=int(HEIGHT * 0.008),
            shadow_fill=soft_shadow,
            stroke_fill=text_outline,
        )
    else:
        draw_centered_fit(
            draw,
            author_line,
            (WIDTH // 2, author_y),
            SERIF_REGULAR,
            int(HEIGHT * 0.020),
            0,
            muted,
            max_width=text_width_limit,
            min_size=int(HEIGHT * 0.010),
            shadow_fill=soft_shadow,
            stroke_fill=text_outline,
        )
    draw_centered_fit(
        draw,
        edition_label(plan),
        (WIDTH // 2, int(HEIGHT * 0.858 if title_en else HEIGHT * 0.802)),
        SERIF_REGULAR,
        int(HEIGHT * 0.019),
        2,
        muted,
        max_width=text_width_limit,
        min_size=int(HEIGHT * 0.010),
        shadow_fill=soft_shadow,
        stroke_fill=text_outline,
    )
    draw_centered_fit(
        draw,
        "AgInTiFlow curated",
        (WIDTH // 2, int(HEIGHT * 0.895)),
        SERIF_REGULAR,
        int(HEIGHT * 0.015),
        2,
        muted,
        max_width=text_width_limit,
        min_size=int(HEIGHT * 0.009),
        shadow_fill=soft_shadow,
        stroke_fill=text_outline,
        stroke_width=2,
    )
    draw_centered_fit(
        draw,
        "https://flow.lazying.art",
        (WIDTH // 2, int(HEIGHT * 0.921)),
        SERIF_REGULAR,
        int(HEIGHT * 0.015),
        2,
        muted,
        max_width=text_width_limit,
        min_size=int(HEIGHT * 0.009),
        shadow_fill=soft_shadow,
        stroke_fill=text_outline,
        stroke_width=2,
    )
    draw_centered_fit(
        draw,
        "powered by LazyingArt",
        (WIDTH // 2, int(HEIGHT * 0.947)),
        SERIF_REGULAR,
        int(HEIGHT * 0.015),
        2,
        muted,
        max_width=text_width_limit,
        min_size=int(HEIGHT * 0.009),
        shadow_fill=soft_shadow,
        stroke_fill=text_outline,
        stroke_width=2,
    )

    composed = Image.alpha_composite(image, overlay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    composed.convert("RGB").save(args.output, quality=94, optimize=True)
    print(args.output.resolve().relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
