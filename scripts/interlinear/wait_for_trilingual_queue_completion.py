#!/usr/bin/env python3
"""Wait until every book in a trilingual source-plan queue is complete."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_report(manifest: str, chunk_dir: str) -> dict[str, str]:
    proc = subprocess.run(
        [
            "python",
            "scripts/interlinear/report_trilingual_progress.py",
            "--manifest",
            manifest,
            "--chunk-dir",
            chunk_dir,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    report: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            report[key] = value
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def is_complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in ("", "0", None)
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def tmux_active(session: str) -> bool:
    return (
        subprocess.run(
            ["tmux", "has-session", "-t", f"={session}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def load_queue(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        task["book_id"]
        for task in sorted(data.get("tasks", []), key=lambda item: item.get("priority", 999999))
    ]


def book_report(book_id: str) -> dict[str, str]:
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    if not plan_path.exists():
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "stale_chunks": "0", "error": "missing_plan"}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = str(plan.get("chunks_manifest") or "")
    chunk_dir = str(plan.get("raw_chunk_dir") or "")
    if not manifest or not chunk_dir:
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "stale_chunks": "0", "error": "missing_manifest_or_chunk_dir"}
    return run_report(manifest, chunk_dir)


def active_writer_or_finalizer(book_ids: list[str]) -> list[str]:
    active: list[str] = []
    for book_id in book_ids:
        for suffix in ("trilingual", "trilingual-finalize"):
            session = f"zhjpbook-{book_id}-{suffix}"
            if tmux_active(session):
                active.append(session)
    return active


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else ROOT / args.queue
    book_ids = load_queue(queue_path)
    if not book_ids:
        raise SystemExit(f"empty_queue={queue_path}")

    while True:
        reports = {book_id: book_report(book_id) for book_id in book_ids}
        incomplete = [book_id for book_id, report in reports.items() if not is_complete(report)]
        active = active_writer_or_finalizer(book_ids)
        timestamp = datetime.now(timezone.utc).isoformat()
        print(
            f"timestamp={timestamp} queue={queue_path.relative_to(ROOT)} "
            f"complete={len(book_ids) - len(incomplete)}/{len(book_ids)} "
            f"incomplete={','.join(incomplete)} active={','.join(active)}",
            flush=True,
        )
        for book_id in incomplete[:5]:
            report = reports[book_id]
            print(
                f"waiting_book={book_id} "
                f"progress={report.get('valid_chunks','0')}/{report.get('manifest_chunks','0')} "
                f"missing={report.get('missing_chunks','?')} stale={report.get('stale_chunks','?')} "
                f"error={report.get('error','')}",
                flush=True,
            )
        if not incomplete and not active:
            print(f"queue_complete=1 queue={queue_path.relative_to(ROOT)}", flush=True)
            return 0
        if args.once:
            return 1
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
