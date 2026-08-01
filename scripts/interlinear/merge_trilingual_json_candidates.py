#!/usr/bin/env python3
"""Validate and merge trilingual JSON candidates into the canonical chunk directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from codex_chunk_worker import load_chunks
from validate_trilingual_interlinear_json import sanitize_source_controls, validate_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_chunks(path: Path) -> list[dict[str, Any]]:
    return [sanitize_source_controls(chunk) for chunk in load_chunks(path)]


def is_valid_existing(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        return not validate_chunk(source, load_json(path))
    except Exception:
        return False


def canonicalize_chapter_title(
    data: dict[str, Any],
    source: dict[str, Any],
    canonical_titles: dict[str, dict[str, Any]],
) -> bool:
    """Keep one validated multilingual title for every manifest chapter.

    Parallel workers may produce equally valid but slightly different title
    translations for consecutive chunks in one chapter. Manifest order is
    authoritative: the first validated chunk establishes the title, and later
    chunks reuse it without another model call.
    """
    chapter = data.get("chapter")
    if not isinstance(chapter, dict):
        return False
    title = chapter.get("title")
    if not isinstance(title, dict):
        return False
    chapter_id = str(source.get("chapter_id") or chapter.get("id") or "").strip()
    if not chapter_id:
        return False
    canonical = canonical_titles.get(chapter_id)
    if canonical is None:
        canonical_titles[chapter_id] = deepcopy(title)
        return False
    if title == canonical:
        return False
    chapter["title"] = deepcopy(canonical)
    return True


def write_atomic_json(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--after-merge-command", default="")
    parser.add_argument("--max-merge", type=int, default=0)
    args = parser.parse_args()

    sources = load_source_chunks(Path(args.chunks_jsonl))
    candidate_dir = Path(args.candidate_dir) / "accepted"
    canonical_dir = Path(args.canonical_dir)
    merged_dir = Path(args.merged_dir)
    rejected_dir = Path(args.candidate_dir) / "merge-rejected"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    merged = 0
    merged_ids: list[str] = []
    canonical_titles: dict[str, dict[str, Any]] = {}
    known_ids = {chunk["chunk_id"] for chunk in sources}
    for stray_path in sorted(candidate_dir.glob("*.json")):
        if stray_path.stem not in known_ids:
            shutil.move(str(stray_path), rejected_dir / stray_path.name)

    for source in sources:
        chunk_id = source["chunk_id"]
        canonical_path = canonical_dir / f"{chunk_id}.json"
        if canonical_path.exists():
            try:
                canonical_data = load_json(canonical_path)
                canonical_errors = validate_chunk(source, canonical_data)
            except Exception:
                canonical_errors = ["could not load existing canonical chunk"]
            if not canonical_errors:
                title_changed = canonicalize_chapter_title(
                    canonical_data,
                    source,
                    canonical_titles,
                )
                if title_changed:
                    normalized_errors = validate_chunk(source, canonical_data)
                    if normalized_errors:
                        raise RuntimeError(
                            f"canonical title normalization invalidated {chunk_id}: "
                            + "; ".join(normalized_errors[:10])
                        )
                    write_atomic_json(canonical_path, canonical_data)
                    print(f"normalized_chapter_title {chunk_id}")
                continue
        candidate_path = candidate_dir / f"{chunk_id}.json"
        if not candidate_path.exists():
            print(f"waiting_for={chunk_id}")
            break
        try:
            data = load_json(candidate_path)
            canonicalize_chapter_title(data, source, canonical_titles)
            errors = validate_chunk(source, data)
        except Exception as exc:
            errors = [str(exc)]
        if errors:
            reject_path = rejected_dir / candidate_path.name
            shutil.move(str(candidate_path), reject_path)
            (reject_path.with_suffix(".errors.txt")).write_text("\n".join(errors) + "\n", encoding="utf-8")
            print(f"rejected {chunk_id}: {'; '.join(errors[:10])}")
            break
        write_atomic_json(canonical_path, data)
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
