#!/usr/bin/env python3
"""Normalize token grammar roles to the English component vocabulary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROLE_ALIASES = {
    "zhu": "subject",
    "subject": "subject",
    "wei": "predicate",
    "predicate": "predicate",
    "verb": "predicate",
    "bin": "object",
    "object": "object",
    "ding": "attributive",
    "attributive": "attributive",
    "zhuang": "adverbial",
    "adverbial": "adverbial",
    "bu": "complement",
    "complement": "complement",
    "topic": "topic",
    "function": "function",
    "particle": "function",
}

JP_COMPONENT_MARKERS = {
    "は",
    "が",
    "を",
    "に",
    "へ",
    "で",
    "と",
    "も",
    "の",
    "から",
    "まで",
    "より",
    "には",
    "では",
    "にも",
    "でも",
    "とは",
    "へは",
    "をも",
}
ZH_COMPONENT_MARKERS = {"的", "地", "得"}


def normalize_role(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("role", "")
    role = str(value or "").strip().lower()
    return ROLE_ALIASES.get(role, role)


def normalize_node(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        if "g" in node:
            old = node["g"]
            new = normalize_role(old)
            if new != old:
                node["g"] = new
                changed += 1
        for legacy_key in ("role", "syntax"):
            if legacy_key in node:
                new = normalize_role(node.pop(legacy_key))
                if new and "g" not in node:
                    node["g"] = new
                changed += 1
        for value in node.values():
            changed += normalize_node(value)
    elif isinstance(node, list):
        for value in node:
            changed += normalize_node(value)
    return changed


def cleanup_component_tokens(tokens: Any, *, lang: str) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    previous_role = ""
    markers = JP_COMPONENT_MARKERS if lang == "ja" else ZH_COMPONENT_MARKERS
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", "")).strip()
        role = normalize_role(token.get("g", ""))
        if role == "function" and text in markers and previous_role and previous_role != "function":
            token["g"] = previous_role
            changed += 1
            role = previous_role
        if role and role != "function" and text:
            previous_role = role
    return changed


def cleanup_components(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        if isinstance(node.get("zh"), list):
            changed += cleanup_component_tokens(node["zh"], lang="zh")
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += cleanup_component_tokens(line, lang="ja")
        for key, value in node.items():
            if key not in {"zh", "ja"}:
                changed += cleanup_components(value)
    elif isinstance(node, list):
        for value in node:
            changed += cleanup_components(value)
    return changed


def iter_json_paths(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(child for child in path.rglob("*.json") if child.is_file()))
        elif path.is_file() and path.suffix == ".json":
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="JSON file or directory paths")
    parser.add_argument(
        "--sync-components",
        action="store_true",
        help="make attached particles/markers inherit the previous major component role",
    )
    args = parser.parse_args()

    changed_files = 0
    changed_roles = 0
    for path in iter_json_paths([Path(item) for item in args.paths]):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = normalize_node(data)
        if args.sync_components:
            changed += cleanup_components(data)
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1
            changed_roles += changed
            print(f"{path}: normalized {changed} roles")
    print(f"changed_files={changed_files} changed_roles={changed_roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
