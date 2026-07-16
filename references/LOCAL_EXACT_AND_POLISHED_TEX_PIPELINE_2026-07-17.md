# Local Exact And Evidence-Gated TeX Pipeline - 2026-07-17

## Purpose

This document records the reusable workflow that produced the high-quality
exact and pocket editions under `build-pocket/`, and distinguishes it from the
optional bilingual editorial workflow under `build-pocket-polished/`.

The exact conversion can run entirely locally. It does not require Mathpix or
a language-model call. The editorial stage is separate and invokes a model only
for source-grounded prose correction or translation that deterministic code
cannot perform.

## Why The Local Exact Output Is Strong

1. **The original is immutable.** Source EPUB/PDF files are copied into ignored
   storage and never edited. Every result remains traceable to a source hash.
2. **The route matches the source.** EPUB uses Pandoc structure directly;
   born-digital PDFs use Marker/Surya layout extraction; scan-only PDFs use the
   same pipeline with OCR enabled.
3. **PDF work is page-sharded and resumable.** A failed page range is rerun
   without discarding successful extraction or repeating a whole book.
4. **Technical objects remain first-class.** Equations become TeX math where
   reliable. Figures, diagrams, dense tables, and ambiguous chemistry or music
   objects remain source-backed image assets instead of being guessed.
5. **Repairs are deterministic first.** Unicode normalization, malformed TeX,
   table widths, page-break fragments, image paths, and display-math fitting are
   fixed by code. Book-specific corrections live in count-checked JSON ledgers.
6. **Exact precedes pocket.** Exact and pocket editions are built from the same
   reviewed body. Pocket layout changes geometry and typography, not content.
7. **Completion is evidence-gated.** A successful process exit is insufficient.
   The pipeline checks source coverage, object inventories, TOC/outlines,
   searchable text, missing glyphs, TeX errors, overflow, and representative
   rendered pages.
8. **Cached rebuilds are cheap.** Layout or sanitizer changes can regenerate
   TeX/PDF from cached extraction using `--rebuild-complete`; OCR is not rerun.

## Local Exact Pipeline

Primary implementation:

`scripts/books/build_pocket_tex_queue.py`

| Phase | Main code responsibility | Durable evidence |
| --- | --- | --- |
| Probe | Classify EPUB, MOBI, born-digital PDF, or scanned PDF | source hash, page count, text and image profile |
| Extract | EPUB repair/Pandoc or Marker/Surya page shards | `work/marker-shards/`, logs, merged Markdown |
| Normalize | Repair OCR Unicode, HTML fragments, math, arrays, URLs, and tables | normalized Markdown and TeX |
| Source repair | Apply exact cardinality-checked JSON replacements and source crops | `books/<id>/local-exact-tex-fixes.json` |
| Render | Build exact and pocket TeX from one content body | `exact/tex/book.tex`, `pocket-large-font/tex/book.tex` |
| Compile | Run repeatable XeLaTeX passes | PDFs and compile logs |
| Validate | Compare source/output structure and inspect TeX/PDF health | `review/status.json` |
| Export | Copy only accepted artifacts and verify byte identity | Nutstore exact/pocket tree |

Supporting commands:

| Script | Role |
| --- | --- |
| `scripts/books/report_local_exact_pocket_queue.py` | Reports manifest-aware extraction and exact/pocket completion. |
| `scripts/books/start_local_exact_pocket_queue_tmux.sh` | Starts a persistent, observable local queue. |
| `data/source-plan/nutstore-share-books-local-exact-queue.json` | Declares sources, validation profiles, repairs, crops, and overflow limits. |
| `references/NUTSTORE_SHARE_BOOKS_LOCAL_TEX_QUEUE_2026-07-17.md` | Records the completed eight-book run and its validation evidence. |

Run or resume:

```sh
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json \
  --continue-on-blocked
```

Rebuild from cached extraction after a code or layout improvement:

```sh
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json \
  --rebuild-complete
```

Report progress:

```sh
python scripts/books/report_local_exact_pocket_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json
```

## Tools

| Tool | Use |
| --- | --- |
| Marker + Surya | Page-aware local layout extraction and OCR. |
| Pandoc | EPUB/Markdown to structured TeX conversion. |
| Poppler (`pdfinfo`, `pdftotext`, `pdfimages`, `pdftoppm`) | Source probing, evidence extraction, and rendered-page inspection. |
| PyMuPDF | Precise source-page crops for difficult figures, equations, and tables. |
| XeLaTeX | Unicode-capable exact and A6 pocket compilation. |
| `qpdf` | PDF structural integrity checks. |
| ImageMagick/contact sheets | Fast visual review across representative pages. |
| JSON repair ledgers | Auditable source-backed exceptions without changing OCR caches. |

