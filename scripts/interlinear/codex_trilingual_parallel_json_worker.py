#!/usr/bin/env python3
"""Generate trilingual chunk JSON candidates in parallel-safe isolated folders."""

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

from codex_chunk_worker import extract_json, load_chunks, mentions_usage_limit, run_codex
from validate_trilingual_interlinear_json import validate_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}


def valid_existing(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
    except Exception:
        return False
    return not validate_chunk(source, data)


def claim_chunk(claim_dir: Path, chunk_id: str, worker_id: str, ttl_seconds: int) -> bool:
    claim_path = claim_dir / chunk_id
    now = time.time()
    try:
        claim_path.mkdir(parents=True)
    except FileExistsError:
        owner_alive = False
        try:
            owner = json.loads((claim_path / "owner.json").read_text(encoding="utf-8"))
            owner_pid = int(owner.get("pid", 0))
            if owner_pid > 0:
                os.kill(owner_pid, 0)
                owner_alive = True
        except (FileNotFoundError, json.JSONDecodeError, ValueError, ProcessLookupError):
            owner_alive = False
        except PermissionError:
            owner_alive = True
        if owner_alive:
            try:
                age = now - claim_path.stat().st_mtime
            except FileNotFoundError:
                return False
            if ttl_seconds <= 0 or age <= ttl_seconds:
                return False
        shutil.rmtree(claim_path, ignore_errors=True)
        try:
            claim_path.mkdir(parents=True)
        except FileExistsError:
            return False
    (claim_path / "owner.json").write_text(
        json.dumps({"worker_id": worker_id, "pid": os.getpid(), "claimed_at": now}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def release_claim(claim_dir: Path, chunk_id: str) -> None:
    shutil.rmtree(claim_dir / chunk_id, ignore_errors=True)


def iter_selected(chunks: list[dict[str, Any]], start_index: int, end_index: int | None) -> list[tuple[int, dict[str, Any]]]:
    selected: list[tuple[int, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks, start=1):
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        selected.append((index, chunk))
    return selected


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious output failed validation. Fix these exact issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:80]
        )
    reference = chunk.get("reference", {})
    ja_ref = reference.get("ja", {})
    ja_instruction = (
        "Use the supplied Japanese reference window when available."
        if ja_ref.get("available")
        else "No Japanese source window is available for this chapter; create the Japanese from the English standard, cross-checking the Chinese references."
    )
    return textwrap.dedent(
        f"""
        You are preparing one chunk of a trilingual pocket interlinear book for language learning.

        Return exactly one JSON object. No Markdown fences. No explanation.

        English is the standard alignment spine. Use the English paragraphs exactly and use the Chinese/Japanese reference sources to improve translation quality.

        Required object shape:
        {{
          "schema_version": "0.1",
          "mode": "trilingual_standard",
          "chunk_id": "{chunk['chunk_id']}",
          "chapter": {{
            "id": "{chunk['chapter_id']}",
            "number": {chunk['chapter_number']},
            "title": {{
              "en": [{{"t":"Chapter title text"}}],
              "zh": [{{"t":"one Chinese Han character","r":"pinyin"}}],
              "ja": [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji"}}]
            }}
          }},
          "paragraphs": [
            {{
              "id": "source paragraph id",
              "source_en": "exact English source paragraph",
              "units": [
                {{
                  "source_en": "exact English sentence or sentence group",
                  "en": [{{"t":"English text segment","g":"optional grammar role"}}],
                  "zh": [{{"t":"one Chinese Han character OR punctuation/non-Han run","r":"pinyin only for one Han character","g":"optional grammar role"}}],
                  "ja": [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji","g":"optional grammar role"}}]
                }}
              ]
            }}
          ]
        }}

        Hard requirements:
        - Preserve paragraph ids and order exactly.
        - Preserve each paragraph source_en exactly.
        - For each paragraph, joining all unit en token "t" values must reconstruct the exact source_en text apart from whitespace normalization.
        - Split English paragraphs into natural reading units, usually sentence by sentence or short sentence groups.
        - English tokens must not have readings. Include spaces where needed so joined English reconstructs the source.
        - Chinese should use the supplied Chinese sources as reference translations whenever they match the English chunk. Do not omit meaning. Do not invent a summary.
        - Japanese: {ja_instruction}
        - Chinese tokenization is strict: every Chinese Han character must be its own token with pinyin with tone marks. Pinyin may only be attached to one-Han-character tokens. Punctuation, Latin text, Arabic numerals, and spaces have no reading.
        - Japanese tokenization is strict: every kanji character must be its own token with furigana. Furigana may only be attached to one-kanji tokens. Kana, okurigana, punctuation, Latin text, Arabic numerals, and spaces have no reading.
        - The Japanese row must be real Japanese. If the source reference is Chinese or unavailable, translate to natural Japanese; do not put Chinese prose in ja.
        - For color mode, add optional "g" roles to meaningful tokens. Use only: subject, predicate, object, attributive, adverbial, complement, topic, function. Try to keep major roles roughly parallel across languages.
        - Keep chapter id and chunk id exactly as provided.
        {error_block}

        Chunk metadata:
        {json.dumps({key: chunk[key] for key in ('chunk_id', 'chapter_id', 'chapter_number', 'chapter_title_en', 'chapter_part_en')}, ensure_ascii=False, indent=2)}

        Source English paragraphs:
        {json.dumps(chunk['paragraphs'], ensure_ascii=False, indent=2)}

        Reference windows:
        {json.dumps(reference, ensure_ascii=False, indent=2)}
        """
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = load_chunks(Path(args.chunks_jsonl))
    canonical_dir = Path(args.canonical_dir)
    candidate_dir = Path(args.candidate_dir)
    work_dir = Path(args.work_dir)
    claim_dir = candidate_dir / "claims"
    accepted_dir = candidate_dir / "accepted"
    rejected_dir = candidate_dir / "rejected"
    failed_dir = candidate_dir / "failed"
    status_dir = candidate_dir / "status"
    for path in (claim_dir, accepted_dir, rejected_dir, failed_dir, status_dir, canonical_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    while True:
        claimed: tuple[int, dict[str, Any]] | None = None
        for item in iter_selected(chunks, args.start_index, args.end_index):
            _index, chunk = item
            chunk_id = chunk["chunk_id"]
            canonical_path = canonical_dir / f"{chunk_id}.json"
            candidate_path = accepted_dir / f"{chunk_id}.json"
            if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                continue
            if not args.retry_failed and (failed_dir / f"{chunk_id}.json").exists():
                continue
            if claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
                if args.retry_failed:
                    (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)
                claimed = item
                break
        if claimed is None:
            print(f"{args.worker_id}: no claimable chunks; accepted={completed} failed={failed}", flush=True)
            return 0

        _index, chunk = claimed
        chunk_id = chunk["chunk_id"]
        canonical_path = canonical_dir / f"{chunk_id}.json"
        candidate_path = accepted_dir / f"{chunk_id}.json"
        errors: list[str] | None = None
        try:
            for attempt in range(1, args.retries + 2):
                if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                    completed += 1
                    break
                prompt = prompt_for_chunk(chunk, errors)
                prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                log_path = work_dir / "logs" / f"{chunk_id}.log"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")
                print(f"{args.worker_id}: codex trilingual {chunk_id} attempt {attempt}", flush=True)
                result: dict[str, Any] | None = None
                try:
                    run_codex(
                        prompt,
                        message_path,
                        log_path,
                        first=True,
                        model=args.model,
                        reasoning=args.reasoning,
                        cwd=cwd,
                        timeout_seconds=args.codex_timeout_seconds,
                    )
                    result = extract_json(message_path.read_text(encoding="utf-8"))
                    errors = validate_chunk(chunk, result)
                except Exception as exc:
                    if mentions_usage_limit(str(exc)):
                        write_json(status_dir / f"{chunk_id}.json", status_record("usage_limit", worker_id=args.worker_id, attempt=attempt))
                        print(f"{args.worker_id}: usage limit detected; stopping worker", flush=True)
                        return 86
                    errors = [f"codex, parse, or validate step failed: {exc}"]
                if errors:
                    print(f"{args.worker_id}: validation failed {chunk_id}: {'; '.join(errors[:12])}", flush=True)
                    reject_path = rejected_dir / f"{chunk_id}.{args.worker_id}.attempt{attempt}.json"
                    if result is not None:
                        write_json(reject_path, result)
                    else:
                        reject_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
                    write_json(status_dir / f"{chunk_id}.json", status_record("attempt_failed", worker_id=args.worker_id, attempt=attempt, errors=errors[:80]))
                    continue
                tmp_path = candidate_path.with_suffix(f".{args.worker_id}.tmp")
                tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp_path.replace(candidate_path)
                write_json(status_dir / f"{chunk_id}.json", status_record("accepted", worker_id=args.worker_id, attempt=attempt))
                print(f"{args.worker_id}: accepted candidate {chunk_id}", flush=True)
                completed += 1
                break
            else:
                write_json(failed_dir / f"{chunk_id}.json", status_record("failed", worker_id=args.worker_id, attempts=args.retries + 1, errors=(errors or [])[:80]))
                failed += 1
        finally:
            release_claim(claim_dir, chunk_id)
        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: max chunks reached ({args.max_chunks})", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
