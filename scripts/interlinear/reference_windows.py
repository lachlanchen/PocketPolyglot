#!/usr/bin/env python3
"""Utilities for broadening bilingual reference windows without rewriting tasks."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


def expand_adjacent_jp_references(chunks: list[dict[str, Any]], *, neighbor_keys: int = 1) -> list[dict[str, Any]]:
    """Return chunks whose Japanese references include neighboring reference keys.

    Chinese and Japanese editions often place chapter breaks a paragraph or two
    apart. The task file can still keep compact chapter references, while workers
    use this in-memory expansion for prompting and review validation.
    """

    if neighbor_keys <= 0:
        return chunks

    key_order: list[str] = []
    refs_by_key: dict[str, OrderedDict[str, dict[str, Any]]] = {}
    for chunk in chunks:
        key = str(chunk.get("paired_reference_key") or chunk.get("paired_story_key") or "")
        if not key:
            continue
        if key not in refs_by_key:
            refs_by_key[key] = OrderedDict()
            key_order.append(key)
        for ref in chunk.get("jp_reference", []):
            if not isinstance(ref, dict):
                continue
            ref_id = str(ref.get("id") or "")
            if not ref_id:
                continue
            refs_by_key[key].setdefault(ref_id, ref)

    key_index = {key: index for index, key in enumerate(key_order)}
    expanded: list[dict[str, Any]] = []
    for chunk in chunks:
        key = str(chunk.get("paired_reference_key") or chunk.get("paired_story_key") or "")
        if key not in key_index:
            expanded.append(chunk)
            continue

        index = key_index[key]
        keys = key_order[max(0, index - neighbor_keys) : index + neighbor_keys + 1]
        refs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for ref_key in keys:
            refs.update(refs_by_key.get(ref_key, {}))

        item = dict(chunk)
        item["jp_reference"] = list(refs.values())
        item["jp_reference_expanded_keys"] = keys
        item["jp_reference_char_count"] = sum(len(str(ref.get("text", ""))) for ref in item["jp_reference"])
        expanded.append(item)

    return expanded
