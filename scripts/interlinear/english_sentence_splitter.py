#!/usr/bin/env python3
"""English sentence boundary helpers shared by book preparation and writers."""

from __future__ import annotations

import re
from collections.abc import Iterator


EN_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?]["”’)]*\s+')

ABBREVIATION_STEMS = {
    "adm",
    "brig",
    "bros",
    "capt",
    "cmdr",
    "col",
    "corp",
    "dr",
    "e",
    "eg",
    "etc",
    "fig",
    "gen",
    "gov",
    "hon",
    "i",
    "ie",
    "inc",
    "jr",
    "ltd",
    "lt",
    "maj",
    "messrs",
    "miss",
    "mlle",
    "mme",
    "mr",
    "mrs",
    "ms",
    "mt",
    "no",
    "prof",
    "rep",
    "rev",
    "sen",
    "sgt",
    "sr",
    "st",
    "vs",
}


def is_abbreviation_boundary(text: str, end: int) -> bool:
    """Return true when a regex boundary is only an abbreviation like ``Mr.``."""
    before = text[:end].rstrip()
    before = re.sub(r'["”’)\]}]+$', "", before).rstrip()
    if re.search(r"(?:\b[A-Za-z]\.){2,}$", before):
        return True
    match = re.search(r"\b([A-Za-z]{1,12})\.$", before)
    if not match:
        return False
    token = match.group(1)
    stem = token.lower()
    if stem in ABBREVIATION_STEMS:
        return True
    return len(token) == 1 and token.isupper()


def sentence_boundary_ends(text: str) -> Iterator[int]:
    """Yield sentence boundary end offsets, skipping common abbreviation dots."""
    for match in EN_SENTENCE_BOUNDARY_RE.finditer(text):
        end = match.end()
        if is_abbreviation_boundary(text, end):
            continue
        yield end
