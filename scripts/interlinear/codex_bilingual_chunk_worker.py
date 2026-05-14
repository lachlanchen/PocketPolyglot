#!/usr/bin/env python3
"""Run one resumable Codex session to align bilingual chunks into JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from codex_chunk_worker import compact, extract_json, flatten_zh, load_chunks, run_codex
from validate_interlinear_json import ja_lines_text, normalize, validate_ja_tokens, validate_named_tokens, validate_zh_tokens

PLACEHOLDER_JA = {"注", "注。", "。"}


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
    chunk_zh_texts: list[str] = []
    chunk_ja_texts: list[str] = []
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
            chunk_zh_texts.append("".join(str(token.get("t", "")) for token in unit.get("zh", [])))
            ja = unit.get("ja", [])
            if len(ja) != 2:
                errors.append(f"{paragraph_id}.units[{unit_index}]: ja must have exactly two lines")
            else:
                validate_ja_tokens(ja[0], f"{paragraph_id}.units[{unit_index}].ja[0]", errors)
                validate_ja_tokens(ja[1], f"{paragraph_id}.units[{unit_index}].ja[1]", errors)
                ja_text = normalize(ja_lines_text(ja))
                chunk_ja_texts.append(ja_text)
                if not ja_text:
                    errors.append(f"{paragraph_id}.units[{unit_index}]: Japanese comment is empty")
                if ja_text in PLACEHOLDER_JA:
                    errors.append(f"{paragraph_id}.units[{unit_index}]: Japanese comment is a placeholder, not aligned text")
    chunk_zh_len = len(normalize("".join(chunk_zh_texts)))
    chunk_ja_len = len(normalize("".join(chunk_ja_texts)))
    if chunk_zh_len >= 120 and chunk_ja_len / chunk_zh_len < 0.18:
        errors.append(f"{source['chunk_id']}: Japanese coverage is too low ({chunk_ja_len}/{chunk_zh_len} chars)")
    return errors


def prompt_for_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious output failed validation. Fix these issues exactly:\n" + "\n".join(f"- {error}" for error in previous_errors)

    metadata = {
        key: chunk[key]
        for key in (
            "chunk_id",
            "section_id",
            "section_title",
            "subsection_id",
            "subsection_title",
            "story_id",
            "story_title",
            "paired_story_key",
        )
    }

    return textwrap.dedent(
        f"""
        You are preparing one chunk of a Chinese-main / Japanese-comment pocket interlinear edition of Natsume Soseki's Kokoro.

        Use the Chinese translation as the continuous main text. Use the supplied Japanese original reference for the Japanese comment lines. Do not make a free Japanese translation when the original Japanese reference contains the corresponding passage.

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
        - Preserve every Chinese source paragraph. Do not omit, summarize, reorder, or rewrite the Chinese.
        - For each paragraph, joining all zh token "t" values across all units must reconstruct the paragraph text exactly, apart from whitespace.
        - Split the Chinese into natural reading units, usually sentence by sentence. Keep each unit readable as continuous Chinese prose.
        - Chinese tokenization is strict: every Chinese Han character must be its own token with pinyin, e.g. "先生" becomes [{{"t":"先","r":"xiān"}},{{"t":"生","r":"sheng"}}]. Never attach pinyin to a multi-character Chinese word or phrase. Punctuation, Arabic numerals, Latin text, and spaces use empty reading.
        - For each Chinese unit, find the corresponding Japanese original wording in the provided Japanese reference paragraphs for the same story/chapter. Split that Japanese correspondence into exactly two short visual rows.
        - The Japanese comment for every unit must contain real aligned Japanese. Never leave Japanese rows empty. Never use placeholders such as "注", "注。", "日本語", or a generic marker.
        - Across the chunk, Japanese text must have reasonable coverage of the Chinese units. If the Japanese reference does not include enough source text for this chunk, say so by failing the task rather than fabricating placeholders.
        - If a Chinese unit is a translator note or editorial note that is not in the Japanese original, write a concise Japanese note for that unit and keep it visibly note-like.
        - Japanese tokenization is strict: every kanji character must be its own token with furigana, and furigana may appear only on one-kanji tokens. Kana, okurigana, punctuation, spaces, and Latin text must have empty reading. Example: "先生と私" becomes [{{"t":"先","r":"せん"}},{{"t":"生","r":"せい"}},{{"t":"と","r":""}},{{"t":"私","r":"わたし"}}]. Example: "書くだけ" becomes [{{"t":"書","r":"か"}},{{"t":"くだけ","r":""}}].
        - Keep ids exactly as provided below.
        - Use the provided section/subsection/story ids and titles. Apply the same strict per-Han-character/per-kanji-character ruby rules to all titles and place fields.
        {error_block}

        Chunk metadata:
        {json.dumps(metadata, ensure_ascii=False, indent=2)}

        Chinese source paragraphs:
        {json.dumps(chunk['paragraphs'], ensure_ascii=False, indent=2)}

        Japanese original reference paragraphs for the same story/chapter:
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
    parser.add_argument("--resume-last", action="store_true", help="resume the newest Codex session for the first missing chunk")
    parser.add_argument("--after-chunk-command", default="", help="shell command to run after each newly written valid chunk")
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
            run_codex(prompt, message_path, log_path, first=first_codex_call, model=args.model, reasoning=args.reasoning, cwd=cwd)
            first_codex_call = False

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
