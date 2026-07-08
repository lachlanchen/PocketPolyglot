# Codex Usage Limit Monitoring - 2026-07-08

This note documents how the current LinguaLeaf/PocketPolyglot queues detect
Codex quota exhaustion and how to inspect it during long tmux runs.

## What Is Monitored

The pipeline does not currently read the interactive Codex `/status` quota
percentage from inside batch workers. Instead, it detects out-of-quota
conditions reactively from Codex command output and from worker status files.
This is enough to keep JSON work resumable without losing generated chunks.

## Detection Path

1. Worker scripts call `codex exec` and write stdout/stderr into per-chunk logs.
2. `scripts/interlinear/codex_chunk_worker.py` defines usage-limit markers:
   `you've hit your usage limit`, `you have hit your usage limit`,
   `usage limit`, `purchase more credits`, and `try again at`.
3. `run_codex()` scans only the new log text produced by the latest attempt.
   If a marker appears, it treats the attempt as quota-limited rather than as a
   normal validation failure.
4. For workers that use `run_codex()` directly, the default behavior is to sleep
   and retry. The launcher exports:
   - `CODEX_USAGE_LIMIT_WAIT_SECONDS=3600`
   - `CODEX_USAGE_LIMIT_MAX_WAIT_SECONDS=0`
5. Trilingual plain JSON workers catch usage-limit exceptions, write a status
   record such as `"status": "usage_limit"`, print `usage limit detected`, and
   stop that worker with exit code `86`. The surrounding tmux/autorepair layer
   can resume from the first missing chunk later.

## Launcher Settings

`scripts/interlinear/start_trilingual_book_tmux.sh` passes quota controls into
the generated tmux run script:

```sh
export CODEX_USAGE_LIMIT_WAIT_SECONDS="${CODEX_USAGE_LIMIT_WAIT_SECONDS:-3600}"
export CODEX_USAGE_LIMIT_MAX_WAIT_SECONDS="${CODEX_USAGE_LIMIT_MAX_WAIT_SECONDS:-0}"
```

For normal long queues, keep the one-hour wait interval. If quota is scarce,
reduce `WORKERS`; do not delete partial JSON, candidates, or status files.

## How To Check A Running Book

Check tmux sessions:

```sh
tmux ls | rg 'world-poetry|<book-id>|trilingual|quadrilingual'
```

Check manifest progress:

```sh
python scripts/interlinear/report_trilingual_progress.py \
  --manifest books/<book-id>/work/trilingual/chunks/manifest.json \
  --chunk-dir books/<book-id>/work/trilingual/interlinear/chunks
```

Check quota/status records:

```sh
find books/<book-id>/work/trilingual/parallel-json/candidates/status \
  -maxdepth 1 -name '*.json' -print0 |
  xargs -0 -r rg -n '"status": "(usage_limit|attempt_failed|accepted)"'
```

Check worker logs for the actual Codex message:

```sh
rg -n 'usage limit|purchase more credits|try again at|wait|sleep' \
  books/<book-id>/work/trilingual/parallel-json/logs \
  books/<book-id>/work/trilingual/parallel-json/tri-worker-* \
  books/<book-id>/work/logs
```

Check whether Codex processes are still actively consuming quota:

```sh
ps -eo pid,ppid,stat,etime,pcpu,args |
  rg 'codex exec|codex_trilingual|codex_quadrilingual|<book-id>' |
  rg -v 'rg '
```

## Interpreting Results

- `usage_limit` means Codex quota was detected; the chunk should be retried
  later and should not be treated as a bad translation.
- `attempt_failed` means the model returned something invalid or incomplete;
  retry/review may be needed.
- `accepted` means the candidate passed validation and can be merged.
- `missing_chunks > 0` with active `codex exec` processes means the book is
  still moving.
- `missing_chunks > 0` with no workers and no recent file changes means the
  queue needs a gentle resume from `first_missing`.

## Current Caveat

This mechanism detects hard quota messages, not remaining quota percentage.
If exact quota percentage matters, a human or interactive Codex session must run
`/status`. Batch scripts should remain conservative: use fewer workers when
quota is low, preserve all current artifacts, and resume from manifests.
