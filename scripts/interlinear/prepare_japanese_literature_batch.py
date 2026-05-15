#!/usr/bin/env python3
"""Prepare markdown and chunk tasks for the Japanese literature batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_before_text(markdown_path: Path, start_text: str) -> bool:
    """Keep the first line equal to start_text and everything after it.

    Some EPUBs do not expose real Markdown headings. This keeps the novel body
    while dropping publisher blurbs or critical introductions.
    """

    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    wanted = start_text.strip()
    for index, line in enumerate(lines):
        if line.strip() == wanted:
            markdown_path.write_text("\n".join(lines[index:]).strip() + "\n", encoding="utf-8")
            return True
    return False


def promote_plain_chapter_lines(markdown_path: Path) -> None:
    """Turn plain chapter marker lines into Markdown headings when needed."""

    chapter_re = re.compile(r"^第[一二三四五六七八九十百千〇零0-9]+章$")
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    changed = False
    promoted: list[str] = []
    for line in lines:
        stripped = line.strip()
        if chapter_re.match(stripped):
            promoted.append(f"# {stripped}")
            changed = True
        else:
            promoted.append(line)
    if changed:
        markdown_path.write_text("\n".join(promoted).strip() + "\n", encoding="utf-8")


def language_markdown_name(language: str) -> str:
    if language in {"zh", "ja", "en"}:
        return f"{language}.md"
    return "source.md"


def prepare_markdown(book: dict[str, Any], force: bool) -> dict[str, str]:
    book_id = book["book_id"]
    language = book.get("source_language", "zh")
    source = ROOT / book["source_path"]
    markdown_dir = ROOT / "books" / book_id / "markdown"
    raw_output = markdown_dir / f"{language}.raw.md"
    clean_output = markdown_dir / f"{language}.clean.md"
    source_markdown = markdown_dir / language_markdown_name(language)

    if not source.exists():
        raise FileNotFoundError(source)
    markdown_dir.mkdir(parents=True, exist_ok=True)

    source_type = book.get("source_type", "")
    if source_type == "epub":
        if force or not clean_output.exists():
            cmd = [
                "python",
                "scripts/books/epub_to_markdown.py",
                str(source),
                "--raw-output",
                str(raw_output),
                "--clean-output",
                str(clean_output),
            ]
            if book.get("start_heading"):
                cmd.extend(["--start-heading", book["start_heading"]])
            if book.get("start_text"):
                cmd.extend(["--start-text", book["start_text"]])
            run(cmd)
    else:
        raise ValueError(f"unsupported source_type for {book_id}: {source_type}")

    if book.get("start_text"):
        if force or source_markdown.exists() or clean_output.exists():
            found = strip_before_text(clean_output, book["start_text"])
            if not found:
                print(f"warning: {book_id}: start_text not found: {book['start_text']}", flush=True)

    if force or not source_markdown.exists():
        shutil.copyfile(clean_output, source_markdown)
    promote_plain_chapter_lines(source_markdown)

    return {
        "raw_markdown": str(raw_output.relative_to(ROOT)),
        "clean_markdown": str(clean_output.relative_to(ROOT)),
        "source_markdown": str(source_markdown.relative_to(ROOT)),
        "source_sha256": sha256(source),
        "markdown_sha256": sha256(source_markdown),
    }


def write_plan(book: dict[str, Any], paths: dict[str, str], launchable: bool) -> Path:
    book_id = book["book_id"]
    work_root = Path("books") / book_id / "work" / "bilingual"
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": book.get("status", ""),
        "launchable": launchable,
        "task_mode": book.get("task_mode", ""),
        "source_language": book.get("source_language", ""),
        "source_type": book.get("source_type", ""),
        "source_path": book.get("source_path", ""),
        **paths,
        "book_title_zh": book.get("book_title_zh", ""),
        "book_title_zh_reading": book.get("book_title_zh_reading", ""),
        "book_title_ja": book.get("book_title_ja", ""),
        "book_title_ja_reading": book.get("book_title_ja_reading", ""),
        "author": book.get("author", ""),
        "author_reading_zh": book.get("author_reading_zh", ""),
        "author_reading_ja": book.get("author_reading_ja", ""),
        "book_description": book.get("book_description", ""),
        "chunk_mode": book.get("chunk_mode", "paragraph"),
        "reference_scope": book.get("reference_scope", "chapter"),
        "chunks_jsonl": str(work_root / "chunks" / "chunks.jsonl"),
        "chunks_manifest": str(work_root / "chunks" / "manifest.json"),
        "raw_chunk_dir": str(work_root / "interlinear" / "chunks"),
        "reviewed_chunk_dir": str(work_root / "reviewed" / "chunks"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    write_json(plan_path, plan)
    return plan_path


def prepare_chunks(book: dict[str, Any], plan_path: Path, force: bool) -> None:
    book_id = book["book_id"]
    plan = load_json(plan_path)
    chunks_jsonl = ROOT / plan["chunks_jsonl"]
    manifest = ROOT / plan["chunks_manifest"]
    if chunks_jsonl.exists() and manifest.exists() and not force:
        print(f"{book_id}: chunks already prepared: {chunks_jsonl.relative_to(ROOT)}", flush=True)
        return

    cmd = [
        "python",
        "scripts/interlinear/chunk_markdown_book.py",
        plan["source_markdown"],
        "--book-id",
        book_id,
        "--book-title-zh",
        plan["book_title_zh"],
        "--book-title-zh-reading",
        plan["book_title_zh_reading"],
        "--book-title-ja",
        plan["book_title_ja"],
        "--book-title-ja-reading",
        plan["book_title_ja_reading"],
        "--author",
        plan["author"],
        "--book-description",
        plan["book_description"],
        "--chunks-jsonl",
        plan["chunks_jsonl"],
        "--manifest",
        plan["chunks_manifest"],
        "--chunk-mode",
        plan["chunk_mode"],
    ]
    run(cmd)


def select_books(manifest: dict[str, Any], selected: set[str]) -> list[dict[str, Any]]:
    books = manifest.get("books", [])
    if not selected:
        return books
    found = {book["book_id"]: book for book in books}
    missing = sorted(selected - set(found))
    if missing:
        raise SystemExit(f"unknown book id(s): {', '.join(missing)}")
    return [found[book_id] for book_id in selected]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default="data/source-plan/japanese-literature-batch.json",
        help="batch source manifest",
    )
    parser.add_argument("--book-id", action="append", default=[], help="prepare only this book id; repeatable")
    parser.add_argument("--force", action="store_true", help="rewrite markdown and chunk task files")
    parser.add_argument("--no-chunks", action="store_true", help="convert markdown only")
    args = parser.parse_args()

    manifest_path = ROOT / args.manifest
    manifest = load_json(manifest_path)
    for book in select_books(manifest, set(args.book_id)):
        book_id = book["book_id"]
        print(f"== {book_id} ==", flush=True)
        paths = prepare_markdown(book, args.force)
        launchable = book.get("status") == "launchable" and book.get("source_language") == "zh"
        plan_path = write_plan(book, paths, launchable)
        if launchable and not args.no_chunks:
            prepare_chunks(book, plan_path, args.force)
        else:
            status_path = ROOT / "books" / book_id / "work" / "prep-status.json"
            write_json(
                status_path,
                {
                    "book_id": book_id,
                    "status": book.get("status", ""),
                    "launchable": launchable,
                    "reason": "zh-jp generation requires a Chinese source in the current pipeline"
                    if book.get("source_language") != "zh"
                    else "chunks skipped by --no-chunks",
                    "source_markdown": paths["source_markdown"],
                    "prepared_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
