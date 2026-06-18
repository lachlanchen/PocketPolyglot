#!/usr/bin/env python3
"""Assemble old bilingual chunks plus English overlay chunks into trilingual JSON."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from assemble_trilingual_json import plain_title, tokenize_ja_title, tokenize_zh_title
from json_to_trilingual_pair_tex import token_text


ROOT = Path(__file__).resolve().parents[2]

BOOK_METADATA: dict[str, dict[str, str]] = {
    "kokoro": {
        "title_en": "Kokoro",
        "title_zh": "心",
        "title_ja": "こころ",
        "author": "夏目漱石",
        "author_reading_ja": "なつ め そう せき",
    },
    "snow-country": {
        "title_en": "Snow Country",
        "title_zh": "雪国",
        "title_ja": "雪国",
        "author": "川端康成",
        "author_reading_ja": "かわばた やすなり",
    },
    "no-longer-human": {
        "title_en": "No Longer Human",
        "title_zh": "人间失格",
        "title_ja": "人間失格",
        "author": "太宰治",
        "author_reading_ja": "だ ざい おさむ",
    },
    "rashomon-stories": {
        "title_en": "Rashomon Stories",
        "title_zh": "罗生门短篇集",
        "title_ja": "羅生門短篇集",
        "author": "芥川龍之介",
        "author_reading_ja": "あくた がわ りゅう の すけ",
    },
    "woman-in-the-dunes": {
        "title_en": "The Woman in the Dunes",
        "title_zh": "砂女",
        "title_ja": "砂の女",
        "author": "安部公房",
        "author_reading_ja": "あ べ こう ぼう",
    },
    "kinkakuji": {
        "title_en": "The Temple of the Golden Pavilion",
        "title_zh": "金阁寺",
        "title_ja": "金閣寺",
        "author": "三島由紀夫",
        "author_reading_ja": "み しま ゆ き お",
    },
    "izu-no-odori": {
        "title_en": "The Dancing Girl of Izu",
        "title_zh": "伊豆的舞女",
        "title_ja": "伊豆の踊子",
        "author": "川端康成",
        "author_reading_ja": "かわばた やすなり",
    },
    "the-old-capital": {
        "title_en": "The Old Capital",
        "title_zh": "古都",
        "title_ja": "古都",
        "author": "川端康成",
        "author_reading_ja": "かわばた やすなり",
    },
    "genji-modern": {
        "title_en": "The Tale of Genji",
        "title_zh": "源氏物语",
        "title_ja": "源氏物語",
        "author": "紫式部",
        "author_reading_ja": "むらさき しき ぶ",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def as_root_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def plan_metadata(book_id: str) -> dict[str, str]:
    metadata = dict(BOOK_METADATA.get(book_id, {}))
    plan = ROOT / "books" / book_id / "book-plan.json"
    if plan.exists():
        data = load_json(plan)
        for source_key, target_key in (
            ("book_title_en", "title_en"),
            ("book_title_zh", "title_zh"),
            ("book_title_ja", "title_ja"),
            ("author", "author"),
            ("author_reading_ja", "author_reading_ja"),
        ):
            value = data.get(source_key)
            if value:
                metadata[target_key] = str(value)
    metadata.setdefault("title_en", book_id.replace("-", " ").title())
    metadata.setdefault("title_zh", metadata["title_en"])
    metadata.setdefault("title_ja", metadata["title_en"])
    metadata.setdefault("author", "")
    metadata.setdefault("author_reading_ja", "")
    return metadata


def normalize_tokens(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        flattened: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                flattened.append(dict(item))
            elif isinstance(item, list):
                flattened.extend(normalize_tokens(item))
            elif item is not None:
                flattened.append({"t": str(item)})
        return flattened
    if isinstance(value, dict):
        return [dict(value)]
    return [{"t": str(value)}]


def title_from_chunk(chunk: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    title_key = f"title_{lang}"
    for key in ("subsection", "story", "section"):
        node = chunk.get(key) or {}
        tokens = normalize_tokens(node.get(title_key))
        if token_text(tokens).strip():
            return tokens
    fallback = str((chunk.get("story") or {}).get("id") or (chunk.get("section") or {}).get("id") or "")
    return plain_title(fallback)


def chapter_id(chunk: dict[str, Any]) -> str:
    for key in ("story", "section", "subsection"):
        node = chunk.get(key) or {}
        value = str(node.get("id") or "").strip()
        if value and value != "main":
            return value
    return "main"


def chapter_title_en(chunk: dict[str, Any]) -> list[dict[str, str]]:
    zh = token_text(title_from_chunk(chunk, "zh")).strip()
    ja = token_text(title_from_chunk(chunk, "ja")).strip()
    label = zh or ja or chapter_id(chunk)
    return plain_title(label)


def load_overlay_units(path: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    data = load_json(path)
    units: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for unit in data.get("units", []):
        paragraph_id = str(unit.get("paragraph_id") or "")
        unit_index = int(unit.get("unit_index") or 0)
        en = normalize_tokens(unit.get("en"))
        if paragraph_id and unit_index > 0 and en:
            units[(paragraph_id, unit_index)] = en
    return units


def first_existing(paths: list[str]) -> Path | None:
    for candidate in paths:
        path = as_root_path(candidate)
        if path.exists():
            return path
    return None


def matching_base_title(tasks: list[dict[str, Any]], metadata: dict[str, str], lang: str) -> list[dict[str, Any]] | None:
    if not tasks:
        return None
    base_path = first_existing([str(path) for path in tasks[0].get("base_chunk_candidates", [])])
    if not base_path:
        return None
    title = title_from_chunk(load_json(base_path), lang)
    return title if token_text(title).strip() == metadata[f"title_{lang}"].strip() else None


def assemble(book_id: str, allow_missing: bool) -> dict[str, Any]:
    source_manifest = ROOT / "data" / "source-plan" / "incremental-en-modern-ja" / book_id / "manifest.json"
    if not source_manifest.exists():
        raise FileNotFoundError(source_manifest)
    source_plan = load_json(source_manifest)
    tasks = load_jsonl(as_root_path(source_plan["tasks_jsonl"]))
    metadata = plan_metadata(book_id)
    base_title_zh = matching_base_title(tasks, metadata, "zh")
    base_title_ja = matching_base_title(tasks, metadata, "ja")
    chapters: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    missing: list[dict[str, str]] = []
    assembled_chunks = 0
    assembled_units = 0

    for task in tasks:
        chunk_id = str(task["chunk_id"])
        base_path = first_existing([str(path) for path in task.get("base_chunk_candidates", [])])
        overlay_path = as_root_path(task.get("durable_overlay_path") or task.get("output_overlay_path") or "")
        if not base_path or not overlay_path.exists():
            if allow_missing:
                missing.append({"chunk_id": chunk_id, "reason": "missing base or overlay"})
                continue
            raise FileNotFoundError(f"{chunk_id}: base={base_path} overlay={overlay_path}")

        chunk = load_json(base_path)
        overlays = load_overlay_units(overlay_path)
        chapter_key = chapter_id(chunk)
        chapter = chapters.setdefault(
            chapter_key,
            {
                "id": chapter_key,
                "number": str(len(chapters) + 1),
                "title": {
                    "en": chapter_title_en(chunk),
                    "ja": title_from_chunk(chunk, "ja"),
                    "zh": title_from_chunk(chunk, "zh"),
                },
                "paragraphs": [],
            },
        )
        for paragraph in chunk.get("paragraphs", []):
            paragraph_id = str(paragraph.get("id") or "")
            output_paragraph = {"id": paragraph_id, "units": []}
            for index, unit in enumerate(paragraph.get("units", []), start=1):
                en = overlays.get((paragraph_id, index))
                if not en:
                    if allow_missing:
                        continue
                    raise ValueError(f"{chunk_id}: missing English overlay for {paragraph_id} unit {index}")
                output_paragraph["units"].append(
                    {
                        "source_zh": str(unit.get("source_text") or ""),
                        "en": en,
                        "ja": normalize_tokens(unit.get("ja")),
                        "zh": normalize_tokens(unit.get("zh")),
                    }
                )
                assembled_units += 1
            if output_paragraph["units"]:
                chapter["paragraphs"].append(output_paragraph)
        assembled_chunks += 1

    return {
        "schema_version": "0.2",
        "mode": "trilingual_standard",
        "title": {
            "en": plain_title(metadata["title_en"]),
            "zh": base_title_zh or tokenize_zh_title(metadata["title_zh"]),
            "ja": base_title_ja or plain_title(metadata["title_ja"]),
        },
        "author": {
            "name": metadata["author"],
            "reading_ja": metadata["author_reading_ja"],
        },
        "source": {
            "source_manifest": str(source_manifest.relative_to(ROOT)),
            "assembled_chunk_count": assembled_chunks,
            "total_chunk_count": int(source_plan.get("chunk_count") or len(tasks)),
            "assembled_unit_count": assembled_units,
            "missing_count": len(missing),
            "missing": missing,
            "note": "Assembled from read-only bilingual base chunks plus incremental English overlay chunks.",
        },
        "chapters": list(chapters.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    book = assemble(args.book_id, args.allow_missing)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
