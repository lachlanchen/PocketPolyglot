# Cover Layout Policy - 2026-07-12

LinguaLeaf cover images must separate artwork from typography.

## Rules

- Generated background art must be textless: no title, subtitle, letters,
  calligraphy, pseudo-writing, logos, seals, red stamp squares, or single
  kanji/hanzi marks.
- All readable cover text must be overlaid by code, usually through
  `scripts/books/compose_book_cover.py`.
- If `book_title_en` exists, the English title must appear on the cover. Do not
  ship trilingual or maximum-language covers that only show Japanese/Chinese
  titles.
- Prefer a narrow translucent vertical center veil for CJK vertical titles.
  Avoid large opaque horizontal title bands.
- Do not draw the old `流` stamp or any replacement readable seal. If a
  decorative mark is needed later, it must be abstract and non-readable.
- Credits should be small and inside the artwork: `AgInTiFlow curated`,
  `https://flow.lazying.art`, and `powered by LazyingArt`.
- Nutstore Share should receive only maximum-language public editions; after
  cover backfill, resync Share and LinguaLeaf from the corrected build/export
  artifacts.

## Backfill Workflow

1. Recompose cover assets from clean `background.png` or `background-native.png`:
   `python3 scripts/books/backfill_cover_layouts.py`.
2. Regenerate missing backgrounds with
   `node scripts/books/generate_aginti_cover_assets.mjs --force --book <id>`.
3. Re-run the backfill for regenerated books so existing PDF first pages are
   replaced.
4. Process large multi-part books such as `hou-han-shu` and
   `zizhi-tongjian` last.
