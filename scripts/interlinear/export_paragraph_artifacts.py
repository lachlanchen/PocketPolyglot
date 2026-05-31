#!/usr/bin/env python3
"""Export completed interlinear chunks into stable paragraph artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")


def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def ja_text(unit: dict[str, Any]) -> str:
    ja = unit.get("ja")
    if not isinstance(ja, list):
        return ""
    return "".join(token_text(line) for line in ja if isinstance(line, list))


def iter_token_lists(paragraph: dict[str, Any]):
    for unit in paragraph.get("units", []):
        if isinstance(unit, dict):
            yield unit.get("zh", [])
            ja = unit.get("ja", [])
            if isinstance(ja, list):
                for line in ja:
                    yield line


def all_han_have_reading(tokens: Any) -> bool:
    if not isinstance(tokens, list):
        return False
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        reading = str(token.get("r", ""))
        if HAN_RE.search(text) and (not SINGLE_HAN_RE.fullmatch(text) or not reading):
            return False
    return True


def paragraph_features(paragraph: dict[str, Any]) -> dict[str, Any]:
    units = paragraph.get("units", [])
    zh_lists = [unit.get("zh", []) for unit in units if isinstance(unit, dict)]
    ja_lines = [
        line
        for unit in units
        if isinstance(unit, dict)
        for line in unit.get("ja", [])
        if isinstance(line, list)
    ]
    token_total = 0
    grammar_total = 0
    for tokens in iter_token_lists(paragraph):
        if not isinstance(tokens, list):
            continue
        for token in tokens:
            if not isinstance(token, dict):
                continue
            text = str(token.get("t", ""))
            if not text.strip():
                continue
            token_total += 1
            if token.get("g"):
                grammar_total += 1
    return {
        "translation": bool(units) and all(normalize(ja_text(unit)) for unit in units if isinstance(unit, dict)),
        "zh_ruby": bool(zh_lists) and all(all_han_have_reading(tokens) for tokens in zh_lists),
        "ja_ruby": bool(ja_lines) and all(all_han_have_reading(tokens) for tokens in ja_lines),
        "grammar": token_total > 0 and token_total == grammar_total,
        "token_total": token_total,
        "grammar_token_total": grammar_total,
        "unit_count": len(units) if isinstance(units, list) else 0,
    }


def feature_score(features: dict[str, Any]) -> int:
    booleans = ["translation", "zh_ruby", "ja_ruby", "grammar"]
    return sum(1000 for key in booleans if features.get(key)) + int(features.get("token_total") or 0)


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fffぁ-ゟ゠-ヿ一-龯]+", "_", name)


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("chunks", []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--replace", action="store_true", help="replace existing artifacts even when feature score is lower")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_dir = Path(args.chunk_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped_existing = 0
    skipped_stale = 0
    missing = 0

    for item in manifest_items(manifest):
        chunk_path = chunk_dir / f"{item['chunk_id']}.json"
        if not chunk_path.exists():
            missing += 1
            continue
        chunk = load_json(chunk_path)
        expected_ids = item.get("paragraph_ids", [])
        got_ids = [paragraph.get("id") for paragraph in chunk.get("paragraphs", [])]
        if chunk.get("chunk_id") != item["chunk_id"] or got_ids != expected_ids:
            skipped_stale += 1
            continue

        for paragraph in chunk.get("paragraphs", []):
            paragraph_id = str(paragraph.get("id", ""))
            source_text = str(paragraph.get("source_text", ""))
            if not paragraph_id or not source_text:
                continue
            features = paragraph_features(paragraph)
            artifact = {
                "schema_version": "0.1",
                "kind": "interlinear_paragraph_artifact",
                "book_id": manifest.get("book_id"),
                "paragraph_id": paragraph_id,
                "source_text": source_text,
                "source_sha256": sha256_text(source_text),
                "source_normalized_sha256": sha256_text(normalize(source_text)),
                "features": features,
                "source_chunk_id": chunk.get("chunk_id"),
                "source_manifest_sha256": manifest.get("source_sha256"),
                "section": chunk.get("section", {}),
                "subsection": chunk.get("subsection", {}),
                "story": chunk.get("story", {}),
                "paragraph": paragraph,
            }
            artifact_path = output_dir / f"{safe_name(paragraph_id)}.json"
            if artifact_path.exists() and not args.replace:
                old = load_json(artifact_path)
                if old.get("source_normalized_sha256") == artifact["source_normalized_sha256"]:
                    old_score = feature_score(old.get("features", {}))
                    new_score = feature_score(features)
                    if old_score > new_score:
                        skipped_existing += 1
                        continue
            artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            exported += 1

    print(
        f"exported={exported} skipped_existing={skipped_existing} "
        f"missing_chunks={missing} stale_chunks={skipped_stale} output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
