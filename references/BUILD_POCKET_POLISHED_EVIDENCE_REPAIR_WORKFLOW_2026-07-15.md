# Build Pocket Polished Evidence Repair Workflow

Date: 2026-07-15

This workflow repairs a technical pocket-book conversion without repeatedly
regenerating already-valid text. It preserves source evidence, accepted model
outputs, formulas, figures, tables, and resumability.

## Core Rule

Use deterministic repairs for transport, TeX, geometry, and layout defects.
Call the model only for source-grounded language work that cannot be resolved
from existing accepted output. A failed layout gate must not trigger another
translation pass.

## Repair Sequence

1. Locate the defect in the generated PDF and exact TeX.
2. Verify the intended content against the corresponding source PDF page.
3. Record exact, count-checked source corrections in
   `build-pocket/tasks/source-queue-2026-07-12.json` under
   `polish_source_replacements`.
4. Use a source-page crop only where a diagram or visually structured object
   cannot be represented faithfully as text/math. Keep normal prose and simple
   tables as real TeX.
5. Re-run `prepare_build_pocket_polished.py --force` with the same chunk
   geometry. Content-addressed accepted-segment caches should be reused.
6. Normalize deterministic transport defects before assembly:
   ANSI styling, invalid control bytes, Unicode super/subscripts, short plain
   math fragments, and TeX environments spanning segment boundaries.
7. Fit compact simple OCR tables deterministically. Small non-page-breaking
   tables are rendered as width-fitted `tabular`; multipage tables remain
   `longtable`.
8. Insert the cover at the document paper size. Never use `fitpaper=true`,
   which lets image pixel dimensions replace the A6 page geometry.
9. Compile and require all of the following evidence:
   - valid current-manifest chunk coverage;
   - source object inventory preserved;
   - searchable text present;
   - no TeX error markers;
   - no overfull boxes above the configured threshold;
   - A6 dimensions on the cover and interior pages;
   - no unknown or fallback Japanese furigana tokens;
   - visual inspection of the cover and every repaired table/figure page.
10. Sync only after `status.json` reports `complete`.

## Commands

```sh
python scripts/books/prepare_build_pocket_polished.py \
  --book-id BOOK_ID --force \
  --max-chars 7000 --max-segments 32

python scripts/books/assemble_build_pocket_polished.py BOOK_ID

python scripts/books/sync_build_pocket_polished_to_nutstore.py BOOK_ID
```

For a persistent queue:

```sh
tmux new-session -d -s zhjpbook-pocket-polished \
  "cd /home/lachlan/ProjectsLFS/ZhJpBook && \
   python -u scripts/books/run_build_pocket_polished_queue.py \
     --queue build-pocket-polished/tasks/QUEUE.json \
     --status build-pocket-polished/status-QUEUE.json \
     --workers 2 --model gpt-5.6-sol --reasoning low \
     --retries 2 --review-retries 2 --retry-passes 2"
```

## Black Hole War Validation Record

- 109/109 chunks valid.
- 4,381 source segments preserved.
- 232/232 source figures present.
- 59,694 Japanese ruby annotations, with no fallback or unknown tokens.
- 1,210 searchable A6 pages.
- Zero overfull boxes after compact-table fitting.
- Cover and repaired constants/S-matrix pages visually inspected.
- Final PDF synced to `Nutstore Files/Share/PocketPolished/`.
