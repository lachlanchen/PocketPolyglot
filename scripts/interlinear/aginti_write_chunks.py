#!/usr/bin/env python3
"""AgInTi DeepSeek writer for sishu-jizhu interlinear zh-ja chunks.

Reads chunks from books/<book>/work/bilingual/chunks/chunks.jsonl, calls the
DeepSeek API (OpenAI-compatible) chunk by chunk, validates the output against
strict interlinear rules, and writes individual chunk JSON files to
data/interlinear/<book>/chunks/.

Resume-safe: skips chunks that already have a valid output file.  Status is
tracked in data/interlinear/<book>/status.json.

Usage:
  python scripts/interlinear/aginti_write_chunks.py [--max-chunks N] [--dry-run]
  python scripts/interlinear/aginti_write_chunks.py --book sishu-jizhu-aginti --max-chunks 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Env -------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".aginti" / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Install openai: pip install openai")

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]

# --- Regex patterns --------------------------------------------------------
HAN_RE = re.compile(r'[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]')
SINGLE_HAN = re.compile(r'^[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]$')
KANA_ONLY_RE = re.compile(
    r'^[\u3040-\u309F\u30A0-\u30FF\u30FC\u3000-\u3002\u300C\u300D'
    r'\uFF01\uFF1F\u3001\u0020\uFF0C\uFF0E\u3005\u3006\n]+$'
)
GRAMMAR_ROLES = frozenset({
    "subject", "predicate", "object", "attributive",
    "adverbial", "complement", "topic", "function",
})
SPACE_RE = re.compile(r'\s+')

# --- Helpers ---------------------------------------------------------------


def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def token_text(tokens: list[dict]) -> str:
    return "".join(str(t.get("t", "")) for t in tokens)


def has_han(text: str) -> bool:
    return bool(HAN_RE.search(text))


def is_single_han(text: str) -> bool:
    return bool(SINGLE_HAN.fullmatch(text))


def is_kana_only(text: str) -> bool:
    """True if text contains only kana/punctuation and no kanji."""
    return bool(KANA_ONLY_RE.fullmatch(text)) and not has_han(text)


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# --- Validation ------------------------------------------------------------


def validate_zh_tokens(tokens: Any, where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(tokens, list):
        errs.append(f"{where}: must be a list")
        return errs
    for i, tok in enumerate(tokens):
        if not isinstance(tok, dict) or "t" not in tok:
            errs.append(f"{where}[{i}]: token must contain 't'")
            continue
        t = str(tok.get("t", ""))
        r = str(tok.get("r", ""))
        role = tok.get("g")
        if role and str(role) not in GRAMMAR_ROLES:
            errs.append(
                f"{where}[{i}]: invalid grammar role {role!r}; "
                f"allowed: {', '.join(sorted(GRAMMAR_ROLES))}"
            )
        if has_han(t) and not is_single_han(t):
            errs.append(f"{where}[{i}]: Chinese Han token must be exactly one character, got {t!r}")
        if is_single_han(t) and not r:
            errs.append(f"{where}[{i}]: Chinese Han token needs pinyin in 'r'")
        if r and not is_single_han(t):
            errs.append(f"{where}[{i}]: pinyin may only be on one-Han-character tokens")
    return errs


def validate_ja_line(tokens: Any, where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(tokens, list):
        errs.append(f"{where}: must be a list")
        return errs
    for i, tok in enumerate(tokens):
        if not isinstance(tok, dict) or "t" not in tok:
            errs.append(f"{where}[{i}]: token must contain 't'")
            continue
        t = str(tok.get("t", ""))
        role = tok.get("g")
        if role and str(role) not in GRAMMAR_ROLES:
            errs.append(
                f"{where}[{i}]: invalid grammar role {role!r}; "
                f"allowed: {', '.join(sorted(GRAMMAR_ROLES))}"
            )
        # Note: we do NOT enforce one-kanji-per-token for Japanese;
        # the model may produce natural compound tokens like 大学 with reading だいがく
    return errs


def validate_unit(unit: dict, where: str) -> list[str]:
    errs: list[str] = []
    if "zh" not in unit or not isinstance(unit["zh"], list):
        errs.append(f"{where}: missing zh token list")
        return errs
    errs += validate_zh_tokens(unit["zh"], f"{where}.zh")

    ja = unit.get("ja")
    if not isinstance(ja, list) or len(ja) != 2:
        errs.append(f"{where}: ja must be exactly two line arrays")
    else:
        for li in range(2):
            line = ja[li]
            if not isinstance(line, list):
                errs.append(f"{where}.ja[{li}]: must be a token list")
                continue
            errs += validate_ja_line(line, f"{where}.ja[{li}]")
            line_text = token_text(line)
            if not normalize(line_text):
                errs.append(f"{where}.ja[{li}]: empty Japanese line")
            if has_han(line_text) and is_kana_only(line_text) and len(normalize(line_text)) > 3:
                errs.append(
                    f"{where}.ja[{li}]: Japanese line is kana-only despite having "
                    f"kanji content; use normal mixed kanji/kana"
                )

    # Reconstruct source text
    zh_text = token_text(unit["zh"])
    source = unit.get("source_text", "")
    if source and normalize(zh_text) != normalize(source):
        errs.append(
            f"{where}: zh tokens do not reconstruct source text; "
            f"got {normalize(zh_text)[:60]!r}, expected {normalize(source)[:60]!r}"
        )
    return errs


def validate_chunk_output(data: dict) -> list[str]:
    errs: list[str] = []
    if data.get("mode") != "zh_main_ja_comment":
        errs.append("mode must be zh_main_ja_comment")
    units = data.get("units")
    if not isinstance(units, list) or not units:
        errs.append("units must be a nonempty list")
        return errs
    for ui, unit in enumerate(units):
        errs += validate_unit(unit, f"units[{ui}]")
    return errs


# --- Prompt building -------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert in Classical Chinese philology and Japanese scholarly commentary.
Your task is to produce a strict JSON interlinear annotation for a paragraph
from Zhu Xi's 四書章句集註 (Collected Commentaries on the Four Books).

The JSON format:

{
  "mode": "zh_main_ja_comment",
  "chunk_id": "<chunk_id>",
  "units": [
    {
      "source_text": "<the exact Chinese source for this unit>",
      "zh": [{"t": "<char>", "r": "<pinyin>"}, ...],
      "ja": [
        [{"t": "<token>", "r": "<furigana>"}, ...],
        [{"t": "<token>", "r": "<furigana>"}, ...]
      ]
    }
  ]
}

CRITICAL RULES - follow these exactly:

1. **Unit boundaries**: Split the paragraph into semantic units (clauses, sentences).
   Each unit's source_text and zh tokens must reconstruct the EXACT original Chinese text.
   No characters may be added, dropped, or changed.

2. **Chinese tokenization (zh)**:
   - Each Chinese character (Hanzi / 漢字) MUST be its own token with `t` and `r` (pinyin).
   - Punctuation (，。！？；：「」『』〈〉《》) are separate tokens with `t` set to the
     punctuation and `r` set to "".
   - Whitespace between Hanzi is forbidden inside tokens.
   - Non-Hanzi elements like 「, 」, 〈, 〉 are separate tokens.
   - Pinyin must be lowercase with tone numbers (1-4) or tone marks.

3. **Japanese commentary (ja)**:
   - ja is an array of exactly TWO lines (token arrays).
   - **Line 0 (reading/gloss)**: A Japanese gloss reflecting the Chinese meaning in
     natural Japanese. Each kanji character MUST be its own token with furigana in `r`.
     Kana tokens have `r` set to "".
   - **Line 1 (explanatory comment)**: A scholarly Japanese commentary on the unit's
     meaning, in Zhu Xi's interpretive tradition. Each kanji is its own token with
     furigana. Use NATURAL MIXED KANJI/KANA - do NOT write kana-only sentences.
     Use proper Japanese scholarly vocabulary with 漢字.

4. **Grammar roles (g)**: Only on zh tokens. Use one of:
   subject, predicate, object, attributive, adverbial, complement, topic, function.
   Not every token needs a role. Only assign when clear.

5. **Kana-only prohibition**: Neither ja line may be entirely kana when it contains
   semantic content. Use kanji for content words. Only particles, auxiliaries,
   and inflections may be kana-only.

6. **Furigana**: Every single-kanji token in ja lines needs `r` (furigana in hiragana).
   Kana tokens have `r: ""`.

7. **No placeholders**: Every ja line must be real Japanese content.
   Do not output "注。" or "。" as the only content.

Return ONLY valid JSON, no other text. Do not wrap in markdown code fences."""


