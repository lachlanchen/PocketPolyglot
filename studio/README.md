# PocketPolyglot Studio

PocketPolyglot Studio is the local control plane for this repository. It makes
the existing LinguaLeaf, OCR, exact-TeX, PocketPolished, validation, cover, and
Nutstore workflows available through one web app and one Codex-style CLI.

It does not duplicate the book engines. Commands still run from `scripts/`,
`prompt_tools/`, and the established TeX templates, so a pipeline repair in the
repository is immediately available to Studio projects.

![PocketPolyglot Studio showing a live technical-book polish queue](docs/images/pocketpolyglot-studio-queue.png)

## Start

```sh
make studio-install
make studio
```

The default URL is `http://127.0.0.1:8765`. Override it with
`POCKETPOLYGLOT_HOST` and `POCKETPOLYGLOT_PORT`.

For a persistent server:

```sh
tmux new-session -d -s pocketpolyglot-studio \
  'cd /home/lachlan/ProjectsLFS/ZhJpBook && make studio'
```

Local runtime state and the isolated Python environment are stored under
`.pocketpolyglot-studio/` and ignored by Git. Installing Studio does not alter
the repository's base Conda environment. Closing the web app does not stop a
running job.

## CLI

Use the source-tree launcher without installing anything globally:

```sh
./studio/pocketpolyglot doctor
./studio/pocketpolyglot discover
./studio/pocketpolyglot project create "My Book" \
  --workflow lingualeaf --source-language en --target ja --target zh
./studio/pocketpolyglot source add my-book /path/to/book.epub \
  --role primary --language en
./studio/pocketpolyglot run my-book source.inspect
./studio/pocketpolyglot run my-book project.prepare --param profile=fast
./studio/pocketpolyglot status --project my-book
./studio/pocketpolyglot logs JOB_ID
./studio/pocketpolyglot chat my-book
```

Run a prepared multi-book technical polish queue through the same durable job
ledger:

```sh
./studio/pocketpolyglot run technical-pocket-polished-seven pocket.polish.queue \
  --param source_queue=data/source-plan/technical-exact-polished-queue.json \
  --param queue=build-pocket-polished/tasks/studio-technical-seven-queue.json \
  --param status=build-pocket-polished/status-studio-technical-seven.json \
  --param workers=5 \
  --param reasoning=low \
  --param adaptive=true \
  --param network_limit_mbps=100
```

An editable install also exposes `pocketpolyglot` and
`pocketpolyglot-studio` on `PATH`:

```sh
python -m pip install -e studio
```

## Workflows

### LinguaLeaf

The Studio supports modern EN/JP/ZH projects and the maximum-language
classical shape: `wenyan` main text, English, readable modern Japanese, and
modern Chinese. It delegates to the repository's trilingual or quadrilingual
workers, waits for current-manifest coverage, then compiles large-font color
and black-white editions with a table of contents.

### Exact TeX

The exact workflow converts source PDFs into real TeX and then a pocket-size
edition. Figures, equations, tables, diagrams, flowcharts, musical notation,
captions, and source-page evidence remain first-class structures. A
facsimile-only PDF never passes the acceptance contract.

### PocketPolished

The polish workflow splits exact TeX into protected source-linked chunks,
keeps structural TeX immutable, corrects prose and layout, assembles the full
book, checks compilation and overflows, and exports only after evidence passes.

`pocket.polish.queue` is the resumable multi-book form. It migrates valid
reviewed segments into a content-addressed cache before rechunking, limits
model work to unresolved segments, and bounds writer/reviewer retries. A
cross-process resource gate keeps at most the requested number of Codex calls
active and reduces concurrency when network throughput, load, or available
memory crosses configured limits. Its atomic queue status records accepted
segments, current book, worker slots, network throughput, throttling reasons,
assembly, covers, and Nutstore export; the Studio job drawer renders this data
without parsing terminal logs.

### Covers And Validation

`Generate textless cover` uses Codex image generation for the artwork only.
Titles, languages, attribution, and edition labels remain deterministic
overlays in the existing compilers. `Validate current output` records a
workflow-specific `validation.json` covering manifest completion, real TeX,
assembly state, and readable PDFs.

## Chat And Model Routing

Studio chat wraps `codex exec` and persists the conversation in SQLite. The
default route is `gpt-5.6-sol` with low reasoning for fast interaction.

| Profile | Reasoning | Intended use |
| --- | --- | --- |
| Auto | Dynamic | Low by default; escalates diagnostic and audit requests |
| Fast | Low | Status, planning, ordinary edits, deterministic operations |
| Balanced | Medium | Debugging, stalled jobs, OCR or layout diagnosis |
| Deep | High | Broad repair and cross-pipeline review |
| Ultra | X-high | Final evidence audits and difficult architectural failures |

Agent mode gives Codex workspace-write access under the repository's normal
instructions. Read-only mode is available for discussion and inspection. A
chat request is intentionally short-lived; expensive work should be launched
as a Studio job so it survives web-server or browser restarts.

## Durable Job Contract

1. The API builds an argv command from a typed capability or reviewed pipeline
   stage.
2. The job, environment, acceptance checks, and log path are committed to
   SQLite before launch.
3. A dedicated `pps-<job-id>` tmux session starts the runner with an explicit
   environment, independent of the web process and tmux server history.
4. The runner records heartbeats and writes stdout/stderr to a durable log.
5. After the command exits, the evidence engine checks its exit code, files,
   globs, JSON fields, or validator commands.
6. Only jobs whose required evidence all passes receive `complete` status.
   Others become `blocked` with the failed evidence visible in the UI.
7. Retry clones the immutable command and contract into a new job, preserving
   the prior attempt for diagnosis.

SQLite uses WAL mode and atomic report writers use temporary-file replacement.
The API reconciles vanished tmux sessions and marks them `interrupted` instead
of silently leaving a false running state.

## Project Pipeline

Each project has an ignored runtime specification at:

```text
.pocketpolyglot-studio/projects/<project-id>/pipeline.json
```

Schema version 1 contains ordered stages with an argv array, optional
environment, and acceptance checks. The UI shows the exact command before it
runs. `Prepare with Codex` may create source Markdown, book plans, manifests,
and this executable pipeline, but it is explicitly forbidden from starting the
expensive queue during preparation.

Supported acceptance checks:

- `exit_code`
- `path_exists` with optional minimum size
- `glob_min`
- `json_field`
- `command` with return-code and output matching

## Capability Boundaries

Shared Studio code remains task-neutral:

- `capabilities.py` maps stable operations to repository adapters.
- `jobs.py` and `runner.py` own durable execution, not book semantics.
- `evidence.py` proves completion.
- `workflows.py` adapts the existing LinguaLeaf and TeX engines.
- `codex_backend.py` owns chat and dynamic reasoning selection.
- Project-local source choices and book-specific instructions live in the
  project record, preparation report, or existing book plan.

To add a general operation, register a typed capability and evidence contract.
To handle one unusual book, add a project pipeline stage rather than patching
the Studio core.

## Verification

```sh
make studio-doctor
make studio-test
```

`studio-test` runs Python unit tests and the production React build. For an
integration check, create/import a project, register a source, run
`source.inspect`, and confirm both `Command exited successfully` and `Source
report written` appear as passing evidence.
