# Three Caos And Sahara Illustrated Finalization - 2026-07-30

## Three Caos

The completed quadrilingual JSON was reused without new model calls. Each work
now has a textless generated `background.png`, a deterministic composed
`cover.png`, and maximum-language large-font color and black-white exports.

| Book | JSON coverage | Large-font pages | Share language family |
| --- | ---: | ---: | --- |
| `cao-cao-wei-wudi-ji` / 魏武帝集 | 260 / 260 | 567 | `文言文-English-日本語-中文` |
| `cao-pi-wei-wendi-ji` / 魏文帝集 | 76 / 76 | 183 | `文言文-English-日本語-中文` |
| `cao-zhi-cao-zijian-ji` / 曹子建集 | 289 / 289 | 1019 | `文言文-English-日本語-中文` |

Canonical local builds:

```text
build/<book-id>/maximum-language-large-font/wenyan-main-quadrilingual/{color,blackwhite}/
```

Nutstore destinations:

```text
/home/lachlan/Nutstore Files/Share/LinguaLeaf/{color,blackwhite}/
/home/lachlan/Nutstore Files/NoSync/Projects/LinguaLeaf/final-pdfs/
```

## Sahara Illustrated Editions

The original trilingual books were not changed. Three additive projects reuse
their completed English/Japanese/Chinese JSON and restore the figure anchors
already retained by source preparation:

| New project | Reused source project | Figures | Large-font pages |
| --- | --- | ---: | ---: |
| `sahara-cultural-history-illustrated` | `sahara-cultural-history` | 55 | 1278 |
| `round-heads-sahara-illustrated` | `round-heads-sahara` | 47 | 869 |
| `origins-earth-human-history-illustrated` | `origins-earth-human-history` | 28 | 1320 |

Canonical local builds:

```text
build/<illustrated-book-id>/maximum-language-large-font/en-main-jp-zh/{color,blackwhite}/
```

The source-ordered image audit found:

- Sahara Cultural History: 55 figures plus one cover image.
- Round Heads: 47 figures plus one cover image.
- Origins: 28 figures plus one cover image. Two figures share one output page,
  so 29 image objects occupy 28 distinct image-bearing pages.
- All referenced figure files exist.
- All six illustrated large-font TeX logs have zero overfull boxes, zero
  missing-figure messages, and zero LaTeX errors.

## Reusable Pipeline Work

- `json_to_trilingual_en_notes_tex.py --include-figures` now renders paragraph
  figure anchors only when explicitly requested. Existing non-illustrated
  books retain their previous output.
- `prepare_illustrated_trilingual_edition.py` creates an additive edition plan
  that reuses validated chunk JSON.
- `validate_trilingual_figure_assets.py` proves expected figure count and file
  existence before compilation.
- `compile_trilingual_illustrated_book.sh` assembles, validates, renders, and
  compiles the figure-preserving English-main/Japanese/Chinese edition.
- `compose_book_cover.py` accepts optional `cover_title_*` fields, allowing a
  derivative edition to identify itself without modifying the textless
  background.

## Verification

```sh
python3 scripts/interlinear/test_trilingual_en_notes_figures.py
python3 -m py_compile \
  scripts/books/compose_book_cover.py \
  scripts/interlinear/json_to_trilingual_pair_tex.py \
  scripts/interlinear/json_to_trilingual_en_notes_tex.py \
  scripts/interlinear/prepare_illustrated_trilingual_edition.py \
  scripts/interlinear/validate_trilingual_figure_assets.py
```

The final Share copies were opened with `pypdf`, inspected with
`pdfimages -list`, and checked for a first-page image cover. Public filenames
use Nutstore-safe fullwidth punctuation.
