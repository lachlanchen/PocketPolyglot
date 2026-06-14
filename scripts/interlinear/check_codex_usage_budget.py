#!/usr/bin/env python3
"""Gate long Codex workers on an observable remaining-usage percentage.

This helper is deliberately conservative only when a threshold is configured.
It can read a percentage from:

- CODEX_USAGE_REMAINING_PERCENT or CODEX_WEEKLY_REMAINING_PERCENT;
- a JSON status file;
- a custom shell command whose output contains percentages such as
  "Weekly limit ... 57% left".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


PERCENT_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:left|remaining)", re.IGNORECASE)


def parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def percent_from_json(path: Path) -> tuple[float | None, str]:
    if not path.exists():
        return None, f"status file missing: {path}"
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    candidates: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key in (
            "weekly_remaining_percent",
            "remaining_percent",
            "codex_remaining_percent",
            "five_hour_remaining_percent",
            "5h_remaining_percent",
        ):
            candidates.append((key, data.get(key)))
    values = [(key, parse_percent(str(value))) for key, value in candidates if value is not None]
    values = [(key, value) for key, value in values if value is not None]
    if not values:
        return None, f"no usable percent in {path}"
    key, value = min(values, key=lambda item: item[1])
    return value, f"{path}:{key}"


def percent_from_command(command: str) -> tuple[float | None, str]:
    proc = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=60)
    text = proc.stdout + "\n" + proc.stderr
    values = [float(match.group("value")) for match in PERCENT_RE.finditer(text)]
    if not values:
        return None, "command produced no '<n>% left' value"
    return min(values), "command"


def observed_percent(args: argparse.Namespace) -> tuple[float | None, str]:
    for env_name in (
        "CODEX_USAGE_REMAINING_PERCENT",
        "CODEX_WEEKLY_REMAINING_PERCENT",
        "CODEX_5H_REMAINING_PERCENT",
    ):
        value = parse_percent(os.environ.get(env_name))
        if value is not None:
            return value, env_name
    if args.status_file:
        value, source = percent_from_json(Path(args.status_file).expanduser())
        if value is not None:
            return value, source
    command = args.status_command or os.environ.get("CODEX_USAGE_CHECK_COMMAND", "")
    if command:
        return percent_from_command(command)
    return None, "no usage source configured"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-remaining-percent", type=float, default=0)
    parser.add_argument("--status-file", default=os.environ.get("CODEX_USAGE_STATUS_FILE", ""))
    parser.add_argument("--status-command", default="")
    parser.add_argument("--allow-unknown", action="store_true")
    args = parser.parse_args()

    if args.min_remaining_percent <= 0:
        print("codex usage budget gate disabled")
        return 0
    value, source = observed_percent(args)
    if value is None:
        if args.allow_unknown:
            print(f"codex usage budget unknown; allowing because --allow-unknown is set ({source})")
            return 0
        print(f"codex usage budget unknown; waiting ({source})")
        return 86
    if value >= args.min_remaining_percent:
        print(f"codex usage budget ok: {value:.1f}% remaining from {source}")
        return 0
    print(
        f"codex usage budget low: {value:.1f}% remaining from {source}; "
        f"need >= {args.min_remaining_percent:.1f}%"
    )
    return 86


if __name__ == "__main__":
    raise SystemExit(main())
