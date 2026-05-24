#!/usr/bin/env python3
"""Review merged interlinear chunks and backfix broad quality failures."""

from __future__ import annotations

import argparse
import bisect
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

from codex_bilingual_chunk_worker import (
    GRAMMAR_ROLES,
    paragraph_target_text,
    prompt_for_chunk,
    source_requires_ocr_correction,
    validate_chunk,
)
from codex_chunk_worker import extract_json, load_chunks, run_codex
from normalize_grammar_roles import cleanup_components, normalize_node, normalize_ruby_token_shapes, normalize_source_artifacts
from reference_windows import expand_adjacent_jp_references
from validate_interlinear_json import ja_lines_text, normalize

PROMPT_VERSION = "broad-post-merge-review-v4"
CONTENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffぁ-ゟ゠-ヿA-Za-z0-9]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SENTENCE_END_RE = re.compile(r"[。！？!?]")
PUNCT_RE = re.compile(r"^[\s，。！？、；：,.!?;:「」『』（）()《》〈〉“”‘’…—-]+$")
EDITORIAL_NOTE_RE = re.compile(r"^(?:[（(]?\s*\d+\s*[.．、)]|[［\[]\s*\d+\s*[］\]])")
INLINE_NOTE_RE = re.compile(r"[［\[].{4,}?[］\]]")
REFERENCE_SKELETON_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffァ-ヿA-Za-z0-9]")
RUBY_READING_CHARS = r"[ぁ-ゟァ-ヿ]*"
ASCII_GARBAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_/|\\<>@#$%^&*=+~`]{5,}")
OCR_DEBRIS_RE = re.compile(r"[|<>@#$%^&*=+~`]{2,}|�|□|■")


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


def is_editorial_note(text: str) -> bool:
    compact = normalize(text)
    return (
        bool(EDITORIAL_NOTE_RE.match(compact))
        or bool(INLINE_NOTE_RE.search(compact))
        or any(marker in compact for marker in ("译者", "译注", "注释", "注："))
    )


def ocr_noise_issues(text: str, where: str) -> list[str]:
    issues: list[str] = []
    compact = normalize(text)
    if OCR_DEBRIS_RE.search(compact):
        issues.append(f"{where}: corrected_text still contains OCR debris symbols")
    if ASCII_GARBAGE_RE.search(compact):
        issues.append(f"{where}: corrected_text still contains likely OCR ASCII garbage")
    cjk_count = sum(1 for char in compact if HAN_RE.fullmatch(char))
    ascii_letter_count = sum(1 for char in compact if char.isascii() and char.isalpha())
    if cjk_count >= 20 and ascii_letter_count >= max(8, int(cjk_count * 0.08)):
        issues.append(f"{where}: corrected_text has too much ASCII letter noise for a Chinese source paragraph")
    return issues


def reference_skeleton_with_positions(text: str) -> tuple[str, list[int]]:
    """Compare Japanese source text while ignoring inline kana ruby readings.

    Some EPUB/Markdown sources flatten ruby as base kanji followed by kana,
    e.g. 軒のき端ば or 氷柱つらら. Generated JSON stores the base text in
    `t` and the reading in `r`, so exact substring matching would reject
    correct chunks. The skeleton keeps kanji, katakana, Latin, and digits for
    a conservative fallback match after exact matching fails.
    """

    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(normalize(text)):
        if REFERENCE_SKELETON_RE.fullmatch(char):
            chars.append(char)
            positions.append(index)
    return "".join(chars), positions


def reference_skeleton(text: str) -> str:
    return reference_skeleton_with_positions(text)[0]


