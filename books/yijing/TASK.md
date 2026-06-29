# Yijing Quadrilingual Task

Status: prepared only, not started.

Prepared output:

- Book id: `yijing`
- Chapters: `73`
- Chunks: `948`
- Main spine: Wenyan `周易`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Cover: `assets/covers/yijing/background.png`

Source layout:

- Wenyan spine: `sources/yijing/zh/wenyan-wikisource`
- Modern Chinese reference: `sources/yijing/zh/modern-annotated/周易.pdf`
- English references:
  - `sources/yijing/en/i-ching/I Ching.pdf`
  - `sources/yijing/en/bronze-age-document/The Book of Changes (Zhouyi)_ A Bronze Age Document.pdf`
- Japanese reference: `sources/yijing/jp/study/易学 成立と展開.pdf`

Prepared files:

- Plan: `books/yijing/book-plan.json`
- Manifest: `books/yijing/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/yijing/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/yijing/markdown/wenyan.md`

Launch later, but do not run until requested:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  yijing zhjpbook-yijing-100-low
```

After generation, compile color and black-white large-font PDFs, validate manifest coverage and overflow, then sync final PDFs to the LinguaLeaf Nutstore folders.
