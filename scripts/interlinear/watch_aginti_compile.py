#!/usr/bin/env python3
"""Compile prepared-book previews when async writer/reviewer progress changes."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def compile_previews(book: str, log) -> tuple[bool, int]:
    lock_path = ROOT / "data" / "interlinear" / book / "compile.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("compile skipped: another compile is already running")
            return False, 0
        env = os.environ.copy()
        env.setdefault("COMMIT_PROGRESS", "0")
        cmd = ["bash", "scripts/interlinear/compile_prepared_book_both_previews.sh", book]
        log(f"compile start: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        compile_log = ROOT / "data" / "interlinear" / book / "compile-watch.log"
        compile_log.write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            log(f"compile failed rc={result.returncode}; see {compile_log}")
            tail = "\n".join(result.stdout.splitlines()[-20:])
            if tail:
                log(tail)
            return False, result.returncode
        log(f"compile ok; see {compile_log}")
        return True, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", default="sishu-jizhu-aginti")
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--min-delta", type=int, default=50,
                        help="Compile after at least this many newly reviewed chunks")
    parser.add_argument("--max-interval", type=float, default=3600.0,
                        help="Compile if progress exists and this many seconds passed since last compile")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    status_path = ROOT / "data" / "interlinear" / args.book / "status.json"
    state_path = ROOT / "data" / "interlinear" / args.book / "compile-watch-status.json"
    log_path = ROOT / "data" / "interlinear" / args.book / "compile-watch-events.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def tick() -> None:
        status = load_json(status_path)
        state = load_json(state_path)
        reviewed = int(status.get("reviewed") or 0)
        pending = int(status.get("pending") or 0)
        failed = int(status.get("failed") or 0)
        last_compiled_reviewed = int(state.get("last_compiled_reviewed") or 0)
        last_compile_time = float(state.get("last_compile_time") or 0.0)
        now = time.time()
        delta = reviewed - last_compiled_reviewed
        should_compile = reviewed > 0 and delta > 0 and (
            delta >= args.min_delta
            or pending == 0
            or last_compile_time <= 0
            or now - last_compile_time >= args.max_interval
        )
        state.update({
            "book": args.book,
            "checked_at": now_iso(),
            "reviewed": reviewed,
            "pending": pending,
            "failed": failed,
            "delta_since_compile": delta,
        })
        if not should_compile:
            write_json(state_path, state)
            log(
                f"wait: reviewed={reviewed} pending={pending} failed={failed} "
                f"delta={delta}/{args.min_delta}"
            )
            return

        ok, rc = compile_previews(args.book, log)
        state.update({
            "last_compile_at": now_iso(),
            "last_compile_time": now,
            "last_compile_ok": ok,
            "last_compile_returncode": rc,
        })
        if ok:
            state["last_compiled_reviewed"] = reviewed
            state["delta_since_compile"] = 0
        write_json(state_path, state)

    while True:
        tick()
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
