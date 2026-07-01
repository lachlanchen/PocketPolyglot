# Boilerplate Cleanup Summary - 2026-07-02

This pass removed source/license boilerplate from active LinguaLeaf book
outputs, including Wikisource public-domain notices, Project Gutenberg
boilerplate, and redirect stubs that had leaked into rendered text.

## Data Cleanup

- Added `scripts/interlinear/audit_prune_boilerplate_chunks.py` to audit and
  prune boilerplate records from book chunk manifests and overlay task plans.
- Pruned affected source/task records from active manifests for `chuci`,
  `han-shu`, `les-miserables`, `sanguozhi`, `shijing`, `sishu-jizhu`,
  `tangshi-sanbai`, and `the-old-capital`.
- Reassembled `sanguozhi-pei-zhu` from the cleaned Sanguozhi base JSON and
  clean Pei Songzhi commentary chunks.

## Export Fixes

- Updated the large-font export pipeline to avoid stale public PDFs when a
  clean local PDF is over the GitHub size limit.
- Updated Nutstore sync to read from the complete local artifact tree:
  `artifacts/lingualleaf/books`.
- Fixed `sanguozhi-pei-zhu` export discovery so it uses the real
  `wenyan-main-quadrilingual/large-font` PDFs, not the normal-size PDF renamed
  as a large-font export.

## Nutstore Cleanup

Archived six stale duplicate Share PDFs and six stale duplicate Projects PDFs
with the old `・大字版` filename style for:

- `詩經`
- `楚辭`
- `唐詩三百首`

Archive roots:

- `/home/lachlan/Nutstore Files/Share/LinguaLeaf-archive/boilerplate-stale-20260702`
- `/home/lachlan/Nutstore Files/Projects/LinguaLeaf/archive/boilerplate-stale-20260702`

## Verification

- `python scripts/interlinear/audit_prune_boilerplate_chunks.py --no-report`
  returned `affected_records=0`.
- Full artifact PDF text scan: `104` PDFs, `0` hits, `0` extraction errors.
- Active Nutstore Share scan: `122` PDFs, `0` hits, `0` extraction errors.
- Active Nutstore Projects scan: `122` PDFs, `0` hits, `0` extraction errors.
- Public `../LinguaLeaf/docs/pocketpolyglot/books` scan: `103` PDFs, `0`
  hits, `0` extraction errors.
- `sanguozhi-pei-zhu` final large-font artifact and Nutstore copy both report
  `12042` pages.
