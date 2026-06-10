# World Literature OCR Check

This report records the OCR sidecars and promotion decisions for the prepared
EN/ZH/JP world-literature queue. The rule is: always OCR PDF inputs for evidence
and review, but only promote OCR into the task Markdown when embedded text is
missing or clearly weaker.

## OCR Evidence

| Book | OCR Sidecars | Validation | Task Decision |
| --- | --- | --- | --- |
| Wuthering Heights / 呼啸山庄 | `books/wuthering-heights/markdown/zh.ocr-polished.md` | 359 pages, 219,190 chars, 8 suspect pages | Keep embedded Chinese PDF text as `zh.md`; OCR is reference only. |
| One Hundred Years of Solitude / 百年孤独 | `books/one-hundred-years-of-solitude/markdown/en.ocr-polished.md` | 202 pages, 648,693 chars, 0 suspect pages | Keep embedded English PDF text as the spine; OCR is reference only. |
| The Count of Monte Cristo / 基督山伯爵 | `books/the-count-of-monte-cristo/markdown/zh.ocr-polished.md` | 1,622 pages, 763,240 chars, 18 suspect pages | Keep embedded Chinese PDF text as `zh.md`; OCR is reference only. |
| Notre-Dame de Paris / 巴黎圣母院 | `books/notre-dame-de-paris/markdown/en.ocr-polished.md`, `books/notre-dame-de-paris/markdown/zh.ocr-polished.md` | EN: 464 pages, 842,186 chars, 0 suspect pages. ZH: 266 pages, 127,422 chars, 39 suspect pages. | Keep embedded English as spine. Promote polished Chinese OCR because embedded Chinese text is insufficient. |
| Les Misérables / 悲惨世界 | `books/les-miserables/markdown/en.ocr-polished.md`, `books/les-miserables/markdown/zh.ocr-polished.md` | EN: 1,652 pages, 2,538,607 chars, 1 suspect page. ZH: 1,149 pages, 784,337 chars, 29 suspect pages. | Keep embedded English and Chinese PDF text as task Markdown; OCR sidecars are references only. |

## Prepared Task Coverage

| Book | Chunks | English Sections | Chinese Reference Sections |
| --- | ---: | ---: | ---: |
| Wuthering Heights | 329 | 62 | 20 |
| One Hundred Years of Solitude | 361 | 20 | 1 |
| The Count of Monte Cristo | 1,143 | 117 | 122 |
| Notre-Dame de Paris | 471 | 63 | 8 |
| Les Misérables | 1,630 | 438 | 369 |

## Future Policy

- Run OCR for every PDF source and keep `*.ocr-polished.md` as a review sidecar.
- Prefer embedded PDF text or EPUB text when it is complete and clean.
- Promote OCR only when `pdftotext` has insufficient content or when
  `POCKETPOLYGLOT_PREFER_EN_OCR=1` / `POCKETPOLYGLOT_PREFER_ZH_OCR=1` is set.
- Apply aggressive OCR-noise removal only to OCR-derived Chinese text, not to
  embedded Chinese text, so legitimate Latin or French phrases are preserved.
- Re-run `python -m py_compile` on OCR and preparation scripts after pipeline
  edits.
