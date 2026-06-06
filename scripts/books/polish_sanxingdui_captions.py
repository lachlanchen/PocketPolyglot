#!/usr/bin/env python3
"""Repair Sanxingdui polished Markdown figure captions.

The Sanxingdui scanned books contain many image pages where the OCR produced
Latin-letter garbage beside otherwise useful captions.  This pass keeps the
image pages, promotes corrected captions to explicit Markdown blockquotes, and
uses the ``三星堆祭祀坑`` figure index where that book already provides reliable
caption text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_DIR = ROOT / "books" / "sanxingdui" / "markdown"

PAGE_RE = re.compile(r"^## Page (\d+)\s*$")
COMMENT_RE = re.compile(r"^<!--\s*kind=([a-z_]+)\s+confidence=([a-z]+)\s*-->\s*$")
CATALOG_KEY_RE = re.compile(r"(?:图版|拓片|图)\s*[一二三四五六七八九十百〇零]{1,4}")
BAD_ASCII_RE = re.compile(
    r"\b(?:TEAR|SBFO|SEEE|JAHRE|MIR|BUBS|PMA|SDK|DMEF|BUH|Arwen|Pare|"
    r"Feet|MATAR|MASI|HANH|Pawan|SRE|JCRD|PHUT|WEAR|RAB|FAR|WRI|AFL)\b",
    re.IGNORECASE,
)

ROMAN_REPLACEMENTS = {
    "I": "Ⅰ",
    "II": "Ⅱ",
    "III": "Ⅲ",
    "IV": "Ⅳ",
    "V": "Ⅴ",
    "VI": "Ⅵ",
}


@dataclass
class Page:
    number: int
    kind: str
    confidence: str
    lines: list[str]
    start: int
    end: int


def parse_pages(lines: list[str]) -> list[Page]:
    pages: list[Page] = []
    current_number: int | None = None
    current_kind = ""
    current_confidence = "medium"
    body_start = 0
    page_start = 0

    for index, line in enumerate(lines):
        page_match = PAGE_RE.match(line.strip())
        if page_match:
            if current_number is not None:
                pages.append(
                    Page(
                        current_number,
                        current_kind,
                        current_confidence,
                        lines[body_start:index],
                        page_start,
                        index,
                    )
                )
            current_number = int(page_match.group(1))
            current_kind = ""
            current_confidence = "medium"
            page_start = index
            body_start = index + 1
            continue

        if current_number is not None:
            comment_match = COMMENT_RE.match(line.strip())
            if comment_match:
                current_kind = comment_match.group(1)
                current_confidence = comment_match.group(2)
                body_start = index + 1

    if current_number is not None:
        pages.append(
            Page(
                current_number,
                current_kind,
                current_confidence,
                lines[body_start:],
                page_start,
                len(lines),
            )
        )
    return pages


def page_replacement(number: int, kind: str, confidence: str, body: list[str]) -> list[str]:
    cleaned_body = [line.rstrip() for line in body]
    while cleaned_body and not cleaned_body[0].strip():
        cleaned_body.pop(0)
    while cleaned_body and not cleaned_body[-1].strip():
        cleaned_body.pop()

    replacement = [f"## Page {number}", "", f"<!-- kind={kind} confidence={confidence} -->"]
    if cleaned_body:
        replacement += ["", *cleaned_body]
    return replacement


def rewrite_pages(path: Path, replacements: dict[int, tuple[str, str, list[str]]]) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    pages = parse_pages(lines)
    page_lookup = {page.number: page for page in pages}
    changed = 0

    for number in sorted(replacements, reverse=True):
        page = page_lookup.get(number)
        if page is None:
            continue
        kind, confidence, body = replacements[number]
        replacement = page_replacement(number, kind, confidence, body)
        if lines[page.start : page.end] != replacement:
            lines[page.start : page.end] = replacement
            changed += 1

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def normalize_wenwu_catalog_ids(path: Path) -> int:
    """Fix recurring OCR damage in artifact pit IDs without touching prose."""
    text = path.read_text(encoding="utf-8")
    original = text
    literal_replacements = {
        "K2(2)": "K2②",
        "K22②": "K2②",
        "K2⑧": "K2③",
        "K2GB:": "K2③:",
        "K2GB：": "K2③：",
    }
    for old, new in literal_replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"K22(?=[:：,，。\s-])", "K2②", text)
    text = re.sub(r"K2G(?=[:：])", "K2③", text)
    text = re.sub(r"K2G(?=\d)", "K2③:", text)
    if text == original:
        return 0
    path.write_text(text, encoding="utf-8")
    return 1


def normalize_jisikeng_catalog_ids(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace("K2(2)", "K2②")
    text = text.replace("K2G:103-27", "K2③:103-27")
    if text == original:
        return 0
    path.write_text(text, encoding="utf-8")
    return 1


def quote(lines: list[str]) -> list[str]:
    return [f"> {line}" for line in lines if line.strip()]


def normalize_common(text: str) -> str:
    text = text.strip()
    text = text.replace("〈", "（").replace("〉", "）")
    text = text.replace("《", "（").replace("》", "）")
    text = text.replace("((", "（").replace("))", "）")
    text = text.replace("（(", "（").replace(")）", "）")
    text = text.replace("一", "-", 1) if text.startswith("一 ") else text
    text = re.sub(r"\s+", " ", text)
    text = text.replace("， ", "，").replace("、 ", "、")
    text = text.replace(" : ", ":").replace(" ：", "：")
    text = text.replace("K1 :", "K1:").replace("K1 ：", "K1:")
    text = text.replace("K1+", "K1:").replace("K1!", "K1:")
    text = text.replace("CK1", "K1").replace("KK1", "K1")
    text = text.replace("K2@):", "K2②:").replace("K2@:", "K2②:")
    text = text.replace("K2@D):", "K2②:").replace("K2@D:", "K2②:")
    text = text.replace("K2C@D):", "K2②:").replace("K2C@D:", "K2②:")
    text = text.replace("K2Q):", "K2②:").replace("K2Q:", "K2②:")
    text = text.replace("K22):", "K2②:").replace("K22:", "K2②:")
    text = text.replace("K2G@):", "K2③:").replace("K2G@:", "K2③:")
    text = text.replace("K2GB):", "K2③:").replace("K2GB:", "K2③:")
    text = text.replace("K2G):", "K2③:").replace("K2G:", "K2③:")
    text = text.replace("K2(D):", "K2③:").replace("K2D):", "K2③:")
    text = text.replace("K2③):", "K2③:").replace("K2②):", "K2②:")
    text = text.replace("砷米", "厘米").replace("厚米", "厘米").replace("哩米", "厘米")
    text = text.replace("残高", "残高").replace("通高", "通高")
    text = re.sub(r"(\d)\s+厘米", r"\1厘米", text)
    return text.strip(" -_")


def romanize_types(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        roman = match.group(2)
        suffix = match.group(3)
        return f"{prefix}{ROMAN_REPLACEMENTS.get(roman, roman)}{suffix}"

    text = re.sub(r"\b([A-Za-z]{1,2})(I|II|III|IV|V|VI)(式|型)\b", repl, text)
    return text


def looks_like_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in stripped)
    ascii_letters = sum(char.isascii() and char.isalpha() for char in stripped)
    if BAD_ASCII_RE.search(stripped):
        return True
    if cjk == 0 and ascii_letters >= 3:
        return True
    if ascii_letters > max(12, cjk * 2) and not re.search(r"\bK[12]\b", stripped):
        return True
    if re.fullmatch(r"[0-9\s.,:;!?+\-_/\\|()[\]{}<>~`'\"=*&^%$#@，。；：、（）]+", stripped):
        return True
    return False


def clean_caption_lines(raw_lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        if line.startswith("> "):
            line = line[2:].strip()
        elif line.startswith("- "):
            line = line[2:].strip()
        line = normalize_common(romanize_types(line))
        if not line or looks_like_noise(line):
            continue
        if line in {"[图版页/地图页，原页文字有限]", "[图版页/地图页，OCR文字有限]"}:
            continue
        cleaned.append(line)
    return cleaned


def clean_index_caption(text: str) -> str:
    text = normalize_common(romanize_types(text.strip()))
    text = re.sub(r"^[-•]\s*", "", text)
    text = re.sub(r"，?页码\s*\d+\s*[。.]?$", "", text)
    text = re.sub(r"，?页\s*\d+\s*[。.]?$", "", text)
    text = re.sub(r"\s+\d{1,4}\s*[。.]?$", "", text)
    text = re.sub(r"[。；;]\s*$", "", text)
    return text.strip()


def extract_clean_jisikeng_index(path: Path) -> tuple[dict[str, list[str]], dict[int, list[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    pages = parse_pages(lines)
    by_key: dict[str, list[str]] = {}
    by_scan_page: dict[int, list[str]] = {}

    for page in pages:
        if page.kind not in {"catalog", "toc"}:
            continue
        for raw in page.lines:
            line = raw.strip()
            if line.startswith("- "):
                line = line[2:].strip()
            if not (line.startswith("图") or line.startswith("拓片")):
                continue
            if looks_like_noise(line):
                continue
            caption = clean_index_caption(line)
            if not caption:
                continue
            for key in CATALOG_KEY_RE.findall(caption):
                norm_key = re.sub(r"\s+", "", key)
                by_key.setdefault(norm_key, [])
                if caption not in by_key[norm_key]:
                    by_key[norm_key].append(caption)

            page_number_match = re.search(r"(?:页码|页|[\s　])(\d{1,4})\s*[。.]?$", line)
            if page_number_match:
                printed_page = int(page_number_match.group(1))
                scan_page = printed_page + 5
                by_scan_page.setdefault(scan_page, [])
                if caption not in by_scan_page[scan_page]:
                    by_scan_page[scan_page].append(caption)

    return by_key, by_scan_page


def noisy_keys(text: str) -> list[str]:
    normalized = text.replace("C〇", "〇").replace("OO", "〇〇").replace("0", "〇")
    normalized = normalized.replace("图版一〇C〇", "图版一〇〇")
    return [re.sub(r"\s+", "", key) for key in CATALOG_KEY_RE.findall(normalized)]


HUAXIA_REPLACEMENTS: dict[int, tuple[str, str, list[str]]] = {
    6: (
        "caption_or_map",
        "high",
        quote(
            [
                "东方青铜立人像",
                "置于四方台顶部的“昆轮”",
                "三星堆三级四方台",
                "镇守四方台四角的青铜蛇（残件）",
            ]
        ),
    ),
    9: (
        "caption_or_map",
        "high",
        quote(
            [
                "华夏神都：全方位揭秘三星堆文明",
                "神秘的北方遇强",
                "青铜虎形器",
                "青铜爬龙柱形器",
                "金虎",
                "虎形板饰",
                "青铜鸡",
                "三星堆出土的四方祭礼器物",
            ]
        ),
    ),
    11: (
        "caption_or_map",
        "high",
        quote(
            [
                "金沙出土的反绑跪人像",
                "三星堆青铜雄鬼",
                "三星堆出土的头饰钩铃的大禹像",
                "纳西族《神路图》头饰包巾者",
            ]
        ),
    ),
    12: (
        "caption_or_map",
        "high",
        quote(
            [
                "纵目大耳的烛阴、烛阳后来在民间被传为灶神",
                "三星堆出土的烛阴面具",
                "灶神壁纸",
                "三星堆出土的烛阳面具",
            ]
        ),
    ),
    273: (
        "text",
        "high",
        [
            "### 还原昆仑圣山",
            "",
            "每一个神话都连着一个梦想，每一种文明都有一个源头。而昆仑神话就是华夏文明的源头与梦想的集合。回到巍巍昆仑祖山，回到人类始祖的故园，阔别了几万年，一切的器物与布饰都改头换面，然而对于同一种文明血脉中的游子来说，试着把梦中的所见还原，或是把传说中的故园再度修复，那是一种叫人永世萦怀挂记的迷梦。",
            "",
            "记下故园当年的布饰，听听那每一件早已产生历史锈迹的器物的故事，或是就长久地注视着它们并指认出它的名字——这一切都可以从三星堆以及同期或稍远的成都平原多座故城遗址开始。",
        ],
    ),
}

RENJIAN_REPLACEMENTS: dict[int, tuple[str, str, list[str]]] = {
    3: (
        "frontmatter",
        "high",
        [
            "### 人间天国",
            "### 三星堆、金沙王都发现之谜",
            "",
            "岳南 著",
            "",
            "北方联合出版传媒（集团）股份有限公司",
            "万卷出版公司",
            "2013年1月，沈阳",
        ],
    )
}

JISIKENG_MANUAL: dict[int, list[str]] = {
    41: [
        "拓片一 铜羊首牺尊（K1:163、59）纹饰：1. 肩部；2. 腹部；3. 圈足",
        "拓片二 铜龙虎尊（K1:158、258）纹饰",
        "铜龙虎尊虎口下人形图案",
    ],
    44: [
        "图版八 铜尊、铜罍、铜羊首牺尊",
        "1、2. 铜尊（K1:158、258）；3. 羊首牺尊圈足（K1:59）；4. 铜罍（K1:130）口沿及肩部；5. 铜罍（K1:130）圈足",
    ],
    47: ["图二五 铜罍（K1:130）：1. 口沿部分；2. 圈足部分"],
    50: [
        "拓片四 铜罍（K1:130）纹饰：1. 肩、腹部；2. 圈足；3. 外底刮范留下的划痕",
        "铜羊首牺尊（K1:59）圈足纹饰",
    ],
    52: [
        "图版九 铜盘、铜器盖、铜瑗",
        "1、2. 盘（K1:53）；3. 器盖（K1:135）背面；4. 器盖（K1:135）内侧；5. AⅠ式瑗（K1:124）；6. AⅠ式瑗（K1:300-1）",
    ],
    55: [
        "图二九 B型铜瑗：1. BⅢ式（K1:291-4）；2. BⅢ式（K1:115）",
        "图三〇 C型铜瑗：1. K1:51；2. K1:262-2",
    ],
    57: [
        "图版一一 铜环",
        "1. BⅡ式（K1:269-2）；2. BⅢ式（K1:291-4）；3. BⅢ式（K1:115）；4. C型（K1:51）；5. C型（K1:262-2）",
    ],
    78: [
        "图版一九 玉璋",
        "1. DbⅡ式（K1:168）；2. DbⅢ式（K1:235-3）；3. DbⅣ式（K1:97-7）；4. DbⅤ式（K1:75）；5. DbⅤ式（K1:86）；6. DbⅤ式（K1:04）",
    ],
    84: [
        "图版二一 玉璋",
        "1. DcⅢ式（K1:166-2）；2. DcⅢ式（K1:06）；3. DcⅣ式（K1:218）；4. DcⅣ式（K1:94）；5. Ea型（K1:235-5）；6. Ea型（K1:161）",
    ],
    130: [
        "图版四〇 石戈",
        "1. A型（K1:79）；2. A型（K1:109、113）；3. Ba型（K1:166-3）；4. Ba型（K1:80）",
    ],
    146: [
        "图版四七 石斧",
        "1. C型（K1:205）；2. C型（K1:014）；3. D型（K1:168-1）；4. D型（K1:276）；5. D型（K1:271-1）；6. D型（K1:180）",
    ],
    148: [
        "图版四八 石斧",
        "1. D型（K1:224）；2. D型（K1:241）；3. D型（K1:67）；4. D型（K1:234）；5. E型（K1:46）；6. E型（K1:53-6）",
    ],
    153: [
        "图版五一 陶尖底盏",
        "1. A型（K1:334）；2. Ba型（K1:346-5）；3. Ba型（K1:346-7）；4. Bb型（K1:346-8）",
    ],
    238: ["图一二九 铜神坛（K2②:296）"],
    239: [
        "图一三〇 铜神坛：1. K2②:296-1；2. K2②:292-3",
        "图一三一 铜神殿（K2②:143-1）",
    ],
    250: ["拓片一七 Ⅲ式铜圆尊（K2②:112）纹饰：1. 肩部；2. 腹部；3. 圈足"],
    273: [
        "拓片二五 Ⅲ式铜罍（K2②:159）纹饰：1. 口沿；2. 肩部、腹部；3. 圈足",
        "拓片二六 Ⅰ式铜方罍（K2②:80）纹饰：1. 肩部；2. 腹部",
    ],
    285: [
        "图版一〇〇 铜罍残片、铜瓿残片",
        "1. 腹部（K2②:103）；2. 肩部（K2②:103-1）；3. 腹部（K2②:39-1）；4. 腹部（K2②:32）",
    ],
    287: [
        "图一五三 大铜瑗（K2②:111）",
        "图一五四 AⅠ式小铜环：1. K2②:46；2. K2②:134；3. K2②:126",
    ],
    347: [
        "图版一三〇 铜鸟形饰、铜鸟形饰尾部残件",
        "1. D型（K2③:24-1）；2. D型（K2③:193-11）；3. E型（K2③:4-2）；4. F型（K2③:193-12）；5. 尾部残件（K2②:70-14）",
    ],
    421: [
        "图二二三 石器：1. B型（K2②:322-12）；2. B型（K2②:148）；3. B型（K2②:201-1）"
    ],
    534: [
        "图10 一号祭祀坑金杖（K1:1）",
        "图12 一号祭祀坑 AⅠ式铜戈（K1:7-1）",
        "图13 一号祭祀坑 AⅡ式铜戈（K1:11-1）",
    ],
    536: [
        "图15 一号祭祀坑 DeⅠ式玉璋（K1:03）",
        "图16 一号祭祀坑 DeⅢ式玉璋（K1:166-2）",
    ],
    540: [
        "图22 一号祭祀坑 AaⅠ式玉戈（K1:108）",
        "图23 一号祭祀坑 AbⅠ式玉戈（K1:141-1、155-2）",
    ],
    546: [
        "图34 一号祭祀坑 Ab型玉凿（K1:134）",
        "图35 一号祭祀坑 Ad型玉凿（K1:166-1）",
    ],
    550: [
        "图42 二号祭祀坑 B型铜人头像（K2②:04）",
        "图43 二号祭祀坑铜喇叭座顶尊跪坐人像（K2②:48）",
    ],
    562: [
        "图61 二号祭祀坑 B型铜眼形器（K2②:197、8）",
        "图62 二号祭祀坑 C型铜眼形器（K2②:101、106、8-1、99）",
    ],
    564: [
        "图64 二号祭祀坑Ⅱ号大型铜神树（K2②:194）",
        "图65 二号祭祀坑铜神树上立鸟（K2②:194-1）",
    ],
    572: [
        "图77 二号祭祀坑 C型铜铃（K2③:103-28）",
        "图78 二号祭祀坑 Da型铜铃",
        "图79 二号祭祀坑铜铃",
    ],
    573: [
        "图80 二号祭祀坑铜公鸡（K2②:107）",
        "图81 二号祭祀坑 A型龙形铜饰",
        "图82 二号祭祀坑 B型龙形铜饰",
    ],
    608: [
        "2. Ⅴ式铜圆尊（K2②:127）；3. Ⅴ式铜圆尊（K2②:129）；4. 铜方尊（K2②:205、205-1）；5. Ⅲ式铜罍（K2②:159）"
    ],
}

WENWU_MANUAL: dict[int, list[str]] = {
    4: ["青铜神坛局部图版。"],
    41: ["3. 小立人像，K2③:296-1，头残，身着对襟短袖衫，腰间系粗带两周，结祥于腰前。残高10.8厘米。"],
    51: ["11. 顶尊跪坐人像，K2③:48，头顶一件青铜尊，上身赤裸，腰下系一件短裙，双膝跪在一座“神山”座子上。座子直径10、通高15.6厘米。"],
    53: ["12. 铜跪坐人像，K1:293，高髻，上身穿有花纹短服，腰带系带两周，双手扶膝，左右手腕各戴有两只手镯。宽8.2、通高14.6厘米。"],
    56: ["13. 戴兽冠青铜人，K2③:264，下半身残缺，头戴兽形冠，双手呈握物状，身着对襟服，服饰上饰云雷纹。残高40.2厘米。"],
    57: ["14. 小人面像，K1:20，耳残，形体小而薄，是三星堆祭祀坑中出土的唯一的小人面像。面具后缘上下拐角处各有一穿孔。面具宽9.2、高7厘米。"],
    61: ["16. 铜人面像，K2②:128，脸较方，额中穿孔，粗眉大眼，面具两侧的上下各有一个方形穿孔。宽41.5、厚0.3、高25.4厘米。"],
    67: ["22. 铜人面像，K2②:293，额中方孔未凿穿，上有球凿击打痕迹。宽37.8、厚0.4、高25.5厘米。"],
    70: ["25. 铜人面像，K2②:153，形体较大，宽额，粗眉大眼，长耳，口缝曾涂朱砂。宽60.5、厚0.6、高40.3厘米。"],
    71: ["26. 铜人面像，K2②:119，眉梢上绘有黑彩痕迹。"],
    80: [
        "34. 青铜人面具残件，K2③:14，残高26厘米。",
        "35. 铜人头像，K1:26，子母口头顶，埋藏前被砸毁。残宽21.4、残高17.2厘米。",
    ],
    91: ["42. 铜人头像，K1:11，形体较大，这尊头像出土时，在头像内部清理出骨渣、铜瑗、金虎饰、玉琮等物。宽26.4、高37.4厘米。"],
    92: ["43. 铜人头像，K1:3，粗眉大眼，下颌较圆。出土时，在该头像内清理出十多枚海贝。头纵径21.6、残高30.2厘米。"],
    96: ["45. 铜人头像，K2②:83，头较小，头顶似盘辫，或戴有辫状帽。宽额，脸瘦长，两只耳朵上各有三个圆穹。宽10.8、高13.6厘米。"],
    97: ["46. 铜人头像，K2②:51，眼眶及脑后发辫留有黑色痕迹，口部涂有朱砂。宽20、通高40.4厘米。"],
    100: ["49. 铜人头像，K2②:118，头顶有补铸痕迹，头顶上有四个气孔。眉部、眼眶及辫子均有黑彩，口缝有朱砂痕。宽18、通高37.8厘米。"],
    101: ["50. 铜人头像，K2②:104，阔口，嘴角下勾，耳垂有穿孔，脑后有一条发辫。宽19、通高38.6厘米。"],
    102: ["51. 铜人头像，K2②:156，顶盖脱落，脸形较瘦，脑后有发辫。眼、眉描黑彩，口涂朱砂。宽20.4、通高38.5厘米。"],
    103: ["52. 铜人头像，K2②:55，眉及眼球部分曾涂黑彩，脑后有发辫。宽18.3、通高41.3厘米。"],
    109: ["58. 铜人头像，K2②:5735，头残，眉眼、鼻梁、嘴部较清晰。宽19.5、通高49.2厘米。"],
    116: ["63. 铜人面像，K2②:58，宽额，大眼，长耳。口部、眼眶等处有朱砂痕。宽23.8、通高51.6厘米。"],
    121: ["65-1. 金面罩铜人头像，K2②:137，脑后有一发髻，上下端均残缺。金面罩极薄，仅存在额及左脸部分。宽22.4、通高45.8厘米。"],
    125: ["67. 金面罩铜头像，K2②:214，金面罩右额及颐部残缺，脑后发髻脱落，仅存两个长方形孔。宽22、高48.1厘米。"],
    150: ["86. 铜水牛头，K2③:193-9，残，圆鼻、大眼，粗眉，两只角分两边，中间一只角向前。残高2.6厘米。"],
    151: ["87. 铜水牛头，K2③:193-10，残，圆鼻、大眼，粗眉，两只角分两边，中间一只角向前。残高2.6厘米。"],
    152: ["88. 铜水牛头，K2③:193-11，残，圆鼻、大眼，粗眉，两只角分两边，中间一只角向前。残高2.6厘米。"],
    229: ["158. 铜圭形饰，K2②:194-4，顶部残缺，器形较罕见。"],
    232: ["162. 铜眼形器，编号残缺，宽约4.2、高5.2厘米。"],
    241: ["171. 铜神殿屋顶，K2③:143，殿顶呈四面坡形，檐口下折，檐下有一排方形椽头。檐长16.5、上宽8、下宽16.3、残高15.8厘米。"],
    242: ["171-1. 铜神殿屋面上段，K2③:143-1，顶残，屋檐上饰有圆点填充的山形纹和圆圈、涡旋纹等。顶部上宽4.4、下宽6.2、长17.8、残高7.5厘米。"],
    245: ["172. 铜神坛，K2③:296，全器由兽形座、立人座、山形座和盝顶建筑、立鸟等构成，高53.3厘米。（复制件照片）"],
    251: ["173. 太阳形器，K2②:67（上），中心凸起的半球形为太阳，周围五条光芒呈放射状，芒外为晕圈。其形象有如四川岩画及三星堆二号祭祀坑出土青铜神殿屋盖上的“太阳光芒”。直径84厘米。K2③:1（下），器型同K2②:67。直径85厘米。"],
    282: ["196. 铜牌形饰，K2③:261-6，残件，形制及纹饰局部可辨。长约2.3—2.6厘米。"],
    272: [
        "186. 铜尊，K2②:129，肩上饰三个卷角羊头，三个羊头之间有三只立鸟。口径42.6、肩径28、通高45.5厘米。",
        "187. 铜尊，K2②:127，上饰云雷纹，肩上饰三个卷角羊头和三只立鸟。口径40.4、肩径28.8、通高41.6厘米。",
    ],
    274: ["189. 铜尊，K2②:122，以云雷纹为地，上饰兽面纹和三个牛头。口径34、肩径25.7、高31.5厘米。"],
    276: ["190. 铜罍，K2②:159，肩上饰四个大卷角羊头，以勾连云雷纹为地。口径26.5、通高54厘米。"],
    277: ["191. 铜罍，K2②:88，颈部有三周凸弦纹，肩上铸有四个卷羊头。肩部以云雷纹为地，上饰象鼻龙纹。口径20.3、通高35.4厘米。"],
    278: ["192. 铜罍，K2②:70，肩部以云雷纹为地，上饰象鼻龙纹。器身曾涂有朱色。口径21、肩径28、通高33.4厘米。"],
    325: ["盛贮器", "三星堆遗址出土的陶器中，用于盛贮物品的器物，占了三星堆陶器器形的主流，主要有各式各样的罐、缸、瓮、罍、尊等。"],
    328: ["5. 小平底缸，2000GST3108③:33，夹砂褐陶。口径约13厘米，底径约8厘米，高10.4厘米。"],
    329: ["7. 小平底罐，86GSIIIT1416⑧B:123，夹砂褐陶。口径13.6、底径2.8、高8.3厘米。"],
    331: ["12. 陶罐，86GSIIIT1416⑧B，夹砂灰陶。口径14.9、底径3.5、高10.3厘米。"],
    333: ["16. 小平底陶罐，86GSIIIT1516⑨:54，夹砂褐陶，外表曾饰黑衣。口径14.6、肩径17.5、底径3.7、高10.8厘米。"],
    361: ["54. 绳纹深腹罐，99GSZYT103⑨:118，夹砂灰陶。口径24.8、腹径14厘米。"],
    362: [
        "55. 大口缸，84GST104③:17。",
        "56. 器物，2000GSGH22:37。",
    ],
    367: ["64. 圈足器，2000GSGGCT3108TG16⑤，夹砂陶，口径约43.6厘米，圈足径约20.4厘米。"],
    371: ["67. 罍，86GSIIIT1415⑨:172，三足宽沿器泥质褐陶。口径18.5、腰沿直径36、高37.7厘米。"],
    373: ["食器", "三星堆遗址出土的陶器中，有部分是用于盛食物的器物，在这些器物中，有各种各样的盘、豆、钵、盆等。"],
    374: ["69. 器座，86GSIK1:320，夹砂陶，直径13.5厘米；K1:125，器座，夹砂红陶，直径6.6、高3厘米。"],
    386: ["89. 小平底盘，99GSZYH45:9，夹砂灰陶。口径约36厘米，底径8.7厘米。"],
    387: ["91. 曲腹盘，99GSZYT201⑨:4，夹砂黄陶。口径13.7厘米，底径记录残缺。"],
    389: ["95. 高柄豆，86GSDAT2③:36，泥质陶。盘口径18、圈足径16.7、高46厘米，圈足上饰一只“有眼纹”。"],
    391: ["98. 陶器，2000GSGCT3209H4:23，夹砂陶。残高约7.8厘米。"],
    392: ["100. 陶器，99GSZYT103⑨:120，夹砂灰陶。口径12.6、残高10厘米。"],
    395: ["酒器 水器", "三星堆遗址出土的陶器中，有部分是用于盛酒盛水的器物，在这些器物中，有各式各样的陶盉、壶、杯、觚、瓶。"],
    396: ["104. 陶杯，86GSIIIT1515③A，夹砂灰陶。口径11、底径4.3、高12.8厘米。"],
    415: [
        "129. 器物，99GSZYT112②，残件。",
        "130. 高领罐，84GST103③:2，夹砂褐陶，外饰黑陶衣。残高20厘米。",
    ],
    417: [
        "133. 陶盉，84GST003③:1，夹砂红陶。通高33.5厘米。",
        "134. 陶盉，86GSIIIT1416②C:120，夹砂褐陶。通高35.5厘米。",
    ],
    422: ["142. 高领罐，86GSIIIT1414③:4，夹砂褐陶。口径34、肩径33.5、底径6.7、通高63厘米。"],
    443: ["174. 器纽，86GSIIIT1214③C:53，夹砂红陶。宽17、残高11厘米。"],
    448: ["180. 陶器，86GSIIIT1517③A:85，夹砂灰陶。口径30.2、残高10.5厘米。"],
    449: ["181. 陶研磨器（正视），86GSIIITH36③:189，夹砂黑褐陶。口径22、底径9.5、残高18.1厘米。"],
    450: ["182. 陶研磨器（俯视），86GSIIITH36③:189，夹砂黑褐陶。口径22、底径9.5、残高18.1厘米。"],
    455: ["190. “陶器部件”，2000GSGgT3108Tg16:17，夹砂黑褐陶。长23.7、宽12、厚1.1厘米。"],
    468: ["205. 蟾蜍形器纽，86GST1416⑨，夹砂褐陶，外饰黑陶衣。残宽3.4、残高6.4厘米。"],
    477: ["218. 鸟头把，三件，均为泥质陶，器物编号见原图。"],
    499: ["246. “帆形器”，87GZG1③:1，泥质灰陶。直径6、高2.75厘米。"],
    511: ["6. 金叶饰，K130-19、23、24、26、25，薄片状，残件。"],
    594: ["71. 玉璧，K2②:89-4，灰白色，器面平，周缘较圆。通径25.8、孔径约11.5、肉宽约4.8厘米。"],
    597: ["74. 玉璧，K2②:146-3，白色，局部有朱砂痕。好径6.8、肉宽3.5、通径13.7厘米。"],
    581: ["59. 玉璧，K2②:19，碧玉质，淡绿色微黄。出土时仅存一半，残为三段，经拼接复原。肉两面平，厚薄均匀，周缘直。肉两面有八道同心圆凹纹。好两面边缘凸起较高，上缘平，微敞。好径6.5、肉宽2.8、通径12.2厘米。"],
    605: ["83. 玉矛，97GSDgM10:2，浅粒岩，白色，不透明。阔叶形，骹部残断。两面磨平，断面呈六边形，边刃较平。长6.9、宽3.3、厚0.6厘米。"],
    659: ["153. 玉凿，00607，顶端有一段灰白色，成柄状，其下为青灰色，纵剖面呈扁圆形，斜平顶，弧腰，弧刃。长9.6、宽3.4、厚2厘米。"],
    665: [
        "163. 玉凿，K1:240，灰—灰黑—灰白云母石英片岩。一面较平，有切割留下的“台阶”，另一面微凹。顶端有斜向的自然断裂面。全器最宽处在刃端，双面圆弧刃。宽1.7、厚0.9、高15.3厘米。",
        "164. 玉凿，K1:244，碧玉质片岩，白色，顶部黑色。器形厚，顶端残，弧刃。宽2.4、厚1.85、高12.4厘米。",
    ],
    667: ["168. 玉器，K1:261，残件，表面有灰黑色纹理。长约18.3厘米。"],
    681: ["195. 玉器，K2②:39-23，灰色斑点石质，顶端自然断裂。宽1.7、厚0.9、高15.6厘米。"],
    684: ["201. 玉器，K2②:89-39，顶端有自然断裂面，稍加磨光，刃缘可见。宽1.3、厚0.9厘米。"],
    685: ["203. 玉凿，K2②:89-36，斑点状石英片岩。体窄而长，两面平，两侧较直，刃端宽于顶端。宽2.3、厚1、高32.4厘米。"],
    695: ["210. 玉磨石，K2②:280-2，浅灰色云母石英片岩，长8.3、宽4.4、厚1厘米。"],
    697: ["222. 玉磨石，K2③:89-43，长椭圆形，中间厚，周边薄。"],
    698: ["224. 玉磨石，K2③:159，浅灰色云母石英片岩，体宽扁，一端斜抹，另一端有弧形刃。长14、宽8.6、厚0.95厘米。"],
    706: ["239. 石器，97GSDGM5:7，灰黑色纹理，略呈长方形，一面平，另一面弧拱。宽5.5、厚1.9厘米。"],
    707: ["241. 石器，编号00608，青灰色板岩。宽3.5、厚1.8厘米。"],
    743: ["36. 石斧，采:200，英片岩，磨制，弧顶，顶部有砸击过的痕迹，弧腰，上部及中部有一穿孔。残长9.5、残宽5.6厘米。"],
    745: ["38. 石斧，K1:247-4，砂岩。器物被火烧后多处炸裂、剥落。器物两面微凸起，两侧平直，正锋。刃宽4.7、器宽4.9、厚2、高18.1厘米。"],
    749: ["44. 石凿，00053，青灰色，长条形。顶端磨出刃部，单面刃，可作锛用。高5.5、宽1.1、厚0.8厘米。"],
    756: ["51. 石料，86GSIIIT1414⑧A:71，白色带麻点，似为卵石，表面磨圆。长条形，局部层状断裂，经拼接复原。高15.5、宽3.5、厚3.3厘米。"],
    753: ["49. 石兽，残件，牙齿整齐，腿部残。身长10.6、宽6.5、高4.4厘米。"],
}

WENWU_SECTION_REPLACEMENTS: dict[int, tuple[str, str, list[str]]] = {
    252: (
        "text",
        "high",
        [
            "### 兵器",
            "",
            "三星堆出土的铜戈是古蜀文化中的主要兵器。三星堆一、三号祭祀坑中出土的这些带有“锯齿”形的铜戈，属于祭祀礼仪活动中的仪仗器。这种器形在中国其他地区尚未见到。",
        ],
    ),
    306: ("frontmatter", "high", ["### 三星堆出土文物全记录"]),
    523: ("frontmatter", "high", ["### 三星堆出土文物全记录", "### 玉器·石器"]),
}


def build_jisikeng_replacements(path: Path) -> dict[int, tuple[str, str, list[str]]]:
    by_key, by_scan_page = extract_clean_jisikeng_index(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    pages = parse_pages(lines)
    replacements: dict[int, tuple[str, str, list[str]]] = {}

    for page in pages:
        if page.kind != "caption_or_map":
            continue
        captions: list[str] = []
        if page.number in by_scan_page:
            captions.extend(by_scan_page[page.number])
        body = "\n".join(page.lines)
        for key in noisy_keys(body):
            for caption in by_key.get(key, []):
                if caption not in captions:
                    captions.append(caption)
        if page.number in JISIKENG_MANUAL:
            captions = JISIKENG_MANUAL[page.number]
        if not captions:
            captions = clean_caption_lines(page.lines)
        if captions:
            replacements[page.number] = ("caption_or_map", "high", quote(captions))
    return replacements


def build_wenwu_replacements(path: Path) -> dict[int, tuple[str, str, list[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    pages = parse_pages(lines)
    replacements: dict[int, tuple[str, str, list[str]]] = {}
    for page in pages:
        captions = WENWU_MANUAL.get(page.number)
        if captions is not None:
            replacements[page.number] = ("caption_or_map", "medium", quote(captions))
            continue
        if page.kind != "caption_or_map":
            continue
        if captions is None:
            captions = clean_caption_lines(page.lines)
        if captions:
            replacements[page.number] = ("caption_or_map", "medium", quote(captions))
    return replacements


def main() -> int:
    changed = 0
    changed += rewrite_pages(MARKDOWN_DIR / "huaxia-shendu.polished.md", HUAXIA_REPLACEMENTS)
    changed += rewrite_pages(MARKDOWN_DIR / "renjian-tianguo.polished.md", RENJIAN_REPLACEMENTS)
    changed += rewrite_pages(MARKDOWN_DIR / "jisikeng.polished.md", build_jisikeng_replacements(MARKDOWN_DIR / "jisikeng.polished.md"))
    changed += normalize_jisikeng_catalog_ids(MARKDOWN_DIR / "jisikeng.polished.md")
    changed += rewrite_pages(MARKDOWN_DIR / "wenwu-quanjilu.polished.md", build_wenwu_replacements(MARKDOWN_DIR / "wenwu-quanjilu.polished.md"))
    changed += rewrite_pages(MARKDOWN_DIR / "wenwu-quanjilu.polished.md", WENWU_SECTION_REPLACEMENTS)
    changed += normalize_wenwu_catalog_ids(MARKDOWN_DIR / "wenwu-quanjilu.polished.md")
    print(f"caption pages updated: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
