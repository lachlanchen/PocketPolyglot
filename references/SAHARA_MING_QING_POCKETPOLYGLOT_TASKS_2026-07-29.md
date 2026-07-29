# Sahara And Ming-Qing PocketPolyglot Tasks

Date: 2026-07-29

The source archive from `../Books` has been copied into this repository's
ignored `sources/` tree. Originals in `../Books` and `~/Downloads` remain
unchanged. No model workers or conversion queues were started.

## Prepared Queues

| Order | Queue | Books | Current state |
| ---: | --- | ---: | --- |
| 1 | `data/source-plan/sahara-exact-pocket-queue.json` | 3 | Launchable; not started |
| 2 | `data/source-plan/sahara-trilingual-queue.json` | 3 | Waiting for validated exact TeX |
| 3 | `data/source-plan/ming-qing-multilingual-queue.json` | 11 | Source tasks prepared; not chunked or started |

## Sahara Workflow

| Priority | Book | Exact source evidence | Exact task | Multilingual task |
| ---: | --- | --- | --- | --- |
| 1 | *The Sahara: A Cultural History* | 287 pages, 448,877 text characters, 56 embedded images | Real TeX exact + pocket, preserving all meaningful images and captions | EN-JP-ZH after exact validation |
| 2 | *Round Heads* | 199 pages, 337,057 text characters, 175 embedded images | Real TeX exact + pocket, preserving archaeological figures | EN-JP-ZH after exact validation; ICOMOS source as terminology reference |
| 3 | *Origins* | 311 pages, 551,029 text characters, 38 embedded images | Real TeX exact + pocket, preserving figures, maps, and tables | EN-JP-ZH after exact validation |

Run only the exact stage with:

```bash
python scripts/books/build_pocket_tex_queue.py \
  --queue data/source-plan/sahara-exact-pocket-queue.json
```

The exact queue forbids facsimile and page-image-only completion. Each task
uses the `technical_exact` validator with zero required math blocks, because
the strict requirement here is full text and figure preservation rather than
equation density.

The multilingual queue must remain blocked until these paths exist and pass
validation:

```text
build-pocket/<book-id>/exact/tex/book.tex
build-pocket/<book-id>/exact/book.pdf
build-pocket/<book-id>/pocket-large-font/book.pdf
```

Figures are deterministic assets. Language-model chunks translate text and
captions but do not regenerate, reinterpret, or omit figures.

## Chinese Workflow

| Priority | Work | Source classification | Text spine | Preparation route |
| ---: | --- | --- | --- | --- |
| 1 | 《素女經》 | Classical Chinese | Wikisource raw text | `wenyan` + EN + modern JP + modern ZH |
| 2 | 《金瓶梅詞話》 | Premodern vernacular novel | Complete Wikisource PDF | Original ZH + EN + modern JP; scan is evidence |
| 3 | 《肉蒲團》 | Premodern vernacular novel | Complete Wikisource PDF | Original ZH + EN + modern JP; scan is evidence |
| 4 | 《品花寶鑒》 | Qing vernacular novel | EPUB | Reconcile simplified EPUB with traditional Wikisource |
| 5 | 《癡婆子傳》 | Premodern vernacular tale | UTF-8 transcription | Verify uncertain text against Kyoto scan |
| 6 | 《蜃樓志》 | Qing vernacular novel | Wikisource PDF | Verify 25 sections against searchable edition |
| 7 | 《鬧花叢》 | Premodern vernacular text | EPUB | Extract and validate 14 XHTML sections |
| 8 | 《繡榻野史》 | Premodern vernacular text | Wikisource PDF | Use scan as character and heading witness |
| 9 | 《載花船》 | Scan only | None yet | Page-aware OCR and correction required |
| 10 | 《株林野史》 | Scan with garbled text layer | None yet | Ignore bad layer; page-aware OCR required |
| 11 | 《綠野仙蹤》 | Full scan plus incomplete public text | Full scan after OCR | Calibrate only chapters 1-43 against Wikisource |

Only 《素女經》 is assigned the `wenyan` schema by default. The novels keep
their original Chinese source layer instead of receiving a false classical
classification. Their generated Japanese must be modern and readable; English
must be complete and idiomatic. Modern Chinese may be added as explanatory
material later, but must not replace the source text.

## Quality And Rights Contracts

- Preserve chapter order, prefaces, poems, notes, traditional/simplified
  evidence, and page references.
- Remove Wikisource interface text, HTML fragments, page chrome, OCR headers,
  and artificial PDF line breaks before chunking.
- Validate source coverage before starting model workers.
- Compile maximum-language large-font color and black-white editions with a
  cover, TOC, grammar roles, pinyin, and Japanese furigana.
- Several Chinese works contain explicit sexual material; final editions
  require mature-content metadata.
- The three Sahara books are modern commercial editions supplied for private
  study. Do not publish complete derivative books without permission. The
  ICOMOS comparison source remains subject to its CC BY-NC-SA license.
