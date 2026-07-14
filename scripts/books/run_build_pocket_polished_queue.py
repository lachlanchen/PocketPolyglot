#!/usr/bin/env python3
"""Run build-pocket-polished one book at a time with parallel chunk workers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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
) -> bool:
    log_root = OUTPUT_ROOT / book_id / "work/worker-logs"
    log_root.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[subprocess.Popen, object]] = []
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
        processes.append((subprocess.Popen(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT), handle))
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
    parser.add_argument("--no-nutstore-sync", action="store_true")
    parser.add_argument("--nutstore-share-root", type=Path)
    args = parser.parse_args()

    queue = read_json(args.queue)
    selected = set(args.book_id)
    books = [item for item in queue["books"] if not selected or item["book_id"] in selected]
    if args.start_book:
        start = next((index for index, item in enumerate(books) if item["book_id"] == args.start_book), None)
        if start is None:
            parser.error(f"--start-book not found: {args.start_book}")
        books = books[start:]
    if args.max_books:
        books = books[: args.max_books]

    state = {
        "schema_version": 1,
        "model": args.model,
        "reasoning": args.reasoning,
        "workers": args.workers,
        "book_count": len(books),
        "books": {},
    }
    for index, item in enumerate(books, start=1):
        book_id = item["book_id"]
        prior_status_path = OUTPUT_ROOT / book_id / "status.json"
        if prior_status_path.exists():
            prior = read_json(prior_status_path)
            if prior.get("status") == "complete":
                print(f"[{index}/{len(books)}] {book_id}: already complete", flush=True)
                state["books"][book_id] = {"status": "already_complete"}
                write_queue_status(args.status, state)
                if not args.no_nutstore_sync and not sync_to_nutstore(book_id, args.nutstore_share_root):
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
            write_queue_status(args.status, state)
            print(f"{book_id}: blocked at {valid}/{total}; queue stopped for repair", flush=True)
            return 1

        result = subprocess.run(
            [sys.executable, "-u", "scripts/books/assemble_build_pocket_polished.py", book_id],
            cwd=ROOT,
            check=False,
        )
        status = read_json(OUTPUT_ROOT / book_id / "status.json")
        state["books"][book_id] = status
        write_queue_status(args.status, state)
        if result.returncode or status.get("status") != "complete":
            print(f"{book_id}: assembly/layout validation blocked; queue stopped for repair", flush=True)
            return 1
        if not args.no_nutstore_sync and not sync_to_nutstore(book_id, args.nutstore_share_root):
            print(f"{book_id}: Nutstore sync blocked", flush=True)
            return 1
    state.pop("current_book", None)
    state["status"] = "complete"
    write_queue_status(args.status, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
