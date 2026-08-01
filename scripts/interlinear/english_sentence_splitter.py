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
    "ed",
    "eds",
    "e",
    "eg",
    "etc",
    "fig",
    "ff",
    "gen",
    "gov",
    "hon",
    "i",
    "ibid",
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
    "p",
    "pp",
    "prof",
    "rep",
    "rev",
    "sen",
    "sgt",
    "sr",
    "st",
    "trans",
    "vol",
    "vols",
    "vs",
}

SCHOLARLY_ABBREVIATION_RE = re.compile(
    r"(?:\b(?:s\s*\.\s*v|op\s*\.\s*cit|loc\s*\.\s*cit)\.)$",
    re.IGNORECASE,
)


def is_abbreviation_boundary(text: str, end: int) -> bool:
    """Return true when a regex boundary is only an abbreviation like ``Mr.``."""
    before = text[:end].rstrip()
    before = re.sub(r'["”’)\]}]+$', "", before).rstrip()
    if SCHOLARLY_ABBREVIATION_RE.search(before):
        return True
    # ``s. v.`` (sub voce) is often spaced by PDF cleanup.  The regex sees
    # each dot independently, so protect both the ``s.`` and ``v.`` boundary.
    if re.search(r"\bs\.$", before, re.IGNORECASE):
        after = text[end:].lstrip()
        if re.match(r"v\.", after, re.IGNORECASE):
            return True
    if re.search(r"\bs\.\s*v\.$", before, re.IGNORECASE):
        return True
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
