#!/usr/bin/env python3
"""Generate incremental English / modern-Japanese overlay chunks.

The worker reads task manifests from data/source-plan, treats all old chunk JSON
as read-only, and writes additive overlay JSON files. It is safe to run many
instances in parallel because chunks are claimed by directory lock.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_chunk_worker import extract_json, mentions_usage_limit, run_codex
from validate_interlinear_json import GRAMMAR_ROLES, HAN_RE, SINGLE_HAN_RE, validate_ja_tokens


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(text: str) -> str:
    return "".join(str(text or "").split())


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def ja_lines_text(lines: Any) -> str:
    if not isinstance(lines, list):
        return ""
    if lines and all(isinstance(token, dict) for token in lines):
        return token_text(lines)
    return "".join(token_text(line) for line in lines if isinstance(line, list))


def read_tokens_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return token_text(value)
    return ""


def first_existing(paths: list[str]) -> Path | None:
    for raw in paths:
        path = ROOT / raw
        if path.exists():
            return path
    return None


def source_text_from_unit(unit: dict[str, Any]) -> str:
    for key in ("zh_modern", "corrected_text", "source_text"):
        value = unit.get(key)
        text = read_tokens_text(value)
        if text.strip():
            return text
    for key in ("zh", "zh_original"):
        text = read_tokens_text(unit.get(key))
        if text.strip():
            return text
    return ""


def original_text_from_unit(unit: dict[str, Any]) -> str:
    for key in ("source_text", "zh_original", "zh"):
        text = read_tokens_text(unit.get(key))
        if text.strip():
            return text
    return source_text_from_unit(unit)


def legacy_ja_text(unit: dict[str, Any]) -> str:
    ja = unit.get("ja")
    if isinstance(ja, list):
        return ja_lines_text(ja)
    return ""


def source_paragraph_text(paragraph: dict[str, Any]) -> str:
    for key in ("corrected_text", "source_text"):
        text = str(paragraph.get(key, "")).strip()
        if text:
            return text
    units = paragraph.get("units")
    if isinstance(units, list):
        return "".join(source_text_from_unit(unit) for unit in units if isinstance(unit, dict))
    return ""


def unit_blueprint(base: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(base.get("paragraphs", []) or [], start=1):
        if not isinstance(paragraph, dict):
            continue
        paragraph_id = str(paragraph.get("id") or f"p{paragraph_index:05d}")
        for unit_index, unit in enumerate(paragraph.get("units", []) or [], start=1):
            if not isinstance(unit, dict):
                continue
            units.append(
                {
                    "paragraph_id": paragraph_id,
                    "unit_index": unit_index,
                    "source_text": source_text_from_unit(unit),
                    "source_original": original_text_from_unit(unit),
                    "legacy_ja": legacy_ja_text(unit),
                }
            )
    return units


def context_summary(base: dict[str, Any]) -> dict[str, Any]:
    def text_node(node: Any) -> str:
        if not isinstance(node, dict):
            return ""
        for key in ("title", "id"):
            if str(node.get(key, "")).strip():
                return str(node[key])
        for key in ("title_zh", "title_ja"):
            text = read_tokens_text(node.get(key))
            if text.strip():
                return text
        return ""

    paragraphs = []
    for index, paragraph in enumerate(base.get("paragraphs", []) or [], start=1):
        if isinstance(paragraph, dict):
            paragraphs.append(
                {
                    "id": str(paragraph.get("id") or f"p{index:05d}"),
                    "source_text": str(paragraph.get("source_text", "")),
                    "corrected_text": str(paragraph.get("corrected_text", "")),
                    "preferred_text": source_paragraph_text(paragraph),
                }
            )
    return {
        "section": text_node(base.get("section")),
        "subsection": text_node(base.get("subsection")),
        "story": text_node(base.get("story")),
        "paragraphs": paragraphs,
    }


def validate_en_tokens(tokens: Any, where: str, errors: list[str]) -> str:
    if not isinstance(tokens, list) or not tokens:
        errors.append(f"{where}: en must be a non-empty token list")
        return ""
    text_parts: list[str] = []
    has_latin = False
    for index, token in enumerate(tokens):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}[{index}]: token must be an object with t")
            continue
        text = str(token.get("t", ""))
        text_parts.append(text)
        has_latin = has_latin or any("A" <= char <= "Z" or "a" <= char <= "z" for char in text)
        role = token.get("g")
        if role and role not in GRAMMAR_ROLES:
            errors.append(f"{where}[{index}]: unsupported grammar role {role!r}")
        if token.get("r"):
            errors.append(f"{where}[{index}]: English tokens must not have readings")
    text = "".join(text_parts)
    if not has_latin:
        errors.append(f"{where}: English appears to contain no Latin letters")
    return text


def validate_ja_modern(lines: Any, where: str, errors: list[str]) -> str:
    if not isinstance(lines, list) or not lines:
        errors.append(f"{where}: ja_modern must be a non-empty token line list")
        return ""
    normalized_lines = lines if lines and isinstance(lines[0], list) else [lines]
    for line_index, line in enumerate(normalized_lines):
        validate_ja_tokens(line, f"{where}[{line_index}]", errors)
    text = ja_lines_text(normalized_lines)
    if not text.strip():
        errors.append(f"{where}: ja_modern text is empty")
    if not any("\u3040" <= char <= "\u30ff" for char in text):
        errors.append(f"{where}: ja_modern needs real kana, not only Chinese/kanji text")
    if compact(text) in {"注", "注。"}:
        errors.append(f"{where}: ja_modern is a placeholder")
    return text


def validate_overlay(base: dict[str, Any], task: dict[str, Any], manifest: dict[str, Any], overlay: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    book_id = manifest["book_id"]
    chunk_id = task["chunk_id"]
    actions = {action["field"] for action in manifest["actions"]}
    if overlay.get("book_id") != book_id:
        errors.append(f"book_id mismatch: expected {book_id}")
    if overlay.get("chunk_id") != chunk_id:
        errors.append(f"chunk_id mismatch: expected {chunk_id}")
    units = overlay.get("units")
    if not isinstance(units, list):
        return errors + ["units must be a list"]
    blueprint = unit_blueprint(base)
    if len(units) != len(blueprint):
        errors.append(f"unit count mismatch: expected {len(blueprint)}, got {len(units)}")
    for index, expected in enumerate(blueprint):
        if index >= len(units) or not isinstance(units[index], dict):
            errors.append(f"units[{index}]: missing unit object")
            continue
        unit = units[index]
        if unit.get("paragraph_id") != expected["paragraph_id"]:
            errors.append(f"units[{index}]: paragraph_id mismatch")
        if int(unit.get("unit_index", -1)) != expected["unit_index"]:
            errors.append(f"units[{index}]: unit_index mismatch")
        if compact(str(unit.get("source_text", ""))) != compact(expected["source_text"]):
            errors.append(f"units[{index}]: source_text changed")
        if "en" in actions:
            validate_en_tokens(unit.get("en"), f"units[{index}].en", errors)
        if "ja_modern" in actions:
            validate_ja_modern(unit.get("ja_modern"), f"units[{index}].ja_modern", errors)
        if "ja" in unit:
            errors.append(f"units[{index}]: overlay must not overwrite legacy ja")
        if "zh" in unit:
            errors.append(f"units[{index}]: overlay must not overwrite legacy zh")
    return errors


def normalize_overlay_for_task(overlay: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Drop fields that would rewrite base data instead of adding overlays."""
    actions = {action["field"] for action in manifest["actions"]}
    units = overlay.get("units")
    if not isinstance(units, list):
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit.pop("zh", None)
        unit.pop("zh_original", None)
        unit.pop("zh_modern", None)
        unit.pop("ja", None)
        if "en" not in actions:
            unit.pop("en", None)
        if "ja_modern" not in actions:
            unit.pop("ja_modern", None)


