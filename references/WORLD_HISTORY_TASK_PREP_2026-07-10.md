# World History Trilingual Task Prep - 2026-07-10

Prepared two EN-JP-ZH PocketPolyglot tasks from local PDF sources. These are
preparation-only artifacts: source PDFs are ignored under `sources/`, and no
writer queue was started.

| Book ID | Title | Sources | Task Shape | Chunks | Notes |
| --- | --- | --- | --- | ---: | --- |
| `silk-roads` | *The Silk Roads: A New History of the World* / `丝绸之路：一部全新的世界史` / `シルクロード：新しい世界史` | EN PDF + ZH scanned PDF | English spine, Chinese OCR reference, generated modern Japanese | 568 | ZH PDF had no embedded text; OCR cache completed for all 576 pages and was trimmed to body text through the conclusion. |
| `new-roman-empire` | *The New Roman Empire: A History of Byzantium* / `新罗马帝国：拜占庭史` / `新ローマ帝国：ビザンツの歴史` | EN PDF | English spine, generated modern Chinese and Japanese | 1180 | English embedded text was usable. Parser detects Introduction plus 37 body chapters. |

## Stored Sources

| Book ID | Source Path |
| --- | --- |
| `silk-roads` | `sources/world-history/silk-roads/en/The Silk Roads - A New History of the World.pdf` |
| `silk-roads` | `sources/world-history/silk-roads/zh/丝绸之路：一部全新的世界史.pdf` |
| `new-roman-empire` | `sources/world-history/byzantium-new-roman-empire/en/The New Roman Empire - A History of Byzantium.pdf` |

## Generated Task Files

| Book ID | Manifest | Book Plan | Markdown |
| --- | --- | --- | --- |
| `silk-roads` | `books/silk-roads/work/trilingual/chunks/manifest.json` | `books/silk-roads/book-plan.json` | `books/silk-roads/markdown/en.md`, `books/silk-roads/markdown/zh.md` |
| `new-roman-empire` | `books/new-roman-empire/work/trilingual/chunks/manifest.json` | `books/new-roman-empire/book-plan.json` | `books/new-roman-empire/markdown/en.md` |

## Preparation Command

```sh
python scripts/interlinear/prepare_world_history_trilingual.py \
  --book-id silk-roads \
  --book-id new-roman-empire
```

## Start Command

Run one book directly when ready:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_trilingual_book_tmux.sh silk-roads
```

or:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  bash scripts/interlinear/start_trilingual_book_tmux.sh new-roman-empire
```

Use the same large-font, maximum-language export rules as other LinguaLeaf
trilingual books when finalizing.
