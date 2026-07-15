from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .capabilities import list_capabilities
from .codex_backend import stream_chat
from .config import Settings
from .db import Database
from .discovery import discover_repository
from .jobs import JobManager
from .schemas import ChatRequest, JobLaunch, PipelineUpdate, ProjectCreate, ProjectUpdate, SourceRegister
from .workflows import default_pipeline, write_json


settings = Settings.load()
database = Database(settings.database_path)
jobs = JobManager(settings, database)
app = FastAPI(title="PocketPolyglot Studio", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_project(project_id: str) -> dict[str, Any]:
    project = database.get_project(project_id)
    if not project:
        raise HTTPException(404, f"Unknown project: {project_id}")
    return project


def safe_local_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    allowed_roots = [settings.repo_root, settings.state_root, Path.home() / "Nutstore Files"]
    if not any(path == root or root in path.parents for root in allowed_roots):
        raise HTTPException(403, "Path is outside the Studio's allowed local roots")
    return path


@app.get("/api/health")
def health() -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for command in ("codex", "tmux", "xelatex", "pdftotext", "pdfinfo"):
        path = shutil.which(command)
        tools[command] = {"available": bool(path), "path": path or ""}
    codex_version = ""
    if tools["codex"]["available"]:
        process = subprocess.run(
            ["codex", "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )
        codex_version = process.stdout.strip()
    return {
        "status": "ok",
        "version": __version__,
        "repo_root": str(settings.repo_root),
        "state_root": str(settings.state_root),
        "chat_model": settings.chat_model,
        "default_reasoning": settings.default_reasoning,
        "codex_version": codex_version,
        "tools": tools,
    }


@app.get("/api/capabilities")
def capabilities() -> list[dict[str, Any]]:
    return list_capabilities()


@app.get("/api/repository")
def repository() -> dict[str, Any]:
    return discover_repository(settings.repo_root)


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return database.list_projects()


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    project = database.create_project(payload.model_dump())
    write_json(settings.project_root(project["id"]) / "pipeline.json", default_pipeline(settings, project))
    return project


@app.post("/api/projects/import/{book_id}", status_code=201)
def import_project(book_id: str) -> dict[str, Any]:
    existing = next((item for item in database.list_projects() if item["book_id"] == book_id), None)
    if existing:
        return existing
    discovered = next(
        (item for item in discover_repository(settings.repo_root)["books"] if item["book_id"] == book_id), None
    )
    if not discovered:
        raise HTTPException(404, f"No existing book workflow found for {book_id}")
    project = database.create_project(
        {
            "title": discovered["title"],
            "book_id": book_id,
            "workflow": discovered["workflow"],
            "status": "ready" if discovered["complete"] else "active",
            "metadata": {"imported": True, "manifest": discovered["manifest"]},
        }
    )
    write_json(settings.project_root(project["id"]) / "pipeline.json", default_pipeline(settings, project))
    return project


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = require_project(project_id)
    pipeline_path = settings.project_root(project_id) / "pipeline.json"
    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8")) if pipeline_path.exists() else {}
    return project | {
        "sources": database.list_sources(project_id),
        "jobs": jobs.list(project_id, 30),
        "artifacts": database.list_artifacts(project_id),
        "messages": database.list_messages(project_id, 50),
        "pipeline": pipeline,
    }


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate) -> dict[str, Any]:
    require_project(project_id)
    updates = payload.model_dump(exclude_none=True)
    project = database.update_project(project_id, updates)
    if not project:
        raise HTTPException(404)
    return project


@app.put("/api/projects/{project_id}/pipeline")
def update_pipeline(project_id: str, payload: PipelineUpdate) -> dict[str, Any]:
    require_project(project_id)
    pipeline = payload.pipeline
    if pipeline.get("schema_version") != 1 or not isinstance(pipeline.get("stages"), list):
        raise HTTPException(422, "pipeline must use schema_version 1 and contain a stages array")
    path = settings.project_root(project_id) / "pipeline.json"
    write_json(path, pipeline)
    return pipeline


@app.post("/api/projects/{project_id}/sources", status_code=201)
def register_source(project_id: str, payload: SourceRegister) -> dict[str, Any]:
    require_project(project_id)
    path = Path(payload.path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(422, f"Source file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return database.add_source(
        project_id,
        {
            "path": str(path),
            "role": payload.role,
            "language": payload.language,
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        },
    )


@app.put("/api/projects/{project_id}/uploads/{filename}", status_code=201)
async def upload_source(project_id: str, filename: str, request: Request) -> dict[str, Any]:
    require_project(project_id)
    clean_name = Path(filename).name
    if not clean_name:
        raise HTTPException(422, "Invalid filename")
    target_root = settings.uploads_root / project_id
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / clean_name
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as handle:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            digest.update(chunk)
            handle.write(chunk)
    return database.add_source(
        project_id,
        {
            "path": str(target),
            "role": request.headers.get("x-source-role", "reference"),
            "language": request.headers.get("x-source-language", ""),
            "media_type": request.headers.get("content-type", "application/octet-stream"),
            "size_bytes": size,
            "sha256": digest.hexdigest(),
        },
    )


@app.post("/api/projects/{project_id}/jobs", status_code=201)
def launch_job(project_id: str, payload: JobLaunch) -> dict[str, Any]:
    project = require_project(project_id)
    try:
        return jobs.launch(project, payload.capability_id, payload.parameters)
    except KeyError as error:
        raise HTTPException(404, f"Unknown capability: {error.args[0]}") from error
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/jobs")
def list_jobs(project_id: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return jobs.list(project_id, limit)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    return job | {"evidence": database.list_evidence(job_id)}


@app.get("/api/jobs/{job_id}/log")
def get_job_log(job_id: str, tail: int = Query(400, ge=1, le=5000)) -> PlainTextResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    path = Path(job["log_path"])
    if not path.exists():
        return PlainTextResponse("")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return PlainTextResponse("\n".join(lines[-tail:]))


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        return jobs.cancel(job_id)
    except KeyError as error:
        raise HTTPException(404) from error


@app.post("/api/jobs/{job_id}/retry", status_code=201)
def retry_job(job_id: str) -> dict[str, Any]:
    try:
        return jobs.retry(job_id)
    except KeyError as error:
        raise HTTPException(404) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, after: int = 0) -> StreamingResponse:
    if not database.get_job(job_id):
        raise HTTPException(404)

    async def events():
        cursor = after
        idle = 0
        while True:
            rows = database.list_events(job_id, cursor)
            if rows:
                idle = 0
                for row in rows:
                    cursor = row["id"]
                    yield f"id: {cursor}\nevent: {row['kind']}\ndata: {json.dumps(row, ensure_ascii=False)}\n\n"
            else:
                idle += 1
                if idle % 15 == 0:
                    yield ": keepalive\n\n"
            job = database.get_job(job_id)
            if job and job["status"] in {"complete", "blocked", "failed", "cancelled", "interrupted"} and not rows:
                break
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    project = require_project(payload.project_id)

    async def events():
        try:
            async for event in stream_chat(
                settings,
                database,
                project,
                payload.message,
                payload.profile,
                payload.agent_mode,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as error:
            yield f"data: {json.dumps({'type': 'error', 'text': str(error)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/covers/{book_id}")
def cover(book_id: str) -> FileResponse:
    path = settings.repo_root / "assets" / "covers" / Path(book_id).name / "cover.png"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


@app.get("/api/files")
def local_file(path: str) -> FileResponse:
    target = safe_local_path(path)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


if settings.web_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
else:
    @app.get("/")
    def missing_frontend() -> JSONResponse:
        return JSONResponse(
            {
                "studio": "PocketPolyglot Studio",
                "message": "Frontend is not built. Run: cd studio/web && npm install && npm run build",
                "api": "/docs",
            }
        )