def valid_existing(path: Path, base: dict[str, Any], task: dict[str, Any], manifest: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        overlay = load_json(path)
    except Exception:
        return False
    return not validate_overlay(base, task, manifest, overlay)


def claim_chunk(claim_dir: Path, claim_key: str, worker_id: str, ttl_seconds: int) -> bool:
    claim_path = claim_dir / claim_key
    now = time.time()
    try:
        claim_path.mkdir(parents=True)
    except FileExistsError:
        owner_alive = False
        try:
            owner = load_json(claim_path / "owner.json")
            pid = int(owner.get("pid", 0))
            if pid > 0:
                os.kill(pid, 0)
                owner_alive = True
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            age = now - claim_path.stat().st_mtime
            if age < 30:
                return False
        except ProcessLookupError:
            owner_alive = False
        except PermissionError:
            owner_alive = True
        if owner_alive:
            age = now - claim_path.stat().st_mtime
            if ttl_seconds <= 0 or age <= ttl_seconds:
                return False
        shutil.rmtree(claim_path, ignore_errors=True)
        try:
            claim_path.mkdir(parents=True)
        except FileExistsError:
            return False
    write_json(claim_path / "owner.json", {"worker_id": worker_id, "pid": os.getpid(), "claimed_at": now})
    return True


def release_claim(claim_dir: Path, claim_key: str) -> None:
    shutil.rmtree(claim_dir / claim_key, ignore_errors=True)


def prompt_for_overlay(
    *,
    base: dict[str, Any],
    task: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str] | None,
) -> str:
    actions = {action["field"] for action in manifest["actions"]}
    need_en = "en" in actions
    need_ja = "ja_modern" in actions
    unit_items = unit_blueprint(base)
    error_block = ""
    if errors:
        error_block = "\nPrevious output failed validation. Fix these exact issues:\n" + "\n".join(
            f"- {error}" for error in errors[:80]
        )
    unit_shape = []
    for item in unit_items:
        node: dict[str, Any] = {
            "paragraph_id": item["paragraph_id"],
            "unit_index": item["unit_index"],
            "source_text": item["source_text"],
        }
        if need_en:
            node["en"] = [{"t": "Natural English translation with spaces between words.", "g": "predicate"}]
        if need_ja:
            node["ja_modern"] = [[{"t": "読", "r": "よ", "g": "predicate"}, {"t": "みやすい日本語。", "r": "", "g": "function"}]]
        unit_shape.append(node)

    language_requirements = []
    if need_en:
        language_requirements.append(
            "- Add `en` to every unit as a token list. It must be natural, understandable English. Preserve spaces between English words. English tokens never have `r` readings."
        )
    if need_ja:
        language_requirements.append(
            "- Add `ja_modern` to every unit as one or two short token lines. It must be modern, plain, understandable Japanese based on the preferred Chinese meaning, not kanbun gloss and not Chinese prose."
        )
    return textwrap.dedent(
        f"""
        You are backfilling one additive overlay chunk for a PocketPolyglot/LinguaLeaf book.

        Return exactly one JSON object. No Markdown fences. No explanation.

        Required object:
        {{
          "schema_version": 1,
          "task_family": "incremental_english_modern_japanese_overlay",
          "book_id": "{manifest['book_id']}",
          "chunk_id": "{task['chunk_id']}",
          "units": {json.dumps(unit_shape, ensure_ascii=False, indent=2)}
        }}

        Hard requirements:
        - Do not rewrite old JSON. This output is an overlay only.
        - Preserve every `paragraph_id`, `unit_index`, and `source_text` exactly as provided.
        - Produce one output unit for every input unit, in the same order.
        - Use the preferred Chinese text as meaning source. For classical Chinese, rely on `zh_modern` if present.
        - Use legacy Japanese only as a reference; if it is difficult, kanbun-like, or unnatural, create readable modern Japanese.
        - Japanese tokenization is strict: every kanji character must be its own token with furigana in `r`. Furigana may only be attached to one-kanji tokens. Kana, okurigana, punctuation, Latin text, Arabic numerals, and spaces have no reading.
        - Use optional `g` roles only from: {", ".join(sorted(GRAMMAR_ROLES))}.
        {chr(10).join(language_requirements)}
        {error_block}

        Book and chapter context:
        {json.dumps(context_summary(base), ensure_ascii=False, indent=2)}

        Unit sources:
        {json.dumps(unit_items, ensure_ascii=False, indent=2)}
        """
    ).strip()


