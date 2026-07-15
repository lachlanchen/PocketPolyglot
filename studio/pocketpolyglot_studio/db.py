from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    result: list[str] = []
    separator = False
    for char in value:
        if char.isalnum() or ord(char) > 127:
            result.append(char)
            separator = False
        elif not separator:
            result.append("-")
            separator = True
    return "".join(result).strip("-") or f"project-{uuid.uuid4().hex[:8]}"


JSON_COLUMNS = {
    "target_languages",
    "metadata",
    "command",
    "environment",
    "acceptance",
    "payload",
}


def decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in JSON_COLUMNS:
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                pass
    return result


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            workflow TEXT NOT NULL,
            book_id TEXT NOT NULL DEFAULT '',
            primary_language TEXT NOT NULL DEFAULT 'en',
            source_language TEXT NOT NULL DEFAULT 'en',
            target_languages TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'reference',
            language TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(project_id, path)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            capability_id TEXT NOT NULL,
            title TEXT NOT NULL,
            command TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT '{}',
            acceptance TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'queued',
            tmux_session TEXT NOT NULL DEFAULT '',
            log_path TEXT NOT NULL DEFAULT '',
            pid INTEGER,
            exit_code INTEGER,
            progress REAL NOT NULL DEFAULT 0,
            retry_of TEXT,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            heartbeat_at TEXT,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            check_type TEXT NOT NULL,
            label TEXT NOT NULL,
            passed INTEGER NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            artifact_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
            job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            path TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(project_id, path)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            reasoning TEXT NOT NULL DEFAULT '',
            thread_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_project_created ON jobs(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_job_id ON job_events(job_id, id);
        CREATE INDEX IF NOT EXISTS idx_messages_project_created ON messages(project_id, created_at);
        """
        with self.connect() as connection:
            connection.executescript(schema)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = payload.get("id") or uuid.uuid4().hex
        title = payload["title"].strip()
        base_slug = slugify(payload.get("slug") or payload.get("book_id") or title)
        slug = base_slug
        suffix = 2
        while self.get_project_by_slug(slug):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects
                (id, slug, title, workflow, book_id, primary_language, source_language,
                 target_languages, metadata, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    slug,
                    title,
                    payload.get("workflow", "lingualeaf"),
                    payload.get("book_id", base_slug),
                    payload.get("primary_language", payload.get("source_language", "en")),
                    payload.get("source_language", "en"),
                    self._json(payload.get("target_languages", ["ja", "zh"])),
                    self._json(payload.get("metadata", {})),
                    payload.get("status", "draft"),
                    now,
                    now,
                ),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return decode_row(row)

    def get_project_by_slug(self, slug: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        return decode_row(row)

    def update_project(self, project_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "title",
            "workflow",
            "book_id",
            "primary_language",
            "source_language",
            "target_languages",
            "metadata",
            "status",
        }
        values: list[Any] = []
        clauses: list[str] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            clauses.append(f"{key} = ?")
            values.append(self._json(value) if key in {"target_languages", "metadata"} else value)
        if not clauses:
            return self.get_project(project_id)
        clauses.append("updated_at = ?")
        values.extend((utc_now(), project_id))
        with self.connect() as connection:
            connection.execute(f"UPDATE projects SET {', '.join(clauses)} WHERE id = ?", values)
        return self.get_project(project_id)

    def add_source(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO sources
                (id, project_id, path, role, language, media_type, size_bytes, sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    project_id,
                    payload["path"],
                    payload.get("role", "reference"),
                    payload.get("language", ""),
                    payload.get("media_type", ""),
                    payload.get("size_bytes", 0),
                    payload.get("sha256", ""),
                    utc_now(),
                ),
            )
        return self.get_source(source_id)  # type: ignore[return-value]

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return decode_row(row)

    def list_sources(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sources WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = payload.get("id") or uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                (id, project_id, capability_id, title, command, environment, acceptance,
                 status, tmux_session, log_path, progress, retry_of, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    payload.get("project_id"),
                    payload["capability_id"],
                    payload["title"],
                    self._json(payload["command"]),
                    self._json(payload.get("environment", {})),
                    self._json(payload.get("acceptance", [])),
                    payload.get("status", "queued"),
                    payload.get("tmux_session", ""),
                    payload.get("log_path", ""),
                    payload.get("progress", 0),
                    payload.get("retry_of"),
                    utc_now(),
                ),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return decode_row(row)

    def list_jobs(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def update_job(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "status",
            "tmux_session",
            "log_path",
            "pid",
            "exit_code",
            "progress",
            "error",
            "started_at",
            "heartbeat_at",
            "finished_at",
        }
        clauses: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            if key in allowed:
                clauses.append(f"{key} = ?")
                values.append(value)
        if not clauses:
            return self.get_job(job_id)
        values.append(job_id)
        with self.connect() as connection:
            connection.execute(f"UPDATE jobs SET {', '.join(clauses)} WHERE id = ?", values)
        return self.get_job(job_id)

    def add_event(self, job_id: str, kind: str, payload: dict[str, Any] | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO job_events(job_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (job_id, kind, self._json(payload or {}), utc_now()),
            )
        return int(cursor.lastrowid)

    def list_events(self, job_id: str, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? AND id > ? ORDER BY id LIMIT ?",
                (job_id, after_id, limit),
            ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def clear_evidence(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM evidence WHERE job_id = ?", (job_id,))

    def add_evidence(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        evidence_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence
                (id, job_id, check_type, label, passed, detail, artifact_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    job_id,
                    payload["check_type"],
                    payload["label"],
                    int(bool(payload["passed"])),
                    payload.get("detail", ""),
                    payload.get("artifact_path", ""),
                    utc_now(),
                ),
            )
        return payload | {"id": evidence_id, "job_id": job_id}

    def list_evidence(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence WHERE job_id = ? ORDER BY created_at", (job_id,)
            ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def add_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO artifacts
                (id, project_id, job_id, kind, label, path, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    payload.get("project_id"),
                    payload.get("job_id"),
                    payload.get("kind", "file"),
                    payload.get("label", Path(payload["path"]).name),
                    payload["path"],
                    self._json(payload.get("metadata", {})),
                    utc_now(),
                ),
            )
        return payload | {"id": artifact_id}

    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def add_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        message_id = uuid.uuid4().hex
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages
                (id, project_id, role, content, model, reasoning, thread_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    payload.get("project_id"),
                    payload["role"],
                    payload["content"],
                    payload.get("model", ""),
                    payload.get("reasoning", ""),
                    payload.get("thread_id", ""),
                    now,
                ),
            )
        return payload | {"id": message_id, "created_at": now}

    def list_messages(self, project_id: str, limit: int = 40) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages WHERE project_id = ? ORDER BY created_at DESC LIMIT ?
                ) ORDER BY created_at
                """,
                (project_id, limit),
            ).fetchall()
        return [decode_row(row) for row in rows if row is not None]  # type: ignore[misc]

    def execute(self, sql: str, values: Iterable[Any] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, tuple(values))
