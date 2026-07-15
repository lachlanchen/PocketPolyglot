from __future__ import annotations

import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import Settings


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    category: str
    description: str
    workflows: tuple[str, ...]
    icon: str
    parameters: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class JobSpec:
    title: str
    command: list[str]
    environment: dict[str, str]
    acceptance: list[dict[str, Any]]


CAPABILITIES = (
    Capability(
        "source.inspect",
        "Inspect sources",
        "Source",
        "Profile PDF, EPUB, image, and text inputs before planning.",
        ("lingualeaf", "pocket_exact", "pocket_polished", "custom"),
        "scan-search",
    ),
    Capability(
        "project.prepare",
        "Prepare with Codex",
        "Plan",
        "Let Codex inspect the registered sources and create a validated, resumable project plan without starting generation.",
        ("lingualeaf", "pocket_exact", "pocket_polished", "custom"),
        "wand-sparkles",
        ({"name": "profile", "type": "select", "default": "fast", "options": ["fast", "balanced", "deep", "ultra"]},),
    ),
    Capability(
        "lingualeaf.generate",
        "Generate multilingual JSON",
        "LinguaLeaf",
        "Run the prepared trilingual or wenyan quadrilingual queue and wait for manifest coverage.",
        ("lingualeaf",),
        "languages",
        (
            {"name": "workers", "type": "number", "default": 10, "minimum": 1, "maximum": 100},
            {"name": "reasoning", "type": "select", "default": "low", "options": ["low", "medium", "high", "xhigh"]},
        ),
    ),
    Capability(
        "lingualeaf.compile",
        "Compile maximum-language editions",
        "LinguaLeaf",
        "Validate complete chunk coverage, build large-font color and black-white PDFs, and preserve the table of contents.",
        ("lingualeaf",),
        "book-open-check",
    ),
    Capability(
        "pocket.exact",
        "Build exact and pocket TeX",
        "Technical TeX",
        "Create real TeX exact and pocket editions while preserving figures, equations, tables, diagrams, and notation.",
        ("pocket_exact",),
        "file-code-2",
        (
            {"name": "queue", "type": "text", "default": "build-pocket/tasks/queue.json"},
            {"name": "agent_optimize", "type": "boolean", "default": True},
        ),
    ),
    Capability(
        "pocket.polish.prepare",
        "Prepare lossless polish chunks",
        "PocketPolished",
        "Split an exact TeX book into protected, source-linked polish tasks.",
        ("pocket_polished",),
        "list-tree",
    ),
    Capability(
        "pocket.polish.run",
        "Polish and assemble",
        "PocketPolished",
        "Polish chunks, preserve immutable TeX structures, compile, validate, and sync accepted output.",
        ("pocket_polished",),
        "sparkles",
        (
            {"name": "workers", "type": "number", "default": 5, "minimum": 1, "maximum": 20},
            {"name": "reasoning", "type": "select", "default": "low", "options": ["low", "medium", "high", "xhigh"]},
        ),
    ),
    Capability(
        "pocket.polish.queue",
        "Run technical polish queue",
        "PocketPolished",
        "Prepare and run a resumable multi-book queue with segment caching, adaptive Codex concurrency, covers, validation, and Nutstore sync.",
        ("pocket_polished", "custom"),
        "gauge",
        (
            {
                "name": "source_queue",
                "type": "text",
                "default": "data/source-plan/technical-exact-polished-queue.json",
            },
            {
                "name": "queue",
                "type": "text",
                "default": "build-pocket-polished/tasks/studio-technical-seven-queue.json",
            },
            {
                "name": "status",
                "type": "text",
                "default": "build-pocket-polished/status-studio-technical-seven.json",
            },
            {"name": "workers", "type": "number", "default": 5, "minimum": 1, "maximum": 20},
            {"name": "reasoning", "type": "select", "default": "low", "options": ["low", "medium", "high", "xhigh"]},
            {"name": "adaptive", "type": "boolean", "default": True},
            {"name": "network_limit_mbps", "type": "number", "default": 100, "minimum": 1},
        ),
    ),
    Capability(
        "project.validate",
        "Validate current output",
        "Quality",
        "Check manifest coverage, real TeX/PDF artifacts, workflow status, and readable PDFs without changing content.",
        ("lingualeaf", "pocket_exact", "pocket_polished", "custom"),
        "shield-check",
    ),
    Capability(
        "cover.generate",
        "Generate textless cover",
        "Cover",
        "Ask Codex image generation for a clean portrait cover background; titles remain deterministic TeX overlays.",
        ("lingualeaf", "pocket_exact", "pocket_polished"),
        "image",
        ({"name": "reasoning", "type": "select", "default": "medium", "options": ["low", "medium", "high"]},),
    ),
    Capability(
        "export.nutstore",
        "Export to Nutstore",
        "Publish",
        "Sync only the maximum-language public editions to the configured Projects and Share locations.",
        ("lingualeaf",),
        "cloud-upload",
    ),
    Capability(
        "pipeline.stage",
        "Run planned stage",
        "Advanced",
        "Execute one reviewed stage from the project-local pipeline specification.",
        ("lingualeaf", "pocket_exact", "pocket_polished", "custom"),
        "play",
        ({"name": "stage_id", "type": "text", "required": True},),
    ),
    Capability(
        "custom.command",
        "Run command",
        "Advanced",
        "Run an explicit argv command as a durable, logged Studio job.",
        ("custom", "lingualeaf", "pocket_exact", "pocket_polished"),
        "terminal",
        ({"name": "command", "type": "text", "required": True},),
    ),
)


