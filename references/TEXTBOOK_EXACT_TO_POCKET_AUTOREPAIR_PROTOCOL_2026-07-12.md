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

## Evidence-Gated Exact Polishing Queue

Use the `build-pocket-polished` workflow when a real exact TeX body already
exists but still needs page/chunk-level OCR repair, English cleanup, readable
modern Japanese, and stricter publication validation.

Each source task declares an immutable wrapper and body:

```json
{
  "book_id": "example-mathpix-exact-book",
  "source_exact_tex": "build/example/exact/source.tex",
  "source_body_tex": "build/example/work/body.tex",
  "validation_profile": "technical_exact"
}
```

Prepare a reusable queue without modifying either upstream file:

```bash
python scripts/books/prepare_build_pocket_polished.py \
  --queue data/source-plan/technical-exact-polished-queue.json \
  --output-queue build-pocket-polished/tasks/technical-exact-queue.json
```

Start or resume it in an isolated tmux session:

```bash
WORKERS=5 MODEL=gpt-5.6-sol REASONING=low \
  bash scripts/books/start_technical_exact_polished_tmux.sh
```

The runner performs these gates:

1. Flatten the wrapper and body into a new standalone evidence snapshot.
2. Verify the split is byte-lossless and record its SHA-256 digest.
3. Keep figures, diagrams, notation images, citations, labels, references, and
   URLs immutable.
4. Permit mathematical TeX repair only for grounded OCR defects, with an exact
   before/after change record. English and Japanese must retain the same math
   atom multiset even when Japanese grammar reorders clauses.
5. Preserve table rows/columns, numbers, structural commands, technical
   environments, object counts, paths, and ordering through deterministic
   validation.
6. Require a separate semantic reviewer to accept every chunk.
7. Center standalone figures and derive a true A6 pocket layout from either
   `\geometry{...}` or package-option geometry syntax.
8. Compile exact and pocket English/Japanese PDFs with XeLaTeX. Missing assets,
   non-searchable output, TeX errors, object-count changes, or overflow above
   the configured gate stop the queue for repair instead of producing a false
   completion claim.

The default output/status paths are:

```text
build-pocket-polished/<book-id>/
build-pocket-polished/status-technical-exact.json
```

Set `PREPARE_FORCE=1` only after changing segmentation or validation policy.
Accepted JSON remains resumable; failed-attempt evidence stays under the
book-local `work/` directory.

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
