#!/usr/bin/env python3
"""Resumable DeepSeek writer for three-layer classical Chinese chunks.

Reads chunks.jsonl line by line, calls DeepSeek API, validates output,
retries on failure, writes to data/interlinear/shiji-aginti/chunks/.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pypinyin import Style, lazy_pinyin

# Import shared config (replaces duplicated hard-coded constants)
from shiji_config import (
    HAN_RE as CFG_HAN_RE, KANA_RE as CFG_KANA_RE,
    SINGLE_HAN_RE as CFG_SINGLE_HAN_RE,
    GRAMMAR_ROLES, ROLE_ALIASES,
    JP_COMPOUND_READING_OVERRIDES, JP_SINGLE_KANJI_READING_OVERRIDES,
    resolve_role, ja_quality_error, looks_like_real_japanese_reference,
    token_text as cfg_token_text,
    normalize as cfg_normalize,
    allows_identical_zh_modern,
)

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
MODE = "zh_classical_three_layer"

VALIDATOR = str(Path(__file__).resolve().parent / "validate_shiji_chunk.py")
OUT_DIR = Path("data/interlinear/shiji-aginti/chunks")
LOG_DIR = Path("books/shiji/work/aginti/logs")
STATUS = Path("books/shiji/work/aginti/pilot_status.json")
STATUS_LOCK = STATUS.with_suffix(STATUS.suffix + ".lock")
JSONL = Path("books/shiji/work/bilingual/chunks/chunks.jsonl")

JSON_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？；])')
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
ALL_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$")
# KANBUN_MARKERS_IN_JA moved to source-audit.json / shiji_config.py
MISSING_JA_READING_RE = re.compile(r"kanji '([^']+)' needs furigana")
PUNCT_RE = re.compile(r"^[，。、；：！？「」『』【】《》（）—…·・\"'\\-\\.\\!\\?\\;\\:\\(\\)\\[\\]\\s]+$")
# GRAMMAR_ROLES and ROLE_ALIASES imported from shiji_config
# JP_COMPOUND_READING_OVERRIDES imported from shiji_config
JP_SINGLE_KANJI_READING_OVERRIDES = {
    "高": "こう",
    "辛": "しん",
    "娵": "しゅ",
    "訾": "し",
    "氏": "し",
    "摯": "し",
    "嚳": "こく",
    "堯": "ぎょう",
    "勛": "くん",
    "而": "じ",
}


def _pinyin_char(ch: str) -> str:
    if not SINGLE_HAN_RE.fullmatch(ch):
        return ""
    try:
        values = lazy_pinyin(ch, style=Style.TONE, errors="ignore")
    except Exception:
        return ""
    return values[0] if values else ""


def _iter_ja_tokens(data):
    for para in data.get("paragraphs", []):
        for unit in para.get("units", []):
            for tok in unit.get("ja", []) if isinstance(unit.get("ja"), list) else []:
                if isinstance(tok, dict):
                    yield tok


def _split_long_sentence(sentence: str, max_chars: int = 96) -> list[str]:
    """Split oversized classical-Chinese sentences into comma-level clauses.

    DeepSeek often returns truncated JSON for very long, heavily annotated
    sentences because every Hanzi must be tokenized separately. Clause-level
    units still reconstruct the paragraph exactly while keeping each model
    request small enough to return valid JSON.
    """
    sentence = sentence.strip()
    if len(sentence) <= max_chars:
        return [sentence] if sentence else []

    pieces: list[str] = []
    buf: list[str] = []
    min_chars = max(36, max_chars // 2)

    for ch in sentence:
        buf.append(ch)
        if len(buf) >= min_chars and ch in "，、":
            pieces.append("".join(buf).strip())
            buf.clear()

    if buf:
        pieces.append("".join(buf).strip())

    out: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if len(piece) <= max_chars * 3 // 2:
            out.append(piece)
            continue
        # Last-resort split for a long piece with no comma. Prefer not to use
        # this, but it prevents one pathological clause from blocking the run.
        start = 0
        while start < len(piece):
            out.append(piece[start:start + max_chars])
            start += max_chars

    return out


def _split_sentences(text: str) -> list[str]:
    """Split text while keeping closing quotes, then split oversized clauses."""
    out: list[str] = []
    buf: list[str] = []
    closing = set("」』】》）)]")
    i = 0
    while i < len(text):
        ch = text[i]
        buf.append(ch)
        if ch in "。！？；":
            j = i + 1
            while j < len(text) and text[j] in closing:
                buf.append(text[j])
                j += 1
            sentence = "".join(buf).strip()
            if sentence:
                out.extend(_split_long_sentence(sentence))
            buf.clear()
            i = j
            continue
        i += 1
    rest = "".join(buf).strip()
    if rest:
        out.extend(_split_long_sentence(rest))
    return out


def _token_text(tokens: list[dict]) -> str:
    return cfg_token_text(tokens)


def _norm_text(text: str) -> str:
    return cfg_normalize(text)


def _looks_like_real_japanese_reference(text: str) -> bool:
    return looks_like_real_japanese_reference(text)


def _looks_like_name_title_list(text: str) -> bool:
    list_marks = text.count("、") + text.count("，") + text.count(",")
    title_hits = sum(text.count(term) for term in ("侯", "丞相", "卿", "大夫", "將軍", "御史", "廷尉", "博士"))
    return len(HAN_RE.findall(text)) >= 30 and list_marks >= 4 and title_hits >= 2


def _looks_like_table_header(text: str) -> bool:
    """Detect sparse source rows such as timeline/table headers.

    Some Shiji source chunks are not prose sentences, e.g. "公元前 秦 楚 ...".
    They still need a readable Japanese explanatory line rather than a bare
    all-kanji list, while zh_original must preserve the exact source text.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if any(mark in stripped for mark in "。！？；，、："):
        return False
    parts = [p for p in re.split(r"\s+", stripped) if p]
    if len(parts) < 4:
        return False
    han_parts = sum(1 for p in parts if HAN_RE.search(p))
    short_parts = sum(1 for p in parts if len(p) <= 4)
    return han_parts >= 4 and short_parts >= len(parts) - 1


