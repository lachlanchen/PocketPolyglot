from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .capabilities import list_capabilities
from .codex_backend import stream_chat
from .config import Settings
from .db import Database
from .discovery import discover_repository
from .jobs import JobManager
from .workflows import default_pipeline, write_json


def project_from_ref(database: Database, value: str) -> dict[str, Any]:
    project = database.get_project(value) or database.get_project_by_slug(value)
    if not project:
        raise SystemExit(f"Unknown project: {value}")
    return project


def format_project(project: dict[str, Any]) -> str:
    languages = ",".join([project["source_language"], *project["target_languages"]])
    return f"{project['slug']:<30} {project['workflow']:<18} {project['status']:<10} {languages:<18} {project['title']}"


def cmd_doctor(settings: Settings) -> int:
    print(f"PocketPolyglot root: {settings.repo_root}")
    print(f"Studio state:       {settings.state_root}")
    print(f"Chat model:         {settings.chat_model} ({settings.default_reasoning})")
    missing = 0
    for command in ("codex", "tmux", "xelatex", "pdftotext", "pdfinfo", "node", "npm"):
        path = shutil.which(command)
        print(f"{command:<12} {'OK' if path else 'MISSING':<8} {path or ''}")
        missing += int(path is None)
    return 1 if missing else 0


