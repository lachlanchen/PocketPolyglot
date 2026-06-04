#!/usr/bin/env python3
"""Fill missing grammar-color roles in trilingual interlinear chunks.

This is a deterministic completion guard for trilingual books.  The model can
still provide better role labels, but final color builds should not be blocked
or rendered all-black only because a few chunks lack ``g`` fields.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from validate_trilingual_interlinear_json import GRAMMAR_ROLES, validate_chunk


CONTENT_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
WORD_RE = re.compile(r"[A-Za-z0-9]")

FUNCTION_PUNCT = set(" \t\r\n.,;:!?\"'“”‘’()[]{}<>《》〈〉—–-…·・、。，！？；：「」『』（）")

EN_FUNCTION = {
    "and",
    "or",
    "but",
    "nor",
    "so",
    "for",
    "yet",
    "if",
    "because",
    "although",
    "though",
    "while",
    "when",
    "that",
}
EN_SUBJECT_HINTS = {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them"}
EN_AUX_VERBS = {
    "am",
    "are",
    "is",
    "was",
    "were",
    "be",
    "been",
    "being",
    "do",
    "does",
    "did",
    "done",
    "have",
    "has",
    "had",
    "having",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
}
EN_COMMON_VERBS = {
    "said",
    "say",
    "says",
    "go",
    "goes",
    "went",
    "gone",
    "come",
    "came",
    "see",
    "saw",
    "seen",
    "look",
    "looked",
    "think",
    "thought",
    "know",
    "knew",
    "known",
    "tell",
    "told",
    "make",
    "made",
    "take",
    "took",
    "taken",
    "give",
    "gave",
    "given",
    "get",
    "got",
    "love",
    "loved",
    "hate",
    "hated",
    "want",
    "wanted",
    "feel",
    "felt",
    "turn",
    "turned",
    "stand",
    "stood",
    "sit",
    "sat",
    "run",
    "ran",
}
EN_PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "among",
    "around",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "between",
    "by",
    "down",
    "from",
    "in",
    "into",
    "near",
    "of",
    "off",
    "on",
    "over",
    "through",
    "to",
    "under",
    "up",
    "with",
    "without",
}
EN_DETERMINERS = {"a", "an", "the", "this", "that", "these", "those", "my", "your", "his", "her", "its", "our", "their"}

ZH_FUNCTION = set("，。！？；：、“”‘’（）《》〈〉—…")
ZH_ATTRIBUTIVE = set("的")
ZH_ADVERBIAL = set("在从向往到由因因由把被将并也又还都就才只仍仍然忽然已经曾经方")
ZH_PREDICATE = set("是有说看听想知觉感爱恨去来走跑做作使令给拿带问答哭笑叫喊坐站睡醒死活生变成觉记忆望等候")
ZH_COMPLEMENT = set("了着过得完到起下去来住开出入上")

JA_PUNCT = set("、。，．！？；：「」『』（）《》〈〉—…・ ")
JA_SUBJECT_MARKERS = ("は", "が")
JA_OBJECT_MARKERS = ("を",)
JA_ADVERBIAL_MARKERS = ("に", "へ", "で", "から", "まで", "より", "と")
JA_ATTRIBUTIVE_MARKERS = ("の",)
JA_VERBISH_ENDINGS = (
    "た",
    "だ",
    "です",
    "ます",
    "ない",
    "ぬ",
    "れる",
    "られる",
    "せる",
    "させる",
    "う",
    "く",
    "ぐ",
    "す",
    "つ",
    "ぶ",
    "む",
    "る",
)


def is_content(text: str) -> bool:
    return bool(CONTENT_RE.search(text))


def is_punct_or_space(text: str) -> bool:
    return bool(text) and all(ch in FUNCTION_PUNCT for ch in text)


def normalize_role(role: str) -> str:
    role = str(role or "").strip().lower()
    return role if role in GRAMMAR_ROLES else ""


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def content_indices(tokens: list[dict[str, Any]]) -> list[int]:
    return [
        index
        for index, token in enumerate(tokens)
        if isinstance(token, dict) and is_content(str(token.get("t", ""))) and not is_punct_or_space(str(token.get("t", "")))
    ]


def nearest_role(tokens: list[dict[str, Any]], index: int) -> str:
    for neighbor in tokens[index + 1 :]:
        if isinstance(neighbor, dict):
            role = normalize_role(neighbor.get("g", ""))
            if role:
                return role
    for neighbor in reversed(tokens[:index]):
        if isinstance(neighbor, dict):
            role = normalize_role(neighbor.get("g", ""))
            if role:
                return role
    return ""


def wordish(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == "'")


def looks_like_en_predicate(word: str) -> bool:
    return (
        word in EN_AUX_VERBS
        or word in EN_COMMON_VERBS
        or len(word) > 3
        and (word.endswith("ed") or word.endswith("ing"))
    )


def infer_en_roles(tokens: list[dict[str, Any]]) -> dict[int, str]:
    indices = content_indices(tokens)
    words = {index: wordish(str(tokens[index].get("t", ""))) for index in indices}
    first_predicate: int | None = None
    for index in indices:
        if looks_like_en_predicate(words[index]):
            first_predicate = index
            break
    if first_predicate is None and indices:
        first_predicate = indices[min(len(indices) // 2, len(indices) - 1)]

    roles: dict[int, str] = {}
    in_adverbial = False
    for ordinal, index in enumerate(indices):
        word = words[index]
        if not word:
            roles[index] = "function"
        elif word in EN_FUNCTION:
            roles[index] = "function"
            in_adverbial = word in {"if", "when", "while", "because", "although", "though"}
        elif word in EN_PREPOSITIONS:
            roles[index] = "adverbial" if word != "of" else "attributive"
            in_adverbial = word != "of"
        elif first_predicate is not None and index == first_predicate:
            roles[index] = "predicate"
            in_adverbial = False
        elif looks_like_en_predicate(word) and first_predicate is not None and index >= first_predicate:
            roles[index] = "predicate"
            in_adverbial = False
        elif in_adverbial:
            roles[index] = "adverbial"
        elif first_predicate is not None and index < first_predicate:
            roles[index] = "attributive" if word in EN_DETERMINERS and ordinal + 1 < len(indices) else "subject"
        elif word in EN_DETERMINERS:
            roles[index] = "attributive"
        elif word in EN_SUBJECT_HINTS and first_predicate is not None and index < first_predicate:
            roles[index] = "subject"
        else:
            roles[index] = "object" if first_predicate is not None else "topic"
    return roles


def infer_zh_roles(tokens: list[dict[str, Any]]) -> dict[int, str]:
    indices = content_indices(tokens)
    first_predicate: int | None = None
    for index in indices:
        text = str(tokens[index].get("t", ""))
        if text in ZH_PREDICATE:
            first_predicate = index
            break
    if first_predicate is None and indices:
        first_predicate = indices[min(len(indices) // 2, len(indices) - 1)]

    roles: dict[int, str] = {}
    for ordinal, index in enumerate(indices):
        text = str(tokens[index].get("t", ""))
        if text in ZH_FUNCTION:
            roles[index] = "function"
        elif text in ZH_ATTRIBUTIVE:
            roles[index] = nearest_role(tokens, index) or "attributive"
        elif text in ZH_ADVERBIAL:
            roles[index] = "adverbial"
        elif text in ZH_COMPLEMENT:
            roles[index] = "complement" if first_predicate is not None and index >= first_predicate else "predicate"
        elif text in ZH_PREDICATE:
            roles[index] = "predicate"
        elif first_predicate is not None and index < first_predicate:
            roles[index] = "subject" if ordinal < max(2, len(indices) // 5) else "attributive"
        elif first_predicate is not None and index > first_predicate:
            roles[index] = "object"
        else:
            roles[index] = "topic"
    return roles


def infer_ja_role_for_text(text: str, before_predicate: bool, position_ratio: float) -> str:
    if not text or all(ch in JA_PUNCT for ch in text):
        return "function"
    if any(marker in text for marker in JA_SUBJECT_MARKERS):
        return "subject"
    if any(marker in text for marker in JA_OBJECT_MARKERS):
        return "object"
    if any(marker in text for marker in JA_ADVERBIAL_MARKERS):
        return "adverbial"
    if any(marker in text for marker in JA_ATTRIBUTIVE_MARKERS):
        return "attributive"
    if KANA_RE.search(text) and text.endswith(JA_VERBISH_ENDINGS):
        return "predicate"
    if before_predicate:
        return "subject" if position_ratio < 0.24 else "attributive"
    if position_ratio > 0.78:
        return "complement"
    return "object"


def infer_ja_roles(tokens: list[dict[str, Any]]) -> dict[int, str]:
    indices = content_indices(tokens)
    predicate_index: int | None = None
    for index in reversed(indices):
        text = str(tokens[index].get("t", ""))
        if KANA_RE.search(text) and text.endswith(JA_VERBISH_ENDINGS):
            predicate_index = index
            break
    if predicate_index is None and indices:
        predicate_index = indices[-1]
    roles: dict[int, str] = {}
    for ordinal, index in enumerate(indices):
        text = str(tokens[index].get("t", ""))
        ratio = ordinal / max(len(indices) - 1, 1)
        roles[index] = infer_ja_role_for_text(text, predicate_index is None or index < predicate_index, ratio)
    return roles


def infer_roles(tokens: list[dict[str, Any]], lang: str) -> dict[int, str]:
    if lang == "en":
        return infer_en_roles(tokens)
    if lang == "zh":
        return infer_zh_roles(tokens)
    if lang == "ja":
        return infer_ja_roles(tokens)
    return {}


def fill_token_list(tokens: Any, lang: str, *, overwrite_collapsed: bool = False) -> int:
    if not isinstance(tokens, list):
        return 0
    typed_tokens = [token for token in tokens if isinstance(token, dict)]
    inferred = infer_roles(typed_tokens, lang)
    changed = 0
    content = content_indices(typed_tokens)
    existing_roles = [
        normalize_role(typed_tokens[index].get("g", ""))
        for index in content
        if normalize_role(typed_tokens[index].get("g", "")) and normalize_role(typed_tokens[index].get("g", "")) != "function"
    ]
    collapsed = False
    if overwrite_collapsed and len(existing_roles) >= 20:
        dominant = max((existing_roles.count(role), role) for role in set(existing_roles))
        collapsed = dominant[0] / len(existing_roles) >= 0.88

    for index, token in enumerate(typed_tokens):
        text = str(token.get("t", ""))
        role = normalize_role(token.get("g", ""))
        if is_punct_or_space(text):
            if "g" in token and not role:
                token.pop("g", None)
                changed += 1
            continue
        if not is_content(text):
            continue
        if role and not collapsed:
            continue
        new_role = inferred.get(index) or nearest_role(typed_tokens, index) or "function"
        if token.get("g") != new_role:
            token["g"] = new_role
            changed += 1
    return changed


def iter_token_lists(data: Any) -> list[tuple[list[dict[str, Any]], str]]:
    found: list[tuple[list[dict[str, Any]], str]] = []
    if isinstance(data, dict):
        for lang in ("en", "zh", "ja"):
            value = data.get(lang)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                found.append((value, lang))
        for value in data.values():
            found.extend(iter_token_lists(value))
    elif isinstance(data, list):
        for value in data:
            found.extend(iter_token_lists(value))
    return found


def backfill_chunk(data: dict[str, Any], *, overwrite_collapsed: bool = False) -> int:
    changed = 0
    for tokens, lang in iter_token_lists(data):
        changed += fill_token_list(tokens, lang, overwrite_collapsed=overwrite_collapsed)
    return changed


def role_stats(data: dict[str, Any]) -> tuple[int, int, int]:
    content = 0
    with_roles = 0
    colored = 0
    for tokens, _lang in iter_token_lists(data):
        for token in tokens:
            text = str(token.get("t", ""))
            if not is_content(text) or is_punct_or_space(text):
                continue
            content += 1
            role = normalize_role(token.get("g", ""))
            if role:
                with_roles += 1
            if role and role != "function":
                colored += 1
    return content, with_roles, colored


def load_sources(chunks_jsonl: Path) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    with chunks_jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            sources[item["chunk_id"]] = item
    return sources


def process_file(path: Path, source: dict[str, Any] | None, *, overwrite_collapsed: bool, dry_run: bool) -> tuple[int, int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = backfill_chunk(data, overwrite_collapsed=overwrite_collapsed)
    if source is not None:
        errors = validate_chunk(source, data)
        if errors:
            raise ValueError(f"{path}: " + "; ".join(errors[:20]))
    content, with_roles, colored = role_stats(data)
    if changed and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed, with_roles, content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="chunk JSON files or directories")
    parser.add_argument("--chunk-dir", help="directory of chunk JSON files")
    parser.add_argument("--chunks-jsonl", help="source chunks JSONL for validation")
    parser.add_argument("--overwrite-collapsed", action="store_true", help="replace pathological one-color role distributions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths: list[Path] = []
    if args.chunk_dir:
        paths.extend(sorted(Path(args.chunk_dir).glob("*.json")))
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        else:
            paths.append(path)
    if not paths:
        raise SystemExit("No chunk JSON files given")

    sources = load_sources(Path(args.chunks_jsonl)) if args.chunks_jsonl else {}
    changed_files = 0
    changed_tokens = 0
    role_tokens = 0
    total_tokens = 0
    for path in paths:
        source = sources.get(path.stem)
        changed, with_roles, content = process_file(
            path,
            source,
            overwrite_collapsed=args.overwrite_collapsed,
            dry_run=args.dry_run,
        )
        if changed:
            changed_files += 1
            changed_tokens += changed
        role_tokens += with_roles
        total_tokens += content
    print(
        f"changed_files={changed_files} changed_tokens={changed_tokens} "
        f"grammar_role_tokens={role_tokens}/{total_tokens}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
