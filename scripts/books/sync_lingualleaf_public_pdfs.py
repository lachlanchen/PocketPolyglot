#!/usr/bin/env python3
"""Sync compressed LinguaLeaf PDF artifacts into the public PDF repository.

The source repository keeps publication PDFs under ``artifacts/lingualleaf``.
This command mirrors them into ``../LinguaLeaf/docs/pocketpolyglot/books`` and
compresses with Ghostscript when the destination is missing or larger than the
best compressed candidate.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "artifacts" / "lingualleaf" / "books"
DEFAULT_DEST = ROOT.parent / "LinguaLeaf" / "docs" / "pocketpolyglot" / "books"
GITHUB_HARD_LIMIT = 100 * 1024 * 1024


def run(cmd: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def compress_pdf(source: Path, workdir: Path) -> tuple[Path, str]:
    gs = shutil.which("gs")
    if not gs:
        return source, "ghostscript-missing"
    candidate = workdir / source.name
    cmd = [
        gs,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        "-dPDFSETTINGS=/ebook",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dColorImageResolution=180",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dGrayImageResolution=180",
        "-dMonoImageResolution=300",
        f"-sOutputFile={candidate}",
        str(source),
    ]
    result = run(cmd)
    if result.returncode != 0 or not candidate.exists():
        return source, "compression-failed"
    if candidate.stat().st_size >= source.stat().st_size:
        return source, "compressed-larger"
    return candidate, "compressed"


def should_replace(source: Path, dest: Path, *, force: bool) -> bool:
    if force or not dest.exists():
        return True
    return dest.stat().st_size > source.stat().st_size


def copy_if_better(candidate: Path, dest: Path, *, force: bool, dry_run: bool) -> str:
    if dest.exists() and not force and dest.stat().st_size <= candidate.stat().st_size:
        return "kept-existing-smaller"
    if candidate.stat().st_size >= GITHUB_HARD_LIMIT:
        return "skipped-over-github-limit"
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, dest)
    return "copied"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true", help="recompress and replace even when destination exists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="lingualleaf-compress-") as tmpdir:
        workdir = Path(tmpdir)
        for source in sorted(args.source.rglob("*.pdf")):
            rel = source.relative_to(args.source)
            dest = args.dest / rel
            if not should_replace(source, dest, force=args.force):
                stats["kept-existing"] = stats.get("kept-existing", 0) + 1
                continue
            candidate, compression_status = compress_pdf(source, workdir)
            copy_status = copy_if_better(candidate, dest, force=args.force, dry_run=args.dry_run)
            key = f"{compression_status}:{copy_status}"
            stats[key] = stats.get(key, 0) + 1
            if copy_status != "kept-existing-smaller":
                print(f"{copy_status} {rel} ({compression_status})")

    for key in sorted(stats):
        print(f"{key}={stats[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
