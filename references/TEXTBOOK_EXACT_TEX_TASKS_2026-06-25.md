# Exact Textbook TeX Task Plan

Prepared at: 2026-06-25T05:04:18.139679+00:00

These textbooks are formula-heavy. They must be converted page-faithfully into TeX before any multilingual PocketPolyglot edition is generated.

The renderer target is the same pocket profile used by the current books: 105 mm x 148 mm, XeLaTeX, 10 pt document base, and the existing font scale.

| Book ID | Source pages | Content pages | Mathpix pages | Chinese reference | Task path |
| --- | ---: | ---: | ---: | --- | --- |
| `game-theory` | 373 | 370 | 370 | OCR/polish required | `books/game-theory/tasks/exact-tex/` |
| `nonlinear-dynamics-and-chaos` | 616 | 600 | 600 | embedded text usable | `books/nonlinear-dynamics-and-chaos/tasks/exact-tex/` |
| `qft-gifted-amateur` | 512 | 503 | 503 | OCR/polish required | `books/qft-gifted-amateur/tasks/exact-tex/` |

Future start order:

1. Run page-image rendering and Mathpix OCR workers against `tasks/exact-tex/pages.jsonl`.
2. Run Codex page review to produce `reviewed-pages/page-####.tex`.
3. Assemble the exact pocket TeX/PDF.
4. Split reviewed TeX into text/math nodes and generate EN-JP-ZH editions while copying formulas unchanged.

Mathpix API credentials are detected from `MATHPIX_APP_ID` and `MATHPIX_APP_KEY`. If unavailable in a later shell, use open-source OCR only for text and pause formula pages instead of guessing.
