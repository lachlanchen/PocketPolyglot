#!/usr/bin/env python3
"""Run build-pocket-polished one book at a time with parallel chunk workers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pocket_polished_resource_gate import AdaptiveGovernor
from pocket_polished_common import OUTPUT_ROOT, ROOT, read_json, read_jsonl, validate_chunk_output, write_json


def progress(book_id: str) -> tuple[int, int]:
    book_root = OUTPUT_ROOT / book_id
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    valid = 0
    for task in tasks:
        path = book_root / "json" / f"{task['chunk_id']}.json"
        try:
            result = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not validate_chunk_output(task, result):
            valid += 1
    return valid, len(tasks)


def detailed_progress(book_id: str) -> dict[str, int | float | str | bool]:
    book_root = OUTPUT_ROOT / book_id
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    cached_ids = {
        path.stem
        for path in (book_root / "work/accepted-segments").glob("*.json")
    }
    cached_hashes: set[str] = set()
    for path in (book_root / "work/accepted-segments").glob("*.json"):
        try:
            payload = read_json(path)
            source_hash = payload.get("source_sha256")
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            continue
        if isinstance(source_hash, str):
            cached_hashes.add(source_hash)
    valid_chunks = 0
    invalid_chunks = 0
    accepted_segments = 0
    total_segments = sum(len(task.get("segments", [])) for task in tasks)
    for task in tasks:
        path = book_root / "json" / f"{task['chunk_id']}.json"
        errors: list[str] = ["missing"]
        if path.exists():
            try:
                errors = validate_chunk_output(task, read_json(path))
            except (OSError, ValueError, json.JSONDecodeError):
                errors = ["unreadable"]
        if not errors:
            valid_chunks += 1
            accepted_segments += len(task.get("segments", []))
        else:
            if path.exists():
                invalid_chunks += 1
            accepted_segments += sum(
                source.get("segment_id") in cached_ids
                or source.get("source_sha256") in cached_hashes
                for source in task.get("segments", [])
            )
    failed_chunks = sum(
        1 for _path in (book_root / "work/failed").glob("*.json")
    )
    fraction = accepted_segments / total_segments if total_segments else 0.0
    status_path = book_root / "status.json"
    assembled = False
    if status_path.exists():
        try:
            assembled = read_json(status_path).get("status") == "complete"
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return {
        "status": "complete" if assembled else "running" if accepted_segments else "waiting",
        "valid_chunks": valid_chunks,
        "total_chunks": len(tasks),
        "invalid_chunks": invalid_chunks,
        "failed_chunks": failed_chunks,
        "accepted_segments": accepted_segments,
        "total_segments": total_segments,
        "progress": round(fraction, 6),
        "assembled": assembled,
    }


def update_overall_progress(state: dict) -> None:
    rows = [row for row in state.get("books", {}).values() if isinstance(row, dict)]
    accepted = sum(int(row.get("accepted_segments", 0) or 0) for row in rows)
    total = sum(int(row.get("total_segments", 0) or 0) for row in rows)
    state["accepted_segments"] = accepted
    state["total_segments"] = total
    state["progress"] = round(accepted / total, 6) if total else 0.0


def run_workers(
    book_id: str,
    *,
    workers: int,
    model: str,
    reasoning: str,
    retries: int,
    review_retries: int,
    timeout: int,
    backoff: int,
    status_path: Path,
    state: dict,
    governor: AdaptiveGovernor,
    telemetry_interval: int,
) -> bool:
    log_root = OUTPUT_ROOT / book_id / "work/worker-logs"
    log_root.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[subprocess.Popen, object]] = []
    environment = os.environ.copy()
    environment["POCKET_POLYGLOT_GATE_STATE"] = str(governor.state_path)
    governor.sample()
    for worker_index in range(1, workers + 1):
        log_path = log_root / f"worker-{worker_index:02d}.log"
        handle = log_path.open("a", encoding="utf-8")
        cmd = [
            sys.executable,
            "-u",
            "scripts/books/codex_pocket_polish_worker.py",
            book_id,
            "--worker-index",
            str(worker_index),
            "--workers",
            str(workers),
            "--model",
            model,
            "--reasoning",
            reasoning,
            "--retries",
            str(retries),
            "--review-retries",
            str(review_retries),
            "--timeout",
            str(timeout),
            "--backoff",
            str(backoff),
        ]
        processes.append(
            (
                subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    env=environment,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                ),
                handle,
            )
        )
    last_report = 0.0
    while any(process.poll() is None for process, _handle in processes):
        runtime = governor.sample()
        state["runtime"] = runtime
        current = detailed_progress(book_id)
        current["status"] = "running"
        current["active_workers"] = sum(
            process.poll() is None for process, _handle in processes
        )
        state["books"][book_id] = current
        update_overall_progress(state)
        write_queue_status(status_path, state)
        now = time.monotonic()
        if now - last_report >= 30:
            print(
                f"{book_id}: chunks={current['valid_chunks']}/{current['total_chunks']} "
                f"segments={current['accepted_segments']}/{current['total_segments']} "
                f"codex={runtime['active_codex_calls']}/{runtime['desired_concurrency']} "
                f"network={runtime['network_mbps']:.2f}Mbps state={runtime['network_state']}",
                flush=True,
            )
            last_report = now
        time.sleep(max(2, telemetry_interval))
    return_codes: list[int] = []
    for process, handle in processes:
        return_codes.append(process.wait())
        handle.close()
    complete, total = progress(book_id)
    print(f"{book_id}: chunks={complete}/{total} worker_rc={return_codes}", flush=True)
    return complete == total


def write_queue_status(path: Path, payload: dict) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, payload)


def sync_to_nutstore(book_id: str, share_root: Path | None) -> bool:
    cmd = [
        sys.executable,
        "-u",
        "scripts/books/sync_build_pocket_polished_to_nutstore.py",
        book_id,
    ]
    if share_root is not None:
        cmd.extend(("--share-root", str(share_root)))
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=OUTPUT_ROOT / "tasks/queue.json")
    parser.add_argument("--status", type=Path, default=OUTPUT_ROOT / "status.json")
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--start-book", default="")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning", default="low")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--review-retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--backoff", type=int, default=600)
    parser.add_argument("--max-books", type=int, default=0)
    parser.add_argument("--retry-passes", type=int, default=1)
    parser.add_argument(
        "--adaptive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Dynamically gate simultaneous Codex calls when host or network pressure persists.",
    )
    parser.add_argument("--network-limit-mbps", type=float, default=100.0)
    parser.add_argument("--load-limit-ratio", type=float, default=1.25)
    parser.add_argument("--memory-floor-mb", type=float, default=2048.0)
    parser.add_argument("--telemetry-interval", type=int, default=5)
    parser.add_argument("--no-nutstore-sync", action="store_true")
    parser.add_argument("--nutstore-share-root", type=Path)
    parser.add_argument("--no-auto-cover", action="store_true")
    parser.add_argument("--cover-reasoning", default="low", choices=["low", "medium", "high", "xhigh"])
    args = parser.parse_args()

    queue = read_json(args.queue)
    selected = set(args.book_id)
    books = [item for item in queue["books"] if not selected or item["book_id"] in selected]
    if selected:
        missing = sorted(selected - {item["book_id"] for item in books})
        if missing:
            parser.error(
                "selected book IDs are not present in the prepared queue: "
                + ", ".join(missing)
            )
    if args.start_book:
        start = next((index for index, item in enumerate(books) if item["book_id"] == args.start_book), None)
        if start is None:
            parser.error(f"--start-book not found: {args.start_book}")
        books = books[start:]
    if args.max_books:
        books = books[: args.max_books]

    state = {
        "schema_version": 2,
        "queue": str(args.queue),
        "status": "running",
        "model": args.model,
        "reasoning": args.reasoning,
        "workers": args.workers,
        "book_count": len(books),
        "books": {},
    }
    for item in books:
        state["books"][item["book_id"]] = detailed_progress(item["book_id"])
    update_overall_progress(state)
    gate_state = args.status.parent / "runtime" / f"{args.status.stem}-gate.json"
    governor = AdaptiveGovernor(
        gate_state,
        max_concurrency=args.workers,
        network_limit_mbps=args.network_limit_mbps if args.adaptive else 0,
        load_limit_ratio=args.load_limit_ratio if args.adaptive else 999,
        memory_floor_mb=args.memory_floor_mb if args.adaptive else 0,
    )
    state["runtime"] = governor.sample()
    write_queue_status(args.status, state)
    for index, item in enumerate(books, start=1):
        book_id = item["book_id"]
        prior_status_path = OUTPUT_ROOT / book_id / "status.json"
        if prior_status_path.exists():
            prior = read_json(prior_status_path)
            if prior.get("status") == "complete":
                print(f"[{index}/{len(books)}] {book_id}: already complete", flush=True)
                state["books"][book_id] = detailed_progress(book_id)
                state["books"][book_id]["status"] = "already_complete"
                update_overall_progress(state)
                write_queue_status(args.status, state)
                if not args.no_nutstore_sync and not sync_to_nutstore(book_id, args.nutstore_share_root):
                    state["books"][book_id]["status"] = "sync_blocked"
                    state["status"] = "blocked"
                    write_queue_status(args.status, state)
                    print(f"{book_id}: Nutstore sync blocked", flush=True)
                    return 1
                continue
        print(f"[{index}/{len(books)}] {book_id}: polishing", flush=True)
        state["current_book"] = book_id
        state["books"][book_id] = {"status": "running"}
        write_queue_status(args.status, state)
        complete = False
        previous = progress(book_id)[0]
        for pass_index in range(1, args.retry_passes + 1):
            complete = run_workers(
                book_id,
                workers=args.workers,
                model=args.model,
                reasoning=args.reasoning,
                retries=args.retries,
                review_retries=args.review_retries,
                timeout=args.timeout,
                backoff=args.backoff,
                status_path=args.status,
                state=state,
                governor=governor,
                telemetry_interval=args.telemetry_interval,
            )
            if complete:
                break
            current = progress(book_id)[0]
            print(f"{book_id}: retry_pass={pass_index} progress={current} previous={previous}", flush=True)
            if current == previous and pass_index >= args.retry_passes:
                break
            previous = current
            time.sleep(30)
        if not complete:
            valid, total = progress(book_id)
            state["books"][book_id] = {"status": "blocked_chunks", "valid": valid, "total": total}
            state["books"][book_id].update(detailed_progress(book_id))
            state["books"][book_id]["status"] = "blocked_chunks"
            state["status"] = "blocked"
            update_overall_progress(state)
            write_queue_status(args.status, state)
            print(f"{book_id}: blocked at {valid}/{total}; queue stopped for repair", flush=True)
            return 1

        if not args.no_auto_cover:
            state["books"][book_id]["status"] = "preparing_cover"
            write_queue_status(args.status, state)
            cover_result = subprocess.run(
                [
                    sys.executable,
                    "-u",
                    "scripts/books/ensure_textless_pocket_polished_cover.py",
                    book_id,
                    "--model",
                    args.model,
                    "--reasoning",
                    args.cover_reasoning,
                ],
                cwd=ROOT,
                check=False,
            )
            if cover_result.returncode:
                state["books"][book_id]["status"] = "cover_blocked"
                state["status"] = "blocked"
                write_queue_status(args.status, state)
                print(f"{book_id}: textless cover generation blocked", flush=True)
                return 1

        result = subprocess.run(
            [sys.executable, "-u", "scripts/books/assemble_build_pocket_polished.py", book_id],
            cwd=ROOT,
            check=False,
        )
        status = read_json(OUTPUT_ROOT / book_id / "status.json")
        state["books"][book_id] = status
        state["books"][book_id].update(detailed_progress(book_id))
        state["books"][book_id]["status"] = status.get("status", "unknown")
        update_overall_progress(state)
        write_queue_status(args.status, state)
        if result.returncode or status.get("status") != "complete":
            state["status"] = "blocked"
            write_queue_status(args.status, state)
            print(f"{book_id}: assembly/layout validation blocked; queue stopped for repair", flush=True)
            return 1
        if not args.no_nutstore_sync and not sync_to_nutstore(book_id, args.nutstore_share_root):
            state["books"][book_id]["status"] = "sync_blocked"
            state["status"] = "blocked"
            write_queue_status(args.status, state)
            print(f"{book_id}: Nutstore sync blocked", flush=True)
            return 1
    state.pop("current_book", None)
    state["status"] = "complete"
    state["progress"] = 1.0
    write_queue_status(args.status, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
