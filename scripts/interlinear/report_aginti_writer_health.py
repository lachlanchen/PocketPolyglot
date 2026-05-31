#!/usr/bin/env python3
"""Summarize AgInTi interlinear writer health from status and worker logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def latest_log_dir(book: str) -> Path | None:
    logs = sorted(
        (ROOT / "logs").glob(f"{book}-json-workers-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return logs[0] if logs else None


def count_in_logs(log_dir: Path) -> dict[str, int]:
    counters = {
        "ok": 0,
        "validation_retry": 0,
        "validation_failed": 0,
        "api_error": 0,
        "ja_multi_kanji": 0,
        "furigana_on_multi": 0,
        "zh_reconstruct": 0,
        "empty_ja": 0,
        "json_parse": 0,
    }
    for path in sorted(log_dir.glob("worker-*.log")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        counters["ok"] += text.count("  OK ->")
        counters["validation_retry"] += text.count("VALIDATION RETRY")
        counters["validation_failed"] += text.count("VALIDATION FAILED")
        counters["api_error"] += text.count("API ERROR")
        counters["ja_multi_kanji"] += text.count("Japanese kanji token must be exactly one kanji")
        counters["furigana_on_multi"] += text.count("furigana may only be on one-kanji tokens")
        counters["zh_reconstruct"] += text.count("zh tokens do not reconstruct source text")
        counters["zh_reconstruct"] += text.count("units do not reconstruct paragraph source_text")
        counters["empty_ja"] += text.count("empty Japanese line")
        counters["json_parse"] += text.count("JSON PARSE")
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", default="sishu-jizhu-aginti")
    parser.add_argument("--log-dir", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    status_path = ROOT / "data" / "interlinear" / args.book / "status.json"
    status = {}
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))

    log_dir = Path(args.log_dir) if args.log_dir else latest_log_dir(args.book)
    counters = count_in_logs(log_dir) if log_dir and log_dir.exists() else {}

    summary = {
        "book": args.book,
        "status_path": str(status_path),
        "log_dir": str(log_dir) if log_dir else None,
        "total_chunks": status.get("total_chunks"),
        "reviewed": status.get("reviewed"),
        "failed": status.get("failed"),
        "pending": status.get("pending"),
        "first_missing": status.get("first_missing"),
        "last_updated": status.get("last_updated"),
        "log_counters": counters,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"book: {summary['book']}")
        print(f"status: reviewed={summary['reviewed']} failed={summary['failed']} pending={summary['pending']} first_missing={summary['first_missing']}")
        print(f"last_updated: {summary['last_updated']}")
        print(f"log_dir: {summary['log_dir']}")
        for key, value in counters.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
