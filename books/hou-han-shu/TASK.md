# Hou Hanshu Quadrilingual Task

Status: prepared only, not started.

Prepared output:

- Book id: `hou-han-shu`
- Chapters: `131`
- Chunks: `13152`
- Main spine: Wenyan `後漢書`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required after chunk generation
- Font profile: large LinguaLeaf pocket font profile

Source layout:

- Wenyan spine: `sources/hou-han-shu/zh/wenyan-wikisource`
- Li Xian/commented Chinese reference: `sources/hou-han-shu/zh/li-xian-commentary/後漢書.pdf`
- English partial reference: `sources/hou-han-shu/en/military-history-ethnicity/Fan Ye's Book of Later Han (Houhanshu)_ Military History and Ethnicity 1.pdf`
- Japanese excerpt reference: `sources/hou-han-shu/jp/waden-excerpt/Gokanjo-Waden-Fan-Ye-Aozora.html`

Prepared files:

- Plan: `books/hou-han-shu/book-plan.json`
- Manifest: `books/hou-han-shu/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/hou-han-shu/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/hou-han-shu/markdown/wenyan.md`

Important source-order note:

- `注補續漢書八志序` must stay between `卷90` and `卷91`.
- The current prepared Markdown and manifest use that order.

Launch later, but do not run until requested:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  hou-han-shu zhjpbook-hou-han-shu-100-low
```

After generation, run grammar-role backfill, compile color and black-white large-font PDFs, validate manifest coverage and overflow, then sync final PDFs to the LinguaLeaf Nutstore folders.
