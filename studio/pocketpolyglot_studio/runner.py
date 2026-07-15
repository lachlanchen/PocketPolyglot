from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import Settings
from .db import Database, utc_now
from .evidence import evaluate_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one durable PocketPolyglot Studio job.")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    settings = Settings.load()
    database = Database(settings.database_path)
    job = database.get_job(args.job_id)
    if not job:
        print(f"Unknown job: {args.job_id}", file=sys.stderr)
        return 2

    log_path = Path(job["log_path"] or settings.job_root(job["id"]) / "job.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in job["environment"].items()})
    command = [str(item) for item in job["command"]]
    database.update_job(
        job["id"],
        {"status": "running", "started_at": utc_now(), "heartbeat_at": utc_now(), "log_path": str(log_path)},
    )
    database.add_event(job["id"], "started", {"command": command})

    interrupted = False
    child: subprocess.Popen[str] | None = None

    def stop_child(_signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True
        if child and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)

    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        log.write(f"[{utc_now()}] command: {command!r}\n")
        try:
            child = subprocess.Popen(
                command,
                cwd=settings.repo_root,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            database.update_job(job["id"], {"pid": child.pid})
            while child.poll() is None:
                database.update_job(job["id"], {"heartbeat_at": utc_now()})
                database.add_event(job["id"], "heartbeat", {"pid": child.pid})
                time.sleep(5)
            exit_code = int(child.returncode or 0)
        except Exception as error:
            log.write(f"[{utc_now()}] runner error: {error}\n")
            exit_code = 127
            database.update_job(job["id"], {"error": str(error)})

    if interrupted:
        database.update_job(
            job["id"],
            {"status": "cancelled", "exit_code": exit_code, "finished_at": utc_now(), "heartbeat_at": utc_now()},
        )
        database.add_event(job["id"], "cancelled", {"exit_code": exit_code})
        return 130

    database.clear_evidence(job["id"])
    evidence = evaluate_all(settings.repo_root, job["acceptance"], exit_code)
    for item in evidence:
        saved = database.add_evidence(job["id"], item)
        artifact_path = item.get("artifact_path")
        if artifact_path and job.get("project_id"):
            path = Path(artifact_path)
            database.add_artifact(
                {
                    "project_id": job["project_id"],
                    "job_id": job["id"],
                    "kind": "pdf" if path.suffix.casefold() == ".pdf" else "file",
                    "label": item["label"],
                    "path": str(path),
                    "metadata": {"evidence_id": saved["id"]},
                }
            )
    accepted = all(item["passed"] for item in evidence)
    status = "complete" if accepted else "blocked"
    error = "" if accepted else "Command finished, but required acceptance evidence did not pass."
    database.update_job(
        job["id"],
        {
            "status": status,
            "exit_code": exit_code,
            "progress": 1 if accepted else 0,
            "error": error,
            "heartbeat_at": utc_now(),
            "finished_at": utc_now(),
        },
    )
    database.add_event(job["id"], status, {"exit_code": exit_code, "evidence": evidence})
    if job.get("project_id"):
        database.update_project(job["project_id"], {"status": "ready" if accepted else "attention"})
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
