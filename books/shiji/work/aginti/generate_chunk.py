#!/usr/bin/env python3
"""Resumable DeepSeek writer for three-layer classical Chinese chunks.

Reads chunks.jsonl line by line, calls DeepSeek API, validates output,
retries on failure, writes to data/interlinear/shiji-aginti/chunks/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pypinyin import Style, lazy_pinyin

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
MODE = "zh_classical_three_layer"

VALIDATOR = str(Path(__file__).resolve().parent / "validate_shiji_chunk.py")
OUT_DIR = Path("data/interlinear/shiji-aginti/chunks")
LOG_DIR = Path("books/shiji/work/aginti/logs")
STATUS = Path("books/shiji/work/aginti/pilot_status.json")
JSONL = Path("books/shiji/work/bilingual/chunks/chunks.jsonl")

JSON_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？；])')
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
ALL_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$")
MISSING_JA_READING_RE = re.compile(r"kanji '([^']+)' needs furigana")
PUNCT_RE = re.compile(r"^[，。、；：！？「」『』【】《》（）—…·・\"'\\-\\.\\!\\?\\;\\:\\(\\)\\[\\]\\s]+$")
GRAMMAR_ROLES = {
    "subject", "predicate", "object", "attributive",
    "adverbial", "complement", "topic", "function",
}
ROLE_ALIASES = {
    "conjunction": "function",
    "preposition": "function",
    "particle": "function",
    "auxiliary": "function",
    "modal": "function",
    "marker": "function",
    "copula": "predicate",
    "verb": "predicate",
    "adjective": "predicate",
    "adverb": "adverbial",
    "noun": "object",
    "name": "object",
    "proper_noun": "object",
    "proper noun": "object",
}
JP_COMPOUND_READING_OVERRIDES = {
    "葷粥": ["くん", "いく"],
    "釜山": ["ふ", "ざん"],
    "涿鹿": ["たく", "ろく"],
    "風后": ["ふう", "こう"],
    "力牧": ["りき", "ぼく"],
    "常先": ["じょう", "せん"],
    "大鴻": ["たい", "こう"],
}
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


def _split_sentences(text: str) -> list[str]:
    """Split text while keeping closing quotes with the sentence."""
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
                out.append(sentence)
            buf.clear()
            i = j
            continue
        i += 1
    rest = "".join(buf).strip()
    if rest:
        out.append(rest)
    return out


def _token_text(tokens: list[dict]) -> str:
    return "".join(str(tok.get("t", "")) for tok in tokens if isinstance(tok, dict))


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _ja_quality_error(ja_text: str, zh_original_text: str) -> str:
    ja_norm = _norm_text(ja_text)
    zh_norm = _norm_text(zh_original_text)
    if not HAN_RE.search(zh_norm):
        return ""
    ja_han_count = len(HAN_RE.findall(ja_norm))
    if ja_norm == zh_norm:
        return "ja is identical to zh_original; write real Japanese, not copied classical Chinese"
    if ja_han_count >= 5 and not KANA_RE.search(ja_norm):
        return "ja has Han characters but no kana; write Japanese kundoku/translation with kana and okurigana"
    return ""


def _role(value: str, default: str = "function") -> str:
    role = str(value or "").strip().lower().replace("-", "_")
    role = ROLE_ALIASES.get(role, role)
    return role if role in GRAMMAR_ROLES else default


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
    body = json.dumps({"model": MODEL, "messages": messages,
                       "temperature": temp, "max_tokens": 8192}).encode()
    req = urllib.request.Request(DEEPSEEK_URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + k,
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        b = e.read().decode(errors="replace")
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
    """Build a per-sentence prompt with trimmed Japanese reference (~1000 chars)."""
    jp_excerpt = ""
    for r in jp_refs:
        txt = r.get("text", "")
        if len(jp_excerpt) + len(txt) + 1 > 1200:
            remaining = 1000 - len(jp_excerpt)
            if remaining > 40:
                jp_excerpt += txt[:remaining] + "\n"
            break
        jp_excerpt += txt + "\n"
    if len(jp_excerpt) > 1200:
        jp_excerpt = jp_excerpt[:1200] + "..."

    sysmsg = (
        "You are a classical Chinese linguistics expert producing JSON for Sima Qian's 史記. "
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
        '  "ja": [{"t": text, "r": furigana, "g": role}] — Japanese correspondence, FLAT token list (NOT nested). '
        "Every kanji is single-char with furigana. Kana tokens must have r=\"\".\n"
        '  "zh_modern": [{"t": char, "r": pinyin, "g": role}] — MODERN Chinese paraphrase. Every Hanzi single-char with pinyin. '
        "MUST DIFFER from zh_original text.\n\n"
        "ALLOWED GRAMMAR ROLES (use ONLY these):\n"
        "- subject predicate object attributive adverbial complement topic function\n"
        "DO NOT use: conjunction, auxiliary, particle, or any other role.\n\n"
        "RULES:\n"
        "- zh_original joined MUST exactly reconstruct source_text (whitespace-insensitive).\n"
        "- zh_modern is a MODERN Chinese explanation/paraphrase in your OWN words.\n"
        "- ja is actual Japanese kundoku/translation, not copied Chinese/Kanbun source text. "
        "The reference may itself be classical Chinese hosted on Japanese Wikisource; use it only as alignment help.\n"
        "- For real text sentences, ja MUST contain Japanese kana/okurigana/particles. "
        "Do not output all-kanji/all-Hanzi Japanese except for punctuation-only units.\n"
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

    user = (
        "Tokenize this classical Chinese sentence from 史記:\n\n"
        "Section: " + section_title + " (" + section_id + ")\n"
        "Paragraph: " + paragraph_id + "\n"
        "Sentence:\n" + sentence_text + "\n\n"
        "Japanese reference:\n" + jp_excerpt + "\n\n"
        "Output JSON with source_text, zh_original, ja (flat), zh_modern for this one sentence only.\n"
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
            if HAN_RE.search(zt) and zmt == zt:
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

    st = load_status()
    ids = [args.chunk_id] if args.chunk_id else [
        "shiji-chunk-" + str(n).zfill(4) for n in range(args.start, args.start + args.limit)]

    current_fail = 0
    for cid in ids:
        was_ok = bool(st.get("chunks", {}).get(cid, {}).get("ok"))
        ok = generate_one(cid, args.max_retries, args.force)
        st["chunks"][cid] = {"ok": ok, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if ok and not was_ok:
            st["generated"] = st.get("generated", 0) + 1
        else:
            if not ok:
                st["failed"] = st.get("failed", 0) + 1
                current_fail += 1
        save_status(st)

    print("\nDone. ok=" + str(len(ids) - current_fail) + " fail=" + str(current_fail))
    return 0 if current_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
