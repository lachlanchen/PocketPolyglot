#!/usr/bin/env python3
"""Wait for classical quadrilingual completion, then run world-poetry books.

This monitor is intentionally conservative. World-poetry plans are often
source-only first; the monitor stops at the first unprepared poetry book instead
of skipping ahead or inventing chunk manifests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "books" / "_queues" / "world-poetry-after-classics"
DEFAULT_POETRY_BATCH = ROOT / "data" / "source-plan" / "world-poetry-source-batch.json"

DEFAULT_CLASSICS = [
    "lunyu",
    "mengzi",
    "xunzi",
    "mozi",
    "hanfeizi",
    "guiguzi",
    "lushi-chunqiu",
    "sunzi-bingfa",
    "wuzi",
    "sunbin-bingfa",
    "simafa",
    "weiliaozi",
]


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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_plan(book_id: str) -> dict[str, Any] | None:
    path = ROOT / "books" / book_id / "book-plan.json"
    if not path.exists():
        return None
    return load_json(path)


def parse_report(text: str) -> dict[str, str]:
    report: dict[str, str] = {}
    for line in text.splitlines():
        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=(.*?)(?=\s+[A-Za-z_][A-Za-z0-9_]*=|$)", line):
            key = match.group(1).strip()
            value = match.group(2).strip()
            if key:
                report[key] = value
    return report


def path_ready(value: str | None, *, require_file: bool) -> bool:
    if not value:
        return False
    path = ROOT / value
    return path.is_file() if require_file else path.is_dir()


def poetry_ids_from_batch(path: Path) -> list[str]:
    payload = load_json(path)
    ids: list[str] = []
    for task in payload.get("tasks", []):
        book_id = task.get("book_id")
        if isinstance(book_id, str) and book_id:
            ids.append(book_id)
    return ids


def quadrilingual_progress(book_id: str) -> dict[str, str]:
    plan = load_plan(book_id)
    if not plan:
        return {"error": "missing book-plan.json", "valid": "0/0", "missing": "0", "stale": "0"}
    if not path_ready(plan.get("chunks_manifest"), require_file=True) or not path_ready(plan.get("chunks_jsonl"), require_file=True):
        return {"error": "missing quadrilingual manifest or chunks_jsonl", "valid": "0/0", "missing": "0", "stale": "0"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_quadrilingual_progress.py",
            "--manifest",
            str(plan.get("chunks_manifest") or ""),
            "--chunks-jsonl",
            str(plan.get("chunks_jsonl") or ""),
            "--chunk-dir",
            str(plan.get("raw_chunk_dir") or ""),
        ],
        quiet=True,
    )
    report = parse_report(proc.stdout)
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def trilingual_progress(book_id: str) -> dict[str, str]:
    plan = load_plan(book_id)
    if not plan:
        return {"error": "missing book-plan.json", "manifest_chunks": "0", "valid_chunks": "0"}
    manifest = plan.get("chunks_manifest")
    chunk_dir = plan.get("raw_chunk_dir")
    if not path_ready(manifest, require_file=True):
        return {
            "status": "not_chunked",
            "manifest_chunks": "0",
            "valid_chunks": "0",
            "missing_chunks": "0",
            "stale_chunks": "0",
        }
    proc = run(
        [
            "python",
            "scripts/interlinear/report_trilingual_progress.py",
            "--manifest",
            str(manifest or ""),
            "--chunk-dir",
            str(chunk_dir or ""),
        ],
        quiet=True,
    )
    report = parse_report(proc.stdout)
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def quadrilingual_complete(report: dict[str, str]) -> bool:
    valid = str(report.get("valid") or "0/0")
    if "/" not in valid:
        return False
    done, total = valid.split("/", 1)
    return total not in {"", "0"} and done == total and report.get("missing") == "0" and report.get("stale") == "0"


def trilingual_complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in {"", "0", None}
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def quadrilingual_session(book_id: str) -> str:
    return f"zhjpbook-{book_id}-quadrilingual"


def trilingual_session(book_id: str) -> str:
    return f"zhjpbook-{book_id}-trilingual"


def active_classical_sessions(book_ids: list[str]) -> list[str]:
    sessions: list[str] = []
    for session in ("zhjpbook-classics-after-fantasy",):
        if tmux_active(session):
            sessions.append(session)
    for book_id in book_ids:
        session = quadrilingual_session(book_id)
        if tmux_active(session):
            sessions.append(session)
    return sessions


def active_poetry_sessions(book_ids: list[str]) -> list[str]:
    sessions: list[str] = []
    for session in ("zhjpbook-world-poetry-after-classics",):
        if tmux_active(session):
            sessions.append(session)
    for book_id in book_ids:
        for suffix in ("trilingual", "trilingual-finalize", "trilingual-repair", "trilingual-autorepair"):
            session = f"zhjpbook-{book_id}-{suffix}"
            if tmux_active(session):
                sessions.append(session)
    return sessions


def launchability(book_id: str) -> dict[str, Any]:
    plan = load_plan(book_id)
    if not plan:
        return {"launchable": False, "reason": "missing book-plan.json"}
    missing: list[str] = []
    if not plan.get("launchable"):
        missing.append("book-plan launchable=false")
    if not path_ready(plan.get("chunks_jsonl"), require_file=True):
        missing.append("missing chunks_jsonl")
    if not path_ready(plan.get("chunks_manifest"), require_file=True):
        missing.append("missing chunks_manifest")
    if not path_ready(plan.get("raw_chunk_dir"), require_file=False):
        missing.append("missing raw_chunk_dir")
    return {
        "launchable": not missing,
        "reason": "; ".join(missing) if missing else "ready",
        "status": plan.get("status"),
        "task_mode": plan.get("task_mode"),
    }


def start_poetry(book_id: str, args: argparse.Namespace) -> bool:
    status = launchability(book_id)
    if not status["launchable"]:
        print(f"waiting_for_poetry_preparation={book_id} reason={status['reason']}", flush=True)
        return False
    session = trilingual_session(book_id)
    if tmux_active(session):
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
    proc = run(["bash", "scripts/interlinear/start_trilingual_book_tmux.sh", book_id, session], env=env)
    print(proc.stdout, end="")
    if proc.returncode:
        print(f"start_failed={book_id} returncode={proc.returncode}", flush=True)
        return False
    finalizer = f"{session}-finalize"
    proc = run(["bash", "scripts/interlinear/start_trilingual_finalize_tmux.sh", book_id, session, finalizer], env=env)
    print(proc.stdout, end="")
    if proc.returncode:
        print(f"finalizer_start_failed={book_id} returncode={proc.returncode}", flush=True)
        return False
    return True


def write_state(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classical-book-id", action="append", default=[])
    parser.add_argument("--poetry-book-id", action="append", default=[])
    parser.add_argument("--poetry-batch", default=os.environ.get("POETRY_BATCH", str(DEFAULT_POETRY_BATCH)))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "10")))
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning", default=os.environ.get("REASONING", "low"))
    parser.add_argument("--retry-failed", action="store_true", default=os.environ.get("RETRY_FAILED") == "1")
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("INTERVAL_SECONDS", "1800")))
    parser.add_argument("--merge-interval-seconds", type=int, default=int(os.environ.get("MERGE_INTERVAL", "120")))
    parser.add_argument("--compile-interval-seconds", type=int, default=int(os.environ.get("COMPILE_INTERVAL_SECONDS", "1200")))
    parser.add_argument("--max-active-books", type=int, default=int(os.environ.get("MAX_ACTIVE_BOOKS", "1")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    classical_ids = args.classical_book_id or DEFAULT_CLASSICS
    poetry_ids = args.poetry_book_id or poetry_ids_from_batch(ROOT / args.poetry_batch)

    while True:
        timestamp = datetime.now(timezone.utc).isoformat()
        classical_reports = {book_id: quadrilingual_progress(book_id) for book_id in classical_ids}
        classical_done = all(quadrilingual_complete(report) for report in classical_reports.values())
        active_classics = active_classical_sessions(classical_ids)
        poetry_reports = {book_id: trilingual_progress(book_id) for book_id in poetry_ids}
        poetry_status = {book_id: launchability(book_id) for book_id in poetry_ids}
        active_poetry = active_poetry_sessions(poetry_ids)
        active_poetry_workers = [
            session
            for session in active_poetry
            if session != "zhjpbook-world-poetry-after-classics" and not session.endswith("-finalize")
        ]

        print(
            f"timestamp={timestamp} classical_complete={int(classical_done)} "
            f"active_classical={len(active_classics)} active_poetry={len(active_poetry)}",
            flush=True,
        )
        write_state(
            {
                "timestamp": timestamp,
                "classical_book_ids": classical_ids,
                "classical_reports": classical_reports,
                "classical_complete": classical_done,
                "active_classical_sessions": active_classics,
                "poetry_book_ids": poetry_ids,
                "poetry_reports": poetry_reports,
                "poetry_status": poetry_status,
                "active_poetry_sessions": active_poetry,
            }
        )

        if not classical_done or active_classics:
            print("waiting_for_classical_queue=1", flush=True)
        else:
            if all(trilingual_complete(report) for report in poetry_reports.values()):
                print("world_poetry_queue_complete=1", flush=True)
                return 0
            if len(active_poetry_workers) >= args.max_active_books:
                print(f"waiting_for_active_poetry_workers={len(active_poetry_workers)}", flush=True)
            else:
                for book_id in poetry_ids:
                    if trilingual_complete(poetry_reports[book_id]):
                        print(f"skip_complete={book_id}", flush=True)
                        continue
                    start_poetry(book_id, args)
                    break

        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
