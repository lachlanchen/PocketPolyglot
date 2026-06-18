#!/usr/bin/env python3
"""OCR, polish, and validate world-literature PDF sources for trilingual tasks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PAGE_RE = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)
META_RE = re.compile(r"<!--[^>]*-->")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]")
CONTENT_RE = re.compile(r"[\w\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


@dataclass(frozen=True)
class OcrSource:
    book_id: str
    lang: str
    title: str
    source_pdf: Path
    tesseract_lang: str
    psm: int = 4


SOURCES: tuple[OcrSource, ...] = (
    OcrSource(
        "one-hundred-years-of-solitude",
        "en",
        "One Hundred Years of Solitude",
        Path("sources/one-hundred-years-of-solitude/One Hundred Years of Solitude.pdf"),
        "eng",
    ),
    OcrSource(
        "wuthering-heights",
        "zh",
        "呼啸山庄",
        Path("sources/wuthering-heights/呼啸山庄.pdf"),
        "chi_sim+eng",
    ),
    OcrSource(
        "jane-eyre",
        "zh",
        "简·爱",
        Path("sources/jane-eyre/夏洛蒂·勃朗特-简·爱.pdf"),
        "chi_sim+eng",
    ),
    OcrSource(
        "the-count-of-monte-cristo",
        "zh",
        "基督山伯爵",
        Path(
            "sources/the-count-of-monte-cristo/"
            "读客经典文库：基督山伯爵（余华不吃不喝不睡，疯了般读完《基督山伯爵》！人类全部的智慧尽在其中！全三册一字未删完整版！）.pdf"
        ),
        "chi_sim+eng",
    ),
    OcrSource(
        "notre-dame-de-paris",
        "en",
        "Notre-Dame de Paris",
        Path("sources/notre-dame-de-paris/Notre-dame de Paris, by Victor Hugo.pdf"),
        "eng",
    ),
    OcrSource(
        "notre-dame-de-paris",
        "zh",
        "巴黎圣母院",
        Path("sources/notre-dame-de-paris/巴黎圣母院.pdf"),
        "chi_sim+eng",
    ),
    OcrSource(
        "les-miserables",
        "en",
        "Les Misérables",
        Path("sources/les-miserables/Les Misérables.pdf"),
        "eng",
    ),
    OcrSource(
        "les-miserables",
        "zh",
        "悲惨世界",
        Path("sources/les-miserables/悲惨世界（上、下）【文字版】.pdf"),
        "chi_sim+eng",
    ),
)


def run(cmd: list[str], *, log_path: Path) -> None:
    print("+ " + " ".join(cmd), flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = process.wait()
    if rc:
        raise RuntimeError(f"command failed with status {rc}: {' '.join(cmd)}")


def pdf_pages(path: Path) -> int:
    text = subprocess.check_output(["pdfinfo", str(path)], cwd=ROOT, text=True, stderr=subprocess.STDOUT)
    for line in text.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return 0


def parse_pages(markdown: str) -> list[dict[str, Any]]:
    matches = list(PAGE_RE.finditer(markdown))
    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        page = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = META_RE.sub("", markdown[start:end]).strip()
        pages.append({"page": page, "text": body})
    return pages


def clean_page_lines(text: str, *, lang: str) -> list[str]:
    cleaned: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = re.sub(r"[ \t\u3000]+", " ", raw).strip()
        if not line:
            continue
        if line.startswith("---") or line.startswith("source_pdf:") or line.startswith("ocr_"):
            continue
        if re.fullmatch(r"[-—–]?\s*\d{1,5}\s*[-—–]?", line):
            continue
        if "No OCR text detected" in line:
            continue
        if lang == "zh":
            line = normalize_zh_noise(line)
        else:
            line = normalize_en_noise(line)
        if line:
            cleaned.append(line)
    return cleaned


def normalize_zh_noise(line: str) -> str:
    replacements = {
        " ,": "，",
        " .": "。",
        " !": "！",
        " ?": "？",
        " :": "：",
        " ;": "；",
        "．": "。",
        "﹐": "，",
        "﹔": "；",
        "﹕": "：",
    }
    for bad, good in replacements.items():
        line = line.replace(bad, good)
    line = line.replace("“ ", "“").replace(" ”", "”")
    line = line.replace("( ", "（").replace(" )", "）")
    line = re.sub(r"\s+([，。！？；：、”）》])", r"\1", line)
    line = re.sub(r"([“《（])\s+", r"\1", line)
    line = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", line)
    return line.strip()


def normalize_en_noise(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = line.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":")
    line = line.replace(" ?", "?").replace(" !", "!")
    return line


def join_lines(lines: list[str], *, lang: str) -> str:
    if lang == "zh":
        out = ""
        for line in lines:
            if not out:
                out = line
            elif re.search(r"[，。！？；：、”）》]$", out) or re.match(r"^[，。！？；：、”）》]", line):
                out += line
            else:
                out += line
        return out.strip()
    text = ""
    for line in lines:
        if not text:
            text = line
        elif text.endswith("-"):
            text = text[:-1] + line
        else:
            text += " " + line
    return text.strip()


def split_reasonable_paragraphs(text: str, *, lang: str, max_chars: int = 1200) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text else []
    if lang == "zh":
        pieces = re.split(r"(?<=[。！？])", text)
    else:
        pieces = []
        start = 0
        for match in re.finditer(r'[.!?]["”’)]?\s+', text):
            pieces.append(text[start : match.end()].strip())
            start = match.end()
        tail = text[start:].strip()
        if tail:
            pieces.append(tail)
    out: list[str] = []
    pending = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if pending and len(pending) + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = (pending + (" " if lang == "en" else "") + piece).strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def page_payload(text: str, *, lang: str) -> tuple[str, dict[str, Any]]:
    lines = clean_page_lines(text, lang=lang)
    paragraph = join_lines(lines, lang=lang)
    paragraphs = split_reasonable_paragraphs(paragraph, lang=lang)
    polished = "\n\n".join(paragraphs).strip()
    cjk_chars = len(CJK_RE.findall(polished))
    latin_chars = len(LATIN_RE.findall(polished))
    content_chars = len(CONTENT_RE.findall(polished))
    suspect_reasons: list[str] = []
    if not polished:
        suspect_reasons.append("empty_page")
    if "�" in polished:
        suspect_reasons.append("replacement_character")
    if lang == "zh":
        if content_chars >= 80 and cjk_chars / max(content_chars, 1) < 0.55:
            suspect_reasons.append("low_cjk_ratio")
        if re.search(r"[A-Za-z]{18,}", polished):
            suspect_reasons.append("long_latin_run")
    if lang == "en" and content_chars >= 80 and latin_chars / max(content_chars, 1) < 0.55:
        suspect_reasons.append("low_latin_ratio")
    return polished, {
        "content_chars": content_chars,
        "cjk_chars": cjk_chars,
        "latin_chars": latin_chars,
        "suspect_reasons": suspect_reasons,
    }


def polish_raw_ocr(source: OcrSource, raw_path: Path, polished_path: Path, validation_path: Path) -> None:
    raw = raw_path.read_text(encoding="utf-8", errors="replace")
    pages = parse_pages(raw)
    total_content = 0
    suspect_pages: list[dict[str, Any]] = []
    polished_path.parent.mkdir(parents=True, exist_ok=True)
    with polished_path.open("w", encoding="utf-8") as handle:
        handle.write("---\n")
        handle.write(f"book_id: {source.book_id}\n")
        handle.write(f"lang: {source.lang}\n")
        handle.write(f"title: {source.title}\n")
        handle.write(f"source_pdf: {source.source_pdf}\n")
        handle.write("conversion: tesseract-ocr-polished\n")
        handle.write(f"generated_at: {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        handle.write("notes: Polished OCR reference. Keep page headings for evidence; trilingual prep ignores them.\n")
        handle.write("---\n\n")
        handle.write(f"# {source.title}（OCR校订参考）\n\n")
        for page in pages:
            polished, stats = page_payload(str(page["text"]), lang=source.lang)
            total_content += int(stats["content_chars"])
            handle.write(f"## Page {page['page']}\n\n")
            handle.write(
                f"<!-- content_chars={stats['content_chars']} cjk_chars={stats['cjk_chars']} "
                f"latin_chars={stats['latin_chars']} -->\n\n"
            )
            if polished:
                handle.write(polished)
            else:
                handle.write("[OCR text sparse or blank]")
            handle.write("\n\n")
            if stats["suspect_reasons"]:
                suspect_pages.append({"page": page["page"], **stats})
    validation = {
        "book_id": source.book_id,
        "lang": source.lang,
        "title": source.title,
        "source_pdf": str(source.source_pdf),
        "pages": len(pages),
        "total_content_chars": total_content,
        "suspect_page_count": len(suspect_pages),
        "suspect_pages_sample": suspect_pages[:80],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "raw_ocr_markdown": str(raw_path.relative_to(ROOT)),
        "polished_markdown": str(polished_path.relative_to(ROOT)),
    }
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_source(source: OcrSource, args: argparse.Namespace) -> None:
    source_pdf = ROOT / source.source_pdf
    if not source_pdf.exists():
        raise FileNotFoundError(source_pdf)
    work_dir = ROOT / "books" / source.book_id / "work" / "ocr" / source.lang
    raw_path = work_dir / f"{source.lang}.ocr.md"
    log_path = work_dir / "ocr.log"
    status_path = work_dir / "status.json"
    polished_path = ROOT / "books" / source.book_id / "markdown" / f"{source.lang}.ocr-polished.md"
    validation_path = work_dir / "validation.json"

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": "started",
                "book_id": source.book_id,
                "lang": source.lang,
                "source_pdf": str(source.source_pdf),
                "pages": pdf_pages(source_pdf),
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.force or not raw_path.exists():
        cmd = [
            sys.executable,
            "scripts/ocr/pdf_to_markdown.py",
            str(source.source_pdf),
            "--output",
            str(raw_path.relative_to(ROOT)),
            "--lang",
            source.tesseract_lang,
            "--psm",
            str(args.psm or source.psm),
            "--dpi",
            str(args.dpi),
            "--workers",
            str(args.workers),
            "--crop",
            "--threshold",
        ]
        if args.pages != "all":
            cmd.extend(["--pages", args.pages])
        run(cmd, log_path=log_path)
    else:
        print(f"skip_existing_raw_ocr={raw_path.relative_to(ROOT)}", flush=True)
    polish_raw_ocr(source, raw_path, polished_path, validation_path)
    status_path.write_text(
        json.dumps(
            {
                "status": "done",
                "book_id": source.book_id,
                "lang": source.lang,
                "source_pdf": str(source.source_pdf),
                "raw_ocr_markdown": str(raw_path.relative_to(ROOT)),
                "polished_markdown": str(polished_path.relative_to(ROOT)),
                "validation": str(validation_path.relative_to(ROOT)),
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"ocr_polished={source.book_id}:{source.lang} output={polished_path.relative_to(ROOT)}", flush=True)


def refresh_prepared_books(book_ids: list[str]) -> None:
    if not book_ids:
        return
    cmd = [sys.executable, "scripts/interlinear/prepare_world_literature_trilingual.py"]
    for book_id in sorted(set(book_ids)):
        cmd.extend(["--book-id", book_id])
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", help="Process one target as <book-id>:<lang>; repeatable.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--psm", type=int, default=0, help="Override source PSM; 0 uses source default.")
    parser.add_argument("--pages", default="all")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    args = parser.parse_args()

    targets = set(args.target or [])
    known = {f"{source.book_id}:{source.lang}" for source in SOURCES}
    unknown = targets.difference(known)
    if unknown:
        raise SystemExit(f"unknown target(s): {', '.join(sorted(unknown))}")
    processed: list[str] = []
    for source in SOURCES:
        key = f"{source.book_id}:{source.lang}"
        if targets and key not in targets:
            continue
        process_source(source, args)
        processed.append(source.book_id)
        if not args.no_refresh:
            refresh_prepared_books([source.book_id])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
