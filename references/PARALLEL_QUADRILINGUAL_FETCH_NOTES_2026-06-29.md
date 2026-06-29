# Parallel Quadrilingual Fetch Notes

These notes record the safer fetch pattern for large LinguaLeaf/PocketPolyglot
classical-text runs such as `han-shu`, `sanguozhi`, and other
wenyan-main quadrilingual books.

## Lessons From Earlier Runs

- Trust manifest coverage, not PDF page count. A preview PDF may compile from
  partial JSON and still look plausible.
- Each worker must claim chunks atomically and write one chunk file at a time.
  Shared aggregate JSON is assembled only after chunk validation.
- Old claims must expire. At high concurrency a dead worker can otherwise hide a
  chunk indefinitely.
- `codex exec` should run with isolated prompt context for JSON fetches:
  `CODEX_EXEC_IGNORE_USER_CONFIG=1` and `CODEX_EXEC_IGNORE_RULES=1`.
- Use short Codex timeouts for small chunks. A stalled call is cheaper to retry
  than to let one worker block for hours.
- Low reasoning is acceptable for first-pass chunk fetch only when validation
  checks target-language presence and exact source preservation. Use medium or
  high later only for failed or semantically suspicious chunks.

## Safe 100-Worker Pattern

Use one tmux session and one canonical chunk directory. Workers coordinate
through atomic claim directories under `parallel-json/candidates/claims`.

Example:

```sh
WORKERS=100 \
MODEL=gpt-5.5 \
REASONING=low \
CLAIM_TTL_SECONDS=1800 \
CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 \
CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh han-shu zhjpbook-han-shu-100-low
```

Monitor with:

```sh
python scripts/interlinear/report_quadrilingual_progress.py \
  --manifest books/han-shu/work/quadrilingual/chunks/manifest.json \
  --chunks-jsonl books/han-shu/work/quadrilingual/chunks/chunks.jsonl \
  --chunk-dir books/han-shu/work/quadrilingual/interlinear/chunks
```

## Prompt Rules To Preserve

- Preserve `source_wenyan`, IDs, and order exactly.
- Ask for plain alignment JSON first, then promote locally to strict token JSON.
- Japanese must be modern Japanese with kana and inflection, not Han-only
  Chinese or kanbun.
- Chinese must be readable modern Chinese, not a second copy of wenyan except
  for names or titles.
- English should be clear and literal enough for study, using references only
  when they match the broad chapter window.
