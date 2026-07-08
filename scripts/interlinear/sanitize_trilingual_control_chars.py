#!/usr/bin/env python3
"""Remove forbidden control characters from trilingual JSON artifacts.

Some PDF/OCR extraction paths encode artifacts such as BEL (``\\u0007``) or
NUL (``\\u0000``) into JSON strings.  They survive JSON validation unless we
load the file, but XeLaTeX receives real control characters and fails.  This
tool is intentionally conservative: it only removes C0 controls except tab,
newline, and carriage return, and it creates backups before writing.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED = {"\t", "\n", "\r"}


def clean_text(text: str) -> tuple[str, int]:
    cleaned_chars: list[str] = []
    removed = 0
    for ch in text:
        if ord(ch) < 32 and ch not in ALLOWED:
            removed += 1
            continue
        cleaned_chars.append(ch)
    return "".join(cleaned_chars), removed


def split_yeats_vocative_token(token: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Repair the Spark artifact ``：\\u00000，`` as the vocative "O,".

    Removing NUL leaves ``：0，``.  In the Chinese row this is intended as
    ``：哦，``.  Because Chinese Han tokens must be one character with pinyin,
    split it into valid punctuation + Han + punctuation tokens.
    """

    text = str(token.get("t", ""))
    if text not in {"：0，", ":0,", "：“0，", ':"0,'}:
        return None
    role = token.get("g") or "function"
    prefix = "：“" if text.startswith("：“") or text.startswith(':"') else "："
    suffix = "，" if "，" in text else ","
    return [
        {"t": prefix, "g": "function"},
        {"t": "哦", "r": "ō", "g": role},
        {"t": suffix, "g": "function"},
    ]


def clean_obj(value: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        output: list[Any] = []
        removed = 0
        for item in value:
            cleaned, item_removed = clean_obj(item)
            removed += item_removed
            if isinstance(cleaned, dict) and "t" in cleaned:
                split = split_yeats_vocative_token(cleaned)
                if split is not None:
                    output.extend(split)
                    continue
            output.append(cleaned)
        return output, removed
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        removed = 0
        for key, child in value.items():
            cleaned, child_removed = clean_obj(child)
            output[key] = cleaned
            removed += child_removed
        return output, removed
    return value, 0


def backup_path(path: Path, backup_root: Path) -> Path:
    return backup_root / path.as_posix()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_json(path: Path, backup_root: Path) -> tuple[int, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cleaned, removed = clean_obj(data)
    changed = cleaned != data
    if changed:
        target = backup_path(path, backup_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        write_json(path, cleaned)
    return removed, changed


def sanitize_jsonl(path: Path, backup_root: Path) -> tuple[int, bool]:
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    removed_total = 0
    changed = False
    for line in lines:
        if not line.strip():
            output.append(line)
            continue
        data = json.loads(line)
        cleaned, removed = clean_obj(data)
        removed_total += removed
        changed = changed or cleaned != data
        output.append(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")))
    if changed:
        target = backup_path(path, backup_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return removed_total, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="JSON/JSONL files or directories to sanitize")
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path("books/_backups/control-char-sanitize") / datetime.now().strftime("%Y%m%dT%H%M%S"),
    )
    args = parser.parse_args()

    files: list[Path] = []
    for path in args.paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.suffix in {".json", ".jsonl"}:
            files.append(path)

    changed_files = 0
    removed_chars = 0
    for path in files:
        if path.suffix == ".jsonl":
            removed, changed = sanitize_jsonl(path, args.backup_root)
        else:
            removed, changed = sanitize_json(path, args.backup_root)
        removed_chars += removed
        changed_files += int(changed)
        if changed:
            print(f"sanitized {path} removed={removed}")
    print(f"changed_files={changed_files} removed_control_chars={removed_chars} backup_root={args.backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
