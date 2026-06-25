# Game Theory Exact TeX Task

Retype Osborne and Rubinstein, A Course in Game Theory, as a pocket-size TeX book. All definitions, propositions, payoff matrices, symbols, equations, and references must match the source. The Chinese PDF is reference material but has almost no embedded text, so OCR/polish is required before relying on it for translated editions.

This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.

Required order:

1. Render page images from the exact source PDF.
2. Run Mathpix OCR for every content page, especially formula-heavy pages.
3. Review each page against the image and correct formulas, theorem labels, figures, and captions.
4. Assemble `build/<book>-exact-pocket/source.tex` with `tex/textbook-pocket/book.tex`.
5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.

Do not start from `pdftotext` prose chunks for this book.