def list_capabilities() -> list[dict[str, Any]]:
    return [asdict(item) for item in CAPABILITIES]


def get_capability(capability_id: str) -> Capability:
    for capability in CAPABILITIES:
        if capability.id == capability_id:
            return capability
    raise KeyError(capability_id)


def _module_command(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", f"pocketpolyglot_studio.{module}", *args]


def build_job_spec(
    settings: Settings,
    project: dict[str, Any],
    capability_id: str,
    parameters: dict[str, Any],
) -> JobSpec:
    capability = get_capability(capability_id)
    if project["workflow"] not in capability.workflows:
        raise ValueError(f"{capability.name} does not support workflow {project['workflow']}")
    project_id = project["id"]
    book_id = project.get("book_id") or project["slug"]
    environment = {
        "POCKETPOLYGLOT_ROOT": str(settings.repo_root),
        "POCKETPOLYGLOT_STATE": str(settings.state_root),
        "PYTHONPATH": str(settings.repo_root / "studio"),
    }

    if capability_id == "source.inspect":
        report = settings.project_root(project_id) / "source-report.json"
        return JobSpec(
            capability.name,
            _module_command("workflows", "inspect", project_id),
            environment,
            [{"type": "path_exists", "label": "Source report written", "path": str(report), "min_bytes": 20}],
        )

    if capability_id == "project.prepare":
        profile = str(parameters.get("profile", "fast"))
        return JobSpec(
            capability.name,
            _module_command("workflows", "prepare", project_id, "--profile", profile),
            environment,
            [
                {
                    "type": "path_exists",
                    "label": "Project preparation report",
                    "path": str(settings.project_root(project_id) / "preparation.json"),
                    "min_bytes": 40,
                },
                {
                    "type": "path_exists",
                    "label": "Executable pipeline plan",
                    "path": str(settings.project_root(project_id) / "pipeline.json"),
                    "min_bytes": 40,
                },
            ],
        )

    if capability_id == "lingualeaf.generate":
        workers = max(1, min(int(parameters.get("workers", 10)), 100))
        reasoning = str(parameters.get("reasoning", "low"))
        return JobSpec(
            capability.name,
            _module_command(
                "workflows",
                "lingualeaf-generate",
                project_id,
                "--workers",
                str(workers),
                "--model",
                settings.worker_model,
                "--reasoning",
                reasoning,
            ),
            environment,
            [
                {
                    "type": "json_field",
                    "label": "Manifest coverage is complete",
                    "path": str(settings.project_root(project_id) / "generation-status.json"),
                    "field": "complete",
                    "equals": True,
                }
            ],
        )

    if capability_id == "lingualeaf.compile":
        return JobSpec(
            capability.name,
            _module_command("workflows", "lingualeaf-compile", project_id),
            environment,
            [
                {
                    "type": "glob_min",
                    "label": "Color and black-white PDFs exist",
                    "pattern": f"build/{book_id}/**/*.pdf",
                    "minimum": 2,
                }
            ],
        )

    if capability_id == "pocket.exact":
        queue = str(parameters.get("queue", "build-pocket/tasks/queue.json"))
        command = [
            sys.executable,
            "scripts/books/build_pocket_tex_queue.py",
            "--queue",
            queue,
            "--book-id",
            book_id,
        ]
        if parameters.get("agent_optimize", True):
            command.extend(("--agent-optimize", "--agent-model", settings.worker_model, "--agent-reasoning", "low"))
        return JobSpec(
            capability.name,
            command,
            environment,
            [
                {"type": "path_exists", "label": "Exact TeX", "path": f"build-pocket/{book_id}/exact/tex/book.tex"},
                {"type": "path_exists", "label": "Exact PDF", "path": f"build-pocket/{book_id}/exact/book.pdf"},
                {"type": "path_exists", "label": "Pocket TeX", "path": f"build-pocket/{book_id}/pocket-large-font/tex/book.tex"},
                {"type": "path_exists", "label": "Pocket PDF", "path": f"build-pocket/{book_id}/pocket-large-font/book.pdf"},
            ],
        )

    if capability_id == "pocket.polish.prepare":
        return JobSpec(
            capability.name,
            [sys.executable, "scripts/books/prepare_build_pocket_polished.py", "--book-id", book_id],
            environment,
            [
                {
                    "type": "path_exists",
                    "label": "Polish manifest",
                    "path": f"build-pocket-polished/{book_id}/tasks/manifest.json",
                }
            ],
        )

    if capability_id == "pocket.polish.run":
        workers = max(1, min(int(parameters.get("workers", 5)), 20))
        reasoning = str(parameters.get("reasoning", "low"))
        return JobSpec(
            capability.name,
            [
                sys.executable,
                "scripts/books/run_build_pocket_polished_queue.py",
                "--book-id",
                book_id,
                "--workers",
                str(workers),
                "--model",
                settings.worker_model,
                "--reasoning",
                reasoning,
            ],
            environment,
            [
                {
                    "type": "json_field",
                    "label": "Polished assembly accepted",
                    "path": f"build-pocket-polished/{book_id}/status.json",
                    "field": "status",
                    "equals": "complete",
                },
                {
                    "type": "glob_min",
                    "label": "Polished PDFs",
                    "pattern": f"build-pocket-polished/{book_id}/**/*.pdf",
                    "minimum": 1,
                },
            ],
        )

    if capability_id == "pocket.polish.queue":
        workers = max(1, min(int(parameters.get("workers", 5)), 20))
        reasoning = str(parameters.get("reasoning", "low"))
        source_queue = str(
            parameters.get(
                "source_queue",
                "data/source-plan/technical-exact-polished-queue.json",
            )
        )
        queue = str(
            parameters.get(
                "queue",
                "build-pocket-polished/tasks/studio-technical-seven-queue.json",
            )
        )
        status = str(
            parameters.get(
                "status",
                "build-pocket-polished/status-studio-technical-seven.json",
            )
        )
        adaptive = bool(parameters.get("adaptive", True))
        network_limit = max(1.0, float(parameters.get("network_limit_mbps", 100)))
        environment["POCKETPOLYGLOT_PROGRESS_PATH"] = str(
            (settings.repo_root / status).resolve()
        )
        command = _module_command(
            "workflows",
            "pocket-polish-queue",
            "--source-queue",
            source_queue,
            "--queue",
            queue,
            "--status",
            status,
            "--workers",
            str(workers),
            "--model",
            settings.worker_model,
            "--reasoning",
            reasoning,
            "--network-limit-mbps",
            str(network_limit),
        )
        if not adaptive:
            command.append("--no-adaptive")
        return JobSpec(
            capability.name,
            command,
            environment,
            [
                {
                    "type": "json_field",
                    "label": "All queued books passed assembly and export",
                    "path": status,
                    "field": "status",
                    "equals": "complete",
                }
            ],
        )

    if capability_id == "project.validate":
        report = settings.project_root(project_id) / "validation.json"
        return JobSpec(
            capability.name,
            _module_command("workflows", "validate", project_id),
            environment,
            [
                {
                    "type": "json_field",
                    "label": "Workflow output accepted",
                    "path": str(report),
                    "field": "accepted",
                    "equals": True,
                }
            ],
        )

    if capability_id == "cover.generate":
        reasoning = str(parameters.get("reasoning", "medium"))
        cover_path = settings.repo_root / "assets" / "covers" / book_id / "cover.png"
        return JobSpec(
            capability.name,
            _module_command("workflows", "cover", project_id, "--reasoning", reasoning),
            environment,
            [
                {
                    "type": "path_exists",
                    "label": "Textless cover artwork",
                    "path": str(cover_path),
                    "min_bytes": 10000,
                }
            ],
        )

    if capability_id == "export.nutstore":
        return JobSpec(
            capability.name,
            [sys.executable, "scripts/books/sync_max_language_book_to_nutstore.py", book_id],
            environment,
            [],
        )

    if capability_id == "pipeline.stage":
        stage_id = str(parameters.get("stage_id", ""))
        if not stage_id:
            raise ValueError("stage_id is required")
        pipeline_path = settings.project_root(project_id) / "pipeline.json"
        import json

        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
        stage = next((item for item in pipeline.get("stages", []) if item.get("id") == stage_id), None)
        if not stage:
            raise ValueError(f"Unknown pipeline stage: {stage_id}")
        command = [str(item) for item in stage.get("argv", [])]
        if not command:
            raise ValueError(f"Pipeline stage {stage_id} has no argv")
        return JobSpec(
            stage.get("title", stage_id),
            command,
            environment | {str(key): str(value) for key, value in stage.get("environment", {}).items()},
            list(stage.get("acceptance", [])),
        )

    if capability_id == "custom.command":
        command = shlex.split(str(parameters.get("command", "")))
        if not command:
            raise ValueError("command is required")
        return JobSpec(capability.name, command, environment, list(parameters.get("acceptance", [])))

    raise KeyError(capability_id)