async def run_chat(
    settings: Settings,
    database: Database,
    project: dict[str, Any],
    message: str,
    profile: str,
    agent_mode: bool,
) -> int:
    return_code = 0
    async for event in stream_chat(settings, database, project, message, profile, agent_mode):
        if event["type"] == "route":
            print(f"[{event['model']} · {event['reasoning']} · {event['reason']}]", file=sys.stderr)
        elif event["type"] == "message":
            print(event["text"])
        elif event["type"] == "activity":
            print(f"· {event['text']}", file=sys.stderr)
        elif event["type"] == "error":
            print(f"error: {event['text']}", file=sys.stderr)
        elif event["type"] == "done":
            return_code = int(event["returncode"])
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pocketpolyglot",
        description="Chat with and operate PocketPolyglot Studio from the terminal.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check local runtime dependencies.")
    serve = subparsers.add_parser("serve", help="Run the local web app.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    subparsers.add_parser("capabilities", help="List runnable Studio capabilities.")
    subparsers.add_parser("discover", help="Discover existing repository books and progress.")

    project_parser = subparsers.add_parser("project", help="Manage Studio projects.")
    project_sub = project_parser.add_subparsers(dest="project_command", required=True)
    project_sub.add_parser("list")
    create = project_sub.add_parser("create")
    create.add_argument("title")
    create.add_argument("--book-id", default="")
    create.add_argument("--workflow", choices=["lingualeaf", "pocket_exact", "pocket_polished", "custom"], default="lingualeaf")
    create.add_argument("--source-language", default="en")
    create.add_argument("--primary-language", default="en")
    create.add_argument("--target", action="append", default=[])
    show = project_sub.add_parser("show")
    show.add_argument("project")
    import_parser = project_sub.add_parser("import")
    import_parser.add_argument("book_id")

    source_parser = subparsers.add_parser("source", help="Register a local source file.")
    source_sub = source_parser.add_subparsers(dest="source_command", required=True)
    add = source_sub.add_parser("add")
    add.add_argument("project")
    add.add_argument("path", type=Path)
    add.add_argument("--role", default="reference")
    add.add_argument("--language", default="")

    run = subparsers.add_parser("run", help="Launch a durable Studio job in tmux.")
    run.add_argument("project")
    run.add_argument("capability")
    run.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    status = subparsers.add_parser("status", help="Show jobs.")
    status.add_argument("job", nargs="?")
    status.add_argument("--project")
    logs = subparsers.add_parser("logs", help="Tail a Studio job log.")
    logs.add_argument("job")
    logs.add_argument("--lines", type=int, default=100)
    cancel = subparsers.add_parser("cancel")
    cancel.add_argument("job")
    retry = subparsers.add_parser("retry")
    retry.add_argument("job")
    chat = subparsers.add_parser("chat", help="Chat with Codex in a Studio project.")
    chat.add_argument("project")
    chat.add_argument("message", nargs="*")
    chat.add_argument("--profile", choices=["auto", "fast", "balanced", "deep", "ultra"], default="auto")
    chat.add_argument("--read-only", action="store_true")

    browser = subparsers.add_parser("browser", help="Operate the persistent Studio noVNC/CDP browser.")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    browser_start = browser_sub.add_parser("start", help="Start or reuse the managed browser.")
    browser_start.add_argument("--studio-url")
    browser_start.add_argument("--display")
    browser_start.add_argument("--vnc-port", type=int)
    browser_start.add_argument("--novnc-port", type=int)
    browser_start.add_argument("--cdp-port", type=int)
    browser_start.add_argument("--browser-profile", type=Path)
    browser_start.add_argument("--session")
    browser_start.add_argument("--resolution")
    browser_start.add_argument("--wait", type=float, default=40)
    browser_sub.add_parser("status", help="Show browser, noVNC, CDP, and Studio health.")
    browser_sub.add_parser("stop", help="Stop the managed browser without deleting its profile.")
    browser_sub.add_parser("pages", help="List CDP pages in the managed browser.")
    browser_refresh = browser_sub.add_parser("refresh", help="Reload the visible Studio page through CDP.")
    browser_refresh.add_argument("--project")
    browser_progress = browser_sub.add_parser("progress", help="Inspect active jobs through the Studio web app.")
    browser_progress.add_argument("--project")
    browser_screenshot = browser_sub.add_parser("screenshot", help="Capture the visible Studio page through CDP.")
    browser_screenshot.add_argument("--project")
    browser_screenshot.add_argument("--output", type=Path)
    browser_chat = browser_sub.add_parser("chat", help="Send a message through the visible Studio chat UI.")
    browser_chat.add_argument("project")
    browser_chat.add_argument("message", nargs="+")
    browser_chat.add_argument("--profile", choices=["auto", "fast", "balanced", "deep", "ultra"], default="fast")
    browser_chat.add_argument("--read-only", action="store_true")
    browser_chat.add_argument("--timeout", type=float, default=600)
    browser_chat.add_argument("--screenshot", type=Path)
    args = parser.parse_args()

    settings = Settings.load()
    database = Database(settings.database_path)
    manager = JobManager(settings, database)

    if args.command == "browser":
        from .browser_control import (
            BrowserConfig,
            browser_status,
            chat_in_ui,
            inspect_progress,
            list_pages,
            select_project,
            start_browser,
            stop_browser,
            studio_page,
            summarize_progress,
        )

        overrides: dict[str, Any] = {}
        if args.browser_command == "start":
            overrides = {
                "studio_url": args.studio_url,
                "display": args.display,
                "vnc_port": args.vnc_port,
                "novnc_port": args.novnc_port,
                "cdp_port": args.cdp_port,
                "profile": args.browser_profile,
                "session": args.session,
                "resolution": args.resolution,
            }
        config = BrowserConfig.load(settings, overrides)
        if args.browser_command == "start":
            print(json.dumps(start_browser(config, args.wait), ensure_ascii=False, indent=2))
            return 0
        if args.browser_command == "status":
            print(json.dumps(browser_status(config), ensure_ascii=False, indent=2))
            return 0
        if args.browser_command == "stop":
            print(json.dumps(stop_browser(config), ensure_ascii=False, indent=2))
            return 0
        if args.browser_command == "pages":
            print(json.dumps(list_pages(config), ensure_ascii=False, indent=2))
            return 0
        if not browser_status(config)["healthy"]:
            raise SystemExit("Studio browser is not healthy; run `pocketpolyglot browser start`.")
        page = studio_page(config)
        try:
            if args.browser_command == "progress":
                if args.project:
                    select_project(page, project_from_ref(database, args.project)["title"])
                print(json.dumps(summarize_progress(inspect_progress(page)), ensure_ascii=False, indent=2))
                return 0
            if args.browser_command == "refresh":
                page.reload()
                if args.project:
                    select_project(page, project_from_ref(database, args.project)["title"])
                print(json.dumps(inspect_progress(page), ensure_ascii=False, indent=2))
                return 0
            if args.browser_command == "screenshot":
                if args.project:
                    select_project(page, project_from_ref(database, args.project)["title"])
                output = (args.output or (config.state_dir / "studio.png")).expanduser().resolve()
                print(page.screenshot(output))
                return 0
            if args.browser_command == "chat":
                project = project_from_ref(database, args.project)
                result = chat_in_ui(
                    page,
                    project["title"],
                    " ".join(args.message),
                    args.profile,
                    not args.read_only,
                    args.timeout,
                )
                screenshot = (args.screenshot or (config.state_dir / "last-chat.png")).expanduser().resolve()
                page.screenshot(screenshot)
                result["screenshot"] = str(screenshot)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
        finally:
            page.close()
        return 2

    if args.command == "doctor":
        return cmd_doctor(settings)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("pocketpolyglot_studio.api:app", host=args.host, port=args.port, reload=False)
        return 0
    if args.command == "capabilities":
        for capability in list_capabilities():
            print(f"{capability['id']:<30} {capability['category']:<16} {capability['name']}")
        return 0
    if args.command == "discover":
        state = discover_repository(settings.repo_root)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    if args.command == "project":
        if args.project_command == "list":
            for project in database.list_projects():
                print(format_project(project))
            return 0
        if args.project_command == "create":
            project = database.create_project(
                {
                    "title": args.title,
                    "book_id": args.book_id,
                    "workflow": args.workflow,
                    "source_language": args.source_language,
                    "primary_language": args.primary_language,
                    "target_languages": args.target or ["ja", "zh"],
                }
            )
            write_json(settings.project_root(project["id"]) / "pipeline.json", default_pipeline(settings, project))
            print(json.dumps(project, ensure_ascii=False, indent=2))
            return 0
        if args.project_command == "show":
            project = project_from_ref(database, args.project)
            print(json.dumps(project | {"sources": database.list_sources(project["id"]), "jobs": manager.list(project["id"])}, ensure_ascii=False, indent=2))
            return 0
        if args.project_command == "import":
            found = next((item for item in discover_repository(settings.repo_root)["books"] if item["book_id"] == args.book_id), None)
            if not found:
                raise SystemExit(f"Book not discovered: {args.book_id}")
            project = database.create_project(
                {
                    "title": found["title"],
                    "book_id": args.book_id,
                    "workflow": found["workflow"],
                    "status": "ready" if found["complete"] else "active",
                    "metadata": {"imported": True, "manifest": found["manifest"]},
                }
            )
            write_json(settings.project_root(project["id"]) / "pipeline.json", default_pipeline(settings, project))
            print(json.dumps(project, ensure_ascii=False, indent=2))
            return 0
    if args.command == "source":
        project = project_from_ref(database, args.project)
        path = args.path.expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Source not found: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source = database.add_source(
            project["id"],
            {
                "path": str(path),
                "role": args.role,
                "language": args.language,
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            },
        )
        print(json.dumps(source, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        project = project_from_ref(database, args.project)
        parameters: dict[str, Any] = {}
        for item in args.param:
            if "=" not in item:
                raise SystemExit(f"Invalid --param {item!r}; expected KEY=VALUE")
            key, value = item.split("=", 1)
            if value.casefold() in {"true", "false"}:
                parameters[key] = value.casefold() == "true"
            elif value.isdigit():
                parameters[key] = int(value)
            else:
                parameters[key] = value
        job = manager.launch(project, args.capability, parameters)
        print(f"job:     {job['id']}")
        print(f"status:  {job['status']}")
        print(f"tmux:    {job['tmux_session']}")
        print(f"log:     {job['log_path']}")
        return 0
    if args.command == "status":
        if args.job:
            job = manager.get(args.job)
            if not job:
                raise SystemExit(f"Unknown job: {args.job}")
            print(json.dumps(job | {"evidence": database.list_evidence(args.job)}, ensure_ascii=False, indent=2))
        else:
            project_id = project_from_ref(database, args.project)["id"] if args.project else None
            for job in manager.list(project_id):
                print(f"{job['id'][:12]} {job['status']:<12} {job['capability_id']:<28} {job['title']}")
        return 0
    if args.command == "logs":
        job = manager.get(args.job)
        if not job:
            raise SystemExit(f"Unknown job: {args.job}")
        path = Path(job["log_path"])
        if path.exists():
            print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-args.lines :]))
        return 0
    if args.command == "cancel":
        print(json.dumps(manager.cancel(args.job), ensure_ascii=False, indent=2))
        return 0
    if args.command == "retry":
        print(json.dumps(manager.retry(args.job), ensure_ascii=False, indent=2))
        return 0
    if args.command == "chat":
        project = project_from_ref(database, args.project)
        if args.message:
            return asyncio.run(run_chat(settings, database, project, " ".join(args.message), args.profile, not args.read_only))
        print(f"PocketPolyglot Studio · {project['title']} · /exit to leave")
        while True:
            try:
                message = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if message in {"/exit", "/quit"}:
                return 0
            if message:
                asyncio.run(run_chat(settings, database, project, message, args.profile, not args.read_only))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
