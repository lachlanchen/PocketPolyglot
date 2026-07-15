from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from .config import Settings
from .db import Database
from .model_router import ModelChoice, choose_model


def build_prompt(
    project: dict[str, Any],
    sources: list[dict[str, Any]],
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
- Never claim completion without naming the artifact and the validator/evidence that proves it.
- Answer directly and briefly after performing the requested work.
"""


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
    database.add_message(
        {
            "project_id": project["id"],
            "role": "user",
            "content": message,
            "model": choice.model,
            "reasoning": choice.reasoning,
        }
    )
    prompt = build_prompt(project, sources, history, message)
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
        "workspace-write" if agent_mode else "read-only",
        "-",
    ]
    yield {
        "type": "route",
        "model": choice.model,
        "reasoning": choice.reasoning,
        "profile": choice.profile,
        "reason": choice.reason,
    }
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
