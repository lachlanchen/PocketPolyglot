# Editable Textbook TeX Quality Protocol

This workflow is for turning formula-heavy PDFs into real pocket-size TeX/PDF books. The output must be text, TeX formulas, TeX tables, and extracted figures, not page-image facsimiles.

## Pipeline

1. Keep the original PDF in `sources/` only; do not commit it.
2. Run Mathpix whole-PDF conversion through `scripts/interlinear/textbook_mathpix_pdf_job.py`.
3. Compile with `scripts/interlinear/compile_textbook_english_pocket.py`.
4. Validate with `scripts/interlinear/validate_textbook_editable_pdf.py`.
5. Generate page-level review tasks with `scripts/interlinear/prepare_textbook_editable_review_tasks.py --render-images`.
6. Fix durable OCR/content errors in tracked `books/<book>/editable-fixes.json`, not in generated `build/**/source.tex`.
7. Recompile and require: no missing images, no oversized floats, no explicit OCR-garbage markers, and all remaining overfulls represented as review tasks.

## Current Status

| Book | PDF pages | Overfull | Oversized floats | OCR markers | Review tasks |
| --- | ---: | ---: | ---: | ---: | ---: |
| `game-theory` | 646 | 8 | 0 | 0 | 8 |
| `game-theory-101` | 469 | 1 | 0 | 0 | 1 |
| `nonlinear-dynamics-and-chaos` | 1094 | 2 | 0 | 0 | 2 |
| `chaos-making-new-science` | 615 | 14 | 0 | 0 | 12 |
| `qft-gifted-amateur` | 1106 | 74 | 0 | 0 | 21 |

## Remaining Work To Reach “Perfect”

- For each `tasks/editable-review/tasks.jsonl` entry, compare `source_page_image`, embedded source text, and generated TeX.
- Repair prose OCR with `editable-fixes.json` when the error is durable and exact.
- Repair formula overflow by editing the generated TeX pattern into proper `aligned`, `split`, `gathered`, or smaller local display blocks. Do not silence warnings with `hfuzz` or by deleting equations.
- Preserve figures and captions; if a figure is too large, constrain it with `max width`, `max totalheight`, and `keepaspectratio`.
- Re-run compile and validation after every repair group, then commit tracked fixes and review manifests.

The automatic pipeline is now good enough to produce usable drafts. QFT remains the hardest case because most remaining defects are long equations that need mathematical line breaking, not OCR cleanup.
