# Sunzi, Daodejing, And Lunyu Task Preparation - 2026-07-05

Prepared local sources and launchable quadrilingual PocketPolyglot tasks for
`sunzi-bingfa`, `daodejing`, and `lunyu`. Raw source books are stored under
ignored `sources/`; tracked task metadata is stored under `books/` and
`data/source-plan/`.

## Copied Source Layout

| Work | Wenyan spine | References |
| --- | --- | --- |
| 孫子兵法 / The Art of War | `sources/sunzi-bingfa/zh/wikisource-chapterized/` | ZH EPUB, EN Wikisource/EPUBs, JP Wikisource |
| 道德經 / Tao Te Ching | `sources/daodejing/zh/wenyan-from-japanese-wikisource/` | ZH `老子他說`, EN Wikisource/EPUB, JP Wikisource/PDFs |
| 論語 / The Analects | `sources/lunyu/zh/wikisource/` | ZH Wikisource EPUB, EN Wikisource/EPUB/PDFs, JP Wikisource |

## Prepared Tasks

| Book ID | Chapters | Chunks | Manifest |
| --- | ---: | ---: | --- |
| `sunzi-bingfa` | 13 | 74 | `books/sunzi-bingfa/work/quadrilingual/chunks/manifest.json` |
| `daodejing` | 81 | 81 | `books/daodejing/work/quadrilingual/chunks/manifest.json` |
| `lunyu` | 20 | 506 | `books/lunyu/work/quadrilingual/chunks/manifest.json` |

## Notes

- `道德經` Chinese Wikisource was only an index/version page, so the main spine
  uses the cleaner Japanese Wikisource classical text with kundoku marks removed.
- `老子他說` is retained as a Chinese commentary/reference, not as the main text.
- `論語` preparation filters root/all-view/index pages and sorts the twenty
  canonical chapters.

## Launch Command

No writer was started. To run later:

```sh
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
  scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  sunzi-bingfa zhjpbook-sunzi-bingfa-quadrilingual
```

Repeat with `daodejing` or `lunyu` as the first argument.
