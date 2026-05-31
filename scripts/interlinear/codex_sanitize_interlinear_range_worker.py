#!/usr/bin/env python3
"""Sanitize existing interlinear chunks in a parallel-safe range."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_chunk_worker import extract_json, load_chunks, mentions_usage_limit, run_codex
from normalize_grammar_roles import cleanup_components, normalize_node, normalize_ruby_token_shapes
from reference_windows import expand_adjacent_jp_references
from review_backfix_interlinear_chunks import json_sha, repair_prompt, review_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}


def claim_chunk(claim_dir: Path, chunk_id: str, worker_id: str, ttl_seconds: int) -> bool:
    claim_path = claim_dir / chunk_id
    now = time.time()
    try:
        claim_path.mkdir(parents=True)
    except FileExistsError:
        if ttl_seconds <= 0:
            return False
        try:
            age = now - claim_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age <= ttl_seconds:
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


def clear_failed(failed_dir: Path, chunk_id: str) -> None:
    (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)


def selected_chunks(
    chunks: list[dict[str, Any]],
    start_index: int,
    end_index: int | None,
) -> list[tuple[int, dict[str, Any]]]:
    selected: list[tuple[int, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks, start=1):
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        selected.append((index, chunk))
    return selected


def reviewed_ok(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
        normalize_node(data)
        normalize_ruby_token_shapes(data)
        cleanup_components(data)
        return not review_chunk(source, data)
    except Exception:
        return False


def choose_current(read_dirs: list[Path], chunk_id: str) -> tuple[Path, dict[str, Any]] | None:
    for directory in read_dirs:
        path = directory / f"{chunk_id}.json"
        if not path.exists():
            continue
        data = load_json(path)
        normalize_node(data)
        normalize_ruby_token_shapes(data)
        cleanup_components(data)
        return path, data
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--read-dir", action="append", default=[], help="existing chunk dirs, in salvage priority order")
    parser.add_argument("--write-dir", action="append", required=True, help="chunk dirs to update with sanitized JSON")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="medium")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = expand_adjacent_jp_references(load_chunks(Path(args.chunks_jsonl)))
    write_dirs = [Path(path) for path in args.write_dir]
    read_dirs = [Path(path) for path in args.read_dir] or write_dirs
    work_dir = Path(args.work_dir)
    claim_dir = work_dir / "claims"
    status_dir = work_dir / "status"
    failed_dir = work_dir / "failed"
    rejected_dir = work_dir / "rejected"
    for path in [work_dir, claim_dir, status_dir, failed_dir, rejected_dir, *write_dirs]:
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    for _index, source in selected_chunks(chunks, args.start_index, args.end_index):
        chunk_id = source["chunk_id"]
        if all(reviewed_ok(directory / f"{chunk_id}.json", source) for directory in write_dirs):
            (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)
            continue
        if not args.retry_failed and (failed_dir / f"{chunk_id}.json").exists():
            continue
        if not claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
            continue
        try:
            chosen = choose_current(read_dirs, chunk_id)
            if chosen is None:
                write_json(
                    failed_dir / f"{chunk_id}.json",
                    status_record("missing_input", worker_id=args.worker_id),
                )
                failed += 1
                continue
            input_path, data = chosen
            issues = review_chunk(source, data)
            if not issues:
                for directory in write_dirs:
                    write_json(directory / f"{chunk_id}.json", data)
                clear_failed(failed_dir, chunk_id)
                write_json(
                    status_dir / f"{chunk_id}.json",
                    status_record("ok", worker_id=args.worker_id, input=str(input_path), input_sha=json_sha(data)),
                )
                print(f"{args.worker_id}: sanitize ok {chunk_id}", flush=True)
                completed += 1
            else:
                print(f"{args.worker_id}: sanitize failed review {chunk_id}: {len(issues)} issue(s)", flush=True)
                previous_issues = issues
                repaired = False
                for attempt in range(1, args.retries + 2):
                    prompt = repair_prompt(source, data, previous_issues)
                    prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                    message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                    log_path = work_dir / "logs" / f"{chunk_id}.log"
                    prompt_path.parent.mkdir(parents=True, exist_ok=True)
                    prompt_path.write_text(prompt, encoding="utf-8")

                    print(f"{args.worker_id}: codex sanitize {chunk_id} attempt {attempt}", flush=True)
                    candidate: dict[str, Any] | None = None
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
                        candidate = extract_json(message_path.read_text(encoding="utf-8"))
                        normalize_node(candidate)
                        normalize_ruby_token_shapes(candidate)
                        cleanup_components(candidate)
                        validation = review_chunk(source, candidate)
                        if validation:
                            raise ValueError("; ".join(validation[:80]))
                    except Exception as exc:
                        if mentions_usage_limit(str(exc)):
                            write_json(
                                status_dir / f"{chunk_id}.json",
                                status_record("usage_limit", worker_id=args.worker_id, attempt=attempt),
                            )
                            print(f"{args.worker_id}: usage limit detected; stopping sanitizer", flush=True)
                            return 86
                        previous_issues = [str(exc)]
                        reject_path = rejected_dir / f"{chunk_id}.{args.worker_id}.attempt{attempt}.json"
                        if candidate is not None:
                            write_json(reject_path, candidate)
                        else:
                            reject_path.write_text(previous_issues[0] + "\n", encoding="utf-8")
                        print(f"{args.worker_id}: sanitize backfix failed {chunk_id}: {previous_issues[0]}", flush=True)
                        continue

                    for directory in write_dirs:
                        write_json(directory / f"{chunk_id}.json", candidate)
                    clear_failed(failed_dir, chunk_id)
                    write_json(
                        status_dir / f"{chunk_id}.json",
                        status_record(
                            "backfixed",
                            worker_id=args.worker_id,
                            input=str(input_path),
                            input_sha=json_sha(candidate),
                            initial_issue_count=len(issues),
                            attempt=attempt,
                        ),
                    )
                    print(f"{args.worker_id}: sanitized {chunk_id}", flush=True)
                    completed += 1
                    repaired = True
                    break
                if not repaired:
                    write_json(
                        failed_dir / f"{chunk_id}.json",
                        status_record(
                            "failed",
                            worker_id=args.worker_id,
                            input=str(input_path),
                            initial_issue_count=len(issues),
                            last_errors=previous_issues[:80],
                        ),
                    )
                    failed += 1
            if args.max_chunks and completed >= args.max_chunks:
                print(f"{args.worker_id}: reached max_chunks={args.max_chunks}; failed={failed}", flush=True)
                return 0
        finally:
            release_claim(claim_dir, chunk_id)

    print(f"{args.worker_id}: sanitizer complete completed={completed} failed={failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
