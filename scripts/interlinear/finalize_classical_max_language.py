#!/usr/bin/env python3
"""Audit or finalize classical books without duplicating valid large-font exports."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = ROOT / "data/source-plan/classical-quadrilingual-source-batch.json"
DEFAULT_STATUS = ROOT / "books/_queues/classical-max-language/status.json"

# These books were intentionally published as multiple volumes.  The corrected
# comment-aware Zizhi Tongjian supersedes its older six-part export for the
# completion audit.
MULTIPART_EXPORTS = {
    "hou-han-shu": {
        "part_ids": tuple(f"hou-han-shu-part-{index:02d}" for index in range(1, 4)),
        "layouts": ("wenyan-main-quadrilingual/large-font",),
    },
    "zizhi-tongjian": {
        "part_ids": tuple(
            f"zizhi-tongjian-comment-aware-part-{index:02d}"
            for index in range(1, 7)
        ),
        "layouts": ("maximum-language-large-font/wenyan-main-quadrilingual",),
    },
}

# Several finished books predate the current canonical directory name but use
# the same large PocketPolyglot typography.  Recompiling them merely to rename
# a directory wastes time and can create a misleading duplicate edition.
SINGLE_VOLUME_LAYOUTS = (
    "maximum-language-large-font/wenyan-main-quadrilingual",
    "maximum-language-shiji-font/wenyan-main-quadrilingual",
    "wenyan-main-quadrilingual/large-font",
    "wenyan-main-quadrilingual/shiji-aginti-font",
)


def valid_pdfs(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    result = []
    for path in sorted(directory.glob("*.pdf")):
        try:
            with path.open("rb") as stream:
                header = stream.read(5)
            if path.stat().st_size >= 1024 and header == b"%PDF-":
                result.append(path)
        except OSError:
            continue
    return result


def paired_export_evidence(root: Path) -> list[Path]:
    color = valid_pdfs(root / "color")
    blackwhite = valid_pdfs(root / "blackwhite")
    if not color or not blackwhite:
        return []
    return [color[0], blackwhite[0]]


def first_complete_layout(book_id: str, layouts: Iterable[str]) -> list[Path]:
    book_root = ROOT / "build" / book_id
    for layout in layouts:
        evidence = paired_export_evidence(book_root / layout)
        if evidence:
            return evidence
    return []


def export_evidence(book_id: str) -> list[Path]:
    multipart = MULTIPART_EXPORTS.get(book_id)
    if multipart:
        evidence = []
        for part_id in multipart["part_ids"]:
            part_evidence = first_complete_layout(part_id, multipart["layouts"])
            if not part_evidence:
                return []
            evidence.extend(part_evidence)
        return evidence
    return first_complete_layout(book_id, SINGLE_VOLUME_LAYOUTS)


def export_complete(book_id: str) -> bool:
    return bool(export_evidence(book_id))


def relative_evidence(book_id: str) -> list[str]:
    return [str(path.relative_to(ROOT)) for path in export_evidence(book_id)]


def run_export(book_id: str, *, force: bool) -> tuple[bool, str]:
    cmd = [
        "python",
        "scripts/interlinear/export_max_language_shiji_catalog.py",
        "--book",
        book_id,
        "--force-compress",
        "--no-readme",
        "--no-manifest",
    ]
    if force:
        cmd.append("--force-compile")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.returncode == 0 and export_complete(book_id), result.stdout


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Report existing exports without compiling missing books.",
    )
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    selected = set(args.book_id)
    book_ids = [
        item["book_id"]
        for item in batch.get("books", [])
        if not selected or item["book_id"] in selected
    ]
    results: dict[str, dict[str, object]] = {}
    failures = 0
    for index, book_id in enumerate(book_ids, start=1):
        if export_complete(book_id) and not args.force:
            evidence = relative_evidence(book_id)
            results[book_id] = {
                "status": "already_complete",
                "edition": "multipart" if book_id in MULTIPART_EXPORTS else "single_volume",
                "evidence": evidence,
            }
            print(f"[{index}/{len(book_ids)}] {book_id}: already complete", flush=True)
        elif args.audit_only:
            results[book_id] = {"status": "missing"}
            failures += 1
            print(f"[{index}/{len(book_ids)}] {book_id}: missing", flush=True)
        else:
            print(f"[{index}/{len(book_ids)}] {book_id}: compiling", flush=True)
            complete, output = run_export(book_id, force=args.force)
            results[book_id] = {
                "status": "complete" if complete else "failed",
                "evidence": relative_evidence(book_id) if complete else [],
                "log_tail": output[-8000:],
            }
            if not complete:
                failures += 1
                print(f"{book_id}: failed", flush=True)
        write_status(
            args.status,
            {
                "schema_version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "book_count": len(book_ids),
                "complete_count": sum(
                    item["status"] in {"complete", "already_complete"}
                    for item in results.values()
                ),
                "failed_count": sum(
                    item["status"] in {"failed", "missing"}
                    for item in results.values()
                ),
                "results": results,
            },
        )

    print(f"books={len(book_ids)} failures={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
