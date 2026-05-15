#!/usr/bin/env python3
"""Normalize OCR Markdown for 中国民间故事集成 四川卷 上."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


PAGE_RE = re.compile(r"^## Page (\d+)\s*$")
STORY_RE = re.compile(r"^([0-9０-９]{3})\s*[.．、]\s*(.+)$")
MAJOR_TITLES = {
    "神话",
    "传说",
    "故事",
    "笑话",
    "寓言",
}


def squeeze_spaces(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def normalize_text_line(raw: str) -> str:
    text = squeeze_spaces(raw)
    replacements = {
        "〈": "（",
        "〉": "）",
        "(": "（",
        ")": "）",
        "．": ".",
        "，": "，",
        "。": "。",
        "；": "；",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[“”\"'`]+", "", text)
    text = re.sub(r"\s*([，。！？；：、,.!?;:])\s*", r"\1", text)
    return text.strip()


def compact_heading(text: str) -> str:
    text = normalize_text_line(text)
    text = re.sub(r"[，。！？；：、,.!?;:]+$", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def is_major_title(text: str) -> bool:
    compact = compact_heading(text)
    return compact in MAJOR_TITLES


def is_subsection_title(text: str) -> bool:
    compact = compact_heading(text)
    if len(compact) > 18:
        return False
    return compact.endswith(("神话", "传说", "故事", "笑话", "寓言"))


def story_heading(text: str) -> str | None:
    match = STORY_RE.match(normalize_text_line(text))
    if not match:
        return None
    number = match.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    title = normalize_text_line(match.group(2))
    title = re.sub(r"\s+", " ", title)
    return f"{number}. {title}"


def normalize(raw: str, *, start_page: int) -> str:
    output: list[str] = []
    current_page = 0
    seen_body = False
    previous_blank = True

    def emit(line: str = "") -> None:
        nonlocal previous_blank
        if not line:
            if not previous_blank:
                output.append("")
            previous_blank = True
            return
        output.append(line)
        previous_blank = False

    for raw_line in raw.splitlines():
        page_match = PAGE_RE.match(raw_line)
        if page_match:
            current_page = int(page_match.group(1))
            emit()
            continue
        if current_page and current_page < start_page:
            continue
        if raw_line.startswith("---") or raw_line.startswith("source_") or raw_line.startswith("ocr_"):
            continue
        if raw_line.startswith("dpi:") or raw_line.startswith("generated_at:") or raw_line.startswith("notes:"):
            continue
        if raw_line.startswith("# OCR:"):
            continue

        line = normalize_text_line(raw_line)
        if not line:
            emit()
            continue
        if re.fullmatch(r"\d{1,4}", line):
            continue

        story = story_heading(line)
        if story:
            emit()
            emit(f"### {story}")
            emit()
            seen_body = True
            continue

        if is_major_title(line):
            emit()
            emit(f"# {compact_heading(line)}")
            emit()
            seen_body = True
            continue

        if seen_body and is_subsection_title(line):
            emit()
            emit(f"## {compact_heading(line)}")
            emit()
            continue

        if seen_body:
            emit(line)

    while output and not output[-1]:
        output.pop()
    return "\n".join(output) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-page", type=int, default=79)
    args = parser.parse_args()

    source = Path(args.input)
    result = normalize(source.read_text(encoding="utf-8"), start_page=args.start_page)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    print(output)
    print(f"chars={len(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
