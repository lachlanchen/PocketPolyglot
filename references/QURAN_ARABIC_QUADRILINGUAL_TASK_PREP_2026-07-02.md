# Quran Arabic Quadrilingual Task Prep - 2026-07-02

Prepared and compiled `quran` as an Arabic-spine quadrilingual LinguaLeaf task.

## Sources Mirrored

| Layer | Wikisource Title | Local Path | Pages | Use |
| --- | --- | --- | ---: | --- |
| Arabic | `القرآن الكريم (حفص، المدينة النبوية)` | `sources/quran/ar/wikisource-hafs-madina/` | 115 | Exact source spine |
| English | `The Meaning of the Glorious Koran (1930)` | `sources/quran/en/wikisource-pickthall-1930/` | 85 | Partial public-domain reference |
| English | `The Koran (Rodwell)` | `sources/quran/en/wikisource-rodwell/` | 35 | Partial public-domain reference |
| Japanese | `クルアーン` | `sources/quran/ja/wikisource-quran/` | 5 | Partial reference |
| Chinese | `漢譯古蘭經` | `sources/quran/zh/wikisource-hanyigulanjing/` | 27 | Partial older Chinese reference |
| Chinese | `古蘭經譯解` | `sources/quran/zh/wikisource-gulanjing-yijie/` | 5 | Partial older Chinese reference |
| Chinese | `古蘭經大義` | `sources/quran/zh/wikisource-gulanjing-dayi/` | 4 | Partial older Chinese reference |

The Arabic source is complete by sura. The English, Japanese, and Chinese
mirrors are useful references but not complete enough to be treated as exact
aligned translations.

## Prepared Task

- Book id: `quran`
- Mode: `arabic_quadrilingual_main`
- Spine: Arabic
- Chapters: `114`
- Chunks: `842`
- Chunk size: up to 8 ayah units
- Missing Arabic suras: `0`
- Manifest: `books/quran/work/arabic-quadrilingual/chunks/manifest.json`
- Source Markdown: `books/quran/markdown/quran-arabic-source.md`
- Full generated JSON: `books/quran/work/arabic-quadrilingual/preview/quran.full.json`
- Color PDF: `build/quran/ar-main-quadrilingual/color/القرآن الكريم（English・日本語・中文注）.pdf`
- Black-white PDF: `build/quran/ar-main-quadrilingual/blackwhite/القرآن الكريم（English・日本語・中文注・黑白）.pdf`

Each source unit preserves exact Arabic text and includes initial
`ar_tokens` with `t` text and `r` ruby/transliteration. These readings are
mechanical seeds for the future Arabic renderer/reviewer; the writer should
preserve Arabic exactly and refine readings only with validation evidence.

## Completion Notes

The completed first edition uses:

- Arabic source spine from the prepared Wikisource Hafs/Madina mirror.
- Quran.com word-level Arabic transliteration and word gloss cache.
- QuranEnc `english_rwwad`, `japanese_saeedsato`, and `chinese_makin`
  verse-aligned SQLite translations.
- Heuristic normalized grammar roles for Arabic, English, Japanese, and Chinese
  tokens, rendered in color or black-white.
- Dedicated XeLaTeX Arabic RTL/ruby renderer using `bidi` and Amiri.

Validation on 2026-07-02:

- `validate_quran_arabic_quadrilingual_json.py`: passed.
- Color PDF: `3014` pages, `0` overfull boxes, `0` fatal TeX errors.
- Black-white PDF: `3014` pages, `0` overfull boxes, `0` fatal TeX errors.
- Synced to Nutstore `Share/LinguaLeaf` and the project export tree. The
  current project export root is
  `/home/lachlan/Nutstore Files/NoSync/Projects/LinguaLeaf`; do not recreate
  the old synced `Projects/LinguaLeaf` path.
