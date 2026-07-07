# World Poetry Source Repair - 2026-07-07

Two poetry tasks were intentionally blocked because their fallback sources would
produce poor PDFs. They are now launchable from cleaner source structures.

| Book ID | Previous Problem | Repair |
| --- | --- | --- |
| `xu-zhimo-poems` | The local scanned PDF OCR was visibly garbled. | Mirrored Xu Zhimo Wikisource poem pages and extracted only poem-body HTML nodes. Author metadata, public-domain notices, and `猛虎集/序` are skipped. |
| `english-poetry-anthology` | The EPUB was treated as a mixed anthology fallback. | Identified the file as the Whitman bilingual volume and paired alternating English/Chinese TOC entries poem by poem. |

Local ignored source mirror:

- `resources/curated-books/world-poetry/xu-zhimo/poems-zh-wikisource/`

Updated task state:

- `books/xu-zhimo-poems/book-plan.json`: 50 clean Chinese-spine poem chunks.
- `books/english-poetry-anthology/book-plan.json`: 92 English-spine chunks from 51 paired Whitman poems.

The preparer now clears stale `blocked_reason` fields on successful preparation
and records exact paired poem references where available.
