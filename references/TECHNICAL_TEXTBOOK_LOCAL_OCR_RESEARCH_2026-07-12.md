# Technical Textbook Local OCR Research - 2026-07-12

Goal: convert formula/table/figure-heavy textbooks into pocket-size editable TeX
and EN/ZH JSON without treating pages as screenshots. The five prepared books
are `game-theory`, `game-theory-101`, `nonlinear-dynamics-and-chaos`,
`chaos-making-new-science`, and `qft-gifted-amateur`.

## Tool Findings

| Tool | Role | Local status | Use in this repo |
| --- | --- | --- | --- |
| Marker + Surya | Whole-PDF/page conversion to Markdown/JSON with layout, OCR, tables, figures, and equations | Installed in `.venv/ocr` target; global install had dependency conflicts | Primary local OCR engine for smoke tests and full page parsing |
| MinerU | Mathpix-like PDF parser for Markdown/JSON/LaTeX-style outputs, good for scientific PDFs | Not installed yet | Secondary engine for cross-checking pages where Marker loses structure |
| Docling | General document conversion with OCR/table structure | Not installed yet | Tertiary validator for text/table structure |
| Pix2Text / pix2tex | Formula OCR fallback for cropped equations | `pix2tex` available; Pix2Text not installed | Targeted equation repair when whole-page engines disagree |
| Mathpix | Commercial high-accuracy baseline | Previous artifacts exist under `books/*/work/exact-tex/mathpix-pdf/` | Optional validator; do not overwrite existing artifacts |
| olmOCR / VLM OCR | Heavy model fallback for hard pages | Not installed | Last-resort page validator on GPU, not first-line pipeline |

## Chosen Pipeline

1. Keep original PDFs in ignored `sources/`.
2. Preserve the existing exact-TeX/Mathpix artifacts and task manifests.
3. Generate local OCR task contracts with
   `scripts/interlinear/prepare_textbook_local_ocr_en_zh_tasks.py`.
4. Smoke-test page ranges with
   `scripts/interlinear/run_textbook_local_ocr.py --book-id <id> --smoke`.
5. For each page, produce ordered nodes:
   - `prose`: English source plus Chinese translation.
   - `math`: exact TeX copied unchanged across language editions.
   - `figure`: extracted/cropped image plus translated caption/comment.
   - `table`: preserved cell grid; translate prose cells only.
6. Compile the English pocket TeX first, then derive EN/ZH JSON and PDFs.
7. Validate against source page images, TeX logs, missing-image checks, and
   overfull-line reports.

## Quality Rules

- Never translate or paraphrase equations.
- Never replace payoff matrices, phase portraits, Feynman diagrams, tables, or
  exercises with prose summaries.
- Keep equation, theorem, figure, table, section, and chapter numbering.
- If OCR engines disagree, store both outputs and mark the page for review.
- If a formula is missing or malformed, crop the equation and run pix2tex before
  asking a language model to infer anything.
- For page-image-heavy fragments, keep the image as an anchored figure and add
  a review task instead of pretending it is editable TeX.

## Prepared Artifacts

- Queue: `data/source-plan/technical-textbook-local-ocr-en-zh-queue.json`
- Per-book local OCR manifests:
  `books/<book-id>/tasks/local-ocr-en-zh/manifest.json`
- Per-page local OCR tasks:
  `books/<book-id>/tasks/local-ocr-en-zh/pages.jsonl`
- Work output root:
  `books/<book-id>/work/exact-tex/local-ocr/`

## Source References Used For Tool Research

- Marker: <https://github.com/VikParuchuri/marker>
- Surya OCR: <https://github.com/datalab-to/surya>
- MinerU: <https://github.com/opendatalab/MinerU>
- Docling: <https://github.com/docling-project/docling>
- Pix2Text: <https://github.com/breezedeus/Pix2Text>
- pix2tex / LaTeX-OCR: <https://github.com/lukas-blecher/LaTeX-OCR>
- olmOCR: <https://github.com/allenai/olmocr>

