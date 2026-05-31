<p align="center">
  <a href="README.md">English</a> ·
  <a href="i18n/README.zh-Hans.md">中文</a> ·
  <a href="i18n/README.ja.md">日本語</a>
</p>

# PocketPolyglot

Generate beautiful pocket-size interlinear books for language learning.

[![Website](https://img.shields.io/badge/learn.lazying.art-PocketPolyglot-7b5dff)](https://learn.lazying.art)
[![TeX](https://img.shields.io/badge/XeLaTeX-pocket%20books-0f766e)](https://www.tug.org/xetex/)
[![Python](https://img.shields.io/badge/Python-pipeline-3776ab)](scripts/)
[![JSON](https://img.shields.io/badge/JSON-line%20aligned-f59e0b)](data/interlinear/sample.json)

PocketPolyglot turns bilingual texts into ruby, pinyin, grammar-colored, line-aligned pocket books. The current production workflow focuses on Chinese/Japanese editions, but the data model is language-pair neutral: EN-JP, ZH-EN, classical-modern, and other paired reading formats can use the same structure.

The repository is a toolkit: TeX templates, Python scripts, JSON schemas, preview assets, and sample data. Bring your own rights-cleared source texts before publishing full generated books.

## What It Builds

Every complete paired book can be exported in four reader choices:

| Direction | Color | Black and White |
| --- | --- | --- |
| Chinese main text with Japanese notes | grammar-colored ruby/pinyin edition | monochrome edition for e-ink |
| Japanese main text with Chinese notes | grammar-colored furigana/pinyin edition | monochrome edition for e-ink |

The page format is pocket-size, with line-based interlinear blocks, full furigana over Japanese kanji, pinyin over Chinese text, optional grammar roles, tables of contents, generated covers, and chapter page breaks.

## Gallery

These previews are first pages rendered from generated PDFs, not standalone cover images.

| Preview | Book | Editions |
| --- | --- | --- |
| <img src="assets/readme-previews/kokoro.png" width="150" alt="Kokoro first page preview"> | **Kokoro / 心 / こころ** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/snow-country.png" width="150" alt="Snow Country first page preview"> | **Snow Country / 雪国** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/no-longer-human.png" width="150" alt="No Longer Human first page preview"> | **No Longer Human / 人間失格** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/the-old-capital.png" width="150" alt="The Old Capital first page preview"> | **The Old Capital / 古都** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/izu-no-odori.png" width="150" alt="The Dancing Girl of Izu first page preview"> | **The Dancing Girl of Izu / 伊豆の踊子** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/kinkakuji.png" width="150" alt="The Temple of the Golden Pavilion first page preview"> | **The Temple of the Golden Pavilion / 金閣寺** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/rashomon-stories.png" width="150" alt="Rashomon stories first page preview"> | **Rashomon Stories / 羅生門短篇集** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/genji-modern.png" width="150" alt="Tale of Genji first page preview"> | **The Tale of Genji / 源氏物語** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/sishu-jizhu-aginti.png" width="150" alt="Sishu Zhangju Jizhu first page preview"> | **Sishu Zhangju Jizhu / 四書章句集註** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/shiji-aginti.png" width="150" alt="Shiji first page preview"> | **Shiji / 史記** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |
| <img src="assets/readme-previews/sichuan-folk-stories-vol1.png" width="150" alt="Sichuan folk stories first page preview"> | **Sichuan Folk Stories, Volume 1 / 中国民间故事集成四川卷上** | ZH-main color, ZH-main black and white, JP-main color, JP-main black and white |

## Quick Start

Build the simple paired demo:

```sh
make sample
```

Build the Chinese-main interlinear sample:

```sh
make interlinear
```

Build the Japanese-main interlinear sample from the same JSON:

```sh
make interlinear-jp-main
```

Export completed local PDFs into a flat browsing folder and regenerate README previews:

```sh
make export-books
make readme-previews
```

## Data Model

The core format is a paragraph/chapter JSON model. Text is split into aligned reading units, and each token can carry a reading and an optional grammar role.

```json
{
  "zh": [{"t": "天地", "r": "tiān dì", "g": "subject"}],
  "ja": [[{"t": "天地", "r": "てんち", "g": "subject"}]]
}
```

Stable token fields:

| Field | Meaning |
| --- | --- |
| `t` | surface text |
| `r` | ruby, furigana, pinyin, or other reading |
| `g` | optional grammar role such as `subject`, `predicate`, `object`, `attributive`, `adverbial`, `complement`, `topic`, or `function` |

## Project Layout

| Path | Purpose |
| --- | --- |
| `tex/` | XeLaTeX templates for paired, block interlinear, run-in, and JP-main layouts |
| `scripts/books/` | EPUB/PDF/Markdown preparation, cover composition, preview export |
| `scripts/interlinear/` | JSON chunking, validation, rendering, compiling, long-run workers |
| `data/interlinear/sample.json` | small public sample of the structured format |
| `assets/readme-previews/` | first-page preview images generated from PDFs |
| `references/` | design notes, naming notes, and pipeline references |
| `sources/` | local source books, ignored by Git |
| `build/` | generated PDFs and TeX intermediates, ignored by Git |

## Public Use

PocketPolyglot is designed for language learners, teachers, and book builders who want maintainable bilingual editions rather than manually aligned TeX. Keep source rights clear: publish templates, samples, and previews freely; publish full book PDFs only when the source text and translation can be redistributed.

Project site: [learn.lazying.art](https://learn.lazying.art)