def build_user_prompt(chunk: dict, context_chunks: list[dict]) -> str:
    parts: list[str] = []
    parts.append(f"Book: 四書章句集註 (sì shū zhāng jù jí zhù)")
    parts.append(f"Section: {chunk.get('subsection_title', '')}")
    parts.append(f"Chunk ID: {chunk.get('chunk_id', '')}")
    parts.append("")

    if context_chunks:
        parts.append("--- Context (surrounding paragraphs in this chapter) ---")
        for ctx in context_chunks:
            ctx_text = ctx["paragraphs"][0]["text"]
            parts.append(ctx_text)
        parts.append("--- End Context ---")
        parts.append("")

    para = chunk["paragraphs"][0]
    parts.append(f"--- Paragraph to annotate ---")
    parts.append(para["text"])
    parts.append("--- End Paragraph ---")
    parts.append("")
    parts.append("Produce the JSON annotation for this paragraph.")
    parts.append("Use semantic unit boundaries (clauses/sentences) for splitting.")
    return "\n".join(parts)


# --- API call --------------------------------------------------------------


def call_deepseek(client: OpenAI, model: str, system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=16384,
    )
    return response.choices[0].message.content or ""


# --- Status management -----------------------------------------------------


def load_status(status_path: Path) -> dict:
    if status_path.exists():
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "book": "",
        "total_chunks": 0,
        "raw": 0,
        "reviewed": 0,
        "failed": 0,
        "pending": 0,
        "first_missing": None,
        "last_updated": None,
    }


