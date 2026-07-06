# Self-Healing Interlinear Pipeline

This project should keep long book jobs complete, correct, robust, and efficient without turning a small transient failure into a full restart. The pipeline therefore uses layered recovery, from deterministic checks to controlled Codex self-repair.

## Core Principle

Never overwrite good artifacts just because the chunk plan or prompt changes. Treat the manifest, chunks, accepted candidates, reviewed chunks, sanitizer outputs, PDFs, and commits as separate recoverable layers. A later stage may repair or enrich an earlier layer, but it should not delete usable work unless validation proves it is stale for the current manifest.

## Runtime Layers

1. **Workers** generate raw bilingual JSON into isolated candidate folders.
2. **Reviewers** validate and backfix chunk JSON without changing source files.
3. **Sanitizers** repair already generated chunks when stricter review rules are added, such as OCR `corrected_text`.
4. **Ordered mergers** promote only contiguous valid chunks, so missing or bad chunks are visible as `waiting_for=<chunk>`.
5. **Autorepair companions** are launched by the writer start scripts. They are separate tmux sessions, independent of the writer process, and stay mostly dormant unless progress stalls.
6. **Book monitors** remain as a fallback layer for coarse progress reporting and queued book handoff.

## Generic Companion Logic

The reusable companion is `scripts/autorepair_companion.py`; the tmux launcher
is `scripts/interlinear/start_autorepair_companion_tmux.sh`. This is the
preferred layer for new long-running jobs because it is neutral: it accepts a
health command, completion keys, watched artifact paths, logs, and an optional
restart command.

The companion spends no model tokens during normal checks. It compares health
output, tmux state, artifact mtimes, and `py_compile` results. It launches a
separate `codex exec` repair session only when a deterministic restart fails,
`py_compile` fails, the health command crashes, or an active tmux job stalls for
the configured threshold.

Repair reasoning is dynamic and capped: first simple faults use `low`, active
stalls or repeated faults use `medium`, and repeated unclear orchestration
failures use `high` unless `AUTOREPAIR_MAX_REASONING=xhigh` is explicitly set.

Trilingual and quadrilingual runners enable it by default:

```sh
bash scripts/interlinear/start_trilingual_book_tmux.sh return-of-the-king
bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh sunzi-bingfa
```

Disable it only for debugging:

```sh
START_AUTOREPAIR_COMPANION=0 bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh sunzi-bingfa
```

## Legacy Guardian Logic

The older book-profile guardian lives in `scripts/interlinear/self_healing_guardian.py`. It remains available for legacy bilingual profiles:

```sh
bash scripts/interlinear/start_sichuan_folk_parallel_json_tmux.sh zhjpbook-sichuan-folk-json
bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh kinkakuji zhjpbook-kinkakuji-json
```

It can also be started explicitly through the compatibility path:

```sh
bash scripts/interlinear/start_autorepair_companion_tmux.sh sichuan-folk-stories-vol1
```

It runs one short check per interval, then exits so the tmux shell loop reloads updated code on the next pass. This makes the companion able to benefit from its own code fixes. The shell loop owns the companion lifecycle, so if `self_healing_guardian.py` has a syntax error or crashes before it can supervise, the shell starts a separate `*-repair` tmux session with the crash facts.

Each cycle:

- `py_compile` critical pipeline scripts.
- Run raw and reviewed ordered merges.
- Read manifest progress from raw and reviewed chunk directories.
- If merge waits inside an already generated range, start the sanitizer for that exact range.
- If the writer stopped before completion, restart it from the first missing chunk.
- If code validation fails or repeated failures indicate a script bug, start a separate repair tmux session.
- If sessions remain active but no progress changes for `ACTIVE_STALL_REPAIR_SECONDS`, start a maintainer repair session instead of waiting forever.

## Writer Integration

Writer start scripts enable the companion by default with `AUTOREPAIR_COMPANION=1`. Disable only for debugging:

```sh
AUTOREPAIR_COMPANION=0 bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh kinkakuji
```

The companion session is named after the writer, for example `zhjpbook-kinkakuji-json-autorepair`. Because it runs in its own tmux session, it is not blocked if the writer process is stuck inside Codex, TeX, merge logic, or a shell wait.

The companion has two stall thresholds. `AUTOREPAIR_STALL_SECONDS` is the gentle warning/restart threshold. `ACTIVE_STALL_REPAIR_SECONDS` is the stronger threshold for the case where tmux sessions still exist but no files or progress counters move.

## Self-Repair Rules

Self-repair must be conservative. The maintainer Codex session may edit tracked pipeline code, references, or closely related metadata, but must not edit `sources/`, delete work artifacts, or reset generated chunks. It must run `python -m py_compile` on touched Python files and commit tracked fixes with a short imperative message.

## Failure Classes

- **Quota limit:** worker `run_codex()` waits and retries hourly; no chunk should be marked permanently failed for quota.
- **Validation gap:** merge reports `waiting_for`; sanitizer or reviewer repairs the blocked chunk only.
- **Stopped worker:** guardian restarts from `first_missing`.
- **Stale claim:** normal monitor clears old claim directories after TTL.
- **Script bug:** guardian starts `zhjpbook-<book>-guardian-repair` with the observed facts and waits for a committed fix.

## Completion Rule

A book is complete only when manifest progress says all chunks are valid, stale count is zero, both reading directions compile, and progress artifacts are committed. PDF page count alone is not a completion signal.
