#!/usr/bin/env python3
"""Prepare modern prose EN-JP-ZH trilingual PocketPolyglot tasks.

The input is a queue JSON under data/source-plan/. Each task uses one declared
English, Japanese, or Chinese source as the alignment spine and prepares
launchable chunk manifests for the standard trilingual writer. This script does
not start model workers.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from english_sentence_splitter import sentence_boundary_ends

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover - optional quality dependency
    zipf_frequency = None


ROOT = Path(__file__).resolve().parents[2]
SPACE_RE = re.compile(r"\s+")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_IMAGE_LINE_RE = re.compile(
    r"^\s*!\[(?P<caption>[^\]]*)\]\((?P<path>[^)\n]+)\)\s*$"
)
MARKDOWN_IMAGE_RE = re.compile(
    r"!\[(?P<caption>[^\]]*)\]\((?P<path>[^)\n]+)\)"
)
MARKER_PAGE_RE = re.compile(r"(?:^|[-_/])_?page_(?P<page>\d+)(?:_|[-/.])", re.I)
PAGE_NUMBER_RE = re.compile(r"^(?:[-–—]?\s*)?(?:\d{1,5}|[ivxlcdm]{1,10})(?:\s*[-–—]?)?$", re.I)
RUNNING_HEADER_RE = re.compile(
    r"^(?:"
    r"(?:\d{1,4}|[ivxlcdm]{1,10})\s+(?:preface|introduction|prologue|epilogue|book\s+[ivxlcdm]+|chapter\s+(?:\d+|[ivxlcdm]+))|"
    r"(?:preface|introduction|prologue|epilogue|book\s+[ivxlcdm]+|chapter\s+(?:\d+|[ivxlcdm]+))\s+(?:\d{1,4}|[ivxlcdm]{1,10})"
    r")$",
    re.I,
)
LATIN_RE = re.compile(r"[A-Za-z]{3,}")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
SENTENCE_END_RE = re.compile(r'[.!?]["”’)\]]*$')
CJK_SENTENCE_END_RE = re.compile(r'[。！？!?；;][」』”’）)\]】〉》]*$')
HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+)?(?:"
    r"Introduction|Foreword|Preface|Prologue|Epilogue|Conclusion|Afterword|Acknowledg(?:e)?ments|"
    r"(?:Part|Book|Chapter|CHAPTER)\s+(?:[IVXLCDM]+|\d+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b.*|"
    r"\d{1,3}[.)]\s+.{2,90}"
    r")$",
    re.I,
)
BOILERPLATE_RE = re.compile(
    r"(copyright|all rights reserved|isbn|published by|printed in|library of congress|"
    r"www\.|http[s]?://|ebook|cover design|permissions|random house|penguin|"
    r"basic books|oxford university press|mcgraw-hill|wiley)",
    re.I,
)
OCR_METADATA_RE = re.compile(
    r"^(?:source_pdf|conversion|generated_at|total_pdf_pages|ocr_|title):\s+",
    re.I,
)
OCR_PAGE_RE = re.compile(r"^#{1,6}\s+Page\s+\d+\b", re.I)
PAGE_ARTIFACT_RE = re.compile(
    r"^(?:Page\s+\d+|P(?:S|AGE)(?:\s+.+)?|[.$\sA-Z0-9_-]{8,}|"
    r"Trim Size:.+|k(?:\s+k)*|l)$"
)
TERMINAL_BACK_MATTER_RE = re.compile(
    r"\s+(?:"
    r"N\s*ot\s*e\s*s(?:\s+C\s*h\s*a\s*p\s*t\s*e\s*r|\s+Chapter|\b)|"
    r"References\b|Bibliography\b|Glossary\b|Index\b|"
    r"About the Author\b|ALSO BY\b|Copyright\b|Manufactured in China\b|"
    r"Get personalized book picks\b"
    r")"
)
I_VERBS = r"also|am|was|were|have|had|hope|think|believe|will|would|can|could|shall|should|do|did|must|may|might|owe|thank"
BROKEN_I_RE = re.compile(rf"(?:(?<=^)|(?<=[\s\"“‘(\[]))[\[|](?=\s*(?:{I_VERBS})\b)")
STUCK_I_RE = re.compile(rf"\bI(?=(?:{I_VERBS})\b)")
LOWER_L_I_RE = re.compile(rf"(?:(?<=^)|(?<=[\s\"“‘(\[]))l(?=\s+(?:{I_VERBS})\b)")
PUNCT_SPACE_RE = re.compile(r"([,.;:!?])(?=([A-Za-z]|\d))")
SPACED_THOUSAND_RE = re.compile(r"\b(\d)\s+(\d{2})\s*,\s*(\d{3})\b")
NUM_COMMA_SPACE_RE = re.compile(r"\b(\d{1,3})\s*,\s*(\d{3})\b")
THOUSANDS_CONTINUATION_SPACE_RE = re.compile(r"(?<=\d{3}),\s+(?=\d{3}\b)")
SPACED_YEAR_RE = re.compile(r"\b([12])\s+(\d)\s+(\d)\s+(\d)(s?)\b")
SPACED_SMALL_INT_RE = re.compile(
    r"\b([1-9])\s+(\d)(?=\s+(?:billion|million|thousand|percent|inch|inches|feet|"
    r"miles|seconds|years|dimensions|dimensional|centimeters|meters|pages|chapters)\b)"
)
SPLIT_WORD_RE = re.compile(r"\b([a-z]{2,})\s+([a-z]{2,})\b")
SINGLE_HYPHEN_WORD_RE = re.compile(r"(?<!-)\b([A-Za-z]{2,})-([A-Za-z]{2,})\b(?!-)")
LETTER_SPACED_HEADER_RE = re.compile(r"^(?:[A-Z]\s+){3,}[A-Z](?:\s+(?:[A-Z]\s+){2,}[A-Z])*$")
CHAPTER_HEADING_RE = re.compile(
    r"^(?:Part|Book|Chapter|CHAPTER)\s+(?:[IVXLCDM]+|\d+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b(?:\s*[:.-]?\s+.{2,70})?$",
    re.I,
)
SPECIAL_HEADING_RE = re.compile(r"^(?:Introduction|Foreword|Preface|Prologue|Epilogue|Conclusion|Afterword|Acknowledg(?:e)?ments)$", re.I)
NUMERIC_HEADING_RE = re.compile(r"^\d{1,3}[.)]\s+[A-Z][A-Za-z0-9 ,:'\"&-]{2,90}$")
CJK_HEADING_RE = re.compile(
    r"^(?:第[〇零一二三四五六七八九十百千万两兩\d]+[卷巻部篇章回節节]|"
    r"[〇零一二三四五六七八九十百千万两兩\d]+[、.．\s]+|"
    r"\S.{0,60}\s+第[〇零一二三四五六七八九十百千万两兩\d]+部$)\S*.{0,88}$"
)
KEEP_HYPHENATED = {
    "as-yet",
    "big-bang",
    "black-hole",
    "black-holes",
    "brain-stimulating",
    "cutting-edge",
    "down-to",
    "earth-like",
    "far-reaching",
    "full-fledged",
    "general-level",
    "higher-dimensional",
    "left-right",
    "long-sought",
    "mind-bending",
    "old-fashioned",
    "page-turning",
    "paradigm-shaking",
    "self-consistent",
    "self-contained",
    "space-time",
    "space-based",
    "three-dimensional",
    "two-dimensional",
    "well-known",
}

CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"


def source_spine_lang(task: dict[str, Any]) -> str:
    lang = str(task.get("source_spine_lang") or "en").strip().lower()
    if lang not in {"en", "ja", "zh"}:
        raise ValueError(f"unsupported source_spine_lang: {lang!r}")
    return lang


def source_title(task: dict[str, Any]) -> str:
    lang = source_spine_lang(task)
    return str(task.get(f"title_{lang}") or task.get("title_en") or task["book_id"])


def has_language_content(text: str, lang: str) -> bool:
    if lang == "en":
        return bool(LATIN_RE.search(text))
    if lang == "ja":
        return bool(KANA_RE.search(text) or CJK_RE.search(text))
    return bool(CJK_RE.search(text))


def visible_content_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, stderr=subprocess.STDOUT).decode("utf-8", errors="replace")


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def repair_embedded_text_artifacts(text: str) -> str:
    """Repair common PDF embedded-text artifacts without rewriting prose.

    This is deliberately conservative. It targets artifacts seen in born-digital
    nonfiction PDFs: OCR-style `| hope` / `[ have`, missing spaces after
    punctuation, and dictionary-backed intra-word hyphenation such as
    `mod-ern` or `math-ematics`. Real compounds are kept.
    """

    text = BROKEN_I_RE.sub("I", text)
    text = LOWER_L_I_RE.sub("I", text)
    text = STUCK_I_RE.sub("I ", text)
    text = PUNCT_SPACE_RE.sub(r"\1 ", text)
    text = SPACED_THOUSAND_RE.sub(r"\1\2,\3", text)
    previous = None
    while previous != text:
        previous = text
        text = NUM_COMMA_SPACE_RE.sub(r"\1,\2", text)
        text = THOUSANDS_CONTINUATION_SPACE_RE.sub(",", text)
    text = SPACED_YEAR_RE.sub(r"\1\2\3\4\5", text)
    text = SPACED_SMALL_INT_RE.sub(r"\1\2", text)
    text = text.replace(" .", ".").replace(" ,", ",")
    if text.startswith("uring the last thirty years"):
        text = "D" + text
    text = re.sub(r"\bC alling\b", "Calling", text)
    text = text.replace("al] the way", "all the way")
    text = text.replace("cach of these", "each of these")
    text = text.replace("cither small", "either small")
    text = text.replace("when scen", "when seen")
    text = text.replace("struc-tureless", "structureless")
    text = text.replace("experi-mentalists", "experimentalists")
    if text.startswith("HADN'T EXPECTED MY POPULAR BOOK"):
        text = "I " + text
    text = text.replace("W, EACH EXIST", "WE EACH EXIST")

    if zipf_frequency is not None:
        def dehyphen(match: re.Match[str]) -> str:
            original = match.group(0)
            lower = original.casefold()
            if lower in KEEP_HYPHENATED:
                return original
            left, right = match.group(1), match.group(2)
            joined = left + right
            if zipf_frequency(joined.casefold(), "en") >= 2.2:
                return joined
            return original

        text = SINGLE_HYPHEN_WORD_RE.sub(dehyphen, text)

        def join_split_word(match: re.Match[str]) -> str:
            left, right = match.group(1), match.group(2)
            joined = left + right
            if (
                zipf_frequency(joined, "en") >= 3.15
                and min(zipf_frequency(left, "en"), zipf_frequency(right, "en")) <= 2.25
            ):
                return joined
            return match.group(0)

        previous = None
        while previous != text:
            previous = text
            text = SPLIT_WORD_RE.sub(join_split_word, text)
    split_pair_fixes = {
        "cos mos": "cosmos",
        "ques tion": "question",
        "ques tions": "questions",
        "descrip tion": "description",
        "descrip tions": "descriptions",
        "scien tific": "scientific",
        "scien tists": "scientists",
        "experi ments": "experiments",
        "ex perience": "experience",
        "ex periments": "experiments",
        "under standing": "understanding",
        "elec tron": "electron",
        "elec trons": "electrons",
        "pro tons": "protons",
        "neu trons": "neutrons",
        "sys tem": "system",
        "sys tems": "systems",
        "every thing": "everything",
        "any thing": "anything",
        "longterm": "long-term",
    }
    for bad, good in split_pair_fixes.items():
        text = re.sub(rf"\b{re.escape(bad)}\b", good, text)
    spaced_word_fixes = {
        "C l assical": "Classical",
        "R e a l i ty": "Reality",
        "Re a l i ty": "Reality",
        "T h e": "The",
        "T h i s": "This",
        "W h e n": "When",
        "O n e": "One",
        "J a n u a r y": "January",
        "J u l y": "July",
        "M e V": "MeV",
    }
    for bad, good in spaced_word_fixes.items():
        text = re.sub(rf"\b{re.escape(bad)}\b", good, text)
    return compact(text)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_to_markdown(task: dict[str, Any]) -> Path:
    exact_markdown = str(task.get("source_exact_markdown") or "").strip()
    if exact_markdown:
        exact_path = ROOT / exact_markdown
        exact_status = str(task.get("source_exact_status") or "").strip()
        if exact_status:
            status_path = ROOT / exact_status
            if not status_path.exists():
                raise RuntimeError(
                    f"{task['book_id']} exact conversion status is missing: {status_path}"
                )
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("status") != "complete":
                raise RuntimeError(
                    f"{task['book_id']} exact conversion is not complete: "
                    f"{status.get('status', 'unknown')} {status.get('reason', '')}".strip()
                )
        if not exact_path.exists():
            raise FileNotFoundError(exact_path)
        return exact_path

    source = ROOT / task["source_path"]
    if not source.exists():
        raise FileNotFoundError(source)
    spine_lang = source_spine_lang(task)
    title = source_title(task)
    out = ROOT / "books" / task["book_id"] / f"work/source-extraction/{spine_lang}.raw.md"
    if out.exists() and not task.get("force_extract", False):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        cmd = [
            "python",
            "scripts/interlinear/pdf_text_or_ocr.py",
            task["source_path"],
            "--output",
            str(out.relative_to(ROOT)),
            "--title",
            title,
            "--min-content-chars",
            str(task.get("min_content_chars", 5000)),
            "--ocr-lang",
            str(task.get("ocr_lang", "eng")),
            "--ocr-psm",
            str(task.get("ocr_psm", 4)),
            "--ocr-dpi",
            str(task.get("ocr_dpi", 220)),
            "--ocr-workers",
            str(task.get("ocr_workers", 8)),
            "--ocr-pages",
            str(task.get("ocr_pages", "all")),
            "--ocr-crop",
            "--ocr-threshold",
        ]
        if task.get("force_ocr", False):
            cmd.append("--force-ocr")
        subprocess.check_call(cmd, cwd=ROOT)
        return out
    if suffix in {".epub", ".mobi", ".azw3"}:
        try:
            text = run_text(["pandoc", str(source), "-t", "gfm", "--wrap=none"])
            method = "pandoc-gfm"
        except subprocess.CalledProcessError:
            if suffix != ".epub":
                raise
            text = epub_to_markdown_fallback(source)
            method = "epub-html-fallback"
    else:
        raise ValueError(f"unsupported source type for {source}")
    body = normalize_raw_text(text)
    min_content_chars = int(task.get("min_content_chars", 5000))
    if suffix == ".epub" and visible_content_chars(body) < min_content_chars:
        text = epub_to_markdown_fallback(source)
        body = normalize_raw_text(text)
        method = "epub-html-fallback-after-empty-pandoc"
    if visible_content_chars(body) < min_content_chars:
        raise RuntimeError(
            f"{task['book_id']} extracted only {visible_content_chars(body)} content characters; "
            f"expected at least {min_content_chars}"
        )
    out.write_text(
        "---\n"
        f"source_file: {source.name}\n"
        f"conversion: {method}\n"
        f"generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return out


def epub_spine_paths(source: Path) -> list[str]:
    with zipfile.ZipFile(source) as zf:
        names = set(zf.namelist())
        opf_path = ""
        if "META-INF/container.xml" in names:
            container = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
            match = re.search(r'full-path=["\']([^"\']+)["\']', container)
            if match:
                opf_path = match.group(1)
        if opf_path and opf_path in names:
            opf = zf.read(opf_path).decode("utf-8", errors="replace")
            soup = BeautifulSoup(opf, "xml")
            base = posixpath.dirname(opf_path)
            manifest = {
                item.get("id"): item.get("href")
                for item in soup.find_all("item")
                if item.get("id") and item.get("href")
            }
            paths: list[str] = []
            for itemref in soup.find_all("itemref"):
                href = manifest.get(itemref.get("idref"))
                if not href:
                    continue
                path = posixpath.normpath(posixpath.join(base, href))
                if path in names and path.lower().endswith((".xhtml", ".html", ".htm")):
                    paths.append(path)
            if paths:
                return paths
        return sorted(
            name for name in names
            if name.lower().endswith((".xhtml", ".html", ".htm")) and not name.lower().endswith("nav.xhtml")
        )


def epub_to_markdown_fallback(source: Path) -> str:
    blocks: list[str] = []
    last = ""
    with zipfile.ZipFile(source) as zf:
        for name in epub_spine_paths(source):
            soup = BeautifulSoup(zf.read(name).decode("utf-8", errors="replace"), "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            body = soup.body or soup
            for node in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
                text = compact(node.get_text(" ", strip=True))
                if not text or text == last:
                    continue
                if node.name and node.name.startswith("h"):
                    level = min(int(node.name[1]), 6)
                    block = f"{'#' * level} {text}"
                elif node.name == "li":
                    block = f"- {text}"
                elif node.name == "blockquote":
                    block = f"> {text}"
                else:
                    block = text
                blocks.append(block)
                last = text
    if not blocks:
        raise RuntimeError(f"fallback EPUB extractor found no text in {source}")
    return "\n\n".join(blocks)


def normalize_raw_text(text: str) -> str:
    lines: list[str] = []
    in_yaml = False
    for raw in text.replace("\f", "\n\n").splitlines():
        line = html.unescape(raw)
        line = LINK_RE.sub(r"\1", line)
        line = TAG_RE.sub("", line)
        line = compact(line)
        if line == "---":
            in_yaml = not in_yaml
            continue
        if in_yaml or not line:
            lines.append("")
            continue
        if line.startswith("![]("):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_markdown_line(line: str) -> str:
    """Keep heading structure while removing extraction-only inline markup."""

    literal_asterisk = "POCKETPOLYGLOT_LITERAL_ASTERISK"
    match = re.match(r"^(?P<prefix>\s*#{1,6}\s+)(?P<body>.*)$", line)
    prefix = match.group("prefix") if match else ""
    body = match.group("body") if match else line
    body = html.unescape(body)
    body = LINK_RE.sub(r"\1", body)
    body = TAG_RE.sub("", body)
    body = body.replace(r"\*", literal_asterisk)
    body = body.replace("**", "").replace("__", "").replace("`", "")
    body = re.sub(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", body)
    # Marker escapes literal note marks as ``\*``. Keep the visible marker,
    # but discard the Markdown-only escape character.
    body = body.replace(literal_asterisk, "*")
    body = body.replace(r"\(", "(").replace(r"\)", ")")
    spaced_roman = re.fullmatch(
        r"((?:Part|Book|Chapter)\s+)([IVXLCDM]+(?:\s+[IVXLCDM]+)+)",
        body,
        re.I,
    )
    if spaced_roman:
        body = spaced_roman.group(1) + re.sub(r"\s+", "", spaced_roman.group(2))
    return prefix + compact(body)


def matches_configured_heading(line: str, task: dict[str, Any] | None) -> bool:
    if not task:
        return False
    line = re.sub(r"^#{1,6}\s+", "", line).strip()
    flags = 0 if task.get("chapter_heading_case_sensitive", False) else re.I
    for pattern in task.get("chapter_heading_exclude_patterns", []):
        if re.fullmatch(str(pattern), line, flags):
            return False
    return any(
        re.fullmatch(str(pattern), line, flags)
        for pattern in task.get("chapter_heading_patterns", [])
    )


def clean_line(
    line: str,
    title: str,
    lang: str = "en",
    task: dict[str, Any] | None = None,
) -> str:
    if task:
        replacements = task.get("source_line_replacements", {})
        compact_source = compact(line)
        if compact_source in replacements:
            line = str(replacements[compact_source])
    line = clean_markdown_line(line.replace("\u00ad", ""))
    if not line or PAGE_NUMBER_RE.fullmatch(line) or RUNNING_HEADER_RE.fullmatch(line):
        return ""
    if line.startswith("Syntax Warning"):
        return ""
    terminal_candidate = re.sub(r"^#{1,6}\s+", "", line).strip().casefold()
    if terminal_candidate.startswith(
        (
            "about the author",
            "also by",
            "copyright",
            "manufactured in china",
            "get personalized book picks",
        )
    ):
        return line
    if line.casefold() in {"index", "glossary", "notes", "acknowledgments", "acknowledgements"}:
        return line
    if LETTER_SPACED_HEADER_RE.fullmatch(line) or is_probable_spaced_header(line):
        return ""
    if is_symbol_noise(line):
        return ""
    if OCR_METADATA_RE.match(line) or OCR_PAGE_RE.match(line):
        return ""
    if (
        PAGE_ARTIFACT_RE.fullmatch(line)
        and not HEADING_RE.fullmatch(line)
        and not matches_configured_heading(line, task)
    ):
        return ""
    if BOILERPLATE_RE.search(line):
        return ""
    if line.casefold() == title.casefold():
        return ""
    if len(line) <= 3 and not has_language_content(line, lang):
        return ""
    # Drop isolated running headers but keep useful all-caps chapter headings.
    if (
        lang == "en"
        and re.fullmatch(r"[A-Z][A-Z .,'&:-]{3,70}", line)
        and not HEADING_RE.match(line)
        and not matches_configured_heading(line, task)
    ):
        words = [w for w in re.split(r"\W+", line) if w]
        if 1 <= len(words) <= 5:
            return ""
    return repair_embedded_text_artifacts(line)


def is_probable_spaced_header(line: str) -> bool:
    if len(line) > 90 or any(ch in line for ch in ".?!,;:()[]"):
        return False
    single_letters = re.findall(r"\b[A-Za-z]\b", line)
    letters = re.findall(r"[A-Za-z]", line)
    return len(single_letters) >= 4 and len(single_letters) / max(len(letters), 1) >= 0.45


def is_symbol_noise(line: str) -> bool:
    if len(line) < 60:
        return False
    symbol_count = sum(1 for ch in line if not ch.isalnum() and not ch.isspace() and ch not in ".,;:!?()[]'\"-/–—")
    ascii_word_count = len(re.findall(r"[A-Za-z]{3,}", line))
    return symbol_count >= 12 and ascii_word_count <= 12


def is_heading_line(line: str, task: dict[str, Any]) -> bool:
    lang = source_spine_lang(task)
    has_markdown_heading = line.lstrip().startswith("#")
    line = re.sub(r"^#{1,6}\s+", "", line).strip()
    if len(line) > 100:
        return False
    flags = 0 if task.get("chapter_heading_case_sensitive", False) else re.I
    for pattern in task.get("chapter_heading_exclude_patterns", []):
        if re.fullmatch(str(pattern), line, flags):
            return False
    configured_patterns = task.get("chapter_heading_patterns", [])
    for pattern in configured_patterns:
        if re.fullmatch(str(pattern), line, flags):
            return True
    if configured_patterns and task.get("chapter_heading_mode") == "configured_only":
        return False
    if SPECIAL_HEADING_RE.fullmatch(line):
        return True
    if CHAPTER_HEADING_RE.fullmatch(line):
        # Body prose often says "Chapter 7 (and as we'll see...)"; avoid
        # turning those references into fake chapters.
        if "(" in line or re.match(r"^Chapter\s+\d+\.", line, re.I):
            return False
        if not has_markdown_heading and line.casefold().startswith("chapter ") and len(line.split()) > 4 and ":" not in line:
            return False
        return True
    if lang != "en" and task.get("allow_cjk_numbered_headings", False) and CJK_HEADING_RE.fullmatch(line):
        return True
    if task.get("allow_numeric_headings", False) and NUMERIC_HEADING_RE.fullmatch(line):
        if re.match(r"^\d{1,3}\.\s*\d", line):
            return False
        return True
    if (
        has_markdown_heading
        and task.get("allow_markdown_headings", False)
        and 2 <= len(line) <= 100
        and has_language_content(line, lang)
    ):
        return True
    return False


def canonical_chapter_title(line: str, task: dict[str, Any]) -> str:
    title = re.sub(r"^#{1,6}\s+", "", line).strip()
    title_map = task.get("chapter_title_map", {})
    if title in title_map:
        return str(title_map[title])
    folded = title.casefold()
    for source, replacement in title_map.items():
        if str(source).casefold() == folded:
            return str(replacement)
    return title


def promote_task_markdown_heading(raw_line: str, task: dict[str, Any]) -> str:
    """Promote source-proven bold-only EPUB chapter titles when configured."""

    if not task.get("bold_lines_as_headings", False):
        return raw_line
    match = re.fullmatch(r"\s*\*\*(?P<title>[^*\n]+)\*\*\s*", raw_line)
    if not match:
        return raw_line
    title = compact(match.group("title"))
    patterns = task.get("bold_heading_patterns", [])
    flags = 0 if task.get("chapter_heading_case_sensitive", False) else re.I
    if patterns and not any(re.fullmatch(str(pattern), title, flags) for pattern in patterns):
        return raw_line
    return f"## {title}"


def drop_repeated_page_headers(lines: list[str]) -> list[str]:
    """Drop running headers like `Roads to Reality 17`.

    They are not always page numbers alone, so they survive `clean_line()` and
    can be mistaken for section headings. We only remove bases that recur with
    page-number suffixes, which avoids deleting a real one-off heading.
    """

    base_counts: dict[str, int] = {}
    parsed: list[tuple[str, str] | None] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            parsed.append(None)
            continue
        match = re.match(r"^(.{4,70}?)\s+\d{1,4}$", line)
        if match and not SENTENCE_END_RE.search(match.group(1)):
            base = compact(match.group(1)).casefold()
            base_counts[base] = base_counts.get(base, 0) + 1
            parsed.append((base, line))
        else:
            parsed.append(None)

    out: list[str] = []
    for line, marker in zip(lines, parsed):
        if marker and base_counts.get(marker[0], 0) >= 2:
            out.append("")
        else:
            out.append(line)
    return out


def join_proven_page_continuations(lines: list[str]) -> list[str]:
    """Join prose paragraphs split only by a source-page boundary.

    Marker occasionally emits the second half of a page-spanning paragraph as
    a new Markdown paragraph. A join is safe only when the preceding prose has
    no terminal punctuation and the continuation begins with a lowercase
    letter. Structural Markdown, figures, lists, tables, and quotes are never
    joined.
    """

    def structural(line: str) -> bool:
        stripped = line.lstrip()
        return (
            not stripped
            or stripped.startswith(("#", "|", ">", "```", "~~~"))
            or re.match(r"^(?:[-+*]|\d+[.)])\s+", stripped) is not None
            or stripped.startswith("POCKETPOLYGLOT_FIGURE_ANCHOR_")
        )

    def can_join(previous: str, following: str) -> bool:
        if structural(previous) or structural(following):
            return False
        if len(previous) < 24 or len(following) < 8:
            return False
        if SENTENCE_END_RE.search(previous):
            return False
        first_letter = next((char for char in following if char.isalpha()), "")
        return bool(first_letter and first_letter.islower())

    joined: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line or not joined:
            joined.append(line)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(lines) and not lines[next_index]:
            next_index += 1
        if (
            joined
            and next_index < len(lines)
            and can_join(joined[-1], lines[next_index])
        ):
            joined[-1] = compact(f"{joined[-1]} {lines[next_index]}")
            index = next_index + 1
            continue

        joined.append(line)
        index += 1
    return joined


def find_start(lines: list[str], task: dict[str, Any]) -> int:
    marker = str(task.get("start_marker") or "").strip()
    if marker:
        needle = compact(marker).casefold()
        exact = bool(task.get("start_marker_exact", False))
        occurrence = max(1, int(task.get("start_marker_occurrence") or 1))
        seen = 0
        for index, line in enumerate(lines):
            candidate = re.sub(r"^#{1,6}\s+", "", compact(line)).strip().casefold()
            matched = candidate == needle if exact else needle in candidate
            if matched:
                seen += 1
                if seen == occurrence:
                    return index
        raise ValueError(
            f"start marker not found: {marker!r} "
            f"(occurrence={occurrence}, exact={exact})"
        )
    body_markers = task.get(
        "body_start_markers",
        [
            "Introduction",
            "INTRODUCTION",
            "Foreword",
            "FOREWORD",
            "Prologue",
            "PROLOGUE",
            "Preface",
            "PREFACE",
            "Chapter 1",
            "CHAPTER 1",
            "Chapter One",
            "CHAPTER ONE",
            "Part I",
            "PART I",
            "Book I",
            "BOOK I",
        ],
    )
    front_matter_last = 0
    for index, line in enumerate(lines[:700]):
        normalized = re.sub(r"^#{1,6}\s+", "", compact(line)).strip()
        lower = normalized.casefold()
        if (
            lower in {"contents", "illustrations", "figures", "maps", "plates", "timeline", "chronology", "dramatis personae"}
            or lower.endswith(" contents")
            or lower.endswith(" illustrations")
            or lower.startswith(("list of illustrations", "list of figures", "list of maps", "list of plates"))
            or lower in {"cover", "title page", "dedication", "copyright", "about the author", "about the publisher"}
            or re.fullmatch(r"(?:notes|endnotes|index|acknowledg(?:e)?ments|appendix [a-z]).*", lower)
            or ("about the author" in lower and len(lower) <= 120)
        ):
            front_matter_last = index
    for index, line in enumerate(lines):
        if index < max(10, front_matter_last + 1):
            continue
        normalized = re.sub(r"^#{1,6}\s+", "", compact(line)).strip()
        if not normalized:
            continue
        for body_marker in body_markers:
            body_marker = str(body_marker)
            if normalized == body_marker:
                return index
            if normalized.startswith(body_marker + " "):
                tail = normalized[len(body_marker) :].strip()
                if re.fullmatch(r"(?:[ivxlcdm]{1,10}|\d{1,4})", tail, re.I):
                    continue
                return index
    for index, line in enumerate(lines):
        if HEADING_RE.match(line) or (len(line) > 80 and LATIN_RE.search(line)):
            return index
    return 0


def should_stop(line: str, task: dict[str, Any]) -> bool:
    normalized = re.sub(r"^#{1,6}\s+", "", compact(line)).strip()
    lower = normalized.casefold()
    for marker in task.get("stop_markers", []):
        wanted = compact(str(marker)).casefold()
        if not wanted:
            continue
        if lower == wanted:
            return True
        if re.fullmatch(rf"{re.escape(wanted)}\s+\d{{1,4}}", lower):
            return True
        if wanted == "index" and lower.startswith(wanted + " "):
            return True
        if wanted in {"notes", "glossary", "index"} and re.fullmatch(rf"(?:\d+\s*)?{re.escape(wanted)}(?:\s+to\s+pages?.*)?", lower):
            return True
        if wanted in {"glossary", "index"} and re.fullmatch(rf"\d+(?:\s+\d+)?\s+{re.escape(wanted)}", lower):
            return True
        if wanted == "notes" and re.fullmatch(r"notes(?:\s+\d{1,4})?", lower):
            return True
        # Short stop markers such as "Index" or "Notes" are common ordinary
        # words in nonfiction body text. Treat prefixes as terminal only for
        # explicit longer phrases like "About the Author".
        if len(wanted) >= 12 and lower.startswith(wanted):
            return True
    return False


def split_terminal_back_matter(line: str) -> tuple[str, bool]:
    """Trim terminal back matter when OCR joins it to the final body paragraph."""

    normalized = re.sub(r"^#{1,6}\s+", "", line).strip()
    if re.fullmatch(r"notes\s*:\s*", normalized, re.I):
        return line, False
    if TERMINAL_BACK_MATTER_RE.match(" " + normalized):
        return "", True
    match = TERMINAL_BACK_MATTER_RE.search(line)
    if not match:
        return line, False
    return compact(line[: match.start()]), True


def is_notes_heading(line: str) -> bool:
    normalized = re.sub(r"^#{1,6}\s+", "", compact(line)).strip().casefold()
    return normalized in {"notes", "endnotes"} or re.fullmatch(r"notes\s+\d{1,4}", normalized) is not None


def has_later_chapter_heading(lines: list[str], start_index: int, task: dict[str, Any], *, window: int = 120) -> bool:
    for later in lines[start_index + 1 : start_index + 1 + window]:
        if is_heading_line(later, task):
            return True
    return False


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
        if pending and len(pending) + 1 + len(piece) > max_chars:
            out.append(pending)
            pending = piece
        else:
            pending = f"{pending} {piece}".strip() if pending else piece
    if pending:
        out.append(pending)
    return out


def split_cjk_units(text: str, *, max_chars: int) -> list[str]:
    sentence_ends = set("。！？!?；;")
    closers = set("」』”’）)]】〉》")
    pieces: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in sentence_ends:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in closers:
            end += 1
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
        index = end
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
            pending += piece
    if pending:
        out.append(pending)
    return out


def split_source_units(text: str, lang: str, *, max_chars: int) -> list[str]:
    return split_english_units(text, max_chars=max_chars) if lang == "en" else split_cjk_units(text, max_chars=max_chars)


def markdown_figure_from_parts(
    caption: str,
    raw_path: str,
    markdown: Path,
) -> dict[str, Any]:
    raw_path = raw_path.strip().strip("<>")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw_path):
        path = raw_path
    else:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (markdown.parent / candidate).resolve()
        try:
            path = str(candidate.relative_to(ROOT))
        except ValueError:
            path = str(candidate)
    page_match = MARKER_PAGE_RE.search(path)
    figure: dict[str, Any] = {
        "path": path,
        "caption": compact(caption),
        "source_order": 0,
    }
    if page_match:
        figure["source_page_index"] = int(page_match.group("page"))
    return figure


def markdown_figure(raw_line: str, markdown: Path) -> dict[str, Any] | None:
    match = MARKDOWN_IMAGE_LINE_RE.fullmatch(raw_line.strip())
    if not match:
        return None
    return markdown_figure_from_parts(
        match.group("caption"),
        match.group("path"),
        markdown,
    )


def split_markdown_line_figures(
    raw_line: str,
    markdown: Path,
) -> list[str | dict[str, Any]]:
    """Return every ordered image anchor plus any surrounding source text."""

    parts: list[str | dict[str, Any]] = []
    cursor = 0
    for match in MARKDOWN_IMAGE_RE.finditer(raw_line):
        prefix = raw_line[cursor : match.start()].strip()
        if prefix:
            parts.append(prefix)
        parts.append(
            markdown_figure_from_parts(
                match.group("caption"),
                match.group("path"),
                markdown,
            )
        )
        cursor = match.end()
    suffix = raw_line[cursor:].strip()
    if suffix:
        parts.append(suffix)
    return parts or [raw_line]


def parse_chapters(markdown: Path, task: dict[str, Any], *, max_unit_chars: int) -> list[dict[str, Any]]:
    spine_lang = source_spine_lang(task)
    title = source_title(task)
    raw_lines = markdown.read_text(encoding="utf-8", errors="replace").splitlines()
    figure_tokens: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    for raw_line in raw_lines:
        raw_line = promote_task_markdown_heading(raw_line, task)
        for part in split_markdown_line_figures(raw_line, markdown):
            if isinstance(part, str):
                lines.append(clean_line(part, title, spine_lang, task))
                continue
            token = f"POCKETPOLYGLOT_FIGURE_ANCHOR_{len(figure_tokens) + 1:06d}"
            part["source_order"] = len(figure_tokens) + 1
            figure_tokens[token] = part
            lines.append(token)
    lines = drop_repeated_page_headers(lines)
    start_index = find_start(lines, task)
    preserved_front_figures = []
    if task.get("preserve_front_matter_figures", False):
        preserved_front_figures = [
            figure_tokens[line]
            for line in lines[:start_index]
            if line in figure_tokens
        ]
    lines = lines[start_index:]
    if task.get("join_page_continuations", True):
        lines = join_proven_page_continuations(lines)
    chapters: list[dict[str, Any]] = []
    default_titles = {"en": "Main Text", "ja": "本文", "zh": "正文"}
    current = {
        "number": 1,
        "title": str(task.get("default_chapter_title") or default_titles[spine_lang]),
        "paragraphs": [],
    }
    buffer: list[str] = []
    pending_figures: list[dict[str, Any]] = list(preserved_front_figures)
    body_chars_seen = 0
    min_body_chars_before_terminal = int(task.get("min_body_chars_before_terminal", 20000))
    skipping_intermediate_notes = False

    def flush() -> None:
        nonlocal buffer, pending_figures
        if not buffer:
            return
        text = repair_embedded_text_artifacts(" ".join(buffer))
        buffer = []
        min_paragraph_chars = int(
            task.get("min_paragraph_chars", 20 if spine_lang == "en" else 4)
        )
        if len(text) >= min_paragraph_chars and has_language_content(text, spine_lang):
            for unit in split_source_units(text, spine_lang, max_chars=max_unit_chars):
                paragraph: dict[str, Any] = {"text": unit}
                if pending_figures:
                    paragraph["figures"] = pending_figures
                    pending_figures = []
                current["paragraphs"].append(paragraph)

    for line_index, line in enumerate(lines):
        if line in figure_tokens:
            flush()
            figure = figure_tokens[line]
            if current["paragraphs"]:
                current["paragraphs"][-1].setdefault("figures", []).append(figure)
            else:
                pending_figures.append(figure)
            continue
        if skipping_intermediate_notes:
            if is_heading_line(line, task):
                skipping_intermediate_notes = False
            else:
                continue
        if (
            body_chars_seen >= min_body_chars_before_terminal
            and is_notes_heading(line)
            and has_later_chapter_heading(lines, line_index, task)
        ):
            flush()
            skipping_intermediate_notes = True
            continue
        if (
            body_chars_seen >= min_body_chars_before_terminal
            and "copyright" in compact(line).casefold()
            and has_later_chapter_heading(lines, line_index, task)
        ):
            flush()
            continue
        if (
            task.get("split_terminal_back_matter", True)
            and
            body_chars_seen >= min_body_chars_before_terminal
            and has_later_chapter_heading(lines, line_index, task)
            and TERMINAL_BACK_MATTER_RE.search(line)
            and not should_stop(line, task)
        ):
            terminal_after_line = False
        elif (
            task.get("split_terminal_back_matter", True)
            and body_chars_seen >= min_body_chars_before_terminal
        ):
            line, terminal_after_line = split_terminal_back_matter(line)
        else:
            terminal_after_line = False
        if body_chars_seen >= min_body_chars_before_terminal and should_stop(line, task):
            flush()
            break
        if not line:
            flush()
            if terminal_after_line:
                break
            continue
        heading = is_heading_line(line, task)
        if heading:
            flush()
            if current["paragraphs"]:
                chapters.append(current)
            current = {
                "number": len(chapters) + 1,
                "title": canonical_chapter_title(line, task),
                "paragraphs": [],
            }
            continue
        if spine_lang == "en" and buffer and buffer[-1].endswith("-") and line and line[0].islower():
            buffer[-1] = buffer[-1][:-1] + line
        else:
            buffer.append(line)
            body_chars_seen += len(line) + 1
        if terminal_after_line:
            flush()
            break
        sentence_ended = SENTENCE_END_RE.search(line) if spine_lang == "en" else CJK_SENTENCE_END_RE.search(line)
        if sentence_ended and len(" ".join(buffer)) >= max_unit_chars:
            flush()
    flush()
    if pending_figures and current["paragraphs"]:
        current["paragraphs"][-1].setdefault("figures", []).extend(pending_figures)
        pending_figures = []
    if current["paragraphs"]:
        chapters.append(current)
    if not chapters:
        raise RuntimeError(f"no usable paragraphs parsed for {task['book_id']}")
    return chapters


def build_chunks(task: dict[str, Any], chapters: list[dict[str, Any]], *, max_chunk_chars: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spine_lang = source_spine_lang(task)
    chunks: list[dict[str, Any]] = []
    paragraph_index = 0
    supplemental_sources = task.get("reference_paths", {})
    translation_contract = dict(task.get(
        "translation_contract",
        {
            "style": "Accurate, complete, modern, understandable, elegant nonfiction translation.",
            "alignment": "Translate each source unit faithfully; do not summarize, skip, merge unrelated units, or add unsupported facts.",
            "japanese": "Use natural modern Japanese with kana and clear technical terms; never output Chinese prose in the Japanese field.",
            "chinese": "Use natural modern Chinese with precise terminology; preserve names, dates, causal claims, and distinctions.",
            "grammar": "Grammar-role analysis is required later in the pipeline; keep sentence structure clear enough for subject/predicate/object/topic/function tagging.",
        },
    ))
    if task.get("terminology"):
        translation_contract["terminology"] = task["terminology"]
    for chapter in chapters:
        pending: list[dict[str, str]] = []
        pending_chars = 0

        def flush() -> None:
            nonlocal pending, pending_chars
            if not pending:
                return
            index = len(chunks) + 1
            chunk_id = f"{task['book_id']}-c{index:04d}"
            source_ref = "\n".join(item[spine_lang] for item in pending)
            chunks.append(
                {
                    "schema_version": 1,
                    "mode": "trilingual_standard",
                    "book_id": task["book_id"],
                    "source_spine_lang": spine_lang,
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "chapter_id": f"chapter-{chapter['number']:03d}",
                    "chapter_number": chapter["number"],
                    "chapter_title_en": chapter["title"] if spine_lang == "en" else f"Chapter {chapter['number']}",
                    "chapter_title_zh": chapter["title"] if spine_lang == "zh" else "",
                    "chapter_title_ja": chapter["title"] if spine_lang == "ja" else "",
                    "chapter_part_en": "",
                    "paragraph_ids": [item["id"] for item in pending],
                    "paragraphs": pending,
                    "reference": {
                        "english": {
                            "available": spine_lang == "en",
                            "chapter": chapter["title"] if spine_lang == "en" else "",
                            "text": source_ref if spine_lang == "en" else "",
                            "quality": "source_spine" if spine_lang == "en" else f"generate_from_{spine_lang}_spine",
                        },
                        "zh_primary": {
                            "available": spine_lang == "zh",
                            "chapter": chapter["title"] if spine_lang == "zh" else "",
                            "text": source_ref if spine_lang == "zh" else "",
                            "quality": "source_spine" if spine_lang == "zh" else f"generate_from_{spine_lang}_spine",
                        },
                        "zh_secondary": {"available": False, "chapter": "", "text": ""},
                        "ja": {
                            "available": spine_lang == "ja",
                            "chapter": chapter["title"] if spine_lang == "ja" else "",
                            "text": source_ref if spine_lang == "ja" else "",
                            "quality": "source_spine" if spine_lang == "ja" else f"generate_from_{spine_lang}_spine",
                        },
                        "supplemental_sources": supplemental_sources,
                        "reference_notes": task.get("reference_notes", ""),
                    },
                    "translation_contract": translation_contract,
                }
            )
            pending = []
            pending_chars = 0

        for paragraph_entry in chapter["paragraphs"]:
            if isinstance(paragraph_entry, dict):
                paragraph = str(paragraph_entry.get("text") or "")
                figures = list(paragraph_entry.get("figures") or [])
            else:
                paragraph = str(paragraph_entry)
                figures = []
            paragraph_index += 1
            paragraph_id = f"{task['book_id']}-s{chapter['number']:03d}-p{paragraph_index:05d}"
            if pending and pending_chars + len(paragraph) > max_chunk_chars:
                flush()
            prepared_paragraph: dict[str, Any] = {"id": paragraph_id, spine_lang: paragraph}
            if figures:
                prepared_paragraph["figures"] = figures
                prepared_paragraph["source_pages"] = sorted(
                    {
                        int(figure["source_page_index"])
                        for figure in figures
                        if "source_page_index" in figure
                    }
                )
            pending.append(prepared_paragraph)
            pending_chars += len(paragraph) + 1
        flush()

    source_path = ROOT / task["source_path"]
    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": task["book_id"],
        "book_title_en": task["title_en"],
        "book_title_zh": task["title_zh"],
        "book_title_ja": task["title_ja"],
        "book_title_zh_reading": task.get("title_zh_reading", ""),
        "book_title_ja_reading": task.get("title_ja_reading", ""),
        "author": task.get("author", ""),
        "author_reading_zh": task.get("author_reading_zh", ""),
        "author_reading_ja": task.get("author_reading_ja", ""),
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": spine_lang,
        "source_paths": {spine_lang: task["source_path"]},
        "source_reference_paths": supplemental_sources,
        "source_sha256": {spine_lang: sha256(source_path)},
        "source_note": task.get("description", ""),
        "reference_notes": task.get("reference_notes", ""),
        "figure_count": sum(
            len(paragraph.get("figures") or [])
            for chunk in chunks
            for paragraph in chunk.get("paragraphs", [])
        ),
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


def write_book(task: dict[str, Any], queue: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    spine_lang = source_spine_lang(task)
    raw_md = source_to_markdown(task)
    chapters = parse_chapters(raw_md, task, max_unit_chars=args.max_unit_chars)
    book_root = ROOT / "books" / task["book_id"]
    markdown_path = book_root / f"markdown/{spine_lang}.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_out = [f"# {source_title(task)}", ""]
    for chapter in chapters:
        markdown_out.extend([f"## {chapter['title']}", ""])
        for paragraph_entry in chapter["paragraphs"]:
            if isinstance(paragraph_entry, dict):
                markdown_out.append(str(paragraph_entry.get("text") or ""))
                for figure in paragraph_entry.get("figures") or []:
                    markdown_out.append(
                        f"![{figure.get('caption', '')}]({figure.get('path', '')})"
                    )
            else:
                markdown_out.append(str(paragraph_entry))
        markdown_out.append("")
    markdown_path.write_text("\n".join(markdown_out).strip() + "\n", encoding="utf-8")

    manifest, chunks = build_chunks(task, chapters, max_chunk_chars=args.max_chunk_chars)
    min_chunks = int(task.get("min_chunk_count", 1))
    if len(chunks) < min_chunks:
        raise RuntimeError(
            f"{task['book_id']} parsed only {len(chunks)} chunks; "
            f"expected at least {min_chunks}. Check start/stop markers and source extraction."
        )
    chunks_dir = book_root / "work/trilingual/chunks"
    raw_chunk_dir = book_root / "work/trilingual/interlinear/chunks"
    preview_dir = book_root / "work/trilingual/preview"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    raw_chunk_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    (chunks_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    write_json(chunks_dir / "manifest.json", manifest)
    figures = [
        {
            "chunk_id": chunk["chunk_id"],
            "paragraph_id": paragraph["id"],
            **figure,
        }
        for chunk in chunks
        for paragraph in chunk.get("paragraphs", [])
        for figure in paragraph.get("figures") or []
    ]
    figure_manifest_path = book_root / "work/trilingual/assets/figure-manifest.json"
    write_json(
        figure_manifest_path,
        {
            "schema_version": 1,
            "book_id": task["book_id"],
            "source_exact_markdown": task.get("source_exact_markdown", ""),
            "figure_count": len(figures),
            "figures": figures,
        },
    )
    plan = {
        "schema_version": 1,
        "book_id": task["book_id"],
        "status": "prepared_trilingual",
        "launchable": True,
        "task_mode": task.get("task_mode", "trilingual_modern_nonfiction_en_source_generated_zh_ja"),
        "source_spine_lang": spine_lang,
        "source_paths": manifest["source_paths"],
        "source_reference_paths": manifest["source_reference_paths"],
        "source_sha256": manifest["source_sha256"],
        "source_extraction": {
            "en_cache": str(raw_md.relative_to(ROOT)),
            "note": (
                "Illustrated nonfiction uses the validated exact Marker Markdown and preserves "
                "ordered figure anchors; ordinary PDF uses pdftotext and EPUB/MOBI uses pandoc."
                if task.get("source_exact_markdown")
                else "Modern nonfiction generic extraction. PDF uses pdftotext; EPUB/MOBI uses pandoc."
            ),
        },
        "markdown": {spine_lang: str(markdown_path.relative_to(ROOT))},
        "book_title_en": task["title_en"],
        "book_title_zh": task["title_zh"],
        "book_title_ja": task["title_ja"],
        "book_title_zh_reading": task.get("title_zh_reading", ""),
        "book_title_ja_reading": task.get("title_ja_reading", ""),
        "author": task.get("author", ""),
        "author_reading_zh": task.get("author_reading_zh", ""),
        "author_reading_ja": task.get("author_reading_ja", ""),
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "book_description": task.get("description", ""),
        "chunk_mode": "paragraph_sentence_group",
        "reference_scope": f"{spine_lang}_spine_with_declared_supplemental_references",
        "chunks_jsonl": str((chunks_dir / "chunks.jsonl").relative_to(ROOT)),
        "chunks_manifest": str((chunks_dir / "manifest.json").relative_to(ROOT)),
        "raw_chunk_dir": str(raw_chunk_dir.relative_to(ROOT)),
        "preview_json": str((preview_dir / f"{task['book_id']}.partial.json").relative_to(ROOT)),
        "assembled_json": str((preview_dir / f"{task['book_id']}.partial.json").relative_to(ROOT)),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "queue_id": queue.get("queue_id", ""),
        "queue_model": task.get("model", queue.get("model", "")),
        "queue_reasoning": task.get("reasoning", queue.get("reasoning", "")),
        "chunk_count": len(chunks),
        "figure_count": len(figures),
        "figure_manifest": str(figure_manifest_path.relative_to(ROOT)),
        "english_chapter_count": len(chapters),
        "preparation_notes": {
            "script": "scripts/interlinear/prepare_modern_nonfiction_trilingual.py",
            "source_spine": f"{spine_lang} source text is the immutable chunk spine.",
            "supplemental_sources": "Optional local references are recorded in source_reference_paths; they are not used as chunk spine text unless a later project-specific pass aligns them.",
            "chinese_reference": "Preserve a Chinese source spine exactly when configured; otherwise generate readable modern Chinese from the declared spine.",
            "japanese_reference": "Preserve a Japanese source spine exactly when configured; otherwise generate natural modern Japanese from the declared spine.",
            "reference_notes": task.get("reference_notes", ""),
        },
    }
    write_json(book_root / "book-plan.json", plan)
    return {
        "book_id": task["book_id"],
        "chunks": len(chunks),
        "chapters": len(chapters),
        "manifest": str((chunks_dir / "manifest.json").relative_to(ROOT)),
        "book_plan": str((book_root / "book-plan.json").relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, type=Path, help="queue JSON file")
    parser.add_argument("--book-id", action="append", help="prepare selected book id; repeatable")
    parser.add_argument("--max-chunk-chars", type=int, default=2600)
    parser.add_argument("--max-unit-chars", type=int, default=900)
    parser.add_argument("--update-queue", action="store_true", help="write prepared status and chunk counts back to queue JSON")
    args = parser.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else ROOT / args.queue
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    selected = set(args.book_id or [])
    summaries: list[dict[str, Any]] = []
    for task in queue.get("tasks", []):
        if selected and task["book_id"] not in selected:
            continue
        summary = write_book(task, queue, args)
        summaries.append(summary)
        print(
            f"prepared book_id={summary['book_id']} chunks={summary['chunks']} "
            f"chapters={summary['chapters']} manifest={summary['manifest']}",
            flush=True,
        )
    if not summaries:
        raise SystemExit("no tasks selected")
    if args.update_queue:
        by_id = {item["book_id"]: item for item in summaries}
        for task in queue.get("tasks", []):
            summary = by_id.get(task.get("book_id"))
            if not summary:
                continue
            task["status"] = "chunked_launchable"
            task["launchable"] = True
            task["book_plan"] = summary["book_plan"]
            task["chunks_manifest"] = summary["manifest"]
            task["chunk_count"] = summary["chunks"]
            task["english_chapter_count"] = summary["chapters"]
            task["prepared_chunks_at"] = datetime.now(timezone.utc).isoformat()
        task_statuses = [str(task.get("status") or "") for task in queue.get("tasks", [])]
        queue["status"] = (
            "chunked_launchable"
            if task_statuses and all(status == "chunked_launchable" for status in task_statuses)
            else "partially_chunked"
        )
        queue["last_chunk_preparation_at"] = datetime.now(timezone.utc).isoformat()
        write_json(queue_path, queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
