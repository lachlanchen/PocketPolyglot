# Sengoku PDF-to-TeX OCR Completion - 2026-08-02

The PDF-gated Sengoku reference queue is complete. Each source was converted
to searchable, editable TeX and compiled in two layouts from the same reviewed
Markdown body:

- `exact/`: review edition on the source-oriented page profile.
- `pocket-large-font/`: pocket-size large-font edition.

These are real-text TeX books. No source page was embedded with
`\includepdf`, and no page-image facsimile was accepted as body content.
Source figures, maps, diagrams, tables that required visual preservation, and
their captions remain first-class assets referenced by the TeX.

| Book ID | Source pages | Exact pages | Pocket pages | Reviewed text chars | Retained figures |
| --- | ---: | ---: | ---: | ---: | ---: |
| `hideyoshi-berry` | 312 | 256 | 474 | 576,945 | 6 |
| `japan-emerging-premodern` | 497 | 572 | 980 | 1,053,097 | 19 |
| `giving-up-the-gun` | 140 | 112 | 170 | 141,774 | 52 |
| `war-in-japan-1467-1615` | 96 | 135 | 199 | 157,232 | 64 |
| `samurai-world-warrior` | 229 | 241 | 349 | 274,283 | 120 |
| `japonius-tyrannus` | 146 | 318 | 564 | 632,788 | 14 |
| `tokugawa-ieyasu-totman` | 221 | 200 | 351 | 379,138 | 20 |
| `history-japan-1334-1615` | 480 | 569 | 955 | 1,016,029 | 66 |
| `samurai-sourcebook` | 321 | 798 | 1,166 | 842,957 | 192 |

Each output is under `build-pocket/<book-id>/`:

```text
exact/tex/book.tex
exact/book.pdf
pocket-large-font/tex/book.tex
pocket-large-font/book.pdf
review/source-reviewed.md
review/status.json
```

## Source-Evidenced Repairs

- Restored six omitted source figures in *Hideyoshi* from explicit PDF crops.
- Preserved the periodization table in *Japan Emerging* and retained all other
  extracted figures.
- Removed scanner-watermark strips from *Tokugawa Ieyasu: Shogun* using an
  audited dimensional/source rule while retaining its 20 substantive figures.
- Reconstructed the source genealogy table and corrected localized OCR damage
  without changing the immutable extraction.
- Rebuilt *The Samurai Sourcebook* index by OCRing each source column in reading
  order, preserved its Japanese-family-name table and armour glossary as
  600-dpi source crops, removed one repetition hallucination, and corrected the
  systematic `samural`/`HERALORY` OCR substitutions with source evidence.

Task-specific corrections are data under
`data/source-plan/sengoku-history-source-fixes/`; raw OCR remains unchanged.

## Renderer Improvements

- Cross-process GPU locking prevents simultaneous Marker processes from
  exhausting VRAM.
- Generated media directories are reset before rendering so stale images
  cannot satisfy figure validation.
- Source-evidenced image exclusions are recorded and included in the retention
  denominator.
- CommonMark table line breaks survive Pandoc and are restored only inside TeX
  tables.
- Missing-character warnings block completion.
- Unnumbered Pandoc headings receive independent PDF destinations, preventing
  TOC entries from inheriting a preceding list or table target.

## Validation

- Queue result: `9 complete`, `0 blocked`.
- `qpdf --check`: 18/18 generated PDFs passed.
- Exact/pocket figure sequence hashes match for all 9 books.
- Missing figure references: 0.
- Missing-character log markers: 0.
- Severe overfull lines above the configured 18 pt gate: 0. The only nonzero
  measured overflow is 6.66016 pt in the Totman pocket edition, below the gate.
- Stale or duplicate PDF TOC destinations: 0.
- Leaked HTML entities/tags, Unicode replacement characters, and source-page
  placeholder prose: 0.
- Focused renderer tests: 16/16 passed.

Representative exact and pocket pages were rendered and visually inspected,
including the dense family-name table, armour glossary, illustrated pages, and
the reconstructed Sourcebook index.

This completion certifies structural OCR, real-TeX rendering, figure retention,
and audited localized repairs. It does not claim line-by-line scholarly
copyediting of every proper name in the nine English reference books. The
reviewed text is now suitable as the stable source layer for later EN-JP-ZH
generation.
