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

Start the queue in tmux and inspect progress:

```sh
scripts/books/start_local_exact_pocket_queue_tmux.sh
python scripts/books/report_local_exact_pocket_queue.py
```
