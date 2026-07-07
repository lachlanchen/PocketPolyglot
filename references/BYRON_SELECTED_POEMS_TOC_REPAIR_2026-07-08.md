# Byron Selected Poems TOC Repair - 2026-07-08

The original Byron build was complete but structurally noisy. PDF extraction
promoted publisher matter, running page headers, page numbers, glossary pages,
and OCR-spaced headings such as `604 LORD BYRON` and
`T A L E S - T H E GIAOUR 603` into chapter titles. This produced a very long
and misleading table of contents.

## Fix

Added `scripts/interlinear/repair_byron_selected_poems_toc.py`.

The script does not regenerate translation, ruby, pinyin, or grammar data. It
rewrites only chapter metadata in the Byron manifest, source chunk list, and
local generated chunk JSON files, collapsing 836 chunks into 31 logical TOC
chapters:

- front matter and source contents;
- general and work-specific introductions;
- `Childe Harold's Pilgrimage`, `Don Juan`, `The Giaour`, `The Corsair`;
- satire and lyric sections;
- notes, glossary, and index appendices.

Run:

```sh
python3 scripts/interlinear/repair_byron_selected_poems_toc.py
```

The script creates a timestamped backup under
`books/byron-selected-poems/work/trilingual/chunks/` before editing local chunk
metadata.

## Verification

```sh
python3 scripts/interlinear/report_trilingual_progress.py \
  --manifest books/byron-selected-poems/work/trilingual/chunks/manifest.json \
  --chunk-dir books/byron-selected-poems/work/trilingual/interlinear/chunks

bash scripts/interlinear/compile_trilingual_en_notes_book.sh \
  --book-id byron-selected-poems --color-mode color

python3 scripts/interlinear/export_max_language_shiji_catalog.py \
  --book byron-selected-poems --force-compile --force-compress
```

After repair, the max-language TOC contains 31 clean entries instead of 194
OCR-derived entries. The cleaned PDFs were synced to Nutstore Share and Projects.
