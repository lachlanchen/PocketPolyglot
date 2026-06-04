#!/usr/bin/env python3
"""Report trilingual chunk progress against the current manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CONTENT_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
FUNCTION_PUNCT = set(" \t\r\n.,;:!?\"'“”‘’()[]{}<>《》〈〉—–-…·・、。，！？；：「」『』（）")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def paragraph_ids(chunk: dict[str, Any]) -> list[str]:
    return [paragraph.get("id", "") for paragraph in chunk.get("paragraphs", [])]


def token_stats(chunk: dict[str, Any]) -> tuple[int, int]:
    total = 0
    with_roles = 0
    for paragraph in chunk.get("paragraphs", []):
        for unit in paragraph.get("units", []):
            for lang in ("en", "zh", "ja"):
                tokens = unit.get(lang, [])
                if not isinstance(tokens, list):
                    continue
                for token in tokens:
                    if not isinstance(token, dict):
                        continue
                    text = str(token.get("t", ""))
                    if not CONTENT_RE.search(text) or all(char in FUNCTION_PUNCT for char in text):
                        continue
                    total += 1
                    if token.get("g"):
                        with_roles += 1
    return total, with_roles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunk-dir", required=True)
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_dir = Path(args.chunk_dir)
    valid: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    token_total = 0
    token_with_roles = 0
    for item in manifest.get("chunks", []):
        chunk_path = chunk_dir / f"{item['chunk_id']}.json"
        if not chunk_path.exists():
            missing.append(item["chunk_id"])
            continue
        chunk = load_json(chunk_path)
        if chunk.get("chunk_id") != item["chunk_id"] or paragraph_ids(chunk) != item.get("paragraph_ids", []):
            stale.append(item["chunk_id"])
            continue
        valid.append(item["chunk_id"])
        total, with_roles = token_stats(chunk)
        token_total += total
        token_with_roles += with_roles

    print(f"manifest_chunks={len(manifest.get('chunks', []))}")
    print(f"valid_chunks={len(valid)}")
    print(f"stale_chunks={len(stale)}")
    print(f"missing_chunks={len(missing)}")
    print(f"grammar_role_tokens={token_with_roles}/{token_total}")
    if valid:
        print(f"last_valid={valid[-1]}")
    if stale:
        print(f"first_stale={stale[0]}")
    if missing:
        print(f"first_missing={missing[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
