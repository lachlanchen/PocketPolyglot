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
import shutil
import subprocess
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

SISHU_TITLE_PINYIN = {
    "一": "yi1", "七": "qi1", "三": "san1", "中": "zhong1", "九": "jiu3",
    "二": "er4", "五": "wu3", "八": "ba1", "六": "liu4", "十": "shi2",
    "卷": "juan4", "句": "ju4", "四": "si4", "大": "da4", "子": "zi3",
    "孟": "meng4", "學": "xue2", "定": "ding4", "序": "xu4", "庸": "yong1",
    "書": "shu1", "本": "ben3", "法": "fa3", "注": "zhu4", "章": "zhang1",
    "考": "kao3", "註": "zhu4", "語": "yu3", "說": "shuo1", "論": "lun2",
    "讀": "du2", "辨": "bian4", "附": "fu4", "集": "ji2",
}

SISHU_TITLE_FURIGANA = {
    "一": "いち", "七": "しち", "三": "さん", "中": "ちゅう", "九": "きゅう",
    "二": "に", "五": "ご", "八": "はち", "六": "ろく", "十": "じゅう",
    "卷": "かん", "句": "く", "四": "し", "大": "だい", "子": "し",
    "孟": "もう", "學": "がく", "定": "てい", "序": "じょ", "庸": "よう",
    "書": "しょ", "本": "ほん", "法": "ほう", "注": "ちゅう", "章": "しょう",
    "考": "こう", "註": "ちゅう", "語": "ご", "說": "せつ", "論": "ろん",
    "讀": "どく", "辨": "べん", "附": "ふ", "集": "しゅう",
}

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


def title_tokens(text: str, readings: dict[str, str]) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    for char in text:
        if is_single_han(char):
            tokens.append({"t": char, "r": readings.get(char, "")})
        else:
            tokens.append({"t": char, "r": ""})
    return tokens


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
        r = str(tok.get("r", ""))
        role = tok.get("g")
        if role and str(role) not in GRAMMAR_ROLES:
            errs.append(
                f"{where}[{i}]: invalid grammar role {role!r}; "
                f"allowed: {', '.join(sorted(GRAMMAR_ROLES))}"
            )
        if has_han(t) and not is_single_han(t):
            errs.append(f"{where}[{i}]: Japanese kanji token must be exactly one kanji, got {t!r}")
        if is_single_han(t) and not r:
            errs.append(f"{where}[{i}]: Japanese kanji token needs furigana in 'r'")
        if r and not is_single_han(t):
            errs.append(f"{where}[{i}]: furigana may only be on one-kanji tokens")
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


def source_paragraph_text(chunk: dict[str, Any]) -> str:
    return "".join(str(paragraph.get("text", "")) for paragraph in chunk.get("paragraphs", []))


def wrap_renderer_chunk(data: dict[str, Any], source_chunk: dict[str, Any]) -> dict[str, Any]:
    """Wrap AgInTi's compact model JSON into the renderer chunk schema."""
    paragraphs = source_chunk.get("paragraphs") or []
    if not paragraphs:
        raise ValueError(f"{source_chunk.get('chunk_id')}: source chunk has no paragraphs")
    if len(paragraphs) != 1:
        raise ValueError(
            f"{source_chunk.get('chunk_id')}: AgInTi writer currently expects one paragraph per chunk, "
            f"got {len(paragraphs)}"
        )
    paragraph = paragraphs[0]
    units = data.get("units", [])
    section_title = source_chunk.get("section_title", "")
    subsection_title = source_chunk.get("subsection_title", "")
    story_title = source_chunk.get("story_title", "")
    return {
        "chunk_id": source_chunk["chunk_id"],
        "section": {
            "id": source_chunk.get("section_id", "__section__"),
            "title": section_title,
            "title_zh": title_tokens(section_title, SISHU_TITLE_PINYIN),
            "title_ja": title_tokens(section_title, SISHU_TITLE_FURIGANA),
        },
        "subsection": {
            "id": source_chunk.get("subsection_id", "__subsection__"),
            "title": subsection_title,
            "title_zh": title_tokens(subsection_title, SISHU_TITLE_PINYIN),
            "title_ja": title_tokens(subsection_title, SISHU_TITLE_FURIGANA),
        },
        "story": {
            "id": source_chunk.get("story_id", "__story__"),
            "title": story_title,
            "title_zh": title_tokens(story_title, SISHU_TITLE_PINYIN),
            "title_ja": title_tokens(story_title, SISHU_TITLE_FURIGANA),
        },
        "paragraphs": [
            {
                "id": paragraph["id"],
                "source_text": paragraph.get("text", ""),
                "units": units,
            }
        ],
    }


