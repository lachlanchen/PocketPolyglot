#!/usr/bin/env python3
"""Sync current-manifest interlinear chunks into tracked data files."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def paragraph_ids(chunk: dict[str, Any]) -> list[str]:
    return [paragraph.get("id", "") for paragraph in chunk.get("paragraphs", [])]


def token_stats(chunk: dict[str, Any]) -> tuple[int, int]:
    total = 0
    with_roles = 0
    for paragraph in chunk.get("paragraphs", []):
        for unit in paragraph.get("units", []):
            token_groups: list[Any] = [unit.get("zh", [])]
            token_groups.extend(unit.get("ja", []))
            for tokens in token_groups:
                if not isinstance(tokens, list):
                    continue
                for token in tokens:
                    if not isinstance(token, dict):
                        continue
                    text = str(token.get("t", ""))
                    if not text.strip():
                        continue
                    total += 1
                    if token.get("g"):
                        with_roles += 1
    return total, with_roles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--progress-json", required=True)
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_dir = Path(args.chunk_dir)
    output_dir = Path(args.output_dir)
    progress_json = Path(args.progress_json)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_json.parent.mkdir(parents=True, exist_ok=True)

    valid_chunks: list[str] = []
    missing_chunks: list[str] = []
    stale_chunks: list[str] = []
    covered_source_chars = 0
    token_total = 0
    token_with_roles = 0

    for old_chunk in output_dir.glob("*.json"):
        old_chunk.unlink()

    for item in manifest.get("chunks", []):
        chunk_id = item["chunk_id"]
        chunk_path = chunk_dir / f"{chunk_id}.json"
        if not chunk_path.exists():
            missing_chunks.append(chunk_id)
            continue
        chunk = load_json(chunk_path)
        if chunk.get("chunk_id") != chunk_id or paragraph_ids(chunk) != item.get("paragraph_ids", []):
            stale_chunks.append(chunk_id)
            continue
        shutil.copy2(chunk_path, output_dir / chunk_path.name)
        valid_chunks.append(chunk_id)
        expected = set(item.get("paragraph_ids", []))
        covered_source_chars += sum(
            len(str(paragraph.get("source_text", "")))
            for paragraph in chunk.get("paragraphs", [])
            if paragraph.get("id") in expected
        )
        total, with_roles = token_stats(chunk)
        token_total += total
        token_with_roles += with_roles

    progress = {
        "book_id": manifest.get("book_id"),
        "manifest_chunks": len(manifest.get("chunks", [])),
        "valid_chunks": len(valid_chunks),
        "missing_chunks": len(missing_chunks),
        "stale_chunks": len(stale_chunks),
        "covered_source_chars": covered_source_chars,
        "grammar_role_tokens": {
            "with_roles": token_with_roles,
            "total": token_total,
        },
        "last_valid": valid_chunks[-1] if valid_chunks else "",
        "first_missing": missing_chunks[0] if missing_chunks else "",
        "first_stale": stale_chunks[0] if stale_chunks else "",
    }
    progress_json.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"synced valid={progress['valid_chunks']}/{progress['manifest_chunks']} "
        f"roles={token_with_roles}/{token_total} last={progress['last_valid']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