def _ja_quality_error(ja_text: str, zh_original_text: str) -> str:
    return ja_quality_error(ja_text, zh_original_text)


def _role(value: str, default: str = "function") -> str:
    return resolve_role(value, default)


def _normalize_tokens(tokens, lang: str):
    """Normalize model tokens to the strict validator schema."""
    normalized = []
    for tok in tokens if isinstance(tokens, list) else []:
        if not isinstance(tok, dict):
            continue
        text = str(tok.get("t", ""))
        if not text:
            continue
        reading = str(tok.get("r", ""))
        role = str(tok.get("g", ""))
        if ALL_HAN_RE.fullmatch(text) and len(text) > 1:
            readings = []
            if lang == "ja":
                readings = JP_COMPOUND_READING_OVERRIDES.get(text, [])
            elif lang == "zh":
                pieces = [p for p in reading.split() if p]
                if len(pieces) == len(text):
                    readings = pieces
            for i, ch in enumerate(text):
                normalized.append({
                    "t": ch,
                    "r": readings[i] if i < len(readings) else (
                        _pinyin_char(ch) if lang == "zh" else ""
                    ),
                    "g": _role(role, "object"),
                })
            continue
        has_han = bool(HAN_RE.search(text))
        is_single_han = bool(SINGLE_HAN_RE.fullmatch(text))
        if lang == "ja" and not is_single_han:
            reading = ""
        if lang == "zh" and not is_single_han:
            reading = ""
        if lang == "zh" and is_single_han and not reading:
            reading = _pinyin_char(text)
        if lang == "ja" and is_single_han and not reading:
            reading = JP_SINGLE_KANJI_READING_OVERRIDES.get(text, "")
        if lang == "ja" and has_han and not is_single_han:
            kana_buf: list[str] = []

            def flush_kana() -> None:
                if kana_buf:
                    normalized.append({
                        "t": "".join(kana_buf),
                        "r": "",
                        "g": _role(role, "function"),
                    })
                    kana_buf.clear()

            for ch in text:
                if SINGLE_HAN_RE.fullmatch(ch):
                    flush_kana()
                    normalized.append({
                        "t": ch,
                        "r": JP_SINGLE_KANJI_READING_OVERRIDES.get(ch, ""),
                        "g": _role(role, "object"),
                    })
                else:
                    kana_buf.append(ch)
            flush_kana()
            continue
        if PUNCT_RE.fullmatch(text):
            normalized.append({"t": text, "r": "", "g": ""})
        else:
            normalized.append({
                "t": text,
                "r": reading if is_single_han else "",
                "g": _role(role, "function" if not has_han else "object"),
            })
    return normalized


