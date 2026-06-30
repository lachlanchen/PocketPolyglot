# Shanhaijing Quadrilingual Task

Status: prepared only. Do not start automatically.

Prepared output:

- Book id: `shanhaijing`
- Chapters: `19`
- Chunks: `879`
- Main spine: Wenyan `山海經`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Cover: `assets/covers/shanhaijing/cover.png`
- Source order: canonical `山海經` order, starting `郭璞序`, then `南山經`

Source sufficiency:

- Enough material exists for a full quadrilingual task.
- Wenyan spine is backed by Chinese Wikisource and a Gutenberg alternate text.
- Modern Chinese is backed by a local Chinese edition/reference PDF.
- English is backed by `The Classic of Mountains and Seas.pdf`.
- No full aligned Japanese translation source is present; generate clear modern Japanese from the wenyan, modern Chinese, and English references.

Source layout:

- Wenyan spine: `sources/shanhaijing/zh/wenyan-wikisource`
- Alternate wenyan: `sources/shanhaijing/zh/wenyan-gutenberg`
- Wenyan export: `sources/shanhaijing/zh/wenyan-wikisource-export`
- Modern Chinese reference: `sources/shanhaijing/zh/chinese-edition/山海经.pdf`
- English reference: `sources/shanhaijing/en/english-translation/The Classic of Mountains and Seas.pdf`

Prepared files:

- Plan: `books/shanhaijing/book-plan.json`
- Manifest: `books/shanhaijing/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/shanhaijing/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/shanhaijing/markdown/wenyan.md`

Launch command:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  shanhaijing zhjpbook-shanhaijing-100-low
```
