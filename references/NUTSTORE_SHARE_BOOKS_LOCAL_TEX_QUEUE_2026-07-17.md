# Nutstore Share Books Local TeX Queue - 2026-07-17

This queue converts the eight books copied from
`/home/lachlan/Nutstore Files/Share/books/` into editable TeX, an exact review
PDF, and a pocket-size large-font PDF. It does not call Mathpix and does not
accept a facsimile or page-image-only body as completion.

Queue:
`data/source-plan/nutstore-share-books-local-exact-queue.json`

## Books

| Order | Book ID | Source kind | Source pages | Extraction route |
| ---: | --- | --- | ---: | --- |
| 1 | `history-of-western-philosophy-russell-local-exact` | EPUB | 97 HTML documents | EPUB -> Pandoc -> TeX |
| 2 | `theoretical-minimum-classical-mechanics-local-exact` | scan-only PDF | 259 | Marker/Surya OCR shards -> Markdown/math/media -> TeX |
| 3 | `theoretical-minimum-quantum-mechanics-local-exact` | PDF with text layer | 357 | Marker/Surya structured shards -> TeX |
| 4 | `theoretical-minimum-general-relativity-local-exact` | PDF with text layer | 386 | Marker/Surya structured shards -> TeX |
| 5 | `elements-of-information-theory-local-exact` | PDF with text layer | 774 | Marker/Surya structured shards -> TeX |
| 6 | `first-course-in-string-theory-local-exact` | PDF with text layer | 697 | Marker/Surya structured shards -> TeX |
| 7 | `essentials-of-computational-chemistry-local-exact` | PDF with text layer | 607 | Marker/Surya structured shards -> TeX |
| 8 | `introduction-to-computational-chemistry-local-exact` | PDF with text layer | 661 | Marker/Surya structured shards -> TeX |

## Output Contract

Each successful task writes:

- `build-pocket/<book-id>/exact/tex/book.tex`
- `build-pocket/<book-id>/exact/book.pdf`
- `build-pocket/<book-id>/pocket-large-font/tex/book.tex`
- `build-pocket/<book-id>/pocket-large-font/book.pdf`
- `build-pocket/<book-id>/review/status.json`
- source-page shard logs and extraction evidence under
  `build-pocket/<book-id>/work/marker-shards/`

Technical completion requires real generated text, a table of contents,
recognized math, preserved figure references, successful two-pass XeLaTeX,
source-to-output text coverage evidence where the source has a text layer, and
bounded overfull-line warnings. A failed structured extraction blocks the task;
it does not fall back to `pdftotext` and falsely claim that equations and figures
were preserved.

## Commands

Run or resume the queue:

```sh
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json \
  --continue-on-blocked
```

Run one book:

```sh
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json \
  --book-id elements-of-information-theory-local-exact
```

Marker shards are resumable. Re-running without `--force` reuses completed
source-page shards and regenerates only the unfinished portion.

Rebuild TeX and both PDFs from cached extraction without rerunning OCR:

```sh
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/nutstore-share-books-local-exact-queue.json \
  --rebuild-complete
```

Start the queue in tmux and inspect progress:

```sh
scripts/books/start_local_exact_pocket_queue_tmux.sh
python scripts/books/report_local_exact_pocket_queue.py
```

## Final Result

All eight tasks completed on 2026-07-17 using only the local
Marker/Surya/Pandoc/XeLaTeX toolchain. No Mathpix or language-model call was
used.

| Book | Exact pages | Pocket pages | Figures | Math blocks | Source text coverage | Worst overflow exact / pocket |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| History of Western Philosophy | 864 | 1548 | 14 | 0 | EPUB | 0.00 / 0.00 pt |
| Theoretical Minimum: Classical Mechanics | 232 | 359 | 69 | 1299 | scan-only | 0.00 / 0.00 pt |
| Theoretical Minimum: Quantum Mechanics | 295 | 460 | 46 | 1781 | 1.0753 | 0.00 / 0.00 pt |
| Theoretical Minimum: General Relativity | 383 | 605 | 131 | 1068 | 0.9911 | 0.00 / 2.08 pt |
| Elements of Information Theory | 975 | 1513 | 174 | 9983 | 0.9982 | 7.78 / 11.49 pt |
| A First Course in String Theory | 1036 | 1633 | 142 | 11655 | 0.9852 | 8.42 / 8.17 pt |
| Essentials of Computational Chemistry | 919 | 1431 | 134 | 2517 | 0.9795 | 8.85 / 15.18 pt |
| Introduction to Computational Chemistry | 1183 | 1857 | 167 | 4611 | 0.9882 | 14.42 / 13.16 pt |

Final validation covered all 16 generated PDFs:

- 16/16 passed `qpdf --check`.
- 16/16 contain a table of contents and PDF outlines.
- 16/16 contain substantial editable TeX bodies rather than page images.
- No missing-glyph warnings were detected.
- Every overfull line remained below the queue's 18 pt acceptance bound.
- Representative title, contents, middle, end, equation, table, and figure
  pages were visually inspected.

The scan-only Classical Mechanics source was structurally and visually
audited, but its text cannot receive the same text-layer coverage comparison as
the other technical PDFs. Its source-page shard evidence remains under the
book's `work/marker-shards/` directory.

## Nutstore Copy

Verified copies were written without changing the original source folder:

`/home/lachlan/Nutstore Files/Share/PocketBooks/LocalExact/`

Each book folder contains `exact/book.pdf`, `exact/book.tex`,
`pocket-large-font/book.pdf`, `pocket-large-font/book.tex`, and
`review/status.json`. All 16 PDFs and 16 TeX copies were byte-compared with the
build outputs; the copied PDFs also passed `qpdf --check`.
