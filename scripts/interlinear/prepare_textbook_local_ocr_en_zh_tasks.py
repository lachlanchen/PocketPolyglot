#!/usr/bin/env python3
"""Prepare local-OCR exact textbook tasks for EN/ZH pocket books.

This extends the older Mathpix exact-TeX manifests without overwriting them.
The task shape is page-first: OCR/parse each source page into structured nodes,
lock equations/figures/tables, then translate prose nodes into Chinese while
copying mathematical content unchanged.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare_textbook_exact_tex_tasks import BOOKS, ROOT, TextbookConfig, sha256


QUEUE_PATH = ROOT / "data/source-plan/technical-textbook-local-ocr-en-zh-queue.json"
NODE_SCHEMA_PATH = ROOT / "data/source-plan/technical-textbook-en-zh-node-schema.json"
ENGINE_ORDER = [
    "marker-surya",
    "mineru",
    "docling",
    "pix2tex-targeted-equations",
    "mathpix-optional-validator",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def run_text(cmd: list[str]) -> str:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    ).stdout.strip()


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def python_imports(module: str, python: str = "python3") -> bool:
    return subprocess.run(
        [python, "-c", f"import {module}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def exact_manifest(book_id: str) -> dict[str, Any]:
    path = ROOT / "books" / book_id / "tasks/exact-tex/manifest.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return load_json(path)


def exact_page_rows(book_id: str) -> list[dict[str, Any]]:
    path = ROOT / "books" / book_id / "tasks/exact-tex/pages.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tool_status(venv_python: str) -> dict[str, Any]:
    return {
        "gpu": run_text(["bash", "-lc", "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1"]),
        "qpdf": command_exists("qpdf"),
        "pdftocairo": command_exists("pdftocairo"),
        "pdfimages": command_exists("pdfimages"),
        "mutool": command_exists("mutool"),
        "python": run_text([venv_python, "--version"]) if Path(venv_python).exists() else run_text(["python3", "--version"]),
        "marker_import": python_imports("marker", venv_python) if Path(venv_python).exists() else python_imports("marker"),
        "surya_import": python_imports("surya", venv_python) if Path(venv_python).exists() else python_imports("surya"),
        "pix2tex_import": python_imports("pix2tex", venv_python) if Path(venv_python).exists() else python_imports("pix2tex"),
        "mineru_import": python_imports("mineru", venv_python) if Path(venv_python).exists() else python_imports("mineru"),
        "docling_import": python_imports("docling", venv_python) if Path(venv_python).exists() else python_imports("docling"),
    }


def page_task(config: TextbookConfig, exact_page: dict[str, Any], source_sha: str | None) -> dict[str, Any]:
    page_no = int(exact_page["physical_page"])
    page_id = f"{config.book_id}-ocr-page-{page_no:04d}"
    base = f"books/{config.book_id}/work/exact-tex/local-ocr"
    return {
        "schema_version": 1,
        "task_type": "textbook_local_ocr_en_zh_page",
        "book_id": config.book_id,
        "page_id": page_id,
        "physical_page": page_no,
        "source_pdf": str(config.exact_source_pdf),
        "source_sha256": source_sha,
        "is_content_page": exact_page.get("is_content_page", False),
        "formula_score": exact_page.get("formula_score", 0),
        "embedded_text_chars": exact_page.get("embedded_text_chars", 0),
        "engine_order": ENGINE_ORDER,
        "input_artifacts": {
            "page_image": f"{base}/page-images/page-{page_no:04d}.png",
            "page_pdf": f"{base}/page-pdfs/page-{page_no:04d}.pdf",
            "existing_mathpix_page": exact_page.get("mathpix_json"),
            "existing_mathpix_mmd": exact_page.get("mathpix_mmd"),
        },
        "output_artifacts": {
            "marker_dir": f"{base}/marker/page-{page_no:04d}",
            "mineru_dir": f"{base}/mineru/page-{page_no:04d}",
            "figures_dir": f"{base}/figures/page-{page_no:04d}",
            "equation_crops_dir": f"{base}/equation-crops/page-{page_no:04d}",
            "structured_nodes": f"{base}/nodes/page-{page_no:04d}.json",
            "page_tex": f"{base}/tex/page-{page_no:04d}.tex",
            "en_zh_json": f"{base}/en-zh-json/page-{page_no:04d}.json",
        },
        "locked_content_policy": {
            "equations": "OCR to real TeX; never translate, flatten, or paraphrase formulas.",
            "tables": "Preserve cell grid, headers, labels, and numeric content; translate prose cells only.",
            "figures": "Extract/crop figures and keep captions; keep diagrams visual if not safely expressible in TeX.",
            "cross_references": "Preserve equation, theorem, figure, table, chapter, and section numbers.",
        },
        "translation_policy": {
            "source_lang": "en",
            "target_lang": "zh",
            "json_shape": "page contains ordered nodes; prose nodes have en and zh; math/table/figure nodes carry locked source plus optional zh caption/comment.",
            "style": "accurate modern Chinese for technical learning; preserve English symbols and terminology where conventional.",
        },
        "acceptance": {
            "source_page_must_be_visually_checked": True,
            "all_visible_equations_represented": True,
            "all_figures_or_diagrams_preserved": True,
            "all_tables_preserved": True,
            "no_ocr_garbage_markers": True,
            "no_unreviewed_formula_guessing": True,
        },
    }


def prepare_book(config: TextbookConfig, tools: dict[str, Any]) -> dict[str, Any]:
    exact = exact_manifest(config.book_id)
    exact_rows = exact_page_rows(config.book_id)
    source_sha = sha256(config.exact_source_pdf)
    rows = [page_task(config, row, source_sha) for row in exact_rows if row.get("is_content_page")]

    task_root = ROOT / "books" / config.book_id / "tasks/local-ocr-en-zh"
    work_root = ROOT / "books" / config.book_id / "work/exact-tex/local-ocr"
    manifest = {
        "schema_version": 1,
        "book_id": config.book_id,
        "status": "prepared_local_ocr_en_zh_not_started",
        "title_en": config.title_en,
        "title_zh": config.title_zh,
        "author": config.author,
        "source_pdf": str(config.exact_source_pdf),
        "source_sha256": source_sha,
        "source_pages": exact.get("page_count"),
        "content_pages": len(rows),
        "source_references": exact.get("source_paths", {}),
        "engine_order": ENGINE_ORDER,
        "node_schema": str(NODE_SCHEMA_PATH.relative_to(ROOT)),
        "tool_status": tools,
        "task_contract": {
            "goal": "Create editable pocket-size TeX and EN/ZH JSON while preserving every equation, figure, diagram, table, caption, and exercise layout.",
            "primary_engine": "marker-surya in `.venv/ocr` for whole-page structure.",
            "secondary_engine": "MinerU if installed for cross-checking formula/table/layout extraction.",
            "formula_fallback": "pix2tex on cropped equations when Marker/MinerU disagree or omit TeX.",
            "validation": [
                "run local OCR on page ranges first",
                "compare structured nodes against source page image",
                "compile pocket TeX and inspect overfull/missing-image logs",
                "only generate final EN/ZH JSON after page-node validation",
            ],
        },
        "tasks_jsonl": str(task_root.relative_to(ROOT) / "pages.jsonl"),
        "work_root": str(work_root.relative_to(ROOT)),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(task_root / "manifest.json", manifest)
    write_jsonl(task_root / "pages.jsonl", rows)
    (task_root / "README.md").write_text(
        "\n".join(
            [
                f"# {config.title_en} Local OCR EN/ZH Tasks",
                "",
                "Use this manifest for the local Mathpix-parity OCR path. It does not replace the existing exact-TeX/Mathpix artifacts.",
                "",
                "Required order:",
                "",
                "1. Run `scripts/interlinear/run_textbook_local_ocr.py --book-id "
                f"{config.book_id} --smoke` and inspect the output.",
                "2. Run full local OCR only after smoke output preserves equations, tables, and figures.",
                "3. Build structured nodes and EN/ZH JSON from reviewed page output.",
                "4. Compile pocket-size English and EN/ZH PDFs; fix overfull lines and missing figures before finalizing.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "book_id": config.book_id,
        "title_en": config.title_en,
        "title_zh": config.title_zh,
        "source_pdf": str(config.exact_source_pdf),
        "content_pages": len(rows),
        "task_manifest": str((task_root / "manifest.json").relative_to(ROOT)),
        "tasks_jsonl": str((task_root / "pages.jsonl").relative_to(ROOT)),
        "work_root": str(work_root.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", choices=sorted(BOOKS), help="Prepare one book; repeatable.")
    parser.add_argument("--venv-python", default=".venv/ocr/bin/python", help="Python executable for local OCR stack checks.")
    args = parser.parse_args()

    selected = args.book_id or [
        "game-theory",
        "game-theory-101",
        "nonlinear-dynamics-and-chaos",
        "chaos-making-new-science",
        "qft-gifted-amateur",
    ]
    tools = tool_status(args.venv_python)
    books = [prepare_book(BOOKS[book_id], tools) for book_id in selected]
    queue = {
        "schema_version": 1,
        "queue_id": "technical-textbook-local-ocr-en-zh",
        "status": "prepared_not_started",
        "description": "Local OCR exact-TeX and EN/ZH JSON queue for formula/table/figure-heavy technical books.",
        "engine_order": ENGINE_ORDER,
        "node_schema": str(NODE_SCHEMA_PATH.relative_to(ROOT)),
        "tool_status": tools,
        "books": books,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(QUEUE_PATH, queue)
    for book in books:
        print(f"prepared {book['book_id']} content_pages={book['content_pages']} manifest={book['task_manifest']}")
    print(f"queue={QUEUE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
