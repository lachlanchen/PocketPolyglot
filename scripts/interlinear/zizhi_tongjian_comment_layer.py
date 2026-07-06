#!/usr/bin/env python3
"""Build and consume comment-aware spans for the annotated Zizhi Tongjian.

The source PDF keeps Sima Guang's main chronicle text in a larger font and Hu
Sanxing/commentary/pronunciation text in a smaller font.  This module aligns the
existing generated JSON back to that PDF font stream so the derived PDF can mark
comments without regenerating any language JSON.
"""

from __future__ import annotations

import html
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


COMMENT = "comment"
MAIN = "main"
PRONUNCIATION = "pronunciation"
UNKNOWN = "unknown"

SPACE_RE = re.compile(r"\s+")
PRONUNCIATION_RE = re.compile(r"(?:翻|音|切|讀曰|读曰|叶|韻|反切|如字)")
APPARATUS_RE = re.compile(r"[『「]?(?:章|乙|甲|孔本|退齋|校|鄒)[:：]")
BOOK_NOTE_RE = re.compile(r"^[《『][^》』]{1,40}[》』](?:曰|云|：|:)")
LEADING_ENTRY_NUMBER_RE = re.compile(r"^([0-9０-９]{1,3}\s+)(.*)$", re.DOTALL)
APPARATUS_START_RE = re.compile(
    r"^\s*(?:[『「]?(?:章|鄒)[:：]|[甲乙丙丁][一二三四五六七八九十百]+行本|"
    r"張校|.*(?:十一|十二|十五)行本(?:同|正|有|作)|.*本同[；。]?$)"
)
MIXED_PRONUNCIATION_RE = re.compile(
    r"\s[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{1,8}[，,]"
    r"[^。；;]{0,40}(?:翻|音|切|讀曰|读曰|如字)"
)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str
    confidence: float
    method: str


def no_space(text: str) -> str:
    return "".join(str(text or "").split())


def normalize_kind(kind: str, text: str) -> str:
    if kind != COMMENT:
        return kind
    stripped = SPACE_RE.sub("", text)
    if stripped and len(stripped) <= 28 and PRONUNCIATION_RE.search(stripped):
        return PRONUNCIATION
    if stripped and len(stripped) <= 48 and APPARATUS_RE.search(stripped):
        return COMMENT
    return COMMENT


def coalesce_spans(kinds: list[str], *, method: str, confidence: float) -> list[Span]:
    if not kinds:
        return []
    spans: list[Span] = []
    start = 0
    current = kinds[0]
    for index, kind in enumerate(kinds[1:], start=1):
        if kind == current:
            continue
        spans.append(Span(start, index, current, confidence, method))
        start = index
        current = kind
    spans.append(Span(start, len(kinds), current, confidence, method))
    return spans


