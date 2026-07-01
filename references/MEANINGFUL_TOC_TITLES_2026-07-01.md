# Meaningful TOC Titles For Classical Books - 2026-07-01

Classical source pages often expose two title layers: a short path title such as
`卷47` and a richer Wikisource header such as `卷47 班梁列傳 第三十七`.
Pocket-size quadrilingual books should use the richer title for chapter
metadata and the table of contents.

## Rules

- Prefer source-header chapter metadata over generated chunk titles when
  assembling a book JSON.
- Preserve concise volume numbers, but include the meaningful person, emperor,
  treatise, or chapter name when the source provides one.
- Keep the displayed chapter title ruby/pinyin-enabled, but write a plain text
  TOC entry so the PDF contents page stays readable.
- Do not regenerate completed chunk JSON only to fix chapter names. Refresh the
  task manifest and let assembly override stale chapter-title fields.
- Apply this to unfinished split manifests before resuming writers, so later
  parts do not inherit `卷X`-only titles.

## Hou Hanshu Example

The old TOC used entries like `卷47`. The corrected metadata uses entries like
`卷47 班梁列傳 第三十七`, `卷一上‧光武帝紀第一上`, and
`卷74上 袁紹劉表列傳 第六十四上`.

The relevant code paths are:

- `scripts/interlinear/prepare_classical_quadrilingual_task.py` extracts raw
  Wikisource header sections and writes `chapter_title_wenyan`.
- `scripts/interlinear/assemble_quadrilingual_json.py` prefers source chapter
  titles over stale generated chunk titles.
- `scripts/interlinear/json_to_quadrilingual_wenyan_tex.py` passes a plain TOC
  title to TeX.
- `tex/interlinear-quadrilingual/style.tex` renders ruby/pinyin chapter headings
  while using the plain title in `\tableofcontents`.
