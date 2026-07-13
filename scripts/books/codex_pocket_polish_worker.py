#!/usr/bin/env python3
"""Generate and review one worker shard of a polished pocket-book task."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from pocket_polished_common import (
    OUTPUT_ROOT,
    ROOT,
    read_json,
    read_jsonl,
    validate_chunk_output,
    write_json,
)


TRANSIENT_PATTERNS = (
    "rate limit",
    "usage limit",
    "too many requests",
    "status 429",
    "temporarily unavailable",
    "overloaded",
    "timeout",
    "timed out",
    "connection reset",
    "failed to refresh available models",
)


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


def writer_prompt(task: dict[str, Any], feedback: list[str]) -> str:
    feedback_text = "\n".join(f"- {item}" for item in feedback) if feedback else "- none"
    source_language = task.get("source_language", "en")
    english_instruction = (
        "For en_tex, conservatively repair only definite OCR, spacing, punctuation, duplicated-header, "
        "or broken-line errors. Preserve already-correct prose. Never summarize or rewrite merely for style."
        if source_language == "en"
        else "For en_tex, translate the complete source into accurate, natural modern English. Preserve every "
        "claim, qualification, name, date, and ordering; do not summarize or expand."
    )
    change_instruction = (
        "Every English correction must have a changes record. before must be an exact source substring; after "
        "must be an exact en_tex substring; confidence below 0.85 means do not apply the change."
        if source_language == "en"
        else "changes records are only for definite corrections to damaged source text; ordinary translation "
        "does not need a changes record. Never silently guess damaged source text."
    )
    return f"""You are producing a source-faithful, publication-quality English/Japanese edition of one technical or scholarly book chunk.

This is transcription repair and translation, not creative writing. The supplied exact TeX is the authority.

Required work:
1. {english_instruction}
2. For ja_tex, provide complete, natural, modern, readable Japanese faithful to every claim and qualification in the English source. Do not omit or add facts.
3. Keep every @@PROTECTED_NNNN@@ token exactly once and in the same order. They represent equations, figures, citations, labels, URLs, or inline math.
4. Preserve the exact TeX command sequence, braces, table rows/columns, numbers, equation references, names, dates, units, and ordering.
5. Do not invent missing words. If source damage cannot be resolved from context with high confidence, preserve it and list the uncertainty in unresolved.
6. {change_instruction}
7. Return only JSON matching the supplied schema. Do not edit files and do not call another agent.

Feedback from earlier validation/review:
{feedback_text}

Task JSON:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""


def reviewer_prompt(task: dict[str, Any], candidate: dict[str, Any]) -> str:
    return f"""Act as a strict bilingual textual editor validating a proposed English/Japanese TeX chunk against its source.

Accept only if all source content is retained in order, English changes are definite corrections, Japanese is complete/natural/accurate, and no claim, name, number, qualification, table relation, equation reference, or protected TeX object is added, removed, or altered.

Do not demand stylistic rewrites. Do not reject faithful literal terminology merely because another translation is possible. Reject factual invention, omissions, mistranslation, unresolved OCR silently guessed, garbled Japanese, or structural corruption. Return only JSON matching the review schema.

Source task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Candidate:
{json.dumps(candidate, ensure_ascii=False, indent=2)}
"""


def run_codex(
    prompt: str,
    *,
    schema: Path,
    message: Path,
    log: Path,
    model: str,
    reasoning: str,
    timeout: int,
) -> tuple[int, str]:
    message.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "-C",
        str(ROOT),
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "--sandbox",
        "read-only",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(message),
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
            timeout=timeout,
            check=False,
        )
        output = result.stdout or ""
        log.write_text(output, encoding="utf-8", errors="replace")
        return result.returncode, output
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\nTIMEOUT\n"
        log.write_text(output, encoding="utf-8", errors="replace")
        return 124, output


def is_transient(text: str) -> bool:
    lowered = text.lower()
    if "invalid_json_schema" in lowered or (
        "invalid_request_error" in lowered and "rate limit" not in lowered
    ):
        return False
    return any(pattern in lowered for pattern in TRANSIENT_PATTERNS)


def valid_existing(task: dict[str, Any], path: Path) -> bool:
    try:
        result = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return not validate_chunk_output(task, result)


def acquire_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return None


