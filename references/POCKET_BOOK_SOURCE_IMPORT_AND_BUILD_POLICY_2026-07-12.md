# Pocket Book Source Import And Build Policy - 2026-07-12

The current stage is not LinguaLeaf multilingual generation.  The goal is a
clean, high-quality, large-font pocket-size book from each original source,
built through real TeX.

## Source Storage

All newly supplied books were copied into ignored `sources/` folders.  Original
files in `/home/lachlan/Downloads` were not moved.

Tracked task manifest:

`build-pocket/tasks/source-queue-2026-07-12.json`

Local build workspace:

`build-pocket/`

Nutstore Share destination for final pocket PDFs:

`/home/lachlan/Nutstore Files/Share/PocketBooks/`

## New Main Groups

| Group | New source set |
| --- | --- |
| History left / world history | China dynastic history, Iran, Arab peoples, Middle East, Europe, Habsburgs, Ottomans, Japan, Ancient Egypt, Central Asia |
| Leonard Susskind | `The Cosmic Landscape`; `An Introduction to Black Holes, Information and the String Theory Revolution` |
| Mars | `Green Mars`; `Blue Mars` |
| Historical / world literature | `I, Claudius`, `Wolf Hall`, `The Cairo Trilogy`, `The Bridge on the Drina`, `Shahnameh`, `The Janissary Tree`, `My Name Is Red` |

## Build Rule

For each book:

1. Keep the original source under `sources/`.
2. Produce an exact/review TeX edition under `build-pocket/<book-id>/exact/`.
3. Preserve figures, maps, diagrams, charts, equations, tables, and captions.
4. Produce a large-font pocket edition under
   `build-pocket/<book-id>/pocket-large-font/`.
5. Generate or compose a clean cover.
6. Validate PDF, TOC, text extraction, overfull lines, and representative pages.
7. Deterministically remove duplicated source-printed TOCs, normalize tables,
   constrain figures, and scale long display math to the pocket width.
8. If severe layout evidence remains, optionally run one final scoped
   `codex exec` pass using `gpt-5.5` with `xhigh` reasoning. This pass receives
   only generated-TeX hotspots and must not spawn nested agents or loop. Invoke
   it with Codex's no-sandbox CLI flag so the subprocess can actually read and
   edit the generated TeX instead of failing inside nested workspace sandboxing.
9. Recompile once after that final pass and validate the evidence again.
10. Sync only final pocket PDFs to the Nutstore Share `PocketBooks` folder.

Generated `build-pocket` contents are ignored except this task metadata.

## Non-Negotiable Constraint

Do not create facsimile, page-image-only, or hidden-OCR-layer output for this
queue.  The acceptable route is:

```text
PDF / EPUB / MOBI / AZW3 source
  -> real extracted or OCR-corrected TeX body
  -> exact/review PDF from that TeX
  -> large-font pocket PDF from the same TeX body
```

For PDF sources, local Mathpix-like tooling may extract figures as referenced
image assets, but the book body must remain real text/math/table TeX.  If the
local toolchain cannot produce a credible TeX body for a book, the runner must
write a blocked status with logs and validation evidence, not a placeholder PDF.
