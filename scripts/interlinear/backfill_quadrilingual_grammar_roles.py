#!/usr/bin/env python3
"""Fill missing grammar-color roles in quadrilingual chunk JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backfill_trilingual_grammar_roles import fill_token_list
from validate_quadrilingual_interlinear_json import validate_chunk


FIELD_LANG = {
    "wenyan": "zh",
    "zh_modern": "zh",
    "ja_modern": "ja",
    "en": "en",
}


def iter_token_lists(data: Any) -> list[tuple[list[dict[str, Any]], str]]:
    found: list[tuple[list[dict[str, Any]], str]] = []
    if isinstance(data, dict):
        for field, lang in FIELD_LANG.items():
            value = data.get(field)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                found.append((value, lang))
        for value in data.values():
            found.extend(iter_token_lists(value))
    elif isinstance(data, list):
        for value in data:
            found.extend(iter_token_lists(value))
    return found


def process_file(path: Path, source: dict[str, Any] | None, *, overwrite_collapsed: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for tokens, lang in iter_token_lists(data):
        changed += fill_token_list(tokens, lang, overwrite_collapsed=overwrite_collapsed)
    if source is not None:
        errors = validate_chunk(source, data)
        if errors:
            raise ValueError(f"{path}: " + "; ".join(errors[:30]))
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--overwrite-collapsed", action="store_true")
    args = parser.parse_args()
    sources = {
        item["chunk_id"]: item
        for item in (
            json.loads(line)
            for line in Path(args.chunks_jsonl).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    changed_files = 0
    changed_tokens = 0
    for path in sorted(Path(args.chunk_dir).glob("*.json")):
        changed = process_file(path, sources.get(path.stem), overwrite_collapsed=args.overwrite_collapsed)
        if changed:
            changed_files += 1
            changed_tokens += changed
    print(f"changed_files={changed_files} changed_tokens={changed_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
