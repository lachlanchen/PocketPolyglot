#!/usr/bin/env python3
"""Validate editable textbook pocket builds and write a compact report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OVERFULL_RE = re.compile(r"Overfull \\hbox \(([-0-9.]+)pt too wide\).*?lines? ([0-9]+)(?:--([0-9]+))?")
FLOAT_RE = re.compile(r"Float too large for page by ([-0-9.]+)pt on input line ([0-9]+)")
ERROR_RE = re.compile(r"(! (?:LaTeX|Package|Undefined|Missing|Emergency|File).*|Fatal|Erroneous nesting|Unable to load)")
MISSING_IMAGE_RE = re.compile(r"(Unable to load picture|File `[^']+' not found|LaTeX Warning: File `[^']+' not found)")
SUSPECT_RE = re.compile(
    r"computational nuysice|diffentiable|destroving|Descretize|practioners|allsp|"
    r"Chapter summary\s*[0-9]+Exercises|D0．|OH：|计算|物项|听并|Holograph",
    re.I,
)


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def pdfinfo(pdf: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in run(["pdfinfo", str(pdf)]).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return info


def source_excerpt(source: Path, line: int, context: int = 2) -> list[str]:
    if not source.exists() or line <= 0:
        return []
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, line - context)
    end = min(len(lines), line + context)
    return [f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1)]


def validate(build_dir: Path) -> dict[str, Any]:
    pdfs = sorted(build_dir.glob("*english-pocket.pdf"))
    pdf = pdfs[0] if pdfs else None
    log = sorted(build_dir.glob("*english-pocket.log"))
    log_path = log[0] if log else build_dir / "missing.log"
    source = build_dir / "source.tex"
    log_text = read(log_path)
    source_text = read(source)

    overfull = [
        {
            "pt": float(match.group(1)),
            "line_start": int(match.group(2)),
            "line_end": int(match.group(3) or match.group(2)),
            "excerpt": source_excerpt(source, int(match.group(2)), context=1),
        }
        for match in OVERFULL_RE.finditer(log_text)
    ]
    overfull.sort(key=lambda item: item["pt"], reverse=True)

    floats = [
        {
            "pt": float(match.group(1)),
            "line": int(match.group(2)),
            "excerpt": source_excerpt(source, int(match.group(2)), context=1),
        }
        for match in FLOAT_RE.finditer(log_text)
    ]
    floats.sort(key=lambda item: item["pt"], reverse=True)

    suspects = []
    for idx, line in enumerate(source_text.splitlines(), start=1):
        if SUSPECT_RE.search(line):
            suspects.append({"line": idx, "text": line[:300]})

    report: dict[str, Any] = {
        "build_dir": str(build_dir.relative_to(ROOT)),
        "pdf": str(pdf.relative_to(ROOT)) if pdf else None,
        "pdfinfo": pdfinfo(pdf) if pdf else {},
        "log": str(log_path.relative_to(ROOT)) if log_path.exists() else None,
        "overfull_count": len(overfull),
        "worst_overfull": overfull[:25],
        "float_too_large_count": len(floats),
        "worst_float_too_large": floats[:25],
        "error_markers": ERROR_RE.findall(log_text)[:50],
        "suspect_ocr_count": len(suspects),
        "suspect_ocr": suspects[:80],
        "missing_image_count": len(MISSING_IMAGE_RE.findall(log_text)),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    build_dir = ROOT / args.build_dir
    report = validate(build_dir)
    output = ROOT / args.output if args.output else build_dir / "validation-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
