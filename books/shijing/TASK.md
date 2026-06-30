# Shijing Quadrilingual Task

Status: complete.

Prepared output:

- Book id: `shijing`
- Chapters: `300`
- Chunks: `949`
- Main spine: Wenyan `詩經`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Cover: `assets/covers/shijing/cover.png`
- Source order: root Wikisource anthology order, starting `關雎`

Completed run:

- Session: `zhjpbook-shijing-100-low`
- Workers: `100`
- Model/reasoning: `gpt-5.5`, `low`
- Coverage: `949/949`, no missing chunks, no stale chunks
- Grammar analysis: generated and backfilled through the quadrilingual renderer
- Large-font PDF pages: `740`

Source layout:

- Wenyan spine: `sources/shijing/zh-wikisource`
- Wenyan export: `sources/shijing/zh-wikisource-export/詩經-Wikisource.epub`
- Chinese references: `sources/shijing/zh/詩經.pdf`, `sources/shijing/诗经选.epub`, `sources/shijing/詩經注析（全二冊） 上册.pdf`, `sources/shijing/詩經注析（全二冊） 下册.pdf`
- Classical commentary: `sources/shijing/毛詩注疏.pdf`
- English references: `sources/shijing/en/The Book of Songs - The Ancient Chinese Classic of Poetry.pdf`, `sources/shijing/en-wikisource-classic-of-poetry`, `sources/shijing/en-wikisource-export/Classic-of-Poetry-Wikisource.epub`
- Japanese references: `sources/shijing/ja-wikisource-shikyo`, `sources/shijing/ja-wikisource-export/詩経-Wikisource.epub`, `sources/shijing/jp/詩経 - 歌の原始 書物誕生.pdf`

Prepared files:

- Plan: `books/shijing/book-plan.json`
- Manifest: `books/shijing/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/shijing/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/shijing/markdown/wenyan.md`

Launch command:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  shijing zhjpbook-shijing-100-low
```

Built PDFs:

- `build/shijing/wenyan-main-quadrilingual/large-font/color/詩經（英文・現代日本語・現代中文注）・大字版.pdf`
- `build/shijing/wenyan-main-quadrilingual/large-font/blackwhite/詩經（英文・現代日本語・現代中文注・黑白）・大字版.pdf`

Working normal-font PDFs:

- `build/shijing/wenyan-main-quadrilingual/color/詩經（英文・現代日本語・現代中文注）.pdf`
- `build/shijing/wenyan-main-quadrilingual/blackwhite/詩經（英文・現代日本語・現代中文注・黑白）.pdf`
