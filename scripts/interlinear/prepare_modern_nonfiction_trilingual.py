#!/usr/bin/env python3
"""Prepare modern nonfiction EN-JP-ZH trilingual PocketPolyglot tasks.

The input is a queue JSON under data/source-plan/. Each task uses an English
source as the alignment spine and prepares launchable chunk manifests for the
standard trilingual writer. This script does not start model workers.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from english_sentence_splitter import sentence_boundary_ends


ROOT = Path(__file__).resolve().parents[2]
SPACE_RE = re.compile(r"\s+")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
TAG_RE = re.compile(r"<[^>]+>")
PAGE_NUMBER_RE = re.compile(r"^(?:[-–—]?\s*)?(?:\d{1,5}|[ivxlcdm]{1,10})(?:\s*[-–—]?)?$", re.I)
LATIN_RE = re.compile(r"[A-Za-z]{3,}")
SENTENCE_END_RE = re.compile(r'[.!?]["”’)\]]*$')
HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+)?(?:"
    r"Introduction|Preface|Prologue|Epilogue|Conclusion|Afterword|Acknowledg(?:e)?ments|"
    r"(?:Part|Book|Chapter|CHAPTER)\s+(?:[IVXLCDM]+|\d+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b.*|"
    r"\d{1,3}[.)]\s+.{2,90}"
    r")$",
    re.I,
)
BOILERPLATE_RE = re.compile(
    r"(copyright|all rights reserved|isbn|published by|printed in|library of congress|"
    r"www\.|http[s]?://|ebook|cover design|permissions|random house|penguin|"
    r"basic books|oxford university press|mcgraw-hill|wiley)",
    re.I,
)
OCR_METADATA_RE = re.compile(
    r"^(?:source_pdf|conversion|generated_at|total_pdf_pages|ocr_|title):\s+",
    re.I,
)
OCR_PAGE_RE = re.compile(r"^#{1,6}\s+Page\s+\d+\b", re.I)
PAGE_ARTIFACT_RE = re.compile(
    r"^(?:Page\s+\d+|P(?:S|AGE)(?:\s+.+)?|[.$\sA-Z0-9_-]{8,}|"
    r"Trim Size:.+|k(?:\s+k)*|l)$"
)

CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, stderr=subprocess.STDOUT).decode("utf-8", errors="replace")


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_to_markdown(task: dict[str, Any]) -> Path:
    source = ROOT / task["source_path"]
    if not source.exists():
        raise FileNotFoundError(source)
    out = ROOT / "books" / task["book_id"] / "work/source-extraction/en.raw.md"
    if out.exists() and not task.get("force_extract", False):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        cmd = [
            "python",
            "scripts/interlinear/pdf_text_or_ocr.py",
            task["source_path"],
            "--output",
            str(out.relative_to(ROOT)),
            "--title",
            task["title_en"],
            "--min-content-chars",
            str(task.get("min_content_chars", 5000)),
            "--ocr-lang",
            str(task.get("ocr_lang", "eng")),
            "--ocr-psm",
            str(task.get("ocr_psm", 4)),
            "--ocr-dpi",
            str(task.get("ocr_dpi", 220)),
            "--ocr-workers",
            str(task.get("ocr_workers", 8)),
            "--ocr-pages",
            str(task.get("ocr_pages", "all")),
            "--ocr-crop",
            "--ocr-threshold",
        ]
        if task.get("force_ocr", False):
            cmd.append("--force-ocr")
        subprocess.check_call(cmd, cwd=ROOT)
        return out
    if suffix in {".epub", ".mobi", ".azw3"}:
        try:
            text = run_text(["pandoc", str(source), "-t", "gfm", "--wrap=none"])
            method = "pandoc-gfm"
        except subprocess.CalledProcessError:
            if suffix != ".epub":
                raise
            text = epub_to_markdown_fallback(source)
            method = "epub-html-fallback"
    else:
        raise ValueError(f"unsupported source type for {source}")
    body = normalize_raw_text(text)
    out.write_text(
        "---\n"
        f"source_file: {source.name}\n"
        f"conversion: {method}\n"
        f"generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        "---\n\n"
        f"# {task['title_en']}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return out


def epub_spine_paths(source: Path) -> list[str]:
    with zipfile.ZipFile(source) as zf:
        names = set(zf.namelist())
        opf_path = ""
        if "META-INF/container.xml" in names:
            container = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
            match = re.search(r'full-path=["\']([^"\']+)["\']', container)
            if match:
                opf_path = match.group(1)
        if opf_path and opf_path in names:
            opf = zf.read(opf_path).decode("utf-8", errors="replace")
            soup = BeautifulSoup(opf, "xml")
            base = posixpath.dirname(opf_path)
            manifest = {
                item.get("id"): item.get("href")
                for item in soup.find_all("item")
                if item.get("id") and item.get("href")
            }
            paths: list[str] = []
            for itemref in soup.find_all("itemref"):
                href = manifest.get(itemref.get("idref"))
                if not href:
                    continue
                path = posixpath.normpath(posixpath.join(base, href))
                if path in names and path.lower().endswith((".xhtml", ".html", ".htm")):
                    paths.append(path)
            if paths:
                return paths
        return sorted(
            name for name in names
            if name.lower().endswith((".xhtml", ".html", ".htm")) and not name.lower().endswith("nav.xhtml")
        )


def epub_to_markdown_fallback(source: Path) -> str:
    blocks: list[str] = []
    last = ""
    with zipfile.ZipFile(source) as zf:
        for name in epub_spine_paths(source):
            soup = BeautifulSoup(zf.read(name).decode("utf-8", errors="replace"), "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            body = soup.body or soup
            for node in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
                text = compact(node.get_text(" ", strip=True))
                if not text or text == last:
                    continue
                if node.name and node.name.startswith("h"):
                    level = min(int(node.name[1]), 6)
                    block = f"{'#' * level} {text}"
                elif node.name == "li":
                    block = f"- {text}"
                elif node.name == "blockquote":
                    block = f"> {text}"
                else:
                    block = text
                blocks.append(block)
                last = text
    if not blocks:
        raise RuntimeError(f"fallback EPUB extractor found no text in {source}")
    return "\n\n".join(blocks)


def normalize_raw_text(text: str) -> str:
    lines: list[str] = []
    in_yaml = False
    for raw in text.replace("\f", "\n\n").splitlines():
        line = html.unescape(raw)
        line = LINK_RE.sub(r"\1", line)
        line = TAG_RE.sub("", line)
        line = compact(line)
        if line == "---":
            in_yaml = not in_yaml
            continue
        if in_yaml or not line:
            lines.append("")
            continue
        if line.startswith("![]("):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_line(line: str, title: str) -> str:
    line = compact(line.replace("\u00ad", ""))
    if not line or PAGE_NUMBER_RE.fullmatch(line):
        return ""
    if OCR_METADATA_RE.match(line) or OCR_PAGE_RE.match(line):
        return ""
    if PAGE_ARTIFACT_RE.fullmatch(line):
        return ""
    if BOILERPLATE_RE.search(line):
        return ""
    if line.casefold() == title.casefold():
        return ""
    if len(line) <= 3 and not LATIN_RE.search(line):
        return ""
    # Drop isolated running headers but keep useful all-caps chapter headings.
    if re.fullmatch(r"[A-Z][A-Z .,'&:-]{3,70}", line) and not HEADING_RE.match(line):
        words = [w for w in re.split(r"\W+", line) if w]
        if 1 <= len(words) <= 5:
            return ""
    return line


def find_start(lines: list[str], task: dict[str, Any]) -> int:
    marker = str(task.get("start_marker") or "").strip()
    if marker:
        needle = compact(marker).casefold()
        for index, line in enumerate(lines):
            if needle in compact(line).casefold():
                return index
    for index, line in enumerate(lines):
        if HEADING_RE.match(line) or (len(line) > 80 and LATIN_RE.search(line)):
            return index
    return 0


def should_stop(line: str, task: dict[str, Any]) -> bool:
    lower = compact(line).casefold()
    for marker in task.get("stop_markers", []):
        wanted = compact(str(marker)).casefold()
        if not wanted:
            continue
        if lower == wanted:
            return True
        # Short stop markers such as "Index" or "Notes" are common ordinary
        # words in nonfiction body text. Treat prefixes as terminal only for
        # explicit longer phrases like "About the Author".
        if len(wanted) >= 12 and lower.startswith(wanted):
            return True
    return False


def split_english_units(text: str, *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    for end in sentence_boundary_ends(text):
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    if not pieces:
        pieces = [text]
    out: list[str] = []
    pending = ""
    for piece in pieces:
        if pending and len(pending) + 1 + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = f"{pending} {piece}".strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def parse_chapters(markdown: Path, task: dict[str, Any], *, max_unit_chars: int) -> list[dict[str, Any]]:
    raw_lines = markdown.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [clean_line(line, task["title_en"]) for line in raw_lines]
    lines = lines[find_start(lines, task) :]
    chapters: list[dict[str, Any]] = []
    current = {"number": 1, "title": str(task.get("default_chapter_title") or "Main Text"), "paragraphs": []}
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = compact(" ".join(buffer))
        buffer = []
        if len(text) >= 20 and LATIN_RE.search(text):
            current["paragraphs"].extend(split_english_units(text, max_chars=max_unit_chars))

    for line in lines:
        if should_stop(line, task):
            flush()
            break
        if not line:
            flush()
            continue
        heading = bool(HEADING_RE.match(line)) and len(line) <= 120
        if heading:
            flush()
            if current["paragraphs"]:
                chapters.append(current)
            current = {"number": len(chapters) + 1, "title": re.sub(r"^#{1,6}\s+", "", line), "paragraphs": []}
            continue
        if buffer and buffer[-1].endswith("-") and line and line[0].islower():
            buffer[-1] = buffer[-1][:-1] + line
        else:
            buffer.append(line)
        if SENTENCE_END_RE.search(line) and len(" ".join(buffer)) >= max_unit_chars:
            flush()
    flush()
    if current["paragraphs"]:
        chapters.append(current)
    if not chapters:
        raise RuntimeError(f"no usable paragraphs parsed for {task['book_id']}")
    return chapters


def build_chunks(task: dict[str, Any], chapters: list[dict[str, Any]], *, max_chunk_chars: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    paragraph_index = 0
    translation_contract = task.get(
        "translation_contract",
        {
            "style": "Accurate, complete, modern, understandable, elegant nonfiction translation.",
            "alignment": "Translate each source unit faithfully; do not summarize, skip, merge unrelated units, or add unsupported facts.",
            "japanese": "Use natural modern Japanese with kana and clear technical terms; never output Chinese prose in the Japanese field.",
            "chinese": "Use natural modern Chinese with precise terminology; preserve names, dates, causal claims, and distinctions.",
            "grammar": "Grammar-role analysis is required later in the pipeline; keep sentence structure clear enough for subject/predicate/object/topic/function tagging.",
        },
    )
    for chapter in chapters:
        pending: list[dict[str, str]] = []
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_chars
            if not pending:
                return
            index = len(chunks) + 1
            chunk_id = f"{task['book_id']}-c{index:04d}"
            en_ref = "\n".join(item["en"] for item in pending)
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": task["book_id"],
                    "source_spine_lang": "en",
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "chapter_id": f"chapter-{chapter['number']:03d}",
                    "chapter_number": chapter["number"],
                    "chapter_title_en": chapter["title"],
                    "chapter_title_zh": "",
                    "chapter_part_en": "",
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": {
                        "english": {"available": True, "chapter": chapter["title"], "text": en_ref},
                        "zh_primary": {"available": False, "chapter": "", "text": "", "quality": "generate_from_english_spine"},
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": {"available": False, "chapter": "", "text": ""},
                    },
                    "translation_contract": translation_contract,
                }
            )
            pending = []
            pending_chars = 0

        for paragraph in chapter["paragraphs"]:
            paragraph_index += 1
            paragraph_id = f"{task['book_id']}-s{chapter['number']:03d}-p{paragraph_index:05d}"
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
            pending.append({"id": paragraph_id, "en": paragraph})
            pending_chars += len(paragraph) + 1
        flush()

    source_path = ROOT / task["source_path"]
    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": task["book_id"],
        "book_title_en": task["title_en"],
        "book_title_zh": task["title_zh"],
        "book_title_ja": task["title_ja"],
        "book_title_zh_reading": task.get("title_zh_reading", ""),
        "book_title_ja_reading": task.get("title_ja_reading", ""),
        "author": task.get("author", ""),
        "author_reading_zh": task.get("author_reading_zh", ""),
        "author_reading_ja": task.get("author_reading_ja", ""),
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": "en",
        "source_paths": {"en": task["source_path"]},
        "source_sha256": {"en": sha256(source_path)},
        "source_note": task.get("description", ""),
        "chunk_count": len(chunks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "chapter_id": chunk["chapter_id"],
                "chapter_number": chunk["chapter_number"],
                "paragraph_ids": chunk["paragraph_ids"],
            }
            for chunk in chunks
        ],
    }
    return manifest, chunks


def write_book(task: dict[str, Any], queue: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    raw_md = source_to_markdown(task)
    chapters = parse_chapters(raw_md, task, max_unit_chars=args.max_unit_chars)
    book_root = ROOT / "books" / task["book_id"]
    markdown_path = book_root / "markdown/en.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_out = [f"# {task['title_en']}", ""]
    for chapter in chapters:
        markdown_out.extend([f"## {chapter['title']}", ""])
        markdown_out.extend(chapter["paragraphs"])
        markdown_out.append("")
    markdown_path.write_text("\n".join(markdown_out).strip() + "\n", encoding="utf-8")

    manifest, chunks = build_chunks(task, chapters, max_chunk_chars=args.max_chunk_chars)
    min_chunks = int(task.get("min_chunk_count", 1))
    if len(chunks) < min_chunks:
        raise RuntimeError(
            f"{task['book_id']} parsed only {len(chunks)} chunks; "
            f"expected at least {min_chunks}. Check start/stop markers and source extraction."
        )
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    write_json(chunks_dir / "manifest.json", manifest)
    plan = {
        "schema_version": 1,
        "book_id": task["book_id"],
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": task.get("task_mode", "trilingual_modern_nonfiction_en_source_generated_zh_ja"),
        "source_spine_lang": "en",
        "source_paths": manifest["source_paths"],
        "source_sha256": manifest["source_sha256"],
        "source_extraction": {
            "en_cache": str(raw_md.relative_to(ROOT)),
            "note": "Modern nonfiction generic extraction. PDF uses pdftotext; EPUB/MOBI uses pandoc.",
        },
        "markdown": {"en": str(markdown_path.relative_to(ROOT))},
        "book_title_en": task["title_en"],
        "book_title_zh": task["title_zh"],
        "book_title_ja": task["title_ja"],
        "book_title_zh_reading": task.get("title_zh_reading", ""),
        "book_title_ja_reading": task.get("title_ja_reading", ""),
        "author": task.get("author", ""),
        "author_reading_zh": task.get("author_reading_zh", ""),
        "author_reading_ja": task.get("author_reading_ja", ""),
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "book_description": task.get("description", ""),
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": "english_spine_only",
        "chunks_jsonl": str((chunks_dir / "chunks.jsonl").relative_to(ROOT)),
        "chunks_manifest": str((chunks_dir / "manifest.json").relative_to(ROOT)),
        "raw_chunk_dir": str(raw_chunk_dir.relative_to(ROOT)),
        "preview_json": str((preview_dir / f"{task['book_id']}.partial.json").relative_to(ROOT)),
        "assembled_json": str((preview_dir / f"{task['book_id']}.partial.json").relative_to(ROOT)),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "queue_id": queue.get("queue_id", ""),
        "queue_model": queue.get("model", ""),
        "queue_reasoning": queue.get("reasoning", ""),
        "chunk_count": len(chunks),
        "english_chapter_count": len(chapters),
        "preparation_notes": {
            "script": "scripts/interlinear/prepare_modern_nonfiction_trilingual.py",
            "english_spine": "English source text is the chunk spine.",
            "chinese_reference": "No published Chinese source configured for this task; generate readable modern Chinese from English.",
            "japanese_reference": "No published Japanese source configured for this task; generate natural modern Japanese from English.",
        },
    }
    write_json(book_root / "book-plan.json", plan)
    return {
        "book_id": task["book_id"],
        "chunks": len(chunks),
        "chapters": len(chapters),
        "manifest": str((chunks_dir / "manifest.json").relative_to(ROOT)),
        "book_plan": str((book_root / "book-plan.json").relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, type=Path, help="queue JSON file")
    parser.add_argument("--book-id", action="append", help="prepare selected book id; repeatable")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--max-unit-chars", type=int, default=900)
    parser.add_argument("--update-queue", action="store_true", help="write prepared status and chunk counts back to queue JSON")
    args = parser.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else ROOT / args.queue
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    selected = set(args.book_id or [])
    summaries: list[dict[str, Any]] = []
    for task in queue.get("tasks", []):
        if selected and task["book_id"] not in selected:
            continue
        summary = write_book(task, queue, args)
        summaries.append(summary)
        print(
            f"prepared book_id={summary['book_id']} chunks={summary['chunks']} "
            f"chapters={summary['chapters']} manifest={summary['manifest']}",
            flush=True,
        )
    if not summaries:
        raise SystemExit("no tasks selected")
    if args.update_queue:
        by_id = {item["book_id"]: item for item in summaries}
        for task in queue.get("tasks", []):
            summary = by_id.get(task.get("book_id"))
            if not summary:
                continue
            task["status"] = "chunked_launchable"
            task["book_plan"] = summary["book_plan"]
            task["chunks_manifest"] = summary["manifest"]
            task["chunk_count"] = summary["chunks"]
            task["english_chapter_count"] = summary["chapters"]
            task["prepared_chunks_at"] = datetime.now(timezone.utc).isoformat()
        queue["status"] = "chunked_launchable"
        queue["last_chunk_preparation_at"] = datetime.now(timezone.utc).isoformat()
        write_json(queue_path, queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
