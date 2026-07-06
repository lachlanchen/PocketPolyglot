#!/usr/bin/env python3
"""Build a comment-span sidecar for the copied Zizhi Tongjian JSON chunks."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zizhi_tongjian_comment_layer import PdfFontStream, sidecar_key, spans_to_json


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def span_text(spans: list[dict[str, Any]], source_text: str) -> str:
    return "".join(source_text[int(span["start"]) : int(span["end"])] for span in spans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--source-pdf", required=True)
    parser.add_argument("--xml-cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--sample-limit", type=int, default=80)
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunks_jsonl = load_jsonl(Path(args.chunks_jsonl))
    selected = {
        item.get("chunk_id") if isinstance(item, dict) else str(item)
        for item in manifest.get("chunks", [])
    }
    chunks_jsonl = [item for item in chunks_jsonl if item.get("chunk_id") in selected]

    xml_cache = Path(args.xml_cache)
    PdfFontStream.ensure_xml(Path(args.source_pdf), xml_cache)
    stream = PdfFontStream.from_pdf_xml(xml_cache)

    out_path = Path(args.output)
    report_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    cursor = 0
    total_units = 0
    failed_reconstruction = 0
    with out_path.open("w", encoding="utf-8") as out:
        for source in chunks_jsonl:
            chunk_id = source["chunk_id"]
            chunk_path = Path(args.chunk_dir) / f"{chunk_id}.json"
            data = load_json(chunk_path)
            for paragraph in data.get("paragraphs", []):
                paragraph_id = str(paragraph.get("id", ""))
                for unit_index, unit in enumerate(paragraph.get("units", [])):
                    source_text = str(unit.get("source_wenyan", ""))
                    spans, cursor, method = stream.unit_spans(source_text, cursor)
                    span_items = spans_to_json(spans, source_text)
                    reconstructed = span_text(span_items, source_text)
                    if reconstructed != source_text:
                        failed_reconstruction += 1
                    methods = {span["method"] for span in span_items}
                    for span in span_items:
                        kind_counts[str(span["kind"])] += int(span["end"]) - int(span["start"])
                    counts[method] += 1
                    if len(span_items) > 1:
                        counts["mixed_units"] += 1
                    if any(str(method).startswith("heuristic") for method in methods):
                        counts["heuristic_units"] += 1
                    record = {
                        "key": sidecar_key(paragraph_id, unit_index),
                        "chunk_id": chunk_id,
                        "paragraph_id": paragraph_id,
                        "unit_index": unit_index,
                        "source_wenyan": source_text,
                        "spans": span_items,
                    }
                    out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    total_units += 1
                    if (
                        len(samples) < args.sample_limit
                        and (len(span_items) > 1 or method != "pdf-font-align")
                    ):
                        samples.append(record)

    report = {
        "schema_version": 1,
        "book_id": manifest.get("book_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pdf": str(args.source_pdf),
        "xml_cache": str(xml_cache),
        "manifest": str(args.manifest),
        "chunk_dir": str(args.chunk_dir),
        "total_units": total_units,
        "method_counts": dict(counts),
        "kind_char_counts": dict(kind_counts),
        "failed_reconstruction": failed_reconstruction,
        "sample_records": samples,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed_reconstruction:
        raise SystemExit(f"span reconstruction failed for {failed_reconstruction} units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

