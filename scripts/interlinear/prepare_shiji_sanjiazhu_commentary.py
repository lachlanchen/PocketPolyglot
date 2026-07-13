#!/usr/bin/env python3
"""Extract and conservatively align public-domain Shiji commentaries.

The completed Shiji language JSON remains immutable. This script writes an
additive sidecar keyed by chunk/paragraph/unit coordinates. Only exact anchor
matches are promoted; unresolved notes are retained in a review queue.
"""

from __future__ import annotations

import argparse
import json
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup, NavigableString, Tag
from opencc import OpenCC
from pypinyin import Style, lazy_pinyin


ROOT = Path(__file__).resolve().parents[2]
COMMENT_LABELS = {"集解", "索隱", "正義", "索隱述贊", "注"}
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SPACE_RE = re.compile(r"\s+")
T2S = OpenCC("t2s")


@dataclass(frozen=True)
class UnitRef:
    chunk_id: str
    section_id: str
    paragraph_index: int
    unit_index: int
    source_text: str
    normalized: str

    @property
    def key(self) -> str:
        return f"{self.chunk_id}#p{self.paragraph_index:04d}#u{self.unit_index:04d}"


def normalized_anchor(text: str) -> str:
    simplified = T2S.convert(str(text or ""))
    return "".join(ch for ch in simplified if CJK_RE.match(ch))


def clean_text(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("〈", "").replace("〉", "")).strip()


def tokenize_zh(text: str) -> list[dict[str, str]]:
    readings = iter(lazy_pinyin(text, style=Style.TONE, errors=lambda item: list(item)))
    tokens: list[dict[str, str]] = []
    for char in text:
        token = {"t": char}
        reading = next(readings, "")
        if CJK_RE.match(char) and reading and reading != char:
            token["r"] = reading
        tokens.append(token)
    return tokens


def badge_spans(small: Tag) -> list[Tag]:
    result: list[Tag] = []
    for span in small.find_all("span"):
        label = clean_text(span.get_text("", strip=True))
        style = str(span.get("style", "")).lower()
        if label in COMMENT_LABELS and "background-color" in style:
            result.append(span)
    return result


def text_after_badge(badge: Tag, small: Tag, stop_badges: set[int]) -> str:
    pieces: list[str] = []
    for node in badge.next_elements:
        parent = node.parent if isinstance(node, (Tag, NavigableString)) else None
        ancestors = list(parent.parents) if isinstance(parent, Tag) else []
        if parent is not small and small not in ancestors:
            break
        if isinstance(node, Tag) and id(node) in stop_badges:
            break
        if isinstance(node, NavigableString):
            parent = node.parent
            if parent is badge or (isinstance(parent, Tag) and parent.find_parent() is badge):
                continue
            if isinstance(parent, Tag):
                style = str(parent.get("style", "")).replace(" ", "").lower()
                if "color:transparent" in style or "font-size:0px" in style:
                    continue
            pieces.append(str(node))
    return clean_text("".join(pieces))


def sibling_text(nodes: Iterable[Any]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, Tag) and node.name != "small":
            parts.append(node.get_text("", strip=False))
    return clean_text("".join(parts))


def nearby_document_text(small: Tag, *, previous: bool, limit: int = 96) -> str:
    iterator = small.previous_elements if previous else small.next_elements
    pieces: list[str] = []
    normalized_length = 0
    for node in iterator:
        if not isinstance(node, NavigableString):
            continue
        parent = node.parent
        if not isinstance(parent, Tag) or parent.name in {"script", "style"}:
            continue
        ancestors = list(parent.parents)
        if parent is small or small in ancestors:
            continue
        style = str(parent.get("style", "")).replace(" ", "").lower()
        if "color:transparent" in style or "font-size:0px" in style:
            continue
        piece = clean_text(str(node))
        if not piece:
            continue
        pieces.append(piece)
        normalized_length += len(normalized_anchor(piece))
        if normalized_length >= limit:
            break
    if previous:
        pieces.reverse()
    return clean_text("".join(pieces))


