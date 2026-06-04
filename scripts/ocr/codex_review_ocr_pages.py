#!/usr/bin/env python3
"""Review raw OCR Markdown pages with Codex and assemble corrected Markdown."""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "interlinear"))
from codex_chunk_worker import extract_json, run_codex  # noqa: E402


PAGE_RE = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)
META_RE = re.compile(r"<!--\s*kind=([^ ]+)\s+content_chars=(\d+)\s+cjk_chars=(\d+)\s+latin_chars=(\d+)\s*-->")


def parse_pages(markdown: str) -> list[dict[str, Any]]:
    matches = list(PAGE_RE.finditer(markdown))
    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        page = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        kind = "unknown"
        content_chars = 0
        meta = META_RE.search(body)
        if meta:
            kind = meta.group(1)
            content_chars = int(meta.group(2))
            body = META_RE.sub("", body, count=1).strip()
        pages.append({"page": page, "kind": kind, "content_chars": content_chars, "text": body})
    return pages


def prompt_for_page(title: str, slug: str, page: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    errors = ""
    if previous_errors:
        errors = "\nPrevious output failed validation. Fix these issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:20]
        )
    return textwrap.dedent(
        f"""
        You are correcting OCR text from a Chinese Sanxingdui archaeology/art-history source.

        Return exactly one JSON object. No Markdown fences, no explanation outside JSON.

        Book: {title}
        Slug: {slug}
        Page: {page['page']}
        OCR page kind: {page['kind']}

        Correct only obvious OCR errors, spacing errors, broken Chinese words, punctuation errors,
        and common Sanxingdui/Jinsha archaeology terms. Preserve the source meaning. Do not invent
        missing paragraphs. If the page is mostly a figure/map/table/blank with little recoverable
        prose, keep a concise note such as "[图版页/地图页，OCR文字有限]" and preserve any reliable
        captions or labels.

        Common terms to protect or repair when context fits:
        三星堆, 金沙, 古蜀, 祭祀坑, 青铜, 铜人, 铜面具, 玉器, 金器, 陶器, 石器,
        广汉, 成都平原, 四川, 遗址, 文物, 博物馆, 考古, 商周, 神树, 纵目面具,
        神鸟, 金杖, 城墙, 文化遗存, 保护范围.

        Required JSON shape:
        {{
          "page": {page['page']},
          "kind": "text|caption_or_map|figure_or_blank",
          "corrected_text": "corrected Chinese OCR text or a concise figure-page note",
          "notes": ["short review notes"],
          "confidence": "high|medium|low"
        }}

        Hard rules:
        - corrected_text must be Chinese prose/text, not English commentary.
        - Do not translate.
        - Do not summarize text pages; keep page text in reading order.
        - Do not add facts that are not recoverable from the OCR text.
        - For figure-only pages, do not hallucinate captions.
        {errors}

        Raw OCR text:
        {page['text']}
        """
    ).strip()


