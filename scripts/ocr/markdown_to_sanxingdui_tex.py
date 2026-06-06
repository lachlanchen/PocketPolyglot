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
POLISHED_EDITION_ID = "sanxingdui-polished-tex"
POCKET_EDITION_ID = "sanxingdui-tex-pocket"
POLISHED_POCKET_EDITION_ID = "sanxingdui-polished-tex-pocket"
BOOKLIKE_EDITION_ID = "sanxingdui-polished-booklike-tex"
BOOKLIKE_POCKET_EDITION_ID = "sanxingdui-polished-booklike-pocket"
TEMPLATE = ROOT / "tex" / "sanxingdui-tex" / "book.tex"
PLAN = ROOT / "books" / BOOK_ID / "book-plan.json"

PAGE_RE = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
COMMENT_RE = re.compile(r"^<!--\s*(.*?)\s*-->\s*$")
KIND_RE = re.compile(r"\bkind=([A-Za-z0-9_:-]+)")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9]")
PUNCT_END_RE = re.compile(r"[。！？；：，、,.!?;:）】》」』”’]$")
PAGE_NUMBER_LINE_RE = re.compile(r"\s+\d{1,4}$")
LONG_ASCII_RE = re.compile(r"[A-Za-z0-9]{18,}")
BREAK_MARKER = "\ue000"
BOOKLIKE_FIGURE_KINDS = {"figure_or_blank", "caption_or_map"}
BOOKLIKE_SKIP_KINDS = {"toc", "frontmatter"}
PLACEHOLDER_RE = re.compile(
    r"^\[?(?:图版页|地图页|图版页/地图页|本页当前文本为空|本页文字无法可靠识读|原页文字有限|地图页，文字有限)[^\]]*\]?$"
)
BOOKLIKE_META_SENTENCE_RE = re.compile(
    r"(^|[；;。])\s*"
    r"(?:本页为|原书第[^，。；;]*页)?"
    r"(?:图版页|图版或地图页|图版或说明页|图版页/地图页|地图页|空白页)"
    r"[^。；;]*"
    r"(?:文字(?:信息)?(?:有限|残缺|无法可靠恢复|无法可靠识读)|原页文字有限|题名和说明无法可靠恢复|当前文本为空)"
    r"[。；;]?"
)
TEXT_NORMALIZATION = str.maketrans(
    {
        "₀": "0",
        "₁": "1",
        "₂": "2",
        "₃": "3",
        "₄": "4",
        "₅": "5",
        "₆": "6",
        "₇": "7",
        "₈": "8",
        "₉": "9",
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
        "⁺": "+",
        "⁻": "-",
        "₊": "+",
        "₋": "-",
        "⁽": "(",
        "⁾": ")",
        "₍": "(",
        "₎": ")",
    }
)
BOOKLIKE_NO_TOC_HEADING_RE = re.compile(
    r"^(?:"
    r"图书在版编目|目录|图例|彩图目录|主编|摄影|翻译|责任编辑|封面设计|出版发行|"
    r"第[一二三四五六七八九十百零〇\d]+章|"
    r"原诗\s*译文|下部|"
    r"The\s+Whole\s+Collection|"
    r"(?:图版|拓片)[一二三四五六七八九十百〇零\dA-Za-z、，,.\s]*.*|"
    r"(?:表|附表|续表)[一二三四五六七八九十百〇零\dA-Za-z、，,.\s]*.*|"
    r".*(?:统计表|登记表|结果表|分析结果|检测限度|尺寸.*重量表|重量.*表)|"
    r"[A-Za-z]{1,3}[A-Za-z0-9ⅠⅡⅢⅣⅤⅥ]*[型式]?|"
    r"[A-Z][a-z]?[ⅠⅡⅢⅣⅤⅥ]+式|"
    r"[ⅠⅡⅢⅣⅤⅥ]+型|"
    r"NO\d+样|"
    r"[a-z]\.|"
    r".*\d+件"
    r")$",
    re.IGNORECASE,
)


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


def choose_markdown(slug: str, prefer_reviewed: bool, polished: bool) -> tuple[Path, str]:
    markdown_dir = ROOT / "books" / BOOK_ID / "markdown"
    polished_path = markdown_dir / f"{slug}.polished.md"
    reviewed = markdown_dir / f"{slug}.reviewed.md"
    raw = markdown_dir / f"{slug}.ocr.md"
    if polished:
        if polished_path.exists():
            return polished_path, "OCR润色校订稿"
        raise FileNotFoundError(f"No polished Markdown text found for {slug}: expected {polished_path}")
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
    text = text.translate(TEXT_NORMALIZATION)
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


