#!/usr/bin/env python3
"""Run isolated Codex calls to align bilingual chunks into JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from codex_chunk_worker import compact, extract_json, flatten_zh, load_chunks, run_codex
from normalize_grammar_roles import (
    cleanup_components,
    normalize_node,
    normalize_ruby_token_shapes,
    normalize_source_artifacts,
    strip_reader_note_artifacts,
)
from reference_windows import expand_adjacent_jp_references
from validate_interlinear_json import ja_lines_text, normalize, validate_ja_tokens, validate_named_tokens, validate_zh_tokens

PLACEHOLDER_JA = {"注", "注。", "。"}
SENTENCE_END_RE = re.compile(r"[。！？!?]")
CONTENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffぁ-ゟ゠-ヿA-Za-z0-9]")
GRAMMAR_ROLES = {
    "subject",
    "predicate",
    "object",
    "attributive",
    "adverbial",
    "complement",
    "topic",
    "function",
}
ZH_UNIT_HARD_MAX = 128
ZH_UNIT_MULTI_SENTENCE_MAX = 82
JA_COMMENT_LINE_MAX = 54


def zh_unit_text(unit: dict[str, Any]) -> str:
    return "".join(str(token.get("t", "")) for token in unit.get("zh", []))


def token_text(tokens: list[dict[str, Any]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def source_requires_ocr_correction(source: dict[str, Any]) -> bool:
    return bool(source.get("requires_ocr_correction"))


def paragraph_target_text(paragraph: dict[str, Any], *, fallback: str = "") -> str:
    corrected = str(paragraph.get("corrected_text", "")).strip()
    if corrected:
        return corrected
    return str(fallback if fallback else paragraph.get("source_text", ""))


def unit_target_text(unit: dict[str, Any]) -> str:
    corrected = str(unit.get("corrected_text", "")).strip()
    if corrected:
        return corrected
    return str(unit.get("source_text", ""))


def reader_compact(text: str) -> str:
    return compact(strip_reader_note_artifacts(text))


def needs_grammar_role(text: str) -> bool:
    return bool(CONTENT_RE.search(text))


def validate_grammar_tokens(tokens: Any, where: str, errors: list[str]) -> None:
    if not isinstance(tokens, list):
        return
    for token_index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        role = str(token.get("g", "")).strip().lower()
        if needs_grammar_role(text) and not role:
            errors.append(f"{where}[{token_index}]: content token needs grammar role g")
        if role and role not in GRAMMAR_ROLES:
            allowed = ", ".join(sorted(GRAMMAR_ROLES))
            errors.append(f"{where}[{token_index}]: unsupported grammar role {role!r}; use one of {allowed}")


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
    require_ocr_correction = source_requires_ocr_correction(source)
    chunk_zh_texts: list[str] = []
    chunk_ja_texts: list[str] = []
    for paragraph in paragraphs:
        paragraph_id = paragraph.get("id")
        if paragraph_id not in source_by_id:
            continue
        source_text = source_by_id[paragraph_id]
        if reader_compact(paragraph.get("source_text", "")) != reader_compact(source_text):
            errors.append(f"{paragraph_id}: paragraph source_text changed")
        if require_ocr_correction and "corrected_text" not in paragraph:
            errors.append(f"{paragraph_id}: corrected_text is required for OCR-reviewed source")
        target_text = paragraph_target_text(paragraph, fallback=source_text)
        if reader_compact(flatten_zh(paragraph)) != reader_compact(target_text):
            errors.append(f"{paragraph_id}: zh tokens do not reconstruct corrected paragraph")
        if not paragraph.get("units"):
            errors.append(f"{paragraph_id}: missing units")
        for unit_index, unit in enumerate(paragraph.get("units", [])):
            unit_where = f"{paragraph_id}.units[{unit_index}]"
            zh_where = f"{unit_where}.zh"
            validate_zh_tokens(unit.get("zh", []), zh_where, errors)
            validate_grammar_tokens(unit.get("zh", []), zh_where, errors)
            zh_text = zh_unit_text(unit)
            unit_target = unit_target_text(unit)
            if unit_target and reader_compact(zh_text) != reader_compact(unit_target):
                errors.append(f"{unit_where}: zh tokens do not reconstruct unit source_text/corrected_text")
            chunk_zh_texts.append(zh_text)
            sentence_end_count = len(SENTENCE_END_RE.findall(zh_text))
            if len(zh_text) > ZH_UNIT_HARD_MAX or (
                len(zh_text) > ZH_UNIT_MULTI_SENTENCE_MAX and sentence_end_count >= 2
            ):
                errors.append(
                    f"{unit_where}: Chinese unit is too broad; split sentence-by-sentence or clause-by-clause"
                )
            ja = unit.get("ja", [])
            if len(ja) != 2:
                errors.append(f"{unit_where}: ja must have exactly two lines")
            else:
                for line_index, line in enumerate(ja):
                    line_where = f"{unit_where}.ja[{line_index}]"
                    validate_ja_tokens(line, line_where, errors)
                    validate_grammar_tokens(line, line_where, errors)
                    if not isinstance(line, list):
                        continue
                    line_text = normalize(token_text(line))
                    if len(line_text) > JA_COMMENT_LINE_MAX:
                        errors.append(
                            f"{line_where}: Japanese comment row is too long ({len(line_text)} chars); split/rebalance the unit"
                        )
                ja_text = normalize(ja_lines_text(ja))
                chunk_ja_texts.append(ja_text)
                if not ja_text:
                    errors.append(f"{unit_where}: Japanese comment is empty")
                if ja_text in PLACEHOLDER_JA:
                    errors.append(f"{unit_where}: Japanese comment is a placeholder, not aligned text")
    chunk_zh_len = len(normalize("".join(chunk_zh_texts)))
    chunk_ja_len = len(normalize("".join(chunk_ja_texts)))
    if chunk_zh_len >= 120 and chunk_ja_len / chunk_zh_len < 0.18:
        errors.append(f"{source['chunk_id']}: Japanese coverage is too low ({chunk_ja_len}/{chunk_zh_len} chars)")
    return errors


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        shown_errors = previous_errors[:80]
        error_block = "\nPrevious output failed validation. Fix these issues exactly:\n" + "\n".join(
            f"- {error}" for error in shown_errors
        )
        if len(previous_errors) > len(shown_errors):
            error_block += f"\n- ... {len(previous_errors) - len(shown_errors)} additional validation errors omitted"

    metadata_keys = (
        "chunk_id",
        "section_id",
        "section_title",
        "subsection_id",
        "subsection_title",
        "story_id",
        "story_title",
        "paired_story_key",
        "book_title_zh",
        "book_title_zh_reading",
        "book_title_ja",
        "book_title_ja_reading",
        "author",
        "book_description",
    )
    metadata = {key: chunk[key] for key in metadata_keys if key in chunk}
    work_description = chunk.get("book_description") or "Natsume Soseki's Kokoro"
    has_jp_reference = bool(chunk.get("jp_reference"))
    source_instruction = (
        "Use the Chinese translation as the continuous main text. Use the supplied Japanese original reference "
        "for the Japanese comment lines. The reference is intentionally a rough chapter-level context, not a "
        "precomputed sentence match; locate the corresponding original Japanese wording yourself. Do not make "
        "a free Japanese translation when the original Japanese reference contains the corresponding passage."
        if has_jp_reference
        else "Use the Chinese source as the continuous main text. No Japanese original reference is supplied "
        "for this book; create faithful, natural Japanese comment lines directly from each Chinese unit. "
        "Keep the Japanese close enough that a reader can compare the two languages sentence by sentence."
    )
    ja_source_requirement = (
        "- For each Chinese unit, find the corresponding Japanese original wording in the provided Japanese reference paragraphs for the same rough chapter/reference scope. Split that Japanese correspondence into exactly two short visual rows.\n"
        "- Some Japanese references may come from vertically typeset ruby PDFs where a reading gloss was extracted inline before its kanji, for example \"はかま袴\", \"い謂わば\", or \"とういす籐椅子\". Treat those as ruby extraction artifacts: output the real Japanese wording with one-kanji tokens and furigana, not duplicated kana plus kanji.\n"
        "- Across the chunk, Japanese text must have reasonable coverage of the Chinese units. If the Japanese reference does not include enough source text for this chunk, say so by failing the task rather than fabricating placeholders."
        if has_jp_reference
        else "- For each Chinese unit, write a faithful natural Japanese translation/comment. Split that Japanese correspondence into exactly two short visual rows.\n"
        "- Since this is a Chinese-source-only book, do not reject the task for missing Japanese original reference and do not fabricate source quotations. The Japanese must be your own accurate sentence-level rendering of the Chinese."
    )
    reference_payload_label = (
        "Japanese original reference paragraphs for the same rough chapter/reference scope:"
        if has_jp_reference
        else "Japanese original reference paragraphs: [] (none supplied; translate from the Chinese source)"
    )
    ocr_instruction = ""
    paragraph_corrected_shape = ""
    if source_requires_ocr_correction(chunk):
        paragraph_corrected_shape = '\n              "corrected_text": "clean corrected Chinese paragraph; same as source_text if no OCR correction is needed",'
        ocr_instruction = """
        - This Chinese source comes from OCR and may contain recognition errors. Keep "source_text" as the exact OCR paragraph, but use "corrected_text" and the zh tokens as the clean reader-facing Chinese text.
        - Correct only clear OCR/normalization errors: wrong but visually similar characters, broken punctuation, accidental Latin/ASCII garbage, repeated page debris, and line-join artifacts. Do not summarize, modernize dialect, invent missing story content, or silently delete meaningful words.
        - If the OCR is uncertain, make the smallest plausible correction that preserves the story. If no correction is needed, set corrected_text equal to source_text.
        - For each paragraph, joining all zh token "t" values across all units must reconstruct corrected_text exactly, apart from whitespace. The paragraph source_text must still reproduce the provided OCR source exactly.
        """

    return textwrap.dedent(
        f"""
        You are preparing one chunk of a Chinese-main / Japanese-comment pocket interlinear edition of {work_description}.

        {source_instruction}

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
              "source_text": "exact source paragraph",{paragraph_corrected_shape}
              "units": [
                {{
                  "source_text": "exact reader-facing Chinese sentence or sentence group from corrected_text/source_text",
                  "zh": [{{"t":"one Chinese Han character","r":"that character's pinyin with tone mark","g":"English component role"}}],
                  "ja": [
                    [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji, empty otherwise","g":"English component role"}}],
                    [{{"t":"one Japanese kanji OR kana/punctuation run","r":"furigana only for one kanji, empty otherwise","g":"English component role"}}]
                  ]
                }}
              ]
            }}
          ]
        }}

        Hard requirements:
        - Preserve every Chinese source paragraph in source_text. Do not omit, summarize, or reorder paragraphs.
        {ocr_instruction}
        - Remove EPUB/HTML footnote reference debris from reader-facing fields and tokens. Examples: [\\[12\\]](#part1338.html#m12), [12](#note), [1], ［2］. Do not turn these into Japanese 注 lines.
        - For non-OCR-cleanup chunks, joining all zh token "t" values across all units must reconstruct the paragraph source text exactly, apart from whitespace.
        - Split the Chinese into natural reading units, usually sentence by sentence. Keep each unit readable as continuous Chinese prose.
        - Line-based pairing requirement: one unit should be one Chinese sentence, or one tightly bound sentence fragment when the sentence/comment is very long. Do not put a whole paragraph into one unit. If a paragraph has multiple sentence-ending punctuation marks, make multiple units in the same order.
        - Target each Chinese unit at roughly 18-65 Chinese characters. A unit longer than 90 characters should normally be split by clause. A unit longer than 128 characters will be rejected.
        - Chinese tokenization is strict: every Chinese Han character must be its own token with pinyin, e.g. "先生" becomes [{{"t":"先","r":"xiān"}},{{"t":"生","r":"sheng"}}]. Never attach pinyin to a multi-character Chinese word or phrase. Punctuation, Arabic numerals, Latin text, and spaces use empty reading.
        {ja_source_requirement}
        - Keep each Japanese comment row short: no row should exceed 54 visible Japanese characters. If a row would be longer, split the Chinese unit into smaller sentence/clause units or rebalance the two rows.
        - The Japanese comment for every unit must contain real aligned Japanese. Never leave Japanese rows empty. Never use placeholders such as "注", "注。", "日本語", or a generic marker.
        - If a Chinese unit is a translator note or editorial note that is not in the Japanese original, write a concise Japanese note for that unit and keep it visibly note-like.
        - Japanese tokenization is strict: every kanji character must be its own token with furigana, and furigana may appear only on one-kanji tokens. Kana, okurigana, punctuation, spaces, and Latin text must have empty reading. Example: "先生と私" becomes [{{"t":"先","r":"せん"}},{{"t":"生","r":"せい"}},{{"t":"と","r":""}},{{"t":"私","r":"わたし"}}]. Example: "書くだけ" becomes [{{"t":"書","r":"か"}},{{"t":"くだけ","r":""}}].
        - Do not use automatic pinyin, furigana, morphological, or grammar tagging libraries/tools such as pypinyin, kakasi, MeCab, Sudachi, fugashi, or similar packages. The readings and grammar roles must be supplied by your own linguistic reasoning.
        - Unified component analysis is mandatory. Every Chinese and Japanese content token must include "g" with exactly one English role: subject, predicate, object, attributive, adverbial, complement, topic, or function.
        - Use "g" as the single visual grammar-component role across both languages. Do not add a second color role, alias role, component id, or separate syntax field.
        - Assign the same "g" to corresponding major components when reasonable, even when Chinese and Japanese express that component with different local syntax. A Japanese は/が phrase that functions as the paired sentence subject should normally be subject; reserve topic for a real discourse topic that is not simply the sentence subject. A Japanese topic/case/list particle attached to a subject/object/adverbial phrase inherits that phrase's role instead of becoming function. List markers such as だの, など, や, and と inherit the listed phrase role; if the listed events/things correspond to Chinese objects, use object for the whole listed phrase.
        - For Chinese multi-character words, repeat the same "g" on each one-character token. For Japanese kanji plus okurigana or attached particles inside the same major component, use the same "g" so the PDF colors that whole component consistently.
        - Do not use Chinese role aliases such as zhu, wei, bin, ding, zhuang, or bu. Do not invent labels such as noun, adjective, modifier, subject-object, punct, or unknown.
        - Keep ids exactly as provided below.
        - Use the provided section/subsection/story ids and titles. Apply the same strict per-Han-character/per-kanji-character ruby rules to all titles and place fields.
        {error_block}

        Chunk metadata:
        {json.dumps(metadata, ensure_ascii=False, indent=2)}

        Chinese source paragraphs:
        {json.dumps(chunk['paragraphs'], ensure_ascii=False, indent=2)}

        {reference_payload_label}
        {json.dumps(chunk.get('jp_reference', []), ensure_ascii=False, indent=2)}
        """
    ).strip()


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
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument(
        "--resume-last",
        action="store_true",
        help="deprecated: kept for old scripts; bilingual chunk calls intentionally start fresh",
    )
    parser.add_argument("--after-chunk-command", default="", help="shell command to run after each newly written valid chunk")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = expand_adjacent_jp_references(load_chunks(Path(args.chunks_jsonl)))
    output_dir = Path(args.output_dir)
    work_dir = Path(args.work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    selected = chunks[args.start_index - 1 :]
    if args.max_chunks:
        selected = selected[: args.max_chunks]

    for selected_index, chunk in enumerate(selected, start=args.start_index):
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

            print(f"codex bilingual {chunk['chunk_id']} attempt {attempt}")
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

            normalize_node(result)
            normalize_source_artifacts(result)
            normalize_ruby_token_shapes(result)
            cleanup_components(result)
            errors = validate_chunk(chunk, result)
            if errors:
                print(f"validation failed for {chunk['chunk_id']}: {'; '.join(errors)}", file=sys.stderr)
                reject_path = work_dir / "rejected" / f"{chunk['chunk_id']}.attempt{attempt}.json"
                reject_path.parent.mkdir(parents=True, exist_ok=True)
                reject_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                continue

            final_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {final_path}")
            if args.after_chunk_command:
                env = os.environ.copy()
                env.update(
                    {
                        "ZHJPBOOK_CHUNK_ID": chunk["chunk_id"],
                        "ZHJPBOOK_CHUNK_INDEX": str(selected_index),
                        "ZHJPBOOK_CHUNK_PATH": str(final_path),
                    }
                )
                subprocess.run(args.after_chunk_command, shell=True, check=True, cwd=cwd, env=env)
            break
        else:
            raise RuntimeError(f"failed {chunk['chunk_id']} after retries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
