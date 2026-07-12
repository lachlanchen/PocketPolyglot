# Build Pocket Workspace

`build-pocket/` is the local workspace for high-quality exact-to-pocket books.
This is separate from LinguaLeaf/PocketPolyglot multilingual generation.

## Current Policy

- Keep all original source books under `sources/`.
- Do not commit large generated PDFs, OCR caches, image layers, or TeX scratch.
- First create an exact/review edition from the source book as real TeX.
- Then create a large-font pocket edition from the reviewed body.
- Preserve figures, maps, diagrams, charts, formulas, equations, tables,
  captions, music notation, and exercise layouts as first-class content.
- Never produce facsimile, page-image-only, or hidden-OCR-layer books for this
  workspace. If the local PDF-to-TeX toolchain cannot recover real text,
  math, tables, and figure references well enough, mark the book blocked with
  evidence instead of generating a fake completion.
- Deterministic cleanup runs first: remove duplicated source-printed TOCs,
  normalize tables, constrain figures, and scale long display math by wrapping
  the actual math in a wider internal TeX box that is reduced to pocket width.
  If severe layout evidence still remains after this compile, the runner may
  make exactly one final `codex exec` polish call with `gpt-5.5` / `xhigh`,
  scoped to generated TeX hotspots only, then recompile once for validation.
  That subprocess must use Codex's no-sandbox CLI flag; nested workspace
  sandboxing can fail before the agent can read or edit generated TeX.
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
- Figures/tables/equations are present and readable as TeX/math/table content
  where possible, with extracted figure assets used only for real visual
  objects such as maps, diagrams, charts, and illustrations.
- Pocket layout uses large, comfortable spacing and does not clip headers.
- Cover is clean, with text overlay separated from the generated art.
