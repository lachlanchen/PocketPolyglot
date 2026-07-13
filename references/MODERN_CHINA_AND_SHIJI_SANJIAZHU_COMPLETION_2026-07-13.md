# Modern China And Shiji Sanjiazhu Completion - 2026-07-13

## The Search for Modern China

Source:

`sources/world-history/modern-china/en/The Search for Modern China - Third Edition - Jonathan D Spence.pdf`

The source was converted through Marker to Markdown and then reconstructed as
real TeX. The final pocket edition is not a page-image facsimile. Prose remains
searchable text and 222 extracted figures are preserved. Four OCR-damaged table
regions were replaced by clipped vector regions from the source PDF rather than
publishing incorrect or overlapping reconstructed tables.

Outputs:

- Exact text edition: `build-pocket/search-for-modern-china/exact/book.pdf`
- A6 large-font pocket edition: `build-pocket/search-for-modern-china/pocket-large-font/book.pdf`
- Pocket pages: 1,757
- Missing-glyph warnings: 0
- Overfull boxes above 5 pt: 0
- Worst residual overfull box: 3.55698 pt

Nutstore copies:

- `NoSync/Projects/LinguaLeaf/search-for-modern-china/exact/`
- `NoSync/Projects/LinguaLeaf/search-for-modern-china/pocket-large-font/`
- `Share/PocketBooks/Search for Modern China/`

## Shiji Sanjiazhu Comment-Aware Edition

This is an additive project. It reuses the 4,622 existing Shiji base chunks and
does not modify or delete the old JSON. Commentary is stored in a sidecar keyed
to stable base-unit identifiers and rendered after the wenyan main text and
before the Japanese and modern-Chinese layers.

Commentary style:

- Explicit labels: `注·集解`, `注·索隱`, and `注·正義`
- Intermediate 10.4 pt type with 14.9 pt leading
- Pinyin retained
- No grammar color on commentary; grammar color remains available on main text

Alignment evidence:

- Wikisource pages: 131
- Base units: 34,539
- Extracted notes: 17,825
- Safely aligned notes: 16,562
- Unmatched notes: 1,263
- Exact-anchor match rate: 92.9144%

The unmatched notes are preserved in the review queue and are not guessed into
the book. Therefore this output is a verified-commentary partial edition, not a
claim that every source note has been aligned.

Outputs:

- Color: `build/shiji-sanjiazhu-comment-aware/maximum-language-large-font/wenyan-main-jp-zh/color/史記三家注（本文・日本語・現代中文）・大字版・彩色.pdf`
- Black-white: `build/shiji-sanjiazhu-comment-aware/maximum-language-large-font/wenyan-main-jp-zh/blackwhite/史記三家注（本文・日本語・現代中文）・大字版・黑白.pdf`
- Each edition: 7,725 A6 pages
- Overfull warnings: 0

Both editions were copied and hash-verified under:

- `NoSync/Projects/LinguaLeaf/shiji-sanjiazhu-comment-aware/`
- `Share/LinguaLeaf/color/`
- `Share/LinguaLeaf/blackwhite/`

No ZhJpBook generation queue was restarted after the system reboot.
