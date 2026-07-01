# Japanese Drama And Waka Task Preparation - 2026-07-02

This note records the launchable PocketPolyglot/LinguaLeaf tasks prepared from
the current local `sources/` mirrors. Original EPUB/PDF/source mirrors remain
ignored; durable task metadata and scripts are tracked.

## Prepared Tasks

| Book ID | Work | Task Mode | Source Spine | Chapters | Chunks | Manifest |
| --- | --- | --- | --- | ---: | ---: | --- |
| `mudanting` | 牡丹亭 / The Peony Pavilion | `quadrilingual_wenyan_main` | Chinese Wikisource wenyan | 55 scenes | 523 | `books/mudanting/work/quadrilingual/chunks/manifest.json` |
| `xixiangji` | 西廂記 / The Story of the Western Wing | `quadrilingual_wenyan_main` | Chinese Wikisource wenyan | 5 books | 101 | `books/xixiangji/work/quadrilingual/chunks/manifest.json` |
| `manyoshu` | 万葉集 / Man'yoshu / 万叶集 | `trilingual_japanese_classical_main` | Japanese Wikisource kundoku | 20 volumes | 4562 | `books/manyoshu/work/trilingual/chunks/manifest.json` |
| `kokin-wakashu` | 古今和歌集 / Kokin Wakashu | `trilingual_japanese_classical_main` | Japanese Wikisource | 23 sections | 1123 | `books/kokin-wakashu/work/trilingual/chunks/manifest.json` |

## Source Notes

- `mudanting` uses the canonical 55-scene order from Chinese Wikisource. The
  duplicate `歡撓` page is excluded in favor of `懽撓`.
- `xixiangji` uses only the Wang Shifu five-book spine. `北西廂記` and
  `南西廂記` are variant sibling texts and are excluded from the main stream.
- `manyoshu` uses Japanese Wikisource kundoku as readable source text and keeps
  original/kana fields in the chunk references. English Wikisource anthology
  material is partial and should only be used when it clearly matches.
- `kokin-wakashu` uses Japanese Wikisource as source text, the local modern
  translation EPUB as a broad Japanese reference, and partial English
  Wikisource anthology pages as broad references.
- Full matching English/Japanese Wikisource roots were not found for the Chinese
  drama tasks. Full matching Chinese Wikisource roots were not found for the
  waka tasks, so those layers are generated from the preserved source spine.

## Preparation Commands

```sh
python scripts/interlinear/prepare_classical_quadrilingual_task.py \
  --book-id mudanting --book-id xixiangji --force

python scripts/interlinear/prepare_japanese_classical_trilingual_task.py \
  --book-id manyoshu --book-id kokin-wakashu --force
```

## Launch Commands

Use conservative worker counts if other Codex tasks are running. Increase
`WORKERS` only when quota and machine load are comfortable.

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh mudanting \
  zhjpbook-mudanting-10-low

WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh xixiangji \
  zhjpbook-xixiangji-10-low

WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_trilingual_book_tmux.sh manyoshu \
  zhjpbook-manyoshu-10-low

WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_trilingual_book_tmux.sh kokin-wakashu \
  zhjpbook-kokin-wakashu-10-low
```

## Cover Generation

The cover generator has theme hints for all four book IDs. After generation
completes, run:

```sh
node scripts/books/generate_aginti_cover_assets.mjs \
  --book mudanting --book xixiangji --book manyoshu --book kokin-wakashu
```

Then compile final large-font color and black-white editions and sync them to
the normal LinguaLeaf Nutstore/share destinations.
