#!/usr/bin/env python3
"""Commit completed world-literature OCR artifacts from a running tmux job."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

from world_literature_ocr_sources import ROOT, SOURCES


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check)


def staged_paths() -> list[str]:
    proc = run_git(["diff", "--cached", "--name-only"])
    return [line for line in proc.stdout.splitlines() if line.strip()]


def expected_paths(book_id: str, lang: str) -> list[Path]:
    book_dir = ROOT / "books" / book_id
    candidates = [
        book_dir / "markdown" / f"{lang}.ocr-polished.md",
        book_dir / "book-plan.json",
        book_dir / "markdown" / "en.md",
        book_dir / "markdown" / "zh.md",
        book_dir / "markdown" / "jp.md",
        book_dir / "work" / "trilingual" / "chunks" / "manifest.json",
    ]
    return [path for path in candidates if path.exists()]


def status_path(book_id: str, lang: str) -> Path:
    return ROOT / "books" / book_id / "work" / "ocr" / lang / "status.json"


def is_done(book_id: str, lang: str) -> bool:
    path = status_path(book_id, lang)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return data.get("status") == "done"


def commit_target(book_id: str, lang: str) -> bool:
    before = staged_paths()
    if before:
        print(f"skip_commit={book_id}:{lang} reason=preexisting_staged paths={before}", flush=True)
        return False

    rel_paths = [str(path.relative_to(ROOT)) for path in expected_paths(book_id, lang)]
    if not rel_paths:
        print(f"skip_commit={book_id}:{lang} reason=no_expected_paths", flush=True)
        return False

    run_git(["add", *rel_paths])
    after = staged_paths()
    if not after:
        print(f"nothing_to_commit={book_id}:{lang}", flush=True)
        return True

    title = book_id.replace("-", " ")
    run_git(["commit", "-m", f"Add {title} {lang.upper()} OCR reference"])
    print(f"committed={book_id}:{lang} paths={after}", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    pending = {f"{source.book_id}:{source.lang}" for source in SOURCES}
    state_dir = ROOT / "books" / "_world_literature_ocr_monitor" / "work"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "commit-monitor-state.json"
    if state_path.exists():
        try:
            committed = set(json.loads(state_path.read_text(encoding="utf-8")).get("committed", []))
            pending.difference_update(committed)
        except json.JSONDecodeError:
            committed = set()
    else:
        committed = set()

    while pending:
        for key in sorted(list(pending)):
            book_id, lang = key.split(":", 1)
            if not is_done(book_id, lang):
                continue
            if commit_target(book_id, lang):
                committed.add(key)
                pending.remove(key)
                state_path.write_text(
                    json.dumps(
                        {
                            "committed": sorted(committed),
                            "pending": sorted(pending),
                            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        if args.once:
            break
        if pending:
            print(f"waiting pending={len(pending)} interval={args.interval}s", flush=True)
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
