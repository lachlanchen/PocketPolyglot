#!/usr/bin/env python3
"""Audit and optionally normalize PocketPolyglot PDF language filenames.

The renderer stores language information in both directory names and PDF
filenames. This catches stale names such as an EN/ZH pair carrying a JP/ZH
title marker after a rebuild or export.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANG_TITLE_KEYS = {
    "en": ("book_title_en", "title_en"),
    "zh": ("book_title_zh", "book_title_zh_modern", "title_zh"),
    "ja": ("book_title_ja", "book_title_ja_modern", "title_ja"),
    "wenyan": ("book_title_wenyan",),
}
PAIR_SUFFIXES = ("zh-en", "zh-jp", "jp-en")
LANG_FROM_DIR = {"en": "en", "zh": "zh", "ja": "ja", "jp": "ja", "wenyan": "wenyan"}
EDITION_SUFFIX_RE = re.compile(r"（[^（）]*注(?:・黑白)?）$")
NOTE_LABEL = {
    "en": "英文",
    "zh": "中文",
    "ja": "日文",
    "wenyan": "文言",
}
QUAD_MAIN_NOTES = {
    "wenyan": ["ja", "zh", "en"],
    "zh_modern": ["wenyan", "ja", "en"],
    "ja_modern": ["wenyan", "zh", "en"],
    "en": ["wenyan", "ja", "zh"],
}


@dataclass(frozen=True)
class ExpectedName:
    book_id: str
    main_lang: str
    comments: tuple[str, ...]
    variant: str
    path: Path
    expected_stem: str


def clean_name(text: str) -> str:
    return str(text or "").strip().replace("/", "／").replace("\\", "＼")


def load_plans() -> dict[str, dict]:
    plans: dict[str, dict] = {}
    for plan_path in sorted((ROOT / "books").glob("*/book-plan.json")):
        try:
            plans[plan_path.parent.name] = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return plans


def title_for(plan: dict | None, book_id: str, lang: str) -> str:
    if plan:
        for key in LANG_TITLE_KEYS.get(lang, ()):
            value = clean_name(plan.get(key, ""))
            if value:
                return value
    return ""


def visible_title(stem: str) -> str:
    return clean_name(EDITION_SUFFIX_RE.sub("", stem))


def preferred_title(plan: dict | None, book_id: str, lang: str, current_stem: str) -> str:
    return title_for(plan, book_id, lang) or visible_title(current_stem) or book_id


def label_for(lang: str, *, modern: bool = False) -> str:
    if modern and lang == "ja":
        return "現代日本語"
    if modern and lang == "zh":
        return "現代中文"
    return NOTE_LABEL[lang]


def suffix_for_comments(comments: tuple[str, ...], variant: str, *, modern: bool = False) -> str:
    labels = [label_for(lang, modern=modern and lang in {"ja", "zh"}) for lang in comments]
    suffix = f"{'・'.join(labels)}注"
    if variant == "blackwhite":
        suffix = f"{suffix}・黑白"
    return f"（{suffix}）"


def quadrilingual_suffix(main_layer: str, comments: tuple[str, ...], variant: str) -> str:
    labels = [label_for(lang, modern=lang in {"ja", "zh"}) for lang in comments]
    main_label = {
        "wenyan": "",
        "zh_modern": "現代中文主文・",
        "ja_modern": "現代日本語主文・",
        "en": "英文主文・",
    }[main_layer]
    suffix = f"{main_label}{'・'.join(labels)}注"
    if variant == "blackwhite":
        suffix = f"{suffix}・黑白"
    return f"（{suffix}）"


def split_pair_book_id(book_part: str) -> tuple[str, str | None]:
    for pair in PAIR_SUFFIXES:
        suffix = f"-{pair}"
        if book_part.endswith(suffix):
            return book_part[: -len(suffix)], pair
    return book_part, None


def other_lang(pair: str, main_lang: str) -> str:
    langs = ["ja" if value == "jp" else value for value in pair.split("-")]
    for lang in langs:
        if lang != main_lang:
            return lang
    raise ValueError(f"cannot infer comment language from pair={pair} main={main_lang}")


def expected_from_build_parts(parts: tuple[str, ...], pdf: Path, plans: dict[str, dict]) -> ExpectedName | None:
    if len(parts) < 4:
        return None
    if parts[0] == "books" and "__" in pdf.stem:
        fields = pdf.stem.split("__", 3)
        if len(fields) != 4:
            return None
        book_part, direction, variant, current_title = fields
        if variant not in {"color", "blackwhite"} or not direction.endswith("-main"):
            return None
        book_id, pair = split_pair_book_id(book_part)
        main_code = direction.removesuffix("-main")
        main_lang = LANG_FROM_DIR.get(main_code)
        if not main_lang:
            return None
        if pair:
            comment = other_lang(pair, main_lang)
        elif main_lang == "zh":
            comment = "ja"
        elif main_lang == "ja":
            comment = "zh"
        else:
            return None
        plan = plans.get(book_id)
        title = preferred_title(plan, book_id, main_lang, current_title)
        expected = f"{book_part}__{direction}__{variant}__{title}{suffix_for_comments((comment,), variant)}"
        return ExpectedName(book_id, main_lang, (comment,), variant, pdf, expected)

    # build/<book>/en-main-jp-zh/<variant>/<file>.pdf
    if len(parts) == 4 and parts[1] == "en-main-jp-zh" and parts[2] in {"color", "blackwhite"}:
        book_id, _kind, variant, _filename = parts
        title = preferred_title(plans.get(book_id), book_id, "en", pdf.stem)
        expected = f"{title}{suffix_for_comments(('ja', 'zh'), variant)}"
        return ExpectedName(book_id, "en", ("ja", "zh"), variant, pdf, expected)

    # build/<book>/<pair>/<direction>/<variant>/<file>.pdf
    if len(parts) == 5 and parts[1] in PAIR_SUFFIXES and parts[3] in {"color", "blackwhite"}:
        book_id, pair, direction, variant, _filename = parts
        if not direction.endswith("-main"):
            return None
        main_lang = LANG_FROM_DIR.get(direction.removesuffix("-main"))
        if not main_lang:
            return None
        comment = other_lang(pair, main_lang)
        title = preferred_title(plans.get(book_id), book_id, main_lang, pdf.stem)
        expected = f"{title}{suffix_for_comments((comment,), variant)}"
        return ExpectedName(book_id, main_lang, (comment,), variant, pdf, expected)

    # build/<book>/<direction>/<variant>/<file>.pdf for ordinary bilingual builds.
    if len(parts) == 4 and parts[1] in {"zh-main", "jp-main"} and parts[2] in {"color", "blackwhite"}:
        book_id, direction, variant, _filename = parts
        main_lang = "zh" if direction == "zh-main" else "ja"
        comment = "ja" if main_lang == "zh" else "zh"
        title = preferred_title(plans.get(book_id), book_id, main_lang, pdf.stem)
        expected = f"{title}{suffix_for_comments((comment,), variant)}"
        return ExpectedName(book_id, main_lang, (comment,), variant, pdf, expected)

    # build/<book>/<main-layer>-main-quadrilingual/<variant>/<file>.pdf
    if len(parts) == 4 and parts[1].endswith("-main-quadrilingual") and parts[2] in {"color", "blackwhite"}:
        book_id, direction, variant, _filename = parts
        main_layer = direction.removesuffix("-main-quadrilingual")
        comments = tuple(QUAD_MAIN_NOTES.get(main_layer, ()))
        if not comments:
            return None
        title_lang = {
            "wenyan": "wenyan",
            "zh_modern": "zh",
            "ja_modern": "ja",
            "en": "en",
        }[main_layer]
        title = preferred_title(plans.get(book_id), book_id, title_lang, pdf.stem)
        expected = f"{title}{quadrilingual_suffix(main_layer, comments, variant)}"
        return ExpectedName(book_id, main_layer, comments, variant, pdf, expected)

    return None


def discover(root: Path, plans: dict[str, dict]) -> list[ExpectedName]:
    items: list[ExpectedName] = []
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.name == "book.pdf":
            continue
        try:
            parts = pdf.relative_to(root).parts
        except ValueError:
            continue
        expected = expected_from_build_parts(parts, pdf, plans)
        if expected:
            items.append(expected)
    return items


def sibling_with_stem(path: Path, expected_stem: str, suffix: str) -> Path:
    return path.with_name(f"{expected_stem}{suffix}")


def fix_name(item: ExpectedName) -> list[str]:
    actions: list[str] = []
    target = sibling_with_stem(item.path, item.expected_stem, item.path.suffix)
    if target == item.path:
        return actions
    if target.exists():
        actions.append(f"skip existing target: {item.path} -> {target}")
        return actions
    item.path.rename(target)
    actions.append(f"renamed pdf: {item.path} -> {target}")
    for ext in (".tex", ".cover.json"):
        sidecar = sibling_with_stem(item.path, item.path.stem, ext)
        if sidecar.exists():
            sidecar_target = sibling_with_stem(target, item.expected_stem, ext)
            if not sidecar_target.exists():
                sidecar.rename(sidecar_target)
                actions.append(f"renamed sidecar: {sidecar} -> {sidecar_target}")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "build", help="root folder to audit")
    parser.add_argument("--fix", action="store_true", help="rename mismatched PDFs in place")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    plans = load_plans()
    mismatches: list[ExpectedName] = []
    for item in discover(root, plans):
        if item.path.stem != item.expected_stem:
            mismatches.append(item)

    if not mismatches:
        print(f"ok: no language/title filename mismatches under {root}")
        return 0

    print(f"mismatches={len(mismatches)}")
    for item in mismatches:
        target = sibling_with_stem(item.path, item.expected_stem, item.path.suffix)
        print(f"{item.path.relative_to(root)}")
        print(f"  expected: {target.name}")
        if args.fix:
            for action in fix_name(item):
                print(f"  {action}")
    return 1 if not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