def spans_to_json(spans: Iterable[Span], source_text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for span in spans:
        text = source_text[span.start : span.end]
        kind = normalize_kind(span.kind, text)
        result.append(
            {
                "start": span.start,
                "end": span.end,
                "kind": kind,
                "confidence": round(span.confidence, 6),
                "method": span.method,
                "sample": text[:80],
            }
        )
    return result


def json_to_spans(items: list[dict[str, Any]]) -> list[Span]:
    spans: list[Span] = []
    for item in items:
        spans.append(
            Span(
                int(item["start"]),
                int(item["end"]),
                str(item["kind"]),
                float(item.get("confidence", 1.0)),
                str(item.get("method", "sidecar")),
            )
        )
    return spans


class PdfFontStream:
    """A normalized char stream with one main/comment kind per source char."""

    def __init__(self, chars: list[str], kinds: list[str]) -> None:
        self.chars = chars
        self.kinds = kinds
        self.text = "".join(chars)

    @staticmethod
    def ensure_xml(pdf_path: Path, xml_path: Path) -> None:
        if xml_path.exists() and xml_path.stat().st_size > 0:
            return
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = xml_path.with_suffix("")
        subprocess.run(
            ["pdftohtml", "-xml", "-i", str(pdf_path), str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    @classmethod
    def from_pdf_xml(cls, xml_path: Path, *, main_font_threshold: int = 20) -> "PdfFontStream":
        font_sizes: dict[str, int] = {}
        chars: list[str] = []
        kinds: list[str] = []
        for _event, elem in ET.iterparse(xml_path, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "fontspec":
                font_id = str(elem.attrib.get("id", ""))
                try:
                    font_sizes[font_id] = int(float(elem.attrib.get("size", "0")))
                except ValueError:
                    font_sizes[font_id] = 0
            elif tag == "text":
                raw = html.unescape("".join(elem.itertext()))
                if raw:
                    font_id = str(elem.attrib.get("font", ""))
                    size = font_sizes.get(font_id, 0)
                    kind = MAIN if size >= main_font_threshold else COMMENT
                    for ch in raw:
                        if ch.isspace():
                            continue
                        chars.append(ch)
                        kinds.append(kind)
            elem.clear()
        return cls(chars, kinds)

    def find(self, needle: str, start: int) -> int:
        return self.text.find(needle, start)

    def find_near(self, needle: str, start: int) -> int:
        pos = self.find(needle, start)
        if pos >= 0:
            return pos
        # Permit a small backwards overlap for chunk boundaries or duplicated
        # page/header text, then fall back to a whole-document search.
        pos = self.text.find(needle, max(0, start - 5000))
        if pos >= 0:
            return pos
        return self.text.find(needle)

    def unit_spans(self, source_text: str, start: int) -> tuple[list[Span], int, str]:
        needle = no_space(source_text)
        if not needle:
            return [Span(0, len(source_text), MAIN, 1.0, "empty")], start, "empty"
        pos = self.find_near(needle, start)
        if pos < 0:
            numbered = LEADING_ENTRY_NUMBER_RE.match(source_text)
            if numbered:
                prefix, rest = numbered.groups()
                rest_needle = no_space(rest)
                rest_pos = self.find_near(rest_needle, start) if rest_needle else -1
                if rest_pos >= 0:
                    rest_kinds = self.kinds[rest_pos : rest_pos + len(rest_needle)]
                    projected = [MAIN] * len(prefix) + project_kinds_to_source(rest, rest_kinds)
                    spans = coalesce_spans(
                        projected,
                        method="pdf-font-align-entry-number",
                        confidence=0.995,
                    )
                    return spans, rest_pos + len(rest_needle), "pdf-font-align-entry-number"
            return heuristic_spans(source_text), start, "heuristic-no-pdf-match"
        matched_kinds = self.kinds[pos : pos + len(needle)]
        source_kinds = project_kinds_to_source(source_text, matched_kinds)
        spans = coalesce_spans(source_kinds, method="pdf-font-align", confidence=1.0)
        return spans, pos + len(needle), "pdf-font-align"


def project_kinds_to_source(source_text: str, compact_kinds: list[str]) -> list[str]:
    kinds = [UNKNOWN] * len(source_text)
    compact_index = 0
    for index, ch in enumerate(source_text):
        if ch.isspace():
            continue
        if compact_index >= len(compact_kinds):
            kinds[index] = MAIN
        else:
            kinds[index] = compact_kinds[compact_index]
        compact_index += 1
    last = MAIN
    for index, kind in enumerate(kinds):
        if kind == UNKNOWN:
            continue
        last = kind
        break
    for index, kind in enumerate(kinds):
        if kind == UNKNOWN:
            kinds[index] = last
        else:
            last = kind
    for index in range(len(kinds) - 1, -1, -1):
        if source_text[index].isspace() and index + 1 < len(kinds):
            kinds[index] = kinds[index + 1]
    return kinds


def heuristic_spans(source_text: str) -> list[Span]:
    """Conservative fallback for rare PDF-alignment misses."""
    text = source_text
    stripped = text.strip()
    if not stripped:
        return [Span(0, len(text), MAIN, 0.3, "heuristic-empty")]
    if APPARATUS_START_RE.search(stripped):
        return [Span(0, len(text), COMMENT, 0.7, "heuristic-apparatus")]
    marker = re.search(r"\s[《『][^》』]{1,40}[》』](?:曰|云|：|:)", text)
    if marker and marker.start() > 0:
        return [
            Span(0, marker.start() + 1, MAIN, 0.58, "heuristic-mixed"),
            Span(marker.start() + 1, len(text), COMMENT, 0.58, "heuristic-mixed"),
        ]
    apparatus = re.search(r"\s[『「]?(?:章|鄒)[:：]", text)
    if apparatus and apparatus.start() > 0:
        return [
            Span(0, apparatus.start() + 1, MAIN, 0.6, "heuristic-mixed-apparatus"),
            Span(apparatus.start() + 1, len(text), COMMENT, 0.6, "heuristic-mixed-apparatus"),
        ]
    pron = MIXED_PRONUNCIATION_RE.search(text)
    if pron and pron.start() > 0:
        return [
            Span(0, pron.start() + 1, MAIN, 0.6, "heuristic-mixed-pronunciation"),
            Span(pron.start() + 1, len(text), PRONUNCIATION, 0.6, "heuristic-mixed-pronunciation"),
        ]
    leading = len(text) - len(text.lstrip())
    if BOOK_NOTE_RE.search(stripped) or PRONUNCIATION_RE.search(stripped):
        return [Span(0, len(text), COMMENT, 0.62, "heuristic-note")]
    if leading and len(stripped) <= 32 and PRONUNCIATION_RE.search(stripped):
        return [Span(0, len(text), PRONUNCIATION, 0.62, "heuristic-pronunciation")]
    if leading:
        return [Span(0, len(text), COMMENT, 0.56, "heuristic-leading-note")]
    return [Span(0, len(text), MAIN, 0.45, "heuristic-main")]


def sidecar_key(paragraph_id: str, unit_index: int) -> str:
    return f"{paragraph_id}#{unit_index:04d}"