def process_chunk(
    task: dict[str, Any],
    *,
    book_root: Path,
    model: str,
    reasoning: str,
    retries: int,
    timeout: int,
    backoff: int,
) -> bool:
    chunk_id = task["chunk_id"]
    output_path = book_root / "json" / f"{chunk_id}.json"
    if valid_existing(task, output_path):
        print(f"skip valid {chunk_id}", flush=True)
        return True
    lock_path = book_root / "work/locks" / f"{chunk_id}.lock"
    lock_fd = acquire_lock(lock_path)
    if lock_fd is None:
        print(f"skip locked {chunk_id}", flush=True)
        return True
    os.write(lock_fd, f"pid={os.getpid()}\n".encode())
    os.close(lock_fd)
    feedback: list[str] = []
    try:
        attempt = 1
        while attempt <= retries:
            prefix = book_root / "work/attempts" / chunk_id / f"attempt-{attempt:02d}"
            writer_message = prefix.with_suffix(".writer.json")
            writer_log = prefix.with_suffix(".writer.log")
            rc, raw = run_codex(
                writer_prompt(task, feedback),
                schema=OUTPUT_ROOT / "tasks/polish-output.schema.json",
                message=writer_message,
                log=writer_log,
                model=model,
                reasoning=reasoning,
                timeout=timeout,
            )
            if rc != 0:
                if "model is not supported" in raw.lower() or "model metadata" in raw.lower() and "invalid_request" in raw.lower():
                    raise RuntimeError(f"unsupported model {model}; see {writer_log}")
                if is_transient(raw):
                    print(f"transient writer failure {chunk_id}; sleeping {backoff}s", flush=True)
                    time.sleep(backoff)
                    continue
                feedback = [f"writer command failed on attempt {attempt}; return valid schema JSON"]
                attempt += 1
                continue
            try:
                candidate = extract_json(writer_message.read_text(encoding="utf-8"))
            except Exception as exc:
                feedback = [f"output was not valid JSON: {exc}"]
                attempt += 1
                continue
            errors = validate_chunk_output(task, candidate)
            if errors:
                write_json(prefix.with_suffix(".deterministic-rejection.json"), {"errors": errors})
                feedback = errors[:30]
                attempt += 1
                continue

            review_message = prefix.with_suffix(".review.json")
            review_log = prefix.with_suffix(".review.log")
            rc, raw = run_codex(
                reviewer_prompt(task, candidate),
                schema=OUTPUT_ROOT / "tasks/semantic-review.schema.json",
                message=review_message,
                log=review_log,
                model=model,
                reasoning=reasoning,
                timeout=timeout,
            )
            if rc != 0:
                if is_transient(raw):
                    print(f"transient review failure {chunk_id}; sleeping {backoff}s", flush=True)
                    time.sleep(backoff)
                    continue
                feedback = [f"semantic reviewer command failed on attempt {attempt}"]
                attempt += 1
                continue
            try:
                review = extract_json(review_message.read_text(encoding="utf-8"))
            except Exception as exc:
                feedback = [f"semantic reviewer returned invalid JSON: {exc}"]
                attempt += 1
                continue
            if not review.get("accept"):
                feedback = [
                    f"{item.get('segment_id', chunk_id)}: {item.get('message', 'review rejected')}"
                    for item in review.get("issues", [])
                    if isinstance(item, dict)
                ] or [review.get("summary", "semantic review rejected the candidate")]
                attempt += 1
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(output_path, candidate)
            write_json(book_root / "review" / f"{chunk_id}.json", review)
            print(f"accepted {chunk_id}", flush=True)
            return True
        write_json(
            book_root / "work/failed" / f"{chunk_id}.json",
            {"chunk_id": chunk_id, "attempts": retries, "last_feedback": feedback},
        )
        print(f"failed {chunk_id} after {retries} attempts", flush=True)
        return False
    finally:
        lock_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--worker-index", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning", default="low")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--backoff", type=int, default=600)
    parser.add_argument("--max-chunks", type=int, default=0)
    args = parser.parse_args()
    if args.worker_index < 1 or args.worker_index > args.workers:
        parser.error("worker index must be in 1..workers")

    book_root = OUTPUT_ROOT / args.book_id
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    selected = [
        task
        for index, task in enumerate(tasks)
        if index % args.workers == args.worker_index - 1
    ]
    if args.max_chunks:
        selected = selected[: args.max_chunks]
    failures = 0
    for task in selected:
        if not process_chunk(
            task,
            book_root=book_root,
            model=args.model,
            reasoning=args.reasoning,
            retries=args.retries,
            timeout=args.timeout,
            backoff=args.backoff,
        ):
            failures += 1
    print(f"worker={args.worker_index}/{args.workers} selected={len(selected)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
