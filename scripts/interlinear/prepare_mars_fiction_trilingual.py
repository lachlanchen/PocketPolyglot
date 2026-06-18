#!/usr/bin/env python3
"""Prepare Mars trilingual EN/JP/ZH chunk tasks."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from english_sentence_splitter import sentence_boundary_ends


ROOT = Path(__file__).resolve().parents[2]
SCIENCE_FICTION_DIR = Path("sources/mars/science-fiction")
SCIENCE_HISTORY_DIR = Path("sources/mars/science-history")
SOURCE_DIR = SCIENCE_FICTION_DIR
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)(?:\{[^}]+\})?")
BRACKET_REPEAT_RE = re.compile(r"^\[([^\]]+)\]\[[^\]]+\]$")
RT_RE = re.compile(r"<rt[^>]*>.*?</rt>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
EN_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?]["”’)]*\s+')
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
EN_DATE_HEADING_RE = re.compile(r"^(?:[A-Za-z]+ \d{4}|20\d{2}(?:-\d{2,4})?):\s+.+$")
EN_PART_WORDS = r"\d{1,3}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve"
EN_NUMBERED_TITLE_RE = re.compile(r"^(\d{1,3})\.\s+(.+)$")
EN_HEADING_RE = re.compile(
    rf"^(?:Prologue|Epilogue|Introduction|Conclusion|Nota Bene:\s+.+|Chapter\s+\d+(?:(?::|\s+).+)?|\d{{1,3}}[.:]\s+.+|\d{{1,3}}\s+[^.?!]{{2,80}}|PART\s+(?:[IVXLCDM]+|{EN_PART_WORDS})(?::|\s| • | -).+|Part\s+(?:[IVXLCDM]+|{EN_PART_WORDS})(?::|\s| • | -).+)$",
    re.IGNORECASE,
)
EN_PART_RE = re.compile(rf"^(?:PART|Part)\s+(?:[IVXLCDM]+|{EN_PART_WORDS})(?:(?::|\s| • | -).+)?$", re.IGNORECASE)
EN_NUMBER_ONLY_RE = re.compile(r"^\d{1,3}\.?$")
ZH_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百〇零0-9]+\s*章\s*.*$")
ZH_SECTION_HEADING_RE = re.compile(
    r"^第[一二三四五六七八九十百〇零0-9]+\s*[部卷篇].*(?:第[一二三四五六七八九十百〇零0-9]+\s*章.*)?$"
)
ZH_DATE_HEADING_RE = re.compile(
    r"^[一二三四五六七八九十〇零○0-9]{4}年(?:-|—|至|[一二三四五六七八九十〇零○0-9]{0,4}年)?\s*[一二三四五六七八九十冬春夏秋月0-9]*月?\s+.{1,30}$"
)
ZH_PART_RE = re.compile(r"^[IVX]+\s+.+$")
DROP_LINES = {
    "[]",
    "Cover",
    "Title Page",
    "Copyright Page",
    "Contents",
    "目录",
    "封面",
    "版权信息",
}
EN_STOP_HEADINGS = {
    "Acknowledgments",
    "Acknowledgements",
    "About the Author",
    "Also by",
    "Bibliography",
    "By Pierce Brown",
    "Copyright",
    "Dedication",
    "Index",
    "Notes",
    "Reading Group Guide",
}
ZH_STOP_HEADINGS = {"致谢", "致 谢", "关于作者", "版权信息"}
PDF_NOISE_LINES = {
    "F T ra n sf o",
    "PD rm",
    "Y",
    "er",
    "ABB",
    "y",
    "bu",
    "2.0",
    "to",
    "re",
    "he",
    "k",
    "lic",
    "C",
    "w",
    "w.",
    "A B B Y Y.c",
    "PUBLISHING HISTORY",
    "CHRONOLOGY:",
}
PDF_TEXT_FIXES = {
    "Churchil": "Churchill",
    "Druxnmond": "Drummond",
    "Parkhiil": "Parkhill",
    "Stendabi": "Stendahl",
    "bettle-car": "beetle-car",
    "cirde": "circle",
    "cirdes": "circles",
    "cradded": "crackled",
    "dapped": "clapped",
    "dasped": "clasped",
    "esctatic": "ecstatic",
    "exuse": "excuse",
    "flrebrands": "firebrands",
    "inawind": "in a wind",
    "induding": "including",
    "mintes": "minutes",
    "mirade": "miracle",
    "obeisks": "obelisks",
    "partides": "particles",
    "slammng": "slamming",
    "spectade": "spectacle",
    "withpered": "whispered",
    "wintar": "winter",
}


@dataclass
class Chapter:
    number: int
    title: str
    part: str = ""
    paragraphs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BookConfig:
    book_id: str
    title_en: str
    title_zh: str
    title_ja: str
    title_zh_reading: str
    title_ja_reading: str
    author: str
    author_reading_zh: str
    author_reading_ja: str
    en_source: Path | None
    zh_source: Path | None
    en_start_marker: str | None = None
    zh_start_marker: str | None = None
    zh_end_marker: str | None = None
    source_spine_lang: str = "en"
    book_description: str = ""
    task_mode: str = "trilingual_en_zh_sources_generated_ja"


BOOKS: dict[str, BookConfig] = {
    "red-rising-1": BookConfig(
        book_id="red-rising-1",
        title_en="Red Rising",
        title_zh="火星崛起",
        title_ja="レッド・ライジング",
        title_zh_reading="huǒ xīng jué qǐ",
        title_ja_reading="レッド ライジング",
        author="Pierce Brown",
        author_reading_zh="pí ěr sī bù lǎng",
        author_reading_ja="ピアス ブラウン",
        en_source=SOURCE_DIR / "Red Rising.epub",
        zh_source=SOURCE_DIR / "火星崛起（共三册）.epub",
        en_start_marker="I would have lived in peace.",
        zh_start_marker="第一章 地狱掘进者",
        zh_end_marker="火星崛起2：黄金之子",
        book_description="Pierce Brown, Red Rising. English EPUB is the alignment spine; Chinese trilogy EPUB is the reference; Japanese is generated in natural modern Japanese.",
    ),
    "red-rising-2": BookConfig(
        book_id="red-rising-2",
        title_en="Golden Son",
        title_zh="火星崛起2：黄金之子",
        title_ja="ゴールデン・サン",
        title_zh_reading="huǒ xīng jué qǐ èr huáng jīn zhī zǐ",
        title_ja_reading="ゴールデン サン",
        author="Pierce Brown",
        author_reading_zh="pí ěr sī bù lǎng",
        author_reading_ja="ピアス ブラウン",
        en_source=SOURCE_DIR / "Golden Son.epub",
        zh_source=SOURCE_DIR / "火星崛起（共三册）.epub",
        en_start_marker="Once upon a time,",
        zh_start_marker="第一章 将 领",
        zh_end_marker="火星崛起3：晨色之星",
        book_description="Pierce Brown, Golden Son. English EPUB is the alignment spine; Chinese trilogy EPUB is the reference; Japanese is generated in natural modern Japanese.",
    ),
    "red-rising-3": BookConfig(
        book_id="red-rising-3",
        title_en="Morning Star",
        title_zh="火星崛起3：晨色之星",
        title_ja="モーニング・スター",
        title_zh_reading="huǒ xīng jué qǐ sān chén sè zhī xīng",
        title_ja_reading="モーニング スター",
        author="Pierce Brown",
        author_reading_zh="pí ěr sī bù lǎng",
        author_reading_ja="ピアス ブラウン",
        en_source=SOURCE_DIR / "Morning Star.epub",
        zh_source=SOURCE_DIR / "火星崛起（共三册）.epub",
        en_start_marker="I rise into darkness,",
        zh_start_marker="第一章 只剩黑暗",
        zh_end_marker=None,
        book_description="Pierce Brown, Morning Star. English EPUB is the alignment spine; Chinese trilogy EPUB is the reference; Japanese is generated in natural modern Japanese.",
    ),
    "the-martian": BookConfig(
        book_id="the-martian",
        title_en="The Martian",
        title_zh="火星救援",
        title_ja="火星の人",
        title_zh_reading="huǒ xīng jiù yuán",
        title_ja_reading="かせい の ひと",
        author="Andy Weir",
        author_reading_zh="ān dí wēi ěr",
        author_reading_ja="アンディ ウィアー",
        en_source=SOURCE_DIR / "Weir, Andy - The Martian.epub",
        zh_source=SOURCE_DIR / "火星救援（译林幻系列）.epub",
        en_start_marker="Chapter 1",
        zh_start_marker="第一章",
        source_spine_lang="en",
        book_description="Andy Weir, The Martian. English EPUB is the alignment spine; Chinese EPUB is the reference; Japanese is generated in natural modern Japanese.",
    ),
    "martian-chronicles": BookConfig(
        book_id="martian-chronicles",
        title_en="The Martian Chronicles",
        title_zh="火星编年史",
        title_ja="火星年代記",
        title_zh_reading="huǒ xīng biān nián shǐ",
        title_ja_reading="かせい ねんだいき",
        author="Ray Bradbury",
        author_reading_zh="léi bù léi dé bó lǐ",
        author_reading_ja="レイ ブラッドベリ",
        en_source=SOURCE_DIR / "Bradbury, Ray - The Martian Chronicles.pdf",
        zh_source=SOURCE_DIR / "火星编年史.epub",
        en_start_marker="January 1999:",
        zh_start_marker="一九九九年一月 火箭之夏",
        zh_end_marker="本书由“行行”整理",
        source_spine_lang="en",
        book_description="Ray Bradbury, The Martian Chronicles. English PDF is the alignment spine; Chinese EPUB is the reference; Japanese is generated in natural modern Japanese.",
    ),
    "the-sirens-of-mars": BookConfig(
        book_id="the-sirens-of-mars",
        title_en="The Sirens of Mars",
        title_zh="火星的塞壬",
        title_ja="火星のセイレーン",
        title_zh_reading="huǒ xīng de sài rén",
        title_ja_reading="かせい の セイレーン",
        author="Sarah Stewart Johnson",
        author_reading_zh="sà lā sī tú ěr tè yuē hàn xùn",
        author_reading_ja="サラ スチュワート ジョンソン",
        en_source=SCIENCE_HISTORY_DIR / "The Sirens of Mars_ Searching for Life on Another World.epub",
        zh_source=None,
        en_start_marker="Prologue",
        source_spine_lang="en",
        task_mode="trilingual_en_source_generated_zh_ja",
        book_description="Sarah Stewart Johnson, The Sirens of Mars. English EPUB is the complete alignment spine; Chinese and Japanese are generated as natural explanatory translations for language learning.",
    ),
    "a-city-on-mars": BookConfig(
        book_id="a-city-on-mars",
        title_en="A City on Mars",
        title_zh="火星城市",
        title_ja="火星に都市をつくる",
        title_zh_reading="huǒ xīng chéng shì",
        title_ja_reading="かせい に とし を つくる",
        author="Kelly Weinersmith and Zach Weinersmith",
        author_reading_zh="kǎi lì wēi nà shǐ mì sī hé zhā kè wēi nà shǐ mì sī",
        author_reading_ja="ケリー ワイナースミス と ザック ワイナースミス",
        en_source=SCIENCE_HISTORY_DIR
        / "A City on Mars _ Can we settle space, should we settle space, and have we really thought this through_.epub",
        zh_source=None,
        en_start_marker="Introduction",
        source_spine_lang="en",
        task_mode="trilingual_en_source_generated_zh_ja",
        book_description="Kelly and Zach Weinersmith, A City on Mars. English EPUB is the complete alignment spine; Chinese and Japanese are generated as natural explanatory translations for language learning.",
    ),
    "red-mars": BookConfig(
        book_id="red-mars",
        title_en="Red Mars",
        title_zh="红火星",
        title_ja="レッド・マーズ",
        title_zh_reading="hóng huǒ xīng",
        title_ja_reading="レッド マーズ",
        author="Kim Stanley Robinson",
        author_reading_zh="jīn sī tǎn lì luó bīn xùn",
        author_reading_ja="キム スタンリー ロビンソン",
        en_source=SCIENCE_FICTION_DIR / "Red Mars.epub",
        zh_source=SCIENCE_FICTION_DIR / "108红火星.mobi",
        en_start_marker="Part One",
        zh_start_marker="第二部 太空远航 第一章",
        source_spine_lang="en",
        book_description="Kim Stanley Robinson, Red Mars. English EPUB is the complete alignment spine; Chinese MOBI is a partial reference beginning from the second part and should be used only when it matches the English location; Japanese is generated in natural modern Japanese.",
    ),
}


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT).decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def clean_line(raw_line: str) -> str:
    line = raw_line.replace("\\_", "_").replace("\\-", "-").replace("\\", "")
    line = BRACKET_REPEAT_RE.sub(r"\1", line)
    line = LINK_RE.sub(r"\1", line)
    line = RT_RE.sub("", line)
    line = TAG_RE.sub("", line)
    line = html.unescape(line)
    line = line.strip("> ")
    line = compact(line)
    bracketed = re.fullmatch(r"\[([A-Za-z0-9][^][]+)\]", line)
    if bracketed:
        line = bracketed.group(1).strip()
    if line.startswith("![]("):
        return ""
    if line in DROP_LINES:
        return ""
    if "暂缺" in line and len(line) <= 24:
        return ""
    if re.fullmatch(r"[-+=*#_•. ]{3,}", line):
        return ""
    return line


def epub_lines(path: Path) -> list[str]:
    raw = run_text(["pandoc", str(path), "-t", "plain", "--wrap=none"])
    return [line for line in (clean_line(raw_line) for raw_line in raw.splitlines()) if line]


def html_lines(path: Path) -> list[str]:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    for node in soup(["script", "style"]):
        node.decompose()
    return [line for line in (clean_line(raw_line) for raw_line in soup.get_text("\n").splitlines()) if line]


def mobi_lines(path: Path) -> list[str]:
    import mobi

    tempdir, extracted = mobi.extract(str(ROOT / path))
    try:
        extracted_path = Path(extracted)
        suffix = extracted_path.suffix.lower()
        if suffix == ".epub":
            raw = run_text(["pandoc", str(extracted_path), "-t", "plain", "--wrap=none"])
            return [line for line in (clean_line(raw_line) for raw_line in raw.splitlines()) if line]
        if suffix in {".html", ".htm"}:
            return html_lines(extracted_path)
        if suffix == ".pdf":
            return pdf_lines_with_blanks(extracted_path)
        raise RuntimeError(f"unsupported MOBI extraction output: {extracted_path}")
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def clean_pdf_line(raw_line: str) -> str:
    line = clean_line(raw_line.replace("\f", ""))
    line = re.sub(r"\s+", " ", line).strip()
    if not line:
        return ""
    if line in PDF_NOISE_LINES:
        return ""
    if "ABBYY" in line or "A B B Y Y" in line:
        return ""
    if re.fullmatch(r"[YwCk]|lic|he|re|to|bu|er|rm|PD|ABB", line):
        return ""
    if line.startswith("Copyright ") or line.startswith("ISBN ") or line.startswith("A Bantam"):
        return ""
    line = clean_pdf_text(line)
    return line


def pdf_lines_with_blanks(path: Path) -> list[str]:
    raw = run_text(["pdftotext", "-layout", str(path), "-"])
    return [clean_pdf_line(raw_line) for raw_line in raw.splitlines()]


def clean_pdf_text(text: str) -> str:
    text = text.replace("sucked. dry", "sucked dry")
    text = text.replace("told me- -well", "told me--well")
    text = text.replace('"Yll, lower your voice.\'', '"Yll, lower your voice."')
    for bad, good in PDF_TEXT_FIXES.items():
        text = re.sub(rf"\b{re.escape(bad)}\b", good, text)
    return compact(text)


def looks_like_en_prose(line: str) -> bool:
    if EN_HEADING_RE.match(line) or is_en_stop_heading(line):
        return False
    return len(line) >= 35 and bool(re.search(r"[A-Za-z]{3,}", line))


def looks_like_zh_prose(line: str) -> bool:
    if (
        ZH_CHAPTER_RE.match(line)
        or ZH_SECTION_HEADING_RE.match(line)
        or ZH_DATE_HEADING_RE.match(line)
        or ZH_PART_RE.match(line)
        or line in ZH_STOP_HEADINGS
    ):
        return False
    return len(line) >= 12 and len(CJK_RE.findall(line)) >= 6


def find_en_body_start(lines: list[str], preferred: str) -> int:
    if preferred:
        candidates = [index for index, line in enumerate(lines) if marker_matches(line, preferred)]
        for index in candidates:
            window = lines[index + 1 : index + 18]
            if any(looks_like_en_prose(item) for item in window):
                return index
        if candidates:
            return candidates[-1]
    for index, line in enumerate(lines):
        if EN_HEADING_RE.match(line) and any(looks_like_en_prose(item) for item in lines[index + 1 : index + 12]):
            return index
    return 0


def chapter_title_en(line: str, fallback_number: int) -> str:
    if line.lower() == "prologue":
        return "Prologue"
    if line.lower() == "epilogue":
        return "Epilogue"
    if EN_PART_RE.match(line):
        return line
    return line or f"Chapter {fallback_number}"


def looks_like_en_part(line: str) -> bool:
    return bool(EN_PART_RE.match(line)) and len(line) <= 90


def is_en_stop_heading(line: str) -> bool:
    return line in EN_STOP_HEADINGS or line.startswith("Praise for ") or line.startswith("Also by ")


def looks_like_en_heading(line: str) -> bool:
    if is_en_stop_heading(line):
        return False
    if looks_like_en_part(line):
        return True
    if EN_DATE_HEADING_RE.match(line):
        return True
    if line.lower() in {"prologue", "epilogue"}:
        return True
    if line.lower() in {"introduction", "conclusion"}:
        return True
    if re.match(r"^Chapter\s+\d+(?:(?::|\s+).+)?$", line, re.IGNORECASE):
        return True
    if re.match(r"^Nota Bene:\s+.+$", line, re.IGNORECASE):
        return True
    if re.match(r"^\d{1,3}:\s+.+$", line):
        return True
    if re.match(r"^\d{1,3}\s+[^.?!]{2,80}$", line):
        return True
    return False


def pdf_heading_title(line: str) -> str:
    if EN_DATE_HEADING_RE.match(line):
        left, _, right = line.partition(":")
        return f"{left.strip()}: {right.strip()}"
    return chapter_title_en(line, 1)


def parse_en_pdf(path: Path, *, preferred_start: str) -> list[Chapter]:
    lines = pdf_lines_with_blanks(path)
    starts = [index for index, line in enumerate(lines) if preferred_start and preferred_start in line]
    start = starts[-1] if starts else 0
    chapters: list[Chapter] = []
    current: Chapter | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if current is None or not paragraph_lines:
            paragraph_lines = []
            return
        text = compact(" ".join(paragraph_lines))
        paragraph_lines = []
        if text and looks_like_en_prose(text):
            current.paragraphs.extend(split_english_units(text, max_chars=900))

    for line in lines[start:]:
        if not line:
            flush_paragraph()
            continue
        if line == "ABOUT THE AUTHOR":
            flush_paragraph()
            break
        if line in {"THE MARTIAN CHRONICLES", "For my wife MARGUERITE with all my love"}:
            continue
        if looks_like_en_heading(line):
            flush_paragraph()
            current = Chapter(number=len(chapters) + 1, title=pdf_heading_title(line), part="")
            chapters.append(current)
            continue
        if current is None:
            continue
        if len(line) <= 2:
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    for chapter in chapters:
        chapter.paragraphs = merge_pdf_continuations(chapter.paragraphs)
    return [chapter for chapter in chapters if chapter.paragraphs]


def is_incomplete_english_unit(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and not re.search(r'[.!?]["”’)]*_?$', stripped)


def starts_like_continuation(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and bool(re.match(r'^(?:["_])?[a-z]', stripped))


def merge_pdf_continuations(paragraphs: list[str]) -> list[str]:
    merged: list[str] = []
    for paragraph in paragraphs:
        paragraph = clean_pdf_text(paragraph)
        if merged and is_incomplete_english_unit(merged[-1]) and starts_like_continuation(paragraph):
            merged[-1] = compact(f"{merged[-1]} {paragraph}")
        else:
            merged.append(paragraph)
    return merged


def can_be_split_title(line: str) -> bool:
    if not line or looks_like_en_heading(line) or line in EN_STOP_HEADINGS:
        return False
    if re.match(r"^\d{1,3}[.)]\s+", line):
        return False
    if looks_like_en_prose(line):
        return False
    return bool(re.search(r"[A-Za-z]", line)) and len(line) <= 80


def can_be_numbered_chapter_title(line: str) -> bool:
    if not line or is_en_stop_heading(line) or looks_like_en_part(line):
        return False
    if re.match(r"^\d{1,3}[.)]", line):
        return False
    return bool(re.search(r"[A-Za-z]", line)) and len(line) <= 150


def parse_en_epub(path: Path, *, preferred_start: str) -> list[Chapter]:
    lines = epub_lines(path)
    start = find_en_body_start(lines, preferred_start)
    chapters: list[Chapter] = []
    current: Chapter | None = None
    current_part = ""
    next_numbered_chapter = 1

    index = start
    while index < len(lines):
        line = lines[index]
        if is_en_stop_heading(line) and chapters:
            break
        if looks_like_en_part(line):
            if current_part.startswith(line) and current is not None and current.paragraphs:
                index += 1
                continue
            current_part = line
            current = None
            index += 1
            continue
        if current_part and current is None and can_be_split_title(line):
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if EN_NUMBER_ONLY_RE.match(next_line) or looks_like_en_heading(next_line):
                current_part = f"{current_part}: {line}"
                index += 1
                continue
            current = Chapter(number=len(chapters) + 1, title=line, part=current_part)
            chapters.append(current)
            index += 1
            continue
        if EN_NUMBER_ONLY_RE.match(line) and index + 1 < len(lines) and can_be_numbered_chapter_title(lines[index + 1]):
            title = f"{line.rstrip('.')}. {lines[index + 1]}"
            current = Chapter(number=len(chapters) + 1, title=title, part=current_part)
            chapters.append(current)
            index += 2
            continue
        if looks_like_en_heading(line):
            current = Chapter(number=len(chapters) + 1, title=chapter_title_en(line, len(chapters) + 1), part=current_part)
            chapters.append(current)
            index += 1
            continue
        if (
            current is not None
            and not current.paragraphs
            and current.title.lower() in {"introduction", "conclusion", "prologue", "epilogue"}
            and can_be_split_title(line)
        ):
            current.title = f"{current.title}: {line}"
            index += 1
            continue
        if current is None:
            current = Chapter(number=1, title="Prologue", part=current_part)
            chapters.append(current)
        if looks_like_en_prose(line) or len(line) >= 8:
            current.paragraphs.extend(split_english_units(line, max_chars=900))
        index += 1
    return [chapter for chapter in chapters if chapter.paragraphs]


def parse_en_source(path: Path, *, preferred_start: str) -> list[Chapter]:
    if path.suffix.lower() == ".pdf":
        return parse_en_pdf(path, preferred_start=preferred_start)
    return parse_en_epub(path, preferred_start=preferred_start)


def normalize_marker(text: str) -> str:
    return compact(text).replace("　", " ").replace(" ", " ").replace(" ", " ")


def marker_matches(line: str, marker: str) -> bool:
    normalized = normalize_marker(line)
    marker_norm = normalize_marker(marker)
    marker_compact = marker_norm.replace(" ", "")
    normalized_compact = normalized.replace(" ", "")
    return normalized == marker_norm or marker_compact in normalized_compact


def find_last_marker_before(lines: list[str], marker: str, end: int | None = None) -> int:
    search_end = len(lines) if end is None else end
    hits = [index for index, line in enumerate(lines[:search_end]) if marker_matches(line, marker)]
    if not hits:
        raise RuntimeError(f"marker not found before {search_end}: {marker}")
    return hits[-1]


def marker_hits(lines: list[str], marker: str) -> list[int]:
    return [index for index, line in enumerate(lines) if marker_matches(line, marker)]


def find_first_marker_after(lines: list[str], marker: str, start: int) -> int:
    for index in range(start + 1, len(lines)):
        if marker_matches(lines[index], marker):
            return index
    raise RuntimeError(f"marker not found after {start}: {marker}")


def extract_zh_segment(lines: list[str], *, start_marker: str | None, end_marker: str | None) -> list[str]:
    if not start_marker:
        start = 0
    elif end_marker:
        starts = marker_hits(lines, start_marker)
        ends = marker_hits(lines, end_marker)
        candidates = [hit for hit in starts if any(end > hit for end in ends)]
        if not candidates:
            raise RuntimeError(f"marker pair not found: start={start_marker} end={end_marker}")
        start = candidates[-1]
    else:
        start = find_last_marker_before(lines, start_marker)
    end = find_first_marker_after(lines, end_marker, start) if end_marker else len(lines)
    return lines[start:end]


def parse_zh_lines(lines: list[str]) -> list[Chapter]:
    chapters: list[Chapter] = []
    current: Chapter | None = None
    current_part = ""
    for line in lines:
        if line in ZH_STOP_HEADINGS and chapters:
            break
        if ZH_PART_RE.match(line) and len(line) <= 16:
            current_part = line
            continue
        if ZH_CHAPTER_RE.match(line) or ZH_SECTION_HEADING_RE.match(line) or ZH_DATE_HEADING_RE.match(line):
            current = Chapter(number=len(chapters) + 1, title=line, part=current_part)
            chapters.append(current)
            continue
        if current is None:
            current = Chapter(number=1, title="正文", part=current_part)
            chapters.append(current)
        if looks_like_zh_prose(line) or (CJK_RE.search(line) and len(line) >= 8):
            current.paragraphs.append(line)
    return [chapter for chapter in chapters if chapter.paragraphs]


def parse_zh_epub(path: Path, *, start_marker: str | None, end_marker: str | None) -> list[Chapter]:
    lines = epub_lines(path)
    segment = extract_zh_segment(lines, start_marker=start_marker, end_marker=end_marker)
    return parse_zh_lines(segment)


def parse_zh_source(path: Path | None, *, start_marker: str | None, end_marker: str | None) -> list[Chapter]:
    if path is None:
        return []
    suffix = path.suffix.lower()
    if suffix == ".mobi":
        lines = mobi_lines(path)
        segment = extract_zh_segment(lines, start_marker=start_marker, end_marker=end_marker)
        return parse_zh_lines(segment)
    return parse_zh_epub(path, start_marker=start_marker, end_marker=end_marker)


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
        if pending and len(pending) + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = f"{pending} {piece}".strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def markdown_for_chapters(title: str, chapters: list[Chapter]) -> str:
    out = [f"# {title}", ""]
    for chapter in chapters:
        if chapter.part:
            out.extend([f"## {chapter.part}", ""])
        out.extend([f"## {chapter.title}", ""])
        out.extend(chapter.paragraphs)
        out.append("")
    return "\n".join(out).strip() + "\n"


def all_text(chapters: list[Chapter]) -> str:
    return "\n".join(paragraph for chapter in chapters for paragraph in chapter.paragraphs)


def reference_window(text: str, start_ratio: float, end_ratio: float, *, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    start = max(0, int(len(text) * start_ratio) - max_chars // 3)
    end = min(len(text), int(len(text) * end_ratio) + max_chars // 2)
    if end - start < max_chars:
        extra = max_chars - (end - start)
        start = max(0, start - extra // 2)
        end = min(len(text), end + extra // 2)
    return text[start:end]


def make_chunks(
    config: BookConfig,
    en_chapters: list[Chapter],
    zh_chapters: list[Chapter],
    *,
    max_chunk_chars: int,
    reference_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spine_lang = config.source_spine_lang
    spine_chapters = en_chapters if spine_lang == "en" else zh_chapters
    reference_chapters = zh_chapters if spine_lang == "en" else en_chapters
    reference_text = all_text(reference_chapters)
    has_zh_reference = bool(zh_chapters)
    total_chars = max(sum(len(p) + 1 for c in spine_chapters for p in c.paragraphs), 1)
    chunks: list[dict[str, Any]] = []
    global_cursor = 0
    paragraph_count = 0

    for chapter in spine_chapters:
        pending: list[dict[str, str]] = []
        pending_start = global_cursor
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_start, pending_chars
            if not pending:
                return
            chunk_number = len(chunks) + 1
            chunk_id = f"{config.book_id}-c{chunk_number:04d}"
            start_ratio = pending_start / total_chars
            end_ratio = min(1.0, (pending_start + pending_chars) / total_chars)
            ref = reference_window(reference_text, start_ratio, end_ratio, max_chars=reference_chars)
            source_ref = "\n".join(item[spine_lang] for item in pending)
            if spine_lang == "en":
                reference = {
                    "english": {"available": True, "chapter": chapter.title, "text": source_ref},
                    "zh_primary": {
                        "available": has_zh_reference and bool(ref),
                        "chapter": "global-ratio-window",
                        "text": ref,
                        "quality": "published_translation_reference" if has_zh_reference else "generate_from_english_spine",
                    },
                    "zh_secondary": {"available": False, "chapter": "", "text": ""},
                    "ja": {"available": False, "chapter": "", "text": ""},
                }
            else:
                reference = {
                    "english": {
                        "available": bool(ref),
                        "chapter": "global-ratio-window",
                        "text": ref,
                        "quality": "source_unavailable_or_ratio_reference",
                    },
                    "zh_primary": {
                        "available": True,
                        "chapter": chapter.title,
                        "text": source_ref,
                        "quality": "published_translation_source_spine",
                    },
                    "zh_secondary": {"available": False, "chapter": "", "text": ""},
                    "ja": {"available": False, "chapter": "", "text": ""},
                }
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": config.book_id,
                    "source_spine_lang": spine_lang,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_number,
                    "chapter_id": f"chapter-{chapter.number:03d}",
                    "chapter_number": chapter.number,
                    "chapter_title_en": chapter.title if spine_lang == "en" else config.title_en,
                    "chapter_title_zh": chapter.title if spine_lang == "zh" else "",
                    "chapter_part_en": chapter.part,
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": reference,
                }
            )
            pending = []
            pending_chars = 0

        for paragraph in chapter.paragraphs:
            paragraph_count += 1
            paragraph_id = f"{config.book_id}-s{chapter.number:03d}-p{paragraph_count:05d}"
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
                pending_start = global_cursor
            if not pending:
                pending_start = global_cursor
            pending.append({"id": paragraph_id, spine_lang: paragraph})
            pending_chars += len(paragraph) + 1
            global_cursor += len(paragraph) + 1
        flush()

    source_paths: dict[str, Any] = {}
    if config.zh_source:
        source_paths["zh"] = str(config.zh_source)
    if config.en_source:
        source_paths["en"] = str(config.en_source)
    source_sha256: dict[str, Any] = {}
    if config.zh_source:
        source_sha256["zh"] = sha256(config.zh_source)
    if config.en_source:
        source_sha256["en"] = sha256(config.en_source)
    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": config.book_id,
        "book_title_en": config.title_en,
        "book_title_zh": config.title_zh,
        "book_title_ja": config.title_ja,
        "book_title_zh_reading": config.title_zh_reading,
        "book_title_ja_reading": config.title_ja_reading,
        "author": config.author,
        "author_reading_zh": config.author_reading_zh,
        "author_reading_ja": config.author_reading_ja,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": spine_lang,
        "source_paths": source_paths,
        "source_sha256": source_sha256,
        "source_note": config.book_description,
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


def prepare_book(config: BookConfig, args: argparse.Namespace) -> dict[str, Any]:
    en_chapters: list[Chapter] = []
    if config.en_source:
        preferred = config.en_start_marker or ("Chapter 1" if config.book_id == "the-martian" else "Prologue")
        en_chapters = parse_en_source(config.en_source, preferred_start=preferred)
        if not en_chapters:
            raise RuntimeError(f"no English chapters parsed for {config.book_id}")
    zh_chapters = parse_zh_source(config.zh_source, start_marker=config.zh_start_marker, end_marker=config.zh_end_marker)
    if config.source_spine_lang == "zh" and not zh_chapters:
        raise RuntimeError(f"no Chinese chapters parsed for {config.book_id}")

    book_root = Path("books") / config.book_id
    if en_chapters:
        write_text(book_root / "markdown/en.md", markdown_for_chapters(config.title_en, en_chapters))
    if zh_chapters:
        write_text(book_root / "markdown/zh.md", markdown_for_chapters(config.title_zh, zh_chapters))

    manifest, chunks = make_chunks(
        config,
        en_chapters,
        zh_chapters,
        max_chunk_chars=args.max_chunk_chars,
        reference_chars=args.reference_chars,
    )
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"
    write_json(chunks_dir / "manifest.json", manifest)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    source_paths: dict[str, Any] = {}
    if config.zh_source:
        source_paths["zh"] = str(config.zh_source)
    if config.en_source:
        source_paths["en"] = str(config.en_source)
    plan = {
        "schema_version": 1,
        "book_id": config.book_id,
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": config.task_mode,
        "source_spine_lang": config.source_spine_lang,
        "source_paths": source_paths,
        "source_sha256": manifest["source_sha256"],
        "markdown": {
            **({"en": str(book_root / "markdown/en.md")} if en_chapters else {}),
            **({"zh": str(book_root / "markdown/zh.md")} if zh_chapters else {}),
        },
        "book_title_en": config.title_en,
        "book_title_zh": config.title_zh,
        "book_title_ja": config.title_ja,
        "book_title_zh_reading": config.title_zh_reading,
        "book_title_ja_reading": config.title_ja_reading,
        "author": config.author,
        "author_reading_zh": config.author_reading_zh,
        "author_reading_ja": config.author_reading_ja,
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "book_description": config.book_description,
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": "global_ratio_window",
        "chunks_jsonl": str(chunks_dir / "chunks.jsonl"),
        "chunks_manifest": str(chunks_dir / "manifest.json"),
        "raw_chunk_dir": str(raw_chunk_dir),
        "preview_json": str(preview_dir / f"{config.book_id}.partial.json"),
        "assembled_json": str(preview_dir / f"{config.book_id}.partial.json"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "english_chapter_count": len(en_chapters),
        "chinese_reference_chapter_count": len(zh_chapters),
    }
    write_json(book_root / "book-plan.json", plan)
    return {
        "book_id": config.book_id,
        "chunks": len(chunks),
        "english_chapters": len(en_chapters),
        "chinese_chapters": len(zh_chapters),
        "spine": config.source_spine_lang,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--reference-chars", type=int, default=9000)
    args = parser.parse_args()

    selected = args.book_id or list(BOOKS)
    for book_id in selected:
        result = prepare_book(BOOKS[book_id], args)
        print(
            "prepared "
            f"book_id={result['book_id']} chunks={result['chunks']} "
            f"en_chapters={result['english_chapters']} zh_chapters={result['chinese_chapters']} "
            f"spine={result['spine']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