def break_long_ascii(text: str, width: int = 8) -> str:
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


def flush_paragraph_group(rendered: list[tuple[str, str]], group: list[str], kind: str) -> None:
    if not group:
        return
    if is_list_like(group, kind):
        rendered.extend(("list", line) for line in group)
    else:
        rendered.append(("para", join_lines(group)))


def page_blocks(lines: list[str], kind: str) -> list[tuple[str, str]]:
    rendered: list[tuple[str, str]] = []
    group: list[str] = []
    for line in lines:
        if not line.strip():
            flush_paragraph_group(rendered, group, kind)
            group = []
            continue
        if line.startswith("### "):
            flush_paragraph_group(rendered, group, kind)
            group = []
            rendered.append(("heading", line[4:].strip()))
            continue
        if line.startswith("- "):
            flush_paragraph_group(rendered, group, kind)
            group = []
            rendered.append(("list", line[2:].strip()))
            continue
        if line.startswith("> "):
            flush_paragraph_group(rendered, group, kind)
            group = []
            rendered.append(("caption", line[2:].strip()))
            continue
        group.append(line)
    flush_paragraph_group(rendered, group, kind)
    return rendered


def is_placeholder_text(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    return bool(PLACEHOLDER_RE.match(text))


def clean_booklike_text(text: str) -> str:
    text = text.strip()
    if is_placeholder_text(text):
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if is_placeholder_text(inner):
            return ""
    text = BOOKLIKE_META_SENTENCE_RE.sub(lambda match: match.group(1), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip("；;。 ")


def heading_key(text: str) -> str:
    text = text.translate(TEXT_NORMALIZATION)
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()


def is_booklike_toc_heading(text: str, kind: str, title: str, seen: set[str]) -> bool:
    clean = text.strip()
    if not clean:
        return False
    if kind in {"frontmatter", "toc"}:
        return False
    if BOOKLIKE_NO_TOC_HEADING_RE.match(clean):
        return False
    if re.match(r"^\d+[.．]\s*", clean):
        return False
    if re.match(r"^\d{4}[—-]\d{4}$", clean):
        return False
    if re.match(r"^[A-Za-z][A-Za-z]?[ⅠⅡⅢⅣⅤⅥ0-9]*型\b", clean):
        return False
    if re.match(r"^[a-z][.．]\s*", clean, flags=re.IGNORECASE):
        return False
    if re.match(r"^[一二三四五六七八九十百〇零]{2,}\s*[A-Za-z]", clean):
        return False
    if re.search(r"(?:统计表|登记表|结果表|分析结果|检测限度|分解表|尺寸.*重量表|重量.*表)(?:（.*）)?$", clean):
        return False
    if clean in {"其他", "工具", "兵器", "戈", "璧"}:
        return False
    if len(clean) > 42 and not re.match(r"^[一二三四五六七八九十百〇零\d]+[、.．]", clean):
        return False
    key = heading_key(clean)
    title_key = heading_key(title)
    if key and title_key and (key == title_key or key in title_key or title_key in key):
        return False
    if key in seen:
        return False
    seen.add(key)
    return True


def caption_from_blocks(blocks: list[tuple[str, str]]) -> str:
    captions: list[str] = []
    headings: list[str] = []
    for block_kind, text in blocks:
        clean = text.strip()
        if is_placeholder_text(clean):
            continue
        if block_kind == "caption":
            captions.append(clean)
        elif block_kind == "heading":
            headings.append(clean)
    selected = captions or headings
    return "；".join(selected[:3])


def page_kind_label(kind: str) -> str:
    return {
        "frontmatter": "书名/版权",
        "toc": "目录",
        "text": "正文",
        "catalog": "图录/条目",
        "caption_or_map": "图注/地图文字",
        "figure_or_blank": "图版/空白",
        "notes": "附注",
    }.get(kind, kind)


def title_for_pdf(title: str) -> str:
    title = re.sub(r"（OCR校订稿）$", "", title)
    title = title.replace("_ ", "：").replace("_", "：")
    title = title.replace(".金沙", "、金沙")
    title = re.sub(r"：\s+", "：", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def render_page_image(source_pdf: Path, page_number: int, image_dir: Path, dpi: int) -> Path | None:
    image_dir.mkdir(parents=True, exist_ok=True)
    output = image_dir / f"page-{page_number:04d}.jpg"
    if output.exists() and output.stat().st_size > 0:
        return output
    prefix = image_dir / f"page-{page_number:04d}"
    cmd = [
        "pdftoppm",
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-singlefile",
        "-r",
        str(dpi),
        "-jpeg",
        "-jpegopt",
        "quality=86",
        str(source_pdf),
        str(prefix),
    ]
    try:
        subprocess.check_call(cmd, cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"warning: failed to render page image page={page_number} source={source_pdf}: {exc}", file=sys.stderr)
        return None
    return output if output.exists() else None


def write_source(
    book: MarkdownBook,
    title: str,
    output: Path,
    *,
    pocket: bool = False,
    source_pdf: Path | None = None,
    image_dir: Path | None = None,
    image_dpi: int = 170,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rel_md = book.markdown.relative_to(ROOT)
    subtitle = f"{book.source_kind} {'口袋' if pocket else ''}TeX文本版"
    image_note = "；并嵌入原书页图像以保留图版、地图与原始图注" if source_pdf and image_dir else ""
    note = f"基于 {rel_md} 生成；正文为可见 TeX 排版文本，不是隐藏 OCR 文本层{image_note}。"

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
            if source_pdf and image_dir:
                image_path = render_page_image(source_pdf, page.number, image_dir, image_dpi)
                if image_path:
                    rel_image = image_path.relative_to(ROOT).as_posix()
                    caption = f"原书第 {page.number} 页图像（保留图版与原始图注）"
                    handle.write(f"\\SXOriginalPageImage{{{rel_image}}}{{{tex_escape(caption)}}}\n")
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
                elif block_kind == "heading":
                    handle.write(f"\\SXHeading{{{escaped}}}\n")
                elif block_kind == "list":
                    handle.write(f"\\SXListLine{{{escaped}}}\n")
                elif block_kind == "caption":
                    handle.write(f"\\SXCaption{{{escaped}}}\n")
                else:
                    handle.write(f"\\SXPara{{{escaped}}}\n")


def write_booklike_source(
    book: MarkdownBook,
    title: str,
    output: Path,
    *,
    pocket: bool = False,
    source_pdf: Path | None = None,
    image_dir: Path | None = None,
    image_dpi: int = 170,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rel_md = book.markdown.relative_to(ROOT)
    subtitle = f"{book.source_kind} {'口袋' if pocket else ''}图文书版"
    note = f"基于 {rel_md} 重新排为连续图文书；保留可读正文、标题、目录线索、图版与图注。"

    with output.open("w", encoding="utf-8") as handle:
        handle.write("% Auto-generated by scripts/ocr/markdown_to_sanxingdui_tex.py\n")
        handle.write("% Booklike Sanxingdui edition; no original page boundary labels.\n")
        handle.write(f"% Source Markdown: {rel_md}\n\n")
        handle.write(f"\\SXMeta{{{tex_escape(title)}}}{{ZhJpBook Sanxingdui OCR}}\n")
        handle.write(
            "\\SXTitle"
            f"{{{tex_escape(title)}}}"
            f"{{{tex_escape(subtitle)}}}"
            "{}"
            f"{{{tex_escape(note)}}}\n"
        )
        handle.write(f"\\SXChapter{{{tex_escape(title)}}}{{{tex_escape(subtitle)}}}\n")

        seen_toc_headings: set[str] = set()

        for page in book.pages:
            kind = page.kind or "text"
            if kind in BOOKLIKE_SKIP_KINDS:
                continue
            blocks = page_blocks(page.lines, kind)
            real_blocks = [
                (block_kind, clean)
                for block_kind, text in blocks
                if (clean := clean_booklike_text(text))
            ]

            figure_emitted = False
            if source_pdf and image_dir and kind in BOOKLIKE_FIGURE_KINDS:
                image_path = render_page_image(source_pdf, page.number, image_dir, image_dpi)
                if image_path:
                    rel_image = image_path.relative_to(ROOT).as_posix()
                    handle.write(f"\\SXBookFigure{{{rel_image}}}{{{tex_escape(caption_from_blocks(real_blocks))}}}\n")
                    figure_emitted = True

            for block_kind, clean in real_blocks:
                if figure_emitted and block_kind in {"caption", "heading"}:
                    continue
                escaped = tex_escape(clean)
                if block_kind == "heading":
                    if is_booklike_toc_heading(clean, kind, title, seen_toc_headings):
                        handle.write(f"\\SXSection{{{escaped}}}\n")
                    else:
                        handle.write(f"\\SXHeading{{{escaped}}}\n")
                elif block_kind == "list":
                    handle.write(f"\\SXListLine{{{escaped}}}\n")
                elif block_kind == "caption":
                    handle.write(f"\\SXCaption{{{escaped}}}\n")
                else:
                    handle.write(f"\\SXPara{{{escaped}}}\n")


def compile_tex(source: Path, output_dir: Path, jobname: str, *, pocket: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rel_source = source.relative_to(ROOT)
    mode = r"\def\SXPocketMode{1}" if pocket else ""
    tex_input = rf"{mode}\def\SXSource{{{rel_source.as_posix()}}}\input{{tex/sanxingdui-tex/book.tex}}"
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
    markdown, source_kind = choose_markdown(slug, prefer_reviewed=not args.raw, polished=args.polished)
    book = parse_markdown(markdown, source_kind)
    if args.edition_id:
        edition_id = args.edition_id
    elif args.booklike and args.pocket:
        edition_id = BOOKLIKE_POCKET_EDITION_ID
    elif args.booklike:
        edition_id = BOOKLIKE_EDITION_ID
    elif args.pocket and args.polished:
        edition_id = POLISHED_POCKET_EDITION_ID
    elif args.pocket:
        edition_id = POCKET_EDITION_ID
    else:
        edition_id = POLISHED_EDITION_ID if args.polished else EDITION_ID
    output_dir = ROOT / "build" / edition_id / slug
    source_tex = output_dir / "source.tex"
    display_title = title_for_pdf(title)
    include_page_images = args.include_page_images or ((args.polished or args.booklike) and not args.no_page_images)
    source_pdf = ROOT / book_info["source"] if include_page_images else None
    if include_page_images and args.reuse_page_images_from_edition:
        image_dir = ROOT / "build" / args.reuse_page_images_from_edition / slug / "page-images"
    else:
        image_dir = output_dir / "page-images" if include_page_images else None
    image_dpi = args.image_dpi if args.image_dpi else (120 if args.pocket else 170)
    writer = write_booklike_source if args.booklike else write_source
    writer(
        book,
        display_title,
        source_tex,
        pocket=args.pocket,
        source_pdf=source_pdf,
        image_dir=image_dir,
        image_dpi=image_dpi,
    )
    if args.no_compile:
        return source_tex
    pdf = compile_tex(source_tex, output_dir, slug, pocket=args.pocket)
    if args.booklike:
        suffix = "润色TeX图文口袋版" if args.pocket else "润色TeX图文书版"
    else:
        suffix = ("润色TeX口袋版" if args.pocket else "润色TeX文本版") if args.polished else ("TeX口袋版" if args.pocket else "TeX文本版")
    final_pdf = output_dir / f"{display_title}（{suffix}）.pdf"
    for stale in output_dir.glob("*（*TeX文本版）.pdf"):
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
    parser.add_argument("--polished", action="store_true", help="Use <slug>.polished.md and write sanxingdui-polished-tex output.")
    parser.add_argument("--booklike", action="store_true", help="Render a continuous self-contained figure/text book without original page labels.")
    parser.add_argument("--edition-id", help="Override build/<edition-id>/ output folder.")
    parser.add_argument("--pocket", action="store_true", help="Compile an A6 pocket-size version into build/<sanxingdui-*-pocket>/ by default.")
    parser.add_argument("--include-page-images", action="store_true", help="Render and include original PDF page images.")
    parser.add_argument("--no-page-images", action="store_true", help="Disable default page images for polished output.")
    parser.add_argument("--image-dpi", type=int, default=0, help="DPI for original page images included in TeX; defaults to 170, or 120 in pocket mode.")
    parser.add_argument(
        "--reuse-page-images-from-edition",
        help="Reuse build/<edition>/<slug>/page-images instead of writing page images into the current output folder.",
    )
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
