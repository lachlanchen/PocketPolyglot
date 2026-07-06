# Generic Autorepair Companion - 2026-07-06

The reusable companion is `scripts/autorepair_companion.py`, with tmux launcher
`scripts/interlinear/start_autorepair_companion_tmux.sh`.

## Design

The companion is task-neutral. It does not know about a specific book, language,
or queue. A caller provides:

- a primary tmux session to observe;
- a cheap health command;
- completion keys or ratios parsed from `KEY=VALUE` health output;
- artifact paths whose mtimes represent real progress;
- optional log globs for bounded evidence;
- optional deterministic start command;
- optional `py_compile` paths for tracked Python code.

Normal detection is zero-token. It uses shell probes, tmux state, file mtimes,
health output hashes, and `python -m py_compile`. It launches `codex exec` only
when there is concrete evidence of a code or orchestration fault.

## Reasoning Policy

Repair reasoning is selected automatically:

- `low`: first obvious crash, syntax issue, or failed restart;
- `medium`: active stall or repeated simple fault;
- `high`: repeated repair attempts or unclear orchestration failure;
- `xhigh`: only if explicitly allowed by `AUTOREPAIR_MAX_REASONING=xhigh`.

This keeps routine monitoring cheap and avoids spending large model context on
ordinary progress checks.

## Start Example

```sh
bash scripts/interlinear/start_autorepair_companion_tmux.sh \
  --name zhjpbook-example \
  --primary-session zhjpbook-example \
  --health-command 'python scripts/interlinear/report_trilingual_progress.py --manifest books/example/work/trilingual/chunks/manifest.json --chunk-dir books/example/work/trilingual/interlinear/chunks' \
  --health-nonzero-ok \
  --complete-key missing_chunks=0 \
  --complete-key stale_chunks=0 \
  --complete-key-eq manifest_chunks=valid_chunks \
  --watch books/example/work/trilingual/interlinear/chunks \
  --log 'books/example/work/trilingual/parallel-json/logs/*.log' \
  --py-compile scripts/interlinear/codex_trilingual_plain_json_worker.py \
  --allow-repair
```

## Integration

`start_trilingual_book_tmux.sh` and `start_quadrilingual_wenyan_tmux.sh` now
start this companion by default. Disable it for debugging with:

```sh
START_AUTOREPAIR_COMPANION=0 bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh sunzi-bingfa
```

The restart command passed by each runner also sets
`START_AUTOREPAIR_COMPANION=0`, preventing recursive companion spawning.

## Safety Rules

Repair prompts include only bounded evidence windows. Repair agents are told not
to edit `sources/`, delete generated artifacts, or reset chunk output. Tracked
script fixes must be validated with `python -m py_compile` and committed.
