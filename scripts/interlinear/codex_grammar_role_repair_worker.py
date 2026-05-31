#!/usr/bin/env python3
"""Repair grammar-role colors in existing interlinear chunks without regenerating text."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_chunk_worker import extract_json, load_chunks, run_codex
from codex_bilingual_chunk_worker import GRAMMAR_ROLES, validate_chunk
from normalize_grammar_roles import cleanup_components, normalize_node

PROMPT_VERSION = "major-component-role-repair-v1"


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_sha(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def token_view(tokens: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(tokens, list):
        return []
    result: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if isinstance(token, dict):
            result.append(
                {
                    "path": f"{path}/{index}",
                    "t": token.get("t", ""),
                    "r": token.get("r", ""),
                    "g": token.get("g", ""),
                }
            )
    return result


def role_view(chunk: dict[str, Any]) -> dict[str, Any]:
    paragraphs: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(chunk.get("paragraphs", [])):
        units: list[dict[str, Any]] = []
        for unit_index, unit in enumerate(paragraph.get("units", [])):
            unit_path = f"paragraphs/{paragraph_index}/units/{unit_index}"
            ja_lines = unit.get("ja", [])
            units.append(
                {
                    "source_text": unit.get("source_text", ""),
                    "zh": token_view(unit.get("zh", []), f"{unit_path}/zh"),
                    "ja": [
                        token_view(ja_lines[0], f"{unit_path}/ja/0") if len(ja_lines) > 0 else [],
                        token_view(ja_lines[1], f"{unit_path}/ja/1") if len(ja_lines) > 1 else [],
                    ],
                }
            )
        paragraphs.append(
            {
                "id": paragraph.get("id", ""),
                "source_text": paragraph.get("source_text", ""),
                "units": units,
            }
        )
    return {
        "chunk_id": chunk.get("chunk_id", ""),
        "paragraphs": paragraphs,
    }


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"prompt_version": PROMPT_VERSION, "chunks": {}}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_chunk(data: dict[str, Any]) -> int:
    changed = normalize_node(data)
    changed += cleanup_components(data)
    return changed


def resolve_token(data: dict[str, Any], path: str) -> dict[str, Any]:
    current: Any = data
    for part in path.split("/"):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise ValueError(f"{path}: path enters non-container")
    if not isinstance(current, dict) or "t" not in current:
        raise ValueError(f"{path}: path does not point to a token")
    return current


def apply_edits(data: dict[str, Any], edits: list[Any]) -> int:
    changed = 0
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise ValueError(f"edits[{index}]: must be an object")
        path = str(edit.get("path", ""))
        role = str(edit.get("g", "")).strip().lower()
        if role not in GRAMMAR_ROLES:
            raise ValueError(f"edits[{index}]: unsupported role {role!r}")
        token = resolve_token(data, path)
        expected_text = edit.get("t")
        if expected_text is not None and str(expected_text) != str(token.get("t", "")):
            raise ValueError(f"edits[{index}]: text mismatch at {path}")
        if token.get("g") != role:
            token["g"] = role
            changed += 1
    return changed


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        shown = previous_errors[:80]
        error_block = "\nPrevious edit set failed validation. Fix only these issues:\n" + "\n".join(
            f"- {error}" for error in shown
        )
    roles = ", ".join(sorted(GRAMMAR_ROLES))
    return textwrap.dedent(
        f"""
        You are repairing only the grammar-color roles for an existing Chinese/Japanese interlinear chunk.

        The text, readings, unit boundaries, order, translations, and ruby are already prepared. Do not regenerate or rewrite them.
        Return exactly one JSON object with only role edits, no Markdown fences and no explanation:
        {{
          "chunk_id": "{chunk.get('chunk_id', '')}",
          "prompt_version": "{PROMPT_VERSION}",
          "edits": [
            {{"path": "paragraphs/0/units/0/ja/1/3", "t": "token text at that path", "g": "object"}}
          ]
        }}

        Use an empty edits array if the current roles are already good enough.

        Goal:
        - Make major components between Chinese and Japanese visually close, not exact word-for-word.
        - Use exactly one role per token: {roles}.
        - Prefer stable major phrase coloring over fine grammatical purity.
        - Subject/topic-like Japanese は or が phrases that correspond to Chinese subjects should normally share the subject/topic visual family.
        - Attached Japanese particles, honorific kana, list markers, and case endings inherit the major role of their phrase when that improves visual grouping. Examples: さんを after an object is object; だの/など in an object list is object; に/へ in an adverbial phrase is adverbial.
        - Chinese aspect particles after predicates or attributive verbs may inherit that phrase role when it helps the visual grouping.
        - Keep punctuation, standalone conjunctions, and discourse-only words as function.
        - Do not change any path unless it improves a visible major-component mismatch.
        - Do not output the full chunk JSON. Output only the minimal edits array.
        {error_block}

        Current role view:
        {json.dumps(role_view(chunk), ensure_ascii=False, indent=2)}
        """
    ).strip()


def chunk_sources_by_id(path: Path) -> dict[str, dict[str, Any]]:
    return {chunk["chunk_id"]: chunk for chunk in load_chunks(path)}


def iter_manifest_chunks(manifest_path: Path, chunk_dir: Path, start_index: int, end_index: int | None) -> list[tuple[int, str, Path]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("chunks", [])
    selected: list[tuple[int, str, Path]] = []
    for index, item in enumerate(items, start=1):
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        chunk_id = item["chunk_id"]
        path = chunk_dir / f"{chunk_id}.json"
        if path.exists():
            selected.append((index, chunk_id, path))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--state-json", default="")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="xhigh")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--after-chunk-command", default="")
    args = parser.parse_args()

    cwd = Path.cwd()
    manifest_path = Path(args.manifest)
    chunk_dir = Path(args.chunk_dir)
    work_dir = Path(args.work_dir)
    state_path = Path(args.state_json) if args.state_json else work_dir / "state.json"
    state = load_state(state_path)
    state["prompt_version"] = PROMPT_VERSION
    state.setdefault("chunks", {})
    source_chunks = chunk_sources_by_id(Path(args.chunks_jsonl))

    selected = iter_manifest_chunks(manifest_path, chunk_dir, args.start_index, args.end_index)
    if args.max_chunks:
        selected = selected[: args.max_chunks]

    for manifest_index, chunk_id, chunk_path in selected:
        source = source_chunks[chunk_id]
        data = json.loads(chunk_path.read_text(encoding="utf-8"))
        heuristic_changed = normalize_chunk(data)
        if heuristic_changed:
            chunk_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        input_sha = json_sha(data)
        chunk_state = state["chunks"].get(chunk_id, {})
        if (
            not args.force
            and chunk_state.get("prompt_version") == PROMPT_VERSION
            and chunk_state.get("input_sha") == input_sha
        ):
            print(f"skip repaired {chunk_id}")
            continue

        errors: list[str] | None = None
        for attempt in range(1, args.retries + 2):
            prompt = prompt_for_chunk(data, errors)
            prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
            message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
            log_path = work_dir / "logs" / f"{chunk_id}.log"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")

            print(f"codex grammar repair {chunk_id} attempt {attempt}")
            try:
                run_codex(
                    prompt,
                    message_path,
                    log_path,
                    first=True,
                    model=args.model,
                    reasoning=args.reasoning,
                    cwd=cwd,
                    timeout_seconds=args.codex_timeout_seconds,
                )
                response = extract_json(message_path.read_text(encoding="utf-8"))
                if response.get("chunk_id") != chunk_id:
                    raise ValueError(f"chunk_id mismatch: {response.get('chunk_id')!r}")
                edits = response.get("edits", [])
                if not isinstance(edits, list):
                    raise ValueError("edits must be a list")
                candidate = copy.deepcopy(data)
                edit_count = apply_edits(candidate, edits)
                heuristic_count = normalize_chunk(candidate)
                validation_errors = validate_chunk(source, candidate)
                if validation_errors:
                    raise ValueError("; ".join(validation_errors[:80]))
            except Exception as exc:
                errors = [str(exc)]
                print(f"repair failed for {chunk_id}: {errors[0]}", flush=True)
                continue

            output_sha = json_sha(candidate)
            if output_sha != input_sha:
                chunk_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            state["chunks"][chunk_id] = {
                "prompt_version": PROMPT_VERSION,
                "input_sha": output_sha,
                "edit_count": edit_count,
                "heuristic_count": heuristic_changed + heuristic_count,
                "manifest_index": manifest_index,
                "repaired_at": datetime.now(timezone.utc).isoformat(),
            }
            write_state(state_path, state)
            print(f"repaired {chunk_id}: edits={edit_count} heuristic={heuristic_changed + heuristic_count}")
            if args.after_chunk_command:
                env = os.environ.copy()
                env.update(
                    {
                        "ZHJPBOOK_CHUNK_ID": chunk_id,
                        "ZHJPBOOK_CHUNK_INDEX": str(manifest_index),
                        "ZHJPBOOK_CHUNK_PATH": str(chunk_path),
                    }
                )
                subprocess.run(args.after_chunk_command, shell=True, check=True, cwd=cwd, env=env)
            break
        else:
            raise RuntimeError(f"failed to repair {chunk_id} after retries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
