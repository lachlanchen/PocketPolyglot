#!/usr/bin/env python3
"""Normalize untranslated note fragments in trilingual poetry chunks.

This is intentionally conservative. It does not translate critical apparatus.
When a Japanese row is merely an English/Latin note fragment with no kana or
furigana evidence, it labels the exact fragment as a source note. If the Chinese
row is likewise non-Han, it receives the same source-note wrapper.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa]")
LATIN_RE = re.compile(r"[A-Za-z]")
LATIN_OR_NUMERIC_FRAGMENT_RE = re.compile(r"^[\s\w\d\[\]().,:;:：，。；、'’\"“”\-–—/]+$", re.I)


def token_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(str(token.get("t", "")) for token in value if isinstance(token, dict)).strip()


def ja_has_kana_evidence(tokens: Any) -> bool:
    if not isinstance(tokens, list):
        return False
    for token in tokens:
        if not isinstance(token, dict):
            continue
        if KANA_RE.search(str(token.get("t", ""))) or KANA_RE.search(str(token.get("r", ""))):
            return True
    return False


def zh_note_tokens(fragment: str) -> list[dict[str, str]]:
    return [
        {"t": "原", "r": "yuán", "g": "topic"},
        {"t": "文", "r": "wén", "g": "topic"},
        {"t": "注", "r": "zhù", "g": "topic"},
        {"t": "记", "r": "jì", "g": "topic"},
        {"t": "："},
        {"t": fragment, "g": "object"},
    ]


def ja_note_tokens(fragment: str) -> list[dict[str, str]]:
    return [
        {"t": "原", "r": "げん", "g": "topic"},
        {"t": "文", "r": "ぶん", "g": "topic"},
        {"t": "の", "g": "function"},
        {"t": "注", "r": "ちゅう", "g": "topic"},
        {"t": "記", "r": "き", "g": "topic"},
        {"t": "："},
        {"t": fragment, "g": "object"},
    ]


def repair_unit(unit: dict[str, Any]) -> int:
    changed = 0
    ja_tokens = unit.get("ja")
    ja_text = token_text(ja_tokens)
    ja_is_short_harmless_fragment = bool(LATIN_OR_NUMERIC_FRAGMENT_RE.fullmatch(ja_text)) and len(ja_text) <= 80
    if (
        ja_text
        and not ja_has_kana_evidence(ja_tokens)
        and not ja_is_short_harmless_fragment
        and (LATIN_RE.search(ja_text) or re.search(r"\d", ja_text))
    ):
        unit["ja"] = ja_note_tokens(ja_text)
        changed += 1
        zh_tokens = unit.get("zh")
        zh_text = token_text(zh_tokens)
        if zh_text and not HAN_RE.search(zh_text) and (LATIN_RE.search(zh_text) or re.search(r"\d", zh_text)):
            unit["zh"] = zh_note_tokens(zh_text)
            changed += 1
    return changed


def repair_file(path: Path, backup_dir: Path | None, dry_run: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for paragraph in data.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        for unit in paragraph.get("units") or []:
            if isinstance(unit, dict):
                changed += repair_unit(unit)
    if changed and not dry_run:
        if backup_dir is not None:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / path.name)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", action="append", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=Path("books/_backups/poetry-note-fragment-repair"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total_files = 0
    total_changes = 0
    for chunk_dir in args.chunk_dir:
        book_id = chunk_dir.parts[1] if len(chunk_dir.parts) > 1 and chunk_dir.parts[0] == "books" else chunk_dir.name
        backup_dir = None if args.dry_run else args.backup_root / stamp / book_id
        book_files = 0
        book_changes = 0
        for path in sorted(chunk_dir.glob("*.json")):
            changed = repair_file(path, backup_dir, args.dry_run)
            if changed:
                print(f"{path}: changed_rows={changed}")
                book_files += 1
                book_changes += changed
        print(f"book={book_id} changed_files={book_files} changed_rows={book_changes}")
        total_files += book_files
        total_changes += book_changes
    print(f"changed_files={total_files}")
    print(f"changed_rows={total_changes}")
    if not args.dry_run:
        print(f"backup_root={args.backup_root / stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
