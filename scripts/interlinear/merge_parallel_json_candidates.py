#!/usr/bin/env python3
"""Validate and merge parallel JSON candidates into the canonical chunk directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from codex_chunk_worker import load_chunks
from codex_bilingual_chunk_worker import validate_chunk
from normalize_grammar_roles import cleanup_components, normalize_node, normalize_ruby_token_shapes, normalize_source_artifacts


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_valid_existing(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
        normalize_node(data)
        normalize_source_artifacts(data)
        normalize_ruby_token_shapes(data)
        cleanup_components(data)
        return not validate_chunk(source, data)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--after-merge-command", default="")
    parser.add_argument("--max-merge", type=int, default=0, help="0 means merge all currently valid candidates")
    args = parser.parse_args()

    sources = load_chunks(Path(args.chunks_jsonl))
    candidate_dir = Path(args.candidate_dir) / "accepted"
    canonical_dir = Path(args.canonical_dir)
    merged_dir = Path(args.merged_dir)
    rejected_dir = Path(args.candidate_dir) / "merge-rejected"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    merged = 0
    merged_ids: list[str] = []
    known_ids = {chunk["chunk_id"] for chunk in sources}
    for stray_path in sorted(candidate_dir.glob("*.json")):
        if stray_path.stem not in known_ids:
            shutil.move(str(stray_path), rejected_dir / stray_path.name)

    for source in sources:
        chunk_id = source["chunk_id"]
        canonical_path = canonical_dir / f"{chunk_id}.json"
        if is_valid_existing(canonical_path, source):
            continue

        candidate_path = candidate_dir / f"{chunk_id}.json"
        if not candidate_path.exists():
            print(f"waiting_for={chunk_id}")
            break
        try:
            data = load_json(candidate_path)
            normalize_node(data)
            normalize_source_artifacts(data)
            normalize_ruby_token_shapes(data)
            cleanup_components(data)
            errors = validate_chunk(source, data)
        except Exception as exc:
            errors = [str(exc)]
        if errors:
            reject_path = rejected_dir / candidate_path.name
            shutil.move(str(candidate_path), reject_path)
            (reject_path.with_suffix(".errors.txt")).write_text("\n".join(errors) + "\n", encoding="utf-8")
            print(f"rejected {chunk_id}: {'; '.join(errors[:10])}")
            break

        tmp_path = canonical_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(canonical_path)
        shutil.move(str(candidate_path), merged_dir / candidate_path.name)
        merged += 1
        merged_ids.append(chunk_id)
        print(f"merged {chunk_id}")
        if args.max_merge and merged >= args.max_merge:
            break

    print(f"merged_count={merged}")
    if merged and args.after_merge_command:
        env = os.environ.copy()
        env.update(
            {
                "ZHJPBOOK_MERGED_CHUNKS": " ".join(merged_ids),
                "ZHJPBOOK_MERGED_COUNT": str(merged),
                "ZHJPBOOK_FIRST_MERGED": merged_ids[0],
                "ZHJPBOOK_LAST_MERGED": merged_ids[-1],
            }
        )
        result = subprocess.run(args.after_merge_command, shell=True, env=env)
        if result.returncode:
            print(f"after_merge_command_failed={result.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
