#!/usr/bin/env python3
"""Monitor a trilingual book, then start queued trilingual books one by one."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, env: dict[str, str] | None = None, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


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


def load_plan(book_id: str) -> dict[str, Any] | None:
    path = ROOT / "books" / book_id / "book-plan.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def parse_report(text: str) -> dict[str, str]:
    report: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            report[key] = value
    return report


def progress(book_id: str) -> dict[str, str]:
    plan = load_plan(book_id)
    if not plan:
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "error": "missing book-plan.json"}
    manifest = str(plan.get("chunks_manifest") or "")
    chunk_dir = str(plan.get("raw_chunk_dir") or "")
    if not manifest or not chunk_dir:
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "error": "missing manifest/chunk dir in plan"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_trilingual_progress.py",
            "--manifest",
            manifest,
            "--chunk-dir",
            chunk_dir,
        ],
        quiet=True,
    )
    report = parse_report(proc.stdout)
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in ("", "0", None)
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def writer_session(book_id: str) -> str:
    return f"zhjpbook-{book_id}-trilingual"


def finalizer_session(book_id: str) -> str:
    return f"zhjpbook-{book_id}-trilingual-finalize"


def active_sessions(book_ids: list[str]) -> list[str]:
    sessions: list[str] = []
    for book_id in book_ids:
        for session in (writer_session(book_id), finalizer_session(book_id)):
            if tmux_active(session):
                sessions.append(session)
    return sessions


def queue_reports(book_ids: list[str]) -> dict[str, dict[str, str]]:
    return {book_id: progress(book_id) for book_id in book_ids}


def all_complete(reports: dict[str, dict[str, str]]) -> bool:
    return all(complete(report) for report in reports.values())


def start_book(book_id: str, args: argparse.Namespace) -> bool:
    plan = load_plan(book_id)
    if not plan:
        print(f"skip_missing_plan={book_id}", flush=True)
        return False
    if not plan.get("launchable", False):
        print(f"skip_not_launchable={book_id}", flush=True)
        return False
    writer = writer_session(book_id)
    finalizer = finalizer_session(book_id)
    if tmux_active(writer) or tmux_active(finalizer):
        print(f"skip_active={book_id}", flush=True)
        return False

    env = os.environ.copy()
    env.update(
        {
            "WORKERS": str(args.workers),
            "MODEL": args.model,
            "REASONING": args.reasoning,
            "MERGE_INTERVAL": str(args.merge_interval_seconds),
            "COMPILE_INTERVAL_SECONDS": str(args.compile_interval_seconds),
        }
    )
    if args.retry_failed:
        env["RETRY_FAILED"] = "1"

    start_proc = run(["bash", "scripts/interlinear/start_trilingual_book_tmux.sh", book_id, writer], env=env)
    print(start_proc.stdout, end="")
    if start_proc.returncode:
        print(f"start_failed={book_id} returncode={start_proc.returncode}", flush=True)
        return False

    finalize_proc = run(["bash", "scripts/interlinear/start_trilingual_finalize_tmux.sh", book_id, writer, finalizer], env=env)
    print(finalize_proc.stdout, end="")
    if finalize_proc.returncode:
        print(f"finalizer_start_failed={book_id} returncode={finalize_proc.returncode}", flush=True)
    return True


def write_state(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    state_dir = ROOT / "books" / args.current_book_id / "work" / "trilingual" / "queue"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-book-id", required=True)
    parser.add_argument("--book-id", action="append", default=[], help="queued book id; repeatable")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "10")))
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning", default=os.environ.get("REASONING", "high"))
    parser.add_argument("--retry-failed", action="store_true", default=os.environ.get("RETRY_FAILED") == "1")
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("INTERVAL_SECONDS", "1800")))
    parser.add_argument("--merge-interval-seconds", type=int, default=int(os.environ.get("MERGE_INTERVAL", "120")))
    parser.add_argument("--compile-interval-seconds", type=int, default=int(os.environ.get("COMPILE_INTERVAL_SECONDS", "1200")))
    parser.add_argument("--max-active-books", type=int, default=int(os.environ.get("MAX_ACTIVE_BOOKS", "1")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        current_report = progress(args.current_book_id)
        is_current_complete = complete(current_report)
        queued_reports = queue_reports(args.book_id)
        current_active = active_sessions([args.current_book_id])
        active = active_sessions(args.book_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        print(
            f"timestamp={timestamp} current={args.current_book_id} "
            f"progress={current_report.get('valid_chunks','0')}/{current_report.get('manifest_chunks','0')} "
            f"complete={int(is_current_complete)} current_active={len(current_active)} "
            f"active={len(active)} queue={','.join(args.book_id)}",
            flush=True,
        )
        write_state(
            args,
            {
                "timestamp": timestamp,
                "current_book_id": args.current_book_id,
                "current_report": current_report,
                "current_complete": is_current_complete,
                "current_active_sessions": current_active,
                "queue": args.book_id,
                "queue_reports": queued_reports,
                "active_sessions": active,
            },
        )

        if not is_current_complete and not current_active:
            start_book(args.current_book_id, args)

        if is_current_complete and not current_active and not active and all_complete(queued_reports):
            completed = ",".join(args.book_id) or "(none)"
            print(f"queue_complete=1 completed={completed}; exiting", flush=True)
            return 0

        if is_current_complete and not current_active and len(active) < args.max_active_books:
            for book_id in args.book_id:
                report = queued_reports[book_id]
                if complete(report):
                    print(f"skip_complete={book_id}", flush=True)
                    continue
                if start_book(book_id, args):
                    break

        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
