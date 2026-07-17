#!/usr/bin/env python3
"""Sync validated polished pocket books into Nutstore Share/PocketPolished."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nutstore_paths import nutstore_safe_filename


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "build-pocket-polished"
DEFAULT_SHARE_ROOT = Path.home() / "Nutstore Files/Share/PocketPolished"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def queue_book_ids(path: Path) -> list[str]:
    queue = read_json(path)
    return [item["book_id"] for item in queue.get("books", [])]


def report_is_publishable(report: dict[str, Any]) -> bool:
    return bool(
        report.get("layout_clean")
        and report.get("objects_complete")
        and report.get("searchable_text_present")
        and report.get("injected_cover_count", 0) >= 1
    )


def try_reassemble_with_existing_cover(book_id: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-u", "scripts/books/assemble_build_pocket_polished.py", book_id],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def sync_book(book_id: str, share_root: Path) -> dict[str, Any]:
    book_root = OUTPUT_ROOT / book_id
    status_path = book_root / "status.json"
    if not status_path.exists():
        return {"book_id": book_id, "status": "waiting", "reason": "missing status.json"}

    status = read_json(status_path)
    if status.get("status") != "complete":
        return {
            "book_id": book_id,
            "status": "waiting",
            "reason": f"assembly status is {status.get('status', 'unknown')}",
        }

    reports = status.get("reports", {})
    required_keys = ("pocket_en_main_ja",)
    if not all(report_is_publishable(reports.get(key, {})) for key in required_keys):
        if try_reassemble_with_existing_cover(book_id):
            status = read_json(status_path)
            reports = status.get("reports", {})
        if not all(report_is_publishable(reports.get(key, {})) for key in required_keys):
            return {
                "book_id": book_id,
                "status": "needs_cover_or_layout_repair",
                "reason": "pocket PDFs must be layout-clean, searchable, object-complete, and covered",
            }

    data_path = book_root / "data/book.json"
    title = read_json(data_path).get("title", book_id) if data_path.exists() else book_id
    share_root.mkdir(parents=True, exist_ok=True)
    report = reports["pocket_en_main_ja"]
    source = ROOT / report["pdf"]
    if not source.is_file():
        return {"book_id": book_id, "status": "error", "reason": f"missing PDF: {source}"}
    filename = nutstore_safe_filename(
        f"{title}｜English-日本語｜Polished Pocket Large Font.pdf"
    )
    destination = share_root / filename
    source_hash = sha256(source)
    changed = not destination.exists() or sha256(destination) != source_hash
    if changed:
        shutil.copy2(source, destination)
    destination_hash = sha256(destination)
    if source_hash != destination_hash:
        destination.unlink(missing_ok=True)
        return {"book_id": book_id, "status": "error", "reason": f"checksum mismatch: {destination}"}
    copied = [
        {
            "languages": ["en", "ja"],
            "main_language": "en",
            "source": str(source),
            "destination": str(destination),
            "sha256": source_hash,
            "bytes": destination.stat().st_size,
            "changed": changed,
        }
    ]
    for obsolete in (
        share_root / nutstore_safe_filename(f"{title}｜English｜Polished Pocket Large Font.pdf"),
        share_root / nutstore_safe_filename(f"{title}｜日本語｜Polished Pocket Large Font.pdf"),
    ):
        obsolete.unlink(missing_ok=True)

    result = {
        "book_id": book_id,
        "status": "synced",
        "share_root": str(share_root),
        "files": copied,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    sync_status = book_root / "nutstore-sync.json"
    sync_status.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def print_result(result: dict[str, Any]) -> None:
    print(f"{result['book_id']}: {result['status']}", flush=True)
    if result.get("reason"):
        print(f"  reason: {result['reason']}", flush=True)
    for item in result.get("files", []):
        action = "copied" if item.get("changed") else "unchanged"
        print(f"  {item['destination']} ({item['bytes']} bytes, {action})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id", nargs="*")
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--share-root", type=Path, default=DEFAULT_SHARE_ROOT)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=120)
    args = parser.parse_args()

    book_ids = list(args.book_id)
    if args.queue:
        book_ids.extend(queue_book_ids(args.queue))
    book_ids = list(dict.fromkeys(book_ids))
    if not book_ids:
        parser.error("provide at least one book_id or --queue")

    while True:
        results = [sync_book(book_id, args.share_root) for book_id in book_ids]
        for result in results:
            print_result(result)
        errors = [result for result in results if result["status"] in {"error", "needs_cover_or_layout_repair"}]
        waiting = [result for result in results if result["status"] == "waiting"]
        if errors:
            return 1
        if not args.watch or not waiting:
            return 0
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
