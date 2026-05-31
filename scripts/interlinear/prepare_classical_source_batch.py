#!/usr/bin/env python3
"""Prepare classical public-domain source books for the zh-jp queue."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]


CLASSICAL_BOOKS: dict[str, dict[str, Any]] = {
    "sishu-jizhu": {
        "book_id": "sishu-jizhu",
        "book_title_zh": "四書章句集註",
        "book_title_zh_reading": "sì shū zhāng jù jí zhù",
        "book_title_ja": "四書章句集注",
        "book_title_ja_reading": "し しょ しょう く しっ ちゅう",
        "author": "朱熹",
        "author_reading_zh": "zhū xī",
        "author_reading_ja": "しゅ き",
        "book_description": "Zhu Xi, Collected Commentaries on the Four Books; Chinese Wikisource text with generated Japanese comment lines. The NDL kana-attached scan is kept as a local visual reference.",
        "source_kind": "html",
        "source_language": "zh",
        "source_path": "sources/sishu/四書章句集註（維基文庫） - 朱熹.json",
        "html_json": "sources/sishu/四書章句集註（維基文庫） - 朱熹.json",
        "local_ja_source_path": "sources/sishu/四書 仮名附（NDL公開） - 朱熹 集注・後藤嘉幸 点.pdf",
        "chunk_mode": "paragraph",
        "reference_scope": "chapter",
    },
    "shiji": {
        "book_id": "shiji",
        "book_title_zh": "史記",
        "book_title_zh_reading": "shǐ jì",
        "book_title_ja": "史記",
        "book_title_ja_reading": "し き",
        "author": "司馬遷",
        "author_reading_zh": "sī mǎ qiān",
        "author_reading_ja": "し ば せん",
        "book_description": "Sima Qian, Records of the Grand Historian. Chinese main text is prepared from the CText public-domain export, with Japanese Wikisource chapter references attached by chapter order.",
        "source_kind": "html",
        "source_language": "zh",
        "source_path": "sources/shiji/史記（中國哲學書電子化計劃） - 司馬遷.json",
        "html_json": "sources/shiji/史記（中國哲學書電子化計劃） - 司馬遷.json",
        "ja_source_path": "sources/shiji/史記（日本語ウィキソース） - 司馬遷.json",
        "ja_html_json": "sources/shiji/史記（日本語ウィキソース） - 司馬遷.json",
        "secondary_zh_source_path": "sources/shiji/史記（維基文庫文言文） - 司馬遷.json",
        "local_scan_source_path": "sources/shiji/史記三家注 【漢】司馬遷 （中華書局，1959）.pdf",
        "chunk_mode": "paragraph",
        "reference_scope": "chapter",
    },
    "kojiki": {
        "book_id": "kojiki",
        "book_title_zh": "古事記",
        "book_title_zh_reading": "gǔ shì jì",
        "book_title_ja": "古事記",
        "book_title_ja_reading": "こ じ き",
        "author": "太安萬侶・稗田阿礼",
        "author_reading_zh": "tài ān wàn lǚ · bài tián ā lǐ",
        "author_reading_ja": "おお の やす まろ・ひえだ の あれ",
        "book_description": "Kojiki. Chinese Wikisource PDF text is the main text; Japanese comment lines are generated from the Chinese source until a clean Japanese OCR/reference source is added.",
        "source_kind": "pdf_text",
        "source_language": "zh",
        "source_path": "sources/kojiki/古事記.pdf",
        "pdf_start_text": "臣安萬侣言：",
        "pdf_start_heading": "序",
        "local_ja_source_path": "sources/kojiki/古事記 (2).pdf",
        "local_en_source_path": "sources/kojiki/Kojiki_ Records Of Ancient Matters.pdf",
        "chunk_mode": "paragraph",
        "reference_scope": "chapter",
    },
}


NOISE_PREFIXES = (
    "Source:",
    "https://",
    "http://",
    "Generated from",
    "Root source:",
    "姊妹计划",
    "姉妹プロジェクト",
    "作者：",
)
NOISE_EXACT = {"←", "→", "◄", "►", "版本", "目錄", "目录"}
PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
FOOTNOTE_RE = re.compile(r"\[[0-9０-９]+\]")
SENTENCE_END_RE = re.compile(r"[。！？!?：；;」』）)]$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def clean_text(text: str) -> str:
    text = FOOTNOTE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise(text: str) -> bool:
    stripped = clean_text(text)
    if not stripped:
        return True
    if stripped in NOISE_EXACT or PAGE_NUMBER_RE.match(stripped):
        return True
    if any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True
    if len(stripped) <= 18 and ("←" in stripped or "→" in stripped or "◄" in stripped or "►" in stripped):
        return True
    return False


def source_html_path(json_path: Path) -> Path:
    data = load_json(json_path)
    html = Path(data["html"])
    if not html.exists():
        raise FileNotFoundError(html)
    return html


def display_chapter_title(raw_title: str, title_prefix_to_drop: str = "") -> str:
    chapter_title = clean_text(raw_title)
    if title_prefix_to_drop and chapter_title.startswith(title_prefix_to_drop):
        chapter_title = chapter_title[len(title_prefix_to_drop) :].strip("/")
    return chapter_title or "未題"


def html_chapter_titles(json_path: Path) -> list[str]:
    soup = BeautifulSoup(source_html_path(json_path).read_text(encoding="utf-8"), "html.parser")
    titles: list[str] = []
    for section in soup.select("section.chapter"):
        heading = section.find("h2")
        if heading:
            titles.append(clean_text(heading.get_text(" ", strip=True)))
    return titles


def html_to_markdown(json_path: Path, output_path: Path, title: str, *, title_prefix_to_drop: str = "") -> None:
    soup = BeautifulSoup(source_html_path(json_path).read_text(encoding="utf-8"), "html.parser")
    lines: list[str] = [f"# {title}", ""]
    for section in soup.select("section.chapter"):
        heading = section.find("h2")
        chapter_title = display_chapter_title(heading.get_text(" ", strip=True) if heading else "", title_prefix_to_drop)
        lines.extend([f"## {chapter_title}", ""])
        for node in section.find_all(["p", "li"], recursive=True):
            text = clean_text(node.get_text(" ", strip=True))
            if is_noise(text):
                continue
            lines.extend([text, ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n", encoding="utf-8")


def pdf_text_to_markdown(
    pdf_path: Path,
    output_path: Path,
    title: str,
    *,
    start_text: str = "",
    start_heading: str = "",
) -> None:
    proc = subprocess.run(
        ["pdftotext", "-raw", str(pdf_path), "-"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    raw_lines = proc.stdout.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if start_text:
        wanted = clean_text(start_text)
        for index, raw_line in enumerate(raw_lines):
            if clean_text(raw_line) == wanted:
                raw_lines = raw_lines[index:]
                break

    lines: list[str] = [f"# {title}", ""]
    if start_heading:
        lines.extend([f"## {start_heading}", ""])
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = clean_text("".join(buffer))
        buffer = []
        if text and not is_noise(text):
            lines.extend([text, ""])

    for raw_line in raw_lines:
        stripped = clean_text(raw_line)
        if not stripped:
            flush()
            continue
        if stripped in {"古事記", "序", "上卷", "中卷", "下卷"}:
            flush()
            lines.extend([f"## {stripped}", ""])
            continue
        if is_noise(stripped):
            continue
        buffer.append(stripped)
        if SENTENCE_END_RE.search(stripped) or len("".join(buffer)) >= 420:
            flush()
    flush()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n", encoding="utf-8")


def write_plan(book: dict[str, Any], paths: dict[str, str]) -> Path:
    book_id = book["book_id"]
    work_root = Path("books") / book_id / "work" / "bilingual"
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "launchable",
        "launchable": True,
        "task_mode": "zh_main_with_ja_source_reference" if paths.get("ja_source_markdown") else "zh_main_generate_jp_comment",
        "source_language": book.get("source_language", "zh"),
        "source_type": book["source_kind"],
        "source_path": book["source_path"],
        "ja_source_path": book.get("ja_source_path", ""),
        "local_ja_source_path": book.get("local_ja_source_path", ""),
        "secondary_zh_source_path": book.get("secondary_zh_source_path", ""),
        "local_scan_source_path": book.get("local_scan_source_path", ""),
        "local_en_source_path": book.get("local_en_source_path", ""),
        **paths,
        "book_title_zh": book["book_title_zh"],
        "book_title_zh_reading": book["book_title_zh_reading"],
        "book_title_ja": book["book_title_ja"],
        "book_title_ja_reading": book["book_title_ja_reading"],
        "author": book["author"],
        "author_reading_zh": book["author_reading_zh"],
        "author_reading_ja": book["author_reading_ja"],
        "book_description": book["book_description"],
        "chunk_mode": book.get("chunk_mode", "paragraph"),
        "reference_scope": book.get("reference_scope", "chapter"),
        "chunks_jsonl": str(work_root / "chunks" / "chunks.jsonl"),
        "chunks_manifest": str(work_root / "chunks" / "manifest.json"),
        "raw_chunk_dir": str(work_root / "interlinear" / "chunks"),
        "reviewed_chunk_dir": str(work_root / "reviewed" / "chunks"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    write_json(plan_path, plan)
    return plan_path


def prepare_book(book: dict[str, Any], *, force: bool) -> None:
    book_id = book["book_id"]
    markdown_dir = ROOT / "books" / book_id / "markdown"
    zh_md = markdown_dir / "zh.md"
    paths: dict[str, str] = {}

    if force or not zh_md.exists():
        if book["source_kind"] == "html":
            html_to_markdown(ROOT / book["html_json"], zh_md, book["book_title_zh"], title_prefix_to_drop=book["book_title_zh"])
        elif book["source_kind"] == "pdf_text":
            pdf_text_to_markdown(
                ROOT / book["source_path"],
                zh_md,
                book["book_title_zh"],
                start_text=book.get("pdf_start_text", ""),
                start_heading=book.get("pdf_start_heading", ""),
            )
        else:
            raise ValueError(f"unknown source_kind: {book['source_kind']}")
    paths.update(
        {
            "source_markdown": str(zh_md.relative_to(ROOT)),
            "clean_markdown": str(zh_md.relative_to(ROOT)),
            "raw_markdown": str(zh_md.relative_to(ROOT)),
            "source_sha256": sha256(ROOT / book["source_path"]),
            "markdown_sha256": sha256(zh_md),
        }
    )

    title_map_path = ""
    if book.get("ja_html_json"):
        ja_md = markdown_dir / "ja.md"
        if force or not ja_md.exists():
            html_to_markdown(ROOT / book["ja_html_json"], ja_md, book["book_title_ja"], title_prefix_to_drop=book["book_title_ja"])
        paths.update(
            {
                "ja_source_markdown": str(ja_md.relative_to(ROOT)),
                "ja_clean_markdown": str(ja_md.relative_to(ROOT)),
                "ja_raw_markdown": str(ja_md.relative_to(ROOT)),
                "ja_source_sha256": sha256(ROOT / book["ja_source_path"]),
                "ja_markdown_sha256": sha256(ja_md),
            }
        )
        zh_titles = html_chapter_titles(ROOT / book["html_json"])
        ja_titles = html_chapter_titles(ROOT / book["ja_html_json"])
        title_map = {
            display_chapter_title(zh_title, book["book_title_zh"]): display_chapter_title(
                ja_title, book["book_title_ja"]
            )
            for zh_title, ja_title in zip(zh_titles, ja_titles)
            if clean_text(zh_title) and clean_text(ja_title)
        }
        title_map_path = f"books/{book_id}/work/bilingual/chunks/title-map.json"
        write_json(ROOT / title_map_path, title_map)
        paths["title_map_json"] = title_map_path

    plan_path = write_plan(book, paths)
    plan = load_json(plan_path)
    chunks_jsonl = ROOT / plan["chunks_jsonl"]
    manifest = ROOT / plan["chunks_manifest"]
    if chunks_jsonl.exists() and manifest.exists() and not force:
        print(f"{book_id}: chunks already prepared: {chunks_jsonl.relative_to(ROOT)}", flush=True)
        return

    if paths.get("ja_source_markdown"):
        cmd = [
            "python",
            "scripts/interlinear/chunk_bilingual_markdown_book.py",
            "--zh-markdown",
            plan["source_markdown"],
            "--ja-markdown",
            plan["ja_source_markdown"],
            "--book-id",
            book_id,
            "--book-title-zh",
            plan["book_title_zh"],
            "--book-title-zh-reading",
            plan["book_title_zh_reading"],
            "--book-title-ja",
            plan["book_title_ja"],
            "--book-title-ja-reading",
            plan["book_title_ja_reading"],
            "--author",
            plan["author"],
            "--book-description",
            plan["book_description"],
            "--chunks-jsonl",
            plan["chunks_jsonl"],
            "--manifest",
            plan["chunks_manifest"],
            "--chunk-mode",
            plan["chunk_mode"],
            "--reference-scope",
            plan["reference_scope"],
            "--title-map-json",
            paths["title_map_json"],
        ]
    else:
        cmd = [
            "python",
            "scripts/interlinear/chunk_markdown_book.py",
            plan["source_markdown"],
            "--book-id",
            book_id,
            "--book-title-zh",
            plan["book_title_zh"],
            "--book-title-zh-reading",
            plan["book_title_zh_reading"],
            "--book-title-ja",
            plan["book_title_ja"],
            "--book-title-ja-reading",
            plan["book_title_ja_reading"],
            "--author",
            plan["author"],
            "--book-description",
            plan["book_description"],
            "--chunks-jsonl",
            plan["chunks_jsonl"],
            "--manifest",
            plan["chunks_manifest"],
            "--chunk-mode",
            plan["chunk_mode"],
        ]
    run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(CLASSICAL_BOOKS), help="prepare one book; repeatable")
    parser.add_argument("--output-suffix", default="", help="append a suffix to generated book ids, e.g. -aginti")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected = args.book_id or ["sishu-jizhu", "shiji", "kojiki"]
    for book_id in selected:
        book = dict(CLASSICAL_BOOKS[book_id])
        if args.output_suffix:
            book["book_id"] = f"{book['book_id']}{args.output_suffix}"
        print(f"== {book['book_id']} ==", flush=True)
        prepare_book(book, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
