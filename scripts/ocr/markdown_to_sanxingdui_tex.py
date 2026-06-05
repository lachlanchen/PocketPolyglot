#!/usr/bin/env python3
"""Render Sanxingdui OCR Markdown as visible-text XeLaTeX books."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "sanxingdui"
EDITION_ID = "sanxingdui-tex"
TEMPLATE = ROOT / "tex" / "sanxingdui-tex" / "book.tex"
PLAN = ROOT / "books" / BOOK_ID / "book-plan.json"

PAGE_RE = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
COMMENT_RE = re.compile(r"^<!--\s*(.*?)\s*-->\s*$")
KIND_RE = re.compile(r"\bkind=([A-Za-z0-9_:-]+)")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9]")
PUNCT_END_RE = re.compile(r"[。！？；：，、,.!?;:）】》」』”’]$")
PAGE_NUMBER_LINE_RE = re.compile(r"\s+\d{1,4}$")
LONG_ASCII_RE = re.compile(r"[A-Za-z0-9]{24,}")
BREAK_MARKER = "\ue000"


@dataclass
class PageBlock:
    number: int
    kind: str = ""
    lines: list[str] = field(default_factory=list)


@dataclass
class MarkdownBook:
    title: str
    pages: list[PageBlock]
    markdown: Path
    source_kind: str


def load_plan() -> list[dict[str, str]]:
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    return list(payload["books"])


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + len("\n---\n") :]
    return text


def choose_markdown(slug: str, prefer_reviewed: bool) -> tuple[Path, str]:
    markdown_dir = ROOT / "books" / BOOK_ID / "markdown"
    reviewed = markdown_dir / f"{slug}.reviewed.md"
    raw = markdown_dir / f"{slug}.ocr.md"
    if prefer_reviewed and reviewed.exists():
        return reviewed, "OCR校订稿"
    if raw.exists():
        return raw, "OCR原稿"
    if reviewed.exists():
        return reviewed, "OCR校订稿"
    raise FileNotFoundError(f"No Markdown text found for {slug}: expected {reviewed} or {raw}")


def parse_markdown(path: Path, source_kind: str) -> MarkdownBook:
    text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    title = path.stem
    pages: list[PageBlock] = []
    current: PageBlock | None = None
    in_page = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current and current.lines and current.lines[-1] != "":
                current.lines.append("")
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        page_match = PAGE_RE.match(line)
        if page_match:
            current = PageBlock(number=int(page_match.group(1)))
            pages.append(current)
            in_page = True
            continue
        if not in_page or current is None:
            continue
        comment_match = COMMENT_RE.match(line)
        if comment_match:
            kind_match = KIND_RE.search(comment_match.group(1))
            if kind_match:
                current.kind = kind_match.group(1)
            continue
        current.lines.append(line)

    return MarkdownBook(title=title, pages=pages, markdown=path, source_kind=source_kind)


def tex_escape(text: str) -> str:
    text = LONG_ASCII_RE.sub(lambda match: break_long_ascii(match.group(0)), text)
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = "".join(replacements.get(char, char) for char in text)
    return escaped.replace(BREAK_MARKER, r"\allowbreak{}")


def break_long_ascii(text: str, width: int = 12) -> str:
    return BREAK_MARKER.join(text[index : index + width] for index in range(0, len(text), width))


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def should_join_with_space(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if CJK_RE.search(left[-1]) and CJK_RE.search(right[0]):
        return False
    if PUNCT_END_RE.search(left):
        return False
    return bool(LATIN_OR_DIGIT_RE.search(left[-1]) or LATIN_OR_DIGIT_RE.search(right[0]))


def join_lines(lines: list[str]) -> str:
    result = ""
    for line in lines:
        if not result:
            result = line
        elif should_join_with_space(result, line):
            result += " " + line
        else:
            result += line
    return result


def is_list_like(lines: list[str], kind: str) -> bool:
    content = [line for line in lines if line.strip()]
    if not content:
        return False
    if kind in {"figure_or_blank", "caption_or_map"}:
        return True
    if any(line in {"目录", "目 录"} for line in content):
        return True
    numbered = sum(1 for line in content if PAGE_NUMBER_LINE_RE.search(line))
    short = sum(1 for line in content if cjk_count(line) <= 18 and len(line) <= 38)
    if len(content) >= 4 and numbered >= max(2, len(content) // 3):
        return True
    return len(content) >= 5 and short >= int(len(content) * 0.75)


def page_blocks(lines: list[str], kind: str) -> list[tuple[str, str]]:
    groups: list[list[str]] = [[]]
    for line in lines:
        if not line.strip():
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(line)
    if groups and not groups[-1]:
        groups.pop()

    rendered: list[tuple[str, str]] = []
    for group in groups:
        if not group:
            continue
        if is_list_like(group, kind):
            rendered.extend(("list", line) for line in group)
        else:
            rendered.append(("para", join_lines(group)))
    return rendered


def page_kind_label(kind: str) -> str:
    return {
        "text": "正文",
        "caption_or_map": "图注/地图文字",
        "figure_or_blank": "图版/空白",
    }.get(kind, kind)


def title_for_pdf(title: str) -> str:
    title = re.sub(r"（OCR校订稿）$", "", title)
    title = title.replace("_ ", "：").replace("_", "：")
    title = title.replace(".金沙", "、金沙")
    title = re.sub(r"：\s+", "：", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def write_source(book: MarkdownBook, title: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rel_md = book.markdown.relative_to(ROOT)
    subtitle = f"{book.source_kind} TeX文本版"
    note = f"基于 {rel_md} 生成；正文为可见 TeX 排版文本，不是隐藏 OCR 文本层。"

    with output.open("w", encoding="utf-8") as handle:
        handle.write("% Auto-generated by scripts/ocr/markdown_to_sanxingdui_tex.py\n")
        handle.write(f"% Source Markdown: {rel_md}\n\n")
        handle.write(f"\\SXMeta{{{tex_escape(title)}}}{{ZhJpBook Sanxingdui OCR}}\n")
        handle.write(
            "\\SXTitle"
            f"{{{tex_escape(title)}}}"
            f"{{{tex_escape(subtitle)}}}"
            f"{{{tex_escape(str(rel_md))}}}"
            f"{{{tex_escape(note)}}}\n"
        )
        handle.write(f"\\SXChapter{{{tex_escape(title)}}}{{{tex_escape(subtitle)}}}\n")

        for page in book.pages:
            kind = page.kind or "text"
            handle.write(f"\\SXPage{{{page.number}}}{{{tex_escape(page_kind_label(kind))}}}\n")
            blocks = page_blocks(page.lines, kind)
            if not blocks:
                handle.write("\\SXFigureNote{本页当前文本为空。}\n")
                continue
            for block_kind, text in blocks:
                clean = text.strip()
                if not clean:
                    continue
                escaped = tex_escape(clean)
                if clean.startswith("[") and clean.endswith("]"):
                    handle.write(f"\\SXFigureNote{{{escaped}}}\n")
                elif block_kind == "list":
                    handle.write(f"\\SXListLine{{{escaped}}}\n")
                else:
                    handle.write(f"\\SXPara{{{escaped}}}\n")


def compile_tex(source: Path, output_dir: Path, jobname: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rel_source = source.relative_to(ROOT)
    tex_input = rf"\def\SXSource{{{rel_source.as_posix()}}}\input{{tex/sanxingdui-tex/book.tex}}"
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={jobname}",
        f"-output-directory={output_dir.relative_to(ROOT)}",
        tex_input,
    ]
    for _ in range(2):
        print("+ " + " ".join(cmd), flush=True)
        subprocess.check_call(cmd, cwd=ROOT)
    return output_dir / f"{jobname}.pdf"


def build_one(book_info: dict[str, str], args: argparse.Namespace) -> Path:
    slug = book_info["slug"]
    title = book_info["title"]
    markdown, source_kind = choose_markdown(slug, prefer_reviewed=not args.raw)
    book = parse_markdown(markdown, source_kind)
    output_dir = ROOT / "build" / EDITION_ID / slug
    source_tex = output_dir / "source.tex"
    display_title = title_for_pdf(title)
    write_source(book, display_title, source_tex)
    if args.no_compile:
        return source_tex
    pdf = compile_tex(source_tex, output_dir, slug)
    final_pdf = output_dir / f"{display_title}（TeX文本版）.pdf"
    for stale in output_dir.glob("*（TeX文本版）.pdf"):
        if stale != final_pdf:
            stale.unlink()
    if final_pdf.exists():
        final_pdf.unlink()
    shutil.copy2(pdf, final_pdf)
    return final_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", help="Render only this slug; may be repeated.")
    parser.add_argument("--raw", action="store_true", help="Use raw OCR Markdown even when reviewed Markdown exists.")
    parser.add_argument("--no-compile", action="store_true", help="Only write source.tex files.")
    args = parser.parse_args()

    wanted = set(args.slug or [])
    books = load_plan()
    unknown = wanted.difference(book["slug"] for book in books)
    if unknown:
        raise SystemExit(f"unknown slug(s): {', '.join(sorted(unknown))}")

    outputs: list[Path] = []
    for book in books:
        if wanted and book["slug"] not in wanted:
            continue
        output = build_one(book, args)
        outputs.append(output)
        print(f"built={book['slug']} output={output.relative_to(ROOT)}", flush=True)

    if not outputs:
        raise SystemExit("no books rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
