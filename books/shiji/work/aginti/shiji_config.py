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


def _without_protected_marker_compounds(text: str, profile: dict) -> str:
    """Strip allowed proper names/titles before raw Kanbun marker checks."""
    cleaned = text
    defaults = ["咸陽", "咸有一德", "咸有一徳", "巫咸", "咸艾", "弗忌", "差弗", "之罘"]
    for value in defaults + list(profile.get("protected_kanbun_marker_compounds", [])):
        compound = normalize(str(value))
        if compound:
            cleaned = cleaned.replace(compound, "")
    return cleaned


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
    min_kana_ratio = profile.get("min_kana_ratio", 0.08)
    min_kana_short = profile.get("min_kana_count_for_short", 2)
    kanbun_markers = profile.get("kanbun_markers", [])
    kanbun_patterns = profile.get("kanbun_patterns", [])

    if ja_norm == zh_norm:
        return "ja is identical to zh_original; write real Japanese, not copied classical Chinese"
    if ja_han_count >= 2 and ja_kana_count == 0:
        return "ja has Han characters but no kana; write real Japanese prose with kana, particles, and okurigana"
    if source_han_count >= 6 and ja_kana_count < min_kana_short:
        return "ja has too little kana for a real Japanese sentence; rewrite as readable Japanese, not Kanbun"
    if source_han_count >= 10 and len(ja_norm) and (ja_kana_count / len(ja_norm)) < min_kana_ratio:
        return "ja is still too Kanbun-like; rewrite as natural Japanese with particles and inflected endings"

    marker_scan_text = _without_protected_marker_compounds(ja_norm, profile)
    for marker in kanbun_markers:
        if marker in marker_scan_text:
            return f"ja contains raw Kanbun marker '{marker}'; translate it into modern Japanese wording"
    for pattern in kanbun_patterns:
        if pattern in ja_norm:
            return f"ja contains Kanbun pattern '{pattern}'; rewrite with Japanese は/とは wording"

    return ""


# ---------------------------------------------------------------------------
# Grammar role resolver
# ---------------------------------------------------------------------------
def resolve_role(value: str, default: str = "function") -> str:
    role = str(value or "").strip().lower().replace("-", "_")
    role = ROLE_ALIASES.get(role, role)
    return role if role in GRAMMAR_ROLES else default
