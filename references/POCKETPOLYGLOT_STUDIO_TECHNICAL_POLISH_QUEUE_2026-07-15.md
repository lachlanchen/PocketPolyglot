# PocketPolyglot Studio Technical Polish Queue - 2026-07-15

## Purpose

This queue converts seven existing real-TeX reconstructions into validated
large-font pocket books. It never substitutes page images for editable TeX.
Equations, figures, tables, diagrams, flowcharts, labels, references, captions,
and music notation remain protected source structures. Codex edits only the
segments that require prose correction or Japanese translation.

## Queue

| Order | Book ID | Exact source | Route | Chunks | Review segments |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | `game-theory-mathpix-exact-book` | `build/game-theory-mathpix-exact-book` | Mathpix exact | 168 | 1,844 |
| 2 | `game-theory-101-mathpix-exact-book` | `build/game-theory-101-mathpix-exact-book` | Mathpix exact | 101 | 1,583 |
| 3 | `qft-gifted-amateur-mathpix-exact-book` | `build/qft-gifted-amateur-mathpix-exact-book` | Mathpix exact | 278 | 4,079 |
| 4 | `chaos-making-new-science-mathpix-exact-book` | `build/chaos-making-new-science-mathpix-exact-book` | Mathpix exact | 124 | 1,187 |
| 5 | `nonlinear-dynamics-and-chaos-mathpix-exact-book` | `build/nonlinear-dynamics-and-chaos-mathpix-exact-book` | Mathpix exact | 235 | 3,347 |
| 6 | `berklee-music-theory-book-1-local-exact-book` | `build/berklee-music-theory-book-1-local-exact-book` | Local hybrid exact | 25 | 391 |
| 7 | `tom-kolb-music-theory-guitarists-local-exact-book` | `build/tom-kolb-music-theory-guitarists-local-exact-book` | Local hybrid exact | 65 | 1,030 |

Total prepared work: 996 chunks and 13,461 review segments. The preparation
stage joined 465 evidence-clear prose continuations split only by exact-source
page-break commands. This removes fragmentary translation units without
changing equations or other protected objects.

## Runtime Contract

- Source queue: `data/source-plan/technical-exact-polished-queue.json`
- Prepared queue: `build-pocket-polished/tasks/studio-technical-seven-queue.json`
- Live status: `build-pocket-polished/status-studio-technical-seven.json`
- Outputs: `build-pocket-polished/<book-id>/`
- Export target: `/home/lachlan/Nutstore Files/Share/PocketPolished/`
- Model: `gpt-5.6-sol`, reasoning `low`
- Maximum active calls: 5
- Chunk limits: 7,000 characters and 16 review segments
- Writer retries: 2; reviewer retries: 2; queue retry passes: 2

The queue is launched as a Studio job, so tmux process lifetime, logs,
heartbeats, evidence, cancellation, and retry are recorded in SQLite. The
worker pool uses a shared adaptive gate. The gate reduces active calls under
network, load, or memory pressure instead of starting duplicate queues or
letting every worker retry independently.

## Token-Efficiency Rules

1. Exact source TeX is immutable and reused in place.
2. Segment cache keys include the protected source hash.
3. Reviewed legacy chunks are salvaged segment by segment before rechunking.
4. Accepted segments are never sent to the model again.
5. Validation errors identify the affected segment; retries do not regenerate
   a whole otherwise-correct chunk.
6. Structural checks are deterministic. Codex handles semantic correction and
   exceptional repair only.

The initial Game Theory smoke test accepted a 15-segment chunk with ten cache
hits, one writer request, and one reviewer request. This is the required
behavioral evidence for launching the full queue.

The first live batch also exposed two upstream defects instead of silently
translating them: a sentence split by `\\clearpage`, and a literal `.gif">`
fragment in the source PDF's preference-relation definition. The general
normalizer now joins only mid-sentence lowercase continuations across known
page-break commands. The book-specific missing definition and fused Pareto
punctuation are restored through cardinality-checked
`polish_source_replacements` in the source queue, using the local source page
and an alternate complete copy of the same edition as evidence. These repairs
remain auditable in each book's `source/normalizations.json`; they are not
hidden model guesses.

The post-repair smoke test for the affected chunk passed with five cache hits,
one newly requested segment, one writer call, and one reviewer call. No retry
was needed.

## Completion Evidence

A book is complete only when all current-manifest chunks and segments are
accepted, the assembled TeX compiles, the PDF is searchable, object inventories
remain complete, layout checks pass, a textless cover is injected with a
deterministic title overlay, and Nutstore sync succeeds. The aggregate Studio
job is complete only when all seven books satisfy those checks.

## Commands

```sh
./studio/pocketpolyglot run technical-pocket-polished-seven pocket.polish.queue \
  --param source_queue=data/source-plan/technical-exact-polished-queue.json \
  --param queue=build-pocket-polished/tasks/studio-technical-seven-queue.json \
  --param status=build-pocket-polished/status-studio-technical-seven.json \
  --param workers=5 \
  --param reasoning=low \
  --param adaptive=true \
  --param network_limit_mbps=100

./studio/pocketpolyglot status --project technical-pocket-polished-seven
./studio/pocketpolyglot logs JOB_ID
```
