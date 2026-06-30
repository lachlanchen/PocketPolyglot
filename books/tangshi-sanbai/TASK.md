# Tangshi Sanbai Quadrilingual Task

Status: prepared only. Do not start automatically.

Prepared output:

- Book id: `tangshi-sanbai`
- Chapters: `320`
- Chunks: `647`
- Main spine: Wenyan `唐詩三百首`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Source order: root Wikisource anthology order, starting `賊退示官吏`

Source layout:

- Wenyan spine: `sources/tangshi-sanbai/zh-wikisource-tangshi-sanbai`
- Wenyan export: `sources/tangshi-sanbai/zh-wikisource-export/唐詩三百首-Wikisource.epub`
- Chinese reference: `sources/tangshi-sanbai/zh/唐詩三百首.pdf`
- English references: `sources/tangshi-sanbai/en/Three Hundred Tang Poems.pdf`, `sources/tangshi-sanbai/en-wikisource-the-jade-mountain`, `sources/tangshi-sanbai/en-wikisource-export/The-Jade-Mountain-Wikisource.epub`
- Japanese context: `sources/tangshi-sanbai/ja-wikipedia-reference`
- Supplemental Chinese reference: `sources/tangshi-sanbai/du-fu/zh/杜甫诗选 POEMAS de DU FU.pdf`

Prepared files:

- Plan: `books/tangshi-sanbai/book-plan.json`
- Manifest: `books/tangshi-sanbai/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/tangshi-sanbai/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/tangshi-sanbai/markdown/wenyan.md`

Launch command:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  tangshi-sanbai zhjpbook-tangshi-100-low
```
