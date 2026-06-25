# Chaos: Making a New Science Exact TeX Task

Retype James Gleick, Chaos: Making a New Science, as a pocket-size TeX book. This is less equation-dense than the textbooks, but figures, captions, quotations, section starts, and occasional formulas still need page-faithful preservation.

This is not a prose translation task. Convert the source PDF page by page into reviewed TeX.

Required order:

1. Compile the open-source facsimile pocket TeX/PDF first.
2. Render page images from the exact source PDF when editable review starts.
3. OCR/retype pages only when needed for editable TeX; do not guess formulas from plain text.
4. Review each editable page against the image and correct formulas, theorem labels, figures, and captions.
5. Only after exact TeX passes validation, derive EN-JP-ZH multilingual editions.

Do not start from `pdftotext` prose chunks for this book. For no-Mathpix output, use the facsimile compiler.
