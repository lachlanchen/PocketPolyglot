#!/usr/bin/env python3
"""Convert interlinear JSON into Japanese-main / Chinese-comment TeX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COMMENT_LINE_ROLES = {
    "comment",
    "explanatory_comment",
    "explanatory-comment",
    "explanation",
    "note",
    "annotation",
    "zhu",
    "注",
}


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def token_role(token: dict[str, str]) -> str:
    return str(token.get("g") or "")


def wrap_role(text: str, role: str) -> str:
    if not role:
        return text
    return rf"\Gram{{{tex_escape(role)}}}{{{text}}}"


def render_tokens(tokens: list[dict[str, str]], ruby_cmd: str, breakable: bool = False) -> str:
    parts: list[str] = []
    for token in tokens:
        raw_text = token.get("t", "")
        text = tex_escape(raw_text)
        ruby = tex_escape(token.get("r", ""))
        role = token_role(token)
        if ruby:
            rendered = rf"\{ruby_cmd}{{{text}}}{{{ruby}}}"
        elif breakable:
            rendered = r"\allowbreak{}".join(tex_escape(ch) for ch in raw_text)
        else:
            rendered = text
        parts.append(wrap_role(rendered, role))
        if breakable:
            parts.append(r"\allowbreak{}")
    return "".join(parts)


def render_ja_line(unit: dict[str, Any], index: int) -> str:
    lines = unit.get("ja", [])
    if index >= len(lines) or not isinstance(lines[index], list):
        return ""
    return render_tokens(lines[index], "jpruby", breakable=True)


def render_ja_lines(unit: dict[str, Any], indexes: list[int]) -> str:
    rendered: list[str] = []
    for index in indexes:
        line = render_ja_line(unit, index)
        if line:
            rendered.append(line)
    return "".join(rendered)


def ja_line_role(unit: dict[str, Any], index: int) -> str:
    roles = unit.get("ja_line_roles") or []
    if index >= len(roles):
        return ""
    return str(roles[index]).strip().lower()


def is_comment_ja_line(unit: dict[str, Any], index: int) -> bool:
    role = ja_line_role(unit, index)
    return role in COMMENT_LINE_ROLES


def brace(text: str) -> str:
    if not text:
        return "{}"
    return "{%\n" + text + "\n}"


def plain_tokens(tokens: list[dict[str, str]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def has_title(entry: dict[str, Any]) -> bool:
    return bool(
        plain_tokens(entry.get("title_zh", [])).strip()
        or plain_tokens(entry.get("title_ja", [])).strip()
    )


def render_author(author: str, author_reading: str) -> str:
    author = author.strip()
    if not author:
        return ""
    readings = [part for part in author_reading.strip().split() if part]
    if not readings:
        return tex_escape(author)
    if len(readings) == 1:
        return rf"\jpruby{{{tex_escape(author)}}}{{{tex_escape(readings[0])}}}"
    chars = list(author)
    if len(readings) == len(chars):
        groups = [(char, reading) for char, reading in zip(chars, readings)]
    elif len(readings) == 2 and len(chars) >= 2:
        split_at = (len(chars) + 1) // 2
        groups = [("".join(chars[:split_at]), readings[0]), ("".join(chars[split_at:]), readings[1])]
    else:
        groups = [(author, " ".join(readings))]
    return "".join(rf"\jpruby{{{tex_escape(text)}}}{{{tex_escape(reading)}}}" for text, reading in groups if text)


def emit_unit(unit: dict[str, Any], *, secondary_ja_mode: str) -> str:
    ja_lines = unit.get("ja", [])
    if secondary_ja_mode == "merge":
        ja_gloss = render_ja_lines(unit, list(range(len(ja_lines))))
        ja_comment = ""
    elif secondary_ja_mode == "auto":
        main_indexes: list[int] = []
        comment_indexes: list[int] = []
        for index in range(len(ja_lines)):
            if index > 0 and is_comment_ja_line(unit, index):
                comment_indexes.append(index)
            else:
                main_indexes.append(index)
        ja_gloss = render_ja_lines(unit, main_indexes)
        ja_comment = render_ja_lines(unit, comment_indexes)
    else:
        ja_gloss = render_ja_lines(unit, [0])
        ja_comment = render_ja_lines(unit, [1]) if secondary_ja_mode == "comment" else ""
    zh = render_tokens(unit["zh"], "zhpy", breakable=True)
    return "\n".join([r"\JpMainUnit", brace(ja_gloss), brace(ja_comment), brace(zh), ""])


def convert(
    data: dict[str, Any],
    *,
    author: str,
    author_reading: str,
    curated_by: str,
    curated_url: str,
    powered_by: str,
    cover_image: str,
    color_mode: str,
    secondary_ja_mode: str,
) -> str:
    title_ja = render_tokens(data["title"]["ja"], "jpruby")
    title_zh = render_tokens(data["title"]["zh"], "zhpy")
    author_rendered = render_author(author, author_reading)
    out: list[str] = [
        "% Generated by scripts/interlinear/json_to_jp_main_tex.py. Edit the JSON source, not this file.",
    ]
    if color_mode == "blackwhite":
        out.append(r"\BlackWhiteMode")
        cover_image = ""
    out.extend(
        [
            rf"\JpMainPdfMeta{{{tex_escape(plain_tokens(data['title']['ja']))}}}{{{tex_escape(plain_tokens(data['title']['zh']))}}}{{{tex_escape(author)}}}",
            rf"\JpMainTitle{brace(title_ja)}{brace(title_zh)}{{{author_rendered}}}{{{tex_escape(curated_by)}}}{{{tex_escape(curated_url)}}}{{{tex_escape(powered_by)}}}{{{tex_escape(cover_image)}}}",
            "",
        ]
    )

    for section in data.get("sections", []):
        out.append(
            rf"\JpMainSection{brace(render_tokens(section['title_ja'], 'jpruby'))}{brace(render_tokens(section['title_zh'], 'zhpy'))}"
        )
        for subsection in section.get("subsections", []):
            if has_title(subsection):
                out.append(
                    rf"\JpMainSubsection{brace(render_tokens(subsection['title_ja'], 'jpruby'))}{brace(render_tokens(subsection['title_zh'], 'zhpy'))}"
                )
            for story_index, story in enumerate(subsection.get("stories", [])):
                if story_index > 0:
                    out.append(r"\JpMainStoryPageBreak")
                title_ja_story = render_tokens(story["title_ja"], "jpruby")
                title_zh_story = render_tokens(story["title_zh"], "zhpy")
                place_ja = render_tokens(story.get("place_ja", []), "jpruby")
                place_zh = render_tokens(story.get("place_zh", []), "zhpy")
                out.append(
                    rf"\JpMainStory{{{tex_escape(story['id'])}}}{brace(title_ja_story)}{brace(title_zh_story)}{brace(place_ja)}{brace(place_zh)}"
                )
                for paragraph in story.get("paragraphs", []):
                    out.append(r"\JpMainParagraphStart")
                    for unit in paragraph.get("units", []):
                        out.append(emit_unit(unit, secondary_ja_mode=secondary_ja_mode))
                    out.append(r"\JpMainParagraphEnd")
                    out.append("")

    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="interlinear JSON source")
    parser.add_argument("-o", "--output", help="TeX output path; defaults to stdout")
    parser.add_argument("--author", default="夏目漱石")
    parser.add_argument("--author-reading", default="")
    parser.add_argument("--curated-by", default="AgInTiFlow curated")
    parser.add_argument("--curated-url", default="https://flow.lazying.art")
    parser.add_argument("--powered-by", default="powered by LazyingArt")
    parser.add_argument("--cover-image", default="")
    parser.add_argument("--color-mode", choices=["color", "blackwhite"], default="color")
    parser.add_argument("--hide-secondary-ja", action="store_true", help="do not render ja[1] explanatory/comment lines")
    parser.add_argument(
        "--secondary-ja-mode",
        choices=["auto", "comment", "hide", "merge"],
        default="auto",
        help="auto-detect explicit comment rows by ja_line_roles, force ja[1] as a note, hide it, or merge all Japanese rows",
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    data = json.loads(source.read_text(encoding="utf-8"))
    secondary_ja_mode = "hide" if args.hide_secondary_ja else args.secondary_ja_mode
    result = convert(
        data,
        author=args.author,
        author_reading=args.author_reading,
        curated_by=args.curated_by,
        curated_url=args.curated_url,
        powered_by=args.powered_by,
        cover_image=args.cover_image,
        color_mode=args.color_mode,
        secondary_ja_mode=secondary_ja_mode,
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
