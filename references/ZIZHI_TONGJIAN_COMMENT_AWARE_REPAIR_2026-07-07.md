# Zizhi Tongjian Comment-Aware Repair - 2026-07-07

The comment-aware `資治通鑑` build derives `注` / `音` spans from the source
PDF font layer. This is accurate for most inline Hu Sanxing notes, but the same
small-font layer is also used for structural material that should remain main
source text.

## Correction Rule

Keep as main text:

- front/editorial chapters: `胡刻通鑑正文校宋記述略`,
  `新註資治通鑑序`, `興文署新刊資治通鑑序`,
  `宋神宗資治通鑑序 禦製`;
- repeated volume-opening source headings, including official title lines,
  `司馬光 奉敕編集`, `胡三省 音 註`, and dynasty range headings such as
  `周紀一...` or `唐紀四十四...`;
- Sima Guang's `進書表` and following colophon/editorial appendices;
- final electronic collation chapters.

Keep as `注` or `音`:

- inline explanatory notes, geography notes, textual apparatus, quotation
  apparatus, and pronunciation glosses inside the chronicle.

## Implementation

Added `scripts/interlinear/repair_zizhi_tongjian_comment_sidecar.py` and wired it
into both Zizhi comment-aware compile scripts. The expensive generated language
JSON is untouched; only the ignored local sidecar is rewritten before TeX
rendering.

Latest local audit:

- records scanned: `362989`
- structural heading keys protected: `1175`
- front/editorial records already or newly protected: `467`
- volume-heading records protected: `1175`
- postscript records protected: `112`
- remaining structural headings rendered as non-main: `0`

Validation spot checks confirmed the first emperor preface, repeated `司馬光`
headings, `胡三省 音 註`, dynasty range headings, and late colophon names now
render as main text, while ordinary inline notes such as `《爾雅》...` remain
`注`.
