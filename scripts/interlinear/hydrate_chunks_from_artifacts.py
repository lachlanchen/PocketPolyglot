#!/usr/bin/env python3
"""Rebuild chunk JSON files from stable paragraph artifacts when possible."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from codex_bilingual_chunk_worker import validate_chunk


SPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fffぁ-ゟ゠-ヿ一-龯]+", "_", name)


def artifact_path(artifact_dir: Path, paragraph_id: str) -> Path:
    return artifact_dir / f"{safe_name(paragraph_id)}.json"


def has_required_features(artifact: dict[str, Any], required: list[str]) -> bool:
    features = artifact.get("features", {})
    return all(bool(features.get(name)) for name in required)


def existing_valid_chunk(path: Path, task: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        chunk = load_json(path)
    except Exception:
        return False
    return not validate_chunk(task, chunk)


def chunk_from_artifacts(task: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    first = artifacts[0]
    return {
        "chunk_id": task["chunk_id"],
        "section": first.get("section", {}),
        "subsection": first.get("subsection", {}),
        "story": first.get("story", {}),
        "paragraphs": [artifact["paragraph"] for artifact in artifacts],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--require-feature",
        action="append",
        default=[],
        choices=["translation", "zh_ruby", "ja_ruby", "grammar"],
        help="required paragraph artifact feature; may be repeated",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace existing valid chunk files")
    args = parser.parse_args()

    tasks = load_chunks(Path(args.chunks_jsonl))
    artifact_dir = Path(args.artifact_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    hydrated = 0
    skipped_existing = 0
    partial = 0
    invalid = 0

    for task in tasks:
        out_path = output_dir / f"{task['chunk_id']}.json"
        if not args.overwrite and existing_valid_chunk(out_path, task):
            skipped_existing += 1
            continue

        artifacts: list[dict[str, Any]] = []
        ok = True
        for paragraph in task.get("paragraphs", []):
            paragraph_id = paragraph["id"]
            path = artifact_path(artifact_dir, paragraph_id)
            if not path.exists():
                ok = False
                break
            artifact = load_json(path)
            expected_hash = sha256_text(normalize(paragraph.get("text", "")))
            if artifact.get("source_normalized_sha256") != expected_hash:
                ok = False
                break
            if not has_required_features(artifact, args.require_feature):
                ok = False
                break
            artifacts.append(artifact)

        if not ok or len(artifacts) != len(task.get("paragraphs", [])):
            partial += 1
            continue

        chunk = chunk_from_artifacts(task, artifacts)
        errors = validate_chunk(task, chunk)
        if errors:
            invalid += 1
            print(f"{task['chunk_id']}: artifact validation failed: {'; '.join(errors[:8])}", file=sys.stderr)
            continue
        out_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        hydrated += 1

    print(
        f"hydrated={hydrated} skipped_existing={skipped_existing} "
        f"partial_or_missing={partial} invalid={invalid} output={output_dir}"
    )
    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
