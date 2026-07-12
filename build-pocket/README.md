# Build Pocket Workspace

`build-pocket/` is the local workspace for high-quality exact-to-pocket books.
This is separate from LinguaLeaf/PocketPolyglot multilingual generation.

## Current Policy

- Keep all original source books under `sources/`.
- Do not commit large generated PDFs, OCR caches, image layers, or TeX scratch.
- First create an exact/review edition from the source book.
- Then create a large-font pocket edition from the reviewed body.
- Preserve figures, maps, diagrams, charts, formulas, equations, tables,
  captions, music notation, and exercise layouts as first-class content.
- Final user-facing pocket PDFs sync to:
  `/home/lachlan/Nutstore Files/Share/PocketBooks/`

## Per-Book Layout

Each book should use this local shape:

```text
build-pocket/<book-id>/
  exact/
    tex/
    figures/
    book.pdf
  review/
    source-map.md
    validation.md
  pocket-large-font/
    tex/
    figures/
    book.pdf
```

## Validation Before Sync

- PDF exists and opens.
- TOC is meaningful and not made from noisy OCR headings.
- Text extraction is clean enough to search and copy.
- No severe overfull lines.
- Figures/tables/equations are present and readable.
- Pocket layout uses large, comfortable spacing and does not clip headers.
- Cover is clean, with text overlay separated from the generated art.

