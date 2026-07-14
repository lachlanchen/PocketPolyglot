#!/usr/bin/env python3
"""Generate and review one worker shard of a polished pocket-book task."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pocket_polished_common import (
    OUTPUT_ROOT,
    ROOT,
    apply_grounded_english_repairs,
    chunk_subset,
    conservative_english_repair,
    machine_review_observations,
    read_json,
    read_jsonl,
    validate_chunk_output,
    validate_segment_output,
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
JAPANESE_SCRIPT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_SOURCE_CACHE_INDEX: dict[Path, dict[str, list[dict[str, Any]]]] = {}


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


def model_task_view(task: dict[str, Any], *, source_english: bool) -> dict[str, Any]:
    """Remove validator-only signatures from prompts while retaining evidence."""

    segments: list[dict[str, Any]] = []
    for segment in task["segments"]:
        row = {
            "segment_id": segment["segment_id"],
            "kind": segment["kind"],
            "source_tex": segment["source_tex"],
            "protected": segment.get("protected", []),
        }
        if source_english:
            _baseline, automatic = conservative_english_repair(segment["source_tex"])
            row["automatic_en_repairs"] = automatic
        segments.append(row)
    return {
        "schema_version": task.get("schema_version", 1),
        "book_id": task["book_id"],
        "title": task.get("title", task["book_id"]),
        "source_language": task.get("source_language", "en"),
        "validation_profile": task.get("validation_profile", "prose_exact"),
        "chunk_id": task["chunk_id"],
        "segment_count": len(segments),
        "segments": segments,
    }


def writer_prompt(task: dict[str, Any], feedback: list[str]) -> str:
    feedback_text = "\n".join(f"- {item}" for item in feedback) if feedback else "- none"
    source_language = task.get("source_language", "en")
    if source_language == "en":
        view = model_task_view(task, source_english=True)
        return f"""Produce a source-faithful publication-quality Japanese rendering of the supplied English TeX segments.

This is a constrained transcription/translation pass, not creative writing.

Rules:
1. Return each requested segment exactly once and in the supplied order.
2. ja_tex must be complete, natural, readable modern Japanese. Preserve every claim, qualification, name, date, numeric value, unit, ordering relation, and technical term.
3. Keep every @@PROTECTED_NNNN@@ token exactly once and in the same order. Protected values are immutable equations, figures, references, labels, URLs, or inline math; never reconstruct them.
4. Preserve structural TeX commands, balanced braces, table rows/columns, and object placement. Translate only human-readable text.
5. Audit every English source segment for definite OCR defects: fused words or sentences, missing spaces, presentation ligatures, obvious misspellings, duplicated running headers, and damaged punctuation. Do not return a rewritten English copy. The program reconstructs English from the immutable source. Use repairs only for a definite defect not already listed in automatic_en_repairs. Each repair.before must be an exact unique source_tex substring, confidence must be at least 0.90, and the repair must not touch a protected token.
6. Natural Japanese numeral formatting is allowed, but the numeric value must remain exact. Check every number before returning.
7. If damage cannot be resolved from supplied evidence, preserve the meaning conservatively and record it in unresolved. Never invent missing content.
8. Return only schema-valid JSON. Do not edit files or call tools.

Feedback for only the still-unresolved segments:
{feedback_text}

Task JSON:
{json.dumps(view, ensure_ascii=False, separators=(",", ":"))}
"""
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
    technical_instruction = ""
    protected_instruction = (
        "Keep every @@PROTECTED_NNNN@@ token exactly once and in the same order. They represent equations, "
        "figures, citations, labels, URLs, or inline math."
    )
    structure_instruction = (
        "Preserve the exact TeX command sequence, braces, table rows/columns, numbers, equation references, "
        "names, dates, units, and ordering."
    )
    if task.get("validation_profile") == "technical_exact":
        technical_instruction = (
            "This is an exact technical-book pass. Treat equations, figures, diagrams, flowcharts, tables, "
            "captions, exercises, music notation, chord diagrams, and fretboards as first-class source content. "
            "Never rewrite mathematical expressions or visual-object tokens from memory. Mathematical TeX is "
            "visible so that definite OCR/transcription defects can be repaired; apply such a repair only when "
            "the supplied source and local context make it unambiguous, record it in changes, and use the exact "
            "same corrected mathematical atoms and duplicate counts in en_tex and ja_tex; Japanese may reorder "
            "expressions or split a semicolon-separated expression only where its natural grammar requires it. "
            "In editable tables, preserve "
            "every row, column, symbol, "
            "unit, and relation while correcting only evidence-clear OCR text."
        )
        protected_instruction = (
            "Keep every @@PROTECTED_NNNN@@ token exactly once and in the same order. They represent immutable "
            "figures, citations, labels, references, or URLs."
        )
        structure_instruction = (
            "Preserve structural TeX commands, braces, table rows/columns, numbers, equation references, names, "
            "dates, units, and ordering. Mathematical commands may change only for a definite, grounded OCR "
            "repair and must then be preserved exactly in both en_tex and ja_tex."
        )
    return f"""You are producing a source-faithful, publication-quality English/Japanese edition of one technical or scholarly book chunk.

