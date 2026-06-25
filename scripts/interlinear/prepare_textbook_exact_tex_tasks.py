#!/usr/bin/env python3
"""Prepare page-faithful textbook-to-TeX tasks.

Technical textbooks must not go through the normal prose-first trilingual
chunker. This preparer creates a page-level exact-TeX task contract: render
source pages, OCR with Mathpix for formula-bearing content, review against the
page image, assemble pocket-size TeX, then derive multilingual editions without
changing formulas.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CURATED_BY = "AgInTiFlow curated"
CURATED_URL = "https://flow.lazying.art"
POWERED_BY = "powered by LazyingArt"

CONTENT_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
FORMULA_RE = re.compile(r"[=<>≤≥∑∫√∞≈≠±×÷∂∇πλμσθωαβγδ_{}^]|\\(?:sum|int|frac|sqrt|alpha|beta|gamma|lambda)")
THEOREM_RE = re.compile(r"\b(?:Definition|Theorem|Lemma|Proposition|Corollary|Proof|Example|Exercise|Assumption)\b", re.I)
SPACE_RE = re.compile(r"\s+")


@dataclasses.dataclass(frozen=True)
class TextbookConfig:
    book_id: str
    title_en: str
    title_zh: str
    title_ja: str
    title_zh_reading: str
    title_ja_reading: str
    author: str
    author_reading_zh: str
    author_reading_ja: str
    exact_source_lang: str
    exact_source_pdf: Path
    zh_reference_pdf: Path | None
    en_secondary_sources: tuple[Path, ...] = ()
    body_start_marker: str = ""
    description: str = ""


BOOKS: dict[str, TextbookConfig] = {
    "game-theory": TextbookConfig(
        book_id="game-theory",
        title_en="Game Theory",
        title_zh="博弈论",
        title_ja="ゲーム理論",
        title_zh_reading="bó yì lùn",
        title_ja_reading="ゲーム りろん",
        author="Martin J. Osborne and Ariel Rubinstein",
        author_reading_zh="mǎ dīng ào sī běn hé ā ruì ěr lǔ bīn sī tǎn",
        author_reading_ja="マーティン オズボーン と アリエル ルービンシュタイン",
        exact_source_lang="en",
        exact_source_pdf=Path("sources/game-theory/A Course in Game Theory.pdf"),
        zh_reference_pdf=Path("sources/game-theory/博弈论教程.pdf"),
        en_secondary_sources=(Path("sources/game-theory/Game_Theory_101_Complete_Textbook_2011.pdf"),),
        body_start_marker="1 Introduction",
        description=(
            "Retype Osborne and Rubinstein, A Course in Game Theory, as a pocket-size TeX book. "
            "All definitions, propositions, payoff matrices, symbols, equations, and references must "
            "match the source. The Chinese PDF is reference material but has almost no embedded text, "
            "so OCR/polish is required before relying on it for translated editions."
        ),
    ),
    "nonlinear-dynamics-and-chaos": TextbookConfig(
        book_id="nonlinear-dynamics-and-chaos",
        title_en="Nonlinear Dynamics and Chaos",
        title_zh="非线性动力学与混沌",
        title_ja="非線形ダイナミクスとカオス",
        title_zh_reading="fēi xiàn xìng dòng lì xué yǔ hùn dùn",
        title_ja_reading="ひせんけい ダイナミクス と カオス",
        author="Steven H. Strogatz",
        author_reading_zh="shǐ dì fēn H. sī tuō jiā cí",
        author_reading_ja="スティーヴン H. ストロガッツ",
        exact_source_lang="en",
        exact_source_pdf=Path(
            "sources/nonlinear-dynamics-and-chaos/"
            "Nonlinear Dynamics and Chaos - With Applications to Physics, Biology, Chemistry, and Engineering.pdf"
        ),
        zh_reference_pdf=Path("sources/nonlinear-dynamics-and-chaos/非线性动力学与混沌.pdf"),
        body_start_marker="1.0 Chaos, Fractals, and Dynamics",
        description=(
            "Retype Strogatz, Nonlinear Dynamics and Chaos, as a pocket-size TeX book. "
            "Equations, figures, captions, examples, exercises, and section numbering must be preserved. "
            "The Chinese PDF is a second-edition translation and should be used as a reference, not as "
            "a replacement for the English exact source."
        ),
    ),
    "qft-gifted-amateur": TextbookConfig(
        book_id="qft-gifted-amateur",
        title_en="Quantum Field Theory for the Gifted Amateur",
        title_zh="献给有天赋业余者的量子场论",
        title_ja="才能あるアマチュアのための量子場理論",
        title_zh_reading="xiàn gěi yǒu tiān fù yè yú zhě de liàng zǐ chǎng lùn",
        title_ja_reading="さいのう ある アマチュア の ため の りょうし ば りろん",
        author="Tom Lancaster and Stephen J. Blundell",
        author_reading_zh="tāng mǔ lán kǎ sī tè hé sī dì fēn J. bù lún dé ěr",
        author_reading_ja="トム ランカスター と スティーヴン J. ブランデル",
        exact_source_lang="en",
        exact_source_pdf=Path(
            "sources/quantum-field-theory-gifted-amateur/"
            "Quantum_Field_Theory_For_The_Gifted_Amateur.pdf"
        ),
        zh_reference_pdf=None,
        body_start_marker="Quantum Field Theory for the Gifted Amateur",
        description=(
            "Retype Lancaster and Blundell, Quantum Field Theory for the Gifted Amateur, "
            "as a pocket-size TeX book. This is a formula-dense physics textbook: all "
            "inline/display equations, Feynman diagrams, examples, exercises, footnotes, "
            "tables, captions, appendices, and references must be preserved page by page. "
            "Mathpix whole-PDF OCR is required as the first pass; plain pdftotext is only "
            "a navigation aid and must not be trusted for formulas."
        ),
    ),
}


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT).decode("utf-8", errors="replace")


def command_exists(name: str) -> bool:
    return subprocess.run(["bash", "-lc", f"command -v {name} >/dev/null 2>&1"], cwd=ROOT).returncode == 0


def python_module_exists(name: str) -> bool:
    return subprocess.run(
        ["python", "-c", f"import {name}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def rel(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256(rel(path).read_bytes()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\u00a0", " ").replace("\u3000", " ")).strip()


def pdfinfo(path: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in run_text(["pdfinfo", str(path)]).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[key.strip()] = value.strip()
    return info


def pdf_text_pages(path: Path) -> list[str]:
    text = run_text(["pdftotext", "-layout", str(path), "-"])
    pages = text.split("\f")
    if pages and not compact(pages[-1]):
        pages.pop()
    return pages


def content_chars(text: str) -> int:
    return len(CONTENT_RE.findall(text))


def formula_score(text: str) -> int:
    return len(FORMULA_RE.findall(text)) + 2 * len(THEOREM_RE.findall(text))


def find_body_start_page(pages: list[str], marker: str) -> int:
    if not marker:
        return 1
    marker_lower = compact(marker).lower()
    for index, page in enumerate(pages, start=1):
        if marker_lower in compact(page).lower():
            return index
    return 1


def source_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False}
    info = pdfinfo(path)
    pages = pdf_text_pages(path)
    chars = sum(content_chars(page) for page in pages)
    return {
        "available": True,
        "path": str(path),
        "sha256": sha256(path),
        "pages": int(info.get("Pages", "0") or 0),
        "page_size": info.get("Page size", ""),
        "embedded_text_chars": chars,
        "embedded_text_usable": chars >= 2000,
    }


def page_tasks(config: TextbookConfig, pages: list[str], page_count: int, body_start_page: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        text = pages[page_number - 1] if page_number <= len(pages) else ""
        chars = content_chars(text)
        score = formula_score(text)
        is_content = page_number >= body_start_page and chars > 0
        page_id = f"{config.book_id}-page-{page_number:04d}"
        tasks.append(
            {
                "schema_version": 1,
                "task_type": "textbook_exact_tex_page",
                "book_id": config.book_id,
                "page_id": page_id,
                "source_pdf": str(config.exact_source_pdf),
                "source_lang": config.exact_source_lang,
                "physical_page": page_number,
                "body_start_page": body_start_page,
                "is_content_page": is_content,
                "embedded_text_chars": chars,
                "formula_score": score,
                "requires_mathpix": is_content,
                "requires_human_or_codex_visual_check": is_content and (score > 0 or chars < 80),
                "render_image": f"books/{config.book_id}/work/exact-tex/page-images/page-{page_number:04d}.png",
                "mathpix_json": f"books/{config.book_id}/work/exact-tex/mathpix/page-{page_number:04d}.json",
                "mathpix_mmd": f"books/{config.book_id}/work/exact-tex/mathpix/page-{page_number:04d}.mmd",
                "page_tex": f"books/{config.book_id}/work/exact-tex/pages/page-{page_number:04d}.tex",
                "reviewed_page_tex": f"books/{config.book_id}/work/exact-tex/reviewed-pages/page-{page_number:04d}.tex",
                "acceptance": {
                    "must_preserve_all_visible_text": True,
                    "must_preserve_all_equations": True,
                    "must_preserve_section_numbering": True,
                    "must_preserve_figures_and_captions": True,
                    "must_compare_against_source_image": True,
                },
                "embedded_text_preview": compact(text)[:700],
            }
        )
    return tasks


def prepare(config: TextbookConfig) -> dict[str, Any]:
    info = pdfinfo(config.exact_source_pdf)
    page_count = int(info.get("Pages", "0") or 0)
    pages = pdf_text_pages(config.exact_source_pdf)
    body_start = find_body_start_page(pages, config.body_start_marker)
    tasks = page_tasks(config, pages, page_count, body_start)

    book_root = Path("books") / config.book_id
    task_root = book_root / "tasks/exact-tex"
    work_root = book_root / "work/exact-tex"
    build_root = Path("build") / f"{config.book_id}-exact-pocket"

    source_paths: dict[str, Any] = {
        "exact_source": str(config.exact_source_pdf),
    }
    if config.zh_reference_pdf:
        source_paths["zh_reference"] = str(config.zh_reference_pdf)
    if config.en_secondary_sources:
        source_paths["en_secondary"] = [str(path) for path in config.en_secondary_sources]

    source_sha256: dict[str, Any] = {
        "exact_source": sha256(config.exact_source_pdf),
    }
    if config.zh_reference_pdf:
        source_sha256["zh_reference"] = sha256(config.zh_reference_pdf)
    if config.en_secondary_sources:
        source_sha256["en_secondary"] = {str(path): sha256(path) for path in config.en_secondary_sources}

    tools = {
        "mathpix_api_credentials": bool(os.environ.get("MATHPIX_APP_ID") and os.environ.get("MATHPIX_APP_KEY")),
        "mathpix_pdf_helper": "scripts/interlinear/textbook_mathpix_pdf_job.py",
        "mathpix_image_helper": "scripts/interlinear/textbook_mathpix_ocr_worker.py",
        "mpxpy": python_module_exists("mpxpy"),
        "pdftocairo": command_exists("pdftocairo"),
        "pdftoppm": command_exists("pdftoppm"),
        "pdfimages": command_exists("pdfimages"),
        "mutool": command_exists("mutool"),
        "tesseract": command_exists("tesseract"),
        "pix2tex": command_exists("pix2tex") or command_exists("latexocr"),
    }

    manifest = {
        "schema_version": 1,
        "book_id": config.book_id,
        "status": "prepared_exact_tex_not_started",
        "task_mode": "exact_textbook_tex_then_multilingual",
        "launchable": True,
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
        "source_paths": source_paths,
        "source_sha256": source_sha256,
        "source_status": {
            "exact_source": source_status(config.exact_source_pdf),
            "zh_reference": source_status(config.zh_reference_pdf),
        },
        "tools": tools,
        "page_count": page_count,
        "body_start_page": body_start,
        "content_page_count": sum(1 for task in tasks if task["is_content_page"]),
        "mathpix_required_page_count": sum(1 for task in tasks if task["requires_mathpix"]),
        "task_contract": {
            "first_artifact": "page-faithful TeX fragments, reviewed against source page images",
            "preferred_ocr": (
                "Use Mathpix v3/pdf whole-document OCR first, requesting tex.zip, mmd.zip, md.zip, "
                "and lines.json. Use per-page Mathpix OCR only for pages that need targeted repair."
            ),
            "formula_policy": "All displayed and inline formulas must be represented as TeX, not paraphrased prose.",
            "figure_policy": "Extract or crop figures from the source PDF and preserve captions; do not silently drop diagrams.",
            "translation_policy": (
                "After exact TeX is assembled, split text/math nodes. Translate text nodes to modern Japanese "
                "and Chinese; copy math nodes unchanged into multilingual editions."
            ),
            "layout_policy": "Use tex/textbook-pocket with the same 105mm x 148mm pocket geometry and font scale as current books.",
            "validation_policy": [
                "compile exact pocket PDF with XeLaTeX",
                "compare page/task coverage against manifest",
                "spot-check formula-heavy pages visually against source images",
                "check TeX log for severe overfull lines and missing figures",
                "only then generate EN-JP-ZH editions",
            ],
        },
        "tasks_jsonl": str(task_root / "pages.jsonl"),
        "manifest": str(task_root / "manifest.json"),
        "work_root": str(work_root),
        "mathpix_pdf_job_dir": str(work_root / "mathpix-pdf"),
        "build_root": str(build_root),
        "tex_template": "tex/textbook-pocket/book.tex",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "description": config.description,
    }
    write_json(task_root / "manifest.json", manifest)
    write_jsonl(task_root / "pages.jsonl", tasks)
    write_json(book_root / "book-plan.json", manifest)
    write_text(
        task_root / "README.md",
        "\n".join(
            [
                f"# {config.title_en} Exact TeX Task",
                "",
                config.description,
                "",
                "This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.",
                "",
                "Required order:",
                "",
                "1. Render page images from the exact source PDF.",
                "2. Run Mathpix OCR for every content page, especially formula-heavy pages.",
                "3. Review each page against the image and correct formulas, theorem labels, figures, and captions.",
                "4. Assemble `build/<book>-exact-pocket/source.tex` with `tex/textbook-pocket/book.tex`.",
                "5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.",
                "",
                "Do not start from `pdftotext` prose chunks for this book.",
            ]
        )
        + "\n",
    )
    return {
        "book_id": config.book_id,
        "pages": page_count,
        "content_pages": manifest["content_page_count"],
        "mathpix_pages": manifest["mathpix_required_page_count"],
        "zh_reference_usable": manifest["source_status"]["zh_reference"].get("embedded_text_usable", False),
    }


def write_reference_doc(results: list[dict[str, Any]]) -> None:
    lines = [
        "# Exact Textbook TeX Task Plan",
        "",
        f"Prepared at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "These textbooks are formula-heavy. They must be converted page-faithfully into TeX before any multilingual PocketPolyglot edition is generated.",
        "",
        "The renderer target is the same pocket profile used by the current books: 105 mm x 148 mm, XeLaTeX, 10 pt document base, and the existing font scale.",
        "",
        "| Book ID | Source pages | Content pages | Mathpix pages | Chinese reference | Task path |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        caveat = "embedded text usable" if result["zh_reference_usable"] else "OCR/polish required"
        lines.append(
            f"| `{result['book_id']}` | {result['pages']} | {result['content_pages']} | "
            f"{result['mathpix_pages']} | {caveat} | `books/{result['book_id']}/tasks/exact-tex/` |"
        )
    lines.extend(
        [
            "",
            "Future start order:",
            "",
            "1. Run page-image rendering and Mathpix OCR workers against `tasks/exact-tex/pages.jsonl`.",
            "2. Run Codex page review to produce `reviewed-pages/page-####.tex`.",
            "3. Assemble the exact pocket TeX/PDF.",
            "4. Split reviewed TeX into text/math nodes and generate EN-JP-ZH editions while copying formulas unchanged.",
            "",
            "Mathpix API credentials are detected from `MATHPIX_APP_ID` and `MATHPIX_APP_KEY`. If unavailable in a later shell, use open-source OCR only for text and pause formula pages instead of guessing.",
        ]
    )
    write_text(Path("references/TEXTBOOK_EXACT_TEX_TASKS_2026-06-25.md"), "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    args = parser.parse_args()

    selected = args.book_id or list(BOOKS)
    results = []
    for book_id in selected:
        result = prepare(BOOKS[book_id])
        results.append(result)
        print(
            "prepared "
            f"book_id={result['book_id']} pages={result['pages']} "
            f"content_pages={result['content_pages']} mathpix_pages={result['mathpix_pages']} "
            f"zh_reference_usable={result['zh_reference_usable']}",
            flush=True,
        )
    write_reference_doc(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