def load_book_tasks(book_manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_json(book_manifest_path)
    tasks_path = ROOT / manifest["tasks_jsonl"]
    tasks = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return manifest, tasks


def iter_claimable_tasks(global_manifest: dict[str, Any], include_waiting_dependencies: bool) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for book in sorted(global_manifest.get("books", []), key=lambda item: item.get("priority", 9999)):
        if book.get("dependency") != "base_chunks_exist" and not include_waiting_dependencies:
            continue
        manifest_path = book.get("manifest_path") or f"data/source-plan/incremental-en-modern-ja/{book['book_id']}/manifest.json"
        manifest, tasks = load_book_tasks(ROOT / manifest_path)
        selected.extend((manifest, task) for task in tasks)
    return selected


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": now_iso(), **extra}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-manifest", default="data/source-plan/incremental-english-modern-japanese.json")
    parser.add_argument("--work-dir", default="books/_incremental-overlays/work/en-modern-ja")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--include-waiting-dependencies", action="store_true")
    args = parser.parse_args()

    global_manifest = load_json(ROOT / args.global_manifest)
    work_dir = ROOT / args.work_dir
    claim_dir = work_dir / "claims"
    failed_dir = work_dir / "failed"
    rejected_dir = work_dir / "rejected"
    status_dir = work_dir / "status"
    prompt_dir = work_dir / args.worker_id / "prompts"
    message_dir = work_dir / args.worker_id / "messages"
    log_dir = work_dir / args.worker_id / "logs"
    for path in (claim_dir, failed_dir, rejected_dir, status_dir, prompt_dir, message_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    tasks = iter_claimable_tasks(global_manifest, args.include_waiting_dependencies)
    while True:
        claimed: tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path, str] | None = None
        for manifest, task in tasks:
            book_id = manifest["book_id"]
            chunk_id = task["chunk_id"]
            claim_key = f"{book_id}__{chunk_id}"
            base_path = first_existing(task.get("base_chunk_candidates", []))
            if base_path is None:
                write_json(status_dir / f"{claim_key}.json", status_record("missing_base_chunk", book_id=book_id, chunk_id=chunk_id))
                continue
            base = load_json(base_path)
            overlay_path = ROOT / task["output_overlay_path"]
            durable_path = ROOT / task["durable_overlay_path"]
            if valid_existing(overlay_path, base, task, manifest) or valid_existing(durable_path, base, task, manifest):
                continue
            if not args.retry_failed and (failed_dir / f"{claim_key}.json").exists():
                continue
            if claim_chunk(claim_dir, claim_key, args.worker_id, args.claim_ttl_seconds):
                if args.retry_failed:
                    (failed_dir / f"{claim_key}.json").unlink(missing_ok=True)
                claimed = (manifest, task, base, overlay_path, durable_path, claim_key)
                break
        if claimed is None:
            print(f"{args.worker_id}: no claimable overlay chunks; completed={completed} failed={failed}", flush=True)
            return 0

        manifest, task, base, overlay_path, durable_path, claim_key = claimed
        errors: list[str] | None = None
        try:
            for attempt in range(1, args.retries + 2):
                if valid_existing(overlay_path, base, task, manifest) or valid_existing(durable_path, base, task, manifest):
                    completed += 1
                    break
                prompt = prompt_for_overlay(base=base, task=task, manifest=manifest, errors=errors)
                prompt_path = prompt_dir / f"{claim_key}.attempt{attempt}.md"
                message_path = message_dir / f"{claim_key}.attempt{attempt}.md"
                log_path = log_dir / f"{claim_key}.log"
                prompt_path.write_text(prompt, encoding="utf-8")
                result: dict[str, Any] | None = None
                print(f"{args.worker_id}: codex overlay {claim_key} attempt {attempt}", flush=True)
                try:
                    run_codex(
                        prompt,
                        message_path,
                        log_path,
                        first=True,
                        model=args.model,
                        reasoning=args.reasoning,
                        cwd=ROOT,
                        timeout_seconds=args.codex_timeout_seconds,
                    )
                    result = extract_json(message_path.read_text(encoding="utf-8"))
                    normalize_overlay_for_task(result, manifest)
                    errors = validate_overlay(base, task, manifest, result)
                except Exception as exc:
                    if mentions_usage_limit(str(exc)):
                        write_json(status_dir / f"{claim_key}.json", status_record("usage_limit", worker_id=args.worker_id))
                        print(f"{args.worker_id}: usage limit detected; stopping", flush=True)
                        return 86
                    errors = [f"codex, parse, or validate failed: {exc}"]
                if errors:
                    print(f"{args.worker_id}: validation failed {claim_key}: {'; '.join(errors[:20])}", flush=True)
                    if result is not None:
                        write_json(rejected_dir / f"{claim_key}.attempt{attempt}.json", result)
                    else:
                        (rejected_dir / f"{claim_key}.attempt{attempt}.txt").write_text("\n".join(errors), encoding="utf-8")
                    write_json(
                        status_dir / f"{claim_key}.json",
                        status_record("attempt_failed", worker_id=args.worker_id, attempt=attempt, errors=errors[:80]),
                    )
                    continue
                overlay_path.parent.mkdir(parents=True, exist_ok=True)
                durable_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = overlay_path.with_suffix(f".{args.worker_id}.tmp")
                tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp_path.replace(overlay_path)
                shutil.copy2(overlay_path, durable_path)
                write_json(status_dir / f"{claim_key}.json", status_record("accepted", worker_id=args.worker_id, attempt=attempt))
                print(f"{args.worker_id}: accepted {claim_key}", flush=True)
                completed += 1
                break
            else:
                write_json(failed_dir / f"{claim_key}.json", status_record("failed", worker_id=args.worker_id, errors=(errors or [])[:80]))
                failed += 1
        finally:
            release_claim(claim_dir, claim_key)

        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: reached max_chunks={args.max_chunks}; failed={failed}", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
