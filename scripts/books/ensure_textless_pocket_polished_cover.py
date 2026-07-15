#!/usr/bin/env python3
"""Create or validate a textless cover background for PocketPolished output."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "build-pocket-polished"


def image_dimensions(path: Path) -> tuple[int, int]:
    process = subprocess.run(
        ["identify", "-format", "%w %h", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode:
        return 0, 0
    try:
        width, height = process.stdout.split()
        return int(width), int(height)
    except (ValueError, IndexError):
        return 0, 0


def valid_cover(path: Path) -> bool:
    width, height = image_dimensions(path)
    return path.is_file() and path.stat().st_size >= 10_000 and width >= 1000 and height > width


def write_summary(book_id: str, source: Path, target: Path) -> None:
    width, height = image_dimensions(source)
    summary = {
        "schema_version": 1,
        "book_id": book_id,
        "background": str(source.relative_to(ROOT)),
        "build_cover": str(target.relative_to(ROOT)),
        "width": width,
        "height": height,
        "text_policy": "textless-background-with-deterministic-tex-overlay",
        "valid": valid_cover(source),
    }
    path = OUTPUT_ROOT / book_id / "cover/summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_cover(book_id: str, model: str, reasoning: str) -> int:
    manifest_path = OUTPUT_ROOT / book_id / "tasks/manifest.json"
    if not manifest_path.is_file():
        print(f"missing polish manifest: {manifest_path}")
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    background = ROOT / "assets/covers" / book_id / "cover.png"
    target = ROOT / "build-pocket" / book_id / "cover/cover.png"
    if not valid_cover(background):
        background.parent.mkdir(parents=True, exist_ok=True)
        prompt = f"""Create one final textless portrait cover background for a technical PocketPolished book.

Book: {manifest.get('title', book_id)}
Author: {manifest.get('author', '')}
Source: {manifest.get('source', '')}
Output path: {background}

Use the installed image-generation skill. Inspect only enough source metadata to understand the subject. Generate a refined, calm, high-end portrait bitmap around 1536x2165 pixels that visually represents the actual subject. Reserve a quiet central area for a deterministic title overlay added later by TeX.

The bitmap itself must contain absolutely no title, author, letters, words, numerals, equations, pseudo-writing, logos, seals, stamps, signatures, or watermarks in any language. Do not edit any TeX, JSON, PDF, or other cover. Save exactly one PNG at the requested path and verify it is portrait and at least 1000 pixels wide.
"""
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "-C",
            str(ROOT),
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning}"',
            "-c",
            'approval_policy="never"',
            "-s",
            "workspace-write",
            "-",
        ]
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            text=True,
            check=False,
        )
        if process.returncode:
            return process.returncode
    if not valid_cover(background):
        print(f"cover generation did not produce a valid portrait PNG: {background}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(background, target)
    write_summary(book_id, background, target)
    print(f"cover: {background.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning", default="low", choices=["low", "medium", "high", "xhigh"])
    args = parser.parse_args()
    return ensure_cover(args.book_id, args.model, args.reasoning)


if __name__ == "__main__":
    raise SystemExit(main())
