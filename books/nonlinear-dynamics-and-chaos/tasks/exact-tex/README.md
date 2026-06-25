# Nonlinear Dynamics and Chaos Exact TeX Task

Retype Strogatz, Nonlinear Dynamics and Chaos, as a pocket-size TeX book. Equations, figures, captions, examples, exercises, and section numbering must be preserved. The Chinese PDF is a second-edition translation and should be used as a reference, not as a replacement for the English exact source.

This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.

Required order:

1. Render page images from the exact source PDF.
2. Run Mathpix OCR for every content page, especially formula-heavy pages.
3. Review each page against the image and correct formulas, theorem labels, figures, and captions.
4. Assemble `build/<book>-exact-pocket/source.tex` with `tex/textbook-pocket/book.tex`.
5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.

Do not start from `pdftotext` prose chunks for this book.
