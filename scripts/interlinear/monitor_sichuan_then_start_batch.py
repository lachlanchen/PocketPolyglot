#!/usr/bin/env python3
"""Wait for Sichuan Folk Stories to finish, then start the prepared book queue."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CURRENT_BOOK = "sichuan-folk-stories-vol1"
DEFAULT_QUEUE = [
    "the-old-capital",
    "izu-no-odori",
    "genji-modern",
    "kojiki",
    "woman-in-the-dunes",
    "chumon-no-ooi-ryoriten",
    "ginga-tetsudo",
]
RAW_ONLY_COMPLETE_BOOKS = {"kokoro"}


@dataclass(frozen=True)
class BookStart:
    book_id: str
    session: str
    command: list[str]
    monitor_start_command: str
    compile_command: str
    no_reviewed_stage: bool = False


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


def parse_report(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def report_progress(book_id: str, chunk_dir: Path) -> dict[str, str]:
    manifest = ROOT / "books" / book_id / "work" / "bilingual" / "chunks" / "manifest.json"
    if not manifest.exists():
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "error": f"missing {manifest}"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_interlinear_progress.py",
            "--manifest",
            str(manifest.relative_to(ROOT)),
            "--chunk-dir",
            str(chunk_dir.relative_to(ROOT)),
        ],
        quiet=True,
    )
    data = parse_report(proc.stdout)
    if proc.returncode:
        data["error"] = proc.stdout.strip()
    return data


def is_complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in ("", "0", None)
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def reviewed_dir(book_id: str) -> Path:
    return ROOT / "books" / book_id / "work" / "bilingual" / "reviewed" / "chunks"


def raw_dir(book_id: str) -> Path:
    return ROOT / "books" / book_id / "work" / "bilingual" / "interlinear" / "chunks"


def book_status(book_id: str) -> tuple[bool, str, dict[str, str]]:
    if book_id in RAW_ONLY_COMPLETE_BOOKS:
        raw = raw_dir(book_id)
        if raw.exists():
            report = report_progress(book_id, raw)
            if is_complete(report):
                return True, "raw", report

    reviewed = reviewed_dir(book_id)
    if reviewed.exists():
        report = report_progress(book_id, reviewed)
        if is_complete(report):
            return True, "reviewed", report
        return False, "reviewed", report

    report = report_progress(book_id, reviewed)
    return False, "reviewed", report


def current_complete(book_id: str) -> tuple[bool, dict[str, str]]:
    report = report_progress(book_id, reviewed_dir(book_id))
    return is_complete(report), report


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def shell_join_env(env_pairs: dict[str, str], command: str) -> str:
    prefix = " ".join(f"{key}={value}" for key, value in env_pairs.items())
    return f"{prefix} {command}" if prefix else command


def build_start(book_id: str, args: argparse.Namespace) -> BookStart | None:
    common_env = {
        "WORKERS": str(args.workers),
        "REVIEW_WORKERS": str(args.review_workers),
        "MODEL": args.model,
        "REASONING": args.reasoning,
    }
    session = f"zhjpbook-{book_id}-json"

    plan_path = ROOT / "books" / book_id / "book-plan.json"
    if plan_path.exists():
        plan = load_json(plan_path)
        if not plan.get("launchable", False):
            print(f"skip_not_launchable={book_id}", flush=True)
            return None
        command = [
            "bash",
            "scripts/interlinear/start_prepared_book_parallel_json_tmux.sh",
            book_id,
            session,
        ]
        monitor_start = shell_join_env(
            common_env,
            f"bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh {book_id} {session}",
        )
        return BookStart(
            book_id=book_id,
            session=session,
            command=command,
            monitor_start_command=monitor_start,
            compile_command=f"bash scripts/interlinear/compile_prepared_book_both_previews.sh {book_id}",
        )

    if book_id == "snow-country":
        command = ["bash", "scripts/interlinear/start_snow_country_parallel_json_tmux.sh", session]
        monitor_start = shell_join_env(
            {**common_env, "ALLOW_WHILE_KOKORO": "1"},
            f"bash scripts/interlinear/start_snow_country_parallel_json_tmux.sh {session}",
        )
        return BookStart(
            book_id=book_id,
            session=session,
            command=command,
            monitor_start_command=monitor_start,
            compile_command="bash scripts/interlinear/compile_snow_country_both_previews.sh",
        )

    if book_id == "no-longer-human":
        command = ["bash", "scripts/interlinear/start_no_longer_human_parallel_json_tmux.sh", session]
        monitor_start = shell_join_env(
            common_env,
            f"bash scripts/interlinear/start_no_longer_human_parallel_json_tmux.sh {session}",
        )
        return BookStart(
            book_id=book_id,
            session=session,
            command=command,
            monitor_start_command=monitor_start,
            compile_command="bash scripts/interlinear/compile_no_longer_human_both_previews.sh",
        )

    if book_id == "kokoro":
        command = ["bash", "scripts/interlinear/start_kokoro_parallel_json_tmux.sh", session]
        monitor_start = shell_join_env(
            common_env,
            f"bash scripts/interlinear/start_kokoro_parallel_json_tmux.sh {session}",
        )
        return BookStart(
            book_id=book_id,
            session=session,
            command=command,
            monitor_start_command=monitor_start,
            compile_command="bash scripts/interlinear/review_compile_kokoro_merged.sh",
            no_reviewed_stage=True,
        )

    print(f"skip_no_start_rule={book_id}", flush=True)
    return None


def active_queue_sessions(queue: list[str]) -> list[str]:
    sessions: list[str] = []
    for book_id in queue:
        candidates = [f"zhjpbook-{book_id}-json"]
        if book_id == "kokoro":
            candidates.append("zhjpbook-parallel-json")
        sessions.extend(session for session in candidates if tmux_active(session))
    return sessions


def start_monitor(start: BookStart, args: argparse.Namespace, dry_run: bool) -> None:
    env = os.environ.copy()
    env.update(
        {
            "BOOK_ID": start.book_id,
            "WORKER_SESSION": start.session,
            "REVIEW_SESSION": start.session,
            "MONITOR_SESSION": f"zhjpbook-{start.book_id}-monitor",
            "INTERVAL_SECONDS": str(args.child_monitor_interval_seconds),
            "STALL_SECONDS": str(args.child_stall_seconds),
            "START_COMMAND": start.monitor_start_command,
            "COMPILE_COMMAND": start.compile_command,
        }
    )
    if start.no_reviewed_stage:
        env["REVIEWED_STAGE"] = "0"
    cmd = ["bash", "scripts/interlinear/start_interlinear_monitor_tmux.sh", start.book_id]
    if dry_run:
        print("dry_run_monitor=" + " ".join(cmd), flush=True)
        return
    proc = run(cmd, env=env)
    print(proc.stdout, end="")
    if proc.returncode:
        raise RuntimeError(f"monitor start failed for {start.book_id}: {proc.returncode}")


def start_book(start: BookStart, args: argparse.Namespace) -> bool:
    if tmux_active(start.session):
        print(f"skip_active_session={start.session}", flush=True)
        return False

    env = os.environ.copy()
    env.update(
        {
            "WORKERS": str(args.workers),
            "REVIEW_WORKERS": str(args.review_workers),
            "MODEL": args.model,
            "REASONING": args.reasoning,
        }
    )
    if start.book_id == "snow-country":
        env["ALLOW_WHILE_KOKORO"] = "1"

    if args.dry_run:
        print("dry_run_start=" + " ".join(start.command), flush=True)
        start_monitor(start, args, dry_run=True)
        return True

    proc = run(start.command, env=env)
    print(proc.stdout, end="")
    if proc.returncode:
        print(f"start_failed={start.book_id} returncode={proc.returncode}", flush=True)
        return False
    start_monitor(start, args, dry_run=False)
    return True


def start_queue(args: argparse.Namespace) -> tuple[int, int, int]:
    started = 0
    skipped_complete = 0
    pending = 0
    for book_id in args.book_id:
        complete, stage, report = book_status(book_id)
        total = report.get("manifest_chunks", "0")
        valid = report.get("valid_chunks", "0")
        if complete:
            skipped_complete += 1
            print(f"skip_complete={book_id} stage={stage} progress={valid}/{total}", flush=True)
            continue

        active = active_queue_sessions(args.book_id)
        if args.max_active_books and len(active) >= args.max_active_books:
            pending += 1
            print(
                f"defer_active_limit={book_id} active={len(active)}/{args.max_active_books} sessions={','.join(active)}",
                flush=True,
            )
            continue

        start = build_start(book_id, args)
        if start is None:
            pending += 1
            continue
        if start_book(start, args):
            started += 1
        else:
            pending += 1
    return started, skipped_complete, pending


def write_state(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    state_path = ROOT / "books" / args.current_book_id / "work" / "monitor" / "sichuan-handoff-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-book-id", default=CURRENT_BOOK)
    parser.add_argument("--book-id", action="append", default=[], help="queued book id; repeatable")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "10")))
    parser.add_argument("--review-workers", type=int, default=int(os.environ.get("REVIEW_WORKERS", "6")))
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning", default=os.environ.get("REASONING", "medium"))
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("INTERVAL_SECONDS", "1800")))
    parser.add_argument("--max-active-books", type=int, default=int(os.environ.get("MAX_ACTIVE_BOOKS", "0")))
    parser.add_argument("--child-monitor-interval-seconds", type=int, default=1800)
    parser.add_argument("--child-stall-seconds", type=int, default=7200)
    parser.add_argument("--once", action="store_true", help="check once and exit")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.book_id:
        args.book_id = list(DEFAULT_QUEUE)

    while True:
        complete, report = current_complete(args.current_book_id)
        total = report.get("manifest_chunks", "0")
        valid = report.get("valid_chunks", "0")
        first_missing = report.get("first_missing", "")
        timestamp = datetime.now(timezone.utc).isoformat()
        print(
            f"timestamp={timestamp} current={args.current_book_id} reviewed={valid}/{total} "
            f"complete={int(complete)} first_missing={first_missing}",
            flush=True,
        )
        write_state(
            args,
            {
                "timestamp": timestamp,
                "current_book_id": args.current_book_id,
                "current_report": report,
                "queue": args.book_id,
                "complete": complete,
            },
        )

        if complete:
            started, skipped_complete, pending = start_queue(args)
            print(
                f"handoff_result started={started} skipped_complete={skipped_complete} pending={pending}",
                flush=True,
            )
            if pending == 0 or args.max_active_books == 0:
                return 0 if pending == 0 else 1

        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
