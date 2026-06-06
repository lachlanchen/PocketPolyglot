#!/usr/bin/env python3
"""Convert the interlinear JSON corpus into TeX macro calls."""

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

SENTENCE_FINAL_PUNCT = set("。！？!?；;")
OPENING_PUNCT = set("「『“‘（【《〈〔〖〘〚")
CLOSING_PUNCT = set("」』”’）】》〉〕〗〙〛")
OTHER_BOUNDARY_PUNCT = set("，、：:,.…—-")
NO_INSERT_AFTER_PUNCT = SENTENCE_FINAL_PUNCT | OPENING_PUNCT | CLOSING_PUNCT | OTHER_BOUNDARY_PUNCT
NO_INSERT_BEFORE_PUNCT = SENTENCE_FINAL_PUNCT | OPENING_PUNCT | CLOSING_PUNCT | OTHER_BOUNDARY_PUNCT


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


def tex_path_arg(path: str) -> str:
    return str(path).replace("\\", "/")


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


def brace(text: str) -> str:
    if not text:
        return "{}"
    return "{%\n" + text + "\n}"


def plain_tokens(tokens: list[dict[str, str]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def strip_trailing_closers(text: str) -> str:
    text = text.strip()
    while text and text[-1] in CLOSING_PUNCT:
        text = text[:-1].rstrip()
    return text


def ends_sentence(tokens: list[dict[str, str]]) -> bool:
    text = strip_trailing_closers(plain_tokens(tokens))
    return bool(text) and text[-1] in SENTENCE_FINAL_PUNCT


def copy_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(token) for token in tokens if isinstance(token, dict)]


def needs_join_punctuation(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    left_text = plain_tokens(left).strip()
    right_text = plain_tokens(right).strip()
    if not left_text or not right_text:
        return False
    if left_text[-1] in NO_INSERT_AFTER_PUNCT:
        return False
    if right_text[0] in NO_INSERT_BEFORE_PUNCT:
        return False
    return True


def join_tokens(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    inserted_punctuation: str = "",
) -> list[dict[str, Any]]:
    joined = copy_tokens(left)
    if inserted_punctuation and needs_join_punctuation(left, right):
        joined.append({"t": inserted_punctuation, "g": "function"})
    joined.extend(copy_tokens(right))
    return joined


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


def render_ja_lines(unit: dict[str, Any], indexes: list[int]) -> str:
    lines = unit.get("ja", [])
    rendered: list[str] = []
    for index in indexes:
        if index < len(lines) and isinstance(lines[index], list):
            line = render_tokens(lines[index], "jpruby", breakable=True)
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


def clone_unit(unit: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(unit)
    cloned["zh"] = copy_tokens(unit.get("zh", []))
    cloned["ja"] = [copy_tokens(line) for line in unit.get("ja", []) if isinstance(line, list)]
    if "ja_line_roles" in unit:
        cloned["ja_line_roles"] = list(unit.get("ja_line_roles") or [])
    return cloned


def merge_unit_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    merged["zh"] = join_tokens(left.get("zh", []), right.get("zh", []), inserted_punctuation="，")

    left_ja = left.get("ja", [])
    right_ja = right.get("ja", [])
    ja_lines: list[list[dict[str, Any]]] = []
    for index in range(max(len(left_ja), len(right_ja))):
        left_line = left_ja[index] if index < len(left_ja) and isinstance(left_ja[index], list) else []
        right_line = right_ja[index] if index < len(right_ja) and isinstance(right_ja[index], list) else []
        if left_line and right_line:
            ja_lines.append(join_tokens(left_line, right_line))
        elif left_line:
            ja_lines.append(copy_tokens(left_line))
        else:
            ja_lines.append(copy_tokens(right_line))
    merged["ja"] = ja_lines

    left_roles = list(left.get("ja_line_roles") or [])
    right_roles = list(right.get("ja_line_roles") or [])
    roles: list[str] = []
    for index in range(max(len(left_roles), len(right_roles))):
        role = left_roles[index] if index < len(left_roles) else ""
        if not role and index < len(right_roles):
            role = right_roles[index]
        roles.append(role)
    if roles:
        merged["ja_line_roles"] = roles
    return merged


def merge_continuation_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_units: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for unit in units:
        next_unit = clone_unit(unit)
        if current is None:
            current = next_unit
            continue
        if current.get("zh") and next_unit.get("zh") and not ends_sentence(current.get("zh", [])):
            current = merge_unit_pair(current, next_unit)
        else:
            merged_units.append(current)
            current = next_unit
    if current is not None:
        merged_units.append(current)
    return merged_units


def emit_unit(unit: dict[str, Any], *, secondary_ja_mode: str) -> str:
    zh = render_tokens(unit["zh"], "zhpy", breakable=True)
    ja_lines = unit.get("ja", [])
    if secondary_ja_mode == "merge":
        ja1 = render_ja_lines(unit, list(range(len(ja_lines))))
        ja2 = ""
    elif secondary_ja_mode == "auto":
        main_indexes: list[int] = []
        comment_indexes: list[int] = []
        for index in range(len(ja_lines)):
            if index > 0 and is_comment_ja_line(unit, index):
                comment_indexes.append(index)
            else:
                main_indexes.append(index)
        ja1 = render_ja_lines(unit, main_indexes)
        ja2 = render_ja_lines(unit, comment_indexes)
    else:
        ja1 = render_ja_lines(unit, [0])
        ja2 = render_ja_lines(unit, [1]) if secondary_ja_mode == "comment" else ""
    return "\n".join([r"\InterUnit", brace(zh), brace(ja1), brace(ja2), ""])


def convert(
    data: dict[str, Any],
    *,
    color_mode: str = "color",
    cover_image: str = "",
    author: str = "",
    author_reading: str = "",
    secondary_ja_mode: str = "auto",
    merge_continuation_units_enabled: bool = False,
) -> str:
    if color_mode == "blackwhite":
        cover_image = ""
    author_rendered = render_author(author, author_reading)
    out: list[str] = [
        "% Generated by scripts/interlinear/json_to_block_tex.py. Edit the JSON source, not this file.",
    ]
    if color_mode == "blackwhite":
        out.append(r"\BlackWhiteMode")
    out.extend(
        [
            rf"\InterPdfMeta{{{tex_escape(plain_tokens(data['title']['zh']))}}}{{{tex_escape(plain_tokens(data['title']['ja']))}}}",
            rf"\InterTitle{brace(render_tokens(data['title']['zh'], 'zhpy'))}{brace(render_tokens(data['title']['ja'], 'jpruby'))}{{{author_rendered}}}{{{tex_path_arg(cover_image)}}}",
            "",
        ]
    )

    for section in data.get("sections", []):
        out.append(
            rf"\InterSection{brace(render_tokens(section['title_zh'], 'zhpy'))}{brace(render_tokens(section['title_ja'], 'jpruby'))}"
        )
        for subsection in section.get("subsections", []):
            if has_title(subsection):
                out.append(
                    rf"\InterSubsection{brace(render_tokens(subsection['title_zh'], 'zhpy'))}{brace(render_tokens(subsection['title_ja'], 'jpruby'))}"
                )
            for story_index, story in enumerate(subsection.get("stories", [])):
                if story_index > 0:
                    out.append(r"\InterStoryPageBreak")
                title_zh = render_tokens(story["title_zh"], "zhpy")
                title_ja = render_tokens(story["title_ja"], "jpruby")
                place_zh = render_tokens(story.get("place_zh", []), "zhpy")
                place_ja = render_tokens(story.get("place_ja", []), "jpruby")
                out.append(rf"\InterStory{{{tex_escape(story['id'])}}}{brace(title_zh)}{brace(title_ja)}{brace(place_zh)}{brace(place_ja)}")
                for paragraph in story.get("paragraphs", []):
                    out.append(r"\InterParagraphStart")
                    units = paragraph.get("units", [])
                    if merge_continuation_units_enabled:
                        units = merge_continuation_units(units)
                    for unit in units:
                        out.append(emit_unit(unit, secondary_ja_mode=secondary_ja_mode))
                    out.append(r"\InterParagraphEnd")
                    out.append("")

    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="interlinear JSON source")
    parser.add_argument("-o", "--output", help="TeX output path; defaults to stdout")
    parser.add_argument("--author", default="")
    parser.add_argument("--author-reading", default="")
    parser.add_argument("--cover-image", default="")
    parser.add_argument("--color-mode", choices=["color", "blackwhite"], default="color")
    parser.add_argument("--hide-secondary-ja", action="store_true", help="do not render ja[1] explanatory/comment lines")
    parser.add_argument(
        "--secondary-ja-mode",
        choices=["auto", "comment", "hide", "merge"],
        default="auto",
        help="auto-detect explicit comment rows by ja_line_roles, force ja[1] as a note, hide it, or merge all Japanese rows",
    )
    parser.add_argument(
        "--merge-continuation-units",
        action="store_true",
        help="merge adjacent Chinese units inside a paragraph until sentence-final punctuation, inserting a comma if a split had no punctuation",
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    data = json.loads(source.read_text(encoding="utf-8"))
    secondary_ja_mode = "hide" if args.hide_secondary_ja else args.secondary_ja_mode
    result = convert(
        data,
        color_mode=args.color_mode,
        cover_image=args.cover_image,
        author=args.author,
        author_reading=args.author_reading,
        secondary_ja_mode=secondary_ja_mode,
        merge_continuation_units_enabled=args.merge_continuation_units,
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
