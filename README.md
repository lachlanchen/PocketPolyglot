[English](README.md) · [العربية](i18n/README.ar.md) · [Español](i18n/README.es.md) · [Français](i18n/README.fr.md) · [日本語](i18n/README.ja.md) · [한국어](i18n/README.ko.md) · [Tiếng Việt](i18n/README.vi.md) · [中文 (简体)](i18n/README.zh-Hans.md) · [中文（繁體）](i18n/README.zh-Hant.md) · [Deutsch](i18n/README.de.md) · [Русский](i18n/README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

Generate beautiful pocket-size interlinear books for language learning.

[![Website](https://img.shields.io/badge/learn.lazying.art-PocketPolyglot-7b5dff)](https://learn.lazying.art)
[![TeX](https://img.shields.io/badge/XeLaTeX-pocket%20books-0f766e)](https://www.tug.org/xetex/)
[![Python](https://img.shields.io/badge/Python-pipeline-3776ab)](scripts/)
[![JSON](https://img.shields.io/badge/JSON-line%20aligned-f59e0b)](data/interlinear/sample.json)

PocketPolyglot turns bilingual texts into ruby, pinyin, grammar-colored, line-aligned pocket books. The current production workflow focuses on Chinese/Japanese editions, but the data model is language-pair neutral: EN-JP, ZH-EN, classical-modern, and other paired reading formats can use the same structure.

The repository is a toolkit: TeX templates, Python scripts, JSON schemas, preview assets, and sample data. Bring your own rights-cleared source texts before publishing full generated books.

## One Sentence In Full Width

JP-main sample from Kokoro: Japanese main text with furigana, Chinese comment with pinyin, and grammar color on the aligned words.

<p align="center">
  <a href="assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="Kokoro JP-main sentence with furigana, Chinese comment, pinyin, and grammar color" width="100%">
  </a>
</p>

## Four Editions At A Glance

The same Kokoro interior page rendered as all four standard editions:

<p align="center">
  <a href="assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro shown as ZH-main color, ZH-main black and white, JP-main color, and JP-main black and white editions" width="100%">
  </a>
</p>

Click the image to open the full-resolution version for readable ruby, furigana, and pinyin.

Chinese/Japanese is the current showcase pair, but the pipeline is not limited to it. Any language pair with prepared aligned text and readings can use the same book model: EN-JP, ZH-EN, classical-modern, learner gloss editions, or teacher-curated parallel readers.

## What It Builds

Every complete paired book can be exported in four reader choices:

| Direction | Color | Black and White |
| --- | --- | --- |
| Chinese main text with Japanese notes | grammar-colored ruby/pinyin edition | monochrome edition for e-ink |
| Japanese main text with Chinese notes | grammar-colored furigana/pinyin edition | monochrome edition for e-ink |

The page format is pocket-size, with line-based interlinear blocks, full furigana over Japanese kanji, pinyin over Chinese text, optional grammar roles, tables of contents, generated covers, and chapter page breaks.

## Gallery

These previews are first pages rendered from generated PDFs, not standalone cover images. The full local export currently contains 224 PDFs across color/black-white variants and reading directions.

| Preview | Book | Edition |
| --- | --- | --- |
| <img src="assets/readme-previews/a-city-on-mars-jp-en.png" width="150" alt="A City on Mars first page preview"> | **A City on Mars** | EN-JP · en-main · color |
| <img src="assets/readme-previews/a-city-on-mars-zh-en.png" width="150" alt="火星城市 first page preview"> | **火星城市** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/a-city-on-mars-zh-jp.png" width="150" alt="火星城市 first page preview"> | **火星城市** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/botchan-jp-en.png" width="150" alt="Botchan first page preview"> | **Botchan** | EN-JP · en-main · color |
| <img src="assets/readme-previews/botchan-zh-en.png" width="150" alt="少爷 first page preview"> | **少爷** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/botchan-zh-jp.png" width="150" alt="少爷 first page preview"> | **少爷** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/genji-modern.png" width="150" alt="源氏物语 first page preview"> | **源氏物语** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/gone-with-the-wind-jp-en.png" width="150" alt="Gone With the Wind first page preview"> | **Gone With the Wind** | EN-JP · en-main · color |
| <img src="assets/readme-previews/gone-with-the-wind-zh-en.png" width="150" alt="飘 first page preview"> | **飘** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/gone-with-the-wind-zh-jp.png" width="150" alt="飘 first page preview"> | **飘** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/i-am-a-cat-jp-en.png" width="150" alt="I Am a Cat first page preview"> | **I Am a Cat** | EN-JP · en-main · color |
| <img src="assets/readme-previews/i-am-a-cat-zh-en.png" width="150" alt="我是猫 first page preview"> | **我是猫** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/i-am-a-cat-zh-jp.png" width="150" alt="我是猫 first page preview"> | **我是猫** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/inugami-curse-jp-en.png" width="150" alt="The Inugami Curse first page preview"> | **The Inugami Curse** | EN-JP · en-main · color |
| <img src="assets/readme-previews/inugami-curse-zh-en.png" width="150" alt="犬神家族 first page preview"> | **犬神家族** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/inugami-curse-zh-jp.png" width="150" alt="犬神家族 first page preview"> | **犬神家族** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/izu-no-odori.png" width="150" alt="伊豆的舞女 first page preview"> | **伊豆的舞女** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/japanese-history-jp-en.png" width="150" alt="A Concise History of Japan first page preview"> | **A Concise History of Japan** | EN-JP · en-main · color |
| <img src="assets/readme-previews/japanese-history-zh-en.png" width="150" alt="日本史 first page preview"> | **日本史** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/japanese-history-zh-jp.png" width="150" alt="日本史 first page preview"> | **日本史** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/kinkakuji.png" width="150" alt="金阁寺 first page preview"> | **金阁寺** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/kojiki.png" width="150" alt="古事記 first page preview"> | **古事記** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/kokoro.png" width="150" alt="心 first page preview"> | **心** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/martian-chronicles-jp-en.png" width="150" alt="The Martian Chronicles first page preview"> | **The Martian Chronicles** | EN-JP · en-main · color |
| <img src="assets/readme-previews/martian-chronicles-zh-en.png" width="150" alt="火星编年史 first page preview"> | **火星编年史** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/martian-chronicles-zh-jp.png" width="150" alt="火星编年史 first page preview"> | **火星编年史** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/no-longer-human.png" width="150" alt="人間失格 first page preview"> | **人間失格** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/rashomon-stories.png" width="150" alt="罗生门短篇集 first page preview"> | **罗生门短篇集** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/red-mars-jp-en.png" width="150" alt="Red Mars first page preview"> | **Red Mars** | EN-JP · en-main · color |
| <img src="assets/readme-previews/red-mars-zh-en.png" width="150" alt="红火星 first page preview"> | **红火星** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/red-mars-zh-jp.png" width="150" alt="红火星 first page preview"> | **红火星** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/red-rising-1-jp-en.png" width="150" alt="Red Rising first page preview"> | **Red Rising** | EN-JP · en-main · color |
| <img src="assets/readme-previews/red-rising-1-zh-en.png" width="150" alt="火星崛起 first page preview"> | **火星崛起** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/red-rising-1-zh-jp.png" width="150" alt="火星崛起 first page preview"> | **火星崛起** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/red-rising-2-jp-en.png" width="150" alt="Golden Son first page preview"> | **Golden Son** | EN-JP · en-main · color |
| <img src="assets/readme-previews/red-rising-2-zh-en.png" width="150" alt="火星崛起2：黄金之子 first page preview"> | **火星崛起2：黄金之子** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/red-rising-2-zh-jp.png" width="150" alt="火星崛起2：黄金之子 first page preview"> | **火星崛起2：黄金之子** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/red-rising-3-jp-en.png" width="150" alt="Morning Star first page preview"> | **Morning Star** | EN-JP · en-main · color |
| <img src="assets/readme-previews/red-rising-3-zh-en.png" width="150" alt="火星崛起3：晨色之星 first page preview"> | **火星崛起3：晨色之星** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/red-rising-3-zh-jp.png" width="150" alt="火星崛起3：晨色之星 first page preview"> | **火星崛起3：晨色之星** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/shiji-aginti.png" width="150" alt="史記 first page preview"> | **史記** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/sichuan-folk-stories-vol1.png" width="150" alt="中国民间故事集成四川卷上 first page preview"> | **中国民间故事集成四川卷上** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/sishu-jizhu.png" width="150" alt="四書章句集註 first page preview"> | **四書章句集註** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/sishu-jizhu-aginti.png" width="150" alt="四書章句集註 first page preview"> | **四書章句集註** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/snow-country.png" width="150" alt="雪国 first page preview"> | **雪国** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/spring-snow-jp-en.png" width="150" alt="Spring Snow first page preview"> | **Spring Snow** | EN-JP · en-main · color |
| <img src="assets/readme-previews/spring-snow-zh-en.png" width="150" alt="春雪 first page preview"> | **春雪** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/spring-snow-zh-jp.png" width="150" alt="春雪 first page preview"> | **春雪** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/the-martian-jp-en.png" width="150" alt="The Martian first page preview"> | **The Martian** | EN-JP · en-main · color |
| <img src="assets/readme-previews/the-martian-zh-en.png" width="150" alt="火星救援 first page preview"> | **火星救援** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/the-martian-zh-jp.png" width="150" alt="火星救援 first page preview"> | **火星救援** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/the-old-capital.png" width="150" alt="古都 first page preview"> | **古都** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/the-sirens-of-mars-jp-en.png" width="150" alt="The Sirens of Mars first page preview"> | **The Sirens of Mars** | EN-JP · en-main · color |
| <img src="assets/readme-previews/the-sirens-of-mars-zh-en.png" width="150" alt="火星的塞壬 first page preview"> | **火星的塞壬** | ZH-EN · zh-main · color |
| <img src="assets/readme-previews/the-sirens-of-mars-zh-jp.png" width="150" alt="火星的塞壬 first page preview"> | **火星的塞壬** | ZH-JP · zh-main · color |
| <img src="assets/readme-previews/woman-in-the-dunes.png" width="150" alt="砂女 first page preview"> | **砂女** | ZH-JP · zh-main · color |

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
make readme-assets
```

## Data Model

The core format is a paragraph/chapter JSON model. Text is split into aligned reading units, and each token can carry a reading and an optional grammar role.

```json
{
  "zh": [{"t": "天", "r": "tiān", "g": "subject"}, {"t": "地", "r": "dì", "g": "subject"}],
  "ja": [[{"t": "天", "r": "てん", "g": "subject"}, {"t": "地", "r": "ち", "g": "subject"}]]
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
| `assets/edition-comparisons/` | single-sentence and four-edition comparison images generated from interior PDF pages |
| `references/` | design notes, naming notes, and pipeline references |
| `sources/` | local source books, ignored by Git |
| `build/` | generated PDFs and TeX intermediates, ignored by Git |

## Public Use

PocketPolyglot is designed for language learners, teachers, and book builders who want maintainable bilingual editions rather than manually aligned TeX. Keep source rights clear: publish templates, samples, and previews freely; publish full book PDFs only when the source text and translation can be redistributed.

Project site: [learn.lazying.art](https://learn.lazying.art)
