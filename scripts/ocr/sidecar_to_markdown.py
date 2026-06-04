#!/usr/bin/env python3
"""Convert OCRmyPDF sidecar text into page-by-page Markdown and stats JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path


CONTENT_RE = re.compile(r"[\w\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def normalize_page(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t\u3000]+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def page_stats(page: int, text: str) -> dict[str, int | str]:
    content_chars = len(CONTENT_RE.findall(text))
    cjk_chars = len(CJK_RE.findall(text))
    latin_chars = len(LATIN_RE.findall(text))
    if content_chars >= 120:
        kind = "text"
    elif content_chars >= 20:
        kind = "caption_or_map"
    else:
        kind = "figure_or_blank"
    return {
        "page": page,
        "kind": kind,
        "content_chars": content_chars,
        "cjk_chars": cjk_chars,
        "latin_chars": latin_chars,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--stats", required=True, type=Path)
    parser.add_argument("--source-pdf", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()

    raw = args.sidecar.read_text(encoding="utf-8", errors="replace")
    pages = raw.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    normalized = [normalize_page(page) for page in pages]
    stats = [page_stats(index, text) for index, text in enumerate(normalized, start=1)]

    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    with args.markdown.open("w", encoding="utf-8") as handle:
        handle.write("---\n")
        handle.write(f"book_id: sanxingdui\n")
        handle.write(f"slug: {args.slug}\n")
        handle.write(f"title: {args.title}\n")
        handle.write(f"source_pdf: {args.source_pdf}\n")
        handle.write("conversion: ocrmypdf-sidecar\n")
        handle.write(f"generated_at: {generated_at}\n")
        handle.write("notes: Raw OCR sidecar. Figure-heavy pages are preserved in the searchable PDF.\n")
        handle.write("---\n\n")
        handle.write(f"# {args.title}\n\n")
        for item, text in zip(stats, normalized):
            handle.write(f"## Page {item['page']}\n\n")
            handle.write(
                f"<!-- kind={item['kind']} content_chars={item['content_chars']} "
                f"cjk_chars={item['cjk_chars']} latin_chars={item['latin_chars']} -->\n\n"
            )
            if text:
                handle.write(text)
                handle.write("\n\n")
            else:
                handle.write("[No OCR text detected on this page.]\n\n")

    total_content = sum(int(item["content_chars"]) for item in stats)
    text_pages = sum(1 for item in stats if item["kind"] == "text")
    stats_payload = {
        "book_id": "sanxingdui",
        "slug": args.slug,
        "title": args.title,
        "source_pdf": args.source_pdf,
        "pages": len(stats),
        "text_pages": text_pages,
        "total_content_chars": total_content,
        "generated_at": generated_at,
        "page_stats": stats,
    }
    args.stats.write_text(json.dumps(stats_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"markdown={args.markdown} stats={args.stats} pages={len(stats)} "
        f"text_pages={text_pages} content_chars={total_content}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
