#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/kokoro/work/bilingual/chunks/manifest.json"
chunk_dir="books/kokoro/work/bilingual/interlinear/chunks"
zh_json="books/kokoro/work/bilingual/preview/kokoro.partial.json"
jp_json="books/kokoro/work/bilingual/preview/kokoro.jp-main.partial.json"

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir"

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "心" \
  --book-title-zh-reading "xīn" \
  --book-title-ja "こころ" \
  --book-title-ja-reading "こころ" \
  --source-markdown "books/kokoro/markdown/zh.md" \
  --source-epub "sources/心.epub" \
  --source-markdown-ja "books/kokoro/markdown/ja.md" \
  --source-epub-ja "sources/夏目 漱石 作品全集.epub" \
  --output-pdf "build/interlinear-block/心（こころ）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "心" \
  --book-title-zh-reading "xīn" \
  --book-title-ja "こころ" \
  --book-title-ja-reading "こころ" \
  --source-markdown "books/kokoro/markdown/zh.md" \
  --source-epub "sources/心.epub" \
  --source-markdown-ja "books/kokoro/markdown/ja.md" \
  --source-epub-ja "sources/夏目 漱石 作品全集.epub" \
  --author "夏目漱石" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "assets/covers/kokoro-jp-main/kokoro-cover.jpeg" \
  --output-pdf "build/interlinear-jp-main/こころ（心）.pdf" \
  --allow-missing
