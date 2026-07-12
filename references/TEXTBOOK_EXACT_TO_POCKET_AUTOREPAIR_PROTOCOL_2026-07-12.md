# Technical Textbook Exact-To-Pocket Autorepair Protocol - 2026-07-12

## Goal

Produce a correct, high-quality pocket-size book from the original input while
preserving real structure:

- prose as editable text;
- equations as TeX math;
- tables as TeX tables or verified table images when OCR structure is unsafe;
- figures, diagrams, graphs, music charts, notation, captions, and exercises as
  first-class content;
- a readable pocket layout with clean typography, no broken headers, no duplicate
  wrapper TOC, and no severe overfull lines.

The compile target is not just “a PDF exists”. The quality target is:

1. high-quality source recognition and transcription;
2. faithful exact/review TeX and PDF;
3. durable repair rules stored outside generated files;
4. pocket-size TeX/PDF derived from the same reviewed body;
5. validation evidence for page count, missing images, TeX errors, overfulls,
   text extraction, and representative page screenshots.

## Two-Stage Build

1. **Exact/review layer**
   - Source: Mathpix archive when available; otherwise local Marker/Surya OCR.
   - Output: `build/<book>-<mode>-exact-book/exact/source.tex` and PDF.
   - Purpose: check transcription, formulas, tables, captions, and figures before
     changing layout.
2. **Pocket layout layer**
   - Source: same TeX body as the exact layer.
   - Output: `build/<book>-<mode>-exact-book/pocket/source.tex` and PDF.
   - Typography follows the readable Susskind/LazyLearn pattern: no paragraph
     indentation, modest paragraph spacing, relaxed baseline, plain page style,
     and constrained figures.

## Reusable Commands

Raw compiler:

```bash
python3 scripts/interlinear/compile_textbook_exact_layers.py \
  --mode mathpix \
  --book-id game-theory \
  --passes 2
```

Autorepair compiler:

```bash
python3 scripts/interlinear/compile_textbook_exact_autorepair.py \
  --mode local \
  --book-id tom-kolb-music-theory-guitarists \
  --passes 2 \
  --max-rounds 8
```

Allow scoped Codex fallback only when deterministic repairs cannot classify the
failure:

```bash
python3 scripts/interlinear/compile_textbook_exact_autorepair.py \
  --mode local \
  --book-id tom-kolb-music-theory-guitarists \
  --passes 2 \
  --max-rounds 8 \
  --allow-codex \
  --codex-model gpt-5.5 \
  --codex-reasoning low
```

## Repair Policy

- Do not edit generated `build/**/source.tex` by hand.
- Durable source OCR fixes go in `books/<book>/local-exact-fixes.json`.
- Durable TeX-level fixes go in `books/<book>/local-exact-tex-fixes.json`.
- Shared, broadly reusable OCR/TeX repairs may be promoted into
  `scripts/interlinear/compile_textbook_exact_layers.py`.
- Ambiguous music notation should preserve the source figure and only repair
  obvious notation tokens such as `#`, flat, sharp, malformed `sqrt`, and escaped
  dollar math.
- If a local OCR table is structurally unsafe, keep the adjacent source figure as
  evidence and replace only the broken speculative table TeX.

## Validation Checklist

- `python3 -m py_compile scripts/interlinear/compile_textbook_exact_layers.py scripts/interlinear/compile_textbook_exact_autorepair.py`
- exact PDF exists and has plausible page count;
- pocket PDF exists and has plausible page count;
- `summary.json` reports image counts and text extraction counts;
- TeX logs have no fatal errors or missing image markers;
- severe overfull lines are either fixed or logged as review tasks;
- spot-check cover, early body page, formula/table page, figure-heavy page, and
  pocket text spacing.

