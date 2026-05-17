#!/usr/bin/env python3
"""Run one resumable Codex session to convert Markdown chunks into interlinear JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

from validate_interlinear_json import validate_ja_tokens, validate_named_tokens, validate_zh_tokens

USAGE_LIMIT_MARKERS = (
    "you've hit your usage limit",
    "you have hit your usage limit",
    "usage limit",
    "purchase more credits",
    "try again at",
)


def mentions_usage_limit(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in USAGE_LIMIT_MARKERS)


def log_mentions_usage_limit(path: Path) -> bool:
    try:
        return mentions_usage_limit(path.read_text(encoding="utf-8", errors="replace")[-8000:])
    except OSError:
        return False


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def usage_limit_wait_enabled() -> bool:
    raw = os.environ.get("CODEX_USAGE_LIMIT_WAIT", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def log_text_since(path: Path, start_size: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(start_size)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(stripped[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(stripped[start : index + 1])
    raise ValueError("unterminated JSON object")


def flatten_zh(paragraph: dict[str, Any]) -> str:
    return "".join(token.get("t", "") for unit in paragraph.get("units", []) for token in unit.get("zh", []))


def compact(text: str) -> str:
    return "".join(str(text).split())


def validate_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
    for key in ("section", "subsection", "story"):
        node = result.get(key)
        if not isinstance(node, dict):
            errors.append(f"{key}: must be an object")
        else:
            validate_named_tokens(node, key, errors)
    expected_ids = [paragraph["id"] for paragraph in source["paragraphs"]]
    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list):
        return ["result.paragraphs must be a list"]
    got_ids = [paragraph.get("id") for paragraph in paragraphs]
    if got_ids != expected_ids:
        errors.append(f"paragraph id/order mismatch: expected {expected_ids}, got {got_ids}")
    source_by_id = {paragraph["id"]: paragraph["text"] for paragraph in source["paragraphs"]}
    for paragraph in paragraphs:
        paragraph_id = paragraph.get("id")
        if paragraph_id not in source_by_id:
            continue
        if compact(paragraph.get("source_text", "")) != compact(source_by_id[paragraph_id]):
            errors.append(f"{paragraph_id}: paragraph source_text changed")
        if compact(flatten_zh(paragraph)) != compact(source_by_id[paragraph_id]):
            errors.append(f"{paragraph_id}: zh tokens do not reconstruct source paragraph")
        if not paragraph.get("units"):
            errors.append(f"{paragraph_id}: missing units")
        for unit_index, unit in enumerate(paragraph.get("units", [])):
            validate_zh_tokens(unit.get("zh", []), f"{paragraph_id}.units[{unit_index}].zh", errors)
            ja = unit.get("ja", [])
            if len(ja) != 2:
                errors.append(f"{paragraph_id}.units[{unit_index}]: ja must have exactly two lines")
            else:
                validate_ja_tokens(ja[0], f"{paragraph_id}.units[{unit_index}].ja[0]", errors)
                validate_ja_tokens(ja[1], f"{paragraph_id}.units[{unit_index}].ja[1]", errors)
    return errors


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious output failed validation. Fix these issues exactly:\n" + "\n".join(f"- {error}" for error in previous_errors)

    return textwrap.dedent(
        f"""
        You are preparing one chunk of a Chinese-main / Japanese-comment pocket interlinear book.

        Return exactly one JSON object and no Markdown fences, no explanation.

        Required object shape:
        {{
          "chunk_id": "{chunk['chunk_id']}",
          "section": {{"id": "...", "title_zh": [{{"t":"...","r":"..."}}], "title_ja": [{{"t":"...","r":"..."}}]}},
          "subsection": {{"id": "...", "title_zh": [{{"t":"...","r":"..."}}], "title_ja": [{{"t":"...","r":"..."}}]}},
          "story": {{"id": "...", "title_zh": [{{"t":"...","r":"..."}}], "title_ja": [{{"t":"...","r":"..."}}], "place_zh": [], "place_ja": []}},
          "paragraphs": [
            {{
              "id": "source paragraph id",
              "source_text": "exact source paragraph",
              "units": [
                {{
                  "source_text": "exact Chinese sentence or sentence group from the paragraph",
                  "zh": [{{"t":"one Chinese Han character","r":"that character's pinyin with tone mark"}}],
                  "ja": [
                    [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji, empty otherwise"}}],
                    [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji, empty otherwise"}}]
                  ]
                }}
              ]
            }}
          ]
        }}

        Hard requirements:
        - Preserve every source paragraph. Do not omit, summarize, reorder, or rewrite the Chinese.
        - For each paragraph, joining all zh token "t" values across all units must reconstruct the paragraph text exactly, apart from whitespace.
        - Split paragraphs into natural Chinese reading units, usually sentence by sentence.
        - Chinese tokenization is strict: every Chinese Han character must be its own token with pinyin, e.g. "先生" becomes [{{"t":"先","r":"xiān"}},{{"t":"生","r":"sheng"}}]. Never attach pinyin to a multi-character Chinese word or phrase. Punctuation, Arabic numerals, Latin text, and spaces use empty reading.
        - Translate each Chinese unit into natural Japanese comment text.
        - Japanese comment must be exactly two token arrays per unit. Split them into two short visual rows.
        - Japanese tokenization is strict: every kanji character must be its own token with furigana, and furigana may appear only on one-kanji tokens. Kana, okurigana, punctuation, spaces, and Latin text must have empty reading. Example: "先生と私" becomes [{{"t":"先","r":"せん"}},{{"t":"生","r":"せい"}},{{"t":"と","r":""}},{{"t":"私","r":"わたし"}}]. Example: "書くだけ" becomes [{{"t":"書","r":"か"}},{{"t":"くだけ","r":""}}].
        - Keep ids exactly as provided below.
        - Use the provided section/subsection/story ids and titles. Apply the same strict per-Han-character/per-kanji-character ruby rules to all titles and place fields.
        {error_block}

        Chunk metadata:
        {json.dumps({key: chunk[key] for key in ('chunk_id', 'section_id', 'section_title', 'subsection_id', 'subsection_title', 'story_id', 'story_title')}, ensure_ascii=False, indent=2)}

        Source paragraphs:
        {json.dumps(chunk['paragraphs'], ensure_ascii=False, indent=2)}
        """
    ).strip()


def run_codex(
    prompt: str,
    output_message: Path,
    log_path: Path,
    *,
    first: bool,
    model: str,
    reasoning: str,
    cwd: Path,
    timeout_seconds: int = 0,
) -> None:
    output_message.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_message.unlink(missing_ok=True)
    common = [
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "--dangerously-bypass-approvals-and-sandbox",
        "--output-last-message",
        str(output_message),
    ]
    if first:
        cmd = ["codex", "exec", "--cd", str(cwd), *common, "-"]
    else:
        cmd = ["codex", "exec", "resume", "--last", *common, "-"]

    wait_seconds = env_int("CODEX_USAGE_LIMIT_WAIT_SECONDS", 3600)
    max_wait_seconds = env_int("CODEX_USAGE_LIMIT_MAX_WAIT_SECONDS", 0)
    waited_seconds = 0
    attempt = 0
    while True:
        attempt += 1
        output_message.unlink(missing_ok=True)
        start_size = log_path.stat().st_size if log_path.exists() else 0
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n\n===== CODEX COMMAND attempt {attempt} =====\n")
            log.write(" ".join(cmd) + "\n")
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    text=True,
                    cwd=cwd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds if timeout_seconds > 0 else None,
                )
            except subprocess.TimeoutExpired as exc:
                log.write(f"\n===== CODEX TIMEOUT after {timeout_seconds}s =====\n")
                raise RuntimeError(f"codex timed out after {timeout_seconds}s; see {log_path}") from exc

        new_log = log_text_since(log_path, start_size)
        if proc.returncode == 0 and not mentions_usage_limit(new_log):
            return
        if mentions_usage_limit(new_log):
            if not usage_limit_wait_enabled() or wait_seconds <= 0:
                raise RuntimeError(f"codex usage limit detected; wait disabled; see {log_path}")
            if max_wait_seconds > 0 and waited_seconds >= max_wait_seconds:
                raise RuntimeError(f"codex usage limit persisted for {waited_seconds}s; see {log_path}")
            sleep_for = wait_seconds
            if max_wait_seconds > 0:
                sleep_for = min(sleep_for, max_wait_seconds - waited_seconds)
            if sleep_for <= 0:
                raise RuntimeError(f"codex usage limit persisted for {waited_seconds}s; see {log_path}")
            waited_seconds += sleep_for
            message = (
                f"codex usage limit detected; sleeping {sleep_for}s before retry "
                f"(total_wait={waited_seconds}s)"
            )
            print(message, flush=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n===== {message} =====\n")
            time.sleep(sleep_for)
            continue
        raise RuntimeError(f"codex exited with {proc.returncode}; see {log_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--max-chunks", type=int, default=0, help="0 means all chunks")
    parser.add_argument("--start-index", type=int, default=1, help="1-based chunk index")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--codex-timeout-seconds", type=int, default=0, help="0 means no timeout")
    parser.add_argument("--resume-last", action="store_true", help="resume the newest Codex session for the first missing chunk")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = load_chunks(Path(args.chunks_jsonl))
    output_dir = Path(args.output_dir)
    work_dir = Path(args.work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    selected = chunks[args.start_index - 1 :]
    if args.max_chunks:
        selected = selected[: args.max_chunks]

    first_codex_call = not args.resume_last
    for chunk in selected:
        final_path = output_dir / f"{chunk['chunk_id']}.json"
        if final_path.exists():
            try:
                existing = json.loads(final_path.read_text(encoding="utf-8"))
                errors = validate_chunk(chunk, existing)
                if not errors:
                    print(f"skip valid {chunk['chunk_id']}")
                    continue
            except Exception:
                pass

        errors: list[str] | None = None
        for attempt in range(1, args.retries + 2):
            prompt = prompt_for_chunk(chunk, errors)
            prompt_path = work_dir / "prompts" / f"{chunk['chunk_id']}.attempt{attempt}.md"
            message_path = work_dir / "messages" / f"{chunk['chunk_id']}.attempt{attempt}.md"
            log_path = work_dir / "logs" / f"{chunk['chunk_id']}.log"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")

            print(f"codex {chunk['chunk_id']} attempt {attempt}")
            try:
                run_codex(
                    prompt,
                    message_path,
                    log_path,
                    first=first_codex_call,
                    model=args.model,
                    reasoning=args.reasoning,
                    cwd=cwd,
                    timeout_seconds=args.codex_timeout_seconds,
                )
                first_codex_call = False
            except Exception as exc:
                errors = [f"codex failed: {exc}"]
                print("; ".join(errors), file=sys.stderr)
                continue

            try:
                result = extract_json(message_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors = [f"could not parse JSON: {exc}"]
                print("; ".join(errors), file=sys.stderr)
                continue

            errors = validate_chunk(chunk, result)
            if errors:
                print(f"validation failed for {chunk['chunk_id']}: {'; '.join(errors)}", file=sys.stderr)
                reject_path = work_dir / "rejected" / f"{chunk['chunk_id']}.attempt{attempt}.json"
                reject_path.parent.mkdir(parents=True, exist_ok=True)
                reject_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                continue

            final_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {final_path}")
            break
        else:
            raise RuntimeError(f"failed {chunk['chunk_id']} after retries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
