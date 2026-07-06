#!/usr/bin/env python3
"""Wait for fantasy trilingual queue completion, then run classical quadrilingual books.

The monitor is intentionally conservative: it never starts a classical
quadrilingual writer while any prerequisite fantasy book is incomplete or has
an active writer/finalizer/repair session.
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
STATE_DIR = ROOT / "books" / "_queues" / "fantasy-then-classics"


DEFAULT_FANTASY = [
    "the-two-towers",
    "return-of-the-king",
    "harry-potter-2",
    "harry-potter-3",
    "harry-potter-4",
    "harry-potter-5",
    "harry-potter-6",
    "harry-potter-7",
    "a-clash-of-kings",
    "a-storm-of-swords",
    "a-feast-for-crows",
    "a-dance-with-dragons",
]

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


def load_plan(book_id: str) -> dict[str, Any] | None:
    path = ROOT / "books" / book_id / "book-plan.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def parse_report(text: str) -> dict[str, str]:
    report: dict[str, str] = {}
    for line in text.splitlines():
        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=(.*?)(?=\s+[A-Za-z_][A-Za-z0-9_]*=|$)", line):
            key = match.group(1).strip()
            value = match.group(2).strip()
            if key:
                report[key] = value
    return report


def trilingual_progress(book_id: str) -> dict[str, str]:
    plan = load_plan(book_id)
    if not plan:
        return {"error": "missing book-plan.json", "manifest_chunks": "0", "valid_chunks": "0"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_trilingual_progress.py",
            "--manifest",
            str(plan.get("chunks_manifest") or ""),
            "--chunk-dir",
            str(plan.get("raw_chunk_dir") or ""),
        ],
        quiet=True,
    )
    report = parse_report(proc.stdout)
    if proc.returncode:
        report["error"] = proc.stdout.strip()
    return report


def quadrilingual_progress(book_id: str) -> dict[str, str]:
    plan = load_plan(book_id)
    if not plan:
        return {"error": "missing book-plan.json", "valid": "0/0", "missing": "0", "stale": "0"}
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


def trilingual_complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in {"", "0", None}
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def quadrilingual_complete(report: dict[str, str]) -> bool:
    valid = str(report.get("valid") or "0/0")
    if "/" not in valid:
        return False
    done, total = valid.split("/", 1)
    return total not in {"", "0"} and done == total and report.get("missing") == "0" and report.get("stale") == "0"


def fantasy_sessions(book_ids: list[str]) -> list[str]:
    sessions: list[str] = []
    for session in ("zhjpbook-fantasy-series-queue",):
        if tmux_active(session):
            sessions.append(session)
    for book_id in book_ids:
        for suffix in ("trilingual", "trilingual-finalize", "trilingual-repair"):
            session = f"zhjpbook-{book_id}-{suffix}"
            if tmux_active(session):
                sessions.append(session)
    return sessions


def quadrilingual_session(book_id: str) -> str:
    return f"zhjpbook-{book_id}-quadrilingual"


def start_classical(book_id: str, args: argparse.Namespace) -> bool:
    plan = load_plan(book_id)
    if not plan or not plan.get("launchable"):
        print(f"skip_not_launchable={book_id}", flush=True)
        return False
    session = quadrilingual_session(book_id)
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
            "MAIN_LAYERS": args.main_layers,
        }
    )
    if args.retry_failed:
        env["RETRY_FAILED"] = "1"
    proc = run(["bash", "scripts/interlinear/start_quadrilingual_wenyan_tmux.sh", book_id, session], env=env)
    print(proc.stdout, end="")
    if proc.returncode:
        print(f"start_failed={book_id} returncode={proc.returncode}", flush=True)
        return False
    return True


def write_state(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fantasy-book-id", action="append", default=[])
    parser.add_argument("--classical-book-id", action="append", default=[])
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "100")))
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning", default=os.environ.get("REASONING", "low"))
    parser.add_argument("--main-layers", default=os.environ.get("MAIN_LAYERS", "wenyan"))
    parser.add_argument("--retry-failed", action="store_true", default=os.environ.get("RETRY_FAILED") == "1")
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("INTERVAL_SECONDS", "1800")))
    parser.add_argument("--merge-interval-seconds", type=int, default=int(os.environ.get("MERGE_INTERVAL", "120")))
    parser.add_argument("--compile-interval-seconds", type=int, default=int(os.environ.get("COMPILE_INTERVAL_SECONDS", "1200")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    fantasy_ids = args.fantasy_book_id or DEFAULT_FANTASY
    classical_ids = args.classical_book_id or DEFAULT_CLASSICS

    while True:
        timestamp = datetime.now(timezone.utc).isoformat()
        fantasy_reports = {book_id: trilingual_progress(book_id) for book_id in fantasy_ids}
        fantasy_done = all(trilingual_complete(report) for report in fantasy_reports.values())
        active_fantasy = fantasy_sessions(fantasy_ids)
        classical_reports = {book_id: quadrilingual_progress(book_id) for book_id in classical_ids}
        active_classical = [quadrilingual_session(book_id) for book_id in classical_ids if tmux_active(quadrilingual_session(book_id))]

        print(
            f"timestamp={timestamp} fantasy_complete={int(fantasy_done)} "
            f"active_fantasy={len(active_fantasy)} active_classical={len(active_classical)}",
            flush=True,
        )
        write_state(
            {
                "timestamp": timestamp,
                "fantasy_book_ids": fantasy_ids,
                "fantasy_reports": fantasy_reports,
                "fantasy_complete": fantasy_done,
                "active_fantasy_sessions": active_fantasy,
                "classical_book_ids": classical_ids,
                "classical_reports": classical_reports,
                "active_classical_sessions": active_classical,
            }
        )

        if fantasy_done and not active_fantasy and not active_classical:
            if all(quadrilingual_complete(report) for report in classical_reports.values()):
                print("classical_queue_complete=1", flush=True)
                return 0
            for book_id in classical_ids:
                if quadrilingual_complete(classical_reports[book_id]):
                    print(f"skip_complete={book_id}", flush=True)
                    continue
                start_classical(book_id, args)
                break
        elif not fantasy_done or active_fantasy:
            print("waiting_for_fantasy_queue=1", flush=True)

        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
