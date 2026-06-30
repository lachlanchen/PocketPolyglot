# Chuci Quadrilingual Task

Status: prepared only. Do not start automatically.

Prepared output:

- Book id: `chuci`
- Chapters: `17`
- Chunks: `178`
- Main spine: Wenyan `楚辭`
- Secondary layers: English, modern Japanese, modern Chinese
- Grammar analysis: required, normalized English role labels
- Font profile: large LinguaLeaf pocket font profile
- Source order: received anthology order, starting `離騷`

Source layout:

- Wenyan spine: `sources/chuci/zh-wikisource`
- Wenyan export: `sources/chuci/zh-wikisource-export/楚辭-Wikisource.epub`
- Chinese references: `sources/chuci/zh/楚辭.pdf`, `sources/chuci/楚辞补注.pdf`, `sources/chuci/楚辞集解.pdf`
- English reference: `sources/chuci/en/The Songs of Chu - Qu Yuan and Others.pdf`
- English context: `sources/chuci/en-wikipedia-reference`
- Japanese context: `sources/chuci/ja-wikipedia-reference`

Prepared files:

- Plan: `books/chuci/book-plan.json`
- Manifest: `books/chuci/work/quadrilingual/chunks/manifest.json`
- Chunks: `books/chuci/work/quadrilingual/chunks/chunks.jsonl`
- Wenyan Markdown: `books/chuci/markdown/wenyan.md`

Launch command:

```bash
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
CLAIM_TTL_SECONDS=1800 CODEX_TIMEOUT_SECONDS=1200 \
CODEX_EXEC_IGNORE_USER_CONFIG=1 CODEX_EXEC_IGNORE_RULES=1 \
MAIN_LAYERS=wenyan \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  chuci zhjpbook-chuci-100-low
```
