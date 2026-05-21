#!/usr/bin/env python3
"""Validate a three-layer classical Chinese chunk JSON file.

Schema: zh_classical_three_layer
Checks: reconstruction, character-level tokens, grammar roles,
        Japanese placeholder rejection, modern Chinese distinctness.

Config-driven checks via shiji_config.py and source-audit.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from shiji_config import (
    HAN_RE, KANA_RE, SINGLE_HAN_RE,
    GRAMMAR_ROLES, ja_quality_error,
    normalize, token_text, allows_identical_zh_modern,
)

SPACE_RE = re.compile(r"\s+")
PLACEHOLDER_JA = {"注", "注。", "。", "日本語"}
PUNCT_RE = re.compile(
    r"^[，。、；：！？「」『』【】《》（）—…·・\"\"''\\-\\.\\!\\?\\;\\:\\\"\\'\\(\\)\\[\\]\\s]+$"
)


def is_punct_or_space(text: str) -> bool:
    return bool(PUNCT_RE.fullmatch(text))


def validate_zh(tokens: list[dict[str, Any]], where: str, errors: list[str]) -> None:
    if not isinstance(tokens, list):
        errors.append(f"{where}: must be a token list")
        return
    for i, tok in enumerate(tokens):
        if not isinstance(tok, dict) or "t" not in tok:
            errors.append(f"{where}[{i}]: token must have t key")
            continue
        t = str(tok.get("t", ""))
        r = str(tok.get("r", ""))
        g = str(tok.get("g", ""))
        has_han = bool(HAN_RE.search(t))
        is_single = bool(SINGLE_HAN_RE.fullmatch(t))
        if has_han and not is_single:
            errors.append(f"{where}[{i}]: Han token '{t}' not single char")
        if is_single and not r:
            errors.append(f"{where}[{i}]: Han char '{t}' needs pinyin")
        if r and not is_single:
            errors.append(f"{where}[{i}]: pinyin on non-Han token '{t}'")
        if is_single or (t and not is_punct_or_space(t)):
            if g not in GRAMMAR_ROLES:
                allowed = ", ".join(sorted(GRAMMAR_ROLES))
                errors.append(
                    f"{where}[{i}]: token '{t}' role '{g}' not in {allowed}"
                )


def validate_ja(tokens: list[dict[str, Any]], where: str, errors: list[str]) -> None:
    if not isinstance(tokens, list):
        errors.append(f"{where}: must be a token list")
        return
    for i, tok in enumerate(tokens):
        if not isinstance(tok, dict) or "t" not in tok:
            errors.append(f"{where}[{i}]: token must have t key")
            continue
        t = str(tok.get("t", ""))
        r = str(tok.get("r", ""))
        g = str(tok.get("g", ""))
        has_kanji = bool(HAN_RE.search(t))
        is_single = bool(SINGLE_HAN_RE.fullmatch(t))
        if has_kanji and not is_single:
            errors.append(f"{where}[{i}]: kanji token '{t}' not single char")
        if is_single and not r:
            errors.append(f"{where}[{i}]: kanji '{t}' needs furigana")
        if r and not is_single:
            errors.append(f"{where}[{i}]: furigana on non-kanji token '{t}'")
        if t and not is_punct_or_space(t):
            if g not in GRAMMAR_ROLES:
                allowed = ", ".join(sorted(GRAMMAR_ROLES))
                errors.append(
                    f"{where}[{i}]: token '{t}' role '{g}' not in {allowed}"
                )


def validate_chunk(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("mode") != "zh_classical_three_layer":
        errors.append(f"mode must be zh_classical_three_layer, got {data.get('mode')!r}")

    if not data.get("chunk_id"):
        errors.append("missing chunk_id")

    paragraphs = data.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        errors.append("paragraphs must be a non-empty list")
        return errors

    for p_idx, para in enumerate(paragraphs):
        p_w = f"paragraphs[{p_idx}]"
        para_src = normalize(str(para.get("source_text", "")))
        units = para.get("units")
        if not isinstance(units, list) or not units:
            errors.append(f"{p_w}: missing or empty units")
            continue

        para_rebuilt: list[str] = []
        for u_idx, unit in enumerate(units):
            u_w = f"{p_w}.units[{u_idx}]"
            unit_src = normalize(str(unit.get("source_text", "")))
            unit_is_punct = bool(unit_src and is_punct_or_space(unit_src))

            zh_orig = unit.get("zh_original")
            if not isinstance(zh_orig, list) or not zh_orig:
                errors.append(f"{u_w}: missing zh_original tokens")
            else:
                validate_zh(zh_orig, f"{u_w}.zh_original", errors)
                zt = normalize(token_text(zh_orig))
                para_rebuilt.append(zt)
                if unit_src and zt != unit_src:
                    errors.append(
                        f"{u_w}: zh_original reconstructs '{zt}' "
                        f"but source_text is '{unit_src}'"
                    )

            ja = unit.get("ja")
            if not isinstance(ja, list):
                errors.append(f"{u_w}: ja must be a token list (list[dict]), got {type(ja).__name__}")
            elif len(ja) > 0 and isinstance(ja[0], list):
                errors.append(f"{u_w}: ja must be list[dict] not list[list[dict]] (flat single-line schema)")
            else:
                validate_ja(ja, f"{u_w}.ja", errors)
                lt = normalize(token_text(ja))
                if not lt:
                    errors.append(f"{u_w}.ja: Japanese text is empty")
                if lt in PLACEHOLDER_JA and not unit_is_punct:
                    errors.append(f"{u_w}.ja: Japanese is placeholder '{lt}'")
                if isinstance(zh_orig, list):
                    err = ja_quality_error(token_text(ja), token_text(zh_orig))
                    if err:
                        errors.append(f"{u_w}.ja: {err}")

            zh_mod = unit.get("zh_modern")
            if not isinstance(zh_mod, list) or not zh_mod:
                errors.append(f"{u_w}: missing zh_modern tokens")
            else:
                validate_zh(zh_mod, f"{u_w}.zh_modern", errors)
                zmt = normalize(token_text(zh_mod))
                zot = normalize(token_text(zh_orig or []))
                if (
                    zmt and zmt == zot
                    and not unit_is_punct
                    and not allows_identical_zh_modern(unit_src)
                ):
                    errors.append(
                        f"{u_w}: zh_modern identical to zh_original; must differ"
                    )

        if para_rebuilt and para_src:
            rp = "".join(para_rebuilt)
            if rp != para_src:
                errors.append(
                    f"{p_w}: units reconstruct '{rp}' "
                    f"but paragraph source_text is '{para_src}'"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", help="Path to chunk JSON file")
    parser.add_argument("--quiet", action="store_true", help="Suppress ok message")
    args = parser.parse_args()

    path = Path(args.json_path)
    if not path.exists():
        print(f"ERROR: file not found: {args.json_path}", file=sys.stderr)
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        return 2

    errs = validate_chunk(data)
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
