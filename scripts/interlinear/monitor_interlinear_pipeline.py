#!/usr/bin/env python3
"""Monitor and gently heal one interlinear book pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Paths:
    book_id: str
    work: Path
    manifest: Path
    chunks_jsonl: Path
    raw_dir: Path
    reviewed_dir: Path
    gen_candidates: Path
    gen_merged: Path
    review_candidates: Path
    review_merged: Path
    review_rejected: Path
    sanitizer_shared: Path
    monitor_dir: Path


def paths_for(book_id: str) -> Paths:
    work = Path("books") / book_id / "work" / "bilingual"
    return Paths(
        book_id=book_id,
        work=work,
        manifest=work / "chunks" / "manifest.json",
        chunks_jsonl=work / "chunks" / "chunks.jsonl",
        raw_dir=work / "interlinear" / "chunks",
        reviewed_dir=work / "reviewed" / "chunks",
        gen_candidates=work / "parallel-json" / "candidates",
        gen_merged=work / "parallel-json" / "merged",
        review_candidates=work / "parallel-review" / "candidates",
        review_merged=work / "parallel-review" / "merged",
        review_rejected=work / "parallel-review" / "merge-rejected",
        sanitizer_shared=work / "sanitizer" / "shared",
        monitor_dir=Path("books") / book_id / "work" / "monitor",
    )


def run(cmd: list[str], *, env: dict[str, str] | None = None, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)


def tmux_active(session: str) -> bool:
    if not session:
        return False
    return subprocess.run(["tmux", "has-session", "-t", f"={session}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def parse_report(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def progress(manifest: Path, chunk_dir: Path) -> dict[str, str]:
    if not manifest.exists():
        return {"manifest_chunks": "0", "valid_chunks": "0", "missing_chunks": "0", "error": f"missing {manifest}"}
    proc = run(
        [
            "python",
            "scripts/interlinear/report_interlinear_progress.py",
            "--manifest",
            str(manifest),
            "--chunk-dir",
            str(chunk_dir),
        ],
        quiet=True,
    )
    data = parse_report(proc.stdout)
    if proc.returncode:
        data["error"] = proc.stdout.strip()
    return data


def count_json(path: Path) -> int:
    return sum(1 for _ in path.glob("*.json")) if path.exists() else 0


def first_json_name(path: Path) -> str:
    if not path.exists():
        return ""
    return next((item.name for item in sorted(path.glob("*.json"))), "")


def latest_mtime(paths: list[Path]) -> float:
    latest = 0.0
    for root in paths:
        if root.is_file():
            latest = max(latest, root.stat().st_mtime)
        elif root.exists():
            for item in root.rglob("*"):
                if item.is_file():
                    latest = max(latest, item.stat().st_mtime)
    return latest


def stale_claims(path: Path, ttl_seconds: int) -> list[Path]:
    now = time.time()
    claim_root = path / "claims"
    if not claim_root.exists():
        return []
    return [item for item in claim_root.iterdir() if item.is_dir() and now - item.stat().st_mtime > ttl_seconds]


def clear_claims(claims: list[Path]) -> None:
    for claim in claims:
        print(f"clearing stale claim {claim}", flush=True)
        shutil.rmtree(claim, ignore_errors=True)


def complete(report: dict[str, str]) -> bool:
    return (
        report.get("manifest_chunks") not in ("", "0", None)
        and report.get("manifest_chunks") == report.get("valid_chunks")
        and report.get("missing_chunks") == "0"
        and report.get("stale_chunks") == "0"
    )


def health(
    paths: Paths,
    worker_session: str,
    review_session: str,
    claim_ttl_seconds: int,
    *,
    no_reviewed_stage: bool = False,
) -> dict[str, Any]:
    raw = progress(paths.manifest, paths.raw_dir)
    reviewed = raw if no_reviewed_stage else progress(paths.manifest, paths.reviewed_dir)
    gen_failed = count_json(paths.gen_candidates / "failed")
    review_failed = count_json(paths.review_candidates / "failed")
    data: dict[str, Any] = {
        "book_id": paths.book_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw": raw,
        "reviewed": reviewed,
        "generation": {
            "accepted": count_json(paths.gen_candidates / "accepted"),
            "failed": gen_failed,
            "rejected": count_json(paths.gen_candidates / "rejected"),
            "merge_rejected": count_json(paths.gen_candidates / "merge-rejected"),
            "stale_claims": [str(p) for p in stale_claims(paths.gen_candidates, claim_ttl_seconds)],
        },
        "review": {
            "accepted": count_json(paths.review_candidates / "accepted"),
            "failed": review_failed,
            "rejected": count_json(paths.review_candidates / "rejected"),
            "merge_rejected": count_json(paths.review_rejected),
            "stale_claims": [str(p) for p in stale_claims(paths.review_candidates, claim_ttl_seconds)],
        },
        "sanitizer": {
            "failed": count_json(paths.sanitizer_shared / "failed"),
            "first_failed": first_json_name(paths.sanitizer_shared / "failed"),
            "claims": len(stale_claims(paths.sanitizer_shared, 0)),
            "stale_claims": [str(p) for p in stale_claims(paths.sanitizer_shared, claim_ttl_seconds)],
        },
        "worker_session_active": tmux_active(worker_session),
        "review_session_active": tmux_active(review_session),
        "latest_mtime": latest_mtime(
            [
                paths.raw_dir,
                paths.reviewed_dir,
                paths.gen_candidates,
                paths.review_candidates,
                Path("books") / paths.book_id / "work" / "logs",
            ]
        ),
    }
    if complete(reviewed):
        data["status"] = "complete"
    elif gen_failed or review_failed or data["sanitizer"]["failed"]:
        data["status"] = "needs_repair"
    elif not data["worker_session_active"] and not data["review_session_active"]:
        data["status"] = "stopped"
    else:
        data["status"] = "running"
    return data


def print_health(data: dict[str, Any]) -> None:
    raw = data["raw"]
    reviewed = data["reviewed"]
    print(f"timestamp={data['timestamp']}")
    print(f"book_id={data['book_id']}")
    print(f"status={data['status']}")
    print(
        "raw="
        f"{raw.get('valid_chunks', '0')}/{raw.get('manifest_chunks', '0')}"
        f" missing={raw.get('missing_chunks', '0')} first_missing={raw.get('first_missing', '')}"
    )
    print(
        "reviewed="
        f"{reviewed.get('valid_chunks', '0')}/{reviewed.get('manifest_chunks', '0')}"
        f" missing={reviewed.get('missing_chunks', '0')} first_missing={reviewed.get('first_missing', '')}"
    )
    print(
        "generation="
        f"accepted:{data['generation']['accepted']} failed:{data['generation']['failed']} "
        f"rejected:{data['generation']['rejected']} stale_claims:{len(data['generation']['stale_claims'])}"
    )
    print(
        "review="
        f"accepted:{data['review']['accepted']} failed:{data['review']['failed']} "
        f"rejected:{data['review']['rejected']} stale_claims:{len(data['review']['stale_claims'])}"
    )
    print(
        "sanitizer="
        f"failed:{data['sanitizer']['failed']} first_failed:{data['sanitizer']['first_failed']} "
        f"claims:{data['sanitizer']['claims']} stale_claims:{len(data['sanitizer']['stale_claims'])}"
    )
    print(f"worker_session_active={int(data['worker_session_active'])}")
    print(f"review_session_active={int(data['review_session_active'])}")


def snapshot(paths: Paths, data: dict[str, Any]) -> Path:
    paths.monitor_dir.mkdir(parents=True, exist_ok=True)
    out = paths.monitor_dir / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def merge(paths: Paths, compile_command: str, *, no_reviewed_stage: bool = False) -> None:
    merge_paths = [paths.raw_dir, paths.gen_merged]
    if not no_reviewed_stage:
        merge_paths.extend([paths.reviewed_dir, paths.review_merged, paths.review_rejected])
    for path in merge_paths:
        path.mkdir(parents=True, exist_ok=True)
    raw = run(
        [
            "python",
            "scripts/interlinear/merge_parallel_json_candidates.py",
            "--chunks-jsonl",
            str(paths.chunks_jsonl),
            "--candidate-dir",
            str(paths.gen_candidates),
            "--canonical-dir",
            str(paths.raw_dir),
            "--merged-dir",
            str(paths.gen_merged),
        ]
    )
    print(raw.stdout, end="")
    if no_reviewed_stage:
        return
    reviewed_cmd = [
        "python",
        "scripts/interlinear/merge_reviewed_chunks.py",
        "--chunks-jsonl",
        str(paths.chunks_jsonl),
        "--candidate-dir",
        str(paths.review_candidates),
        "--final-dir",
        str(paths.reviewed_dir),
        "--merged-dir",
        str(paths.review_merged),
        "--rejected-dir",
        str(paths.review_rejected),
    ]
    if compile_command:
        reviewed_cmd.extend(["--after-merge-command", compile_command])
    reviewed = run(reviewed_cmd)
    print(reviewed.stdout, end="")


def start_worker(start_command: str, start_index: str) -> None:
    env = os.environ.copy()
    if start_index:
        env["START_INDEX"] = start_index.split("-")[-1].lstrip("0") or "1"
    proc = subprocess.run(start_command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    print(proc.stdout, end="")


def monitor_once(args: argparse.Namespace, paths: Paths, state: dict[str, Any]) -> dict[str, Any]:
    if args.heal:
        if args.clear_stale_claims:
            clear_claims(stale_claims(paths.gen_candidates, args.claim_ttl_seconds))
            clear_claims(stale_claims(paths.review_candidates, args.claim_ttl_seconds))
        merge(paths, args.compile_command, no_reviewed_stage=args.no_reviewed_stage)

    data = health(
        paths,
        args.worker_session,
        args.review_session,
        args.claim_ttl_seconds,
        no_reviewed_stage=args.no_reviewed_stage,
    )
    print_health(data)

    marker = json.dumps(
        {
            "raw": data["raw"],
            "reviewed": data["reviewed"],
            "generation": data["generation"],
            "review": data["review"],
            "latest_mtime": data["latest_mtime"],
        },
        sort_keys=True,
    )
    now = time.time()
    if state.get("marker") != marker:
        state["marker"] = marker
        state["since"] = now
    unchanged_for = int(now - float(state.get("since", now)))
    print(f"unchanged_for={unchanged_for}")

    if data["status"] == "complete":
        return data

    if data["status"] == "needs_repair":
        snap = snapshot(paths, data)
        print(f"needs_repair_snapshot={snap}")
        if args.repair_command:
            proc = subprocess.run(args.repair_command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print(proc.stdout, end="")
        return data

    if args.heal and args.start_command and unchanged_for >= args.stall_seconds:
        if not data["worker_session_active"] and not data["review_session_active"]:
            first_missing = data["raw"].get("first_missing") or data["reviewed"].get("first_missing") or ""
            print(f"restarting_from={first_missing or 'default'}")
            start_worker(args.start_command, first_missing)
            state["since"] = now
    elif unchanged_for >= args.stall_seconds:
        snap = snapshot(paths, data)
        print(f"stall_snapshot={snap}")

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--worker-session", default="")
    parser.add_argument("--review-session", default="")
    parser.add_argument("--compile-command", default="")
    parser.add_argument("--start-command", default="")
    parser.add_argument("--repair-command", default="")
    parser.add_argument("--no-reviewed-stage", action="store_true")
    parser.add_argument("--heal", action="store_true")
    parser.add_argument("--clear-stale-claims", action="store_true")
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=1800)
    parser.add_argument("--stall-seconds", type=int, default=3600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    paths = paths_for(args.book_id)
    paths.monitor_dir.mkdir(parents=True, exist_ok=True)
    state_path = paths.monitor_dir / "pipeline-monitor-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    while True:
        data = monitor_once(args, paths, state)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        if not args.loop or data["status"] == "complete":
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
