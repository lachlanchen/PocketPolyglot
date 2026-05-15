#!/usr/bin/env python3
"""Convert the local No Longer Human PDFs into aligned Markdown sources."""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import OrderedDict
from pathlib import Path


CHAPTERS_ZH = ["序曲", "第一手記", "第二手記", "第三手記", "後記"]
CHAPTERS_JA = OrderedDict(
    [
        ("はしがき", "序曲"),
        ("第一の手記", "第一手記"),
        ("第二の手記", "第二手記"),
        ("第三の手記", "第三手記"),
        ("あとがき", "後記"),
    ]
)
STOP_ZH = {"附錄一：太宰治情感圖", "附錄一", "附錄二：太宰治年譜", "譯後記：溫柔與純粹的生死劫", "文末"}


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "command failed"
        raise SystemExit(f"{' '.join(cmd)}: {detail}")
    return proc.stdout


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", "", line).strip()


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "。！？!?":
            end = i + 1
            while end < len(text) and text[end] in "」』”’）)]】":
                end += 1
            sentence = text[start:end].strip()
            if sentence:
                sentences.append(sentence)
            start = end
            i = end
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def group_sentences(sentences: list[str], max_chars: int) -> list[str]:
    groups: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            groups.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        groups.append(current)
    return groups


def write_markdown(path: Path, title: str, sections: OrderedDict[str, list[str]]) -> None:
    out = [f"# {title}", ""]
    for heading, paragraphs in sections.items():
        out.extend([f"## {heading}", ""])
        for paragraph in paragraphs:
            out.extend([paragraph, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def actual_zh_start(lines: list[str]) -> int:
    indices = [index for index, line in enumerate(lines) if line == "序曲"]
    if len(indices) >= 2:
        return indices[1]
    if indices:
        return indices[0]
    raise SystemExit("Could not find the real Chinese 序曲 section")


def extract_zh_sections(raw: str, max_chars: int) -> OrderedDict[str, list[str]]:
    lines = [normalize_line(line) for line in raw.replace("\r", "\n").replace("\f", "\n").splitlines()]
    start = actual_zh_start(lines)
    sections: OrderedDict[str, list[str]] = OrderedDict((chapter, []) for chapter in CHAPTERS_ZH)
    current: str | None = None
    buffers: dict[str, list[str]] = {chapter: [] for chapter in CHAPTERS_ZH}

    for line in lines[start:]:
        if not line:
            continue
        if line in STOP_ZH or any(line.startswith(stop) for stop in STOP_ZH):
            break
        if line in CHAPTERS_ZH:
            current = line
            continue
        if current is None:
            continue
        buffers[current].append(line)

    for chapter, parts in buffers.items():
        text = "".join(parts)
        sections[chapter] = group_sentences(split_sentences(text), max_chars)
    return sections


def ja_segments(raw: str) -> list[str]:
    segments: list[str] = []
    for page in raw.replace("\r", "\n").split("\f"):
        buffer: list[str] = []
        for raw_line in page.splitlines():
            line = normalize_line(raw_line)
            if not line:
                if buffer:
                    segments.append("".join(buffer))
                    buffer = []
                continue
            buffer.append(line)
        if buffer:
            segments.append("".join(buffer))
    return segments


def extract_ja_sections(raw: str, max_chars: int, *, aligned_headings: bool) -> OrderedDict[str, list[str]]:
    sections: OrderedDict[str, list[str]] = OrderedDict()
    buffers: OrderedDict[str, list[str]] = OrderedDict()
    current: str | None = None
    headers = set(CHAPTERS_JA)

    for line in ja_segments(raw):
        if not line or line in {"人間失格", "太宰治"}:
            continue
        if line in headers:
            current = CHAPTERS_JA[line] if aligned_headings else line
            buffers.setdefault(current, [])
            continue
        if current is None:
            continue
        buffers[current].append(line)

    expected = CHAPTERS_ZH if aligned_headings else list(CHAPTERS_JA)
    for heading in expected:
        parts = buffers.get(heading, [])
        sections[heading] = group_sentences(split_sentences("".join(parts)), max_chars)
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zh-pdf", required=True)
    parser.add_argument("--ja-pdf", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--zh-max-chars", type=int, default=220)
    parser.add_argument("--ja-max-chars", type=int, default=260)
    args = parser.parse_args()

    zh_pdf = Path(args.zh_pdf)
    ja_pdf = Path(args.ja_pdf)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zh_raw = run_text(["pdftotext", "-raw", str(zh_pdf), "-"])
    ja_raw = run_text(["mutool", "draw", "-F", "txt", "-o", "-", str(ja_pdf)])

    (out_dir / "zh.raw.md").write_text(zh_raw, encoding="utf-8")
    (out_dir / "ja.raw.md").write_text(ja_raw, encoding="utf-8")

    zh_sections = extract_zh_sections(zh_raw, args.zh_max_chars)
    ja_sections_aligned = extract_ja_sections(ja_raw, args.ja_max_chars, aligned_headings=True)
    ja_sections_original = extract_ja_sections(ja_raw, args.ja_max_chars, aligned_headings=False)

    write_markdown(out_dir / "zh.clean.md", "人間失格", zh_sections)
    write_markdown(out_dir / "zh.md", "人間失格", zh_sections)
    write_markdown(out_dir / "ja.clean.md", "人間失格", ja_sections_original)
    write_markdown(out_dir / "ja.md", "人間失格", ja_sections_aligned)

    print(
        "zh_paragraphs="
        f"{sum(len(items) for items in zh_sections.values())} "
        "ja_paragraphs="
        f"{sum(len(items) for items in ja_sections_aligned.values())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
