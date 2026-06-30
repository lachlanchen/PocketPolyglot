# Yijing Quadrilingual Task

Status: complete.

Prepared output:

- Book id: `yijing`
- Chapters: `73`
- Chunks: `948`
- Main spine: Wenyan `周易`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Cover: `assets/covers/yijing/background.png`

Completed run:

- Session: `zhjpbook-yijing-100-low`
- Workers: `100`
- Model/reasoning: `gpt-5.5`, `low`
- Coverage: `948/948`, no missing chunks, no stale chunks
- Grammar backfill: applied to all chunk JSON files
- PDF pages: `1079`

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

Launch command used:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  yijing zhjpbook-yijing-100-low
```

Built PDFs:

- `build/yijing/wenyan-main-quadrilingual/large-font/color/周易（英文・現代日本語・現代中文注）・大字版.pdf`
- `build/yijing/wenyan-main-quadrilingual/large-font/blackwhite/周易（英文・現代日本語・現代中文注・黑白）・大字版.pdf`

Synced PDFs:

- `/home/lachlan/Nutstore Files/Projects/LinguaLeaf/final-pdfs/文言文-English-日本語-中文/yijing/color/周易（英文・現代日本語・現代中文注）・大字版｜文言文-English-日本語-中文｜彩色.pdf`
- `/home/lachlan/Nutstore Files/Projects/LinguaLeaf/final-pdfs/文言文-English-日本語-中文/yijing/blackwhite/周易（英文・現代日本語・現代中文注・黑白）・大字版｜文言文-English-日本語-中文｜黑白.pdf`
- `/home/lachlan/Nutstore Files/Share/LinguaLeaf/color/周易（英文・現代日本語・現代中文注）・大字版｜文言文-English-日本語-中文｜彩色.pdf`
- `/home/lachlan/Nutstore Files/Share/LinguaLeaf/blackwhite/周易（英文・現代日本語・現代中文注・黑白）・大字版｜文言文-English-日本語-中文｜黑白.pdf`
