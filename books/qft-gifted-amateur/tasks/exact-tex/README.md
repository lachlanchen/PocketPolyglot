# Quantum Field Theory for the Gifted Amateur Exact TeX Task

Retype Lancaster and Blundell, Quantum Field Theory for the Gifted Amateur, as a pocket-size TeX book. This is a formula-dense physics textbook: all inline/display equations, Feynman diagrams, examples, exercises, footnotes, tables, captions, appendices, and references must be preserved page by page. Mathpix whole-PDF OCR is required as the first pass; plain pdftotext is only a navigation aid and must not be trusted for formulas.

This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.

Required order:

1. Render page images from the exact source PDF.
2. Run Mathpix OCR for every content page, especially formula-heavy pages.
3. Review each page against the image and correct formulas, theorem labels, figures, and captions.
4. Assemble `build/<book>-exact-pocket/source.tex` with `tex/textbook-pocket/book.tex`.
5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.

Do not start from `pdftotext` prose chunks for this book.