def refresh_renderer_metadata(renderer_chunk: dict[str, Any], source_chunk: dict[str, Any]) -> dict[str, Any]:
    """Refresh source-derived section/story titles without changing generated units."""
    title_fields = (
        ("section", "section_id", "section_title", "__section__"),
        ("subsection", "subsection_id", "subsection_title", "__subsection__"),
        ("story", "story_id", "story_title", "__story__"),
    )
    for node_name, id_key, title_key, fallback_id in title_fields:
        title = source_chunk.get(title_key, "")
        node = renderer_chunk.setdefault(node_name, {})
        if not isinstance(node, dict):
            node = {}
            renderer_chunk[node_name] = node
        node["id"] = source_chunk.get(id_key, fallback_id)
        node["title"] = title
        node["title_zh"] = title_tokens(title, SISHU_TITLE_PINYIN)
        node["title_ja"] = title_tokens(title, SISHU_TITLE_FURIGANA)
    return renderer_chunk


def validate_renderer_chunk(renderer_chunk: dict[str, Any], source_chunk: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if renderer_chunk.get("chunk_id") != source_chunk.get("chunk_id"):
        errs.append(f"chunk_id mismatch: {renderer_chunk.get('chunk_id')!r}")
    for key in ("section", "subsection", "story"):
        if not isinstance(renderer_chunk.get(key), dict):
            errs.append(f"missing {key} object")
    paragraphs = renderer_chunk.get("paragraphs")
    source_paragraphs = source_chunk.get("paragraphs") or []
    if not isinstance(paragraphs, list) or not paragraphs:
        errs.append("missing paragraphs")
        return errs
    got_ids = [paragraph.get("id") for paragraph in paragraphs]
    expected_ids = [paragraph.get("id") for paragraph in source_paragraphs]
    if got_ids != expected_ids:
        errs.append(f"paragraph ids mismatch: expected {expected_ids}, got {got_ids}")
    for pi, paragraph in enumerate(paragraphs):
        units = paragraph.get("units")
        if not isinstance(units, list) or not units:
            errs.append(f"paragraphs[{pi}]: missing units")
            continue
        rebuilt_parts: list[str] = []
        for ui, unit in enumerate(units):
            errs += validate_unit(unit, f"paragraphs[{pi}].units[{ui}]")
            rebuilt_parts.append(token_text(unit.get("zh", [])))
        target = paragraph.get("source_text", "")
        if target and normalize("".join(rebuilt_parts)) != normalize(str(target)):
            errs.append(f"paragraphs[{pi}]: units do not reconstruct paragraph source_text")
    return errs


def is_renderer_chunk(data: dict[str, Any]) -> bool:
    return "paragraphs" in data and "section" in data and "subsection" in data and "story" in data


def promote_renderer_chunk(renderer_chunk: dict[str, Any], data_path: Path, reviewed_path: Path) -> None:
    atomic_write_json(data_path, renderer_chunk)
    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(data_path, reviewed_path)


def build_status(
    book_id: str,
    chunks: list[dict[str, Any]],
    reviewed_dir: Path,
    failed_ids: set[str],
) -> dict[str, Any]:
    first_missing: int | None = None
    valid_count = 0
    for index, chunk in enumerate(chunks, start=1):
        path = reviewed_dir / f"{chunk['chunk_id']}.json"
        if path.exists():
            valid_count += 1
        elif first_missing is None:
            first_missing = index
    failed_count = len(failed_ids)
    total = len(chunks)
    return {
        "book": book_id,
        "total_chunks": total,
        "raw": valid_count,
        "reviewed": valid_count,
        "failed": failed_count,
        "failed_ids": sorted(failed_ids),
        "pending": max(0, total - valid_count - failed_count),
        "first_missing": first_missing,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def save_computed_status(
    status_path: Path,
    book_id: str,
    chunks: list[dict[str, Any]],
    reviewed_dir: Path,
    failed_ids: set[str],
) -> dict[str, Any]:
    status = build_status(book_id, chunks, reviewed_dir, failed_ids)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def compile_previews(book_id: str, log) -> bool:
    env = os.environ.copy()
    env.setdefault("COMMIT_PROGRESS", "0")
    cmd = ["bash", "scripts/interlinear/compile_prepared_book_both_previews.sh", book_id]
    log(f"Compiling previews: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    compile_log = ROOT / "data" / "interlinear" / book_id / "compile.log"
    compile_log.parent.mkdir(parents=True, exist_ok=True)
    compile_log.write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        log(f"  COMPILE FAILED rc={result.returncode}; see {compile_log}")
        tail = "\n".join(result.stdout.splitlines()[-20:])
        if tail:
            log(tail)
        return False
    log(f"  COMPILE OK; see {compile_log}")
    return True


def promote_existing_outputs(
    chunks: list[dict[str, Any]],
    chunk_out_dir: Path,
    reviewed_dir: Path,
    log,
) -> tuple[int, set[str]]:
    chunk_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    promoted = 0
    failed_ids: set[str] = set()
    for chunk_id, source_chunk in chunk_by_id.items():
        out_path = chunk_out_dir / f"{chunk_id}.json"
        reviewed_path = reviewed_dir / f"{chunk_id}.json"
        if not out_path.exists():
            continue
        try:
            data = load_json(out_path)
        except (json.JSONDecodeError, OSError) as exc:
            log(f"  {chunk_id}: cannot read existing output: {exc}")
            failed_ids.add(chunk_id)
            continue
        if is_renderer_chunk(data):
            renderer = refresh_renderer_metadata(data, source_chunk)
        else:
            raw_errs = validate_chunk_output(data)
            if raw_errs:
                log(f"  {chunk_id}: existing compact output invalid ({len(raw_errs)} errors)")
                failed_ids.add(chunk_id)
                continue
            raw_path = chunk_out_dir / f"{chunk_id}.raw.json"
            if not raw_path.exists():
                atomic_write_json(raw_path, data)
            renderer = wrap_renderer_chunk(data, source_chunk)
        renderer_errs = validate_renderer_chunk(renderer, source_chunk)
        if renderer_errs:
            log(f"  {chunk_id}: renderer wrapper invalid ({len(renderer_errs)} errors)")
            for err in renderer_errs[:8]:
                log(f"    - {err}")
            failed_ids.add(chunk_id)
            continue
        promote_renderer_chunk(renderer, out_path, reviewed_path)
        promoted += 1
    return promoted, failed_ids


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
    parser.add_argument("--reviewed-dir", default="",
                        help="Renderer-ready chunk directory; default reads books/<book>/book-plan.json")
    parser.add_argument("--promote-existing", action="store_true",
                        help="Wrap/promote existing compact AgInTi outputs before writing new chunks")
    parser.add_argument("--promote-existing-only", action="store_true",
                        help="Only wrap/promote existing outputs, then exit")
    parser.add_argument("--compile-every", type=int, default=0,
                        help="Compile both preview PDFs after every N newly promoted chunks")
    parser.add_argument("--compile-at-end", action="store_true",
                        help="Compile both preview PDFs when the run finishes")
    args = parser.parse_args()

    book_id = args.book
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    plan: dict[str, Any] = {}
    if plan_path.exists():
        plan = load_json(plan_path)
    chunks_jsonl = ROOT / "books" / book_id / "work" / "bilingual" / "chunks" / "chunks.jsonl"
    chunk_out_dir = ROOT / "data" / "interlinear" / book_id / "chunks"
    if args.reviewed_dir:
        reviewed_dir = ROOT / args.reviewed_dir
    elif plan.get("reviewed_chunk_dir"):
        reviewed_dir = ROOT / str(plan["reviewed_chunk_dir"])
    else:
        reviewed_dir = ROOT / "books" / book_id / "work" / "bilingual" / "reviewed" / "chunks"
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
    reviewed_dir.mkdir(parents=True, exist_ok=True)
    failed_ids: set[str] = set(status.get("failed_ids", []))

    # Log setup
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")

    def log(msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts} {msg}"
        print(line)
        log_fh.write(line + "\n")
        log_fh.flush()

    if args.promote_existing or args.promote_existing_only:
        promoted, existing_failed = promote_existing_outputs(chunks, chunk_out_dir, reviewed_dir, log)
        failed_ids.update(existing_failed)
        status = save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
        log(
            f"Promoted existing outputs: promoted={promoted} "
            f"valid={status['reviewed']} failed={status['failed']} first_missing={status['first_missing']}"
        )
        if args.promote_existing_only:
            if args.compile_at_end:
                compile_previews(book_id, log)
            log_fh.close()
            return 0

    processed = 0
    newly_promoted = 0
    start_idx = max(0, args.start_chunk - 1)

    for idx in range(start_idx, total):
        if args.max_chunks and processed >= args.max_chunks:
            log(f"Reached --max-chunks={args.max_chunks}, stopping")
            break

        chunk = chunks[idx]
        chunk_id = chunk["chunk_id"]
        out_path = chunk_out_dir / f"{chunk_id}.json"
        raw_path = chunk_out_dir / f"{chunk_id}.raw.json"
        reviewed_path = reviewed_dir / f"{chunk_id}.json"

        # Resume check
        if reviewed_path.exists():
            try:
                existing = load_json(reviewed_path)
                if is_renderer_chunk(existing):
                    existing = refresh_renderer_metadata(existing, chunk)
                errs = validate_renderer_chunk(existing, chunk)
                if not errs:
                    promote_renderer_chunk(existing, out_path, reviewed_path)
                    processed += 1
                    continue
                else:
                    log(f"  {chunk_id}: reviewed file has {len(errs)} validation errors, redoing")
            except (json.JSONDecodeError, OSError) as e:
                log(f"  {chunk_id}: reviewed file corrupt ({e}), redoing")
        elif out_path.exists():
            try:
                existing = load_json(out_path)
                if is_renderer_chunk(existing):
                    renderer = refresh_renderer_metadata(existing, chunk)
                else:
                    raw_errs = validate_chunk_output(existing)
                    if raw_errs:
                        renderer = None
                    else:
                        if not raw_path.exists():
                            atomic_write_json(raw_path, existing)
                        renderer = wrap_renderer_chunk(existing, chunk)
                if renderer:
                    errs = validate_renderer_chunk(renderer, chunk)
                    if not errs:
                        promote_renderer_chunk(renderer, out_path, reviewed_path)
                        processed += 1
                        newly_promoted += 1
                        if args.compile_every and newly_promoted % args.compile_every == 0:
                            compile_previews(book_id, log)
                        continue
                    log(f"  {chunk_id}: existing data output has {len(errs)} validation errors, redoing")
            except (json.JSONDecodeError, OSError, ValueError) as e:
                log(f"  {chunk_id}: existing data output unusable ({e}), redoing")

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
            failed_ids.add(chunk_id)
            save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
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
                    failed_ids.add(chunk_id)
                    raw_path.write_text(raw_response, encoding="utf-8")
                    save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
                    time.sleep(args.delay * 2)
                    continue
            else:
                log(f"  JSON PARSE ERROR: {e}")
                log(f"  Raw response (first 200 chars): {raw_response[:200]}")
                failed_ids.add(chunk_id)
                raw_path.write_text(raw_response, encoding="utf-8")
                save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
                time.sleep(args.delay * 2)
                continue

        # Validate compact model output and renderer wrapper.
        data["chunk_id"] = chunk_id
        errs = validate_chunk_output(data)
        renderer: dict[str, Any] | None = None
        if not errs:
            try:
                renderer = wrap_renderer_chunk(data, chunk)
            except ValueError as exc:
                errs.append(str(exc))
        if renderer is not None:
            errs += validate_renderer_chunk(renderer, chunk)
        if errs:
            log(f"  VALIDATION FAILED ({len(errs)} errors):")
            for err in errs[:10]:
                log(f"    - {err}")
            failed_ids.add(chunk_id)
            # Still save the raw output for debugging
            atomic_write_json(raw_path, data)
            save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
            time.sleep(args.delay * 2)
            continue

        # Save compact audit output and renderer-ready output.
        atomic_write_json(raw_path, data)
        promote_renderer_chunk(renderer, out_path, reviewed_path)
        failed_ids.discard(chunk_id)
        processed += 1
        newly_promoted += 1
        status = save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
        log(f"  OK -> {reviewed_path}")
        if args.compile_every and newly_promoted % args.compile_every == 0:
            compile_previews(book_id, log)

        time.sleep(args.delay)

    # Final status update
    status = save_computed_status(status_path, book_id, chunks, reviewed_dir, failed_ids)
    if args.compile_at_end:
        compile_previews(book_id, log)

    log(
        f"Done. raw={status['raw']} reviewed={status.get('reviewed',0)} "
        f"failed={status.get('failed',0)} pending={status['pending']} "
        f"first_missing={status['first_missing']}"
    )
    log_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