Mathpix was not used for the Nutstore Share eight-book conversion. Existing
Mathpix output is used only as immutable source evidence in a separate older
technical-polish queue.

## Optional Evidence-Gated Editorial Polish

The editorial queue adds corrected English plus readable Japanese while
preserving every protected technical object. It deliberately does not rerun
OCR or regenerate accepted segments.

| Script | Responsibility |
| --- | --- |
| `prepare_build_pocket_polished.py` | Flatten immutable exact TeX, normalize page boundaries, and create stable chunks/segments. |
| `pocket_polished_common.py` | Protect TeX/math, compute signatures, validate numbers/objects, and compare inventories. |
| `codex_pocket_polish_worker.py` | Reuse segment caches, request only unresolved segments, validate, review, and persist metrics. |
| `run_build_pocket_polished_queue.py` | Run books sequentially and workers in parallel with bounded retry passes. |
| `pocket_polished_resource_gate.py` | Reduce concurrency during load, memory, or network pressure. |
| `assemble_build_pocket_polished.py` | Reassemble English-main/Japanese-secondary TeX, add furigana, fit objects, compile, and validate. |
| `ensure_textless_pocket_polished_cover.py` | Ensure a textless image with deterministic title overlay. |
| `sync_build_pocket_polished_to_nutstore.py` | Export only status-verified complete books. |
| `report_build_pocket_polished.py` | Report valid chunks, retries, cache hits, and model-call amplification. |

The key efficiency rule is segment-level retry: accepted segments stay cached,
and a validator failure retries only the affected segment. Protected equations,
figures, tables, labels, numbers, and TeX commands are compared
deterministically rather than repeatedly regenerated by a model.

## Acceptance Gate

A book is complete only when all applicable checks pass:

- current-manifest coverage is complete;
- exact and pocket TeX/PDF exist;
- TeX body is real editable content, not page-image facsimile output;
- source figure/math/table inventories remain present;
- source text coverage is plausible where a text layer exists;
- `qpdf --check` succeeds;
- TOC and PDF outlines exist;
- no fatal TeX or missing-glyph errors remain;
- overflow remains below the declared threshold and hotspots are reviewed;
- representative title, TOC, prose, equation, table, figure, and final pages
  pass visual inspection;
- requested Nutstore copies match the accepted build artifacts.

## Skills

- `ocr-book-polisher`: source probing, OCR route selection, structural repair,
  technical-object preservation, TeX compilation, and evidence validation.
- `pocketpolyglot-bookmaker`: aligned multilingual data, Japanese furigana,
  large-font pocket rendering, resumable queues, and Nutstore export rules.
- `skill-creator`: keeps the general workflow in reusable skill references
  instead of embedding book-specific exceptions in the skill itself.

The canonical reusable skill source is:

`/home/lachlan/ProjectsLFS/LazySkills/skills/ocr-book-polisher/`

## Polish Queue Status

Snapshot taken on 2026-07-17. No polish worker process is currently active.
The Studio runtime field showing one active call is stale; process and tmux
inspection found no running polish queue.

### Susskind Editorial Queue

| Book | Status |
| --- | --- |
| The Black Hole War | Complete; final English-main/Japanese-secondary PDF exists. |
| Black Holes, Information and the String Theory Revolution | Complete; 39/39 reporter chunks. |
| The Cosmic Landscape | 129/130 reporter chunks; one chunk remains and no assembled final PDF exists. |

### Seven-Book Technical Polish Queue

| Book | Status |
| --- | --- |
| Game Theory | Complete and assembled. |
| Game Theory 101 | Complete and assembled. |
| Quantum Field Theory for the Gifted Amateur | Complete and assembled. |
| Chaos: Making a New Science | Complete and assembled. |
| Nonlinear Dynamics and Chaos | 227/235 chunks; 3337/3345 segments accepted; eight evidence defects remain. |
| Berklee Music Theory Book 1 | Waiting; 0/25 chunks and 0/391 segments. |
| Music Theory for Guitarists | Waiting; 0/65 chunks and 0/1030 segments. |

Aggregate technical progress is 12,021/13,450 accepted segments, or 89.38%.
The queue is blocked, not running. The eight Nonlinear Dynamics failures are
specific source/OCR defects, including malformed protected equations, fused
index entries, truncated source prose, and two Japanese-language validation
failures. They require source-backed repair rules before resumption; blind
whole-chunk retry would waste tokens and could lower quality.

PocketPolyglot Studio also contains many historical blocked retry job records.
Those records do not represent concurrent live workers and should be cleaned or
compacted before using Studio auto-retry again.
