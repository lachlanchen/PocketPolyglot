#!/usr/bin/env python3
"""Summarize LaTeX overfull box warnings in build logs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


HBOX_RE = re.compile(r"Overfull \\hbox \(([-0-9.]+)pt too wide\)")
VBOX_RE = re.compile(r"Overfull \\vbox \(([-0-9.]+)pt too high\)")


def scan_log(path: Path) -> tuple[list[float], list[float]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    hboxes = [float(match.group(1)) for match in HBOX_RE.finditer(text)]
    vboxes = [float(match.group(1)) for match in VBOX_RE.finditer(text)]
    return hboxes, vboxes


def summarize(root: Path) -> dict[str, object]:
    hboxes: list[tuple[float, Path]] = []
    vboxes: list[tuple[float, Path]] = []
    logs = sorted(root.rglob("*.log")) if root.is_dir() else [root]
    for log in logs:
        if not log.exists() or not log.is_file():
            continue
        hvals, vvals = scan_log(log)
        hboxes.extend((value, log) for value in hvals)
        vboxes.extend((value, log) for value in vvals)
    hboxes.sort(reverse=True, key=lambda item: item[0])
    vboxes.sort(reverse=True, key=lambda item: item[0])
    return {
        "root": str(root),
        "logs": len(logs),
        "hbox_count": len(hboxes),
        "hbox_over_5pt": sum(value > 5 for value, _ in hboxes),
        "hbox_over_20pt": sum(value > 20 for value, _ in hboxes),
        "hbox_over_50pt": sum(value > 50 for value, _ in hboxes),
        "hbox_over_100pt": sum(value > 100 for value, _ in hboxes),
        "hbox_max": hboxes[0][0] if hboxes else 0.0,
        "hbox_worst_log": str(hboxes[0][1]) if hboxes else "",
        "vbox_count": len(vboxes),
        "vbox_max": vboxes[0][0] if vboxes else 0.0,
        "vbox_worst_log": str(vboxes[0][1]) if vboxes else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        data = summarize(path)
        print(
            "{root}\tlogs={logs}\thbox={hbox_count}\tover5={hbox_over_5pt}"
            "\tover20={hbox_over_20pt}\tover50={hbox_over_50pt}\tover100={hbox_over_100pt}"
            "\tmax={hbox_max:.3f}\tworst={hbox_worst_log}\tvbox={vbox_count}\tvbox_max={vbox_max:.3f}".format(
                **data
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
