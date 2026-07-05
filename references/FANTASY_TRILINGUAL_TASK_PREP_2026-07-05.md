# Fantasy Trilingual Task Prep - 2026-07-05

Prepared three modern-fantasy LinguaLeaf/PocketPolyglot tasks with English as
the alignment spine, Chinese as a published-reference source, and generated
natural modern Japanese where exact Japanese text is not yet OCR-ready.
Fantasy prompts use compact ratio-based Chinese reference windows by default so
large anthology/bundle sources do not get copied into every chunk prompt.

| Book ID | Work | Status | Chunks | Sources |
| --- | --- | --- | ---: | --- |
| `fellowship-of-the-ring` | `The Fellowship of the Ring / 魔戒现身 / 指輪物語 旅の仲間` | Ready; first active task | 405 | EN EPUB, ZH EPUB bundle, JP image-only PDF reference |
| `harry-potter-1` | `Harry Potter and the Sorcerer's Stone / 哈利·波特与魔法石 / ハリー・ポッターと賢者の石` | Prepared; launch after Fellowship | 185 | EN EPUB bundle, ZH EPUB bundle, JP image-only PDF reference |
| `a-game-of-thrones` | `A Game of Thrones / 权力的游戏 / 七王国の玉座` | Prepared; launch after Harry Potter | 697 | EN volume-one EPUB, ZH MOBI anthology |

## Prepared Files

- `books/fellowship-of-the-ring/book-plan.json`
- `books/fellowship-of-the-ring/markdown/en.md`
- `books/fellowship-of-the-ring/markdown/zh.md`
- `books/harry-potter-1/book-plan.json`
- `books/harry-potter-1/markdown/en.md`
- `books/harry-potter-1/markdown/zh.md`
- `books/a-game-of-thrones/book-plan.json`
- `books/a-game-of-thrones/markdown/en.md`
- `books/a-game-of-thrones/markdown/zh.md`
- `scripts/interlinear/prepare_fantasy_trilingual.py`

## Launch Notes

Use the standard trilingual generator with low reasoning and ten workers:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_trilingual_book_tmux.sh fellowship-of-the-ring
```

Only `fellowship-of-the-ring` was launched immediately. `harry-potter-1` and
`a-game-of-thrones` are prepared for later sequential launch after their source
cleanup checks.
