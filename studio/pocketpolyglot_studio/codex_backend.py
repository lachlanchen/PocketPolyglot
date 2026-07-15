from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from .config import Settings
from .db import Database
from .jobs import JobManager
from .model_router import ModelChoice, choose_model


@lru_cache(maxsize=1)
def workspace_sandbox_probe() -> tuple[bool, str]:
    """Check whether Codex's Bubblewrap network namespace can start on this host."""
    bubblewrap = shutil.which("bwrap")
    if not bubblewrap:
        return True, "Bubblewrap is not installed; defer sandbox selection to Codex."
    try:
        result = subprocess.run(
            [
                bubblewrap,
                "--unshare-net",
                "--ro-bind",
                "/",
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "/bin/true",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"Bubblewrap probe failed: {error}"
    detail = (result.stderr or result.stdout).strip()
    return result.returncode == 0, detail or f"Bubblewrap exited {result.returncode}."


def chat_sandbox(settings: Settings, agent_mode: bool) -> tuple[str, str]:
    if not agent_mode:
        return "read-only", "Read-only mode uses the Codex read-only sandbox."
    if settings.agent_sandbox != "auto":
        return settings.agent_sandbox, f"Configured by POCKETPOLYGLOT_AGENT_SANDBOX={settings.agent_sandbox}."
    available, detail = workspace_sandbox_probe()
    if available:
        return "workspace-write", "Bubblewrap workspace sandbox probe passed."
    return (
        "danger-full-access",
        "Workspace sandbox bootstrap is unavailable; local Agent mode is using the explicit "
        f"unsandboxed fallback. Probe: {detail}",
    )


def build_prompt(
    project: dict[str, Any],
    sources: list[dict[str, Any]],
    runtime: dict[str, Any],
    history: list[dict[str, Any]],
    message: str,
) -> str:
    context_messages = [
        {"role": item["role"], "content": item["content"][-8000:]}
        for item in history[-12:]
    ]
    return f"""You are the execution agent inside PocketPolyglot Studio, operating in the ZhJpBook repository.

Current project:
{json.dumps(project, ensure_ascii=False, indent=2)}

Registered sources:
{json.dumps(sources, ensure_ascii=False, indent=2)}

Authoritative Studio runtime snapshot:
{json.dumps(runtime, ensure_ascii=False, indent=2)}

Recent Studio conversation:
{json.dumps(context_messages, ensure_ascii=False, indent=2)}

User message:
{message}

Operating contract:
- Use the repository's existing LinguaLeaf, OCR, exact-TeX, PocketPolished, cover, validation, and export scripts rather than cloning their logic.
- Preserve prior JSON, TeX, sources, figures, equations, tables, diagrams, notation, and source-page evidence. Never substitute facsimile pages for real technical TeX.
- Treat manifest coverage and validators as truth; a partial PDF is not completion evidence.
- For long work, create or launch a resumable PocketPolyglot Studio/tmux job. Do not keep a fragile foreground loop alive in this chat call.
- Diagnose deterministic failures before escalating model reasoning. Keep shared code general; put book-specific instructions in project metadata or project-local plans.
- For progress, status, queue-health, worker, or evidence questions, answer from the authoritative Studio runtime snapshot. Do not run shell commands merely to rediscover data already present in that snapshot.
- Never claim completion without naming the artifact and the validator/evidence that proves it.
- Answer directly and briefly after performing the requested work.
"""


def runtime_snapshot(settings: Settings, database: Database, project_id: str) -> dict[str, Any]:
    manager = JobManager(settings, database)
    jobs: list[dict[str, Any]] = []
    for listed in manager.list(project_id, limit=20):
        job = manager.get(listed["id"]) or listed
        jobs.append(
            {
                key: job.get(key)
                for key in (
                    "id",
                    "capability_id",
                    "title",
                    "status",
                    "progress",
                    "heartbeat_at",
                    "finished_at",
                    "error",
                    "progress_detail",
                )
                if job.get(key) not in (None, "")
            }
            | {"evidence": database.list_evidence(job["id"])}
        )
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
        "artifacts": database.list_artifacts(project_id),
    }


def extract_event_text(event: dict[str, Any]) -> tuple[str, str] | None:
    event_type = str(event.get("type", ""))
    if event_type == "thread.started":
        return "thread", str(event.get("thread_id", ""))
    if event_type == "item.completed":
        item = event.get("item") or {}
        if item.get("type") == "agent_message" and item.get("text"):
            return "message", str(item["text"])
        if item.get("type") in {"command_execution", "mcp_tool_call", "web_search"}:
            label = item.get("command") or item.get("server") or item.get("query") or item.get("type")
            return "activity", str(label)[:500]
    if event_type == "turn.completed":
        return "usage", json.dumps(event.get("usage", {}), ensure_ascii=False)
    if event_type in {"error", "turn.failed"}:
        return "error", str(event.get("message") or event.get("error") or event)
    return None


async def stream_chat(
    settings: Settings,
    database: Database,
    project: dict[str, Any],
    message: str,
    profile: str,
    agent_mode: bool,
) -> AsyncIterator[dict[str, Any]]:
    choice: ModelChoice = choose_model(settings, message, profile)
    history = database.list_messages(project["id"], limit=20)
    sources = database.list_sources(project["id"])
    runtime = runtime_snapshot(settings, database, project["id"])
    sandbox, sandbox_reason = chat_sandbox(settings, agent_mode)
    database.add_message(
        {
            "project_id": project["id"],
            "role": "user",
            "content": message,
            "model": choice.model,
            "reasoning": choice.reasoning,
        }
    )
    prompt = build_prompt(project, sources, runtime, history, message)
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--json",
        "-C",
        str(settings.repo_root),
        "-m",
        choice.model,
        "-c",
        f'model_reasoning_effort="{choice.reasoning}"',
        "-c",
        'approval_policy="never"',
        "-s",
        sandbox,
        "-",
    ]
    yield {
        "type": "route",
        "model": choice.model,
        "reasoning": choice.reasoning,
        "profile": choice.profile,
        "reason": choice.reason,
        "sandbox": sandbox,
        "sandbox_reason": sandbox_reason,
    }
    if sandbox == "danger-full-access":
        yield {"type": "activity", "text": sandbox_reason}
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=settings.repo_root,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdin is not None
    process.stdin.write(prompt.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()

    final_parts: list[str] = []
    thread_id = ""
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded:
            continue
        try:
            event = json.loads(decoded)
        except json.JSONDecodeError:
            yield {"type": "activity", "text": decoded[-1000:]}
            continue
        extracted = extract_event_text(event)
        if not extracted:
            continue
        kind, value = extracted
        if kind == "thread":
            thread_id = value
        elif kind == "message":
            final_parts.append(value)
            yield {"type": "message", "text": value}
        elif kind == "usage":
            try:
                yield {"type": "usage", "usage": json.loads(value)}
            except json.JSONDecodeError:
                pass
        else:
            yield {"type": kind, "text": value}
    return_code = await process.wait()
    final_text = "\n\n".join(final_parts).strip()
    if not final_text and return_code:
        final_text = f"Codex exited with status {return_code}."
    if final_text:
        database.add_message(
            {
                "project_id": project["id"],
                "role": "assistant",
                "content": final_text,
                "model": choice.model,
                "reasoning": choice.reasoning,
                "thread_id": thread_id,
            }
        )
    yield {"type": "done", "returncode": return_code, "thread_id": thread_id}