def save_status(status_path: Path, status: dict) -> None:
    status["last_updated"] = datetime.now(timezone.utc).isoformat()
    status["pending"] = status["total_chunks"] - status["raw"] - status["failed"]
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def repair_json(text: str) -> str | None:
    """Attempt to repair common DeepSeek JSON output issues."""
    if not text:
        return None
    # Remove markdown fences if present
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    # Fix common issues: missing comma before newline+quote
    # e.g. \n    {\"t\" -> \n    ,{\"t\"
    t = re.sub(r'\n(\s*)(?=["{\[])', r',\n\1', t)
    # Remove trailing commas before closing bracket/brace
    t = re.sub(r',(\s*[}\]])', r'\1', t)
    # Fix doubled commas
    t = re.sub(r',\s*,', ',', t)
    if t == text.strip():
        return None  # no changes made
    return t


# --- Main loop -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", default="sishu-jizhu-aginti")
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="Process at most N chunks (0 = unlimited)")
    parser.add_argument("--start-chunk", type=int, default=1,
                        help="1-based chunk index to start from")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without calling API")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay in seconds between API calls")
    args = parser.parse_args()

    book_id = args.book
    chunks_jsonl = ROOT / "books" / book_id / "work" / "bilingual" / "chunks" / "chunks.jsonl"
    chunk_out_dir = ROOT / "data" / "interlinear" / book_id / "chunks"
    status_path = ROOT / "data" / "interlinear" / book_id / "status.json"
    log_path = ROOT / "data" / "interlinear" / book_id / "writer.log"

    if not chunks_jsonl.exists():
        print(f"ERROR: chunks.jsonl not found at {chunks_jsonl}", file=sys.stderr)
        return 1

    # API setup
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key and not args.dry_run:
        print("ERROR: DEEPSEEK_API_KEY not set in environment", file=sys.stderr)
        print("Set it in .aginti/.env or export DEEPSEEK_API_KEY", file=sys.stderr)
        return 1

    model = os.environ.get("AGINTI_DEEPSEEK_MODEL", "deepseek-chat")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1") if not args.dry_run else None  # type: ignore[arg-type]

    # Load chunks
    chunks: list[dict] = []
    with open(chunks_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    total = len(chunks)
    print(f"Loaded {total} chunks from {chunks_jsonl}")

    # Group by subsection for context windows
    subsection_chunks: dict[str, list[dict]] = {}
    for c in chunks:
        sub = c.get("subsection_id", "__unknown__")
        subsection_chunks.setdefault(sub, []).append(c)

    # Status
    status = load_status(status_path)
    status["book"] = book_id
    status["total_chunks"] = total
    chunk_out_dir.mkdir(parents=True, exist_ok=True)

    # Log setup
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")

    def log(msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts} {msg}"
        print(line)
        log_fh.write(line + "\n")
        log_fh.flush()

    processed = 0
    start_idx = max(0, args.start_chunk - 1)

    for idx in range(start_idx, total):
        if args.max_chunks and processed >= args.max_chunks:
            log(f"Reached --max-chunks={args.max_chunks}, stopping")
            break

        chunk = chunks[idx]
        chunk_id = chunk["chunk_id"]
        out_path = chunk_out_dir / f"{chunk_id}.json"

        # Resume check
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                errs = validate_chunk_output(existing)
                if not errs:
                    processed += 1
                    continue
                else:
                    log(f"  {chunk_id}: existing file has {len(errs)} validation errors, redoing")
            except (json.JSONDecodeError, OSError) as e:
                log(f"  {chunk_id}: existing file corrupt ({e}), redoing")

        # Build context
        sub = chunk.get("subsection_id", "__unknown__")
        sub_list = subsection_chunks.get(sub, [])
        sub_idx = next((i for i, c in enumerate(sub_list) if c["chunk_id"] == chunk_id), -1)
        context: list[dict] = []
        if sub_idx >= 0:
            ctx_start = max(0, sub_idx - 2)
            ctx_end = min(len(sub_list), sub_idx + 3)
            for ci in range(ctx_start, ctx_end):
                if ci != sub_idx:
                    context.append(sub_list[ci])

        para_text = chunk["paragraphs"][0]["text"]

        log(f"[{idx+1}/{total}] {chunk_id}: {para_text[:50]}...")

        if args.dry_run:
            log(f"  DRY RUN - would call DeepSeek API")
            processed += 1
            continue

        # Build prompt and call API
        user_prompt = build_user_prompt(chunk, context)
        try:
            raw_response = call_deepseek(client, model, SYSTEM_PROMPT, user_prompt)  # type: ignore[arg-type]
        except Exception as e:
            log(f"  API ERROR: {e}")
            status["failed"] = status.get("failed", 0) + 1
            save_status(status_path, status)
            time.sleep(args.delay * 4)
            continue

        # Parse JSON
        # Strip possible markdown fences
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Attempt repair: common DeepSeek JSON issues
            repaired = repair_json(cleaned)
            if repaired:
                try:
                    data = json.loads(repaired)
                    log(f"  JSON REPAIRED successfully")
                except json.JSONDecodeError as e2:
                    log(f"  JSON PARSE ERROR (repair failed): {e2}")
                    log(f"  Raw response (first 200 chars): {raw_response[:200]}")
                    status["failed"] = status.get("failed", 0) + 1
                    save_status(status_path, status)
                    time.sleep(args.delay * 2)
                    continue
            else:
                log(f"  JSON PARSE ERROR: {e}")
                log(f"  Raw response (first 200 chars): {raw_response[:200]}")
                status["failed"] = status.get("failed", 0) + 1
                save_status(status_path, status)
                time.sleep(args.delay * 2)
                continue

        # Validate
        data["chunk_id"] = chunk_id
        errs = validate_chunk_output(data)
        if errs:
            log(f"  VALIDATION FAILED ({len(errs)} errors):")
            for err in errs[:10]:
                log(f"    - {err}")
            status["failed"] = status.get("failed", 0) + 1
            # Still save the raw output for debugging
            debug_path = chunk_out_dir / f"{chunk_id}.raw.json"
            debug_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            save_status(status_path, status)
            time.sleep(args.delay * 2)
            continue

        # Save
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status["raw"] = status.get("raw", 0) + 1
        status["first_missing"] = None  # will be recomputed
        processed += 1
        log(f"  OK -> {out_path}")
        save_status(status_path, status)

        time.sleep(args.delay)

    # Final status update
    # Find first missing
    first = None
    for idx in range(total):
        cid = chunks[idx]["chunk_id"]
        if not (chunk_out_dir / f"{cid}.json").exists():
            first = idx + 1
            break
    status["first_missing"] = first
    save_status(status_path, status)

    log(f"Done. raw={status['raw']} reviewed={status.get('reviewed',0)} failed={status.get('failed',0)} pending={status['pending']} first_missing={first}")
    log_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
