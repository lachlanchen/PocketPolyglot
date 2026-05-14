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
JP_ATTACHED_SUFFIXES = (
    "さんを",
    "さんが",
    "さんは",
    "だのに",
    "だの",
    "などを",
    "などに",
    "など",
    "を",
    "が",
    "は",
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
)
ZH_COMPONENT_MARKERS = {"的", "地", "得"}
ZH_ASPECT_MARKERS = {"了", "着", "过"}


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
        is_attached_jp = lang == "ja" and any(text.endswith(suffix) for suffix in JP_ATTACHED_SUFFIXES)
        is_attached_zh = lang == "zh" and text in ZH_ASPECT_MARKERS and previous_role in {"predicate", "attributive"}
        if role == "function" and (text in markers or is_attached_jp or is_attached_zh) and previous_role and previous_role != "function":
            token["g"] = previous_role
            changed += 1
            role = previous_role
        if role and role != "function" and text:
            previous_role = role
    return changed


def promote_jp_list_objects(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", "")).strip()
        if "だの" not in text and "など" not in text:
            continue
        cursor = index - 1
        touched = False
        while cursor >= 0:
            previous = tokens[cursor]
            if not isinstance(previous, dict) or normalize_role(previous.get("g", "")) != "adverbial":
                break
            previous["g"] = "object"
            changed += 1
            touched = True
            cursor -= 1
        if touched and normalize_role(token.get("g", "")) != "object":
            token["g"] = "object"
            changed += 1
    return changed


def cleanup_unit_components(unit: dict[str, Any]) -> int:
    changed = 0
    if isinstance(unit.get("zh"), list):
        changed += cleanup_component_tokens(unit["zh"], lang="zh")
    ja = unit.get("ja")
    if isinstance(ja, list):
        for line in ja:
            changed += cleanup_component_tokens(line, lang="ja")
            changed += promote_jp_list_objects(line)
            changed += cleanup_component_tokens(line, lang="ja")
    return changed


def cleanup_components(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        if isinstance(node.get("zh"), list) or isinstance(node.get("ja"), list):
            changed += cleanup_unit_components(node)
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
