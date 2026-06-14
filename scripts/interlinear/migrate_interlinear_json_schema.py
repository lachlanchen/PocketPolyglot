#!/usr/bin/env python3
"""Add PocketPolyglot v2 layer metadata to durable chunk JSON.

The migration is intentionally additive:

- existing token fields such as zh, zh_original, zh_modern, ja, en, jie, zhu,
  and explanation are preserved;
- ambiguous Japanese line arrays receive ja_line_roles;
- a compact pp_schema contract records how legacy fields should be understood;
- each changed file is copied to a local backup directory before rewriting.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_ROOT = ROOT / "backups" / f"interlinear-json-v2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_tracked_json_paths() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "data/interlinear/*/chunks/*.json"],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    )
    return [ROOT / line for line in proc.stdout.splitlines() if line.strip()]


def find_json_paths(book_ids: list[str], *, tracked_only: bool) -> list[Path]:
    if tracked_only:
        paths = git_tracked_json_paths()
    else:
        paths = sorted((ROOT / "data" / "interlinear").glob("*/chunks/*.json"))
    if book_ids:
        wanted = set(book_ids)
        paths = [path for path in paths if path.parts[-3] in wanted]
    return sorted(paths)


def tokens_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if value and all(isinstance(item, list) for item in value):
            return "".join(tokens_text(item) for item in value)
        return "".join(str(token.get("t", "")) for token in value if isinstance(token, dict))
    return ""


def iter_units(data: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for paragraph in data.get("paragraphs", []) or []:
        if not isinstance(paragraph, dict):
            continue
        paragraph_units = paragraph.get("units")
        if isinstance(paragraph_units, list):
            units.extend(unit for unit in paragraph_units if isinstance(unit, dict))
    return units


def has_field(units: list[dict[str, Any]], field: str) -> bool:
    return any(field in unit and tokens_text(unit.get(field)).strip() for unit in units)


def infer_book_type(book_id: str, units: list[dict[str, Any]]) -> str:
    if has_field(units, "zh_original"):
        return "classical_chinese"
    if book_id.startswith(("sishu", "shiji")):
        return "classical_chinese"
    if has_field(units, "source_en") or has_field(units, "en"):
        return "modern_trilingual"
    return "modern_bilingual"


def line_roles_for(book_id: str, unit: dict[str, Any], ja: list[Any]) -> list[str]:
    existing = unit.get("ja_line_roles")
    if isinstance(existing, list) and len(existing) == len(ja):
        return [str(role).strip() for role in existing]
    if book_id == "sishu-jizhu-aginti" and len(ja) >= 2:
        return ["gloss", "explanatory_comment"] + ["continuation"] * (len(ja) - 2)
    return ["translation"] + ["continuation"] * (len(ja) - 1)


def layer_contract(book_id: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    book_type = infer_book_type(book_id, units)
    layers: list[dict[str, str]] = []
    notes: list[dict[str, str]] = []

    def add_layer(layer_id: str, field: str, lang: str, role: str, register: str) -> None:
        if has_field(units, field):
            layers.append(
                {
                    "id": layer_id,
                    "field": field,
                    "lang": lang,
                    "role": role,
                    "register": register,
                }
            )

    add_layer("wenyan", "zh_original", "zh", "source", "classical")
    if not has_field(units, "zh_original"):
        register = "classical" if book_type == "classical_chinese" else "modern"
        add_layer("zh", "zh", "zh", "source" if book_type != "modern_trilingual" else "translation", register)
    add_layer("zh_modern", "zh_modern", "zh", "translation", "modern")
    add_layer("en", "en", "en", "translation", "modern")
    add_layer("ja", "ja", "ja", "translation_or_gloss", "modern_or_kanbun")
    add_layer("ja_modern", "ja_modern", "ja", "translation", "modern")

    for field in ("jie", "zhu", "explanation", "comment", "note"):
        if has_field(units, field):
            notes.append({"field": field, "role": "extra_explanation", "preserve": "true"})

    return {
        "name": "pocketpolyglot.chunk",
        "version": 2,
        "book_type": book_type,
        "legacy_fields_preserved": True,
        "line_role_policy": "ja_line_roles marks continuation versus separate explanation; do not infer that ja[1] is a note unless its role says so.",
        "layers": layers,
        "extra_notes": notes,
    }


def migrate_data(book_id: str, data: dict[str, Any]) -> bool:
    changed = False
    units = iter_units(data)
    schema = layer_contract(book_id, units)
    if data.get("pp_schema") != schema:
        data["pp_schema"] = schema
        changed = True

    for unit in units:
        ja = unit.get("ja")
        if not (isinstance(ja, list) and ja and all(isinstance(line, list) for line in ja)):
            continue
        roles = line_roles_for(book_id, unit, ja)
        if unit.get("ja_line_roles") != roles:
            unit["ja_line_roles"] = roles
            changed = True
    return changed


def backup_file(path: Path, backup_root: Path) -> Path:
    relative = path.relative_to(ROOT)
    backup_path = backup_root / relative
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", default=[], help="Limit migration to one book id; repeatable.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--include-untracked", action="store_true", help="Also migrate untracked local data/interlinear chunk JSON.")
    args = parser.parse_args()

    paths = find_json_paths(args.book_id, tracked_only=not args.include_untracked)
    changed = 0
    failed = 0
    for path in paths:
        book_id = path.parts[-3]
        try:
            data = load_json(path)
            if not isinstance(data, dict):
                continue
            if not migrate_data(book_id, data):
                continue
            changed += 1
            if not args.dry_run:
                if not args.no_backup:
                    backup_file(path, args.backup_root)
                write_json(path, data)
        except Exception as exc:  # noqa: BLE001 - migration report should keep going
            failed += 1
            print(f"failed\t{path.relative_to(ROOT)}\t{exc}")
    print(f"scanned={len(paths)} changed={changed} failed={failed}")
    if changed and not args.dry_run and not args.no_backup:
        print(f"backup_root={args.backup_root}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
