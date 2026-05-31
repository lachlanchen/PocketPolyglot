# Repository Guidelines

## Project Structure & Module Organization

This repository builds pocket-size Chinese/Japanese paired and interlinear books with XeLaTeX. TeX templates live in `tex/`: `paired/`, `interlinear-block/`, `interlinear-run/`, and `interlinear-jp-main/`. Python tooling lives in `scripts/`, grouped by workflow: `books/` for EPUB/Markdown extraction, `ocr/` for scanned PDF OCR, `paired/` for simple paired Markdown, and `interlinear/` for JSON chunking, validation, rendering, and Codex-assisted generation. Source data is in `data/`, reviewed Markdown is in `books/*/markdown/` and `ocr/`, and tracked visual assets are in `assets/`. Large local inputs in `sources/`, build outputs in `build/`, and long-running scratch data in `books/*/work/` are ignored.

## Build, Test, and Development Commands

Use `make sample` to build the paired demo at `build/paired/book.pdf`. Use `make interlinear`, `make interlinear-run`, or `make interlinear-jp-main` for the three interlinear layouts. Use `make compare` to build all interlinear layouts from `INTERLINEAR_DATA` (default `data/interlinear/sample.json`). Convert Kokoro sources with `make kokoro-bilingual-md`, and start the long bilingual tmux pipeline with `make kokoro-bilingual-tmux`. Check generated Kokoro progress with:

```sh
python scripts/interlinear/report_interlinear_progress.py \
  --manifest books/kokoro/work/bilingual/chunks/manifest.json \
  --chunk-dir books/kokoro/work/bilingual/interlinear/chunks
```

## Coding Style & Naming Conventions

Python scripts use 4-space indentation, `argparse` CLIs, `pathlib.Path`, UTF-8 text IO, and `snake_case` names. Keep scripts executable when they are intended as commands. TeX macros use descriptive PascalCase-style names such as `\InterUnit` and `\JpMainUnit`. JSON token fields are short and stable: `t` for text, `r` for reading, and optional `g` for the English grammar-component role (`subject`, `predicate`, `object`, `attributive`, `adverbial`, `complement`, `topic`, or `function`).

## Testing Guidelines

There is no formal test suite. Validate Python edits with `python -m py_compile ...`. Validate interlinear JSON with `python scripts/interlinear/validate_interlinear_json.py <json>`. For layout changes, compile the relevant `make` target and inspect the generated PDF. For Kokoro chunks, progress must report no stale chunks before trusting a preview.

## Commit & Pull Request Guidelines

Commit messages are short imperative summaries, e.g. `Reject stale chunks in interlinear previews` or `Update Kokoro interlinear progress kokoro-chunk-0014`. Commit tracked script/TeX/data changes after each meaningful edit. Generated Kokoro chunks should be synced through `scripts/interlinear/commit_kokoro_progress.sh`, which tracks valid current-manifest chunks under `data/interlinear/kokoro/`. Pull requests should describe the workflow touched, list verification commands, and include PDF paths or screenshots when layout changes are visible.

## Agent-Specific Instructions

Do not commit original PDFs or EPUBs from `sources/`. Do not trust partial PDF page counts unless progress confirms current-manifest coverage. For paired-language books, compile both reading directions at each checkpoint whenever renderers exist, e.g. ZH-main/JP-comment and JP-main/ZH-comment. Compile book PDFs with a table of contents whenever the renderer supports one; if a new renderer omits TOC support, treat that as required pipeline work before calling the book complete. If a new pair such as EN-JP lacks a reverse renderer, treat the reverse compile path as required pipeline work before calling the book complete. For long-running generation, keep tmux sessions observable and prefer resumable scripts in `prompt_tools/` or `scripts/interlinear/`.
