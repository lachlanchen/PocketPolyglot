# Pocket-Polished Heading And Technical-Structure Repair - 2026-08-02

## Scope

This repair applies to the shared `build-pocket-polished` technical-book
pipeline. It is not a Game Theory 101-only patch. The acceptance audit covers:

1. `game-theory-mathpix-exact-book`
2. `game-theory-101-mathpix-exact-book`
3. `qft-gifted-amateur-mathpix-exact-book`
4. `chaos-making-new-science-mathpix-exact-book`
5. `nonlinear-dynamics-and-chaos-mathpix-exact-book`
6. `berklee-music-theory-book-1-local-exact-book`
7. `tom-kolb-music-theory-guitarists-local-exact-book`

## Defects Corrected

- Japanese prose immediately following a translated heading could be lost
  during source/translation fusion.
- A segment containing more than one heading did not preserve every adjacent
  Japanese body independently.
- Pandoc hypertarget wrappers and copied source graphics could be duplicated in
  the Japanese secondary stream.
- Structural filtering could remove semantic math environments such as
  `cases`, `array`, or `aligned` from Japanese content.
- Caption spacing such as `\\[0pt]` could be mistaken for display math.
- Mathpix sometimes emitted equation tags inside arrays or matrices, which
  AMSMath rejects.
- Spaced bold Greek commands such as `\mathbf { \Omega }` could select legacy
  control-character font slots under XeTeX.
- QFT Figure 26.3 was split into three tall independent images instead of the
  source's one-row three-panel figure.

## Acceptance Invariants

The assembler now records an expected Japanese post-heading body for every
eligible source segment and requires each one to appear in the final fused TeX.
Completion is rejected when any expected body is absent. Technical completion
also requires:

- all manifest chunks accepted;
- source figure count and sequence preserved;
- referenced figure assets present;
- searchable PDF text;
- no TeX error markers;
- no missing-character markers;
- no overflow beyond the configured tolerance.

The source segmentation for Berklee Music Theory Book 1 contains no segment in
which a heading and following prose share one translation unit. Its expected
post-heading count is therefore `0/0`; chunk, object, compile, text, and layout
gates still apply.

## Evidence-Backed QFT Repairs

- Source PDF page 23 proves that equation tag `(5)` belongs to the complete
  Lorentz-transformation equation, not the first row of a vector.
- Source PDF page 257 proves that Figure 26.3 panels `(a)`, `(b)`, and `(c)` are
  a single horizontal row. The replacement is cardinality checked and keeps all
  three original image assets in source order.

The generic nested-tag normalizer repaired 128 additional single-tag Mathpix
structures. It refuses ambiguous structures containing multiple nested tags
instead of guessing.

## Final Audit

Run:

```sh
PYTHONPATH=scripts/books python scripts/books/audit_build_pocket_polished_structure.py \
  --queue data/source-plan/technical-exact-polished-queue.json \
  --require-complete \
  --json build-pocket-polished/tasks/technical-global-final-audit.json
```

Validated coverage:

| Book | Chunks | Japanese post-heading bodies | Result |
| --- | ---: | ---: | --- |
| Game Theory | 171/171 | 570/570 | pass |
| Game Theory 101 | 100/100 | 132/132 | pass |
| QFT for the Gifted Amateur | 280/280 | 711/711 | pass |
| Chaos: Making a New Science | 124/124 | 56/56 | pass |
| Nonlinear Dynamics and Chaos | 235/235 | 464/464 | pass |
| Berklee Music Theory Book 1 | 25/25 | 0/0 | pass |
| Music Theory for Guitarists | 65/65 | 5/5 | pass |

The QFT pocket PDF additionally validated with 2,639 pages, 286/286 figures,
zero overfull boxes, zero TeX errors, and zero missing glyphs.
