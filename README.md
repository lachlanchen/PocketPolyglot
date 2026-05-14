# ZhJpBook

Pocket-size TeX workflow for a Chinese/Japanese paired reader with notes, pinyin, and furigana.

## Quick Start

Build the sample paired book:

```sh
make sample
```

The PDF is written to `build/paired/book.pdf`.

Build the Chinese-main/Japanese-comment block layout:

```sh
make interlinear
```

The PDF is written to `build/interlinear-block/book.pdf`.

Build the run-in layout, where Chinese units sit back-to-back and each Japanese comment starts under its own Chinese sentence:

```sh
make interlinear-run
```

The PDF is written to `build/interlinear-run/book.pdf`. Both interlinear layouts use `data/interlinear/sample.json`.

Build the Japanese-main/Chinese-comment layout from the same interlinear JSON:

```sh
make interlinear-jp-main
```

The PDF is written to `build/interlinear-jp-main/book.pdf`. Use `JP_MAIN_COVER=assets/covers/kokoro-jp-main/kokoro-cover.jpeg` to include the prepared Kokoro cover image.

Convert `sources/心.epub` to Markdown:

```sh
make kokoro-md
```

Run the full Codex-assisted `心` interlinear pipeline in tmux:

```sh
make kokoro-tmux
```

The worker uses `gpt-5.5` with high reasoning, resumes one Codex session chunk by chunk, writes `books/kokoro/markdown/book.md`, assembles `data/interlinear/kokoro.json`, and compiles with the `interlinear-block` style to `build/interlinear-block/book.pdf`.

Run the bilingual-source `心（こころ）` pipeline with Chinese as main text and the Japanese original as comment text:

```sh
make kokoro-bilingual-tmux
```

This uses `gpt-5.5` with `xhigh` reasoning, compiles a partial preview after every completed chunk, and writes the named PDF to `build/interlinear-block/心（こころ）.pdf`.
Future bilingual runs default to one Chinese source paragraph per chunk and attach Japanese original context at the chapter/story level. Use `--chunk-mode size --max-chars 450` only when you intentionally want grouped paragraphs.

Run OCR on a few pages of the scanned PDF:

```sh
make ocr-sample PAGES=60-62
```

The Markdown is written to `ocr/sample-pages.md`. For the whole PDF:

```sh
make ocr-all
```

## Preparing Paired Text

Edit `data/paired/source.md`. Each aligned unit is one block:

```md
::: pair
zh: \zhpy{大}{dà}\zhpy{學}{xué}之道，在明明德。
jp: \jpruby{大学}{だいがく}の\jpruby{道}{みち}は、\jpruby{明徳}{めいとく}を\jpruby{明}{あき}らかにするに\jpruby{在}{あ}り。
zh_comment: Chinese note here.
jp_comment: \jpruby{朱子}{しゅし}\jpruby{曰}{い}く：\jpruby{大学}{だいがく}とは、\jpruby{大人}{たいじん}の\jpruby{学}{がく}なり。
:::
```

Use `\zhpy{字}{pin}` for pinyin and `\jpruby{漢字}{かな}` for Japanese ruby. Ruby can be hidden in `tex/paired/book.tex` with `\HideAnnotations`.

For Japanese, wrap every kanji or kanji compound in `\jpruby{...}{...}` when you want full furigana. A drafting helper is available:

```sh
python scripts/paired/add_japanese_furigana.py "大学の道は、明徳を明らかにする。"
```

Review the output manually; automatic readings can be wrong for classical text, names, and terms.

## Interlinear JSON

Use `data/interlinear/sample.json` when the book should read continuously in Chinese while Japanese sits below each Chinese sentence as a compact comment. Each story is split into paragraphs, and each paragraph into reading units:

```json
{
  "zh": [{"t": "天地", "r": "tiān dì"}, {"t": "整治好", "r": "zhěng zhì hǎo"}],
  "ja": [
    [{"t": "天地", "r": "てんち"}, {"t": "を", "r": ""}],
    [{"t": "整", "r": "ととの"}, {"t": "えた。", "r": ""}]
  ]
}
```

Chinese is the main row. Japanese is intentionally split into two short rows so it works like a running comment rather than a second equal text column.

Tokens may also carry an optional grammar role for colorized annotated editions:

```json
{"t": "我", "r": "wǒ", "g": "zhu"}
```

Supported role keys are `zhu`/`subject`, `wei`/`predicate`/`verb`, `bin`/`object`, `ding`/`attributive`, `zhuang`/`adverbial`, `bu`/`complement`, `topic`, and `function`/`particle`. The renderer treats this as a display layer only; text and readings stay unchanged, so an annotated JSON can be validated against the same source text.

The block layout in `tex/interlinear-block/` gives every sentence its own Chinese row plus Japanese note. The run-in layout in `tex/interlinear-run/` makes sentence units flow back-to-back; the Japanese note starts at the same horizontal point as its Chinese unit and wraps inside the measured Chinese-unit width.

The Japanese-main layout in `tex/interlinear-jp-main/` uses the same JSON without changing the source data: Japanese ruby text becomes the main continuous text, and the Chinese pinyin text becomes the smaller comment line under each reading unit.

For bilingual source books, prepare both `books/<book-id>/markdown/zh.md` and `books/<book-id>/markdown/ja.md`. The chunker preserves each Chinese paragraph as its own task by default, while the Japanese reference is intentionally broader chapter context so the Codex worker can find the matching original passage instead of trusting a fragile sentence-range estimate.

The default page is A6 pocket size. To use two columns in the paired demo instead, uncomment `\PairLayoutSideBySide` in `tex/paired/book.tex`.

## Repository Layout

```text
data/interlinear/      structured JSON corpus
data/paired/           simple paired Markdown demo
scripts/interlinear/   JSON-to-TeX renderers
scripts/ocr/           OCR helper
scripts/paired/        paired Markdown and ruby helpers
assets/covers/         tracked cover images for compiled editions
prompt_tools/          tmux/Codex long-running book pipelines
tex/interlinear-block/ previous sentence-block layout
tex/interlinear-run/   new back-to-back main-text layout
tex/interlinear-jp-main/ Japanese-main/Chinese-comment layout
tex/paired/            simple paired reader demo
ocr/                   reviewed OCR Markdown
sources/               local scanned PDFs, ignored by Git
```

## OCR Notes

Original scanned PDFs live in `sources/` and are intentionally ignored by Git. The included scan is an image PDF, so OCR is imperfect. The OCR script creates reviewable Markdown with page headings; it does not try to silently "fix" hard character errors. For this scan, the strongest default found here is:

```sh
python scripts/ocr/pdf_to_markdown.py "sources/中国民间故事集成 四川卷 上 10978512.pdf" \
  --pages 60-62 \
  --lang chi_sim \
  --psm 4 \
  --dpi 300 \
  --output ocr/sample-pages.md
```

Use `--crop --threshold` only if a different scan has dirty margins or weak contrast; Tesseract performed better on this PDF from the raw rendered page. Use `--save-images-dir ocr/images` when you want the page images beside the Markdown for manual correction.

To switch OCR language, pass `OCR_LANG=jpn`, `OCR_LANG=jpn_vert`, `OCR_LANG=chi_tra`, or another language shown by `tesseract --list-langs`.