This is transcription repair and translation, not creative writing. The supplied exact TeX is the authority.
{technical_instruction}

Required work:
1. {english_instruction}
2. For ja_tex, provide complete, natural, modern, readable Japanese faithful to every claim and qualification in the English source. Do not omit or add facts.
3. {protected_instruction}
4. {structure_instruction}
   Preserve every Arabic digit sequence already present in the source. Do not invent numerical facts. A conventional target-language rendering of a written number or Roman ordinal may use digits only when its value is unambiguous (for example, "Leopold I" may be レオポルト1世); the semantic reviewer will verify it against the source.
5. Do not invent missing words. If source damage cannot be resolved from context with high confidence, preserve it and list the uncertainty in unresolved.
6. {change_instruction}
7. Return only JSON matching the supplied schema. Do not edit files and do not call another agent.

Feedback from earlier validation/review:
{feedback_text}

Task JSON:
{json.dumps(model_task_view(task, source_english=False), ensure_ascii=False, separators=(",", ":"))}
"""


def reviewer_prompt(task: dict[str, Any], candidate: dict[str, Any]) -> str:
    technical_instruction = ""
    if task.get("validation_profile") == "technical_exact":
        technical_instruction = (
            "For this exact technical edition, independently verify that editable table structure and all visible "
            "technical labels remain complete, and that no equation, figure, diagram, flowchart, music notation, "
            "exercise, unit, or symbol has been inferred or silently omitted. The mathematical-expression multiset "
            "must be identical between en_tex and ja_tex, though Japanese may reorder complete expressions; accept "
            "a mathematical correction only when it is an unambiguous source OCR "
            "repair with a grounded changes record."
        )
    observations = machine_review_observations(task, candidate)
    return f"""Act as a strict bilingual textual editor validating proposed English/Japanese TeX segments against their source.

Accept only if all source content is retained in order, English changes are definite corrections, Japanese is complete/natural/accurate, and no claim, name, numerical fact, qualification, table relation, equation reference, or protected TeX object is added, removed, or altered.

Do not demand stylistic rewrites. Do not reject faithful literal terminology merely because another translation is possible. A navigation anchor such as hypertarget/hyperlink may move within the same segment when target-language word order requires it; accept that when the anchor content and command order are unchanged. Accept equivalent natural Japanese numeral notation only after verifying the value. Content-bearing figures, equations, citations, labels, and references must remain attached to the corresponding content. Reject factual invention, omissions, mistranslation, unresolved OCR silently guessed, garbled Japanese, or structural corruption.

Review each segment independently. Reject any obvious English OCR/spelling/word-fusion defect that remains in en_tex, as well as a Japanese error. If accept is false, every blocking issue must name the exact supplied segment_id. For every blocking issue that you can fix from the supplied evidence, also return a complete corrected compact segment in corrections: corrected ja_tex plus any grounded English repairs. The repairs array is exclusively for exact English source_tex patches; never put a Japanese edit or explanation in repairs because ja_tex itself carries the complete Japanese correction. corrections must be empty when no correction is needed. Do not reject correct segments because another segment failed. Use severity=warning only for a non-blocking observation. Return only JSON matching the review schema.
{technical_instruction}

Source task:
{json.dumps(model_task_view(task, source_english=False), ensure_ascii=False, separators=(",", ":"))}

Candidate:
{json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))}

Machine observations requiring semantic verification (not automatic failures):
{json.dumps(observations, ensure_ascii=False, separators=(",", ":"))}
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


