#!/usr/bin/env python3
"""Polish Sanxingdui OCR pages into publishable Chinese book text with Codex."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "interlinear"))
from codex_chunk_worker import extract_json, run_codex  # noqa: E402


BOOK_ID = "sanxingdui"
PLAN = ROOT / "books" / BOOK_ID / "book-plan.json"
PAGE_RE = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.MULTILINE | re.IGNORECASE)
META_RE = re.compile(r"<!--\s*([^>]+?)\s*-->")
KIND_RE = re.compile(r"\bkind=([A-Za-z0-9_:-]+)")
CONTENT_RE = re.compile(r"[\w\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_JUNK_RE = re.compile(r"(?i)(?:[a-z]{26,}|[a-z]*[bcdfghjklmnpqrstvwxyz]{18,}[a-z]*|[osear]{18,})")

ALLOWED_KINDS = {
    "frontmatter",
    "toc",
    "text",
    "catalog",
    "caption_or_map",
    "figure_or_blank",
    "notes",
}
ALLOWED_BLOCKS = {"heading", "paragraph", "list_item", "caption", "note"}


def load_plan() -> list[dict[str, str]]:
    return list(json.loads(PLAN.read_text(encoding="utf-8"))["books"])


def parse_pages(markdown: str) -> list[dict[str, Any]]:
    matches = list(PAGE_RE.finditer(markdown))
    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        kind = "text"
        meta_match = META_RE.search(body)
        if meta_match:
            kind_match = KIND_RE.search(meta_match.group(1))
            if kind_match:
                kind = kind_match.group(1)
            body = META_RE.sub("", body, count=1).strip()
        pages.append(
            {
                "page": page_number,
                "kind": kind,
                "content_chars": len(CONTENT_RE.findall(body)),
                "cjk_chars": len(CJK_RE.findall(body)),
                "text": body,
            }
        )
    return pages


def markdown_title(markdown: str, fallback: str) -> str:
    title_match = re.search(r"^title:\s*(.+)$", markdown, flags=re.MULTILINE)
    if title_match:
        return title_match.group(1).strip()
    h1_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    if h1_match:
        return re.sub(r"（(?:OCR校订稿|润色校订稿)）$", "", h1_match.group(1).strip())
    return fallback


def best_markdown(slug: str) -> tuple[Path, str]:
    base = ROOT / "books" / BOOK_ID / "markdown"
    reviewed = base / f"{slug}.reviewed.md"
    raw = base / f"{slug}.ocr.md"
    if reviewed.exists():
        return reviewed, "reviewed"
    if raw.exists():
        return raw, "raw"
    raise FileNotFoundError(f"No OCR Markdown found for {slug}")


def load_prior_review(slug: str, page: int) -> str:
    path = ROOT / "books" / BOOK_ID / "work" / "ocr-review" / "pages" / slug / f"page-{page:04d}.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("corrected_text") or "").strip()


def prompt_for_page(
    title: str,
    slug: str,
    source_kind: str,
    page: dict[str, Any],
    prior_review: str,
    previous_errors: list[str] | None = None,
) -> str:
    errors = ""
    if previous_errors:
        errors = "\nPrevious output failed validation. Fix these issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:25]
        )
    prior = ""
    if prior_review:
        prior = f"\nPrior conservative OCR correction, if useful:\n{prior_review}\n"
    return textwrap.dedent(
        f"""
        You are a senior Chinese editor preparing a publishable TeX book from OCR
        of a Sanxingdui / Jinsha archaeology and art-history source.

        Return exactly one JSON object. No Markdown fences. No explanation outside JSON.

        Book: {title}
        Slug: {slug}
        Page: {page['page']}
        Source text stage: {source_kind}
        OCR page kind: {page['kind']}

        Editorial goal:
        - Produce a normal, beautiful, readable Chinese book page.
        - Correct OCR errors aggressively when the intended Chinese is clear.
        - Remove OCR debris, random Latin noise, repeated filler letters, broken table leaders,
          duplicated fragments, broken line endings, and malformed punctuation.
        - Rejoin broken Chinese lines into coherent paragraphs.
        - Keep catalog/table-of-contents pages as clean list items.
        - Keep reliable artifact captions, figure labels, dates, dimensions, ISBNs, URLs, and names.
        - Do not invent missing facts. If a figure page has too little text, output a concise note.

        Important archaeology terms to protect or repair when context fits:
        三星堆, 金沙, 古蜀, 广汉, 成都平原, 四川, 青铜, 铜人, 铜面具, 纵目面具,
        神树, 祭祀坑, 玉器, 金器, 陶器, 石器, 遗址, 遗物, 文物, 考古, 博物馆,
        商代, 西周, 宝墩文化, 十二桥文化, 金杖, 太阳神鸟, 城墙, 器物坑.

        Required JSON shape:
        {{
          "page": {page['page']},
          "kind": "frontmatter|toc|text|catalog|caption_or_map|figure_or_blank|notes",
          "blocks": [
            {{"type": "heading|paragraph|list_item|caption|note", "text": "polished Chinese text"}}
          ],
          "notes": ["short private editorial notes"],
          "confidence": "high|medium|low"
        }}

        Hard rules:
        - Chinese output only except legitimate titles, ISBN, URLs, units, dates, artifact numbers, or names.
        - Do not translate, summarize, or add new content.
        - Do not preserve OCR garbage. If text cannot be recovered, say it is a figure/page with limited text.
        - Do not mention "OCR" in visible block text unless the source itself says OCR.
        - Preserve original page boundaries. Only polish this one page.
        - For text pages, do not collapse substantial prose into one sentence.
        - Use "heading" only for visible headings/titles.
        - Use "list_item" for目录/catalog rows; do not keep dotted leader garbage.
        - Use "caption" for artifact/image captions.
        {errors}
        {prior}
        Raw page text:
        {page['text']}
        """
    ).strip()


def visible_text(result: dict[str, Any]) -> str:
    return "\n".join(str(block.get("text", "")).strip() for block in result.get("blocks", []) if block.get("text"))


def validate_result(page: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("page") != page["page"]:
        errors.append(f"page mismatch: expected {page['page']}")
    if result.get("kind") not in ALLOWED_KINDS:
        errors.append(f"kind must be one of {sorted(ALLOWED_KINDS)}")
    blocks = result.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errors.append("blocks must be a non-empty list")
        return errors
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"blocks[{index}] must be an object")
            continue
        if block.get("type") not in ALLOWED_BLOCKS:
            errors.append(f"blocks[{index}].type must be one of {sorted(ALLOWED_BLOCKS)}")
        text = str(block.get("text") or "").strip()
        if not text:
            errors.append(f"blocks[{index}].text is empty")
        if "```" in text:
            errors.append(f"blocks[{index}].text contains Markdown/code fence")
    text = visible_text(result)
    if len(text) > max(600, len(page["text"]) * 4):
        errors.append("visible text is implausibly longer than source page")
    if page["content_chars"] >= 220 and len(CJK_RE.findall(text)) < min(80, max(20, page["cjk_chars"] // 5)):
        errors.append("substantial source page was reduced too much")
    if result.get("kind") not in {"figure_or_blank", "caption_or_map"}:
        junk = [match.group(0) for match in LATIN_JUNK_RE.finditer(text)]
        junk = [item for item in junk if not re.search(r"ISBN|https?|www|[A-Z]{1,4}\d", item, flags=re.I)]
        if junk:
            errors.append(f"probable OCR Latin junk remains: {junk[:3]}")
    if result.get("confidence") not in {"high", "medium", "low"}:
        errors.append("confidence must be high, medium, or low")
    if not isinstance(result.get("notes", []), list):
        errors.append("notes must be a list")
    return errors


def fallback_result(page: dict[str, Any], reason: str) -> dict[str, Any]:
    if page["content_chars"] < 40 and page["kind"] != "text":
        text = "[图版页/地图页，原页文字有限]"
        kind = "figure_or_blank"
        block_type = "note"
    else:
        text = page["text"].strip() or "[本页文字无法可靠识读]"
        kind = page["kind"] if page["kind"] in ALLOWED_KINDS else "text"
        block_type = "paragraph"
    return {
        "page": page["page"],
        "kind": kind,
        "blocks": [{"type": block_type, "text": text}],
        "notes": [reason],
        "confidence": "low",
    }


def write_page(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_valid_existing(path: Path, page: dict[str, Any]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if not validate_result(page, payload) else None


def markdown_for_block(block: dict[str, Any]) -> str:
    text = str(block.get("text") or "").strip()
    block_type = block.get("type")
    if block_type == "heading":
        return f"### {text}"
    if block_type == "list_item":
        return f"- {text}"
    if block_type in {"caption", "note"}:
        return f"> {text}"
    return text


def assemble_markdown(title: str, slug: str, pages: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        handle.write(f"# {title}（润色校订稿）\n\n")
        for item in sorted(pages, key=lambda value: int(value["page"])):
            handle.write(f"## Page {item['page']}\n\n")
            handle.write(f"<!-- kind={item['kind']} confidence={item['confidence']} -->\n\n")
            for block in item["blocks"]:
                handle.write(markdown_for_block(block))
                handle.write("\n\n")
    print(f"polished_markdown={output.relative_to(ROOT)} pages={len(pages)}", flush=True)


def compile_polished(slug: str) -> None:
    subprocess.check_call(
        [
            sys.executable,
            "scripts/ocr/markdown_to_sanxingdui_tex.py",
            "--polished",
            "--slug",
            slug,
        ],
        cwd=ROOT,
    )


def polish_book(book: dict[str, str], args: argparse.Namespace) -> None:
    slug = book["slug"]
    source_path, source_kind = best_markdown(slug)
    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    title = markdown_title(source_text, book["title"])
    pages = parse_pages(source_text)
    out_dir = ROOT / "books" / BOOK_ID / "work" / "tex-polish" / "pages" / slug
    codex_dir = ROOT / "books" / BOOK_ID / "work" / "tex-polish" / "codex" / slug
    polished_pages: list[dict[str, Any]] = []
    processed = 0

    for page in pages:
        if page["page"] < args.start_page:
            continue
        page_path = out_dir / f"page-{page['page']:04d}.json"
        existing = None if args.force else load_valid_existing(page_path, page)
        if existing:
            polished_pages.append(existing)
        else:
            if page["content_chars"] < args.min_chars and page["kind"] != "text":
                result = fallback_result(page, "Sparse figure/map page skipped without Codex polishing.")
                write_page(page_path, result)
                polished_pages.append(result)
            else:
                errors: list[str] | None = None
                for attempt in range(1, args.retries + 2):
                    prior = load_prior_review(slug, page["page"])
                    prompt = prompt_for_page(title, slug, source_kind, page, prior, errors)
                    prompt_path = codex_dir / "prompts" / f"page-{page['page']:04d}.attempt{attempt}.md"
                    message_path = codex_dir / "messages" / f"page-{page['page']:04d}.attempt{attempt}.md"
                    log_path = codex_dir / "logs" / f"page-{page['page']:04d}.log"
                    prompt_path.parent.mkdir(parents=True, exist_ok=True)
                    prompt_path.write_text(prompt, encoding="utf-8")
                    print(f"codex_sanxingdui_polish slug={slug} page={page['page']} attempt={attempt}", flush=True)
                    try:
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
                    except Exception as exc:
                        errors = [f"Codex failed: {exc}"]
                        continue
                    try:
                        result = extract_json(message_path.read_text(encoding="utf-8"))
                    except Exception as exc:
                        errors = [f"JSON parse failed: {exc}"]
                        continue
                    errors = validate_result(page, result)
                    if errors:
                        continue
                    write_page(page_path, result)
                    polished_pages.append(result)
                    break
                else:
                    result = fallback_result(page, "Codex polishing failed; source text retained for later repair.")
                    write_page(page_path, result)
                    polished_pages.append(result)
        processed += 1
        if args.max_pages and processed >= args.max_pages:
            break

    if not polished_pages:
        raise SystemExit(f"No pages polished for {slug}")
    assembled = ROOT / "books" / BOOK_ID / "markdown" / f"{slug}.polished.md"
    assemble_markdown(title, slug, polished_pages, assembled)
    if args.compile:
        compile_polished(slug)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", help="Polish only this slug; may be repeated.")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--codex-timeout-seconds", type=int, default=3600)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--min-chars", type=int, default=60)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    wanted = set(args.slug or [])
    books = load_plan()
    unknown = wanted.difference(book["slug"] for book in books)
    if unknown:
        raise SystemExit(f"unknown slug(s): {', '.join(sorted(unknown))}")
    for book in books:
        if wanted and book["slug"] not in wanted:
            continue
        polish_book(book, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