def ruby_insensitive_pattern(text: str) -> str:
    parts: list[str] = []
    for char in normalize(text):
        if HAN_RE.fullmatch(char):
            # Source EPUB text may flatten ruby either after or before the base
            # kanji, e.g. 氷柱つらら or ほ惚. Generated chunks keep only the
            # base kanji in `t`, so tolerate both source forms.
            parts.append(RUBY_READING_CHARS)
            parts.append(re.escape(char))
            parts.append(RUBY_READING_CHARS)
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def reference_match_pos(
    reference_text: str,
    reference_skel: str,
    reference_skel_positions: list[int],
    text: str,
    *,
    min_pos: int = 0,
) -> int:
    compact = normalize(text)
    min_pos = max(0, min_pos)
    exact_pos = reference_text.find(compact, min_pos)
    if exact_pos >= 0:
        return exact_pos

    if HAN_RE.search(compact):
        ruby_match = re.search(ruby_insensitive_pattern(compact), reference_text[min_pos:])
        if ruby_match:
            return min_pos + ruby_match.start()

    skel = reference_skeleton(compact)
    if len(skel) < 4:
        return -1
    min_skel_pos = bisect.bisect_left(reference_skel_positions, min_pos)
    skel_pos = reference_skel.find(skel, min_skel_pos)
    if skel_pos < 0 or skel_pos >= len(reference_skel_positions):
        return -1
    return reference_skel_positions[skel_pos]


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
    reference_skel, reference_skel_positions = reference_skeleton_with_positions(reference_text)
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
        target_text = paragraph_target_text(paragraph, fallback=source_text)
        paragraph_counts = {"zh": {}, "ja": {}, "both": {}}

        def add_paragraph_counts(lang: str, counts: dict[str, int]) -> None:
            for role, count in counts.items():
                paragraph_counts[lang][role] = paragraph_counts[lang].get(role, 0) + count
                paragraph_counts["both"][role] = paragraph_counts["both"].get(role, 0) + count

        if isinstance(units, list):
            sentence_count = len(SENTENCE_END_RE.findall(target_text))
            if sentence_count >= 4 and len(units) < max(2, math.ceil(sentence_count * 0.45)):
                errors.append(
                    f"{paragraph_id}: too few interlinear units for sentence-level reading "
                    f"({len(units)} units for {sentence_count} sentence endings)"
                )
        if source_requires_ocr_correction(source):
            if "corrected_text" not in paragraph:
                errors.append(f"{paragraph_id}: missing corrected_text for OCR source")
            else:
                errors.extend(ocr_noise_issues(target_text, paragraph_id))
        paragraph_is_note = is_editorial_note(target_text)
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
            add_paragraph_counts("zh", zh_counts)
            add_paragraph_counts("ja", ja_counts)
            add_role_collapse_issues(zh_counts, f"{unit_where}.zh", errors, minimum=34, max_ratio=0.92, min_roles=2)
            add_role_collapse_issues(ja_counts, f"{unit_where}.ja", errors, minimum=34, max_ratio=0.92, min_roles=2)

            zh_text = normalize(token_text(unit.get("zh", [])))
            ja_text = normalize(ja_lines_text(unit.get("ja", [])))
            if len(zh_text) >= 14 and len(ja_text) < max(6, int(len(zh_text) * 0.16)):
                errors.append(f"{unit_where}: Japanese correspondence is too short for the Chinese unit")
            if ja_text:
                duplicate_ja[ja_text] = duplicate_ja.get(ja_text, 0) + 1
            if reference_text and len(ja_text) >= 5 and not paragraph_is_note and not is_editorial_note(zh_text):
                min_match_pos = max(0, last_ref_pos - 8)
                ref_pos = reference_match_pos(
                    reference_text,
                    reference_skel,
                    reference_skel_positions,
                    ja_text,
                    min_pos=min_match_pos,
                )
                if ref_pos < 0 and last_ref_pos >= 0:
                    local_ref_pos = reference_match_pos(
                        reference_text,
                        reference_skel,
                        reference_skel_positions,
                        ja_text,
                        min_pos=0,
                    )
                    if local_ref_pos >= 0 and local_ref_pos + 420 >= last_ref_pos:
                        ref_pos = local_ref_pos
                if ref_pos < 0:
                    errors.append(f"{unit_where}: Japanese comment text is not found in the supplied original reference")
                elif ref_pos + 420 < last_ref_pos:
                    errors.append(f"{unit_where}: Japanese correspondence moves backward in the original reference")
                else:
                    last_ref_pos = max(last_ref_pos, ref_pos)
            for token_index, token in enumerate(ja_tokens):
                reading = str(token.get("r", ""))
                if reading and HAN_RE.search(reading):
                    errors.append(f"{unit_where}.ja token {token_index}: furigana contains kanji")
            for token_index, token in enumerate(zh_tokens):
                reading = str(token.get("r", ""))
                if reading and (HAN_RE.search(reading) or re.search(r"\d", reading)):
                    errors.append(f"{unit_where}.zh token {token_index}: pinyin must use tone marks, not Han or tone digits")

        add_role_collapse_issues(paragraph_counts["zh"], f"{paragraph_id}.zh", errors, minimum=70, max_ratio=0.86, min_roles=3)
        add_role_collapse_issues(paragraph_counts["ja"], f"{paragraph_id}.ja", errors, minimum=70, max_ratio=0.86, min_roles=3)
        add_role_collapse_issues(paragraph_counts["both"], paragraph_id, errors, minimum=120, max_ratio=0.84, min_roles=3)

    for text, count in duplicate_ja.items():
        # Short repeated terms can be legitimate in literary prose. Keep the
        # duplicate-collapse guard for sentence-like repeated comments.
        if count >= 3 and len(text) >= 10:
            errors.append(f"{source['chunk_id']}: repeated identical Japanese comment {count} times: {text[:30]}")

    add_role_collapse_issues(chunk_counts["zh"], f"{source['chunk_id']}.zh", errors, minimum=90, max_ratio=0.82, min_roles=4)
    add_role_collapse_issues(chunk_counts["ja"], f"{source['chunk_id']}.ja", errors, minimum=90, max_ratio=0.82, min_roles=4)
    add_role_collapse_issues(chunk_counts["both"], source["chunk_id"], errors, minimum=160, max_ratio=0.78, min_roles=4)
    return errors


