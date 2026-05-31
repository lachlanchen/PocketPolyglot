#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/kokoro/work/bilingual/chunks/manifest.json"
chunk_dir="books/kokoro/work/bilingual/interlinear/chunks"
zh_json="books/kokoro/work/bilingual/preview/kokoro.partial.json"
jp_json="books/kokoro/work/bilingual/preview/kokoro.jp-main.partial.json"
build_root="${KOKORO_BUILD_ROOT:-build/kokoro}"
cover_image="assets/covers/kokoro-jp-main/kokoro-cover.jpeg"

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
  --author "夏目漱石" \
  --author-reading "なつめ そうせき" \
  --source-markdown "books/kokoro/markdown/zh.md" \
  --source-epub "sources/心.epub" \
  --source-markdown-ja "books/kokoro/markdown/ja.md" \
  --source-epub-ja "sources/夏目 漱石 作品全集.epub" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/color/心（こころ）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "心" \
  --book-title-zh-reading "xīn" \
  --book-title-ja "こころ" \
  --book-title-ja-reading "こころ" \
  --author "夏目漱石" \
  --author-reading "なつめ そうせき" \
  --source-markdown "books/kokoro/markdown/zh.md" \
  --source-epub "sources/心.epub" \
  --source-markdown-ja "books/kokoro/markdown/ja.md" \
  --source-epub-ja "sources/夏目 漱石 作品全集.epub" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/blackwhite/心（こころ）.pdf" \
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
  --author-reading "なつめ そうせき" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/color/こころ（心）.pdf" \
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
  --author-reading "なつめ そうせき" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/blackwhite/こころ（心）.pdf" \
  --allow-missing

if [[ "${COMMIT_PROGRESS:-1}" != "0" ]]; then
  bash scripts/interlinear/commit_kokoro_progress.sh
fi
