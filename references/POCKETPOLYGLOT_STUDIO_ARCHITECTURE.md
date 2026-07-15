# PocketPolyglot Studio Architecture

## Objective

PocketPolyglot Studio consolidates the repository's accumulated book-making
capabilities into a durable local application without moving domain logic out
of the scripts that already implement it. It supports source analysis,
LinguaLeaf multilingual generation, PDF-to-real-TeX reconstruction,
pocket-size layout, semantic/mechanical polish, compilation, validation,
covers, artifact inspection, and export.

## System Layers

| Layer | Responsibility |
| --- | --- |
| React work surface | Projects, source files, stages, jobs, evidence, artifacts, and chat |
| FastAPI control plane | Typed API, local uploads, repository discovery, streaming chat |
| SQLite ledger | Projects, messages, immutable job attempts, events, evidence, artifacts |
| tmux runner | Independent process lifetime, heartbeats, logs, cancellation, retry |
| Capability registry | Stable user operations and workflow-compatible parameters |
| Existing engines | LinguaLeaf JSON, OCR, exact TeX, PocketPolished, XeLaTeX, covers, sync |
| Codex backend | Adaptive preparation, interactive execution, diagnosis, final audit |

## Core Invariants

1. A PDF page count is not task completion.
2. The current manifest and its validators define generation coverage.
3. Every completed Studio job has evidence matched to its requested artifact.
4. Technical books require real text/math TeX and preserved visual structures;
   a page-image facsimile is blocked.
5. Long tasks do not depend on the web process or chat request staying alive.
6. Existing JSON, TeX, and sources are incremental assets and are not removed
   by preparation or repair.
7. Shared code carries general workflow ability; book-specific policy remains
   in project data or the existing book plan.

## Model Policy

The interactive default is `gpt-5.6-sol` low reasoning. Auto routing raises
reasoning for explicit diagnosis, repair, deep validation, or final audit.
Worker models and defaults are configurable with:

```sh
POCKETPOLYGLOT_CHAT_MODEL=gpt-5.6-sol
POCKETPOLYGLOT_WORKER_MODEL=gpt-5.6-sol
POCKETPOLYGLOT_REASONING=low
```

Dynamic routing changes reasoning effort, not the book data contract.
Deterministic scripts and validators remain the primary path; Codex handles
ambiguous preparation, semantic correction, and exceptional repair.

## Runtime Paths

| Data | Path |
| --- | --- |
| Application package | `studio/pocketpolyglot_studio/` |
| Web source | `studio/web/src/` |
| Local database | `.pocketpolyglot-studio/studio.sqlite3` |
| Project plans/reports | `.pocketpolyglot-studio/projects/<id>/` |
| Job logs | `.pocketpolyglot-studio/jobs/<id>/job.log` |
| Uploaded local inputs | `.pocketpolyglot-studio/uploads/<id>/` |
| Production frontend | `studio/web/dist/` |

The runtime paths are ignored. Source books remain under `sources/`, tracked
book metadata remains under `books/` and `data/`, and build artifacts remain in
their established output trees.

## Recovery Semantics

- `launching` and `running` jobs are reconciled against exact tmux session
  names.
- A vanished runner without a final database state becomes `interrupted`.
- Cancellation signals the child process group before closing tmux.
- Retry creates a new attempt linked by `retry_of`; it does not overwrite old
  logs or evidence.
- A command that exits zero but fails artifact checks becomes `blocked`, not
  complete.
- Existing repository autorepair companions may remain active inside a
  LinguaLeaf worker; Studio monitors their manifest outcome rather than
  duplicating their internal repair loop.

## Extension Rule

Add a core capability only when the operation is reusable across projects.
Otherwise create or edit the project's `pipeline.json`. This keeps the Studio
general while still allowing Codex chat to prepare unusual sources and invoke
specialized repository scripts.