def _rebuild_zh_original_from_source(source_text: str, tokens: list[dict]) -> list[dict]:
    """Force classical Chinese tokens to exactly follow the source text.

    The model sometimes omits punctuation such as the colon in 曰：「...」 while
    still producing useful pinyin and grammar roles for the Hanzi. Rebuild from
    the source sentence and reuse Hanzi readings/roles in order.
    """
    han_tokens = [
        tok for tok in tokens
        if isinstance(tok, dict) and SINGLE_HAN_RE.fullmatch(str(tok.get("t", "")))
    ]
    rebuilt: list[dict] = []
    han_idx = 0
    for ch in source_text:
        if ch.isspace():
            continue
        if SINGLE_HAN_RE.fullmatch(ch):
            src = han_tokens[han_idx] if han_idx < len(han_tokens) else {}
            rebuilt.append({
                "t": ch,
                "r": str(src.get("r", "")) if isinstance(src, dict) else "",
                "g": _role(str(src.get("g", "")) if isinstance(src, dict) else "", "object"),
            })
            han_idx += 1
        else:
            rebuilt.append({"t": ch, "r": "", "g": ""})
    return rebuilt


def _sanitize_unit(unit):
    unit["zh_original"] = _normalize_tokens(unit.get("zh_original", []), "zh")
    unit["ja"] = _normalize_tokens(unit.get("ja", []), "ja")
    unit["zh_modern"] = _normalize_tokens(unit.get("zh_modern", []), "zh")
    return unit


def _sanitize_data(data):
    for para in data.get("paragraphs", []):
        for unit in para.get("units", []):
            _sanitize_unit(unit)
    return data


def _missing_ja_readings(errors: str) -> list[str]:
    seen = []
    for match in MISSING_JA_READING_RE.finditer(errors or ""):
        char = match.group(1)
        if SINGLE_HAN_RE.fullmatch(char) and char not in seen:
            seen.append(char)
    return seen


def _ja_contexts(data, chars: list[str]) -> dict[str, list[str]]:
    wanted = set(chars)
    contexts = {ch: [] for ch in chars}
    for para in data.get("paragraphs", []):
        for unit in para.get("units", []):
            ja = unit.get("ja", [])
            if not isinstance(ja, list):
                continue
            texts = [str(tok.get("t", "")) if isinstance(tok, dict) else "" for tok in ja]
            for idx, tok in enumerate(ja):
                if not isinstance(tok, dict):
                    continue
                ch = str(tok.get("t", ""))
                if ch not in wanted or tok.get("r"):
                    continue
                start = max(0, idx - 8)
                end = min(len(texts), idx + 9)
                context = "".join(texts[start:end])
                if context and context not in contexts[ch]:
                    contexts[ch].append(context)
    return contexts


def _repair_missing_ja_readings_with_model(data, missing_chars: list[str]) -> dict[str, str]:
    contexts = _ja_contexts(data, missing_chars)
    prompt_payload = {
        "missing_kanji": missing_chars,
        "contexts": {k: v[:4] for k, v in contexts.items()},
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You provide Japanese furigana for single kanji tokens in classical "
                "Chinese/Japanese historical text. Output ONLY JSON. Use hiragana or "
                "katakana readings, no romanization, no explanations."
            ),
        },
        {
            "role": "user",
            "content": (
                "Return JSON in this exact shape: {\"readings\":{\"漢\":\"かん\"}}.\n"
                "Give one reasonable Japanese on-yomi/name reading for each missing "
                "single kanji, considering the local contexts.\n\n"
                + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
            ),
        },
    ]
    resp = chat(messages, temp=0.0)
    raw = resp["choices"][0]["message"]["content"]
    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        return {}
    readings = parsed.get("readings", parsed)
    if not isinstance(readings, dict):
        return {}
    fixed = {}
    for ch in missing_chars:
        reading = str(readings.get(ch, "")).strip()
        if reading:
            fixed[ch] = reading
    return fixed


