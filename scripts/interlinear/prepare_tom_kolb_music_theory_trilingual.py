#!/usr/bin/env python3
"""Prepare Tom Kolb music-theory guitar trilingual pocket-book tasks.

This source is an image-based PDF. The normal prose extractor would silently
lose fretboard diagrams, staff examples, chord grids, and exercise layouts, so
this preparer creates page-aware chunks with source page images attached as
required figure assets.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "tom-kolb-music-theory-guitarists"
SOURCE_PDF = (
    ROOT
    / "resources/curated-books/music-theory-and-guitar/recommended/tom-kolb/en/"
    / "Music Theory for Guitarists_ Everything You Ever Wanted to Know But Were Afraid to Ask.pdf"
)
BOOK_ROOT = ROOT / "books" / BOOK_ID
WORK_ROOT = BOOK_ROOT / "work/trilingual"
OCR_MD = WORK_ROOT / "ocr/source-pages.md"
PAGE_IMAGES = WORK_ROOT / "page-images"
CHUNKS_DIR = WORK_ROOT / "chunks"
RAW_CHUNK_DIR = WORK_ROOT / "interlinear/chunks"
PREVIEW_DIR = WORK_ROOT / "preview"
MARKDOWN_DIR = BOOK_ROOT / "markdown"
ASSET_DIR = WORK_ROOT / "assets"
FIGURE_MANIFEST = ASSET_DIR / "figure-manifest.json"
SPACE_RE = re.compile(r"[ \t\u00a0]+")
CONTENT_RE = re.compile(r"[A-Za-z0-9]")
FIGURE_RE = re.compile(r"\bF(?:ig|iq)[,.]?\s*([0-9§]+[A-Za-z]?)", re.I)
TRACK_RE = re.compile(r"^(?:TRACK|TRAX)\s+(\d+)\b", re.I)
PROSE_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")
COMMON_PROSE_WORDS = {
    "about",
    "above",
    "according",
    "again",
    "also",
    "another",
    "are",
    "because",
    "below",
    "called",
    "can",
    "chapter",
    "chord",
    "directly",
    "every",
    "example",
    "fret",
    "fretboard",
    "guitar",
    "harmonic",
    "harmony",
    "interval",
    "into",
    "measure",
    "music",
    "note",
    "notes",
    "octave",
    "open",
    "pitch",
    "played",
    "playing",
    "scale",
    "section",
    "string",
    "strings",
    "system",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "those",
    "through",
    "tuning",
    "used",
    "when",
    "where",
    "while",
    "with",
    "you",
    "your",
}

CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

CHAPTER_STARTS = [
    (3, "Front Matter", "About the Author, acknowledgments, introduction, and recording notes"),
    (5, "Chapter 1: The Fretboard", "Fretboard layout, repeated pitches, tuning, and harmonics"),
    (8, "Chapter 2: Theory Basics", "Music alphabet, notation basics, rhythm, and fundamental terms"),
    (16, "Chapter 3: Scales and Key Signatures", "Major scale construction and key signatures"),
    (24, "Chapter 4: Intervals", "Interval names, qualities, and fretboard applications"),
    (30, "Chapter 5: Triads", "Triad construction and major/minor/diminished/augmented forms"),
    (35, "Chapter 6: Harmonizing the Major Scale", "Diatonic triads and functional harmony"),
    (40, "Chapter 7: Chord Construction", "Seventh chords, extensions, alterations, and voicings"),
    (49, "Chapter 8: Harmonizing the Minor Scale", "Minor-key harmony and related scale forms"),
    (53, "Chapter 9: Determining Key Centers", "Key-center analysis and common progressions"),
    (61, "Chapter 10: Blues Harmony and Pentatonic Scales", "Blues form, pentatonic materials, and applications"),
    (67, "Chapter 11: Modes and Modal Harmony", "Modes, modal harmony, and guitar contexts"),
    (79, "Chapter 12: Other Scales and Modes", "Other scales, chord/scale relationships, and arpeggios"),
    (88, "Chapter 13: Chord Substitution and Reharmonization", "Substitution, reharmonization, and applied harmony"),
    (94, "Index and Answer Keys", "Index, quiz answers, ear-training answers, and notation legend"),
]

ZH_GLOSSARY = """Technical terminology reference:
fretboard=指板; fret=品; string=弦; open string=空弦; half step=半音; whole step=全音; octave=八度; interval=音程; perfect fourth=纯四度; major third=大三度; scale=音阶; chromatic scale=半音阶; major scale=大调音阶; minor scale=小调音阶; key signature=调号; triad=三和弦; chord=和弦; chord construction=和弦构成; harmonize=配和声; diatonic=自然音阶内的; mode=调式; modal harmony=调式和声; pentatonic scale=五声音阶; blues harmony=布鲁斯和声; arpeggio=琶音; chord substitution=和弦替代; reharmonization=重新配和声; rhythm=节奏; notation=记谱; staff=五线谱; tablature=六线谱; exercise=练习; ear training=听力训练.
Use concise, readable modern Chinese for study notes. Preserve chord names, note names, scale-degree numbers, fret numbers, and track numbers exactly."""

JA_GLOSSARY = """Technical terminology reference:
fretboard=指板; fret=フレット; string=弦; open string=開放弦; half step=半音; whole step=全音; octave=オクターブ; interval=音程; perfect fourth=完全4度; major third=長3度; scale=スケール/音階; chromatic scale=クロマチック・スケール; major scale=メジャー・スケール; minor scale=マイナー・スケール; key signature=調号; triad=三和音; chord=コード/和音; chord construction=コード構成; harmonize=ハーモナイズする; diatonic=ダイアトニック; mode=モード; modal harmony=モード・ハーモニー; pentatonic scale=ペンタトニック・スケール; blues harmony=ブルース・ハーモニー; arpeggio=アルペジオ; chord substitution=コード置換; reharmonization=リハーモナイゼーション; rhythm=リズム; notation=記譜; staff=五線譜; tablature=タブ譜; exercise=練習; ear training=イヤー・トレーニング.
Use clear common modern Japanese for study notes. Preserve chord names, note names, scale-degree numbers, fret numbers, and track numbers exactly."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def ensure_ocr(*, force: bool, workers: int, dpi: int) -> None:
    expected_last = PAGE_IMAGES / "page-0103.png"
    if OCR_MD.exists() and expected_last.exists() and not force:
        return
    OCR_MD.parent.mkdir(parents=True, exist_ok=True)
    PAGE_IMAGES.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "scripts/ocr/pdf_to_markdown.py",
        str(SOURCE_PDF),
        "--pages",
        "all",
        "--output",
        str(OCR_MD),
        "--lang",
        "eng",
        "--psm",
        "4",
        "--dpi",
        str(dpi),
        "--workers",
        str(workers),
        "--crop",
        "--threshold",
        "--keep-linebreaks",
        "--save-images-dir",
        str(PAGE_IMAGES),
        "--progress-every",
        "10",
    ]
    proc = run(cmd, check=False)
    (WORK_ROOT / "ocr/ocr-run.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout)


def normalize_line(line: str) -> str:
    line = line.replace("\u2014", "-").replace("\u00ad", "")
    line = line.replace("ftalf-step", "half-step").replace("trebd/e", "treble")
    line = line.replace("Aarmony", "harmony").replace("mare", "more")
    line = line.replace("aiphabet", "alphabet").replace("stalf", "staff")
    line = line.replace("bariine", "barline").replace("bartines", "barlines")
    line = line.replace("Untike", "Unlike").replace("apen", "open")
    line = re.sub(r"\bTRAX\b", "TRACK", line, flags=re.I)
    line = re.sub(r"\bF[i1]g[, ]", "Fig. ", line, flags=re.I)
    line = re.sub(r"\bFig[,.]?\s*§\b", "Fig. 5", line, flags=re.I)
    line = re.sub(r"\s+\d+\)\s+(Fig[,.])", r" \1", line, flags=re.I)
    line = SPACE_RE.sub(" ", line).strip()
    return line


def prose_words(line: str) -> list[str]:
    return PROSE_WORD_RE.findall(line)


def common_word_count(line: str) -> int:
    return sum(1 for word in prose_words(line) if word.lower() in COMMON_PROSE_WORDS)


def is_section_heading(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    if re.match(
        r"^(CHAPTER|INTRODUCTION|ABOUT THE|ACKNOWLEDGMENTS|Tuning|Intonation|MELODY|RHYTHM|Quiz|Ear Training|"
        r"Accidentals|Measures|Time Signatures|Note Values|SCALE FORMULAS|MINOR KEY SIGNATURES|INTERVAL|"
        r"Roman Numeral|INVERSIONS|AUGMENTED|DIMINISHED|OTHER SCALES|CHORD/SCALE|ARPEGGIOS)\b",
        line,
        re.I,
    ):
        return True
    words = prose_words(line)
    if not 2 <= len(words) <= 7:
        return False
    single_letters = len(re.findall(r"\b[A-Ga-g]\b", line))
    noteish = len(re.findall(r"\b[A-G](?:[#b]|[a-z]{0,2})?\b", line))
    symbol = len(re.findall(r"[^A-Za-z0-9\s]", line))
    if single_letters >= 2 or noteish >= 4 or symbol >= 3:
        return False
    if any(word.upper() == word and len(word) >= 3 for word in words):
        return False
    if line.upper() == line and len(words) > 1:
        return False
    if common_word_count(line) >= 2:
        return False
    titleish = sum(1 for word in words if word[:1].isupper())
    return titleish >= max(1, len(words) - 1)


def is_prose_line(line: str) -> bool:
    words = prose_words(line)
    if len(words) >= 9 and common_word_count(line) >= 1:
        return True
    if len(words) >= 6 and common_word_count(line) >= 2:
        return True
    if len(words) >= 5 and re.search(r"[.!?;:]$", line) and common_word_count(line) >= 1:
        return True
    return is_section_heading(line)


def normalize_figure_label(raw: str) -> str:
    label = raw.replace("§", "5")
    return f"Fig. {label}"


def figure_match(line: str) -> re.Match[str] | None:
    return FIGURE_RE.search(line)


def normalize_track_line(line: str) -> str | None:
    match = TRACK_RE.match(line)
    if not match:
        return None
    return f"TRACK {match.group(1)}"


def is_diagram_artifact(line: str) -> bool:
    if not line:
        return True
    if figure_match(line) or normalize_track_line(line):
        return False
    words = prose_words(line)
    common = common_word_count(line)
    single_letters = len(re.findall(r"\b[A-Ga-g]\b", line))
    noteish = len(re.findall(r"\b[A-G](?:[#b]|[lI][/\\]?[A-Gb#]|[a-z]{0,2})?\b", line))
    visible = len(re.sub(r"\s+", "", line))
    symbol = len(re.findall(r"[^A-Za-z0-9\s]", line))
    digit = len(re.findall(r"\d", line))
    if single_letters >= 6 and common == 0:
        return True
    if noteish >= 8 and len(words) < 6:
        return True
    if visible >= 20 and len(words) <= 3 and symbol + digit >= 6:
        return True
    if visible >= 10 and len(words) <= 3 and symbol >= 5:
        return True
    if visible >= 24 and common == 0 and symbol >= 5 and noteish >= 3:
        return True
    if re.search(r"(?:[_—=-]\s*){4,}", line):
        return True
    if re.search(r"(?:\b[a-zA-Z]\b[^\n]*){10,}", line) and common <= 1:
        return True
    if len(words) <= 2 and visible >= 18 and common == 0:
        return True
    if not words and visible <= 4:
        return True
    return False


def is_diagram_continuation_label(line: str) -> bool:
    return bool(
        re.search(r"\bTRACK\s+\d+\b", line, re.I)
        or re.match(r"^(Scale formula|Intervallic formula|First mode|Second mode|Third mode|Fourth mode|Fifth mode|Sixth mode|Seventh mode)\b", line, re.I)
        or re.match(r"^For Chord Types\b", line, re.I)
    )


def is_noise(line: str) -> bool:
    if not line:
        return True
    if re.fullmatch(r"[-_—=+~|.,;:<>/\\ ]{1,20}", line):
        return True
    if re.fullmatch(r"\d{1,3}", line):
        return True
    alpha = len(re.findall(r"[A-Za-z]", line))
    visible = len(re.sub(r"\s+", "", line))
    symbol = len(re.findall(r"[^A-Za-z0-9\\s]", line))
    note_grid = len(re.findall(r"\b[A-G](?:[#b])?\b", line))
    prose_words = len(re.findall(r"\b[A-Za-z]{3,}\b", line))
    if visible >= 24 and alpha < 8 and symbol + note_grid >= 8:
        return True
    if visible >= 40 and prose_words < 5 and note_grid >= 5:
        return True
    if visible >= 40 and prose_words < 3 and symbol >= 5:
        return True
    if visible >= 40 and alpha / max(visible, 1) < 0.28 and symbol >= 8:
        return True
    if re.search(r"(?:[_—=-]\s*){5,}", line):
        return True
    if is_diagram_artifact(line):
        return True
    if len(CONTENT_RE.findall(line)) < 2 and not re.search(r"[A-G](?:[#b])?", line):
        return True
    return False


def parse_ocr_pages() -> dict[int, str]:
    text = OCR_MD.read_text(encoding="utf-8", errors="replace")
    pages: dict[int, list[str]] = {}
    current: int | None = None
    in_diagram_block = False
    for raw in text.splitlines():
        match = re.match(r"^## Page (\d+)\s*$", raw)
        if match:
            current = int(match.group(1))
            pages[current] = []
            in_diagram_block = False
            continue
        if current is None or raw.startswith("---") or raw.startswith("# OCR:"):
            continue
        line = normalize_line(raw)
        track_line = normalize_track_line(line)
        fig = figure_match(line)
        if fig and (
            fig.start() <= 5
            or (is_prose_line(line[: fig.start()].strip(" .;:-")) and len(line[fig.end() :].strip()) <= 48)
        ):
            prefix = line[: fig.start()].strip(" .;:-")
            if prefix and is_prose_line(prefix):
                pages[current].append(prefix if re.search(r"[.!?;:]$", prefix) else prefix + ".")
            pages[current].append(normalize_figure_label(fig.group(1)))
            in_diagram_block = True
            continue
        if track_line:
            pages[current].append(track_line)
            in_diagram_block = True
            continue
        if in_diagram_block:
            if is_diagram_continuation_label(line):
                if pages[current] and pages[current][-1] != "":
                    pages[current].append("")
                continue
            if is_prose_line(line):
                in_diagram_block = False
            else:
                if pages[current] and pages[current][-1] != "":
                    pages[current].append("")
                continue
        if is_noise(line):
            if pages[current] and pages[current][-1] != "":
                pages[current].append("")
            continue
        pages[current].append(line)

    out: dict[int, str] = {}
    for page, lines in pages.items():
        paragraphs: list[str] = []
        pending: list[str] = []

        def flush() -> None:
            nonlocal pending
            if not pending:
                return
            paragraphs.append(" ".join(pending).strip())
            pending = []

        for line in lines:
            if not line:
                flush()
                continue
            if re.match(r"^(CHAPTER|Fig\\.|Figure|Quiz|Ear Training|TRACK|About the|Introduction|Tuning)", line, re.I):
                flush()
                paragraphs.append(line)
                continue
            pending.append(line)
        flush()
        out[page] = "\n\n".join(p for p in paragraphs if p).strip()
    return out


def chapter_for_page(page: int) -> tuple[int, str, str]:
    current = CHAPTER_STARTS[0]
    for item in CHAPTER_STARTS:
        if page >= item[0]:
            current = item
        else:
            break
    chapter_index = CHAPTER_STARTS.index(current) + 1
    return chapter_index, current[1], current[2]


def figure_for_page(page: int, chapter_title: str) -> dict[str, Any]:
    image = PAGE_IMAGES / f"page-{page:04d}.png"
    return {
        "kind": "source_page_image",
        "path": rel(image),
        "source_page": page,
        "caption": f"Source page {page}: {chapter_title}. Original page image retained for fretboards, notation, diagrams, tables, and exercises.",
        "required_for_publication": True,
    }


def build_chunks(pages: dict[int, str]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    for page in sorted(pages):
        if page < 3:
            continue
        text = pages[page]
        if not text:
            continue
        chapter_number, chapter_title, chapter_note = chapter_for_page(page)
        chunk_index = len(chunks) + 1
        chunk_id = f"{BOOK_ID}-c{chunk_index:04d}"
        figure = figure_for_page(page, chapter_title)
        figures.append({"chunk_id": chunk_id, **figure})
        paragraph_id = f"{BOOK_ID}-p{page:04d}"
        chunks.append(
            {
                "schema_version": 1,
                "mode": "trilingual_standard",
                "book_id": BOOK_ID,
                "source_spine_lang": "en",
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "chapter_id": f"chapter-{chapter_number:02d}",
                "chapter_number": chapter_number,
                "chapter_title_en": chapter_title,
                "chapter_title_zh": "",
                "chapter_title_ja": "",
                "chapter_part_en": f"source page {page}",
                "paragraph_ids": [paragraph_id],
                "paragraphs": [
                    {
                        "id": paragraph_id,
                        "en": text,
                        "source_pages": [page],
                        "figures": [figure],
                    }
                ],
                "reference": {
                    "english": {
                        "available": True,
                        "chapter": chapter_title,
                        "text": text,
                        "quality": "ocr_page_spine_review_against_image",
                    },
                    "zh_primary": {
                        "available": True,
                        "chapter": "music terminology glossary",
                        "text": ZH_GLOSSARY,
                        "quality": "terminology_reference",
                    },
                    "zh_secondary": {
                        "available": False,
                        "chapter": "",
                        "text": "",
                    },
                    "ja": {
                        "available": True,
                        "chapter": "music terminology glossary",
                        "text": JA_GLOSSARY,
                        "quality": "terminology_reference",
                    },
                },
                "technical_note": (
                    f"{chapter_note}. Preserve music symbols, note names, chord symbols, fret numbers, "
                    "scale-degree numbers, track references, quiz/exercise labels, and figure references. "
                    "Use the attached source page image as visual evidence for diagrams; do not paraphrase "
                    "or omit fretboard, staff, tablature, rhythm, chord-grid, or table information."
                ),
            }
        )

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "book_title_en": "Music Theory for Guitarists",
        "book_title_zh": "吉他手音乐理论",
        "book_title_ja": "ギタリストのための音楽理論",
        "book_title_zh_reading": "jí tā shǒu yīn yuè lǐ lùn",
        "book_title_ja_reading": "ギタリスト の ため の おんがく りろん",
        "author": "Tom Kolb",
        "author_reading_zh": "tāng mǔ kē ěr bù",
        "author_reading_ja": "トム コルブ",
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": "en",
        "source_paths": {
            "en_primary": rel(SOURCE_PDF),
            "ocr_markdown": rel(OCR_MD),
            "page_images": rel(PAGE_IMAGES),
            "zh_music_theory_reference": "resources/curated-books/music-theory-and-guitar/zh/music-theory/音乐分析法 (Analyse lernen).pdf",
            "zh_guitar_reference": "resources/curated-books/music-theory-and-guitar/zh/guitar/电吉他自学完整教程.pdf",
            "ja_music_theory_reference": "resources/curated-books/music-theory-and-guitar/ja/music-theory/楽典 音楽の基礎から和声へ.pdf",
            "ja_guitar_chord_reference": "resources/curated-books/music-theory-and-guitar/ja/music-theory/コード編曲法 ~藤巻メソッド~ Chord Arrange -FUJIMAKI Method-.pdf",
        },
        "source_sha256": {"en_primary": sha256(SOURCE_PDF)},
        "source_note": (
            "Image-based music-theory PDF prepared as private EN-JP-ZH study task. "
            "OCR text is the English alignment spine, and original page images are attached as required figure assets."
        ),
        "chunk_count": len(chunks),
        "figure_count": len(figures),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
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
    return manifest, chunks, figures


def update_plan(manifest: dict[str, Any]) -> None:
    plan_path = BOOK_ROOT / "book-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
    plan.update(
        {
            "schema_version": 1,
            "book_id": BOOK_ID,
            "status": "prepared_trilingual",
            "launchable": True,
            "task_mode": "trilingual_music_theory_private_study_notes_en_spine_zh_ja_with_figures",
            "legal_mode": "private_study_notes_with_source_page_figure_evidence",
            "source_spine_lang": "en",
            "book_title_en": manifest["book_title_en"],
            "book_title_zh": manifest["book_title_zh"],
            "book_title_ja": manifest["book_title_ja"],
            "book_title_zh_reading": manifest["book_title_zh_reading"],
            "book_title_ja_reading": manifest["book_title_ja_reading"],
            "author": manifest["author"],
            "author_reading_zh": manifest["author_reading_zh"],
            "author_reading_ja": manifest["author_reading_ja"],
            "source_paths": manifest["source_paths"],
            "chunks_jsonl": rel(CHUNKS_DIR / "chunks.jsonl"),
            "chunks_manifest": rel(CHUNKS_DIR / "manifest.json"),
            "raw_chunk_dir": rel(RAW_CHUNK_DIR),
            "preview_json": rel(PREVIEW_DIR / f"{BOOK_ID}.partial.json"),
            "assembled_json": rel(PREVIEW_DIR / f"{BOOK_ID}.partial.json"),
            "build_root": f"build/{BOOK_ID}",
            "cover_image": f"assets/covers/{BOOK_ID}/cover.png",
            "figure_manifest": rel(FIGURE_MANIFEST),
            "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "chunk_count": manifest["chunk_count"],
            "figure_count": manifest["figure_count"],
            "markdown": {"en": rel(MARKDOWN_DIR / "en.md")},
            "preparation_notes": {
                "status": "Chunk manifest prepared and launchable.",
                "workers": 5,
                "source_handling": "OCR English page text plus attached page images for diagrams.",
                "figure_policy": "Every content page chunk carries the original source page image as a required figure block.",
                "music_policy": "Preserve fretboard diagrams, staff/tablature fragments, chord symbols, rhythm examples, tables, captions, quizzes, and exercises.",
            },
        }
    )
    write_json(plan_path, plan)


def update_batch(manifest: dict[str, Any]) -> None:
    batch_path = ROOT / "data/source-plan/music-theory-guitar-source-batch.json"
    if not batch_path.exists():
        return
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    for task in batch.get("tasks", []):
        if task.get("book_id") == BOOK_ID:
            task["status"] = "chunked_launchable"
            task["chunk_count"] = manifest["chunk_count"]
            task["figure_count"] = manifest["figure_count"]
            task["workers"] = 5
            task["prepared_chunks_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    batch["last_chunk_preparation_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(batch_path, batch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--ocr-workers", type=int, default=5)
    parser.add_argument("--ocr-dpi", type=int, default=260)
    args = parser.parse_args()

    if not SOURCE_PDF.exists():
        parser.error(f"source PDF missing: {SOURCE_PDF}")
    ensure_ocr(force=args.force_ocr, workers=args.ocr_workers, dpi=args.ocr_dpi)
    pages = parse_ocr_pages()
    manifest, chunks, figures = build_chunks(pages)

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    write_json(CHUNKS_DIR / "manifest.json", manifest)
    (CHUNKS_DIR / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    write_json(FIGURE_MANIFEST, {"book_id": BOOK_ID, "figures": figures})
    write_text(
        MARKDOWN_DIR / "en.md",
        "# Music Theory for Guitarists\n\n"
        + "\n\n".join(f"## Page {page}\n\n{text}" for page, text in sorted(pages.items()) if page >= 3 and text),
    )
    update_plan(manifest)
    update_batch(manifest)
    print(f"prepared={BOOK_ID} chunks={manifest['chunk_count']} figures={manifest['figure_count']} workers=5")
    print(f"manifest={rel(CHUNKS_DIR / 'manifest.json')}")
    print(f"chunks={rel(CHUNKS_DIR / 'chunks.jsonl')}")
    print(f"figures={rel(FIGURE_MANIFEST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
