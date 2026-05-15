#!/usr/bin/env python3
"""Normalize Snow Country Chinese/Japanese Markdown into aligned chapter windows."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


CHAPTER_RE = re.compile(r"^\d{2}$")
CONTENT_RE = re.compile(r"\S")


@dataclass
class Chapter:
    title: str
    blocks: list[str]

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def char_count(self) -> int:
        return visible_len(self.text)


def visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def read_blocks(path: Path) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def normalize_chinese(path: Path) -> list[Chapter]:
    blocks = read_blocks(path)
    chapters: list[Chapter] = []
    current: Chapter | None = None
    in_body = False
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines == ["Table of Contents"] or lines[0] == "鄒靖製作":
            break
        if len(lines) == 1 and CHAPTER_RE.match(lines[0]):
            in_body = True
            current = Chapter(lines[0], [])
            chapters.append(current)
            continue
        if not in_body:
            continue
        if current is None:
            continue
        for line in lines:
            if line == "（１９３５—１９４８）":
                continue
            if CONTENT_RE.search(line):
                current.blocks.append(line)
    return chapters


def extract_japanese_body(path: Path) -> list[str]:
    blocks = read_blocks(path)
    snow_indexes = [i for i, block in enumerate(blocks) if block.strip() == "雪 国"]
    if not snow_indexes:
        raise ValueError(f"could not find Japanese body title in {path}")
    start = snow_indexes[-1] + 1
    body: list[str] = []
    for block in blocks[start:]:
        if block.strip() == "注 釈":
            break
        if CONTENT_RE.search(block):
            body.append(block.strip())
    if not body:
        raise ValueError(f"Japanese body is empty after normalization: {path}")
    return body


def split_japanese_by_chinese_chapters(chapters: list[Chapter], ja_blocks: list[str]) -> list[Chapter]:
    if not chapters:
        raise ValueError("Chinese body has no chapters")
    zh_total = sum(chapter.char_count for chapter in chapters)
    ja_lengths = [visible_len(block) for block in ja_blocks]
    ja_total = sum(ja_lengths)
    if zh_total <= 0 or ja_total <= 0:
        raise ValueError("empty source text after normalization")

    output: list[Chapter] = []
    start = 0
    consumed = 0
    cumulative_zh = 0
    for index, chapter in enumerate(chapters):
        if index == len(chapters) - 1:
            end = len(ja_blocks)
        else:
            cumulative_zh += chapter.char_count
            target = ja_total * cumulative_zh / zh_total
            end = start
            while end < len(ja_blocks) - (len(chapters) - index - 1):
                next_len = ja_lengths[end]
                if end > start and consumed + next_len / 2 > target:
                    break
                consumed += next_len
                end += 1
            if end == start:
                consumed += ja_lengths[end]
                end += 1
        output.append(Chapter(chapter.title, ja_blocks[start:end]))
        start = end
    return output


def write_chapters(path: Path, chapters: list[Chapter]) -> None:
    parts: list[str] = []
    for chapter in chapters:
        parts.append(f"# {chapter.title}")
        parts.extend(chapter.blocks)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zh-clean", required=True)
    parser.add_argument("--ja-clean", required=True)
    parser.add_argument("--zh-output", required=True)
    parser.add_argument("--ja-output", required=True)
    args = parser.parse_args()

    zh_chapters = normalize_chinese(Path(args.zh_clean))
    ja_blocks = extract_japanese_body(Path(args.ja_clean))
    ja_chapters = split_japanese_by_chinese_chapters(zh_chapters, ja_blocks)
    write_chapters(Path(args.zh_output), zh_chapters)
    write_chapters(Path(args.ja_output), ja_chapters)
    print(
        "zh_chapters={} ja_chapters={} zh_chars={} ja_chars={}".format(
            len(zh_chapters),
            len(ja_chapters),
            sum(chapter.char_count for chapter in zh_chapters),
            sum(chapter.char_count for chapter in ja_chapters),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
