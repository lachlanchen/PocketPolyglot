#!/usr/bin/env python3
"""Backfill grammar-color roles into existing trilingual chunks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_chunk_worker import extract_json, load_chunks, mentions_usage_limit, run_codex
from validate_trilingual_interlinear_json import GRAMMAR_ROLES, validate_chunk


PROMPT_VERSION = "trilingual-major-component-role-v1"
CONTENT_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_sha(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def is_content_token(token: Any) -> bool:
    return isinstance(token, dict) and bool(CONTENT_RE.search(str(token.get("t", ""))))


def role_counts(chunk: dict[str, Any]) -> tuple[int, int, int]:
    content = 0
    any_role = 0
    colored_role = 0
    for paragraph in chunk.get("paragraphs", []):
        for unit in paragraph.get("units", []):
            for lang in ("en", "zh", "ja"):
                for token in unit.get(lang, []):
                    if not is_content_token(token):
                        continue
                    content += 1
                    role = str(token.get("g", "")).strip()
                    if role:
                        any_role += 1
                    if role and role != "function":
                        colored_role += 1
    return content, any_role, colored_role


def enough_roles(chunk: dict[str, Any]) -> bool:
    content, any_role, colored_role = role_counts(chunk)
    if content == 0:
        return True
    return any_role / content >= 0.72 and colored_role / content >= 0.48


def strip_roles(chunk: dict[str, Any]) -> int:
    changed = 0
    for paragraph in chunk.get("paragraphs", []):
        for unit in paragraph.get("units", []):
            for lang in ("en", "zh", "ja"):
                for token in unit.get(lang, []):
                    if isinstance(token, dict) and "g" in token:
                        token.pop("g", None)
                        changed += 1
    return changed


def token_view(tokens: Any, path: str) -> dict[str, Any]:
    if not isinstance(tokens, list):
        return {"path": path, "tokens": []}
    return {
        "path": path,
        "tokens": [
            {
                "i": index,
                "t": token.get("t", ""),
                **({"g": token.get("g", "")} if token.get("g") else {}),
            }
            for index, token in enumerate(tokens)
            if isinstance(token, dict)
        ],
    }


def role_view(chunk: dict[str, Any]) -> dict[str, Any]:
    paragraphs: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(chunk.get("paragraphs", [])):
        units: list[dict[str, Any]] = []
        for unit_index, unit in enumerate(paragraph.get("units", [])):
            unit_path = f"paragraphs/{paragraph_index}/units/{unit_index}"
            units.append(
                {
                    "source_en": unit.get("source_en", ""),
                    "en": token_view(unit.get("en", []), f"{unit_path}/en"),
                    "zh": token_view(unit.get("zh", []), f"{unit_path}/zh"),
                    "ja": token_view(unit.get("ja", []), f"{unit_path}/ja"),
                }
            )
        paragraphs.append(
            {
                "id": paragraph.get("id", ""),
                "source_en": paragraph.get("source_en", ""),
                "units": units,
            }
        )
    return {"chunk_id": chunk.get("chunk_id", ""), "paragraphs": paragraphs}


def resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("/"):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise ValueError(f"{path}: path enters non-container")
    return current


def apply_span_edits(data: dict[str, Any], edits: list[Any]) -> int:
    changed = 0
    for edit_index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise ValueError(f"edits[{edit_index}]: must be an object")
        path = str(edit.get("path", "")).strip()
        role = str(edit.get("g", "")).strip().lower()
        if role not in GRAMMAR_ROLES:
            raise ValueError(f"edits[{edit_index}]: unsupported role {role!r}")
        target = resolve_path(data, path)
        if not isinstance(target, list):
            raise ValueError(f"edits[{edit_index}]: path must point to a token list")
        if "index" in edit:
            start = int(edit["index"])
            end = start + 1
        else:
            start = int(edit.get("start", 0))
            end = int(edit.get("end", start))
        if start < 0 or end < start or end > len(target):
            raise ValueError(f"edits[{edit_index}]: invalid span {start}:{end} for {path}")
        expected = edit.get("text")
        if expected is not None:
            actual = token_text(target[start:end])
            if str(expected) != actual:
                raise ValueError(f"edits[{edit_index}]: text mismatch at {path}[{start}:{end}]")
        for token in target[start:end]:
            if not isinstance(token, dict):
                continue
            if token.get("g") != role:
                token["g"] = role
                changed += 1
    return changed


def claim_chunk(claim_dir: Path, chunk_id: str, worker_id: str, ttl_seconds: int) -> bool:
    claim_path = claim_dir / chunk_id
    now = time.time()
    try:
        claim_path.mkdir(parents=True)
    except FileExistsError:
        owner_alive = False
        try:
            owner = json.loads((claim_path / "owner.json").read_text(encoding="utf-8"))
            owner_pid = int(owner.get("pid", 0))
            if owner_pid > 0:
                os.kill(owner_pid, 0)
                owner_alive = True
        except (FileNotFoundError, json.JSONDecodeError, ValueError, ProcessLookupError):
            owner_alive = False
        except PermissionError:
            owner_alive = True
        if owner_alive:
            try:
                age = now - claim_path.stat().st_mtime
            except FileNotFoundError:
                return False
            if ttl_seconds <= 0 or age <= ttl_seconds:
                return False
        shutil.rmtree(claim_path, ignore_errors=True)
        try:
            claim_path.mkdir(parents=True)
        except FileExistsError:
            return False
    (claim_path / "owner.json").write_text(
        json.dumps({"worker_id": worker_id, "pid": os.getpid(), "claimed_at": now}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def release_claim(claim_dir: Path, chunk_id: str) -> None:
    shutil.rmtree(claim_dir / chunk_id, ignore_errors=True)


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious role edit set failed validation. Fix these exact issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:80]
        )
    roles = ", ".join(sorted(GRAMMAR_ROLES))
    compact_view = json.dumps(role_view(chunk), ensure_ascii=False, separators=(",", ":"))
    return textwrap.dedent(
        f"""
        You are adding grammar-color roles to an existing trilingual English/Chinese/Japanese interlinear chunk.

        The text, translations, token boundaries, pinyin, and furigana are already fixed. Do not rewrite text. Return only JSON span edits that set token field "g".

        Return exactly one JSON object, no Markdown fences, no explanation:
        {{
          "chunk_id": "{chunk.get('chunk_id', '')}",
          "prompt_version": "{PROMPT_VERSION}",
          "edits": [
            {{"path": "paragraphs/0/units/0/en", "start": 0, "end": 3, "text": "optional exact joined token text", "g": "subject"}}
          ]
        }}

        Roles allowed: {roles}

        Requirements:
        - Assign roles to most content tokens in en, zh, and ja.
        - Make the same major semantic component roughly the same color across languages.
        - Prefer sentence-level visual readability over exact grammar theory.
        - Use subject/topic for the actor or discourse focus; predicate for verbs and verbal/adjectival predicates; object for affected things; attributive for modifiers inside noun phrases; adverbial for time/place/manner/condition phrases; complement for result/direction/degree complements; function only for punctuation, conjunction-only words, particles that cannot inherit a phrase role, or purely grammatical fillers.
        - Japanese particles attached to a phrase should usually share that phrase role. Example: object phrase + を is object; subject phrase + は/が is subject/topic; place/time + に/で is adverbial.
        - Chinese 的/地/得 and aspect particles may inherit the phrase role when that keeps the visual component together.
        - Do not use aliases such as zhu/wei/bin/ding/zhuang/bu. Use English roles only.
        - Use compact span edits. A span is half-open: start inclusive, end exclusive.
        - Do not output the full chunk.
        {error_block}

        Current token view:
        {compact_view}
        """
    ).strip()


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"prompt_version": PROMPT_VERSION, "chunks": {}}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_manifest(manifest_path: Path, start_index: int, end_index: int | None) -> list[tuple[int, str]]:
    manifest = load_json(manifest_path)
    selected: list[tuple[int, str]] = []
    for index, item in enumerate(manifest.get("chunks", []), start=1):
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        selected.append((index, item["chunk_id"]))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--state-json", default="")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--idle-sleep-seconds", type=int, default=60)
    parser.add_argument("--after-chunk-command", default="")
    args = parser.parse_args()

    cwd = Path.cwd()
    manifest_path = Path(args.manifest)
    chunk_dir = Path(args.chunk_dir)
    work_dir = Path(args.work_dir)
    claim_dir = work_dir / "claims"
    done_dir = work_dir / "done"
    failed_dir = work_dir / "failed"
    status_dir = work_dir / "status"
    state_path = Path(args.state_json) if args.state_json else work_dir / "state.json"
    for path in (work_dir, claim_dir, done_dir, failed_dir, status_dir):
        path.mkdir(parents=True, exist_ok=True)

    state = load_state(state_path)
    state["prompt_version"] = PROMPT_VERSION
    state.setdefault("chunks", {})
    source_chunks = {chunk["chunk_id"]: chunk for chunk in load_chunks(Path(args.chunks_jsonl))}

    completed = 0
    while True:
        selected = iter_manifest(manifest_path, args.start_index, args.end_index)
        claimed: tuple[int, str, Path] | None = None
        for manifest_index, chunk_id in selected:
            chunk_path = chunk_dir / f"{chunk_id}.json"
            if not chunk_path.exists():
                continue
            if (failed_dir / f"{chunk_id}.json").exists() and not args.force:
                continue
            try:
                data = load_json(chunk_path)
            except Exception:
                continue
            input_sha = json_sha(data)
            chunk_state = state["chunks"].get(chunk_id, {})
            if not args.force and chunk_state.get("prompt_version") == PROMPT_VERSION and chunk_state.get("input_sha") == input_sha:
                continue
            if not args.force and enough_roles(data):
                state["chunks"][chunk_id] = {
                    "prompt_version": PROMPT_VERSION,
                    "input_sha": input_sha,
                    "edit_count": 0,
                    "skipped_reason": "already_has_roles",
                    "manifest_index": manifest_index,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                write_state(state_path, state)
                continue
            if claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
                claimed = (manifest_index, chunk_id, chunk_path)
                break

        if claimed is None:
            print(f"{args.worker_id}: no available grammar chunks; completed={completed}", flush=True)
            if args.watch:
                time.sleep(args.idle_sleep_seconds)
                continue
            return 0

        manifest_index, chunk_id, chunk_path = claimed
        errors: list[str] | None = None
        try:
            data = load_json(chunk_path)
            strip_roles(data)
            source = source_chunks[chunk_id]
            base_errors = validate_chunk(source, data)
            if base_errors:
                raise ValueError("; ".join(base_errors[:60]))
            input_sha = json_sha(data)
            accepted = False
            for attempt in range(1, args.retries + 2):
                prompt = prompt_for_chunk(data, errors)
                prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                log_path = work_dir / "logs" / f"{chunk_id}.log"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")
                print(f"{args.worker_id}: trilingual grammar {chunk_id} attempt {attempt}", flush=True)
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
                    edit_count = apply_span_edits(candidate, edits)
                    validation_errors = validate_chunk(source, candidate)
                    if validation_errors:
                        raise ValueError("; ".join(validation_errors[:80]))
                    content, any_role, colored_role = role_counts(candidate)
                    if content and any_role / content < 0.72:
                        raise ValueError(f"role coverage too low: {any_role}/{content}")
                    if content and colored_role / content < 0.48:
                        raise ValueError(f"colored role coverage too low: {colored_role}/{content}")
                except Exception as exc:
                    if mentions_usage_limit(str(exc)):
                        (status_dir / f"{chunk_id}.json").write_text(
                            json.dumps({"status": "usage_limit", "worker_id": args.worker_id, "attempt": attempt}, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        print(f"{args.worker_id}: usage limit detected; stopping", flush=True)
                        return 86
                    errors = [str(exc)]
                    print(f"{args.worker_id}: grammar failed {chunk_id}: {errors[0]}", flush=True)
                    continue

                output_sha = json_sha(candidate)
                write_json_atomic(chunk_path, candidate)
                state["chunks"][chunk_id] = {
                    "prompt_version": PROMPT_VERSION,
                    "input_sha": output_sha,
                    "base_sha": input_sha,
                    "edit_count": edit_count,
                    "content_tokens": content,
                    "role_tokens": any_role,
                    "colored_role_tokens": colored_role,
                    "manifest_index": manifest_index,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                write_state(state_path, state)
                (done_dir / f"{chunk_id}.json").write_text(json.dumps(state["chunks"][chunk_id], indent=2) + "\n", encoding="utf-8")
                (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)
                print(f"{args.worker_id}: grammar accepted {chunk_id}: edits={edit_count} roles={any_role}/{content}", flush=True)
                completed += 1
                accepted = True
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
            if not accepted:
                (failed_dir / f"{chunk_id}.json").write_text(
                    json.dumps(
                        {
                            "status": "failed",
                            "worker_id": args.worker_id,
                            "errors": errors or [],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        except Exception as exc:
            (failed_dir / f"{chunk_id}.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "worker_id": args.worker_id,
                        "errors": [str(exc)],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"{args.worker_id}: grammar worker exception {chunk_id}: {exc}", flush=True)
        finally:
            release_claim(claim_dir, chunk_id)

        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: max chunks reached ({args.max_chunks})", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
