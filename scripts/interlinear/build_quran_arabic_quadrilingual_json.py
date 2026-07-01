#!/usr/bin/env python3
"""Build finished Quran Arabic/English/Japanese/Chinese interlinear JSON."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any

from codex_trilingual_plain_json_worker import tokenize_en, tokenize_ja, tokenize_zh


ROOT = Path(__file__).resolve().parents[2]
SPACE_RE = re.compile(r"\s+")
HTML_RE = re.compile(r"<[^>]+>")
FOOTNOTE_MARK_RE = re.compile(r"\[\d+\]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
ARABIC_WORD_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]+")
EN_WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)?")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")

GRAMMAR_ROLES = (
    "topic",
    "subject",
    "predicate",
    "object",
    "attributive",
    "adverbial",
    "complement",
    "function",
)

AR_FUNCTION_WORDS = {
    "و",
    "ف",
    "ثم",
    "أو",
    "بل",
    "لا",
    "ما",
    "من",
    "في",
    "على",
    "إلى",
    "عن",
    "ب",
    "ل",
    "ك",
    "إن",
    "أن",
    "قد",
    "لن",
    "لم",
    "هل",
}
EN_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "not",
    "of",
    "on",
    "or",
    "the",
    "then",
    "to",
    "with",
}
PREDICATE_HINTS = {
    "am",
    "are",
    "be",
    "became",
    "become",
    "created",
    "do",
    "does",
    "did",
    "give",
    "gave",
    "go",
    "guide",
    "have",
    "has",
    "is",
    "make",
    "made",
    "say",
    "said",
    "sent",
    "shall",
    "will",
    "worship",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_translation(text: str) -> str:
    value = str(text or "")
    value = HTML_RE.sub("", value)
    value = FOOTNOTE_MARK_RE.sub("", value)
    value = value.replace("*", "")
    value = value.replace("\u200f", "").replace("\u200e", "")
    value = SPACE_RE.sub(" ", value)
    return value.strip()


def load_quranenc(path: Path) -> dict[tuple[int, int], str]:
    con = sqlite3.connect(path)
    try:
        rows = con.execute("select sura, aya, translation from translations").fetchall()
    finally:
        con.close()
    return {(int(sura), int(aya)): clean_translation(translation) for sura, aya, translation in rows}


def load_qurancom_words(cache_dir: Path) -> dict[tuple[int, int], list[dict[str, str]]]:
    words: dict[tuple[int, int], list[dict[str, str]]] = {}
    for chapter in range(1, 115):
        data = json.loads((cache_dir / f"{chapter:03d}.json").read_text(encoding="utf-8"))
        for verse in data.get("verses") or []:
            key = tuple(int(part) for part in str(verse["verse_key"]).split(":"))
            items: list[dict[str, str]] = []
            for word in verse.get("words") or []:
                if word.get("char_type_name") != "word":
                    continue
                items.append(
                    {
                        "t": str(word.get("text_uthmani") or word.get("text") or ""),
                        "r": clean_translation((word.get("transliteration") or {}).get("text") or ""),
                        "gloss": clean_translation((word.get("translation") or {}).get("text") or ""),
                    }
                )
            words[key] = items
    return words


def normalize_ar_word(text: str) -> str:
    return "".join(ARABIC_WORD_RE.findall(str(text or "")))


def rough_role_for_ar(index: int, total: int, token: dict[str, str]) -> str:
    text = normalize_ar_word(token.get("t", ""))
    gloss = clean_translation(token.get("gloss", "")).lower().strip("()[] ")
    bare = text.lstrip("وف")
    if text in AR_FUNCTION_WORDS or bare in AR_FUNCTION_WORDS:
        return "function"
    if gloss in EN_FUNCTION_WORDS or gloss.startswith(("of ", "to ", "from ", "in ", "with ", "and ")):
        return "function"
    if any(hint in gloss.split() for hint in PREDICATE_HINTS) or text.startswith(("ي", "ت", "ن", "أ")) and total > 2:
        return "predicate"
    if index == 0:
        return "topic" if total > 4 else "subject"
    if index == 1 and total <= 4:
        return "predicate"
    if index >= total - 1 and total > 3:
        return "complement"
    if gloss.startswith(("those", "which", "who", "that")):
        return "attributive"
    return "object" if index > total // 2 else "subject"


def add_roles(tokens: list[dict[str, str]], lang: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    content_indexes = [
        index
        for index, token in enumerate(tokens)
        if (ARABIC_RE.search(token.get("t", "")) if lang == "ar" else EN_WORD_RE.search(token.get("t", "")) if lang == "en" else HAN_RE.search(token.get("t", "")) or KANA_RE.search(token.get("t", "")))
    ]
    rank_by_index = {index: rank for rank, index in enumerate(content_indexes)}
    total = len(content_indexes)
    for index, token in enumerate(tokens):
        item = dict(token)
        text = str(item.get("t", ""))
        if index not in rank_by_index:
            out.append(item)
            continue
        rank = rank_by_index[index]
        if lang == "ar":
            item["g"] = rough_role_for_ar(rank, total, item)
        elif lang == "en":
            word = text.lower().strip("()[]{}.,;:!?")
            if word in EN_FUNCTION_WORDS:
                item["g"] = "function"
            elif word in PREDICATE_HINTS or word.endswith(("ed", "ing")):
                item["g"] = "predicate"
            elif rank == 0:
                item["g"] = "subject"
            elif rank >= total - 2:
                item["g"] = "complement"
            else:
                item["g"] = "object" if rank > total // 2 else "attributive"
        else:
            if text in "，。、；：！？、,.!?;:「」『』（）()[] ":
                pass
            elif rank == 0:
                item["g"] = "topic"
            elif rank == 1:
                item["g"] = "subject"
            elif rank >= total - 2:
                item["g"] = "complement"
            elif text in "是不為为有无ないあるいるするますした":
                item["g"] = "predicate"
            else:
                item["g"] = GRAMMAR_ROLES[(rank % 5) + 1]
        out.append(item)
    return out


def improve_ar_tokens(source_tokens: list[dict[str, str]], quran_words: list[dict[str, str]]) -> list[dict[str, str]]:
    if not source_tokens:
        source_tokens = [{"t": word["t"], "r": word.get("r", "")} for word in quran_words]
    if len(source_tokens) == len(quran_words):
        tokens = [
            {"t": source.get("t", ""), "r": word.get("r") or source.get("r", ""), "gloss": word.get("gloss", "")}
            for source, word in zip(source_tokens, quran_words)
        ]
    else:
        tokens = [
            {"t": source.get("t", ""), "r": source.get("r", ""), "gloss": quran_words[index].get("gloss", "") if index < len(quran_words) else ""}
            for index, source in enumerate(source_tokens)
        ]
    return add_roles(tokens, "ar")


def verse_translation(table: dict[tuple[int, int], str], sura: int, ayah: int) -> str:
    if ayah == 0:
        return table.get((1, 1), "")
    return table.get((sura, ayah), "")


def verse_words(words: dict[tuple[int, int], list[dict[str, str]]], sura: int, ayah: int) -> list[dict[str, str]]:
    if ayah == 0:
        return words.get((1, 1), [])
    return words.get((sura, ayah), [])


def source_title_tokens(chapter: dict[str, Any], lang: str) -> list[dict[str, str]]:
    if lang == "ar":
        return add_roles([{"t": str(chapter.get("chapter_title_ar") or ""), "r": ""}], "ar")
    if lang == "en":
        return add_roles(tokenize_en(str(chapter.get("chapter_title_en") or "")), "en")
    if lang == "ja":
        return add_roles(tokenize_ja(str(chapter.get("chapter_title_ja") or "")), "ja")
    return add_roles(tokenize_zh(str(chapter.get("chapter_title_zh") or "")), "zh")


def build(args: argparse.Namespace) -> dict[str, Any]:
    chunks_jsonl = ROOT / args.chunks_jsonl
    chunk_sources = load_jsonl(chunks_jsonl)
    en = load_quranenc(ROOT / args.english_sqlite)
    ja = load_quranenc(ROOT / args.japanese_sqlite)
    zh = load_quranenc(ROOT / args.chinese_sqlite)
    words = load_qurancom_words(ROOT / args.qurancom_dir)

    canonical_dir = ROOT / args.chunk_dir
    canonical_dir.mkdir(parents=True, exist_ok=True)

    chapters: OrderedDict[str, dict[str, Any]] = OrderedDict()
    total_units = 0
    for source in chunk_sources:
        chapter_id = source["chapter_id"]
        chapter = chapters.setdefault(
            chapter_id,
            {
                "id": chapter_id,
                "number": source["chapter_number"],
                "title": {
                    "ar": source_title_tokens(source, "ar"),
                    "en": source_title_tokens(source, "en"),
                    "ja": source_title_tokens(source, "ja"),
                    "zh": source_title_tokens(source, "zh"),
                },
                "paragraphs": [],
            },
        )
        strict_chunk = {
            "schema_version": "0.1",
            "mode": "arabic_quadrilingual_main",
            "chunk_id": source["chunk_id"],
            "chapter": {
                "id": chapter_id,
                "number": source["chapter_number"],
                "title": chapter["title"],
            },
            "paragraphs": [],
        }
        for paragraph in source.get("paragraphs") or []:
            strict_paragraph = {"id": paragraph["id"], "source_ar": paragraph.get("ar", ""), "units": []}
            for unit in paragraph.get("units") or []:
                sura = int(source["chapter_number"])
                ayah = int(unit.get("ayah", 0))
                ar_tokens = improve_ar_tokens(unit.get("ar_tokens") or [], verse_words(words, sura, ayah))
                en_tokens = add_roles(tokenize_en(verse_translation(en, sura, ayah)), "en")
                ja_tokens = add_roles(tokenize_ja(verse_translation(ja, sura, ayah)), "ja")
                zh_tokens = add_roles(tokenize_zh(verse_translation(zh, sura, ayah)), "zh")
                strict_paragraph["units"].append(
                    {
                        "unit_id": unit["unit_id"],
                        "verse_key": f"{sura}:{ayah}",
                        "ayah": ayah,
                        "source_ar": unit.get("ar", ""),
                        "ar": ar_tokens,
                        "en": en_tokens,
                        "ja": ja_tokens,
                        "zh": zh_tokens,
                    }
                )
                total_units += 1
            strict_chunk["paragraphs"].append(strict_paragraph)
        write_json(canonical_dir / f"{source['chunk_id']}.json", strict_chunk)
        chapter["paragraphs"].extend(strict_chunk["paragraphs"])

    book = {
        "schema_version": "0.1",
        "mode": "arabic_quadrilingual_main",
        "title": {
            "ar": add_roles([{"t": "القرآن الكريم", "r": "al-qur'ān al-karīm"}], "ar"),
            "en": add_roles(tokenize_en("The Quran"), "en"),
            "ja": add_roles(tokenize_ja("クルアーン"), "ja"),
            "zh": add_roles(tokenize_zh("古兰经"), "zh"),
        },
        "source": {
            "note": "Arabic is the source spine. English, Japanese, and Chinese are verse-aligned QuranEnc references. Arabic word ruby/transliteration is from Quran.com word data when available.",
            "chunk_count": len(chunk_sources),
            "chapter_count": len(chapters),
            "unit_count": total_units,
            "translations": {
                "en": "QuranEnc english_rwwad",
                "ja": "QuranEnc japanese_saeedsato",
                "zh": "QuranEnc chinese_makin",
            },
        },
        "chapters": list(chapters.values()),
    }
    write_json(ROOT / args.output, book)
    return book


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", default="books/quran/work/arabic-quadrilingual/chunks/chunks.jsonl")
    parser.add_argument("--qurancom-dir", default="sources/quran/qurancom/verses-by-chapter")
    parser.add_argument("--english-sqlite", default="sources/quran/quranenc/english_rwwad.sqlite")
    parser.add_argument("--japanese-sqlite", default="sources/quran/quranenc/japanese_saeedsato.sqlite")
    parser.add_argument("--chinese-sqlite", default="sources/quran/quranenc/chinese_makin.sqlite")
    parser.add_argument("--chunk-dir", default="books/quran/work/arabic-quadrilingual/interlinear/chunks")
    parser.add_argument("--output", default="books/quran/work/arabic-quadrilingual/preview/quran.full.json")
    args = parser.parse_args()
    book = build(args)
    print(
        f"quran built: chapters={book['source']['chapter_count']} chunks={book['source']['chunk_count']} units={book['source']['unit_count']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
