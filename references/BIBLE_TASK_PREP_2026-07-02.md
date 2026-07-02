# Bible Trilingual Task Prep - 2026-07-02

Prepared `bible` as a LinguaLeaf trilingual task with English as the alignment
spine.

## Sources

| Layer | Source | Local Path | Use |
| --- | --- | --- | --- |
| English | Wikisource King James Version | `sources/bible/en/wikisource-kjv/` | Exact verse spine |
| Chinese | Wikisource Chinese Union Version | `sources/bible/zh/wikisource-union/` | Exact verse layer |
| Japanese | Japanese Wikisource Kougo attempt | `sources/bible/ja/wikisource-kougo-ot/`, `sources/bible/ja/wikisource-kougo-nt/` | Not usable as direct text; pages are metadata/redaction notices |

Because the Japanese Wikisource pages are not usable full verse text, the task
asks the writer to generate natural modern Japanese from the exact English and
Chinese verse sources.

## Prepared Task

- Book id: `bible`
- Mode: `trilingual_standard`
- Spine: English KJV
- Chunks: `2113`
- Chapters: `1189`
- Chunk size: up to 20 verse units
- Cover: `assets/covers/bible/cover.png`
- Manifest: `books/bible/work/trilingual/chunks/manifest.json`

The preparation script records `185` skipped verse references where the fetched
English and Chinese source numbering did not both provide a clean matching
verse. Generated chunks only include units where both exact English and exact
Chinese text exist.

## Launch

Started with:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low CODEX_TIMEOUT_SECONDS=1200 \
  COMPILE_INTERVAL_SECONDS=1800 MERGE_INTERVAL=180 \
  bash scripts/interlinear/start_trilingual_book_tmux.sh bible zhjpbook-bible-10-low
```

Tmux sessions:

- `zhjpbook-bible-10-low`
- `zhjpbook-bible-10-low-repair`

## Pause Note - 2026-07-02

The user asked to stop broad queue execution and keep Bible/Quran work at the
end. The two Bible tmux sessions above were stopped. No generated JSON was
deleted.

Manifest progress at pause:

- `manifest_chunks=2113`
- `valid_chunks=624`
- `stale_chunks=0`
- `missing_chunks=1489`
- `last_valid=bible-chunk-00624`
- `first_missing=bible-chunk-00625`

Resume only by explicit request, and run it as a single-book task rather than
as part of a broad parallel queue.