def validate_result(page: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("page") != page["page"]:
        errors.append(f"page mismatch: expected {page['page']}")
    if result.get("kind") not in {"text", "caption_or_map", "figure_or_blank"}:
        errors.append("kind must be text, caption_or_map, or figure_or_blank")
    corrected = str(result.get("corrected_text") or "").strip()
    if not corrected:
        errors.append("corrected_text is empty")
    if len(corrected) > max(400, len(page["text"]) * 3):
        errors.append("corrected_text is implausibly longer than raw OCR")
    if result.get("confidence") not in {"high", "medium", "low"}:
        errors.append("confidence must be high, medium, or low")
    if not isinstance(result.get("notes", []), list):
        errors.append("notes must be a list")
    return errors


def review_markdown(path: Path, args: argparse.Namespace) -> None:
    slug = path.stem.removesuffix(".ocr")
    title = slug
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"^title:\s*(.+)$", raw, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    pages = parse_pages(raw)
    out_dir = Path(args.output_root) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_root) / slug
    reviewed_pages: list[dict[str, Any]] = []
    reviewed_count = 0
    skipped_count = 0

    for page in pages:
        page_path = out_dir / f"page-{page['page']:04d}.json"
        if page_path.exists() and not args.force:
            try:
                existing = json.loads(page_path.read_text(encoding="utf-8"))
                if not validate_result(page, existing):
                    reviewed_pages.append(existing)
                    skipped_count += 1
                    continue
            except Exception:
                pass
        if page["content_chars"] < args.min_chars and page["kind"] != "text":
            result = {
                "page": page["page"],
                "kind": "figure_or_blank",
                "corrected_text": "[图版页/地图页，OCR文字有限]",
                "notes": ["Skipped semantic Codex review because OCR text is sparse."],
                "confidence": "low",
            }
            page_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            reviewed_pages.append(result)
            skipped_count += 1
            continue

        errors: list[str] | None = None
        for attempt in range(1, args.retries + 2):
            prompt = prompt_for_page(title, slug, page, errors)
            prompt_path = work_dir / "prompts" / f"page-{page['page']:04d}.attempt{attempt}.md"
            message_path = work_dir / "messages" / f"page-{page['page']:04d}.attempt{attempt}.md"
            log_path = work_dir / "logs" / f"page-{page['page']:04d}.log"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")
            print(f"codex_ocr_review slug={slug} page={page['page']} attempt={attempt}", flush=True)
            run_codex(
                prompt,
                message_path,
                log_path,
                first=True,
                model=args.model,
                reasoning=args.reasoning,
                cwd=ROOT,
                timeout_seconds=args.codex_timeout_seconds,
            )
            try:
                result = extract_json(message_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors = [f"JSON parse failed: {exc}"]
                continue
            errors = validate_result(page, result)
            if errors:
                continue
            page_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            reviewed_pages.append(result)
            reviewed_count += 1
            break
        else:
            failed = {
                "page": page["page"],
                "kind": page["kind"] if page["kind"] in {"text", "caption_or_map", "figure_or_blank"} else "text",
                "corrected_text": page["text"],
                "notes": ["Codex review failed; raw OCR retained.", *(errors or [])],
                "confidence": "low",
            }
            page_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            reviewed_pages.append(failed)

        if args.max_pages and reviewed_count >= args.max_pages:
            break

    assembled = Path(args.markdown_output_dir) / f"{slug}.reviewed.md"
    assembled.parent.mkdir(parents=True, exist_ok=True)
    with assembled.open("w", encoding="utf-8") as handle:
        handle.write(f"# {title}（OCR校订稿）\n\n")
        for item in sorted(reviewed_pages, key=lambda value: int(value["page"])):
            handle.write(f"## Page {item['page']}\n\n")
            handle.write(f"<!-- kind={item['kind']} confidence={item['confidence']} -->\n\n")
            handle.write(str(item["corrected_text"]).strip())
            handle.write("\n\n")
    print(
        f"reviewed_markdown={assembled} reviewed_pages={reviewed_count} skipped_pages={skipped_count}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-dir", default="books/sanxingdui/markdown")
    parser.add_argument("--output-root", default="books/sanxingdui/work/ocr-review/pages")
    parser.add_argument("--work-root", default="books/sanxingdui/work/ocr-review/codex")
    parser.add_argument("--markdown-output-dir", default="books/sanxingdui/markdown")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--codex-timeout-seconds", type=int, default=3600)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--min-chars", type=int, default=80)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    markdown_dir = Path(args.markdown_dir)
    seen: set[Path] = set()
    while True:
        files = sorted(markdown_dir.glob("*.ocr.md"))
        for path in files:
            if path in seen and not args.force:
                continue
            review_markdown(path, args)
            seen.add(path)
        if args.once:
            return 0
        print(f"waiting_for_ocr_markdown dir={markdown_dir} sleep={args.poll_seconds}", flush=True)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