def extract_html_notes(path: Path) -> list[dict[str, Any]]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    records: list[dict[str, Any]] = []
    for container in soup.find_all(["p", "dd"]):
        smalls = [
            item
            for item in container.find_all("small")
            if item.find_parent(["p", "dd"]) is container
        ]
        for small in smalls:
            badges = badge_spans(small)
            if not badges:
                continue
            children = list(container.children)
            direct = small
            while direct.parent is not container and direct.parent is not None:
                direct = direct.parent
            try:
                index = children.index(direct)
            except ValueError:
                index = 0
            before = sibling_text(children[:index])
            after = sibling_text(children[index + 1 :])
            if not normalized_anchor(before):
                before = nearby_document_text(small, previous=True)
            if not normalized_anchor(after):
                after = nearby_document_text(small, previous=False)
            stops = {id(item) for item in badges}
            for badge in badges:
                label = clean_text(badge.get_text("", strip=True))
                commentary = text_after_badge(badge, small, stops)
                if not commentary or commentary == label:
                    continue
                records.append(
                    {
                        "source_page": path.stem,
                        "source_section": clean_text(
                            (soup.find(["h2", "h3"]).get_text("", strip=True) if soup.find(["h2", "h3"]) else "")
                        ),
                        "label": label,
                        "text": commentary,
                        "anchor_before": normalized_anchor(before)[-32:],
                        "anchor_after": normalized_anchor(after)[:32],
                    }
                )
    return records


def chunk_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def load_units(chunk_dir: Path) -> list[UnitRef]:
    units: list[UnitRef] = []
    for path in sorted(chunk_dir.glob("*.json"), key=chunk_number):
        data = json.loads(path.read_text(encoding="utf-8"))
        chunk_id = str(data.get("chunk_id") or path.stem)
        section_id = str(data.get("section", {}).get("id") or "")
        for paragraph_index, paragraph in enumerate(data.get("paragraphs", [])):
            for unit_index, unit in enumerate(paragraph.get("units", [])):
                source = str(unit.get("source_text") or unit.get("source_wenyan") or "")
                normalized = normalized_anchor(source)
                if normalized:
                    units.append(UnitRef(chunk_id, section_id, paragraph_index, unit_index, source, normalized))
    return units


def build_stream(units: list[UnitRef]) -> tuple[str, list[int]]:
    ends: list[int] = []
    parts: list[str] = []
    cursor = 0
    for unit in units:
        parts.append(unit.normalized)
        cursor += len(unit.normalized)
        ends.append(cursor)
    return "".join(parts), ends


def section_ranges(units: list[UnitRef], ends: list[int]) -> dict[str, tuple[int, int]]:
    ranges: dict[str, tuple[int, int]] = {}
    for index, unit in enumerate(units):
        key = normalized_anchor(unit.section_id)
        if not key:
            continue
        start = ends[index - 1] if index else 0
        if key not in ranges:
            ranges[key] = (start, ends[index])
        else:
            ranges[key] = (ranges[key][0], ends[index])
    return ranges


