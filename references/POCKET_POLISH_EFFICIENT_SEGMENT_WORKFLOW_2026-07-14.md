# Efficient Segment-Level Pocket Polish Workflow

Date: 2026-07-14

## Goal

Produce evidence-preserving English/Japanese TeX pocket books without repeatedly
regenerating an entire chunk when one local segment fails. Figures, equations,
tables, diagrams, references, labels, and technical notation remain immutable
unless the source evidence proves an exact repair.

## Previous Amplification

The former workflow regenerated a 6,000-7,000-character chunk after any
validator complaint. False numerical and math-inventory complaints therefore
multiplied writer and reviewer calls even when nearly every segment was already
correct.

Representative old Susskind results:

| Chunk | Result | Writer calls | Reviewer calls | Reported tokens |
| --- | --- | ---: | ---: | ---: |
| `p00003` | Accepted after retries | 3 | 3 | 129,726 |
| `p00033` | Failed at 25/29 | 3 | 3 | 114,154 |

## Current Design

1. **Normalize before prompting.** Preserve an untouched upstream flattened TeX
   file, create a separate polish input, and record every deterministic source
   normalization in `source/normalizations.json`.
2. **Protect source objects.** Equations and non-prose TeX remain outside model
   rewriting. Inline objects use immutable placeholders.
3. **Reconstruct English deterministically.** The model returns Japanese plus
   exact English repair patches. It does not repeat the English source or its
   source hash.
4. **Accept independently by segment.** Deterministically valid segments go to
   semantic review. Accepted segments are cached immediately.
5. **Repair in the reviewer response.** A reviewer can return a complete local
   correction. The program validates and promotes it without another writer
   call.
6. **Retry only unresolved segments.** A later writer pass receives only the
   remaining segment IDs and their exact feedback.
7. **Use content-addressed segment IDs.** Rechunking or removing an earlier page
   artifact does not invalidate unrelated reviewed content.
8. **Reuse by source hash.** Cache fallback migrates an accepted segment to its
   new content-addressed ID after a manifest change.
9. **Compare the correct invariant.** English protected placeholders retain
   exact order. Japanese must retain the exact placeholder multiset but may
   reorder complete expressions for natural grammar.
10. **Recover interrupted review work.** A deterministically valid
    `pending-review` segment is located by source hash and sent directly to the
    reviewer after a restart. A completed semantic rejection excludes that
    candidate from recovery, so the same rejected text cannot loop.
11. **Migrate legacy evidence locally.** Old ambiguous spacing records such as
    `"." -> ". "` are replaced by the deterministic exact-substring evidence
    already derived from the immutable source, without a model call.
12. **Bound queue recovery.** A second queue pass is allowed only for unresolved
    chunks; accepted segment caches prevent whole-chunk regeneration.

## Source Normalization Rules

Automatic joins are intentionally narrow:

- a formatted running header between two halves of one sentence;
- two substantial prose paragraphs where the first has no terminal punctuation
  and the second begins with a lowercase continuation;
- no joining of captions, headings, equations, figures, tables, epigraph
  attributions, or structural TeX;
- task-local exact removals/replacements require an expected match count and are
  logged with hashes.

The Susskind pilot removed confirmed `Preface` and `Strings` running headers and
joined split phrases such as `proper spatial distance`. An initially broad rule
that could match section/equation text was rejected during the audit and replaced
with exact structural guards before the full queue started.

## Measured Pilot

After the fixes:

| Chunk | Result | Writer calls | Reviewer calls | Cache hits | Reported tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| normalized `p00002` | 7/7 accepted | 1 | 1 | 2 | 45,231 |
| normalized `p00003` | 19/19 accepted | 1 | 1 | 0 | 53,260 |
| migrated `p00004` | 32/32 accepted | 0 | 0 | 32 | 0 |
| repaired `p00033` | 29/29 accepted | 1 | 1 | 24 | 39,411 |
| recovered `p00005` | 30/30 accepted | 0 | 1 | 29 | 19,032 |
| source-fixed `p00008` | 32/32 accepted | 1 | 1 | 31 | 36,160 |

For `p00033`, the reviewer corrected one Japanese term in the same response. No
second writer call was needed. The prior six-call failure became a two-call
success while preserving all protected objects.

For `p00005`, an interrupted but deterministically valid candidate went directly
to semantic review; the reviewer corrected the sole unresolved segment in the
same response. For `p00008`, 31 accepted segments were reused while only the
one source segment with missing coordinate prime marks was regenerated. The
repair was grounded by the immediately adjacent equations 3.2.5 and 3.2.6 and
recorded as an exact, count-checked source normalization.

## Validation

```sh
python -m py_compile \
  scripts/books/pocket_polished_common.py \
  scripts/books/prepare_build_pocket_polished.py \
  scripts/books/codex_pocket_polish_worker.py \
  scripts/books/run_build_pocket_polished_queue.py \
  scripts/books/assemble_build_pocket_polished.py \
  scripts/books/report_build_pocket_polished.py

python scripts/books/test_pocket_polished_pipeline.py

python scripts/books/report_build_pocket_polished.py \
  --queue build-pocket-polished/tasks/susskind-pilot-queue.json
```

The 21 focused checks cover source-hash cache gating, cache migration,
content-addressed IDs, pending-review recovery, semantic-rejection exclusion,
legacy evidence migration, protected equations, Japanese placeholder
reordering, grounded English repairs, reviewer correction sanitization,
page-header removal, split-prose joins, and exclusions for headings, equations,
captions, and epigraphs.

## Running Queue

```sh
QUEUE=build-pocket-polished/tasks/susskind-pilot-queue.json \
STATUS=build-pocket-polished/status-susskind.json \
WORKERS=2 RETRY_PASSES=2 MODEL=gpt-5.6-sol REASONING=low \
bash scripts/books/start_build_pocket_polished_tmux.sh \
  zhjpbook-susskind-polish-v3-queue
```

Model calls come only from the two worker processes. The tmux controller,
coverage reporter, deterministic validator, cache, assembler, and compilation
checks do not consume model tokens.
