# Tangshi Sanbai Quadrilingual Task

Status: complete.

Prepared output:

- Book id: `tangshi-sanbai`
- Chapters: `320`
- Chunks: `647`
- Main spine: Wenyan `唐詩三百首`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Cover: `assets/covers/tangshi-sanbai/cover.png`
- Source order: root Wikisource anthology order, starting `賊退示官吏`

Completed run:

- Session: `zhjpbook-tangshi-100-low`
- Workers: `100`
- Model/reasoning: `gpt-5.5`, `low`
- Coverage: `647/647`, no missing chunks, no stale chunks
- Grammar analysis: generated and backfilled through the quadrilingual renderer
- Large-font PDF pages: `883`
- Layout check: rebuilt after making quadrilingual note blocks page-breakable; no `Overfull` or fatal entries remain in the checked TeX logs.

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

Built PDFs:

- `build/tangshi-sanbai/wenyan-main-quadrilingual/large-font/color/唐詩三百首（英文・現代日本語・現代中文注）・大字版.pdf`
- `build/tangshi-sanbai/wenyan-main-quadrilingual/large-font/blackwhite/唐詩三百首（英文・現代日本語・現代中文注・黑白）・大字版.pdf`

Working normal-font PDFs:

- `build/tangshi-sanbai/wenyan-main-quadrilingual/color/唐詩三百首（英文・現代日本語・現代中文注）.pdf`
- `build/tangshi-sanbai/wenyan-main-quadrilingual/blackwhite/唐詩三百首（英文・現代日本語・現代中文注・黑白）.pdf`