def _repair_missing_ja_readings(data, errors: str) -> tuple[dict, bool]:
    missing = _missing_ja_readings(errors)
    if not missing:
        return data, False

    readings = {
        ch: JP_SINGLE_KANJI_READING_OVERRIDES[ch]
        for ch in missing
        if ch in JP_SINGLE_KANJI_READING_OVERRIDES
    }
    unresolved = [ch for ch in missing if ch not in readings]
    if unresolved:
        try:
            readings.update(_repair_missing_ja_readings_with_model(data, unresolved))
        except Exception as exc:
            print(f"  furigana repair failed: {str(exc)[:200]}", flush=True)

    changed = False
    for tok in _iter_ja_tokens(data):
        ch = str(tok.get("t", ""))
        if ch in readings and not tok.get("r"):
            tok["r"] = readings[ch]
            changed = True
    if changed:
        repaired = ", ".join(f"{ch}={readings[ch]}" for ch in sorted(readings) if readings.get(ch))
        print(f"  repaired missing ja readings: {repaired}", flush=True)
    return data, changed


def load_key():
    v = os.environ.get("DEEPSEEK_API_KEY", "")
    if v:
        return v
    envf = Path(".aginti/.env")
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def key_ok():
    return bool(load_key())


def chat(messages, temp=0.1):
    import urllib.request
    k = load_key()
    if not k:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temp,
        "max_tokens": int(os.environ.get("SHIJI_DEEPSEEK_MAX_TOKENS", "8192")),
        "response_format": {"type": "json_object"},
    }

    def request_once(body_payload):
        body = json.dumps(body_payload).encode()
        req = urllib.request.Request(DEEPSEEK_URL, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + k,
        })
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())

    try:
        return request_once(payload)
    except urllib.error.HTTPError as e:
        b = e.read().decode(errors="replace")
        if (
            "response_format" in payload
            and re.search(r"response_format|json_object|unsupported|invalid", b, re.I)
        ):
            payload.pop("response_format", None)
            try:
                return request_once(payload)
            except urllib.error.HTTPError as retry_e:
                b = retry_e.read().decode(errors="replace")
                raise RuntimeError("DeepSeek HTTP " + str(retry_e.code) + ": " + b[:300])
        raise RuntimeError("DeepSeek HTTP " + str(e.code) + ": " + b[:300])


FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)

