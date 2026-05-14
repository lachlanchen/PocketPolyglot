#!/usr/bin/env python3
"""Review merged interlinear chunks and backfix broad quality failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_bilingual_chunk_worker import GRAMMAR_ROLES, prompt_for_chunk, validate_chunk
from codex_chunk_worker import extract_json, load_chunks, run_codex
from normalize_grammar_roles import cleanup_components, normalize_node
from validate_interlinear_json import ja_lines_text, normalize

PROMPT_VERSION = "broad-post-merge-review-v1"
CONTENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffぁ-ゟ゠-ヿA-Za-z0-9]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SENTENCE_END_RE = re.compile(r"[。！？!?]")
PUNCT_RE = re.compile(r"^[\s，。！？、；：,.!?;:「」『』（）()《》〈〉“”‘’…—-]+$")


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_sha(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"prompt_version": PROMPT_VERSION, "chunks": {}}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def is_content_token(token: Any) -> bool:
    if not isinstance(token, dict):
        return False
    text = str(token.get("t", ""))
    return bool(CONTENT_RE.search(text)) and not PUNCT_RE.fullmatch(text)


def iter_unit_tokens(unit: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    if lang == "zh":
        items = unit.get("zh", [])
        if isinstance(items, list):
            tokens.extend(token for token in items if isinstance(token, dict))
    elif lang == "ja":
        lines = unit.get("ja", [])
        if isinstance(lines, list):
            for line in lines:
                if isinstance(line, list):
                    tokens.extend(token for token in line if isinstance(token, dict))
    return tokens


def role_counts(tokens: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        if not is_content_token(token):
            continue
        role = str(token.get("g", "")).strip().lower()
        if role == "function":
            continue
        if role:
            counts[role] = counts.get(role, 0) + 1
    return counts


def add_role_collapse_issues(
    counts: dict[str, int],
    where: str,
    errors: list[str],
    *,
    minimum: int,
    max_ratio: float,
    min_roles: int,
) -> None:
    total = sum(counts.values())
    if total < minimum:
        return
    if not counts:
        errors.append(f"{where}: no non-function grammar roles on content tokens")
        return
    dominant_role, dominant_count = max(counts.items(), key=lambda item: item[1])
    ratio = dominant_count / total
    if ratio >= max_ratio:
        percent = round(ratio * 100)
        errors.append(
            f"{where}: grammar/color collapse, {dominant_count}/{total} non-function content tokens "
            f"({percent}%) are {dominant_role}; redistribute major components"
        )
    if len(counts) < min_roles:
        errors.append(
            f"{where}: grammar/color variety too low ({len(counts)} roles across {total} content tokens); "
            "use subject, predicate, object, attributive, adverbial, complement/topic where appropriate"
        )


def review_chunk(source: dict[str, Any], data: dict[str, Any]) -> list[str]:
    errors = validate_chunk(source, data)
    reference_text = normalize("".join(str(item.get("text", "")) for item in source.get("jp_reference", [])))
    chunk_counts = {"zh": {}, "ja": {}, "both": {}}
    last_ref_pos = -1
    duplicate_ja: dict[str, int] = {}

    def add_counts(lang: str, counts: dict[str, int]) -> None:
        for role, count in counts.items():
            chunk_counts[lang][role] = chunk_counts[lang].get(role, 0) + count
            chunk_counts["both"][role] = chunk_counts["both"].get(role, 0) + count

    for paragraph_index, paragraph in enumerate(data.get("paragraphs", [])):
        units = paragraph.get("units", [])
        paragraph_id = paragraph.get("id", f"paragraphs[{paragraph_index}]")
        source_text = str(paragraph.get("source_text", ""))
        if isinstance(units, list):
            sentence_count = len(SENTENCE_END_RE.findall(source_text))
            if sentence_count >= 4 and len(units) < max(2, math.ceil(sentence_count * 0.45)):
                errors.append(
                    f"{paragraph_id}: too few interlinear units for sentence-level reading "
                    f"({len(units)} units for {sentence_count} sentence endings)"
                )
        if not isinstance(units, list):
            continue
        for unit_index, unit in enumerate(units):
            if not isinstance(unit, dict):
                continue
            unit_where = f"{paragraph_id}.units[{unit_index}]"
            zh_tokens = iter_unit_tokens(unit, "zh")
            ja_tokens = iter_unit_tokens(unit, "ja")
            zh_counts = role_counts(zh_tokens)
            ja_counts = role_counts(ja_tokens)
            add_counts("zh", zh_counts)
            add_counts("ja", ja_counts)
            add_role_collapse_issues(zh_counts, f"{unit_where}.zh", errors, minimum=34, max_ratio=0.92, min_roles=2)
            add_role_collapse_issues(ja_counts, f"{unit_where}.ja", errors, minimum=34, max_ratio=0.92, min_roles=2)

            zh_text = normalize(token_text(unit.get("zh", [])))
            ja_text = normalize(ja_lines_text(unit.get("ja", [])))
            if len(zh_text) >= 14 and len(ja_text) < max(6, int(len(zh_text) * 0.16)):
                errors.append(f"{unit_where}: Japanese correspondence is too short for the Chinese unit")
            if ja_text:
                duplicate_ja[ja_text] = duplicate_ja.get(ja_text, 0) + 1
            if reference_text and len(ja_text) >= 5 and not any(marker in zh_text for marker in ("译者", "注")):
                ref_pos = reference_text.find(ja_text)
                if ref_pos < 0:
                    errors.append(f"{unit_where}: Japanese comment text is not found in the supplied original reference")
                elif ref_pos + 8 < last_ref_pos:
                    errors.append(f"{unit_where}: Japanese correspondence moves backward in the original reference")
                else:
                    last_ref_pos = max(last_ref_pos, ref_pos)
            for token_index, token in enumerate(ja_tokens):
                reading = str(token.get("r", ""))
                if reading and HAN_RE.search(reading):
                    errors.append(f"{unit_where}.ja token {token_index}: furigana contains kanji")

    for text, count in duplicate_ja.items():
        if count >= 3 and len(text) >= 5:
            errors.append(f"{source['chunk_id']}: repeated identical Japanese comment {count} times: {text[:30]}")

    add_role_collapse_issues(chunk_counts["zh"], f"{source['chunk_id']}.zh", errors, minimum=90, max_ratio=0.82, min_roles=4)
    add_role_collapse_issues(chunk_counts["ja"], f"{source['chunk_id']}.ja", errors, minimum=90, max_ratio=0.82, min_roles=4)
    add_role_collapse_issues(chunk_counts["both"], source["chunk_id"], errors, minimum=160, max_ratio=0.78, min_roles=4)
    return errors


def repair_prompt(source: dict[str, Any], current: dict[str, Any], issues: list[str]) -> str:
    base_prompt = prompt_for_chunk(source, issues)
    shown_issues = "\n".join(f"- {issue}" for issue in issues[:120])
    return textwrap.dedent(
        f"""
        You are backfixing a merged interlinear chunk that failed broad post-merge review.

        Return the full corrected chunk JSON only. No Markdown fences and no explanation.

        Fix every class of issue, not only grammar:
        - Preserve every Chinese paragraph exactly and keep paragraph ids/order exact.
        - Split at sentence or short clause level so the interline is line-based and readable.
        - Use the supplied Japanese original reference as the comment text, in the correct original order.
        - Ensure every Chinese Han token has pinyin on its own single-character token.
        - Ensure every Japanese kanji has furigana on its own single-kanji token only.
        - Use one English grammar role in "g" for every content token.
        - Avoid color collapse: a whole sentence/chunk must not become one dominant role such as all predicate.
        - Match the major Chinese and Japanese components roughly with the same roles/colors.

        Review failures to fix:
        {shown_issues}

        Current merged JSON to repair:
        {json.dumps(current, ensure_ascii=False, indent=2)}

        Source/reference prompt for this chunk:
        {base_prompt}
        """
    ).strip()


def parse_chunk_ids(raw_values: list[str]) -> list[str]:
    found: list[str] = []
    for raw in raw_values:
        for item in re.split(r"[\s,]+", raw.strip()):
            if item and item not in found:
                found.append(item)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--state-json", default="")
    parser.add_argument("--chunk-id", action="append", default=[])
    parser.add_argument("--chunk-ids", action="append", default=[])
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="xhigh")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--review-only", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunk_dir = Path(args.chunk_dir)
    work_dir = Path(args.work_dir)
    state_path = Path(args.state_json) if args.state_json else work_dir / "state.json"
    state = load_state(state_path)
    state["prompt_version"] = PROMPT_VERSION
    state.setdefault("chunks", {})
    sources = {chunk["chunk_id"]: chunk for chunk in load_chunks(Path(args.chunks_jsonl))}
    chunk_ids = parse_chunk_ids(args.chunk_id + args.chunk_ids)
    if not chunk_ids:
        chunk_ids = sorted(path.stem for path in chunk_dir.glob("*.json"))

    failed: list[str] = []
    for chunk_id in chunk_ids:
        source = sources.get(chunk_id)
        chunk_path = chunk_dir / f"{chunk_id}.json"
        if source is None:
            print(f"{chunk_id}: no source chunk")
            failed.append(chunk_id)
            continue
        if not chunk_path.exists():
            print(f"{chunk_id}: missing canonical chunk")
            failed.append(chunk_id)
            continue

        data = load_json(chunk_path)
        normalize_node(data)
        cleanup_components(data)
        issues = review_chunk(source, data)
        if not issues:
            write_json(chunk_path, data)
            state["chunks"][chunk_id] = {
                "prompt_version": PROMPT_VERSION,
                "input_sha": json_sha(data),
                "status": "ok",
                "issue_count": 0,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
            write_state(state_path, state)
            print(f"review ok {chunk_id}")
            continue

        print(f"review failed {chunk_id}: {len(issues)} issue(s)")
        for issue in issues[:25]:
            print(f"  - {issue}")
        if args.review_only:
            failed.append(chunk_id)
            continue

        previous_issues = issues
        repaired = False
        for attempt in range(1, args.retries + 2):
            prompt = repair_prompt(source, data, previous_issues)
            prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
            message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
            log_path = work_dir / "logs" / f"{chunk_id}.log"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")

            print(f"codex broad backfix {chunk_id} attempt {attempt}")
            run_codex(prompt, message_path, log_path, first=True, model=args.model, reasoning=args.reasoning, cwd=cwd)
            try:
                candidate = extract_json(message_path.read_text(encoding="utf-8"))
                normalize_node(candidate)
                cleanup_components(candidate)
                validation = review_chunk(source, candidate)
                if validation:
                    raise ValueError("; ".join(validation[:80]))
            except Exception as exc:
                previous_issues = [str(exc)]
                print(f"backfix failed {chunk_id}: {previous_issues[0]}")
                continue

            write_json(chunk_path, candidate)
            state["chunks"][chunk_id] = {
                "prompt_version": PROMPT_VERSION,
                "input_sha": json_sha(candidate),
                "status": "backfixed",
                "initial_issue_count": len(issues),
                "attempt": attempt,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
            write_state(state_path, state)
            print(f"backfixed {chunk_id}")
            repaired = True
            break
        if not repaired:
            failed.append(chunk_id)

    if failed:
        print("failed_chunks=" + ",".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