def repair_prompt(source: dict[str, Any], current: dict[str, Any], issues: list[str]) -> str:
    base_prompt = prompt_for_chunk(source, issues)
    shown_issues = "\n".join(f"- {issue}" for issue in issues[:120])
    has_jp_reference = bool(source.get("jp_reference"))
    japanese_source_rule = (
        "- Use the supplied Japanese original reference as the comment text, in the correct original order."
        if has_jp_reference
        else "- No Japanese original reference is supplied for this book. Write faithful, natural Japanese comment text from the Chinese source and keep it sentence-aligned."
    )
    japanese_wrong_source_rule = (
        "Japanese from the wrong chapter, Japanese paraphrase instead of original wording,"
        if has_jp_reference
        else "Japanese that mistranslates, omits, or over-summarizes the Chinese source,"
    )
    return textwrap.dedent(
        f"""
        You are backfixing a merged interlinear chunk that failed broad post-merge review.

        Return the full corrected chunk JSON only. No Markdown fences and no explanation.

        Fix every class of issue, not only grammar:
        - Preserve every original Chinese OCR/source paragraph exactly in paragraph.source_text and keep paragraph ids/order exact.
        - If this source requires OCR cleanup, keep paragraph.corrected_text as the reader-facing corrected Chinese and make the zh tokens reconstruct corrected_text, not the noisy OCR. Correct clear OCR errors, punctuation breaks, accidental ASCII garbage, and page debris without summarizing or inventing story content.
        - For OCR cleanup, actively repair character-level nonsense by context: compare the story title, place, neighboring sentences, and supplied reference window; fix plausible misrecognized Chinese characters, broken names, broken idioms, and sentence fragments. Do not translate or preserve OCR garbage as if it were real prose.
        - When OCR damage is obvious but the exact original is uncertain, choose the most conservative fluent Chinese reading that preserves the event, people, place, and sequence. Mark only paragraph.source_text as the raw evidence; paragraph.corrected_text and zh tokens must be clean reader text.
        - Do not let OCR noise leak into Japanese. Japanese comment text should correspond to corrected_text and the supplied reference/order, not to garbled OCR.
        - Split at sentence or short clause level so the interline is line-based and readable.
        {japanese_source_rule}
        - Ensure every Chinese Han token has pinyin on its own single-character token.
        - Ensure every Japanese kanji has furigana on its own single-kanji token only. If a token mixes kana/punctuation/quotes with a kanji or quoted Chinese glyph, split it, e.g. "おまえはこの「妈」の" must become kana/quote text, one "妈" token with reading, then kana/quote text.
        - Use one English grammar role in "g" for every content token.
        - Avoid color collapse: a whole sentence/chunk must not become one dominant role such as all predicate.
        - Match the major Chinese and Japanese components roughly with the same roles/colors.
        - Treat visible pages that become one color as a serious data bug: it usually means the chunk or paragraph assigns nearly every token the same "g" role.
        - Check for the full set of quality failures a reader would see in the PDF: unresolved OCR errors in Chinese, missing source text, missing Japanese, duplicated Japanese comments, {japanese_wrong_source_rule} oversized units that are not line-based, unbalanced two-line comments, missing pinyin/furigana, furigana on kana or multi-kanji tokens, pinyin on multi-character Chinese tokens, and role/color mismatch between corresponding Chinese and Japanese phrases.
        - Treat numbered Chinese footnotes such as "1.鸟取：..." or "2.江户：..." as editorial notes. They may use concise Japanese note text instead of original-source quotation, but must still be complete, readable, ruby-annotated, and role-colored.
        - Do not merely make validation pass. Make the result read like a clean interlinear book page: corrected continuous Chinese main text, sentence-by-sentence Japanese correspondence, correct ruby/readings, and varied but meaningful grammar colors.

        Review failures to fix:
        {shown_issues}

        Authoritative source/reference prompt for this chunk:
        {base_prompt}

        Defective current merged JSON for salvage only:
        - You may reuse correct readings, token boundaries, and pairings from this JSON.
        - When this JSON conflicts with the authoritative source/reference prompt or the review failures, ignore this JSON.
        - In particular, do not preserve a bad role distribution such as all predicate just because it appears below.
        {json.dumps(current, ensure_ascii=False, indent=2)}
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
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--review-only", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunk_dir = Path(args.chunk_dir)
    work_dir = Path(args.work_dir)
    state_path = Path(args.state_json) if args.state_json else work_dir / "state.json"
    state = load_state(state_path)
    state["prompt_version"] = PROMPT_VERSION
    state.setdefault("chunks", {})
    sources = {
        chunk["chunk_id"]: chunk
        for chunk in expand_adjacent_jp_references(load_chunks(Path(args.chunks_jsonl)))
    }
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
        normalize_source_artifacts(data)
        normalize_ruby_token_shapes(data)
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
                candidate = extract_json(message_path.read_text(encoding="utf-8"))
                normalize_node(candidate)
                normalize_source_artifacts(candidate)
                normalize_ruby_token_shapes(candidate)
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
