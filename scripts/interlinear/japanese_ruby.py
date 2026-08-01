#!/usr/bin/env python3
"""Create compact, compound-safe Japanese ruby tokens."""

from __future__ import annotations

import re
from typing import Any

import pykakasi


HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
RUBY_BASE_MARKS = {"々", "〻", "ヵ", "ヶ"}
JAPANESE_RUN_RE = re.compile(
    r"[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〻ヵヶー]+"
)
KAKASI = pykakasi.kakasi()


def kana_to_hira(text: str) -> str:
    out: list[str] = []
    for char in str(text):
        code = ord(char)
        if 0x30A1 <= code <= 0x30FA:
            out.append(chr(code - 0x60))
        else:
            out.append(char)
    return "".join(out)


def append_plain(tokens: list[dict[str, str]], text: str) -> None:
    if not text:
        return
    if tokens and "r" not in tokens[-1]:
        tokens[-1]["t"] += text
    else:
        tokens.append({"t": text})


def is_ruby_base_char(char: str) -> bool:
    return bool(HAN_RE.fullmatch(char)) or char in RUBY_BASE_MARKS


def tokenize_segment(orig: str, hira: str) -> list[dict[str, str]]:
    """Keep compound readings intact instead of guessing per-kanji morae."""

    if not HAN_RE.search(orig):
        return [{"t": orig}] if orig else []

    chars = list(orig)
    first = next(index for index, char in enumerate(chars) if HAN_RE.fullmatch(char))
    last = len(chars) - 1 - next(
        index
        for index, char in enumerate(reversed(chars))
        if is_ruby_base_char(char)
    )
    prefix = "".join(chars[:first])
    base = "".join(chars[first : last + 1])
    suffix = "".join(chars[last + 1 :])
    reading = kana_to_hira(hira)

    prefix_reading = kana_to_hira(prefix)
    suffix_reading = kana_to_hira(suffix)
    can_trim_prefix = not prefix or reading.startswith(prefix_reading)
    can_trim_suffix = not suffix or reading.endswith(suffix_reading)
    if can_trim_prefix and prefix:
        reading = reading[len(prefix_reading) :]
    if can_trim_suffix and suffix:
        reading = reading[: -len(suffix_reading)]

    # If orthographic kana do not align mechanically with the reading, keep
    # the whole short lexical segment under one correct ruby rather than
    # inventing character-level readings.
    if not (can_trim_prefix and can_trim_suffix) or not reading:
        return [{"t": orig, "r": kana_to_hira(hira) or "よみ"}]

    tokens: list[dict[str, str]] = []
    append_plain(tokens, prefix)
    tokens.append({"t": base, "r": reading})
    append_plain(tokens, suffix)
    return tokens


def tokenize_japanese(text: Any) -> list[dict[str, str]]:
    """Tokenize Japanese while preserving every non-Japanese codepoint.

    Pykakasi can duplicate Latin spans around extended characters such as the
    macrons in ``Gyūichi`` or the cedilla in ``Tçuzzu``.  Feed it only genuine
    Japanese runs and append all other text verbatim.
    """

    tokens: list[dict[str, str]] = []
    original = str(text)
    cursor = 0
    for run in JAPANESE_RUN_RE.finditer(original):
        append_plain(tokens, original[cursor : run.start()])
        run_text = run.group(0)
        try:
            segments = KAKASI.convert(run_text)
        except Exception:
            segments = [{"orig": run_text, "hira": ""}]
        for segment in segments:
            orig = str(segment.get("orig") or "")
            hira = str(segment.get("hira") or "")
            for token in tokenize_segment(orig, hira):
                if token.get("r"):
                    tokens.append(token)
                else:
                    append_plain(tokens, token.get("t", ""))
        cursor = run.end()
    append_plain(tokens, original[cursor:])
    return tokens or [{"t": original}]