def reported_token_usage(text: str) -> int:
    matches = re.findall(r"tokens used\s*\n\s*([\d,]+)", text, re.I)
    return int(matches[-1].replace(",", "")) if matches else 0


def valid_existing(task: dict[str, Any], path: Path) -> bool:
    try:
        result = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return not validate_chunk_output(task, result)


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        try:
            match = re.search(r"\bpid=(\d+)\b", path.read_text(encoding="utf-8"))
        except OSError:
            return None
        if not match or process_is_alive(int(match.group(1))):
            return None
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        try:
            return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return None


def canonicalize_writer_result(
    task: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Convert compact model output into canonical per-segment records."""

    errors: dict[str, list[str]] = {
        source["segment_id"]: [] for source in task["segments"]
    }
    expected_ids = list(errors)
    source_english = task.get("source_language", "en") == "en"
    expected_schema = 3 if source_english else 1
    header_errors: list[str] = []
    if result.get("schema_version") != expected_schema:
        header_errors.append(f"schema_version must be {expected_schema}")
    if result.get("book_id") != task["book_id"]:
        header_errors.append("book_id mismatch")
    if result.get("chunk_id") != task["chunk_id"]:
        header_errors.append("chunk_id mismatch")
    rows = result.get("segments")
    if not isinstance(rows, list):
        header_errors.append("segments must be an array")
        rows = []
    actual: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        segment_id = row.get("segment_id")
        if not isinstance(segment_id, str):
            continue
        if segment_id in actual:
            duplicates.add(segment_id)
        actual[segment_id] = row
    unexpected = sorted(set(actual) - set(expected_ids))
    if unexpected:
        header_errors.append(f"unexpected segment IDs: {unexpected}")
    if header_errors:
        for segment_id in expected_ids:
            errors[segment_id].extend(header_errors)

    canonical: dict[str, dict[str, Any]] = {}
    for source in task["segments"]:
        segment_id = source["segment_id"]
        row = actual.get(segment_id)
        if row is None:
            errors[segment_id].append("model omitted the segment")
            continue
        if segment_id in duplicates:
            errors[segment_id].append("model returned the segment more than once")
        if not source_english and row.get("source_sha256") != source["source_sha256"]:
            errors[segment_id].append("source_sha256 mismatch")
        if source_english:
            ja_tex = row.get("ja_tex")
            repairs = row.get("repairs")
            unresolved = row.get("unresolved")
            if not isinstance(ja_tex, str):
                errors[segment_id].append("ja_tex must be a string")
                continue
            if not isinstance(repairs, list):
                errors[segment_id].append("repairs must be an array")
                continue
            if not isinstance(unresolved, list):
                errors[segment_id].append("unresolved must be an array")
                continue
            en_tex, changes, repair_errors = apply_grounded_english_repairs(
                source["source_tex"], repairs
            )
            errors[segment_id].extend(repair_errors)
            canonical[segment_id] = {
                "segment_id": segment_id,
                "source_sha256": source["source_sha256"],
                "en_tex": en_tex,
                "ja_tex": ja_tex,
                "changes": changes,
                "unresolved": unresolved,
            }
        else:
            canonical[segment_id] = row
    return canonical, errors


def sanitize_reviewer_corrections(
    task: dict[str, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop Japanese edit annotations mistakenly placed in English patches.

    Reviewer ``ja_tex`` is the complete Japanese correction.  A reviewer may
    nevertheless echo a Japanese before/after explanation in ``repairs``.
    Keeping that annotation makes the strict English patch validator reject
    the entire correction and wastes another writer/reviewer cycle.  Only
    clearly Japanese patch entries are ignored here; malformed or ungrounded
    Latin-source patches remain visible to strict validation.
    """

    source_map = {source["segment_id"]: source for source in task["segments"]}
    sanitized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        copied = dict(row)
        repairs = row.get("repairs")
        if isinstance(repairs, list):
            copied["repairs"] = [
                repair
                for repair in repairs
                if not (
                    isinstance(repair, dict)
                    and isinstance(repair.get("before"), str)
                    and JAPANESE_SCRIPT_RE.search(repair["before"])
                    and repair["before"]
                    not in source_map.get(row.get("segment_id"), {}).get(
                        "source_tex", ""
                    )
                )
            ]
        sanitized.append(copied)
    return sanitized


def candidate_from_outputs(
    task: dict[str, Any],
    outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "book_id": task["book_id"],
        "chunk_id": task["chunk_id"],
        "segments": [outputs[source["segment_id"]] for source in task["segments"]],
    }


def segment_cache_path(book_root: Path, segment_id: str) -> Path:
    return book_root / "work/accepted-segments" / f"{segment_id}.json"


def migrate_legacy_cached_output(
    task: dict[str, Any],
    source: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any] | None:
    """Upgrade old ambiguous spacing evidence without another model call."""

    if task.get("source_language", "en") != "en":
        return None
    changes = output.get("changes")
    if not isinstance(changes, list):
        return None
    retained: list[dict[str, Any]] = []
    migrated_any = False
    for change in changes:
        if (
            isinstance(change, dict)
            and change.get("before") == "."
            and change.get("after") == ". "
            and change.get("reason")
            == "Restored missing whitespace after sentence punctuation."
        ):
            # Early pipeline versions recorded only the punctuation mark.  The
            # current deterministic pre-pass records the complete neighboring
            # words, making the repair replay unique and auditable.
            migrated_any = True
            continue
        if isinstance(change, dict):
            retained.append(change)
    if not migrated_any:
        return None
    en_tex, canonical_changes, errors = apply_grounded_english_repairs(
        source["source_tex"], retained
    )
    if errors:
        return None
    migrated = dict(output)
    migrated["segment_id"] = source["segment_id"]
    migrated["source_sha256"] = source["source_sha256"]
    migrated["en_tex"] = en_tex
    migrated["changes"] = canonical_changes
    if validate_segment_output(task, source, migrated):
        return None
    return migrated


def load_cached_segment(
    task: dict[str, Any],
    source: dict[str, Any],
    book_root: Path,
) -> dict[str, Any] | None:
    path = segment_cache_path(book_root, source["segment_id"])
    payloads: list[dict[str, Any]] = []
    try:
        direct = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        direct = None
    if isinstance(direct, dict):
        payloads.append(direct)

    if not payloads:
        cache_root = (book_root / "work/accepted-segments").resolve()
        index = _SOURCE_CACHE_INDEX.get(cache_root)
        if index is None:
            index = {}
            for candidate_path in cache_root.glob("*.json"):
                try:
                    candidate = read_json(candidate_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(candidate, dict):
                    continue
                source_hash = candidate.get("source_sha256")
                if isinstance(source_hash, str):
                    index.setdefault(source_hash, []).append(candidate)
            _SOURCE_CACHE_INDEX[cache_root] = index
        payloads.extend(index.get(source["source_sha256"], []))

    for payload in payloads:
        output = payload.get("output") if isinstance(payload, dict) else None
        if not isinstance(output, dict) or payload.get("book_id") != task["book_id"]:
            continue
        if payload.get("source_sha256") != source["source_sha256"]:
            continue
        output = dict(output)
        output["segment_id"] = source["segment_id"]
        output["source_sha256"] = source["source_sha256"]
        if not validate_segment_output(task, source, output):
            return output
        migrated = migrate_legacy_cached_output(task, source, output)
        if migrated is not None:
            return migrated
    return None


def save_cached_segment(
    task: dict[str, Any],
    source: dict[str, Any],
    output: dict[str, Any],
    review: dict[str, Any],
    book_root: Path,
) -> None:
    errors = validate_segment_output(task, source, output)
    if errors:
        raise ValueError("cannot cache invalid segment: " + "; ".join(errors))
    write_json(
        segment_cache_path(book_root, source["segment_id"]),
        {
            "schema_version": 1,
            "book_id": task["book_id"],
            "source_chunk_id": task["chunk_id"],
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "output": output,
            "review": review,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    _SOURCE_CACHE_INDEX.pop(
        (book_root / "work/accepted-segments").resolve(), None
    )


def load_pending_review_segments(
    task: dict[str, Any], book_root: Path
) -> dict[str, dict[str, Any]]:
    """Recover deterministically valid, not-yet-reviewed output from older runs.

    A process interruption or validator improvement must not force the writer to
    regenerate a segment that already has a valid canonical candidate.  Direct
    segment IDs are preferred.  Source-hash migration is allowed only when that
    hash identifies exactly one current segment, which keeps recovery safe after
    content-addressed ID migrations or conservative rechunking.
    """

    current_by_id = {source["segment_id"]: source for source in task["segments"]}
    current_by_hash: dict[str, list[dict[str, Any]]] = {}
    for source in task["segments"]:
        current_by_hash.setdefault(source["source_sha256"], []).append(source)

    pattern = (
        f"work/runs/*/attempts/{task['chunk_id']}/"
        "attempt-*.pending-review.json"
    )
    candidates = sorted(
        book_root.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    recovered: dict[str, dict[str, Any]] = {}
    for path in candidates:
        try:
            payload = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if (
            not isinstance(payload, dict)
            or payload.get("book_id") != task["book_id"]
            or payload.get("chunk_id") != task["chunk_id"]
            or not isinstance(payload.get("segments"), list)
        ):
            continue
        review_path = path.with_name(
            path.name.replace(".pending-review.json", ".review.json")
        )
        blocking_ids: set[str] = set()
        reject_all = False
        try:
            completed_review = read_json(review_path)
        except (OSError, ValueError, json.JSONDecodeError):
            completed_review = None
        if isinstance(completed_review, dict):
            for issue in completed_review.get("issues", []):
                if not isinstance(issue, dict) or issue.get("severity") == "warning":
                    continue
                segment_id = issue.get("segment_id")
                if isinstance(segment_id, str):
                    blocking_ids.add(segment_id)
            reject_all = not completed_review.get("accept") and not blocking_ids
        for row in payload["segments"]:
            if not isinstance(row, dict):
                continue
            if reject_all or row.get("segment_id") in blocking_ids:
                continue
            source = current_by_id.get(row.get("segment_id"))
            source_hash = row.get("source_sha256")
            if source is not None and source_hash != source["source_sha256"]:
                source = None
            if source is None and isinstance(source_hash, str):
                matches = current_by_hash.get(source_hash, [])
                if len(matches) == 1:
                    source = matches[0]
            if source is None or source["segment_id"] in recovered:
                continue
            migrated = dict(row)
            migrated["segment_id"] = source["segment_id"]
            migrated["source_sha256"] = source["source_sha256"]
            if not validate_segment_output(task, source, migrated):
                recovered[source["segment_id"]] = migrated
    return recovered


def write_metrics(book_root: Path, chunk_id: str, metrics: dict[str, Any]) -> None:
    metrics["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(book_root / "work/metrics" / f"{chunk_id}.json", metrics)


def process_chunk(
    task: dict[str, Any],
    *,
    book_root: Path,
    model: str,
    reasoning: str,
    retries: int,
    review_retries: int,
    timeout: int,
    backoff: int,
) -> bool:
    chunk_id = task["chunk_id"]
    output_path = book_root / "json" / f"{chunk_id}.json"
    failed_path = book_root / "work/failed" / f"{chunk_id}.json"
    if valid_existing(task, output_path):
        failed_path.unlink(missing_ok=True)
        print(f"skip valid {chunk_id}", flush=True)
        return True
    lock_path = book_root / "work/locks" / f"{chunk_id}.lock"
    lock_fd = acquire_lock(lock_path)
    if lock_fd is None:
        print(f"skip locked {chunk_id}", flush=True)
        return True
    os.write(lock_fd, f"pid={os.getpid()}\n".encode())
    os.close(lock_fd)
    metrics: dict[str, Any] = {
        "chunk_id": chunk_id,
        "segment_count": len(task["segments"]),
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + f"-{os.getpid()}",
        "writer_calls": 0,
        "reviewer_calls": 0,
        "writer_tokens": 0,
        "reviewer_tokens": 0,
        "cache_hits": 0,
        "pending_review_hits": 0,
        "accepted_segments": 0,
        "writer_passes": [],
    }
    try:
        accepted: dict[str, dict[str, Any]] = {}
        feedback_by_segment: dict[str, list[str]] = {}
        for source in task["segments"]:
            cached = load_cached_segment(task, source, book_root)
            if cached is not None:
                accepted[source["segment_id"]] = cached
                metrics["cache_hits"] += 1

        staged_for_review = load_pending_review_segments(task, book_root)
        attempt = 1
        reviewer_blocked = False
        while attempt <= retries and len(accepted) < len(task["segments"]):
            pending_ids = [
                source["segment_id"]
                for source in task["segments"]
                if source["segment_id"] not in accepted
            ]
            prefix = (
                book_root
                / "work/runs"
                / metrics["run_id"]
                / "attempts"
                / chunk_id
                / f"attempt-{attempt:02d}"
            )
            recovered_ids = [
                segment_id
                for segment_id in pending_ids
                if segment_id in staged_for_review
            ]
            if recovered_ids:
                active_task = chunk_subset(task, recovered_ids)
                valid_for_review = {
                    segment_id: staged_for_review.pop(segment_id)
                    for segment_id in recovered_ids
                }
                source_map = {
                    source["segment_id"]: source
                    for source in active_task["segments"]
                }
                metrics["pending_review_hits"] += len(recovered_ids)
                pass_metrics = {
                    "attempt": attempt,
                    "origin": "recovered_pending_review",
                    "requested_segments": len(recovered_ids),
                    "deterministic_valid": len(valid_for_review),
                    "deterministic_rejected": 0,
                    "semantic_accepted": 0,
                    "semantic_rejected": 0,
                    "reviewer_corrected": 0,
                }
            else:
                active_task = chunk_subset(task, pending_ids)
                feedback = [
                    f"{segment_id}: {message}"
                    for segment_id in pending_ids
                    for message in feedback_by_segment.get(segment_id, [])[:8]
                ]
                writer_message = prefix.with_suffix(".writer.json")
                writer_log = prefix.with_suffix(".writer.log")
                writer_schema = (
                    OUTPUT_ROOT / "tasks/polish-source-en-output.schema.json"
                    if task.get("source_language", "en") == "en"
                    else OUTPUT_ROOT / "tasks/polish-output.schema.json"
                )
                metrics["writer_calls"] += 1
                rc, raw = run_codex(
                    writer_prompt(active_task, feedback),
                    schema=writer_schema,
                    message=writer_message,
                    log=writer_log,
                    model=model,
                    reasoning=reasoning,
                    timeout=timeout,
                )
                metrics["writer_tokens"] += reported_token_usage(raw)
                if rc != 0:
                    if "model is not supported" in raw.lower() or (
                        "model metadata" in raw.lower()
                        and "invalid_request" in raw.lower()
                    ):
                        raise RuntimeError(f"unsupported model {model}; see {writer_log}")
                    if is_transient(raw):
                        print(
                            f"transient writer failure {chunk_id}; sleeping {backoff}s",
                            flush=True,
                        )
                        time.sleep(backoff)
                        continue
                    for segment_id in pending_ids:
                        feedback_by_segment[segment_id] = [
                            f"writer command failed on attempt {attempt}; return valid schema JSON"
                        ]
                    attempt += 1
                    continue
                try:
                    raw_candidate = extract_json(
                        writer_message.read_text(encoding="utf-8")
                    )
                except Exception as exc:
                    for segment_id in pending_ids:
                        feedback_by_segment[segment_id] = [
                            f"output was not valid JSON: {exc}"
                        ]
                    attempt += 1
                    continue
                canonical, conversion_errors = canonicalize_writer_result(
                    active_task, raw_candidate
                )
                write_json(
                    prefix.with_suffix(".writer-canonical.json"),
                    {
                        "schema_version": 1,
                        "book_id": task["book_id"],
                        "chunk_id": chunk_id,
                        "segments": [
                            canonical[segment_id]
                            for segment_id in pending_ids
                            if segment_id in canonical
                        ],
                    },
                )
                valid_for_review: dict[str, dict[str, Any]] = {}
                deterministic_errors: dict[str, list[str]] = {}
                source_map = {
                    source["segment_id"]: source
                    for source in active_task["segments"]
                }
                for segment_id in pending_ids:
                    segment_errors = list(conversion_errors.get(segment_id, []))
                    output = canonical.get(segment_id)
                    if output is not None:
                        segment_errors.extend(
                            validate_segment_output(
                                active_task, source_map[segment_id], output
                            )
                        )
                    if segment_errors:
                        deterministic_errors[segment_id] = segment_errors
                        feedback_by_segment[segment_id] = segment_errors
                    elif output is not None:
                        valid_for_review[segment_id] = output
                if deterministic_errors:
                    write_json(
                        prefix.with_suffix(".deterministic-rejection.json"),
                        {"errors_by_segment": deterministic_errors},
                    )

                pass_metrics = {
                    "attempt": attempt,
                    "origin": "writer",
                    "requested_segments": len(pending_ids),
                    "deterministic_valid": len(valid_for_review),
                    "deterministic_rejected": len(deterministic_errors),
                    "semantic_accepted": 0,
                    "semantic_rejected": 0,
                    "reviewer_corrected": 0,
                }
            if valid_for_review:
                review_ids = [
                    segment_id for segment_id in pending_ids if segment_id in valid_for_review
                ]
                review_task = chunk_subset(active_task, review_ids)
                review_candidate = candidate_from_outputs(review_task, valid_for_review)
                write_json(prefix.with_suffix(".pending-review.json"), review_candidate)
                review: dict[str, Any] | None = None
                review_failure = ""
                for review_attempt in range(1, review_retries + 1):
                    suffix = "" if review_attempt == 1 else f"-{review_attempt:02d}"
                    review_message = prefix.with_name(prefix.name + suffix).with_suffix(
                        ".review.json"
                    )
                    review_log = prefix.with_name(prefix.name + suffix).with_suffix(
                        ".review.log"
                    )
                    metrics["reviewer_calls"] += 1
                    rc, raw = run_codex(
                        reviewer_prompt(review_task, review_candidate),
                        schema=OUTPUT_ROOT / "tasks/semantic-review.schema.json",
                        message=review_message,
                        log=review_log,
                        model=model,
                        reasoning=reasoning,
                        timeout=timeout,
                    )
                    metrics["reviewer_tokens"] += reported_token_usage(raw)
                    if rc != 0:
                        review_failure = f"semantic reviewer command failed (rc={rc})"
                        if is_transient(raw):
                            print(
                                f"transient review failure {chunk_id}; sleeping {backoff}s",
                                flush=True,
                            )
                            time.sleep(backoff)
                        continue
                    try:
                        review = extract_json(review_message.read_text(encoding="utf-8"))
                    except Exception as exc:
                        review_failure = f"semantic reviewer returned invalid JSON: {exc}"
                        continue
                    break
                if review is None:
                    # Preserve the already-generated candidate.  A reviewer
                    # outage must never trigger another expensive writer call.
                    write_json(
                        prefix.with_suffix(".review-pending.json"),
                        {
                            "candidate": review_candidate,
                            "failure": review_failure,
                        },
                    )
                    for segment_id in review_ids:
                        feedback_by_segment[segment_id] = [review_failure]
                    reviewer_blocked = True
                    metrics["writer_passes"].append(pass_metrics)
                    break

                blocking: dict[str, list[str]] = {}
                warnings: dict[str, list[str]] = {}
                for issue in review.get("issues", []):
                    if not isinstance(issue, dict):
                        continue
                    segment_id = issue.get("segment_id")
                    if segment_id not in valid_for_review:
                        continue
                    target = warnings if issue.get("severity") == "warning" else blocking
                    target.setdefault(segment_id, []).append(
                        str(issue.get("message", "semantic review issue"))
                    )
                declared_blocking = bool(blocking)
                correction_rows = review.get("corrections", [])
                if (
                    task.get("source_language", "en") == "en"
                    and isinstance(correction_rows, list)
                    and blocking
                ):
                    correction_ids = [
                        row.get("segment_id")
                        for row in correction_rows
                        if isinstance(row, dict) and row.get("segment_id") in blocking
                    ]
                    correction_ids = list(dict.fromkeys(correction_ids))
                    if correction_ids:
                        correction_task = chunk_subset(review_task, correction_ids)
                        selected_corrections = [
                            row
                            for row in correction_rows
                            if isinstance(row, dict)
                            and row.get("segment_id") in correction_ids
                        ]
                        correction_result = {
                            "schema_version": 3,
                            "book_id": task["book_id"],
                            "chunk_id": chunk_id,
                            "segments": sanitize_reviewer_corrections(
                                correction_task, selected_corrections
                            ),
                        }
                        corrected, correction_errors = canonicalize_writer_result(
                            correction_task, correction_result
                        )
                        correction_source_map = {
                            source["segment_id"]: source
                            for source in correction_task["segments"]
                        }
                        for segment_id in correction_ids:
                            output = corrected.get(segment_id)
                            errors = list(correction_errors.get(segment_id, []))
                            if output is not None:
                                errors.extend(
                                    validate_segment_output(
                                        correction_task,
                                        correction_source_map[segment_id],
                                        output,
                                    )
                                )
                            if errors:
                                feedback_by_segment[segment_id] = errors
                                continue
                            valid_for_review[segment_id] = output
                            blocking.pop(segment_id, None)
                            pass_metrics["reviewer_corrected"] += 1
                if (
                    not review.get("accept")
                    and not declared_blocking
                    and not blocking
                    and not warnings
                ):
                    # A false verdict without a blocking segment cannot safely
                    # identify a repair unit, so retry only this reviewed subset.
                    fallback = str(review.get("summary", "semantic review rejected"))
                    blocking = {segment_id: [fallback] for segment_id in review_ids}

                for segment_id in review_ids:
                    if segment_id in blocking:
                        feedback_by_segment[segment_id] = blocking[segment_id]
                        continue
                    segment_review = {
                        "accept": True,
                        "issues": warnings.get(segment_id, []),
                        "summary": review.get("summary", "segment accepted"),
                    }
                    save_cached_segment(
                        task,
                        source_map[segment_id],
                        valid_for_review[segment_id],
                        segment_review,
                        book_root,
                    )
                    accepted[segment_id] = valid_for_review[segment_id]
                    feedback_by_segment.pop(segment_id, None)
                pass_metrics["semantic_accepted"] = len(review_ids) - len(blocking)
                pass_metrics["semantic_rejected"] = len(blocking)
            metrics["writer_passes"].append(pass_metrics)
            attempt += 1

        if len(accepted) == len(task["segments"]):
            candidate = candidate_from_outputs(task, accepted)
            errors = validate_chunk_output(task, candidate)
            if errors:
                raise ValueError("cached canonical chunk failed validation: " + "; ".join(errors))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(output_path, candidate)
            write_json(
                book_root / "review" / f"{chunk_id}.json",
                {
                    "accept": True,
                    "issues": [],
                    "summary": "All segments accepted independently and cached with review evidence.",
                },
            )
            failed_path.unlink(missing_ok=True)
            metrics["accepted_segments"] = len(accepted)
            metrics["status"] = "accepted"
            write_metrics(book_root, chunk_id, metrics)
            print(
                f"accepted {chunk_id} writer_calls={metrics['writer_calls']} "
                f"reviewer_calls={metrics['reviewer_calls']} cache_hits={metrics['cache_hits']}",
                flush=True,
            )
            return True

        remaining = [
            source["segment_id"]
            for source in task["segments"]
            if source["segment_id"] not in accepted
        ]
        write_json(
            failed_path,
            {
                "chunk_id": chunk_id,
                "writer_attempts": metrics["writer_calls"],
                "reviewer_blocked": reviewer_blocked,
                "remaining_segments": remaining,
                "feedback_by_segment": {
                    segment_id: feedback_by_segment.get(segment_id, [])
                    for segment_id in remaining
                },
            },
        )
        metrics["accepted_segments"] = len(accepted)
        metrics["status"] = "reviewer_blocked" if reviewer_blocked else "failed_segments"
        metrics["remaining_segments"] = remaining
        write_metrics(book_root, chunk_id, metrics)
        print(
            f"failed {chunk_id}: accepted_segments={len(accepted)}/{len(task['segments'])} "
            f"writer_calls={metrics['writer_calls']} reviewer_calls={metrics['reviewer_calls']}",
            flush=True,
        )
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
    parser.add_argument("--review-retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--backoff", type=int, default=600)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument(
        "--chunk-id",
        action="append",
        default=[],
        help="Process only the named chunk(s), preserving manifest order.",
    )
    args = parser.parse_args()
    if args.worker_index < 1 or args.worker_index > args.workers:
        parser.error("worker index must be in 1..workers")

    book_root = OUTPUT_ROOT / args.book_id
    tasks = read_jsonl(book_root / "tasks/chunks.jsonl")
    if args.chunk_id:
        requested = set(args.chunk_id)
        unknown = sorted(requested - {task["chunk_id"] for task in tasks})
        if unknown:
            parser.error(f"unknown --chunk-id values: {', '.join(unknown)}")
        tasks = [task for task in tasks if task["chunk_id"] in requested]
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
            review_retries=args.review_retries,
            timeout=args.timeout,
            backoff=args.backoff,
        ):
            failures += 1
    print(f"worker={args.worker_index}/{args.workers} selected={len(selected)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
