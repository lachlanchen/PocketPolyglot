# Quran Arabic Quadrilingual Task Prep - 2026-07-02

Prepared `quran` as an Arabic-spine quadrilingual LinguaLeaf task.

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

Each source unit preserves exact Arabic text and includes initial
`ar_tokens` with `t` text and `r` ruby/transliteration. These readings are
mechanical seeds for the future Arabic renderer/reviewer; the writer should
preserve Arabic exactly and refine readings only with validation evidence.

## Required Pipeline Work

The task is intentionally `launchable: false` until the generic pipeline can
handle Arabic explicitly:

- Arabic quadrilingual writer/validator or generic multilingual writer.
- RTL-safe XeLaTeX rendering for Arabic source text.
- Arabic ruby/transliteration above or beside each Arabic word.
- Grammar role `g` support for Arabic plus English/Japanese/Chinese.
- Color and blackwhite large-font PDF compile targets.

The existing Chinese/Japanese/English renderers should not be used by relabeling
Arabic as another language.
