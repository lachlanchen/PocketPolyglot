#!/usr/bin/env python3
"""Prepare Berklee Music Theory Book 1 trilingual pocket-book tasks.

The Berklee source PDF has extractable text, but its notation, keyboard
diagrams, rhythm examples, and exercises are visual first-class content. This
preparer uses text extraction for the English alignment spine and attaches each
source page image as a required figure asset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = "berklee-music-theory-book-1"
SOURCE_PDF = (
    ROOT
    / "resources/curated-books/music-theory-and-guitar/recommended/berklee/en/"
    / "Berklee Music Theory Book 1.pdf"
)
BOOK_ROOT = ROOT / "books" / BOOK_ID
WORK_ROOT = BOOK_ROOT / "work/trilingual"
EXTRACTED_MD = WORK_ROOT / "source-extract/source-pages.md"
PAGE_IMAGES = WORK_ROOT / "page-images"
CHUNKS_DIR = WORK_ROOT / "chunks"
RAW_CHUNK_DIR = WORK_ROOT / "interlinear/chunks"
PREVIEW_DIR = WORK_ROOT / "preview"
MARKDOWN_DIR = BOOK_ROOT / "markdown"
ASSET_DIR = WORK_ROOT / "assets"
FIGURE_MANIFEST = ASSET_DIR / "figure-manifest.json"

CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

START_PAGE = 6
SPACE_RE = re.compile(r"[ \t\u00a0]+")
PROSE_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")
TITLE_RE = re.compile(
    r"^(Introduction|Lesson\s+\d+\.\s+.+|EXERCISES,\s+LESSONS.+|Exercises,\s+Lessons.+|What.s Next\??|About the Author|Practice the examples with a real keyboard.+)\s*$",
    re.I,
)
VISUAL_GLYPHS_RE = re.compile(r"[œŒ˙Ó∑ã‰&♯♭𝄞𝄢|]{1,}")

ZH_GLOSSARY = """Technical terminology reference:
pulse=脉搏/节拍脉冲; beat=拍; meter=拍子; measure=小节; bar=小节; bar line=小节线; final bar line=终止小节线; time signature=拍号; common time=普通拍子; staff=五线谱; line=线; space=间; percussion clef=打击乐谱号; treble clef=高音谱号; bass clef=低音谱号; grand staff=大谱表; note=音符; whole note=全音符; half note=二分音符; quarter note=四分音符; eighth note=八分音符; rest=休止符; whole rest=全休止符; half rest=二分休止符; quarter rest=四分休止符; dotted rhythm=附点节奏; tie=延音线; beam=符杠; pitch=音高; accidental=临时记号; sharp=升号; flat=降号; natural=还原号; key signature=调号; enharmonic equivalent=等音异名; half step=半音; whole step=全音; chromatic scale=半音阶; whole-tone scale=全音音阶; major scale=大调音阶; natural minor scale=自然小调音阶; harmonic minor scale=和声小调音阶; melodic minor scale=旋律小调音阶; relative major/minor=关系大小调; interval=音程; perfect interval=纯音程; major interval=大音程; minor interval=小音程; diminished=减; augmented=增; compound interval=复音程; ear training=听力训练; practice=练习.
Use concise, readable modern Chinese for study notes. Preserve note names, scale-degree numbers, track numbers, measure numbers, accidentals, and exercise numbering exactly."""

JA_GLOSSARY = """Technical terminology reference:
pulse=拍の脈動; beat=拍; meter=拍子; measure=小節; bar=小節; bar line=小節線; final bar line=終止線; time signature=拍子記号; common time=コモンタイム; staff=五線; line=線; space=間; percussion clef=打楽器用の音部記号; treble clef=ト音記号; bass clef=ヘ音記号; grand staff=大譜表; note=音符; whole note=全音符; half note=二分音符; quarter note=四分音符; eighth note=八分音符; rest=休符; whole rest=全休符; half rest=二分休符; quarter rest=四分休符; dotted rhythm=付点リズム; tie=タイ; beam=連桁; pitch=音高; accidental=臨時記号; sharp=シャープ/嬰記号; flat=フラット/変記号; natural=ナチュラル/本位記号; key signature=調号; enharmonic equivalent=異名同音; half step=半音; whole step=全音; chromatic scale=クロマチック・スケール; whole-tone scale=全音音階; major scale=メジャー・スケール; natural minor scale=ナチュラル・マイナー・スケール; harmonic minor scale=ハーモニック・マイナー・スケール; melodic minor scale=メロディック・マイナー・スケール; relative major/minor=平行調; interval=音程; perfect interval=完全音程; major interval=長音程; minor interval=短音程; diminished=減; augmented=増; compound interval=複音程; ear training=イヤー・トレーニング; practice=練習.
Use clear common modern Japanese for study notes. Preserve note names, scale-degree numbers, track numbers, measure numbers, accidentals, and exercise numbering exactly."""


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


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def pdf_page_count() -> int:
    proc = run(["pdfinfo", str(SOURCE_PDF)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", proc.stdout, re.M)
    if not match:
        raise RuntimeError("pdfinfo did not report page count")
    return int(match.group(1))


def extract_pages(*, force: bool) -> dict[int, str]:
    page_count = pdf_page_count()
    if EXTRACTED_MD.exists() and not force:
        return parse_markdown_pages(EXTRACTED_MD.read_text(encoding="utf-8", errors="replace"))
    proc = run(["pdftotext", "-layout", "-f", "1", "-l", str(page_count), str(SOURCE_PDF), "-"])
    pages: dict[int, str] = {}
    for index, text in enumerate(proc.stdout.split("\f"), start=1):
        if index <= page_count:
            pages[index] = text.rstrip()
    body = [
        "---",
        f"source_pdf: {SOURCE_PDF.name}",
        f"source_pages: 1-{page_count}",
        f"total_pdf_pages: {page_count}",
        "extractor: pdftotext -layout",
        f"generated_at: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "notes: Extracted source text. Visual notation and exercises are preserved via page images.",
        "---",
        "",
        f"# Extracted Text: {SOURCE_PDF.name}",
    ]
    for page in range(1, page_count + 1):
        body.append(f"## Page {page}")
        body.append(pages.get(page, "").rstrip())
        body.append("")
    write_text(EXTRACTED_MD, "\n".join(body))
    return pages


def parse_markdown_pages(text: str) -> dict[int, str]:
    pages: dict[int, list[str]] = {}
    current: int | None = None
    for line in text.splitlines():
        match = re.match(r"^## Page (\d+)\s*$", line)
        if match:
            current = int(match.group(1))
            pages[current] = []
            continue
        if current is not None:
            pages[current].append(line)
    return {page: "\n".join(lines).strip() for page, lines in pages.items()}


def ensure_page_images(*, force: bool, dpi: int) -> None:
    page_count = pdf_page_count()
    expected = PAGE_IMAGES / f"page-{page_count:04d}.png"
    if expected.exists() and not force:
        return
    PAGE_IMAGES.mkdir(parents=True, exist_ok=True)
    for page in range(1, page_count + 1):
        out = PAGE_IMAGES / f"page-{page:04d}"
        image = out.with_suffix(".png")
        if image.exists() and not force:
            continue
        proc = run(
            [
                "pdftoppm",
                "-q",
                "-r",
                str(dpi),
                "-png",
                "-f",
                str(page),
                "-l",
                str(page),
                "-singlefile",
                str(SOURCE_PDF),
                str(out),
            ],
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout)


def normalize_line(line: str) -> str:
    line = line.replace("\u00ad", "").replace("\u2014", "-")
    line = line.replace("", "")
    return SPACE_RE.sub(" ", line).strip()


def is_visual_line(line: str) -> bool:
    if not line:
        return True
    if re.fullmatch(r"(?:[ivxlcdm]+|\d{1,3})", line, re.I):
        return True
    if line == "Berklee Music Theory, Book 1":
        return True
    words = PROSE_WORD_RE.findall(line)
    visible = len(re.sub(r"\s+", "", line))
    symbols = len(re.findall(r"[^A-Za-z0-9\s]", line))
    music_glyphs = len(VISUAL_GLYPHS_RE.findall(line))
    if line.startswith(("&", "?", "{", "}", "|")) and len(PROSE_WORD_RE.findall(line)) <= 2:
        return True
    if re.match(r"^\d{1,2}\s*[œŒ˙Ó∑ã’‰w]", line):
        return True
    if music_glyphs and len(words) <= 10:
        return True
    if music_glyphs >= 3:
        return True
    if visible >= 18 and len(words) <= 3 and symbols >= 5:
        return True
    if visible >= 24 and len(words) <= 5 and re.search(r"[œŒ˙Ó∑&?]", line):
        return True
    if re.fullmatch(r"[0-9A-Ga-g#b.+\-–—_\sœŒ˙Ó∑ã’‰wj]+", line) and len(words) <= 4:
        return True
    if re.fullmatch(r"[A-G](?:[#b])?(?:\s+[A-G](?:[#b])?){3,}", line):
        return True
    return False


def clean_page_text(raw: str) -> str:
    lines = [normalize_line(line) for line in raw.splitlines()]
    paragraphs: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            paragraphs.append(" ".join(pending).strip())
            pending = []

    for line in lines:
        if is_visual_line(line):
            flush()
            continue
        if TITLE_RE.match(line) or re.match(r"^(Practice|Ear Training|The Musical Staff|CD Tracks?|Listening|Writing|Keyboard)\b", line, re.I):
            flush()
            paragraphs.append(line)
            continue
        pending.append(line)
    flush()
    if len(paragraphs) >= 2 and paragraphs[0] == paragraphs[1] and TITLE_RE.match(paragraphs[0]):
        paragraphs = paragraphs[1:]
    text = "\n\n".join(part for part in paragraphs if part).strip()
    text = re.sub(r"\b([A-Za-z]+)-\s+([a-z]+)\b", r"\1\2", text)
    return text


def detect_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if TITLE_RE.match(line):
            return line
    return fallback


def chapter_slug(title: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", title.lower()).strip("-")
    return text[:64] or "section"


def figure_for_page(page: int, chapter_title: str) -> dict[str, Any]:
    image = PAGE_IMAGES / f"page-{page:04d}.png"
    return {
        "kind": "source_page_image",
        "path": rel(image),
        "source_page": page,
        "caption": (
            f"Source page {page}: {chapter_title}. Original page image retained for staff notation, rhythm examples, "
            "keyboard diagrams, tables, practice exercises, and visual layout."
        ),
        "required_for_publication": True,
    }


def build_chunks(pages: dict[int, str]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    chapter_numbers: dict[str, int] = {}
    current_title = "Introduction"
    for page in range(START_PAGE, max(pages) + 1):
        text = clean_page_text(pages.get(page, ""))
        if not text:
            continue
        detected = detect_title(text, current_title)
        if detected:
            current_title = detected
        slug = chapter_slug(current_title)
        chapter_number = chapter_numbers.setdefault(slug, len(chapter_numbers) + 1)
        chunk_index = len(chunks) + 1
        chunk_id = f"{BOOK_ID}-c{chunk_index:04d}"
        paragraph_id = f"{BOOK_ID}-p{page:04d}"
        figure = figure_for_page(page, current_title)
        figures.append({"chunk_id": chunk_id, **figure})
        chunks.append(
            {
                "schema_version": 1,
                "mode": "trilingual_standard",
                "book_id": BOOK_ID,
                "source_spine_lang": "en",
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "chapter_id": f"chapter-{chapter_number:02d}-{slug}",
                "chapter_number": chapter_number,
                "chapter_title_en": current_title,
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
                        "chapter": current_title,
                        "text": text,
                        "quality": "extracted_page_spine_review_against_image",
                    },
                    "zh_primary": {
                        "available": True,
                        "chapter": "music terminology glossary",
                        "text": ZH_GLOSSARY,
                        "quality": "terminology_reference",
                    },
                    "zh_secondary": {
                        "available": True,
                        "chapter": "general Chinese music theory references",
                        "text": "Use local Chinese music theory references for terminology consistency when needed.",
                        "quality": "broad_reference",
                    },
                    "ja": {
                        "available": True,
                        "chapter": "music terminology glossary",
                        "text": JA_GLOSSARY,
                        "quality": "terminology_reference",
                    },
                },
                "technical_note": (
                    "Preserve note names, rests, rhythms, accidentals, time signatures, scale-degree labels, track numbers, "
                    "exercise numbering, and all musical notation references. Use the attached source page image as visual "
                    "evidence for staff notation, keyboard diagrams, rhythm examples, and tables; do not omit exercises."
                ),
            }
        )

    manifest = {
        "schema_version": 1,
        "mode": "trilingual_standard",
        "book_id": BOOK_ID,
        "book_title_en": "Berklee Music Theory Book 1",
        "book_title_zh": "伯克利音乐理论第一册",
        "book_title_ja": "バークリー音楽理論 第1巻",
        "book_title_zh_reading": "bó kè lì yīn yuè lǐ lùn dì yī cè",
        "book_title_ja_reading": "バークリー おんがく りろん だい いっかん",
        "author": "Paul Schmeling",
        "author_reading_zh": "bǎo luó shī méi líng",
        "author_reading_ja": "ポール シュメリング",
        "curated_by": CURATED_BY,
        "curated_url": CURATED_URL,
        "powered_by": POWERED_BY,
        "source_spine_lang": "en",
        "source_paths": {
            "en_primary": rel(SOURCE_PDF),
            "extracted_markdown": rel(EXTRACTED_MD),
            "page_images": rel(PAGE_IMAGES),
            "en_guitar_method_volume_1": "resources/curated-books/music-theory-and-guitar/berklee-guitar-method/en/A Modern Method for Guitar - Volume 1.pdf",
            "en_guitar_method_volume_2": "resources/curated-books/music-theory-and-guitar/berklee-guitar-method/en/A Modern Method for Guitar - Volume 2.pdf",
            "zh_music_theory_reference": "resources/curated-books/music-theory-and-guitar/zh/music-theory/音乐分析法 (Analyse lernen).pdf",
            "zh_music_history_reference": "resources/curated-books/music-theory-and-guitar/zh/music-theory/剑桥西方音乐理论发展史.pdf",
            "ja_music_theory_reference": "resources/curated-books/music-theory-and-guitar/ja/music-theory/楽典 音楽の基礎から和声へ.pdf",
            "ja_music_dictionary_reference": "resources/curated-books/music-theory-and-guitar/ja/music-theory/カラー 図解音楽事典 dtv-Atlas zur Musik.pdf",
        },
        "source_sha256": {"en_primary": sha256(SOURCE_PDF)},
        "source_note": (
            "Text-based music-theory PDF prepared as private EN-JP-ZH study task. "
            "Extracted text is the English alignment spine, and original page images are attached as required figure assets."
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
                "source_handling": "Extracted English page text plus attached page images for notation and diagrams.",
                "figure_policy": "Every content page chunk carries the original source page image as a required figure block.",
                "music_policy": "Preserve notation vocabulary, chord symbols, staff/rhythm examples, keyboard diagrams, captions, exercises, and tables.",
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
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--force-images", action="store_true")
    parser.add_argument("--image-dpi", type=int, default=150)
    args = parser.parse_args()

    if not SOURCE_PDF.exists():
        parser.error(f"source PDF missing: {SOURCE_PDF}")
    if not shutil.which("pdftotext") or not shutil.which("pdftoppm"):
        parser.error("pdftotext and pdftoppm are required")

    pages = extract_pages(force=args.force_extract)
    ensure_page_images(force=args.force_images, dpi=args.image_dpi)
    manifest, chunks, figures = build_chunks(pages)

    for path in (CHUNKS_DIR, RAW_CHUNK_DIR, PREVIEW_DIR, ASSET_DIR, MARKDOWN_DIR):
        path.mkdir(parents=True, exist_ok=True)
    write_json(CHUNKS_DIR / "manifest.json", manifest)
    (CHUNKS_DIR / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    write_json(FIGURE_MANIFEST, {"book_id": BOOK_ID, "figures": figures})
    write_text(
        MARKDOWN_DIR / "en.md",
        "# Berklee Music Theory Book 1\n\n"
        + "\n\n".join(
            f"## Page {page}\n\n{clean_page_text(text)}"
            for page, text in sorted(pages.items())
            if page >= START_PAGE and clean_page_text(text)
        ),
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
