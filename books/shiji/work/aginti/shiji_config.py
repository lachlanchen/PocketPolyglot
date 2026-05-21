#!/usr/bin/env python3
"""Shared configuration and quality-check functions for the Shiji pipeline.

This module replaces hard-coded marker lists and duplicate functions in
generate_chunk.py and validate_shiji_chunk.py. All project-specific
language quality checks, kanji reading overrides, and grammar role
definitions live here, driven by source-audit.json where appropriate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex constants (generic language tools, not project-specific)
# ---------------------------------------------------------------------------
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
SPACE_RE = re.compile(r"\s+")

# ---------------------------------------------------------------------------
# Grammar roles (shared across zh and ja token validation)
# ---------------------------------------------------------------------------
GRAMMAR_ROLES = frozenset({
    "subject", "predicate", "object", "attributive",
    "adverbial", "complement", "topic", "function",
})

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

# ---------------------------------------------------------------------------
# Japanese reading overrides (project-specific, stored here for single source)
# ---------------------------------------------------------------------------
JP_COMPOUND_READING_OVERRIDES: dict[str, list[str]] = {
    "葷粥": ["くん", "いく"],
    "釜山": ["ふ", "ざん"],
    "涿鹿": ["たく", "ろく"],
    "風后": ["ふう", "こう"],
    "力牧": ["りき", "ぼく"],
    "常先": ["じょう", "せん"],
    "大鴻": ["たい", "こう"],
}

JP_SINGLE_KANJI_READING_OVERRIDES: dict[str, str] = {
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

# ---------------------------------------------------------------------------
# Source audit loader
# ---------------------------------------------------------------------------
_SOURCE_AUDIT_PATH = Path(__file__).resolve().parent / "source-audit.json"


def load_source_audit() -> dict:
    """Load and return the source-audit.json config."""
    if _SOURCE_AUDIT_PATH.exists():
        return json.loads(_SOURCE_AUDIT_PATH.read_text(encoding="utf-8"))
    return {"sources": {}, "target_language_profile": {}}


def get_ja_profile() -> dict:
    """Return the Japanese target-language quality profile from source-audit."""
    audit = load_source_audit()
    return audit.get("target_language_profile", {}).get("ja", {})


def is_ja_source_canonical() -> bool:
    """Return True if the Japanese source is marked as canonical/prose."""
    audit = load_source_audit()
    src = audit.get("sources", {}).get("ja.md", {})
    return src.get("canonical_ja", True)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def token_text(tokens: list[dict]) -> str:
    return "".join(str(tok.get("t", "")) for tok in tokens if isinstance(tok, dict))


def allows_identical_zh_modern(source_text: str) -> bool:
    """Allow unchanged modern Chinese only for short name-list fragments.

    Historical prose sometimes splits a list of names into sentence fragments
    such as 「賈佗；」 or 「先軫；」. Requiring a paraphrase for those fragments
    causes artificial output and repeated retries. Keep this exemption narrow:
    the source must be a semicolon-terminated fragment containing only one to
    four Han characters after punctuation is stripped, and it must not contain
    common classical function words.
    """
    compact = normalize(source_text)
    core = re.sub(r"[，。、；：！？「」『』【】《》（）—…·・\"'\-\.\!\?\;\:\(\)\[\]\s]", "", compact)
    if not (1 <= len(core) <= 4):
        return False
    if not all(HAN_RE.fullmatch(ch) for ch in core):
        return False
    if not compact.endswith(("；", ";")):
        if not compact.endswith(("。", ".")):
            return False
    forbidden = set(
        "曰為为不以而於于之其是有無无毋乃則则者也乎矣焉何"
        "死卒立殺杀伐攻取見见聞闻言至去來来入出走亡得失破敗败勝胜滅灭生使克"
    )
    return not any(ch in forbidden for ch in core)


def _without_protected_marker_compounds(text: str, profile: dict) -> str:
    """Strip allowed proper names/titles before raw Kanbun marker checks."""
    cleaned = text
    defaults = [
        "咸陽",
        "咸有一德",
        "咸有一徳",
        "咸池",
        "巫咸",
        "咸艾",
        "毋丘",
        "弗忌",
        "弗湟",
        "子弗湟",
        "弗父何",
        "差弗",
        "親弗",
        "之罘",
        "馮毋擇",
        "熊毋康",
        "毋康",
        "毋卹",
        "子毋卹",
        "趙毋卹",
        "審食其",
        "酈食其",
        "食其",
        "關其思",
        "釋之",
        "釈之",
        "释之",
        "宮之奇",
        "施之常",
        "樊於期",
        "於期",
        "於陵子仲",
        "商於",
        "商・於",
        "商、於",
        "商，於",
        "商、於、析",
        "於中",
        "大莫敖",
        "莫邪",
        "勇之",
        "廣莫",
        "広莫",
        "廣莫風",
        "広莫風",
        "焉逢",
        "焉逢攝提格",
        "焉逢摂提格",
        "宋毋忌",
    ]
    for value in defaults + list(profile.get("protected_kanbun_marker_compounds", [])):
        compound = normalize(str(value))
        if compound:
            cleaned = cleaned.replace(compound, "")
    return cleaned


def _source_title_marker_compounds(zh_text: str, markers: list[str]) -> set[str]:
    """Find source-side names/titles where a marker-looking character is part of a title.

    Shiji contains official titles such as 贅其侯. The final 其 should not be
    treated as untranslated Kanbun when the generated Japanese retains that
    title. Keep this narrow: only short source substrings that end in an
    official-title suffix are protected.
    """
    title_suffixes = ("侯", "王", "君", "公", "帝", "后", "相", "卿")
    compounds: set[str] = set()
    marker_set = {str(m) for m in markers if str(m)}
    for match in re.finditer(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", normalize(zh_text)):
        segment = match.group(0)
        length = len(segment)
        for start in range(length):
            stop_max = min(length, start + 6)
            for stop in range(start + 2, stop_max + 1):
                value = segment[start:stop]
                if not value.endswith(title_suffixes):
                    continue
                if any(marker in value for marker in marker_set):
                    compounds.add(value)
    return compounds


def _without_source_title_marker_compounds(text: str, zh_text: str, markers: list[str]) -> str:
    cleaned = text
    for compound in sorted(_source_title_marker_compounds(zh_text, markers), key=len, reverse=True):
        cleaned = cleaned.replace(compound, "")
    return cleaned


def _without_contextual_marker_names(text: str, zh_text: str, profile: dict) -> str:
    """Strip one-character marker-looking names only in configured source contexts."""
    cleaned = text
    zh_norm = normalize(zh_text)
    defaults = [
        {
            "marker": "咸",
            "source_contains": ["于咸", "於咸"],
            "ja_terms": ["咸"],
        },
        {
            "marker": "之",
            "source_contains": [
                "相子之",
                "與子之交",
                "与子之交",
                "子之相燕",
                "尊子之",
                "信子之",
                "子之因",
                "讓相子之",
                "让相子之",
                "讓於子之",
                "让于子之",
                "子之必",
                "子之之心",
                "捐子之之心",
                "屬國於子之",
                "属国于子之",
                "子之大",
                "屬子之",
                "属子之",
                "效之子之",
                "子之南面",
                "決於子之",
                "决于子之",
                "攻子之",
                "燕子之亡",
                "燕相子之",
                "字子之",
                "任子之",
                "子之之亂",
                "子之之乱",
                "殺王噲、子之",
                "杀王哙、子之",
            ],
            "ja_terms": ["子之"],
        },
        {
            "marker": "莫",
            "source_contains": ["其子莫及平夏"],
            "ja_terms": ["莫"],
        },
        {
            "marker": "於",
            "source_contains": ["商、於、析", "商，於，析", "曲沃、於中"],
            "ja_terms": ["於"],
        },
    ]
    for item in defaults + list(profile.get("protected_marker_name_contexts", [])):
        marker = normalize(str(item.get("marker", "")))
        if not marker:
            continue
        contexts = [normalize(str(value)) for value in item.get("source_contains", [])]
        if not any(value and value in zh_norm for value in contexts):
            continue
        for term in item.get("ja_terms", [marker]):
            term_norm = normalize(str(term))
            if term_norm:
                cleaned = cleaned.replace(term_norm, "")
    return cleaned


def _has_forbidden_kanbun_pattern(text: str, pattern: str) -> bool:
    """Return True when a configured Kanbun pattern is really suspicious.

    The broad patterns 者、/者， catch copied Kanbun, but modern Japanese can
    legitimately contain kana-led phrases such as 「王となった者、」. Treat those
    as Japanese, while still rejecting bare Hanzi compounds like 「王者、」.
    """
    if pattern not in {"者、", "者，"}:
        return pattern in text

    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx < 0:
            return False
        prev = text[idx - 1] if idx > 0 else ""
        if not prev or not KANA_RE.fullmatch(prev):
            return True
        start = idx + len(pattern)


def _looks_like_name_title_list(text: str, profile: dict) -> bool:
    """Detect long official-title/person-name enumerations in Shiji prose."""
    source = normalize(text)
    han_count = len(HAN_RE.findall(source))
    list_marks = source.count("、") + source.count("，") + source.count(",")
    terms = profile.get(
        "name_list_terms",
        ["侯", "丞相", "卿", "大夫", "將軍", "御史", "廷尉", "博士"],
    )
    term_hits = sum(source.count(str(term)) for term in terms)
    return han_count >= 30 and list_marks >= 4 and term_hits >= 2


# ---------------------------------------------------------------------------
# Japanese quality checks (config-driven, not hard-coded marker lists)
# ---------------------------------------------------------------------------
def looks_like_real_japanese_reference(text: str) -> bool:
    """Heuristic: does this reference excerpt read like real Japanese prose?"""
    compact = normalize(text)
    if len(compact) < 20:
        return False
    # Filter known boilerplate
    if "パブリックドメイン" in compact or "この作品" in compact:
        return False
    kana_count = len(KANA_RE.findall(compact))
    han_count = len(HAN_RE.findall(compact))
    profile = get_ja_profile()
    min_kana = profile.get("min_context_kana_count", 6)
    return kana_count >= min_kana and han_count > 0


def ja_quality_error(ja_text: str, zh_original_text: str) -> str:
    """Check Japanese quality against config-driven Kanbun markers.

    Returns an error string if the Japanese looks like Kanbun/classical
    Chinese rather than modern Japanese prose, or empty string if OK.
    """
    ja_norm = normalize(ja_text)
    zh_norm = normalize(zh_original_text)
    source_han_count = len(HAN_RE.findall(zh_norm))
    if source_han_count == 0:
        return ""

    ja_han_count = len(HAN_RE.findall(ja_norm))
    ja_kana_count = len(KANA_RE.findall(ja_norm))
    profile = get_ja_profile()
    is_name_list = _looks_like_name_title_list(zh_norm, profile)
    min_kana_ratio = profile.get(
        "min_name_list_kana_ratio" if is_name_list else "min_kana_ratio",
        0.035 if is_name_list else 0.08,
    )
    min_kana_short = profile.get("min_kana_count_for_short", 2)
    kanbun_markers = profile.get("kanbun_markers", [])
    kanbun_patterns = profile.get("kanbun_patterns", [])

    if allows_identical_zh_modern(zh_original_text) and ja_norm == zh_norm:
        return ""
    if ja_norm == zh_norm:
        return "ja is identical to zh_original; write real Japanese, not copied classical Chinese"
    if ja_han_count >= 2 and ja_kana_count == 0:
        return "ja has Han characters but no kana; write real Japanese prose with kana, particles, and okurigana"
    if is_name_list and ja_kana_count < profile.get("min_name_list_kana_count", 6):
        return "ja title/name list lacks enough Japanese frame words; keep names but add particles and a predicate"
    if source_han_count >= 6 and ja_kana_count < min_kana_short:
        return "ja has too little kana for a real Japanese sentence; rewrite as readable Japanese, not Kanbun"
    if source_han_count >= 10 and len(ja_norm) and (ja_kana_count / len(ja_norm)) < min_kana_ratio:
        return "ja is still too Kanbun-like; rewrite as natural Japanese with particles and inflected endings"

    marker_scan_text = _without_protected_marker_compounds(ja_norm, profile)
    marker_scan_text = _without_source_title_marker_compounds(marker_scan_text, zh_norm, kanbun_markers)
    marker_scan_text = _without_contextual_marker_names(marker_scan_text, zh_norm, profile)
    for marker in kanbun_markers:
        if marker in marker_scan_text:
            return f"ja contains raw Kanbun marker '{marker}'; translate it into modern Japanese wording"
    for pattern in kanbun_patterns:
        if _has_forbidden_kanbun_pattern(ja_norm, pattern):
            return f"ja contains Kanbun pattern '{pattern}'; rewrite with Japanese は/とは wording"

    return ""


# ---------------------------------------------------------------------------
# Grammar role resolver
# ---------------------------------------------------------------------------
def resolve_role(value: str, default: str = "function") -> str:
    role = str(value or "").strip().lower().replace("-", "_")
    role = ROLE_ALIASES.get(role, role)
    return role if role in GRAMMAR_ROLES else default
