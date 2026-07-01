#!/usr/bin/env python3
"""Prepare classical Chinese source trees as quadrilingual wenyan-main tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PLAN = ROOT / "data" / "source-plan" / "classical-quadrilingual-source-batch.json"

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SPACE_RE = re.compile(r"\s+")
SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]")
TRAILING_PAGE_CHROME_RE = re.compile(r"(NewPP limit report|Transclusion expansion time report|Saved in parser cache)", re.I)
SANGUOZHI_VOLUME_RE = re.compile(r"卷\s*0*(\d+)")
CLASSICAL_VOLUME_RE = re.compile(r"卷\s*0*(\d+)\s*([上中下])?")
SOURCE_FILE_PREFIX_RE = re.compile(r"(?:^|/)(\d+)-")
CHAPTER_ORDINAL_RE = re.compile(r"([一二三四五六七八九十百〇零]+)$")
WIKI_LINK_RE = re.compile(r"\[\[([^]\|#]+)(?:#[^]\|]*)?(?:\|([^]\n]+))?\]\]")
VOLUME_PART_ORDER = {"": 0, "上": 1, "中": 2, "下": 3}

ZUOZHUAN_CANONICAL_ORDER = {
    "序": 0,
    "隱公": 1,
    "桓公": 2,
    "莊公": 3,
    "閔公": 4,
    "僖公": 5,
    "文公": 6,
    "宣公": 7,
    "成公": 8,
    "襄公": 9,
    "昭公": 10,
    "定公": 11,
    "哀公": 12,
}

ZHANGUOCE_STATE_ORDER = {
    "東周": 1,
    "西周": 2,
    "秦": 3,
    "齊": 4,
    "楚": 5,
    "趙": 6,
    "魏": 7,
    "韓": 8,
    "燕": 9,
    "宋衛": 10,
    "中山": 11,
}

SHANHAIJING_CANONICAL_ORDER = {
    "郭璞序": 0,
    "南山經": 1,
    "西山經": 2,
    "北山經": 3,
    "東山經": 4,
    "中山經": 5,
    "海外南經": 6,
    "海外西經": 7,
    "海外北經": 8,
    "海外東經": 9,
    "海內南經": 10,
    "海內西經": 11,
    "海內北經": 12,
    "海內東經": 13,
    "大荒東經": 14,
    "大荒南經": 15,
    "大荒西經": 16,
    "大荒北經": 17,
    "海內經": 18,
}

ANTHOLOGY_STANDALONE_BOOKS = {"chuci", "foguoji", "platform-sutra", "tangshi-sanbai"}
CHUCI_SKIP_TITLES = {"楚辭", "楚辭章句", "楚辭補注", "屈原賦注"}
CHUCI_CANONICAL_ORDER = {
    "離騷": 1,
    "九歌": 2,
    "天問": 3,
    "九章": 4,
    "遠遊": 5,
    "卜居": 6,
    "漁父": 7,
    "九辯": 8,
    "招魂": 9,
    "大招": 10,
    "惜誓": 11,
    "招隱士": 12,
    "七諫": 13,
    "哀時命": 14,
    "九懷": 15,
    "九歎": 16,
    "九思": 17,
}

YIJING_CANONICAL_ORDER = {
    "乾": 1,
    "坤": 2,
    "屯": 3,
    "蒙": 4,
    "需": 5,
    "訟": 6,
    "師": 7,
    "比": 8,
    "小畜": 9,
    "履": 10,
    "泰": 11,
    "否": 12,
    "同人": 13,
    "大有": 14,
    "謙": 15,
    "豫": 16,
    "隨": 17,
    "蠱": 18,
    "臨": 19,
    "觀": 20,
    "噬嗑": 21,
    "賁": 22,
    "剝": 23,
    "復": 24,
    "无妄": 25,
    "大畜": 26,
    "頤": 27,
    "大過": 28,
    "坎": 29,
    "離": 30,
    "咸": 31,
    "恒": 32,
    "遯": 33,
    "大壯": 34,
    "晉": 35,
    "明夷": 36,
    "家人": 37,
    "睽": 38,
    "蹇": 39,
    "解": 40,
    "損": 41,
    "益": 42,
    "夬": 43,
    "姤": 44,
    "萃": 45,
    "升": 46,
    "困": 47,
    "井": 48,
    "革": 49,
    "鼎": 50,
    "震": 51,
    "艮": 52,
    "漸": 53,
    "歸妹": 54,
    "豐": 55,
    "旅": 56,
    "巽": 57,
    "兌": 58,
    "渙": 59,
    "節": 60,
    "中孚": 61,
    "小過": 62,
    "既濟": 63,
    "未濟": 64,
    "彖": 65,
    "大象": 66,
    "小象": 67,
    "文言": 68,
    "繫辭上": 69,
    "繫辭下": 70,
    "說卦": 71,
    "序卦": 72,
    "雜卦": 73,
}

ROMAN_TO_INT = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
    "XXI": 21,
    "XXII": 22,
    "XXIII": 23,
    "XXIV": 24,
    "XXV": 25,
    "XXVI": 26,
    "XXVII": 27,
    "XXVIII": 28,
    "XXIX": 29,
    "XXX": 30,
    "XXXI": 31,
    "XXXII": 32,
    "XXXIII": 33,
}

WATSON_TITLES = {
    1: "Free and Easy Wandering",
    2: "Discussion on Making All Things Equal",
    3: "The Secret of Caring for Life",
    4: "In the World of Men",
    5: "The Sign of Virtue Complete",
    6: "The Great and Venerable Teacher",
    7: "Fit for Emperors and Kings",
    8: "Webbed Toes",
    9: "Horses' Hoofs",
    10: "Rifling Trunks",
    11: "Let It Be, Leave It Alone",
    12: "Heaven and Earth",
    13: "The Way of Heaven",
    14: "The Turning of Heaven",
    15: "Constrained in Will",
    16: "Mending the Inborn Nature",
    17: "Autumn Floods",
    18: "Supreme Happiness",
    19: "Mastering Life",
    20: "The Mountain Tree",
    21: "Tian Zifang",
    22: "Knowledge Wandered North",
    23: "Gengsang Chu",
    24: "Xu Wugui",
    25: "Zeyang",
    26: "External Things",
    27: "Imputed Words",
    28: "Giving Away a Throne",
    29: "Robber Zhi",
    30: "Discoursing on Swords",
    31: "The Old Fisherman",
    32: "Lie Yukou",
    33: "The World",
}

ZHUANGZI_CANONICAL_ORDER = {
    "逍遙遊": 1,
    "齊物論": 2,
    "養生主": 3,
    "人間世": 4,
    "德充符": 5,
    "大宗師": 6,
    "應帝王": 7,
    "駢拇": 8,
    "馬蹄": 9,
    "胠篋": 10,
    "在宥": 11,
    "天地": 12,
    "天道": 13,
    "天運": 14,
    "刻意": 15,
    "繕性": 16,
    "秋水": 17,
    "至樂": 18,
    "達生": 19,
    "山木": 20,
    "田子方": 21,
    "知北遊": 22,
    "庚桑楚": 23,
    "徐無鬼": 24,
    "則陽": 25,
    "外物": 26,
    "寓言": 27,
    "讓王": 28,
    "盜跖": 29,
    "說劍": 30,
    "漁父": 31,
    "列禦寇": 32,
    "天下": 33,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    if not path.exists() or path.is_dir():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\u3000", "").replace("\xa0", "")
    text = SPACE_RE.sub("", text)
    text = text.strip()
    if TRAILING_PAGE_CHROME_RE.search(text):
        return ""
    return text


def clean_reference_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t\u3000\xa0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def excerpt(text: str, limit: int = 4200) -> str:
    return clean_reference_text(text)[:limit]


def pdftotext(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["pdftotext", "-layout", str(path), "-"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return ""


def epub_text(path: Path) -> str:
    if not path.exists():
        return ""
    parts: list[str] = []
    try:
        with ZipFile(path) as archive:
            html_names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith((".html", ".htm", ".xhtml"))
            )
            for name in html_names:
                soup = BeautifulSoup(archive.read(name), "html.parser")
                text = soup.get_text("\n", strip=True)
                if text:
                    parts.append(text)
    except Exception:
        return ""
    return clean_reference_text("\n\n".join(parts))


def normalized_heading(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def line_window_by_headings(
    lines: list[str],
    headings: dict[int, str],
    *,
    min_line: int = 0,
    max_chars: int = 4200,
) -> dict[int, dict[str, str]]:
    starts: list[tuple[int, int]] = []
    used_lines: set[int] = set()
    for number, heading in headings.items():
        target = normalized_heading(heading)
        best_index = -1
        for index in range(min_line, len(lines)):
            if index in used_lines:
                continue
            block = normalized_heading(" ".join(lines[index : index + 3]))
            if target and target in block:
                best_index = index
                break
        if best_index >= 0:
            starts.append((number, best_index))
            used_lines.add(best_index)
    starts.sort(key=lambda item: item[1])
    windows: dict[int, dict[str, str]] = {}
    for offset, (number, start) in enumerate(starts):
        end = starts[offset + 1][1] if offset + 1 < len(starts) else min(len(lines), start + 500)
        block = "\n".join(lines[start:end])
        windows[number] = {
            "chapter_number": str(number),
            "line_window": f"{start + 1}-{end}",
            "excerpt": excerpt(block, max_chars),
        }
    return windows


def zh_number_to_int(text: str) -> int:
    values = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if not text:
        return 0
    if text == "十":
        return 10
    if "百" in text:
        left, _, right = text.partition("百")
        return (values.get(left, 1) if left else 1) * 100 + zh_number_to_int(right)
    if "十" in text:
        left, _, right = text.partition("十")
        return (values.get(left, 1) if left else 1) * 10 + (values.get(right, 0) if right else 0)
    total = 0
    for char in text:
        total = total * 10 + values.get(char, 0)
    return total


def title_tail(title: str) -> str:
    return title.split("/")[-1].strip()


def normalize_title_key(title: str) -> str:
    title = clean_wiki_markup(title)
    title = title.replace("_", " ").replace("䰟", "魂")
    title = SPACE_RE.sub(" ", title).strip()
    return title


def title_order_keys(title: str) -> list[str]:
    full = normalize_title_key(title)
    tail = normalize_title_key(title_tail(full))
    stripped_tail = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", tail).strip()
    keys = [full, tail, stripped_tail]
    return [key for index, key in enumerate(keys) if key and key not in keys[:index]]


def source_sequence_key(path_name: str) -> int:
    match = SOURCE_FILE_PREFIX_RE.search(path_name)
    return int(match.group(1)) if match else 9999


def should_skip_source_item(book_id: str, title: str) -> bool:
    tail = title_tail(title)
    if book_id == "zuozhuan" and tail == "全覽":
        return True
    if book_id == "vimalakirti-sutra" and tail in {"1", "2", "3"}:
        return True
    return False


def normalize_chapter_title(book_id: str, title: str) -> str:
    parts = [part.strip() for part in title.split("/") if part.strip()]
    tail = title_tail(title)
    if book_id == "sanguozhi":
        return tail.replace("卷", "卷 ")
    if book_id == "zhanguoce" and len(parts) > 2:
        return " ".join(parts[1:])
    if book_id == "shui-jing-zhu" and tail.isdigit():
        return f"卷 {tail}"
    return tail


def first_template_body(text: str, names: set[str]) -> str:
    lowered = text.lower()
    starts = [
        lowered.find("{{" + name.lower())
        for name in names
        if lowered.find("{{" + name.lower()) >= 0
    ]
    if not starts:
        return ""
    index = min(starts)
    depth = 1
    end = index + 2
    while end < len(text) and depth:
        if text.startswith("{{", end):
            depth += 1
            end += 2
        elif text.startswith("}}", end):
            depth -= 1
            end += 2
        else:
            end += 1
    return text[index + 2 : end - 2] if depth == 0 else ""


def top_level_template_field(body: str, field: str) -> str:
    pattern = re.compile(
        rf"(?:^|\|)\s*{re.escape(field)}\s*=\s*(.*?)(?=\|\s*[A-Za-z_][A-Za-z0-9_ -]*\s*=|\Z)",
        re.S,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def clean_wiki_header_field(text: str) -> str:
    text = clean_wiki_markup(text)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("../", "").replace("《", "").replace("》", "")
    return text.strip()


def extract_raw_wiki_header_section(path: Path) -> str:
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = first_template_body(raw, {"header", "header2"})
    title = clean_wiki_header_field(top_level_template_field(body, "title")) if body else ""
    section = clean_wiki_header_field(top_level_template_field(body, "section")) if body else ""
    if "志" in title and "第" in title:
        section_head = section.split(" ", 1)[0] if section else ""
        if section_head and section_head not in title and len(section_head) <= 8:
            return f"{title} {section_head}"
        return title
    if section:
        return section
    if title and title not in {"../", ".."}:
        return title
    for line in raw.splitlines()[:40]:
        text = clean_text(clean_wiki_markup(line.replace("__TOC__", "")))
        if text.startswith("後漢書卷") or text.startswith("漢書卷"):
            return text.replace("　", " ").strip()
    return ""


def meaningful_chapter_title(book_id: str, title: str, header_text: str) -> str:
    base = normalize_chapter_title(book_id, title)
    header = str(header_text or "").replace("\u3000", " ").replace("\xa0", " ")
    header = re.sub(r"\s+", " ", header).strip()
    if book_id in {"han-shu", "hou-han-shu"} and header:
        if header.startswith(("卷", "巻")):
            return header
        if base and header != base:
            return f"{base} {header}"
    if book_id == "vimalakirti-sutra" and header:
        return header
    return base


def is_source_footer_paragraph(text: str) -> bool:
    text = clean_text(text)
    return (
        text.startswith("此作品在全世界都属于公有领域")
        or text.startswith("This work is in the public domain")
        or text.startswith("この作品はパブリックドメイン")
    )


def expand_chapter_anchors(book: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchors = book.get("chapter_anchors") or []
    if not anchors:
        return items
    expanded: list[dict[str, Any]] = []
    missing = {str(anchor["starts_with"]) for anchor in anchors}
    for item in items:
        current: dict[str, Any] | None = None
        for paragraph in item["paragraphs"]:
            matched_anchor = next(
                (anchor for anchor in anchors if paragraph.startswith(str(anchor["starts_with"]))),
                None,
            )
            if matched_anchor:
                missing.discard(str(matched_anchor["starts_with"]))
                current = {
                    **item,
                    "chapter_title": str(matched_anchor["title_wenyan"]),
                    "chapter_title_wenyan": str(matched_anchor["title_wenyan"]),
                    "chapter_title_zh_modern": str(matched_anchor.get("title_zh_modern") or matched_anchor["title_wenyan"]),
                    "chapter_title_ja_modern": str(matched_anchor.get("title_ja_modern") or matched_anchor["title_wenyan"]),
                    "chapter_title_en": str(matched_anchor.get("title_en") or matched_anchor["title_wenyan"]),
                    "paragraphs": [],
                }
                expanded.append(current)
            if current is None:
                current = {**item, "paragraphs": []}
                expanded.append(current)
            current["paragraphs"].append(paragraph)
    if missing:
        raise ValueError(f"{book['book_id']}: missing chapter anchors: {sorted(missing)!r}")
    return [item for item in expanded if item["paragraphs"]]


def canonical_chuci_key(title: str) -> str:
    key = title_order_keys(title)[-1]
    return key.replace("招䰟", "招魂")


def resolve_wiki_link_title(root_title: str, target: str) -> str:
    target = target.strip()
    if target.startswith("/"):
        return f"{root_title}{target}"
    return target


def root_wiki_link_order(
    book_id: str,
    source_dir: Path,
    items: list[dict[str, Any]],
    root_title: str,
) -> dict[str, int]:
    if book_id not in {"shijing", "tangshi-sanbai"}:
        return {}
    root_items = [item for item in items if normalize_title_key(str(item.get("title", ""))) == root_title]
    order: dict[str, int] = {}
    if not root_items:
        return order
    raw_rel = root_items[0].get("raw")
    raw_path = source_dir / raw_rel if raw_rel else Path()
    if not raw_path.exists():
        return order
    sequence = 0
    for line in raw_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.lstrip().startswith("#"):
            continue
        for match in WIKI_LINK_RE.finditer(line):
            target = resolve_wiki_link_title(root_title, match.group(1))
            low = target.lower()
            if low.startswith(("category:", "file:", "image:")):
                continue
            sequence += 1
            for key in title_order_keys(target):
                order.setdefault(key, sequence)
    return order


def chapter_sort_key(
    book_id: str,
    title: str,
    html_name: str,
    header_text: str,
    root_order: dict[str, int] | None = None,
) -> tuple[int, str]:
    tail = title_tail(title)
    if root_order:
        for key in title_order_keys(title):
            if key in root_order:
                return (root_order[key], key)
    if book_id == "yijing":
        return (YIJING_CANONICAL_ORDER.get(tail, 9000 + source_sequence_key(html_name)), tail)
    if book_id == "zhuangzi":
        number = ZHUANGZI_CANONICAL_ORDER.get(tail)
        if not number:
            match = CHAPTER_ORDINAL_RE.search(header_text)
            number = zh_number_to_int(match.group(1)) if match else 0
        return (number or 9999, tail)
    if book_id == "sanguozhi":
        if "上三国志註表" in tail or "上三國志註表" in tail:
            return (0, tail)
        match = SANGUOZHI_VOLUME_RE.search(tail) or SANGUOZHI_VOLUME_RE.search(html_name)
        return (int(match.group(1)) if match else 9999, tail)
    if book_id in {"han-shu", "hou-han-shu"}:
        if book_id == "hou-han-shu" and tail == "注補續漢書八志序":
            return (905, tail)
        match = CLASSICAL_VOLUME_RE.search(tail) or CLASSICAL_VOLUME_RE.search(html_name)
        if match:
            part = match.group(2) or ""
            return (int(match.group(1)) * 10 + VOLUME_PART_ORDER.get(part, 0), tail)
    if book_id == "zuozhuan":
        return (ZUOZHUAN_CANONICAL_ORDER.get(tail, 9999), tail)
    if book_id == "zhanguoce":
        parts = [part.strip() for part in title.split("/") if part.strip()]
        if len(parts) >= 3 and parts[-2] in ZHANGUOCE_STATE_ORDER:
            return (1000 + ZHANGUOCE_STATE_ORDER[parts[-2]] * 100 + zh_number_to_int(parts[-1]), title)
        if tail in ZHANGUOCE_STATE_ORDER:
            return (1000 + ZHANGUOCE_STATE_ORDER[tail] * 100, title)
        return (source_sequence_key(html_name), title)
    if book_id == "shanhaijing":
        return (SHANHAIJING_CANONICAL_ORDER.get(tail, 9000 + source_sequence_key(html_name)), tail)
    if book_id == "chuci":
        return (CHUCI_CANONICAL_ORDER.get(canonical_chuci_key(tail), 9000 + source_sequence_key(html_name)), tail)
    if book_id == "xu-xiake-youji":
        for prefix, base in (
            ("滇遊日記", 1200),
            ("粵西遊日記", 1300),
            ("黔遊日記", 1700),
            ("雞山志略", 1600),
        ):
            if tail.startswith(prefix):
                suffix = tail.removeprefix(prefix)
                return (base + zh_number_to_int(suffix), tail)
        return (source_sequence_key(html_name), tail)
    if book_id == "shui-jing-zhu":
        if tail == "原序":
            return (0, tail)
        if tail.isdigit():
            return (int(tail), tail)
        return (source_sequence_key(html_name), tail)
    return (source_sequence_key(html_name), tail)


def clean_soup_for_source(content: BeautifulSoup, *, drop_small: bool) -> None:
    selectors = [
        "style",
        "script",
        "table",
        "ul#plainSister",
        ".noprint",
        ".sisitem",
        ".variant-tooltip",
        "sup",
        "link",
        "figure",
    ]
    for selector in selectors:
        for tag in content.select(selector):
            tag.decompose()
    if drop_small:
        for tag in content.find_all("small"):
            tag.decompose()


def extract_html_paragraphs(path: Path, *, drop_small: bool) -> tuple[str, list[str]]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    content = soup.select_one(".mw-parser-output") or soup
    clean_soup_for_source(content, drop_small=drop_small)
    header_text = clean_text("".join(item.get_text("", strip=True) for item in soup.find_all("title")[:1]))
    paragraphs: list[str] = []
    for node in content.find_all("p"):
        text = clean_text(node.get_text("", strip=False))
        if not text or not HAN_RE.search(text):
            continue
        if text.startswith("Source:") or text in {"←", "→"}:
            continue
        paragraphs.append(text)
    return header_text, paragraphs


def remove_balanced_templates(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            depth = 1
            end = index + 2
            while end < len(text) and depth:
                if text.startswith("{{", end):
                    depth += 1
                    end += 2
                elif text.startswith("}}", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            body = text[index + 2 : end - 2] if depth == 0 else text[index + 2 :]
            name, _, rest = body.partition("|")
            name = name.strip()
            if name in {"YL", "lang", "j", "zh"}:
                out.append(rest.split("|", 1)[0].strip())
            elif name == "另":
                out.append(rest.split("|", 1)[0].strip())
            elif name in {"*"}:
                pass
            else:
                pass
            index = end
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def clean_wiki_markup(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = remove_balanced_templates(text)
    text = re.sub(r"-\{(?:[^{}|]*\|)?([^{}|]+)\}-", r"\1", text)
    text = re.sub(r"\[\[(?:File|Image):[^\]\n]+\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[([^]|\n]+)\|([^]\n]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^]\n]+)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    return text


def extract_raw_wiki_paragraphs(path: Path) -> tuple[str, list[str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if re.match(r"^\s*#\s*(?:重定向|redirect)\s*", raw, flags=re.I):
        return "", []
    raw = clean_wiki_markup(raw)
    header_text = ""
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = clean_text("".join(buffer))
        buffer = []
        if text and HAN_RE.search(text):
            paragraphs.append(text)

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("[[Category:") or stripped.startswith("__"):
            continue
        stripped = re.sub(r"^[*#:;]+\s*", "", stripped)
        if re.fullmatch(r"周易/.+", stripped):
            continue
        heading = re.fullmatch(r"=+\s*(.+?)\s*=+", stripped)
        if heading:
            flush()
            if not header_text:
                header_text = clean_text(heading.group(1))
            continue
        if stripped.startswith("|") or stripped.startswith("{|") or stripped.startswith("|}"):
            continue
        buffer.append(stripped)
    flush()
    return header_text, paragraphs


def split_paragraph(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    last_break = 0
    for match in SENTENCE_END_RE.finditer(text):
        last_break = match.end()
        if last_break - start >= max_chars:
            pieces.append(text[start:last_break])
            start = last_break
    if start < len(text):
        tail = text[start:]
        if len(tail) > max_chars * 1.5:
            offset = 0
            while offset < len(tail):
                end = min(len(tail), offset + max_chars)
                pieces.append(tail[offset:end])
                offset = end
        else:
            pieces.append(tail)
    return [piece.strip() for piece in pieces if piece.strip()]


def source_plan_by_id() -> dict[str, dict[str, Any]]:
    data = load_json(SOURCE_PLAN)
    return {book["book_id"]: book for book in data["books"]}


def manifest_items(book: dict[str, Any]) -> list[dict[str, Any]]:
    source = next(layer for layer in book["source_layers"] if layer["layer"] == "wenyan" and layer["role"] == "classical_source")
    source_dir = ROOT / source["path"]
    manifest_path = source_dir / "manifest.json"
    manifest_data = load_json(manifest_path)
    if isinstance(manifest_data, dict):
        manifest_data = manifest_data.get("pages", [])
    items = [item for item in manifest_data if item.get("status") == "ok"]
    root_order = root_wiki_link_order(book["book_id"], source_dir, items, book["book_title_wenyan"])
    prepared = []
    seen_titles: set[str] = set()
    for item in items:
        title = str(item.get("title", ""))
        if "/" not in title and book["book_id"] not in ANTHOLOGY_STANDALONE_BOOKS:
            continue
        if root_order and not any(key in root_order for key in title_order_keys(title)):
            continue
        if should_skip_source_item(book["book_id"], title):
            continue
        preliminary_chapter_title = normalize_chapter_title(book["book_id"], title)
        if book["book_id"] == "chuci":
            if preliminary_chapter_title in CHUCI_SKIP_TITLES:
                continue
            if preliminary_chapter_title in seen_titles:
                continue
            seen_titles.add(preliminary_chapter_title)
        html_rel = item.get("html")
        raw_rel = item.get("raw")
        html_path = source_dir / html_rel if html_rel else Path()
        raw_path = source_dir / raw_rel if raw_rel else Path()
        raw_header_text = extract_raw_wiki_header_section(raw_path) if raw_path.exists() else ""
        if book["book_id"] == "yijing" and raw_rel and raw_path.exists():
            source_path = raw_path
            header_text, paragraphs = extract_raw_wiki_paragraphs(raw_path)
        elif html_rel and html_path.exists():
            source_path = html_path
            header_text, paragraphs = extract_html_paragraphs(html_path, drop_small=book["book_id"] == "sanguozhi")
        elif raw_rel and raw_path.exists():
            source_path = raw_path
            header_text, paragraphs = extract_raw_wiki_paragraphs(raw_path)
        else:
            continue
        if raw_header_text:
            header_text = raw_header_text
        paragraphs = [paragraph for paragraph in paragraphs if not is_source_footer_paragraph(paragraph)]
        if not paragraphs:
            continue
        chapter_title = meaningful_chapter_title(book["book_id"], title, header_text)
        prepared.append(
            {
                **item,
                "chapter_title": chapter_title,
                "source_path": source_path,
                "header_text": header_text,
                "paragraphs": paragraphs,
                "sort_key": chapter_sort_key(book["book_id"], title, source_path.name, header_text, root_order),
            }
        )
    prepared.sort(key=lambda item: item["sort_key"])
    prepared = expand_chapter_anchors(book, prepared)
    return prepared


@lru_cache(maxsize=1)
def load_zhuangzi_giles_windows() -> dict[int, dict[str, str]]:
    path = ROOT / "sources" / "zhuangzi" / "en" / "gutenberg-giles" / "Chuang-Tzu-Giles-59709.txt"
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\s*CHAPTER\s+([IVXLCDM]+)\.\s*", line)
        if match:
            number = ROMAN_TO_INT.get(match.group(1))
            if number:
                starts.append((number, index))
    windows: dict[int, dict[str, str]] = {}
    for offset, (number, start) in enumerate(starts):
        end = starts[offset + 1][1] if offset + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        block = re.sub(r"\n{3,}", "\n\n", block).strip()
        windows[number] = {
            "source": "Giles Project Gutenberg Chuang Tzu",
            "chapter_number": str(number),
            "line_window": f"{start + 1}-{end}",
            "excerpt": block[:4200],
        }
    return windows


@lru_cache(maxsize=1)
def load_zhuangzi_watson_windows() -> dict[int, dict[str, str]]:
    path = ROOT / "sources" / "zhuangzi" / "en" / "burton-watson" / "The Complete Works of Zhuangzi.pdf"
    text = pdftotext(path)
    if not text:
        return {}
    windows = line_window_by_headings(text.splitlines(), WATSON_TITLES, min_line=1000)
    for item in windows.values():
        item["source"] = "Burton Watson, The Complete Works of Zhuangzi"
        item["path"] = str(path.relative_to(ROOT))
    return windows


@lru_cache(maxsize=1)
def load_zhuangzi_jp_secondary_text() -> dict[str, str]:
    epub = ROOT / "sources" / "zhuangzi" / "jp" / "essay-retelling" / "荘子.epub"
    text = epub_text(epub)
    return {
        "source": "岡本かの子『荘子』 EPUB / Aozora-style retelling",
        "path": str(epub.relative_to(ROOT)),
        "excerpt": excerpt(text, 3200),
        "note": "Secondary Japanese literary retelling, not a complete aligned translation.",
    }


@lru_cache(maxsize=1)
def load_sanguozhi_open_en_windows() -> dict[int, dict[str, str]]:
    raw_dir = ROOT / "sources" / "sanguozhi" / "en" / "wikisource-open-license" / "raw"
    if not raw_dir.exists():
        return {}
    windows: dict[int, dict[str, str]] = {}
    for path in sorted(raw_dir.glob("*.wiki")):
        match = re.search(r"Volume[ _](\d+)", path.name)
        if not match:
            continue
        number = int(match.group(1))
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
        text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
        text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        windows[number] = {
            "source": "English Wikisource open-license Sanguozhi excerpt",
            "chapter_number": str(number),
            "path": str(path.relative_to(ROOT)),
            "excerpt": text[:4200],
        }
    return windows


@lru_cache(maxsize=1)
def load_sanguozhi_zh_epub_windows() -> dict[int, dict[str, str]]:
    path = ROOT / "sources" / "sanguozhi" / "zh" / "pei-songzhi-source-epub" / "三国志（中华经典普及文库）.epub"
    windows: dict[int, dict[str, str]] = {}
    if not path.exists():
        return windows
    try:
        with ZipFile(path) as archive:
            html_names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith((".html", ".htm", ".xhtml"))
            )
            for name in html_names:
                soup = BeautifulSoup(archive.read(name), "html.parser")
                text = clean_reference_text(soup.get_text("\n", strip=True))
                match = re.search(r"三国志卷([一二三四五六七八九十百〇零]+)", text)
                if not match:
                    continue
                number = zh_number_to_int(match.group(1))
                if number and number not in windows:
                    windows[number] = {
                        "source": "中华书局《三国志》EPUB with Pei Songzhi commentary",
                        "path": str(path.relative_to(ROOT)),
                        "epub_item": name,
                        "excerpt": excerpt(text, 4200),
                    }
    except Exception:
        return windows
    return windows


@lru_cache(maxsize=1)
def load_sanguozhi_selection_en_windows() -> dict[int, dict[str, str]]:
    path = (
        ROOT
        / "sources"
        / "sanguozhi"
        / "en"
        / "empresses-and-consorts-selections"
        / "Empresses and Consorts_ Selections from Chen Shou's Records of the Three States with Pei Songzhi's Commentary.pdf"
    )
    text = pdftotext(path)
    if not text:
        return {}
    lines = text.splitlines()
    headings = {
        5: "Fascicle 5 Empresses and Consorts",
        34: "Fascicle 34 Consorts and Sons of the Two Sovereigns",
        50: "Fascicle 50 Consorts and Concubines",
    }
    windows = line_window_by_headings(lines, headings, min_line=1800)
    for number, item in windows.items():
        item["source"] = "Cutter/Crowell, Empresses and Consorts: selections from Records of the Three States"
        item["path"] = str(path.relative_to(ROOT))
        item["note"] = f"Partial English selection, relevant mainly to fascicle {number}."
    return windows


@lru_cache(maxsize=1)
def load_foguoji_references() -> dict[str, Any]:
    en_raw = ROOT / "sources" / "foguoji" / "en" / "wikisource-record-of-buddhistic-kingdoms" / "raw" / "0001-Record of the Buddhistic Kingdoms.wiki"
    ja_work = ROOT / "sources" / "foguoji" / "jp" / "wikipedia-reference" / "仏国記.html"
    ja_author = ROOT / "sources" / "foguoji" / "jp" / "wikipedia-reference" / "法顕.html"
    zh_author = ROOT / "sources" / "foguoji" / "zh" / "wikipedia-reference" / "法显.html"

    def html_excerpt(path: Path, limit: int = 2600) -> str:
        if not path.exists():
            return ""
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        content = soup.select_one(".mw-parser-output") or soup
        for tag in content.select("style, script, table, sup, .noprint"):
            tag.decompose()
        return excerpt(content.get_text("\n", strip=True), limit)

    en_text = ""
    if en_raw.exists():
        en_text = excerpt(clean_wiki_markup(en_raw.read_text(encoding="utf-8", errors="replace")), 4200)
    return {
        "en": {
            "source": "English Wikisource, Record of the Buddhistic Kingdoms",
            "path": str(en_raw.relative_to(ROOT)),
            "excerpt": en_text,
        },
        "ja_modern": [
            {
                "source": "Japanese Wikipedia reference for 仏国記",
                "path": str(ja_work.relative_to(ROOT)),
                "excerpt": html_excerpt(ja_work),
                "note": "Reference only; no full Japanese translation was found locally.",
            },
            {
                "source": "Japanese Wikipedia reference for 法顕",
                "path": str(ja_author.relative_to(ROOT)),
                "excerpt": html_excerpt(ja_author),
                "note": "Author/traveler context for terminology.",
            },
        ],
        "zh_modern": {
            "source": "Chinese Wikipedia reference for 法显",
            "path": str(zh_author.relative_to(ROOT)),
            "excerpt": html_excerpt(zh_author),
            "note": "Author/traveler context; generate modern Chinese from the wenyan spine.",
        },
    }


def broad_references(book: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    layers = book["source_layers"]
    paths_by_layer: dict[str, list[dict[str, str]]] = OrderedDict()
    for layer in layers:
        paths_by_layer.setdefault(layer["layer"], []).append(
            {
                "role": layer["role"],
                "path": layer["path"],
                "quality": layer["quality"],
            }
        )
    reference: dict[str, Any] = {
        "scope": "References are broad chapter/source references. Preserve the wenyan source exactly and only use references when they clearly match.",
        "paths": paths_by_layer,
    }
    if book["book_id"] == "zhuangzi":
        en_refs = []
        watson = load_zhuangzi_watson_windows().get(chapter_number)
        giles = load_zhuangzi_giles_windows().get(chapter_number)
        if watson:
            en_refs.append(watson)
        if giles:
            en_refs.append(giles)
        reference["en"] = en_refs
        reference["zh_modern"] = {
            "source": "sources/zhuangzi/zh/modern-annotated/庄子_ 中华经典名著全本全注全译丛书.pdf",
            "note": "Scanned/metadata-only under pdftotext; use as source reference for later OCR, not as direct text in this chunk.",
        }
        reference["ja_modern"] = [
            {
                "source": "sources/zhuangzi/jp/modern-translation-scan",
                "note": "Public-domain Japanese modern translation scan; image-only under pdftotext in the current environment, so OCR is required before prompt-time textual use.",
            },
            load_zhuangzi_jp_secondary_text(),
        ]
    elif book["book_id"] == "sanguozhi":
        en_refs = []
        open_en = load_sanguozhi_open_en_windows().get(chapter_number)
        selection_en = load_sanguozhi_selection_en_windows().get(chapter_number)
        if open_en:
            en_refs.append(open_en)
        if selection_en:
            en_refs.append(selection_en)
        reference["en"] = en_refs
        zh_epub = load_sanguozhi_zh_epub_windows().get(chapter_number)
        reference["zh_modern"] = {
            "source": "sources/sanguozhi/zh/pei-songzhi-source-epub/三国志（中华经典普及文库）.epub",
            "note": "Chinese source edition with Pei Songzhi commentary; use as a broad Chinese reference while keeping commentary out of the primary wenyan stream.",
            "excerpt": zh_epub.get("excerpt", "") if zh_epub else "",
            "epub_item": zh_epub.get("epub_item", "") if zh_epub else "",
        }
        reference["ja_modern"] = {
            "source": "sources/sanguozhi/jp/wikisource-index",
            "note": "Index-only Japanese source. Generate natural modern Japanese where no matching source exists.",
        }
    elif book["book_id"] == "foguoji":
        reference.update(load_foguoji_references())
    return reference


def write_markdown(book: dict[str, Any], chapters: list[dict[str, Any]]) -> Path:
    markdown = ROOT / "books" / book["book_id"] / "markdown" / "wenyan.md"
    lines = [f"# {book['book_title_wenyan']}", ""]
    for chapter in chapters:
        lines.extend([f"## {chapter['chapter_title']}", ""])
        for paragraph in chapter["paragraphs"]:
            lines.extend([paragraph, ""])
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return markdown


def prepare(book_id: str, *, max_chars: int, force: bool) -> None:
    plans = source_plan_by_id()
    if book_id not in plans:
        raise KeyError(f"unknown book id: {book_id}")
    book = plans[book_id]
    out_root = ROOT / "books" / book_id
    chunk_dir = out_root / "work" / "quadrilingual" / "chunks"
    chunks_jsonl = chunk_dir / "chunks.jsonl"
    manifest_path = chunk_dir / "manifest.json"
    plan_path = out_root / "book-plan.json"
    if chunks_jsonl.exists() and manifest_path.exists() and plan_path.exists() and not force:
        print(f"{book_id}: already prepared")
        return

    source_items = manifest_items(book)
    chapters: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    chunk_counter = 0
    for chapter_number, item in enumerate(source_items, start=1):
        chapter_title = str(item.get("chapter_title") or meaningful_chapter_title(book_id, str(item["title"]), str(item.get("header_text") or "")))
        chapter_title_wenyan = str(item.get("chapter_title_wenyan") or chapter_title)
        chapter_title_zh_modern = str(item.get("chapter_title_zh_modern") or chapter_title_wenyan)
        chapter_title_ja_modern = str(item.get("chapter_title_ja_modern") or chapter_title_wenyan)
        chapter_title_en = str(item.get("chapter_title_en") or f"{book['book_title_en']} {chapter_number}: {chapter_title_wenyan}")
        chapter_paragraphs = item["paragraphs"]
        chapters.append({"chapter_title": chapter_title_wenyan, "paragraphs": chapter_paragraphs})
        chapter_id = f"{book_id}-chapter-{chapter_number:02d}"
        for paragraph_number, paragraph in enumerate(chapter_paragraphs, start=1):
            for part_number, piece in enumerate(split_paragraph(paragraph, max_chars), start=1):
                chunk_counter += 1
                chunk_id = f"{book_id}-chunk-{chunk_counter:04d}"
                paragraph_id = f"{chunk_id}-p001"
                section_suffix = f" paragraph {paragraph_number}"
                if part_number > 1:
                    section_suffix += f" part {part_number}"
                chunks.append(
                    {
                        "schema_version": 1,
                        "task_type": "quadrilingual_wenyan_main",
                        "book_id": book_id,
                        "book_title_wenyan": book["book_title_wenyan"],
                        "chunk_id": chunk_id,
                        "chapter_id": chapter_id,
                        "chapter_number": chapter_number,
                        "chapter_title_wenyan": chapter_title_wenyan,
                        "chapter_title_zh_modern": chapter_title_zh_modern,
                        "chapter_title_ja_modern": chapter_title_ja_modern,
                        "chapter_title_en": chapter_title_en,
                        "section_title_wenyan": f"{chapter_title_wenyan}{section_suffix}",
                        "source_spine_lang": "wenyan",
                        "paragraphs": [{"id": paragraph_id, "wenyan": piece}],
                        "reference": broad_references(book, chapter_number),
                    }
                )

    markdown = write_markdown(book, chapters)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks_jsonl.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    source_paths = {
        layer["role"]: layer["path"]
        for layer in book["source_layers"]
    }
    manifest = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "prepared",
        "task_mode": "quadrilingual_wenyan_main",
        "book_title_wenyan": book["book_title_wenyan"],
        "book_title_zh_modern": book["book_title_zh"],
        "book_title_ja_modern": book["book_title_ja"],
        "book_title_en": book["book_title_en"],
        "author": book["author"],
        "author_reading_zh": book["author_reading_zh"],
        "author_reading_ja": book["author_reading_ja"],
        "chunk_count": len(chunks),
        "chapter_count": len(chapters),
        "chunks": [{"chunk_id": chunk["chunk_id"], "chapter_number": chunk["chapter_number"]} for chunk in chunks],
        "source_paths": source_paths | {"wenyan_markdown": str(markdown.relative_to(ROOT))},
        "source_sha256": {str(markdown.relative_to(ROOT)): sha256(markdown)},
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(manifest_path, manifest)
    plan = {
        "schema_version": 1,
        "book_id": book_id,
        "status": "launchable",
        "launchable": True,
        "task_mode": "quadrilingual_wenyan_main",
        "source_language": "wenyan",
        "default_note_order": {
            "wenyan": ["en", "ja_modern", "zh_modern"],
            "en": ["wenyan", "ja_modern", "zh_modern"],
            "ja_modern": ["wenyan", "en", "zh_modern"],
            "zh_modern": ["wenyan", "en", "ja_modern"],
        },
        "book_title_wenyan": manifest["book_title_wenyan"],
        "book_title_zh": manifest["book_title_zh_modern"],
        "book_title_ja": manifest["book_title_ja_modern"],
        "book_title_en": manifest["book_title_en"],
        "author": manifest["author"],
        "author_reading_zh": manifest["author_reading_zh"],
        "author_reading_ja": manifest["author_reading_ja"],
        "book_description": f"{book['book_title_wenyan']} with classical Chinese as the main text and English, modern Japanese, and modern Chinese overlays.",
        "source_paths": manifest["source_paths"],
        "chunks_jsonl": str(chunks_jsonl.relative_to(ROOT)),
        "chunks_manifest": str(manifest_path.relative_to(ROOT)),
        "raw_chunk_dir": f"books/{book_id}/work/quadrilingual/interlinear/chunks",
        "assembled_json": f"books/{book_id}/work/quadrilingual/preview/{book_id}.partial.json",
        "build_root": f"build/{book_id}/wenyan-main-quadrilingual",
        "prepared_at": manifest["prepared_at"],
    }
    for cover_candidate in (
        ROOT / "assets" / "covers" / book_id / "background.png",
        ROOT / "assets" / "covers" / book_id / "cover.png",
    ):
        if cover_candidate.exists():
            plan["cover_image"] = str(cover_candidate.relative_to(ROOT))
            break
    write_json(plan_path, plan)
    print(f"{book_id}: chapters={len(chapters)} chunks={len(chunks)}")
    print(plan_path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True)
    parser.add_argument("--max-chars", type=int, default=520)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for book_id in args.book_id:
        prepare(book_id, max_chars=args.max_chars, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
