from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utc_now
from .model_router import PROFILE_REASONING


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_capture(argv: list[str], *, cwd: Path, timeout: int = 120) -> tuple[int, str]:
    try:
        process = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return process.returncode, process.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)


def inspect_source(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "extension": path.suffix.casefold(),
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }
    if not path.is_file():
        return result
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    result["sha256"] = digest.hexdigest()
    if path.suffix.casefold() == ".pdf":
        code, info = run_capture(["pdfinfo", str(path)], cwd=path.parent)
        result["pdfinfo_ok"] = code == 0
        for line in info.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip() in {"Pages", "Page size", "Title", "Author", "Encrypted"}:
                    result[key.strip().lower().replace(" ", "_")] = value.strip()
        code, sample = run_capture(["pdftotext", "-f", "1", "-l", "3", str(path), "-"], cwd=path.parent)
        sample = sample.strip()
        result["text_extract_ok"] = code == 0 and len(sample) >= 80
        result["text_sample"] = sample[:1200]
        code, images = run_capture(["pdfimages", "-list", str(path)], cwd=path.parent)
        result["image_rows"] = max(0, len(images.splitlines()) - 2) if code == 0 else None
    elif path.suffix.casefold() == ".epub":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
            result["archive_ok"] = True
            result["document_files"] = sum(name.casefold().endswith((".xhtml", ".html", ".htm")) for name in names)
            result["image_files"] = sum(name.casefold().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) for name in names)
        except (OSError, zipfile.BadZipFile) as error:
            result["archive_ok"] = False
            result["error"] = str(error)
    return result


def inspect_project(settings: Settings, database: Database, project_id: str) -> Path:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    sources = database.list_sources(project_id)
    report = {
        "schema_version": 1,
        "project_id": project_id,
        "book_id": project["book_id"],
        "generated_at": utc_now(),
        "sources": [inspect_source(Path(source["path"])) for source in sources],
    }
    report["ready"] = bool(report["sources"]) and all(item["exists"] for item in report["sources"])
    path = settings.project_root(project_id) / "source-report.json"
    write_json(path, report)
    print(path)
    return path


def default_pipeline(settings: Settings, project: dict[str, Any]) -> dict[str, Any]:
    project_id = project["id"]
    book_id = project["book_id"] or project["slug"]
    python = sys.executable
    prefix = [python, "-m", "pocketpolyglot_studio.workflows"]
    stages: list[dict[str, Any]] = []
    if project["workflow"] == "lingualeaf":
        stages.extend(
            [
                {
                    "id": "generate",
                    "title": "Generate multilingual JSON",
                    "argv": prefix + ["lingualeaf-generate", project_id, "--workers", "10", "--model", settings.worker_model, "--reasoning", "low"],
                    "acceptance": [
                        {
                            "type": "json_field",
                            "label": "Manifest coverage complete",
                            "path": str(settings.project_root(project_id) / "generation-status.json"),
                            "field": "complete",
                            "equals": True,
                        }
                    ],
                },
                {
                    "id": "compile",
                    "title": "Compile large-font editions",
                    "argv": prefix + ["lingualeaf-compile", project_id],
                    "acceptance": [{"type": "glob_min", "pattern": f"build/{book_id}/**/*.pdf", "minimum": 2}],
                },
                {
                    "id": "export",
                    "title": "Export maximum-language editions",
                    "argv": [python, "scripts/books/sync_max_language_book_to_nutstore.py", book_id],
                    "acceptance": [],
                },
            ]
        )
    elif project["workflow"] == "pocket_exact":
        stages.append(
            {
                "id": "build",
                "title": "Build exact and pocket TeX",
                "argv": [
                    python,
                    "scripts/books/build_pocket_tex_queue.py",
                    "--book-id",
                    book_id,
                    "--agent-optimize",
                    "--agent-model",
                    settings.worker_model,
                    "--agent-reasoning",
                    "low",
                ],
                "acceptance": [
                    {"type": "path_exists", "path": f"build-pocket/{book_id}/exact/tex/book.tex"},
                    {"type": "path_exists", "path": f"build-pocket/{book_id}/pocket-large-font/book.pdf"},
                ],
            }
        )
    elif project["workflow"] == "pocket_polished":
        stages.extend(
            [
                {
                    "id": "prepare-polish",
                    "title": "Prepare lossless polish tasks",
                    "argv": [python, "scripts/books/prepare_build_pocket_polished.py", "--book-id", book_id],
                    "acceptance": [{"type": "path_exists", "path": f"build-pocket-polished/{book_id}/tasks/manifest.json"}],
                },
                {
                    "id": "polish",
                    "title": "Polish, validate, and assemble",
                    "argv": [
                        python,
                        "scripts/books/run_build_pocket_polished_queue.py",
                        "--book-id",
                        book_id,
                        "--workers",
                        "5",
                        "--model",
                        settings.worker_model,
                        "--reasoning",
                        "low",
                    ],
                    "acceptance": [
                        {
                            "type": "json_field",
                            "path": f"build-pocket-polished/{book_id}/status.json",
                            "field": "status",
                            "equals": "complete",
                        }
                    ],
                },
            ]
        )
    return {"schema_version": 1, "project_id": project_id, "book_id": book_id, "stages": stages}


PREPARATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "project_type", "book_id", "prepared", "manifest_paths", "evidence", "risks"],
    "properties": {
        "summary": {"type": "string"},
        "project_type": {"type": "string", "enum": ["lingualeaf", "pocket_exact", "pocket_polished", "custom"]},
        "book_id": {"type": "string"},
        "prepared": {"type": "boolean"},
        "manifest_paths": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
}


def prepare_project(settings: Settings, database: Database, project_id: str, profile: str) -> Path:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    report_path = inspect_project(settings, database, project_id)
    source_report = json.loads(report_path.read_text(encoding="utf-8"))
    project_root = settings.project_root(project_id)
    schema_path = project_root / "preparation.schema.json"
    prompt_path = project_root / "preparation-prompt.md"
    output_path = project_root / "preparation.json"
    write_json(schema_path, PREPARATION_SCHEMA)
    prompt = f"""You are the preparation agent inside PocketPolyglot Studio for this repository.

Project:
{json.dumps(project, ensure_ascii=False, indent=2)}

Source inspection:
{json.dumps(source_report, ensure_ascii=False, indent=2)}

Prepare this project, but do not start the expensive generation queue. Work at the correct layer:
- For LinguaLeaf, produce or repair source Markdown, book-plan metadata, lossless chunks, and the current manifest using the repository's existing generic scripts.
- For exact pocket TeX, register the source in the build-pocket queue and preserve figures, equations, tables, diagrams, notation, and source-page evidence as first-class content. Never create a facsimile-only result.
- For PocketPolished, verify that the exact source TeX exists and prepare protected lossless polish chunks.
- Reuse established repository conventions and validators. Do not invent book-specific behavior in shared core scripts.
- Do not delete prior JSON, TeX, source files, or generated work. Do not start writers, reviewers, or long tmux queues.
- Validate every file you create. Your final JSON must state concrete manifest paths and evidence. Set prepared=false if the sources are insufficient.
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    reasoning = PROFILE_REASONING.get(profile, "low")
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "-C",
        str(settings.repo_root),
        "-m",
        settings.chat_model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "-c",
        'approval_policy="never"',
        "-s",
        "workspace-write",
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
        "-",
    ]
    process = subprocess.run(
        command,
        cwd=settings.repo_root,
        input=prompt,
        text=True,
        stdout=sys.stdout,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode:
        raise SystemExit(process.returncode)
    try:
        preparation = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Codex did not return valid preparation JSON: {error}")
    if not preparation.get("prepared"):
        raise SystemExit("Preparation agent reported that the project is not ready; inspect preparation.json")
    write_json(project_root / "pipeline.json", default_pipeline(settings, project))
    database.update_project(project_id, {"status": "prepared"})
    print(output_path)
    return output_path


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def lingualeaf_report(settings: Settings, project: dict[str, Any]) -> dict[str, Any]:
    book_id = project["book_id"] or project["slug"]
    plan_path = settings.repo_root / "books" / book_id / "book-plan.json"
    if not plan_path.exists():
        return {"complete": False, "error": f"Missing {plan_path}"}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = plan.get("chunks_manifest") or plan.get("manifest")
    chunks_jsonl = plan.get("chunks_jsonl")
    chunk_dir = plan.get("raw_chunk_dir")
    if not manifest or not chunk_dir:
        return {"complete": False, "error": "book-plan.json lacks manifest or raw_chunk_dir"}
    classical = project["primary_language"] == "wenyan" or project["source_language"] == "wenyan"
    if classical:
        argv = [
            sys.executable,
            "scripts/interlinear/report_quadrilingual_progress.py",
            "--manifest",
            manifest,
            "--chunks-jsonl",
            chunks_jsonl,
            "--chunk-dir",
            chunk_dir,
        ]
    else:
        argv = [
            sys.executable,
            "scripts/interlinear/report_trilingual_progress.py",
            "--manifest",
            manifest,
            "--chunk-dir",
            chunk_dir,
        ]
    code, output = run_capture(argv, cwd=settings.repo_root, timeout=300)
    values = parse_key_values(output)
    if classical:
        total = int(values.get("manifest_chunks") or values.get("total") or 0)
        valid = int(values.get("valid_chunks") or values.get("valid") or 0)
        missing = int(values.get("missing_chunks") or values.get("missing") or max(0, total - valid))
        stale = int(values.get("stale_chunks") or values.get("stale") or 0)
    else:
        total = int(values.get("manifest_chunks") or 0)
        valid = int(values.get("valid_chunks") or 0)
        missing = int(values.get("missing_chunks") or max(0, total - valid))
        stale = int(values.get("stale_chunks") or 0)
    return {
        "complete": bool(total and valid == total and missing == 0 and stale == 0),
        "total": total,
        "valid": valid,
        "missing": missing,
        "stale": stale,
        "returncode": code,
        "raw": output[-4000:],
    }


def tmux_exists(session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", f"={session}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def generate_lingualeaf(
    settings: Settings,
    database: Database,
    project_id: str,
    workers: int,
    model: str,
    reasoning: str,
) -> int:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    book_id = project["book_id"] or project["slug"]
    session = f"pps-{project['slug'][:24]}-writer"
    status_path = settings.project_root(project_id) / "generation-status.json"
    initial = lingualeaf_report(settings, project)
    write_json(status_path, initial | {"updated_at": utc_now()})
    if initial["complete"]:
        return 0
    classical = project["primary_language"] == "wenyan" or project["source_language"] == "wenyan"
    launcher = (
        "scripts/interlinear/start_quadrilingual_wenyan_tmux.sh"
        if classical
        else "scripts/interlinear/start_trilingual_book_tmux.sh"
    )
    if not tmux_exists(session):
        environment = os.environ.copy()
        environment.update(
            {
                "WORKERS": str(workers),
                "MODEL": model,
                "REASONING": reasoning,
                "RETRY_FAILED": "1",
                "START_AUTOREPAIR_COMPANION": "1",
            }
        )
        process = subprocess.run(
            ["bash", launcher, book_id, session],
            cwd=settings.repo_root,
            env=environment,
            check=False,
        )
        if process.returncode:
            return process.returncode
    while True:
        report = lingualeaf_report(settings, project)
        write_json(status_path, report | {"updated_at": utc_now(), "session": session})
        print(
            f"{book_id}: valid={report.get('valid', 0)}/{report.get('total', 0)} "
            f"missing={report.get('missing', 0)} stale={report.get('stale', 0)}",
            flush=True,
        )
        if report["complete"]:
            return 0
        if not tmux_exists(session):
            print("Writer session ended before complete coverage; autorepair evidence is in the book work directory.")
            return 1
        time.sleep(60)


def compile_lingualeaf(settings: Settings, database: Database, project_id: str) -> int:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    report = lingualeaf_report(settings, project)
    if not report["complete"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    book_id = project["book_id"] or project["slug"]
    classical = project["primary_language"] == "wenyan" or project["source_language"] == "wenyan"
    if classical:
        argv = [sys.executable, "scripts/interlinear/finalize_classical_max_language.py", "--book-id", book_id]
    else:
        argv = ["bash", "scripts/interlinear/finalize_trilingual_book_after_complete.sh", book_id, ""]
    return subprocess.run(argv, cwd=settings.repo_root, check=False).returncode


def valid_pdf(path: Path) -> tuple[bool, str]:
    if not path.is_file() or path.stat().st_size < 1024:
        return False, f"missing or too small: {path}"
    code, output = run_capture(["pdfinfo", str(path)], cwd=path.parent)
    return code == 0 and "Pages:" in output, output[-1000:]


def validate_project(settings: Settings, database: Database, project_id: str) -> Path:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    book_id = project["book_id"] or project["slug"]
    checks: list[dict[str, Any]] = []
    if project["workflow"] == "lingualeaf":
        progress = lingualeaf_report(settings, project)
        checks.append({"label": "Current manifest coverage", "passed": bool(progress.get("complete")), "detail": progress})
        pdfs = sorted((settings.repo_root / "build" / book_id).rglob("*.pdf")) if (settings.repo_root / "build" / book_id).exists() else []
        checks.append({"label": "Color and black-white outputs", "passed": len(pdfs) >= 2, "detail": [str(path) for path in pdfs[:20]]})
    elif project["workflow"] == "pocket_exact":
        exact_tex = settings.repo_root / "build-pocket" / book_id / "exact/tex/book.tex"
        pocket_tex = settings.repo_root / "build-pocket" / book_id / "pocket-large-font/tex/book.tex"
        checks.append({"label": "Exact real TeX", "passed": exact_tex.is_file() and exact_tex.stat().st_size > 1000, "detail": str(exact_tex)})
        checks.append({"label": "Pocket real TeX", "passed": pocket_tex.is_file() and pocket_tex.stat().st_size > 1000, "detail": str(pocket_tex)})
        for label, path in (
            ("Exact PDF", settings.repo_root / "build-pocket" / book_id / "exact/book.pdf"),
            ("Pocket PDF", settings.repo_root / "build-pocket" / book_id / "pocket-large-font/book.pdf"),
        ):
            passed, detail = valid_pdf(path)
            checks.append({"label": label, "passed": passed, "detail": detail})
    elif project["workflow"] == "pocket_polished":
        status_path = settings.repo_root / "build-pocket-polished" / book_id / "status.json"
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}
        checks.append({"label": "Polished assembly status", "passed": status.get("status") == "complete", "detail": status})
        pdfs = sorted((settings.repo_root / "build-pocket-polished" / book_id).rglob("*.pdf")) if (settings.repo_root / "build-pocket-polished" / book_id).exists() else []
        pdf_results = [valid_pdf(path)[0] for path in pdfs]
        checks.append({"label": "Readable polished PDF", "passed": bool(pdfs) and all(pdf_results), "detail": [str(path) for path in pdfs]})
    else:
        pipeline_path = settings.project_root(project_id) / "pipeline.json"
        checks.append({"label": "Executable project pipeline", "passed": pipeline_path.is_file(), "detail": str(pipeline_path)})
    report = {
        "schema_version": 1,
        "project_id": project_id,
        "book_id": book_id,
        "generated_at": utc_now(),
        "accepted": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
    }
    path = settings.project_root(project_id) / "validation.json"
    write_json(path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return path


def generate_cover(
    settings: Settings,
    database: Database,
    project_id: str,
    reasoning: str,
) -> int:
    project = database.get_project(project_id)
    if not project:
        raise SystemExit(f"Unknown project: {project_id}")
    book_id = project["book_id"] or project["slug"]
    cover_root = settings.repo_root / "assets" / "covers" / book_id
    cover_root.mkdir(parents=True, exist_ok=True)
    cover_path = cover_root / "cover.png"
    if cover_path.exists():
        shutil.copy2(cover_path, settings.project_root(project_id) / "cover-before-generation.png")
    prompt = f"""Create the final textless cover artwork for this PocketPolyglot project.

