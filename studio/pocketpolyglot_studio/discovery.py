from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _manifest_count(path: Path) -> int:
    value = read_json(path)
    chunks = value.get("chunks")
    if isinstance(chunks, list):
        return len(chunks)
    return int(value.get("chunk_count") or value.get("task_count") or 0)


def _json_output_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def discover_repository(repo_root: Path) -> dict[str, Any]:
    books: dict[str, dict[str, Any]] = {}
    books_root = repo_root / "books"
    if books_root.exists():
        for book_root in sorted(path for path in books_root.iterdir() if path.is_dir() and not path.name.startswith("_")):
            book_id = book_root.name
            plan = read_json(book_root / "book-plan.json")
            manifests = sorted(book_root.glob("work/**/chunks/manifest.json"))
            selected_manifest = manifests[-1] if manifests else None
            total = _manifest_count(selected_manifest) if selected_manifest else 0
            chunk_dirs = [
                Path(plan.get("raw_chunk_dir", "")) if plan.get("raw_chunk_dir") else None,
                book_root / "work/trilingual/interlinear/chunks",
                book_root / "work/quadrilingual/interlinear/chunks",
                book_root / "work/bilingual/interlinear/chunks",
            ]
            generated = max(
                (_json_output_count(repo_root / path) if path and not path.is_absolute() else _json_output_count(path) if path else 0)
                for path in chunk_dirs
            )
            pdfs = list((repo_root / "build" / book_id).rglob("*.pdf")) if (repo_root / "build" / book_id).exists() else []
            if total or plan or pdfs:
                books[book_id] = {
                    "book_id": book_id,
                    "title": plan.get("book_title_en") or plan.get("title") or book_id.replace("-", " ").title(),
                    "workflow": "lingualeaf",
                    "manifest": str(selected_manifest.relative_to(repo_root)) if selected_manifest else "",
                    "generated": min(generated, total) if total else generated,
                    "total": total,
                    "pdf_count": len(pdfs),
                    "complete": bool(total and generated >= total),
                    "cover": f"assets/covers/{book_id}/cover.png" if (repo_root / "assets/covers" / book_id / "cover.png").exists() else "",
                }

    polished_root = repo_root / "build-pocket-polished"
    if polished_root.exists():
        for task_root in sorted(path for path in polished_root.iterdir() if path.is_dir()):
            manifest = task_root / "tasks/manifest.json"
            if not manifest.exists():
                continue
            book_id = task_root.name
            total = _manifest_count(manifest)
            generated = _json_output_count(task_root / "json")
            status = read_json(task_root / "status.json")
            item = books.setdefault(
                book_id,
                {
                    "book_id": book_id,
                    "title": book_id.replace("-", " ").title(),
                    "workflow": "pocket_polished",
                    "pdf_count": 0,
                    "cover": "",
                },
            )
            item.update(
                {
                    "workflow": "pocket_polished",
                    "manifest": str(manifest.relative_to(repo_root)),
                    "generated": generated,
                    "total": total,
                    "complete": status.get("status") == "complete" or bool(total and generated >= total),
                    "pdf_count": len(list(task_root.rglob("*.pdf"))),
                }
            )

    values = sorted(books.values(), key=lambda item: (not item["complete"], item["title"].casefold()))
    return {
        "books": values,
        "counts": {
            "books": len(values),
            "complete": sum(1 for item in values if item["complete"]),
            "in_progress": sum(1 for item in values if item["total"] and not item["complete"]),
            "pdfs": sum(item["pdf_count"] for item in values),
        },
    }
