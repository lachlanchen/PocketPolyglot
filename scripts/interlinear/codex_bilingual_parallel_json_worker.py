#!/usr/bin/env python3
"""Generate bilingual chunk JSON candidates in parallel-safe isolated folders."""

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
from codex_bilingual_chunk_worker import prompt_for_chunk, validate_chunk
from normalize_grammar_roles import cleanup_components, normalize_node, normalize_ruby_token_shapes, normalize_source_artifacts
from reference_windows import expand_adjacent_jp_references


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}


def valid_existing(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
    except Exception:
        return False
    normalize_node(data)
    normalize_source_artifacts(data)
    normalize_ruby_token_shapes(data)
    cleanup_components(data)
    return not validate_chunk(source, data)


def claim_chunk(claim_dir: Path, chunk_id: str, worker_id: str, ttl_seconds: int) -> bool:
    claim_path = claim_dir / chunk_id
    now = time.time()
    ownerless_grace_seconds = min(30, ttl_seconds) if ttl_seconds > 0 else 30

    def claim_age_seconds() -> float | None:
        try:
            return now - claim_path.stat().st_mtime
        except FileNotFoundError:
            return None

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
        except FileNotFoundError:
            age = claim_age_seconds()
            if age is None or age < ownerless_grace_seconds:
                return False
            owner_alive = False
        except (json.JSONDecodeError, ValueError):
            age = claim_age_seconds()
            if age is None or age < ownerless_grace_seconds:
                return False
            owner_alive = False
        except ProcessLookupError:
            owner_alive = False
        except PermissionError:
            owner_alive = True

        if not owner_alive:
            shutil.rmtree(claim_path, ignore_errors=True)
            try:
                claim_path.mkdir(parents=True)
            except FileExistsError:
                return False
        elif ttl_seconds > 0:
            try:
                age = now - claim_path.stat().st_mtime
            except FileNotFoundError:
                return False
            if age > ttl_seconds:
                shutil.rmtree(claim_path, ignore_errors=True)
                try:
                    claim_path.mkdir(parents=True)
                except FileExistsError:
                    return False
            else:
                return False
        else:
            return False
    (claim_path / "owner.json").write_text(
        json.dumps({"worker_id": worker_id, "pid": os.getpid(), "claimed_at": now}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def release_claim(claim_dir: Path, chunk_id: str) -> None:
    shutil.rmtree(claim_dir / chunk_id, ignore_errors=True)


def iter_selected(chunks: list[dict[str, Any]], start_index: int, end_index: int | None) -> list[tuple[int, dict[str, Any]]]:
    selected: list[tuple[int, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks, start=1):
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        selected.append((index, chunk))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="xhigh")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0, help="0 means keep claiming until no tasks remain")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--retry-failed", action="store_true", help="retry chunks with existing failed markers")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = expand_adjacent_jp_references(load_chunks(Path(args.chunks_jsonl)))
    canonical_dir = Path(args.canonical_dir)
    candidate_dir = Path(args.candidate_dir)
    work_dir = Path(args.work_dir)
    claim_dir = candidate_dir / "claims"
    accepted_dir = candidate_dir / "accepted"
    rejected_dir = candidate_dir / "rejected"
    failed_dir = candidate_dir / "failed"
    status_dir = candidate_dir / "status"
    for path in (claim_dir, accepted_dir, rejected_dir, failed_dir, status_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    while True:
        claimed: tuple[int, dict[str, Any]] | None = None
        for item in iter_selected(chunks, args.start_index, args.end_index):
            index, chunk = item
            chunk_id = chunk["chunk_id"]
            canonical_path = canonical_dir / f"{chunk_id}.json"
            candidate_path = accepted_dir / f"{chunk_id}.json"
            if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                continue
            if not args.retry_failed and (failed_dir / f"{chunk_id}.json").exists():
                continue
            if claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
                if args.retry_failed:
                    (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)
                claimed = (index, chunk)
                break
        if claimed is None:
            print(f"{args.worker_id}: no claimable chunks; accepted={completed} failed={failed}")
            return 0

        index, chunk = claimed
        chunk_id = chunk["chunk_id"]
        errors: list[str] | None = None
        try:
            for attempt in range(1, args.retries + 2):
                if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                    print(f"{args.worker_id}: {chunk_id} resolved externally; skipping remaining retries", flush=True)
                    completed += 1
                    break
                prompt = prompt_for_chunk(chunk, errors)
                prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                log_path = work_dir / "logs" / f"{chunk_id}.log"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")

                print(f"{args.worker_id}: codex bilingual {chunk_id} attempt {attempt}", flush=True)
                result: dict[str, Any] | None = None
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
                    result = extract_json(message_path.read_text(encoding="utf-8"))
                    normalize_node(result)
                    normalize_source_artifacts(result)
                    normalize_ruby_token_shapes(result)
                    cleanup_components(result)
                    errors = validate_chunk(chunk, result)
                except Exception as exc:
                    if mentions_usage_limit(str(exc)):
                        write_json(
                            status_dir / f"{chunk_id}.json",
                            status_record("usage_limit", worker_id=args.worker_id, attempt=attempt),
                        )
                        print(f"{args.worker_id}: usage limit detected; stopping worker", flush=True)
                        return 86
                    errors = [f"codex, parse, normalize, or validate step failed: {exc}"]

                if errors:
                    print(f"{args.worker_id}: validation failed {chunk_id}: {'; '.join(errors[:20])}", flush=True)
                    reject_path = rejected_dir / f"{chunk_id}.{args.worker_id}.attempt{attempt}.json"
                    if result is not None:
                        write_json(reject_path, result)
                    else:
                        reject_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
                    write_json(
                        status_dir / f"{chunk_id}.json",
                        status_record(
                            "attempt_failed",
                            worker_id=args.worker_id,
                            attempt=attempt,
                            errors=errors[:80],
                        ),
                    )
                    continue

                final_path = accepted_dir / f"{chunk_id}.json"
                tmp_path = final_path.with_suffix(f".{args.worker_id}.tmp")
                tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp_path.replace(final_path)
                write_json(
                    status_dir / f"{chunk_id}.json",
                    status_record("accepted", worker_id=args.worker_id, attempt=attempt),
                )
                print(f"{args.worker_id}: accepted candidate {chunk_id}", flush=True)
                completed += 1
                break
            else:
                write_json(
                    failed_dir / f"{chunk_id}.json",
                    status_record(
                        "failed",
                        worker_id=args.worker_id,
                        attempts=args.retries + 1,
                        errors=(errors or ["unknown failure"])[:80],
                    ),
                )
                print(f"{args.worker_id}: marked failed {chunk_id}; continuing", flush=True)
                failed += 1
        except Exception as exc:
            write_json(
                failed_dir / f"{chunk_id}.json",
                status_record("failed", worker_id=args.worker_id, errors=[f"worker exception: {exc}"]),
            )
            print(f"{args.worker_id}: worker exception on {chunk_id}: {exc}; continuing", flush=True)
            failed += 1
        finally:
            release_claim(claim_dir, chunk_id)

        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: reached max_chunks={args.max_chunks}; failed={failed}")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
