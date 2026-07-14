#!/usr/bin/env python3
"""Add dictionary-derived word-level furigana to visible Japanese in TeX.

The annotator is deterministic and local.  It preserves math, references,
URLs, labels, and existing ruby commands, while allowing visible arguments
such as headings and emphasized prose to receive furigana.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

import pykakasi
import unidic_lite
from fugashi import GenericTagger


KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆]")
JAPANESE_RUN_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uf900-\ufaff々〆〇ヶヵー]+"
)
MATH_ENVIRONMENTS = {
    "align",
    "align*",
    "alignat",
    "alignat*",
    "array",
    "displaymath",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "math",
    "multline",
    "multline*",
    "split",
    "tikzcd",
}
PRESERVE_ONE_ARGUMENT = {
    "autoref",
    "cite",
    "citep",
    "citet",
    "eqref",
    "includegraphics",
    "index",
    "label",
    "pageref",
    "path",
    "ref",
    "url",
}


@dataclass
class FuriganaStats:
    ruby_count: int = 0
    fallback_count: int = 0
    unknown_tokens: list[str] = field(default_factory=list)

    def merge(self, other: "FuriganaStats") -> None:
        self.ruby_count += other.ruby_count
        self.fallback_count += other.fallback_count
        self.unknown_tokens.extend(other.unknown_tokens)


_TAGGER = GenericTagger(f"-r /dev/null -d {unidic_lite.DICDIR}")
_KAKASI = pykakasi.kakasi()


def katakana_to_hiragana(text: str) -> str:
    chars: list[str] = []
    for char in text:
        codepoint = ord(char)
        if 0x30A1 <= codepoint <= 0x30FA:
            chars.append(chr(codepoint - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def balanced_argument(
    text: str, opening: int, open_char: str = "{", close_char: str = "}"
) -> tuple[str, int]:
    if opening >= len(text) or text[opening] != open_char:
        raise ValueError(f"expected {open_char!r} at offset {opening}")
    depth = 0
    for index in range(opening, len(text)):
        if is_escaped(text, index):
            continue
        if text[index] == open_char:
            depth += 1
        elif text[index] == close_char:
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index], index + 1
    raise ValueError(f"unbalanced {open_char}{close_char} argument")


def command_end(text: str, opening: int) -> int:
    cursor = opening + 1
    if cursor >= len(text):
        return cursor
    if text[cursor].isalpha() or text[cursor] == "@":
        while cursor < len(text) and (text[cursor].isalpha() or text[cursor] == "@"):
            cursor += 1
        if cursor < len(text) and text[cursor] == "*":
            cursor += 1
        return cursor
    return min(cursor + 1, len(text))


def skip_spaces(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def fallback_reading(surface: str) -> str:
    return "".join(item["hira"] for item in _KAKASI.convert(surface))


def annotate_word(surface: str, raw_reading: str) -> tuple[str, bool, bool]:
    if not KANJI_RE.search(surface):
        return surface, False, False
    reading = katakana_to_hiragana(raw_reading) if raw_reading and raw_reading != "*" else ""
    used_fallback = False
    if not reading:
        reading = fallback_reading(surface)
        used_fallback = True

    positions = [index for index, char in enumerate(surface) if KANJI_RE.match(char)]
    first, last = positions[0], positions[-1]
    prefix = surface[:first]
    base = surface[first : last + 1]
    suffix = surface[last + 1 :]
    normalized_prefix = katakana_to_hiragana(prefix)
    normalized_suffix = katakana_to_hiragana(suffix)
    if normalized_prefix and reading.startswith(normalized_prefix):
        reading = reading[len(normalized_prefix) :]
    if normalized_suffix and reading.endswith(normalized_suffix):
        reading = reading[: -len(normalized_suffix)]
    if not reading or KANJI_RE.search(reading):
        return surface, False, used_fallback
    return rf"{prefix}\JpRuby{{{base}}}{{{reading}}}{suffix}", True, used_fallback


def annotate_japanese_run(text: str) -> tuple[str, FuriganaStats]:
    stats = FuriganaStats()
    rendered: list[str] = []
    words = list(_TAGGER(text))
    if "".join(word.surface for word in words) != text:
        raise ValueError(f"Japanese tokenizer did not preserve source text: {text!r}")
    for word in words:
        # UniDic Lite field 17 is the inflected surface kana.  The lemma
        # reading at field 6 is wrong for forms such as 行った (it yields
        # いく rather than いった), so use surface kana first.
        reading = ""
        for index in (17, 9, 6):
            if len(word.feature) > index and word.feature[index] not in {"", "*"}:
                reading = word.feature[index]
                break
        annotated, changed, fallback = annotate_word(word.surface, reading)
        rendered.append(annotated)
        if changed:
            stats.ruby_count += 1
        elif KANJI_RE.search(word.surface):
            stats.unknown_tokens.append(word.surface)
        if fallback:
            stats.fallback_count += 1
    return "".join(rendered), stats


def annotate_plain_text(text: str) -> tuple[str, FuriganaStats]:
    stats = FuriganaStats()
    parts: list[str] = []
    cursor = 0
    for match in JAPANESE_RUN_RE.finditer(text):
        parts.append(text[cursor : match.start()])
        rendered, current = annotate_japanese_run(match.group(0))
        parts.append(rendered)
        stats.merge(current)
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts), stats


def find_math_end(text: str, opening: int) -> int:
    if text.startswith("$$", opening):
        closing = "$$"
        cursor = opening + 2
    else:
        closing = "$"
        cursor = opening + 1
    while True:
        found = text.find(closing, cursor)
        if found < 0:
            return len(text)
        if not is_escaped(text, found):
            return found + len(closing)
        cursor = found + len(closing)


def parse_command_arguments(text: str, cursor: int, count: int) -> tuple[list[str], int] | None:
    arguments: list[str] = []
    for _ in range(count):
        cursor = skip_spaces(text, cursor)
        if cursor >= len(text) or text[cursor] != "{":
            return None
        argument, end = balanced_argument(text, cursor)
        arguments.append(argument)
        cursor = end
    return arguments, cursor


def annotate_japanese_tex(tex: str) -> tuple[str, FuriganaStats]:
    """Annotate visible Japanese while leaving TeX structure byte-stable."""

    stats = FuriganaStats()
    output: list[str] = []
    plain_start = 0
    cursor = 0

    def flush_plain(end: int) -> None:
        nonlocal plain_start
        if end > plain_start:
            rendered, current = annotate_plain_text(tex[plain_start:end])
            output.append(rendered)
            stats.merge(current)

    while cursor < len(tex):
        if tex[cursor] == "%" and not is_escaped(tex, cursor):
            flush_plain(cursor)
            end = tex.find("\n", cursor)
            end = len(tex) if end < 0 else end + 1
            output.append(tex[cursor:end])
            cursor = plain_start = end
            continue
        if tex[cursor] == "$" and not is_escaped(tex, cursor):
            flush_plain(cursor)
            end = find_math_end(tex, cursor)
            output.append(tex[cursor:end])
            cursor = plain_start = end
            continue
        if tex.startswith(r"\(", cursor) or tex.startswith(r"\[", cursor):
            flush_plain(cursor)
            closing = r"\)" if tex.startswith(r"\(", cursor) else r"\]"
            found = tex.find(closing, cursor + 2)
            end = len(tex) if found < 0 else found + 2
            output.append(tex[cursor:end])
            cursor = plain_start = end
            continue
        if tex.startswith(r"\begin{", cursor):
            environment, begin_end = balanced_argument(tex, cursor + len(r"\begin"))
            if environment in MATH_ENVIRONMENTS:
                flush_plain(cursor)
                closing = rf"\end{{{environment}}}"
                found = tex.find(closing, begin_end)
                end = len(tex) if found < 0 else found + len(closing)
                output.append(tex[cursor:end])
                cursor = plain_start = end
                continue
        if tex[cursor] != "\\" or is_escaped(tex, cursor):
            cursor += 1
            continue

        end = command_end(tex, cursor)
        command = tex[cursor + 1 : end].rstrip("*")
        if command in {"JpRuby", "jpruby", "ruby"}:
            parsed = parse_command_arguments(tex, end, 2)
            if parsed:
                _, command_end_offset = parsed
                flush_plain(cursor)
                output.append(tex[cursor:command_end_offset])
                cursor = plain_start = command_end_offset
                continue
        if command == "texorpdfstring":
            parsed = parse_command_arguments(tex, end, 2)
            if parsed:
                (visible, bookmark), command_end_offset = parsed
                annotated, current = annotate_japanese_tex(visible)
                flush_plain(cursor)
                output.append(rf"\texorpdfstring{{{annotated}}}{{{bookmark}}}")
                stats.merge(current)
                cursor = plain_start = command_end_offset
                continue
        if command in {"href", "hypertarget"}:
            parsed = parse_command_arguments(tex, end, 2)
            if parsed:
                (target, visible), command_end_offset = parsed
                annotated, current = annotate_japanese_tex(visible)
                flush_plain(cursor)
                output.append(rf"\{command}{{{target}}}{{{annotated}}}")
                stats.merge(current)
                cursor = plain_start = command_end_offset
                continue
        if command in PRESERVE_ONE_ARGUMENT:
            parsed = parse_command_arguments(tex, end, 1)
            if parsed:
                _, command_end_offset = parsed
                flush_plain(cursor)
                output.append(tex[cursor:command_end_offset])
                cursor = plain_start = command_end_offset
                continue

        # The command name is structural, but visible text in following braces
        # remains eligible for annotation.
        flush_plain(cursor)
        output.append(tex[cursor:end])
        cursor = plain_start = end

    flush_plain(len(tex))
    return "".join(output), stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Japanese text/TeX; stdin when omitted")
    args = parser.parse_args(argv)
    source = args.text if args.text is not None else sys.stdin.read()
    rendered, stats = annotate_japanese_tex(source)
    sys.stdout.write(rendered)
    if source and not source.endswith("\n"):
        sys.stdout.write("\n")
    print(
        f"ruby={stats.ruby_count} fallback={stats.fallback_count} "
        f"unknown={len(stats.unknown_tokens)}",
        file=sys.stderr,
    )
    return 0 if not stats.unknown_tokens else 1


if __name__ == "__main__":
    raise SystemExit(main())
