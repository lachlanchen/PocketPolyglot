# Quantum Field Theory for the Gifted Amateur Exact TeX Task

Retype Lancaster and Blundell, Quantum Field Theory for the Gifted Amateur, as a pocket-size TeX book. This is a formula-dense physics textbook: all inline/display equations, Feynman diagrams, examples, exercises, footnotes, tables, captions, appendices, and references must be preserved page by page. The open-source facsimile path should be generated first. Mathpix whole-PDF OCR is only needed for an editable/reflowed TeX pass; plain pdftotext is a navigation aid and must not be trusted for formulas.

This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.

Required order:

1. Compile the open-source facsimile pocket TeX/PDF first.
2. Render page images from the exact source PDF when editable review starts.
3. OCR/retype pages only when needed for editable TeX; do not guess formulas from plain text.
4. Review each editable page against the image and correct formulas, theorem labels, figures, and captions.
5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.

Do not start from `pdftotext` prose chunks for this book. For no-Mathpix output, use the facsimile compiler.
