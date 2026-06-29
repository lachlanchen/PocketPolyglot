#!/usr/bin/env python3
"""Generate quadrilingual wenyan-main chunk JSON in parallel-safe workers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_chunk_worker import extract_json, load_chunks, mentions_usage_limit, run_codex
from codex_trilingual_parallel_json_worker import claim_chunk, iter_selected, release_claim
from codex_trilingual_plain_json_worker import split_cjk_units, tokenize_en, tokenize_ja, tokenize_zh
from validate_quadrilingual_interlinear_json import HAN_RE, KANA_RE, validate_chunk


SPACE_RE = re.compile(r"\s+")
SOURCE_NOTE_MARK_RE = re.compile(r"^\s*\d{1,3}\s*$")
CATALOG_COUNTER_RE = re.compile(r"[一二三四五六七八九十百千〇零\d]+[篇卷巻]")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}


def plain_text(text: Any) -> str:
    return SPACE_RE.sub(" ", str(text or "").replace("\n", " ")).strip()


def ignorable_source_unit(text: str) -> bool:
    return bool(SOURCE_NOTE_MARK_RE.fullmatch(str(text or "")))


def source_has_content(text: str) -> bool:
    return bool(HAN_RE.search(str(text or "")))


def chunk_has_source_content(chunk: dict[str, Any]) -> bool:
    return any(
        source_has_content(unit["source_wenyan"])
        for paragraph in source_unit_plan(chunk)
        for unit in paragraph["units"]
    )


def catalog_like_source(text: str) -> bool:
    """Detect bibliographic list entries such as 漢書藝文志 catalog rows."""
    source = str(text or "")
    return len(CATALOG_COUNTER_RE.findall(source)) >= 2 and any(mark in source for mark in "，、；;")


def repair_catalog_like_ja(source: dict[str, Any], plain: dict[str, Any]) -> dict[str, Any]:
    """Add a Japanese predicate to catalog rows that otherwise contain no kana.

    Low-reasoning fetches often render Han catalog lists as title lists only:
    『黃帝...』十二卷、... . That is not readable Japanese and fails the kana
    validator. For catalog-like source rows only, append a short predicate so the
    line is explicit Japanese without altering the listed titles.
    """
    plan_by_id = {
        paragraph["id"]: {unit["unit_id"]: unit["source_wenyan"] for unit in paragraph["units"]}
        for paragraph in source_unit_plan(source)
    }
    for paragraph in plain.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        paragraph_sources = plan_by_id.get(str(paragraph.get("id")), {})
        for unit in paragraph.get("units") or []:
            if not isinstance(unit, dict):
                continue
            unit_id = str(unit.get("unit_id") or "")
            source_wenyan = paragraph_sources.get(unit_id, "")
            ja = plain_text(unit.get("ja_modern"))
            if ja and not KANA_RE.search(ja) and catalog_like_source(source_wenyan):
                unit["ja_modern"] = ja.rstrip("。") + "である。"
    return plain


def deterministic_plain_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.1-plain",
        "mode": "quadrilingual_plain_alignment",
        "chunk_id": chunk["chunk_id"],
        "paragraphs": [
            {
                "id": paragraph["id"],
                "units": [
                    {
                        "unit_id": unit["unit_id"],
                        "source_wenyan": unit["source_wenyan"],
                        "zh_modern": unit["source_wenyan"],
                        "ja_modern": unit["source_wenyan"],
                        "en": unit["source_wenyan"],
                    }
                    for unit in paragraph["units"]
                ],
            }
            for paragraph in source_unit_plan(chunk)
        ],
    }


def source_unit_plan(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for paragraph in chunk.get("paragraphs", []):
        if paragraph.get("source_units"):
            units = []
            for index, unit in enumerate(paragraph.get("source_units") or [], start=1):
                if not isinstance(unit, dict):
                    continue
                source_wenyan = str(unit.get("source_wenyan") or unit.get("source_text") or "")
                if not source_wenyan or ignorable_source_unit(source_wenyan):
                    continue
                item = {
                    "unit_id": str(unit.get("unit_id") or f"{paragraph['id']}-u{index:03d}"),
                    "source_wenyan": source_wenyan,
                }
                for key in ("existing_ja", "existing_zh", "existing_note"):
                    if unit.get(key):
                        item[key] = plain_text(unit.get(key))
                units.append(item)
        else:
            units = [
                {"unit_id": f"{paragraph['id']}-u{index:03d}", "source_wenyan": unit}
                for index, unit in enumerate(split_cjk_units(str(paragraph.get("wenyan", ""))), start=1)
                if not ignorable_source_unit(unit)
            ]
        plan.append({"id": paragraph["id"], "units": units})
    return plan


def valid_existing(path: Path, source: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
    except Exception:
        return False
    return not validate_chunk(source, data)


def prompt_for_plain_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious output failed validation. Fix these exact issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:80]
        )
    book_title = plain_text(
        chunk.get("book_title_wenyan")
        or chunk.get("book_title_zh")
        or chunk.get("book_id")
        or "the source text"
    )
    return textwrap.dedent(
        f"""
        You are preparing one chunk of a quadrilingual pocket book.

        Return exactly one JSON object. No Markdown fences. No explanation.

        The main stream is wenyan/classical Chinese from {book_title}. Preserve it exactly.
        Add three aligned reading layers for each supplied unit:
        - zh_modern: readable modern Chinese.
        - ja_modern: real, common modern Japanese with kana; not Chinese, not kanbun, and not copied Han text.
        - en: clear English.

        Required object shape:
        {{
          "schema_version": "0.1-plain",
          "mode": "quadrilingual_plain_alignment",
          "chunk_id": "{chunk['chunk_id']}",
          "paragraphs": [
            {{
              "id": "exact source paragraph id",
              "units": [
                {{
                  "unit_id": "exact supplied unit id",
                  "source_wenyan": "exact supplied source_wenyan",
                  "zh_modern": "modern Chinese corresponding to this unit",
                  "ja_modern": "modern Japanese corresponding to this unit",
                  "en": "English corresponding to this unit"
                }}
              ]
            }}
          ]
        }}

        Hard requirements:
        - Preserve chunk_id, paragraph ids, unit ids, order, and source_wenyan exactly.
        - Output valid JSON only. Escape all quotes inside strings. Do not output comments, trailing commas, multiple JSON objects, or Markdown.
        - Do not omit, summarize, reorder, or rewrite the wenyan.
        - Modern Chinese must be normal readable Chinese, not another copy of the classical text unless the unit is only a name/title.
        - Modern Japanese must be natural Japanese with kana and inflection. Translate the meaning into modern Japanese; never put pure Chinese prose, kanbun, or a Han-only string in ja_modern.
        - If no reliable Japanese reference exists, first understand the wenyan through zh_modern, then write concise modern Japanese from that meaning.
        - For catalog/list rows with titles and counts, do not output a title list only. Add Japanese particles or a predicate, e.g. "...である", so ja_modern contains kana.
        - If the supplied unit plan contains existing_ja, reuse or gently modernize it when it matches the wenyan.
        - English must be natural English and should use the English reference only when it clearly matches this broad book/chapter window.
        - Keep each unit aligned to the same meaning. Do not add footnotes or commentary.
        - No ruby, pinyin, token arrays, Markdown, or grammar labels in this plain response.
        {error_block}

        Chunk metadata:
        {json.dumps({k: chunk.get(k) for k in ("chunk_id", "chapter_id", "chapter_number", "chapter_title_wenyan", "section_title_wenyan")}, ensure_ascii=False, indent=2)}

        Source unit plan:
        {json.dumps(source_unit_plan(chunk), ensure_ascii=False, indent=2)}

        Broad reference material:
        {json.dumps(chunk.get("reference", {}), ensure_ascii=False, indent=2)}
        """
    ).strip()


def validate_plain_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
    if result.get("mode") not in {"quadrilingual_plain_alignment", None}:
        errors.append("mode must be quadrilingual_plain_alignment when present")
    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list):
        return errors + ["paragraphs must be a list"]
    expected_ids = [p["id"] for p in source.get("paragraphs", [])]
    got_ids = [p.get("id") for p in paragraphs if isinstance(p, dict)]
    if got_ids != expected_ids:
        errors.append(f"paragraph id/order mismatch: expected {expected_ids}, got {got_ids}")
    plan_by_id = {paragraph["id"]: paragraph["units"] for paragraph in source_unit_plan(source)}
    for p_index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            errors.append(f"paragraphs[{p_index}]: must be object")
            continue
        paragraph_id = paragraph.get("id")
        expected_units = plan_by_id.get(paragraph_id, [])
        got_units = paragraph.get("units")
        if not isinstance(got_units, list) or not got_units:
            errors.append(f"{paragraph_id}: missing units")
            continue
        expected_unit_ids = [unit["unit_id"] for unit in expected_units]
        got_unit_ids = [unit.get("unit_id") for unit in got_units if isinstance(unit, dict)]
        if got_unit_ids != expected_unit_ids:
            errors.append(f"{paragraph_id}: unit id/order mismatch: expected {expected_unit_ids}, got {got_unit_ids}")
        for u_index, unit in enumerate(got_units):
            if not isinstance(unit, dict):
                errors.append(f"{paragraph_id}.units[{u_index}]: must be object")
                continue
            expected_wenyan = expected_units[u_index]["source_wenyan"] if u_index < len(expected_units) else ""
            require_content = source_has_content(expected_wenyan)
            zh = plain_text(unit.get("zh_modern"))
            ja = plain_text(unit.get("ja_modern"))
            en = plain_text(unit.get("en"))
            if not zh or (require_content and not HAN_RE.search(zh)):
                errors.append(f"{paragraph_id}.units[{u_index}].zh_modern: missing Chinese")
            if KANA_RE.search(zh):
                errors.append(f"{paragraph_id}.units[{u_index}].zh_modern: contains Japanese kana")
            if not ja or (require_content and len("".join(ja.split())) > 8 and not KANA_RE.search(ja)):
                errors.append(f"{paragraph_id}.units[{u_index}].ja_modern: must be real Japanese with kana")
            if not en or (require_content and not re.search(r"[A-Za-z]", en)):
                errors.append(f"{paragraph_id}.units[{u_index}].en: missing English")
    return errors


def promote_plain_chunk(source: dict[str, Any], plain: dict[str, Any]) -> dict[str, Any]:
    source_paragraphs = {p["id"]: p for p in source.get("paragraphs", [])}
    expected_units_by_paragraph = {
        paragraph["id"]: {unit["unit_id"]: unit["source_wenyan"] for unit in paragraph["units"]}
        for paragraph in source_unit_plan(source)
    }
    strict = {
        "schema_version": "0.1",
        "mode": "quadrilingual_wenyan_main",
        "chunk_id": source["chunk_id"],
        "chapter": {
            "id": source["chapter_id"],
            "number": source["chapter_number"],
            "title": {
                "wenyan": tokenize_zh(str(source.get("chapter_title_wenyan") or "")),
                "zh_modern": tokenize_zh(str(source.get("chapter_title_zh_modern") or source.get("chapter_title_wenyan") or "")),
                "ja_modern": tokenize_ja(str(source.get("chapter_title_ja_modern") or source.get("chapter_title_wenyan") or "")),
                "en": tokenize_en(str(source.get("chapter_title_en") or f"Book {source['chapter_number']}")),
            },
        },
        "paragraphs": [],
    }
    for paragraph in plain.get("paragraphs", []):
        paragraph_id = paragraph["id"]
        source_paragraph = source_paragraphs[paragraph_id]
        expected_units = expected_units_by_paragraph.get(paragraph_id, {})
        strict_paragraph = {
            "id": paragraph_id,
            "source_wenyan": source_paragraph["wenyan"],
            "units": [],
        }
        for unit in paragraph.get("units", []):
            source_wenyan = str(expected_units.get(unit.get("unit_id")) or unit.get("source_wenyan", ""))
            strict_paragraph["units"].append(
                {
                    "source_wenyan": source_wenyan,
                    "wenyan": tokenize_zh(source_wenyan),
                    "zh_modern": tokenize_zh(plain_text(unit.get("zh_modern", ""))),
                    "ja_modern": tokenize_ja(plain_text(unit.get("ja_modern", ""))),
                    "en": tokenize_en(plain_text(unit.get("en", ""))),
                }
            )
        strict["paragraphs"].append(strict_paragraph)
    return strict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="medium")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--failed-retry-age-seconds", type=int, default=1800)
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = load_chunks(Path(args.chunks_jsonl))
    canonical_dir = Path(args.canonical_dir)
    candidate_dir = Path(args.candidate_dir)
    work_dir = Path(args.work_dir)
    claim_dir = candidate_dir / "claims"
    accepted_dir = candidate_dir / "accepted"
    plain_dir = candidate_dir / "plain-accepted"
    rejected_dir = candidate_dir / "rejected"
    failed_dir = candidate_dir / "failed"
    status_dir = candidate_dir / "status"
    for path in (claim_dir, accepted_dir, plain_dir, rejected_dir, failed_dir, status_dir, canonical_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    while True:
        claimed: tuple[int, dict[str, Any]] | None = None
        for item in iter_selected(chunks, args.start_index, args.end_index):
            _index, chunk = item
            chunk_id = chunk["chunk_id"]
            canonical_path = canonical_dir / f"{chunk_id}.json"
            if valid_existing(canonical_path, chunk) or valid_existing(accepted_dir / f"{chunk_id}.json", chunk):
                continue
            failed_path = failed_dir / f"{chunk_id}.json"
            if failed_path.exists():
                if not args.retry_failed:
                    continue
                if args.failed_retry_age_seconds > 0 and time.time() - failed_path.stat().st_mtime < args.failed_retry_age_seconds:
                    continue
            if claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
                failed_path.unlink(missing_ok=True)
                claimed = item
                break
        if claimed is None:
            print(f"{args.worker_id}: no claimable chunks; accepted={completed} failed={failed}", flush=True)
            return 0

        _index, chunk = claimed
        chunk_id = chunk["chunk_id"]
        errors: list[str] | None = None
        try:
            if not chunk_has_source_content(chunk):
                plain = deterministic_plain_chunk(chunk)
                errors = validate_plain_chunk(chunk, plain)
                if errors:
                    raise ValueError("; ".join(errors[:60]))
                strict = promote_plain_chunk(chunk, plain)
                errors = validate_chunk(chunk, strict)
                if errors:
                    raise ValueError("; ".join(errors[:60]))
                write_json(plain_dir / f"{chunk_id}.json", plain)
                write_json(accepted_dir / f"{chunk_id}.json", strict)
                write_json(canonical_dir / f"{chunk_id}.json", strict)
                write_json(
                    status_dir / f"{chunk_id}.json",
                    status_record("accepted", chunk_id=chunk_id, note="deterministic no-Han source chunk"),
                )
                completed += 1
                continue
            for attempt in range(1, args.retries + 2):
                prompt = prompt_for_plain_chunk(chunk, errors)
                prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                log_path = work_dir / "logs" / f"{chunk_id}.log"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")
                print(f"{args.worker_id}: codex quadrilingual {chunk_id} attempt {attempt}", flush=True)
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
                    raw_text = message_path.read_text(encoding="utf-8")
                    plain = extract_json(raw_text)
                    plain = repair_catalog_like_ja(chunk, plain)
                    errors = validate_plain_chunk(chunk, plain)
                    if errors:
                        raise ValueError("; ".join(errors[:60]))
                    strict = promote_plain_chunk(chunk, plain)
                    errors = validate_chunk(chunk, strict)
                    if errors:
                        raise ValueError("; ".join(errors[:60]))
                except Exception as exc:  # noqa: BLE001
                    raw_log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
                    if mentions_usage_limit(raw_log):
                        print(f"{args.worker_id}: usage limit mentioned for {chunk_id}; leaving claim for retry", flush=True)
                        raise
                    errors = [str(exc)]
                    write_json(rejected_dir / f"{chunk_id}.attempt{attempt}.json", status_record("rejected", error=str(exc)))
                    if attempt <= args.retries:
                        continue
                    write_json(failed_dir / f"{chunk_id}.json", status_record("failed", error=str(exc), chunk_id=chunk_id))
                    failed += 1
                    break
                else:
                    write_json(plain_dir / f"{chunk_id}.json", plain)
                    write_json(accepted_dir / f"{chunk_id}.json", strict)
                    write_json(canonical_dir / f"{chunk_id}.json", strict)
                    write_json(status_dir / f"{chunk_id}.json", status_record("accepted", chunk_id=chunk_id))
                    completed += 1
                    break
        finally:
            release_claim(claim_dir, chunk_id)
        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: reached max_chunks={args.max_chunks}", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
