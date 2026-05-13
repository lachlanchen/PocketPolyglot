#!/usr/bin/env python3
"""Run one resumable Codex session to align bilingual chunks into JSON."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from codex_chunk_worker import compact, extract_json, flatten_zh, load_chunks, run_codex


def validate_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
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
            if len(unit.get("ja", [])) != 2:
                errors.append(f"{paragraph_id}.units[{unit_index}]: ja must have exactly two lines")
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
                  "zh": [{{"t":"Chinese token","r":"pinyin with tone marks"}}],
                  "ja": [
                    [{{"t":"Japanese original token","r":"furigana for every kanji token, empty for kana/punctuation"}}],
                    [{{"t":"Japanese original token","r":"furigana for every kanji token, empty for kana/punctuation"}}]
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
        - Put pinyin with tone marks in every Chinese token where a reading is meaningful. Punctuation may use an empty reading.
        - For each Chinese unit, find the corresponding Japanese original wording in the provided Japanese reference paragraphs for the same story/chapter. Split that Japanese correspondence into exactly two short visual rows.
        - If a Chinese unit is a translator note or editorial note that is not in the Japanese original, write a concise Japanese note for that unit and keep it visibly note-like.
        - Give furigana for every Japanese kanji or kanji compound. Kana and punctuation should use an empty reading.
        - Keep ids exactly as provided below.
        - Use the provided section/subsection/story ids and titles. Chinese title readings need pinyin; Japanese title readings need furigana.
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
            break
        else:
            raise RuntimeError(f"failed {chunk['chunk_id']} after retries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
