from __future__ import annotations

import os
import json
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capabilities import build_job_spec
from .config import Settings
from .db import Database, utc_now


def tmux_exists(session: str) -> bool:
    if not session:
        return False
    return subprocess.run(
        ["tmux", "has-session", "-t", f"={session}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


class JobManager:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database

    def launch(
        self,
        project: dict[str, Any],
        capability_id: str,
        parameters: dict[str, Any],
        *,
        retry_of: str | None = None,
    ) -> dict[str, Any]:
        spec = build_job_spec(self.settings, project, capability_id, parameters)
        draft = self.database.create_job(
            {
                "project_id": project["id"],
                "capability_id": capability_id,
                "title": spec.title,
                "command": spec.command,
                "environment": spec.environment,
                "acceptance": spec.acceptance,
                "retry_of": retry_of,
            }
        )
        job_id = draft["id"]
        session = f"pps-{job_id[:12]}"
        log_path = self.settings.job_root(job_id) / "job.log"
        self.database.update_job(
            job_id,
            {"tmux_session": session, "log_path": str(log_path), "status": "launching"},
        )
        runner_environment = {
            "POCKETPOLYGLOT_ROOT": str(self.settings.repo_root),
            "POCKETPOLYGLOT_STATE": str(self.settings.state_root),
            "PYTHONPATH": str(self.settings.repo_root / "studio"),
        }
        runner = [
            "env",
            *(f"{key}={value}" for key, value in runner_environment.items()),
            sys.executable,
            "-m",
            "pocketpolyglot_studio.runner",
            "--job-id",
            job_id,
        ]
        environment = os.environ.copy()
        environment.update(runner_environment)
        shell_command = "exec " + shlex.join(runner)
        process = subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session,
                "-n",
                "job",
                "-c",
                str(self.settings.repo_root),
                shell_command,
            ],
            cwd=self.settings.repo_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if process.returncode:
            self.database.update_job(
                job_id,
                {
                    "status": "failed",
                    "error": process.stdout.strip(),
                    "finished_at": utc_now(),
                    "exit_code": process.returncode,
                },
            )
            self.database.add_event(job_id, "launch_failed", {"output": process.stdout})
            raise RuntimeError(process.stdout.strip() or "tmux launch failed")
        self.database.add_event(job_id, "launched", {"session": session, "command": spec.command})
        return self.database.get_job(job_id)  # type: ignore[return-value]

    def reconcile(self, job: dict[str, Any]) -> dict[str, Any]:
        if job["status"] not in {"launching", "running", "cancelling"}:
            return job
        if tmux_exists(job.get("tmux_session", "")):
            return job
        heartbeat = job.get("heartbeat_at")
        if heartbeat:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat)).total_seconds()
            except ValueError:
                age = 999
            if age < 20:
                return job
        updated = self.database.update_job(
            job["id"],
            {
                "status": "interrupted",
                "error": "Runner tmux session ended without writing a final state.",
                "finished_at": utc_now(),
            },
        )
        self.database.add_event(job["id"], "interrupted", {"session": job.get("tmux_session", "")})
        return updated or job

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self.database.get_job(job_id)
        if not job:
            return None
        job = self.reconcile(job)
        progress_path_value = job.get("environment", {}).get(
            "POCKETPOLYGLOT_PROGRESS_PATH", ""
        )
        if progress_path_value:
            try:
                job["progress_detail"] = json.loads(
                    Path(progress_path_value).read_text(encoding="utf-8")
                )
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                pass
        return job

    def list(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return [self.reconcile(job) for job in self.database.list_jobs(project_id, limit)]

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.database.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        session = job.get("tmux_session", "")
        self.database.update_job(job_id, {"status": "cancelling"})
        child_pid = job.get("pid")
        if child_pid:
            try:
                os.killpg(int(child_pid), signal.SIGTERM)
                time.sleep(0.4)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
        if tmux_exists(session):
            subprocess.run(["tmux", "send-keys", "-t", f"={session}", "C-c"], check=False)
            subprocess.run(["tmux", "kill-session", "-t", f"={session}"], check=False)
        self.database.update_job(
            job_id,
            {"status": "cancelled", "finished_at": utc_now(), "error": "Cancelled by user"},
        )
        self.database.add_event(job_id, "cancelled", {})
        return self.database.get_job(job_id)  # type: ignore[return-value]

    def retry(self, job_id: str) -> dict[str, Any]:
        job = self.database.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        project = self.database.get_project(job["project_id"])
        if not project:
            raise ValueError("The original project no longer exists")
        spec_job = self.database.create_job(
            {
                "project_id": project["id"],
                "capability_id": job["capability_id"],
                "title": f"Retry: {job['title']}",
                "command": job["command"],
                "environment": job["environment"],
                "acceptance": job["acceptance"],
                "retry_of": job_id,
            }
        )
        new_id = spec_job["id"]
        session = f"pps-{new_id[:12]}"
        log_path = self.settings.job_root(new_id) / "job.log"
        self.database.update_job(new_id, {"tmux_session": session, "log_path": str(log_path), "status": "launching"})
        runner = [
            "env",
            f"POCKETPOLYGLOT_ROOT={self.settings.repo_root}",
            f"POCKETPOLYGLOT_STATE={self.settings.state_root}",
            f"PYTHONPATH={self.settings.repo_root / 'studio'}",
            sys.executable,
            "-m",
            "pocketpolyglot_studio.runner",
            "--job-id",
            new_id,
        ]
        environment = os.environ.copy()
        environment.update(job["environment"])
        process = subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session,
                "-n",
                "job",
                "-c",
                str(self.settings.repo_root),
                "exec " + shlex.join(runner),
            ],
            cwd=self.settings.repo_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if process.returncode:
            self.database.update_job(new_id, {"status": "failed", "error": process.stdout, "finished_at": utc_now()})
            raise RuntimeError(process.stdout.strip())
        self.database.add_event(new_id, "retried", {"retry_of": job_id})
        return self.database.get_job(new_id)  # type: ignore[return-value]