Project metadata:
{json.dumps(project, ensure_ascii=False, indent=2)}

Use the installed image generation skill/tool. Inspect the project's source metadata or representative content first so the concept reflects the actual book. Generate one elegant portrait cover background at approximately 1536x2165 pixels and save it exactly as:
{cover_path}

Hard requirements:
- The bitmap must contain no title, subtitle, author name, letters, words, numerals, logos, seals, stamps, watermarks, or pseudo-writing in any language.
- Keep the composition calm, high-end, legible behind later vertical or centered title overlays, and specific to the book's subject.
- Do not compose title text into this image. Existing deterministic TeX/cover scripts add correct multilingual titles later.
- Do not edit other cover files, book JSON, TeX, or PDFs.
- Verify the saved PNG exists, is portrait, and is at least 1000 pixels wide before finishing.
"""
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "-C",
        str(settings.repo_root),
        "-m",
        settings.chat_model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "-c",
        'approval_policy="never"',
        "-s",
        "workspace-write",
        "-",
    ]
    process = subprocess.run(
        command,
        cwd=settings.repo_root,
        input=prompt,
        text=True,
        stdout=sys.stdout,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return process.returncode


def repository_relative_path(settings: Settings, value: str) -> Path:
    path = (settings.repo_root / value).resolve()
    if settings.repo_root not in path.parents:
        raise SystemExit(f"Path must stay inside the repository: {value}")
    return path


def run_pocket_polish_queue(
    settings: Settings,
    *,
    source_queue_value: str,
    queue_value: str,
    status_value: str,
    workers: int,
    model: str,
    reasoning: str,
    adaptive: bool,
    network_limit_mbps: float,
) -> int:
    """Prepare and execute one evidence-gated technical polish queue."""

    source_queue = repository_relative_path(settings, source_queue_value)
    prepared_queue = repository_relative_path(settings, queue_value)
    status = repository_relative_path(settings, status_value)
    if not source_queue.is_file():
        raise SystemExit(f"Missing source queue: {source_queue}")
    payload = json.loads(source_queue.read_text(encoding="utf-8"))
    book_ids = [
        str(task["book_id"])
        for task in payload.get("tasks", [])
        if isinstance(task, dict) and task.get("book_id")
    ]
    if not book_ids:
        raise SystemExit(f"Source queue contains no books: {source_queue}")

    # Preserve valid historical language work before a schema upgrade or
    # content-addressed rechunk changes the current task identifiers.
    migration = subprocess.run(
        [
            sys.executable,
            "-u",
            "scripts/books/migrate_reviewed_pocket_polish_segments.py",
            *book_ids,
        ],
        cwd=settings.repo_root,
        check=False,
    )
    if migration.returncode:
        return migration.returncode

    preparation = subprocess.run(
        [
            sys.executable,
            "-u",
            "scripts/books/prepare_build_pocket_polished.py",
            "--queue",
            str(source_queue),
            "--output-queue",
            str(prepared_queue),
            "--max-chars",
            "7000",
            "--max-segments",
            "16",
        ],
        cwd=settings.repo_root,
        check=False,
    )
    if preparation.returncode:
        return preparation.returncode

    command = [
        sys.executable,
        "-u",
        "scripts/books/run_build_pocket_polished_queue.py",
        "--queue",
        str(prepared_queue),
        "--status",
        str(status),
        "--workers",
        str(max(1, workers)),
        "--model",
        model,
        "--reasoning",
        reasoning,
        "--retries",
        "2",
        "--review-retries",
        "2",
        "--retry-passes",
        "2",
        "--network-limit-mbps",
        str(network_limit_mbps),
        "--cover-reasoning",
        "low",
    ]
    if not adaptive:
        command.append("--no-adaptive")
    return subprocess.run(command, cwd=settings.repo_root, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="PocketPolyglot Studio workflow adapters.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("project_id")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("project_id")
    prepare_parser.add_argument("--profile", default="fast", choices=["fast", "balanced", "deep", "ultra"])
    generate_parser = subparsers.add_parser("lingualeaf-generate")
    generate_parser.add_argument("project_id")
    generate_parser.add_argument("--workers", type=int, default=10)
    generate_parser.add_argument("--model", default="gpt-5.6-sol")
    generate_parser.add_argument("--reasoning", default="low")
    compile_parser = subparsers.add_parser("lingualeaf-compile")
    compile_parser.add_argument("project_id")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("project_id")
    cover_parser = subparsers.add_parser("cover")
    cover_parser.add_argument("project_id")
    cover_parser.add_argument("--reasoning", default="medium", choices=["low", "medium", "high"])
    polish_queue_parser = subparsers.add_parser("pocket-polish-queue")
    polish_queue_parser.add_argument("--source-queue", required=True)
    polish_queue_parser.add_argument("--queue", required=True)
    polish_queue_parser.add_argument("--status", required=True)
    polish_queue_parser.add_argument("--workers", type=int, default=5)
    polish_queue_parser.add_argument("--model", default="gpt-5.6-sol")
    polish_queue_parser.add_argument("--reasoning", default="low", choices=["low", "medium", "high", "xhigh"])
    polish_queue_parser.add_argument("--network-limit-mbps", type=float, default=100.0)
    polish_queue_parser.add_argument(
        "--adaptive",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    settings = Settings.load()
    database = Database(settings.database_path)
    if args.command == "inspect":
        inspect_project(settings, database, args.project_id)
        return 0
    if args.command == "prepare":
        prepare_project(settings, database, args.project_id, args.profile)
        return 0
    if args.command == "lingualeaf-generate":
        return generate_lingualeaf(settings, database, args.project_id, args.workers, args.model, args.reasoning)
    if args.command == "lingualeaf-compile":
        return compile_lingualeaf(settings, database, args.project_id)
    if args.command == "validate":
        report = validate_project(settings, database, args.project_id)
        return 0 if json.loads(report.read_text(encoding="utf-8"))["accepted"] else 1
    if args.command == "cover":
        return generate_cover(settings, database, args.project_id, args.reasoning)
    if args.command == "pocket-polish-queue":
        return run_pocket_polish_queue(
            settings,
            source_queue_value=args.source_queue,
            queue_value=args.queue,
            status_value=args.status,
            workers=args.workers,
            model=args.model,
            reasoning=args.reasoning,
            adaptive=args.adaptive,
            network_limit_mbps=args.network_limit_mbps,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