def matching_section_range(
    source_section: str,
    ranges: dict[str, tuple[int, int]],
) -> tuple[int, int] | None:
    source = normalized_anchor(source_section)
    candidates = [
        (key, bounds)
        for key, bounds in ranges.items()
        if len(key) >= 2 and (source.startswith(key) or key.startswith(source))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    return candidates[0][1]


def find_unique_in_range(
    stream: str,
    anchor: str,
    bounds: tuple[int, int],
    *,
    from_end: bool,
) -> tuple[int, int]:
    start, end = bounds
    window = stream[start:end]
    for length in (32, 24, 18, 12):
        needle = anchor[-length:] if from_end else anchor[:length]
        if len(needle) < length:
            continue
        first = window.find(needle)
        if first >= 0 and window.find(needle, first + 1) < 0:
            return start + first, length
    return -1, 0


def find_anchor(
    stream: str,
    anchor: str,
    cursor: int,
    *,
    from_end: bool = True,
) -> tuple[int, int, str]:
    for length in (32, 24, 18, 12):
        needle = anchor[-length:] if from_end else anchor[:length]
        if len(needle) < length:
            continue
        position = stream.find(needle, max(0, cursor - 1000))
        if position >= 0:
            return position, length, "sequential"
        first = stream.find(needle)
        if first >= 0 and stream.find(needle, first + 1) < 0:
            return first, length, "globally_unique"
    return -1, 0, "unmatched"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", default="data/interlinear/shiji-aginti/chunks")
    parser.add_argument(
        "--html-dir",
        default="sources/shiji/commentaries/wikisource-combined/wikisource/html",
    )
    parser.add_argument(
        "--output",
        default="books/shiji-sanjiazhu-comment-aware/work/commentary/commentary-sidecar.jsonl",
    )
    parser.add_argument(
        "--report",
        default="books/shiji-sanjiazhu-comment-aware/work/commentary/alignment-report.json",
    )
    parser.add_argument(
        "--unmatched",
        default="books/shiji-sanjiazhu-comment-aware/work/commentary/unmatched-review.jsonl",
    )
    parser.add_argument("--page-limit", type=int, default=0)
    args = parser.parse_args()

    units = load_units(ROOT / args.chunk_dir)
    stream, ends = build_stream(units)
    ranges = section_ranges(units, ends)
    html_paths = sorted((ROOT / args.html_dir).glob("*.html"))
    if args.page_limit:
        html_paths = html_paths[: args.page_limit]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    cursor = 0
    extracted = 0
    for html_path in html_paths:
        for record in extract_html_notes(html_path):
            extracted += 1
            position, anchor_length, scope = find_anchor(stream, record["anchor_before"], cursor)
            method = "anchor_before"
            if position >= 0:
                target_offset = position + anchor_length
            else:
                after = record["anchor_after"]
                position, anchor_length, scope = find_anchor(stream, after, cursor, from_end=False)
                target_offset = position if position >= 0 else -1
                method = "anchor_after" if position >= 0 else "unmatched"
            if position < 0:
                bounds = matching_section_range(record.get("source_section", ""), ranges)
                if bounds:
                    position, anchor_length = find_unique_in_range(
                        stream,
                        record["anchor_before"],
                        bounds,
                        from_end=True,
                    )
                    if position >= 0:
                        target_offset = position + anchor_length
                        method = "section_anchor_before"
                        scope = "section_unique"
                    else:
                        position, anchor_length = find_unique_in_range(
                            stream,
                            record["anchor_after"],
                            bounds,
                            from_end=False,
                        )
                        if position >= 0:
                            target_offset = position
                            method = "section_anchor_after"
                            scope = "section_unique"
            if position < 0:
                unmatched.append(record)
                counts["unmatched"] += 1
                continue
            unit_index = min(bisect_right(ends, target_offset), len(units) - 1)
            unit = units[unit_index]
            cursor = max(cursor, position)
            note = {
                "label": record["label"],
                "text": record["text"],
                "tokens": tokenize_zh(record["text"]),
                "source_page": record["source_page"],
                "alignment": {
                    "method": method,
                    "scope": scope,
                    "anchor_length": anchor_length,
                    "confidence": 1.0 if anchor_length >= 24 else 0.94,
                },
            }
            grouped[unit.key].append(note)
            counts[record["label"]] += 1
            counts["matched"] += 1

    output = ROOT / args.output
    report_path = ROOT / args.report
    unmatched_path = ROOT / args.unmatched
    for path in (output, report_path, unmatched_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for key, notes in grouped.items():
            handle.write(json.dumps({"key": key, "notes": notes}, ensure_ascii=False) + "\n")
    with unmatched_path.open("w", encoding="utf-8") as handle:
        for record in unmatched:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {
        "schema_version": 1,
        "book_id": "shiji-sanjiazhu-comment-aware",
        "html_pages": len(html_paths),
        "base_units": len(units),
        "extracted_notes": extracted,
        "matched_notes": counts["matched"],
        "unmatched_notes": counts["unmatched"],
        "matched_ratio": round(counts["matched"] / extracted, 6) if extracted else 0,
        "label_counts": {label: counts[label] for label in sorted(COMMENT_LABELS)},
        "sidecar_records": len(grouped),
        "policy": "exact anchors only; unmatched notes are never guessed",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