def extract_json(text):
    # Try markdown fence first
    m = FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON
    m = JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def validate(path):
    r = subprocess.run([sys.executable, VALIDATOR, str(path), "--quiet"],
                       capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr.strip()


def read_line(cid):
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("chunk_id") == cid:
                return obj
    return None


def prompt_sentence(sentence_text, section_title, section_id,
                    paragraph_id, jp_refs, sentence_idx, total_sentences,
                    prev_sentence_text="", retry_errs=""):
    """Build a per-sentence prompt with trimmed Kanbun/Japanese reference."""
    jp_excerpt = ""
    for r in jp_refs:
        txt = r.get("text", "")
        if not _looks_like_real_japanese_reference(txt):
            continue
        if len(jp_excerpt) + len(txt) + 1 > 1200:
            remaining = 1000 - len(jp_excerpt)
            if remaining > 40:
                jp_excerpt += txt[:remaining] + "\n"
            break
        jp_excerpt += txt + "\n"
    if len(jp_excerpt) > 1200:
        jp_excerpt = jp_excerpt[:1200] + "..."
    if not jp_excerpt:
        jp_excerpt = (
            "No reliable real Japanese translation reference was found for this chapter. "
            "The available Japanese-Wikisource material is mostly Kanbun/classical Chinese. "
            "Generate the ja field yourself as natural Japanese from the Chinese source sentence."
        )

    sysmsg = (
        "You are a classical Chinese and Japanese literary translation expert producing JSON for Sima Qian's 史記. "
        "Output ONLY valid JSON, no commentary.\n\n"
        "CRITICAL TOKEN RULES - VIOLATING THESE MEANS FAILURE:\n"
        "1. EVERY single Chinese character (Hanzi) MUST be its own separate token. "
        "Example: 黄帝 → {\"t\":\"黄\"} and {\"t\":\"帝\"}, NEVER {\"t\":\"黄帝\"}.\n"
        "2. EVERY single Japanese kanji MUST be its own separate token. "
        "Example: 黄帝 → {\"t\":\"黄\",\"r\":\"こう\"} and {\"t\":\"帝\",\"r\":\"てい\"}, NEVER {\"t\":\"黄帝\",\"r\":\"こうてい\"}.\n"
        "3. Kana (hiragana/katakana) may be multi-char, must have r=\"\" (NO furigana on kana) and a valid grammar role.\n"
        "4. Punctuation tokens have g=\"\" and r=\"\" (no reading).\n\n"
        "SCHEMA:\n"
        'Output a JSON object with keys: source_text, zh_original, ja, zh_modern.\n'
        '  "source_text": the exact sentence text.\n'
        '  "zh_original": [{"t": char, "r": pinyin, "g": role}] — classical Chinese, every Hanzi a single-char token with pinyin.\n'
        '  "ja": [{"t": text, "r": furigana, "g": role}] — REAL JAPANESE rendering, FLAT token list (NOT nested). '
        "Every kanji is single-char with furigana. Kana tokens must have r=\"\".\n"
        '  "zh_modern": [{"t": char, "r": pinyin, "g": role}] — MODERN Chinese paraphrase. Every Hanzi single-char with pinyin. '
        "MUST DIFFER from zh_original text.\n\n"
        "ALLOWED GRAMMAR ROLES (use ONLY these):\n"
        "- subject predicate object attributive adverbial complement topic function\n"
        "DO NOT use: conjunction, auxiliary, particle, or any other role.\n\n"
        "RULES:\n"
        "- zh_original joined MUST exactly reconstruct source_text (whitespace-insensitive).\n"
        "- zh_modern is a MODERN Chinese explanation/paraphrase in your OWN words.\n"
        "- ja MUST be real modern Japanese prose. Do NOT write Kanbun kundoku fragments. "
        "It must have Japanese grammar, kana particles, okurigana, and inflected endings.\n"
        "- The so-called Japanese reference is often NOT a Japanese translation. It may be Kanbun/classical Chinese "
        "from Japanese Wikisource. Use it only to confirm alignment and names; DO NOT copy it into ja.\n"
        "- Forbidden ja style: all-kanji/all-Hanzi Kanbun such as 「而蚩尤最為暴、莫能伐。」 or "
        "「帝顓頊生子曰窮蟬。」.\n"
        "- Also forbidden inside ja: raw Classical Chinese function markers like 而, 之, 於, 曰, 乃, 弗, 莫, 毋, 咸, 其, 焉. "
        "Translate them as Japanese: しかし/そして, の, において, 言った, そこで, ない, みな, その, etc. "
        "Exception: real proper names, work/music titles, wind/calendar names, and official titles may retain their kanji, including short titles ending in 侯/王/君, e.g. 咸陽, 咸池, 廣莫/広莫, 廣莫風/広莫風, 焉逢/焉逢攝提格, 宋毋忌, 子弗湟, 巫咸, 咸艾, 咸有一德/咸有一徳, 弗忌, 差弗, 之罘, 馮毋擇, 審食其, 酈食其, 食其, 釋之/釈之, 勇之, 贅其侯.\n"
        "A one-character place name may be retained only when the source clearly uses it as a place, e.g. 咸 in 敗翟于咸.\n"
        "Likewise, 子之 may be retained as a personal name in the Yan passage about 蘇秦/蘇代, but do not retain 之 as a particle elsewhere.\n"
        "- Do not write kundoku marker phrases such as 於是乃ち, 而して, 焉に, 之を, 其の. "
        "Use modern Japanese instead: そこで, そして/それから, そこを, これを/それを, その.\n"
        "- For 者 clauses, write natural Japanese such as 人, 者(もの), or ...する者 only when it follows kana. "
        "Do not output bare Kanbun-style compounds such as 王者、 or 侯者、.\n"
        "- Good ja style examples: 「しかし蚩尤は最も凶暴で、誰も討つことができなかった。」 / "
        "「帝顓頊は子をもうけ、その名を窮蟬といった。」 / "
        "「黃帝には二十五人の子があり、そのうち姓を得た者は十四人であった。」\n"
        "- Prefer idiomatic Japanese over word-for-word Kanbun. For example, translate 最為暴 as 最も凶暴で, "
        "not 最も暴で; translate 曰 as 言った, not 曰く/曰う; translate 之 as の/それ/彼/彼ら as context requires.\n"
        "- Citation formulas such as 詩傳曰, 太史公曰, 褚先生曰 must become modern Japanese framing, "
        "for example 『詩伝』には「...」とある / 太史公は「...」と述べた. Never leave 曰 inside ja.\n"
        "- Astronomical/table formulas beginning with 曰 must also become Japanese wording, "
        "for example 曰東方木，主春 → 東方は木に属し、春をつかさどるという. "
        "Never copy the character 曰 into ja, even when the source is a compact formula.\n"
        "- For every content-bearing sentence, ja must contain kana. Names and terms may stay in kanji, but the sentence "
        "must still read as Japanese prose.\n"
        "- For long lists of officials or personal names, keep each title/name in kanji, but wrap the list in Japanese syntax, "
        "for example: 「列侯武城侯の王離、列侯通武侯の王賁、...らが従い、海上でともに議論した。」 "
        "Do not force-read every name as prose, and do not output a bare Chinese list.\n"
        "- ja is FLAT list of dicts, NOT nested arrays, NOT [[...], [...]] double lines.\n"
        "- Punctuation attaches to preceding unit.\n"
        "- NO placeholder Japanese like 注 or 日本語. Every unit must have meaningful Japanese.\n"
        "- Before outputting, double-check: is every single kanji/Hanzi its own token?\n"
        "- DOUBLE CHECK: kana (ひらがな, カタカナ) NEVER have furigana. Only kanji have furigana.\n"
    )
    note = ""
    if retry_errs:
        note = "\nPREVIOUS VALIDATION ERRORS:\n" + retry_errs + "\n\nFix these and output valid JSON for this sentence.\n"
    if total_sentences > 1:
        note += f"\nThis is sentence {sentence_idx + 1} of {total_sentences} for this paragraph.\n"
        if prev_sentence_text:
            note += f"Previous sentence: {prev_sentence_text}\n"
        note += "Continue the flow naturally.\n"
    if _looks_like_name_title_list(sentence_text):
        note += (
            "\nThis sentence is mostly official titles and personal names. Keep titles and names in kanji, "
            "but add a clear Japanese frame with particles and a final predicate. Use a structure like: "
            "「列侯武城侯の王離、列侯通武侯の王賁、...らが従い、海上でともに議論した。」 "
            "Do not output a bare Chinese-style list.\n"
        )
    if _norm_text(sentence_text).startswith("曰"):
        note += (
            "\nThis source sentence begins with 曰 as a compact formula marker. In ja, translate it with "
            "Japanese wording such as 「...という」 or 「...とされる」. Do not include the character 曰 "
            "or the word 曰く in the ja tokens.\n"
        )
    if _looks_like_table_header(sentence_text):
        note += (
            "\nThis source line is a table/timeline header, not narrative prose. Preserve zh_original exactly, "
            "but write ja as a readable Japanese explanatory sentence with kana and a predicate, not a bare list. "
            "Example style: 「これは『公元前』と秦・楚・項・趙・齊・漢・燕・魏・韓を並べた表の見出しである。」 "
            "Write zh_modern as a modern Chinese explanation such as: 「这是一个表头，列出公元前以及秦、楚、项、赵、齐、汉、燕、魏、韩等栏目。」\n"
        )

    user = (
        "Tokenize this classical Chinese sentence from 史記:\n\n"
        "Section: " + section_title + " (" + section_id + ")\n"
        "Paragraph: " + paragraph_id + "\n"
        "Sentence:\n" + sentence_text + "\n\n"
        "Kanbun/Japanese-source reference. WARNING: this is often classical Chinese, not real Japanese; do not copy it:\n"
        + jp_excerpt + "\n\n"
        "Output JSON with source_text, zh_original, ja (flat REAL Japanese prose), zh_modern for this one sentence only.\n"
        + note
    )
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def load_status():
    if STATUS.exists():
        return json.loads(STATUS.read_text())
    return {"generated": 0, "failed": 0, "chunks": {}}


def save_status(st):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def update_status(cid: str, ok: bool) -> None:
    """Record chunk status safely when multiple shard writers run."""
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_LOCK.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        st = load_status()
        was_ok = bool(st.get("chunks", {}).get(cid, {}).get("ok"))
        st.setdefault("chunks", {})[cid] = {
            "ok": ok,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if ok and not was_ok:
            st["generated"] = st.get("generated", 0) + 1
        elif not ok:
            st["failed"] = st.get("failed", 0) + 1
        tmp = STATUS.with_suffix(f"{STATUS.suffix}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATUS)
        fcntl.flock(lock, fcntl.LOCK_UN)


def generate_sentence_unit(sentence_text, section_title, section_id,
                           paragraph_id, jp_refs, sentence_idx, total_sentences,
                           prev_sentence_text="", max_retries=2):
    """Generate one sentence unit via DeepSeek. Returns (unit_dict, error_str)."""
    retry = ""
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            msgs = prompt_sentence(sentence_text, section_title, section_id,
                                   paragraph_id, jp_refs, sentence_idx,
                                   total_sentences, prev_sentence_text, retry)
            resp = chat(msgs)
            txt = resp["choices"][0]["message"]["content"]
            data = extract_json(txt)
            if not data:
                sample = txt[:300].replace("\n", "\\n")
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: no JSON, raw sample: {sample}", flush=True)
                retry = f"No JSON found. Response starts: {sample}. Output ONLY valid JSON."
                last_err = retry
                continue

            # Validate the unit structure minimally
            if not isinstance(data.get("source_text"), str) or not data.get("source_text"):
                last_err = "missing or empty source_text"
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue
            if not isinstance(data.get("zh_original"), list) or not data["zh_original"]:
                last_err = "missing zh_original token list"
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue
            if not isinstance(data.get("ja"), list) or not data["ja"]:
                last_err = "missing ja token list"
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue
            if not isinstance(data.get("zh_modern"), list) or not data["zh_modern"]:
                last_err = "missing zh_modern token list"
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue

            data = _sanitize_unit(data)
            data["source_text"] = sentence_text
            data["zh_original"] = _rebuild_zh_original_from_source(
                sentence_text, data["zh_original"])

            # Check reconstruction: zh_original joined should match source_text
            zt = re.sub(r"\s+", "", "".join(t.get("t", "") for t in data["zh_original"]))
            st = re.sub(r"\s+", "", sentence_text)
            if zt != st:
                last_err = f"zh_original reconstructs '{zt[:60]}' != source_text '{st[:60]}'"
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue

            zmt = _norm_text(_token_text(data["zh_modern"]))
            if HAN_RE.search(zt) and zmt == zt and not allows_identical_zh_modern(sentence_text):
                last_err = (
                    "zh_modern identical to zh_original; rewrite zh_modern as "
                    "modern Chinese explanatory prose, not the classical source"
                )
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue

            ja_err = _ja_quality_error(_token_text(data["ja"]), _token_text(data["zh_original"]))
            if ja_err:
                last_err = ja_err
                print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                      f"attempt {attempt+1}: {last_err}", flush=True)
                retry = last_err
                continue

            # Post-process: fix common model errors before returning
            # 1. Strip furigana from non-kanji ja tokens (kana should have r="")
            # 2. Map unauthorized grammar roles to "function"
            ALLOWED_ROLES = {"subject", "predicate", "object", "attributive",
                             "adverbial", "complement", "topic", "function"}
            KANJI_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
            for token_list_name in ["zh_original", "ja", "zh_modern"]:
                tl = data.get(token_list_name, [])
                if not isinstance(tl, list):
                    continue
                for tok in tl:
                    if not isinstance(tok, dict):
                        continue
                    t = str(tok.get("t", ""))
                    # Fix grammar role
                    g = str(tok.get("g", ""))
                    if g and g not in ALLOWED_ROLES:
                        tok["g"] = "function"
                    # Fix furigana on non-kanji in ja
                    if token_list_name == "ja" and tok.get("r"):
                        if t and not KANJI_RE.search(t):
                            tok["r"] = ""

            unit = {
                "source_text": data["source_text"],
                "zh_original": data["zh_original"],
                "ja": data["ja"],
                "zh_modern": data["zh_modern"],
            }
            print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                  f"OK (attempt {attempt+1}): {data['source_text'][:50]}...", flush=True)
            return unit, ""

        except Exception as e:
            last_err = str(e)[:300]
            print(f"    sentence[{sentence_idx+1}/{total_sentences}] "
                  f"attempt {attempt+1}: {last_err}", flush=True)
            retry = last_err
            time.sleep(2)

    return None, last_err


def generate_paragraph_sentences(chunk, max_retries):
    """Generate all paragraphs for a chunk using per-sentence DeepSeek calls.
    Returns list of paragraph dicts, or None on failure."""
    paras = chunk.get("paragraphs", [])
    section_title = chunk.get("subsection_title", "") or chunk.get("section_title", "")
    section_id = chunk.get("subsection_id", "") or section_title
    jp_refs = chunk.get("jp_reference", [])
    out_paras = []

    for p_idx, para in enumerate(paras):
        zh = para.get("text", "")
        pid = para.get("id", "")
        sentences = _split_sentences(zh)
        print(f"  para[{p_idx+1}/{len(paras)}]: {len(sentences)} sentences, "
              f"total chars={len(zh)}", flush=True)

        if not sentences:
            print(f"  para[{p_idx+1}/{len(paras)}]: empty, skipping", flush=True)
            continue

        units = []
        prev_text = ""
        all_ok = True
        for s_idx, sentence in enumerate(sentences):
            print(f"  sentence[{s_idx+1}/{len(sentences)}]: {sentence[:60]}...", flush=True)
            unit, err = generate_sentence_unit(
                sentence_text=sentence,
                section_title=section_title,
                section_id=section_id,
                paragraph_id=pid,
                jp_refs=jp_refs,
                sentence_idx=s_idx,
                total_sentences=len(sentences),
                prev_sentence_text=prev_text,
                max_retries=max_retries,
            )
            if unit is None:
                print(f"    FAILED sentence[{s_idx+1}/{len(sentences)}]: {err[:200]}", flush=True)
                all_ok = False
                break
            units.append(unit)
            prev_text = sentence

        if not all_ok:
            return None

        out_paras.append({"source_text": zh, "units": units})

    return out_paras


def generate_one(cid, max_retries, force):
    """Generate one chunk using per-sentence DeepSeek calls."""
    opath = OUT_DIR / (cid + ".json")
    if opath.exists() and not force:
        ok, _ = validate(opath)
        if ok:
            print("  " + cid + ": already valid, skip")
            return True
        print("  " + cid + ": exists invalid, regenerating")

    chunk = read_line(cid)
    if not chunk:
        print("  " + cid + ": NOT FOUND in JSONL")
        return False

    paras = generate_paragraph_sentences(chunk, max_retries)
    if paras is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / (cid + ".fail.log")).write_text(
            "Paragraph-level generation failed.\n", encoding="utf-8")
        print("  " + cid + ": FAILED (paragraph generation)")
        return False

    section_title = chunk.get("subsection_title", "") or chunk.get("section_title", "")
    section_id = chunk.get("subsection_id", "") or section_title

    data = {
        "mode": MODE,
        "chunk_id": cid,
        "section": {
            "id": section_id,
            "title_zh_original": section_title,
            "title_ja": section_title,
        },
        "paragraphs": paras,
    }
    data = _sanitize_data(data)

    opath.parent.mkdir(parents=True, exist_ok=True)
    candidate = opath.with_suffix(".candidate.json")
    candidate.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    ok, errs = validate(candidate)
    for _ in range(2):
        if ok:
            break
        data, changed = _repair_missing_ja_readings(data, errs)
        if not changed:
            break
        candidate.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        ok, errs = validate(candidate)
    if ok:
        candidate.replace(opath)
        print("  " + cid + ": OK")
        return True
    print("  " + cid + ": validation failed after generation\n  " + errs.replace("\n", "\n  "))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / (cid + ".invalid.json")).write_text(
        candidate.read_text(encoding="utf-8"), encoding="utf-8")
    (LOG_DIR / (cid + ".fail.log")).write_text(
        "errors:\n" + errs + "\n", encoding="utf-8")
    candidate.unlink(missing_ok=True)
    if opath.exists():
        existing_ok, _ = validate(opath)
        if not existing_ok:
            opath.unlink()
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk-id")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not key_ok():
        print("ERROR: DEEPSEEK_API_KEY missing", file=sys.stderr)
        return 3

    ids = [args.chunk_id] if args.chunk_id else [
        "shiji-chunk-" + str(n).zfill(4) for n in range(args.start, args.start + args.limit)]

    current_fail = 0
    for cid in ids:
        ok = generate_one(cid, args.max_retries, args.force)
        update_status(cid, ok)
        if not ok:
            current_fail += 1

    print("\nDone. ok=" + str(len(ids) - current_fail) + " fail=" + str(current_fail))
    return 0 if current_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
