#!/usr/bin/env python3
"""Recompose LinguaLeaf cover overlays and update finished PDFs.

The image background remains textless.  This script only refreshes the stable
typographic overlay, then replaces an existing first-page image cover in build
PDFs.  Very large books are processed last so quick cover repairs finish first.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BIG_BOOK_HINTS = (
    "hou-han-shu",
    "houhanshu",
    "zizhi-tongjian",
    "zizhitongjian",
    "zizhi",
)
COVER_ALIASES = {
    "kokoro": "kokoro-jp-main",
    "sanguozhi-pei-zhu": "sanguozhi",
    "shiji-aginti": "shiji-aginti",
    "zizhi-tongjian-comment-aware": "zizhi-tongjian",
}
PLAN_ALIASES = {
    "shiji-aginti": "shiji",
    "zizhi-tongjian-comment-aware": "zizhi-tongjian",
}


def base_book_id(book_id: str) -> str:
    return re.sub(r"-part-\d+$", "", book_id)


def discover_books(build_dir: Path) -> list[str]:
    books: set[str] = set()
    for pdf in build_dir.glob("*/*/*/*.pdf"):
        if pdf.parent.name in {"color", "blackwhite"} and pdf.name != "book.pdf":
            books.add(pdf.relative_to(build_dir).parts[0])
    for pdf in build_dir.glob("*/*/*/*/*.pdf"):
        if pdf.parent.name in {"color", "blackwhite"} and pdf.name != "book.pdf":
            books.add(pdf.relative_to(build_dir).parts[0])
    return sorted(books, key=book_order_key)


def book_order_key(book_id: str) -> tuple[int, str]:
    normalized = book_id.lower().replace("_", "-")
    is_big = any(hint in normalized for hint in BIG_BOOK_HINTS)
    return (1 if is_big else 0, normalized)


def resolve_plan(book_id: str) -> Path | None:
    base_id = base_book_id(book_id)
    candidates = [book_id, base_id]
    alias = PLAN_ALIASES.get(book_id)
    if alias:
        candidates.append(alias)
    base_alias = PLAN_ALIASES.get(base_id)
    if base_alias:
        candidates.append(base_alias)
    for candidate in candidates:
        plan = ROOT / "books" / candidate / "book-plan.json"
        if plan.exists():
            return plan
    return None


def resolve_cover_dir(book_id: str) -> Path:
    base_id = base_book_id(book_id)
    alias = COVER_ALIASES.get(book_id) or COVER_ALIASES.get(base_id)
    cover_id = alias or base_id
    return ROOT / "assets" / "covers" / cover_id


def run_command(cmd: list[str], *, dry_run: bool) -> subprocess.CompletedProcess[str] | None:
    if dry_run:
        print("dry-run:", " ".join(cmd))
        return None
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def log_event(log_path: Path, event: dict[str, object]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def process_book(
    book_id: str,
    *,
    log_path: Path,
    apply_pdfs: bool,
    dry_run: bool,
    use_cover_as_background: bool,
) -> bool:
    plan = resolve_plan(book_id)
    cover_dir = resolve_cover_dir(book_id)
    background_candidates = [cover_dir / "background.png", cover_dir / "background-native.png"]
    background = next((candidate for candidate in background_candidates if candidate.exists()), cover_dir / "background.png")
    output = cover_dir / "cover.png"
    event: dict[str, object] = {
        "book_id": book_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cover_dir": str(cover_dir.relative_to(ROOT)) if cover_dir.exists() else str(cover_dir),
    }
    if plan is None:
        event["status"] = "missing-plan"
        print(f"missing plan: {book_id}")
        log_event(log_path, event)
        return False
    if not background.exists():
        if use_cover_as_background and output.exists():
            background = output
            event["background_mode"] = "existing-cover"
        else:
            event["status"] = "missing-background"
            print(f"missing background: {book_id}")
            log_event(log_path, event)
            return False

    compose_cmd = [
        "python3",
        "scripts/books/compose_book_cover.py",
        "--plan",
        str(plan.relative_to(ROOT)),
        "--background",
        str(background.relative_to(ROOT)),
        "--output",
        str(output.relative_to(ROOT)),
        "--book-id",
        book_id,
    ]
    compose = run_command(compose_cmd, dry_run=dry_run)
    if compose and compose.returncode != 0:
        event["status"] = "compose-failed"
        event["stdout"] = compose.stdout[-2000:]
        event["stderr"] = compose.stderr[-2000:]
        print(f"compose failed: {book_id}")
        log_event(log_path, event)
        return False
    if compose and compose.stdout:
        print(compose.stdout.strip())

    event["cover"] = str(output.relative_to(ROOT))
    if apply_pdfs:
        apply_cmd = [
            "python3",
            "scripts/books/prepend_cover_pages.py",
            "--book",
            book_id,
            "--force",
            "--replace-existing",
        ]
        apply = run_command(apply_cmd, dry_run=dry_run)
        if apply and apply.returncode not in {0, 1}:
            event["status"] = "pdf-apply-failed"
            event["stdout"] = apply.stdout[-2000:]
            event["stderr"] = apply.stderr[-2000:]
            print(f"PDF cover update failed: {book_id}")
            log_event(log_path, event)
            return False
        if apply and apply.stdout:
            print(apply.stdout.strip())
        event["pdf_apply_returncode"] = apply.returncode if apply else None
    event["status"] = "ok"
    log_event(log_path, event)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", dest="books", help="book id to process")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-apply-pdfs", action="store_true")
    parser.add_argument(
        "--use-cover-as-background",
        action="store_true",
        help="fallback for legacy assets without background.png; may retain old embedded text",
    )
    args = parser.parse_args()

    log_path = args.log or ROOT / "logs" / f"cover-backfill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    books = args.books or discover_books(args.build_dir)
    print(f"books={len(books)} log={log_path.relative_to(ROOT)}")
    ok = 0
    failed = 0
    for index, book_id in enumerate(books, start=1):
        print(f"[{index}/{len(books)}] {book_id}", flush=True)
        if process_book(
            book_id,
            log_path=log_path,
            apply_pdfs=not args.no_apply_pdfs,
            dry_run=args.dry_run,
            use_cover_as_background=args.use_cover_as_background,
        ):
            ok += 1
        else:
            failed += 1
    print(f"ok={ok} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
