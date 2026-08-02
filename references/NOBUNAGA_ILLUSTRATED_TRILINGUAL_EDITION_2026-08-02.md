# Nobunaga Illustrated Trilingual Edition - 2026-08-02

## Result

`chronicle-lord-nobunaga-illustrated` is an additive illustrated edition of
the completed English-main `chronicle-lord-nobunaga` project. It reuses the
validated English, modern Japanese, modern Chinese, ruby, and grammar tokens
without model calls or translation regeneration.

The English main layer is the immutable text extracted from:

`sources/japan-history/sengoku/primary-source-translations/shincho-koki/en/The Chronicle of Lord Nobunaga - Ota Gyuichi.pdf`

Source SHA-256:

`6bc9f445dc807891adf87d0fc79d252e45492b8548304907d6c273d5d13dd1bd`

The historical Japanese source edition is retained as reference evidence, but
was not inserted as another interlinear layer because it is not reliably
sentence-aligned with the scholarly English edition. The existing Japanese
layer remains readable modern Japanese.

## Restored Figures

The source PDF contains one cover image, one publisher mark, and fifteen body
maps. Only the fifteen substantive maps were restored.

| Map | Source PDF page | Caption |
| ---: | ---: | --- |
| 1 | 73 | Owari Province |
| 2 | 140 | Ōmi Province |
| 3 | 155 | Ise and Iga Provinces |
| 4 | 172 | The Ozaka Honganji |
| 5 | 209 | Kyoto and Periphery |
| 6 | 232 | The Delta |
| 7 | 244 | Mikawa Province |
| 8 | 254 | Echizen Province |
| 9 | 283 | Izumi and Kii Provinces |
| 10 | 309 | The Western Front |
| 11 | 325 | Settsu Province |
| 12 | 385 | The Northern Front |
| 13 | 448 | Shinano and Kai Provinces |
| 14 | 474 | Suruga and Tōtōmi Provinces |
| 15 | 498 | Japan in the Sixteenth Century |

Each map is extracted losslessly with `pdfimages`, matched to a unique
English-source paragraph, and recorded with its source PDF page, paragraph ID,
source phrase, image hash, and source PDF hash.

Tracked configuration:

`data/source-plan/sengoku-history/chronicle-lord-nobunaga-figures.json`

Generated local figure manifest:

`books/chronicle-lord-nobunaga-illustrated/work/trilingual/assets/figure-manifest.json`

## Reusable Workflow

```sh
python scripts/interlinear/extract_pdf_figures_to_manifest.py \
  data/source-plan/sengoku-history/chronicle-lord-nobunaga-figures.json

python scripts/interlinear/prepare_illustrated_trilingual_edition.py \
  --source-book-id chronicle-lord-nobunaga \
  --output-book-id chronicle-lord-nobunaga-illustrated \
  --figure-manifest books/chronicle-lord-nobunaga-illustrated/work/trilingual/assets/figure-manifest.json \
  --keep-title

scripts/interlinear/compile_trilingual_illustrated_book.sh \
  --book-id chronicle-lord-nobunaga-illustrated \
  --color-mode color

scripts/interlinear/compile_trilingual_illustrated_book.sh \
  --book-id chronicle-lord-nobunaga-illustrated \
  --color-mode blackwhite
```

`apply_trilingual_figure_manifest.py` overlays figures after JSON assembly, so
the source chunks and completed translation chunks remain unchanged.

## Validation

- Figure overlay: `15/15`, with no missing assets.
- Rendered `TriAllFigure` calls: `15` in each TeX variant.
- Embedded PDF images: `16` per PDF, consisting of one cover plus fifteen maps.
- Color PDF: `2516` pages.
- Black-white PDF: `2516` pages.
- XeLaTeX overfull boxes: `0` in both variants.
- Missing-character and LaTeX errors: `0` in both variants.
- `qpdf --check`: passed for both variants and both Nutstore Share copies.
- Visual contact-sheet review: all maps are readable, correctly oriented,
  source-ordered, proportionally scaled, and captioned.

## Nutstore

The earlier figureless Share copies were replaced by the illustrated
maximum-language large-font PDFs:

- `Share/LinguaLeaf/color/The Chronicle of Lord Nobunaga（日文・中文注）｜English-日本語-中文｜彩色.pdf`
- `Share/LinguaLeaf/blackwhite/The Chronicle of Lord Nobunaga（日文・中文注）｜English-日本語-中文｜黑白.pdf`

Matching copies are stored under:

`NoSync/Projects/LinguaLeaf/final-pdfs/English-日本語-中文/chronicle-lord-nobunaga-illustrated/`
