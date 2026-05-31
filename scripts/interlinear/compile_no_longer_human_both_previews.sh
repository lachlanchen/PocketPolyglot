#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/no-longer-human/work/bilingual/chunks/manifest.json"
chunk_dir="${NO_LONGER_HUMAN_CHUNK_DIR:-books/no-longer-human/work/bilingual/reviewed/chunks}"
zh_json="books/no-longer-human/work/bilingual/preview/no-longer-human.partial.json"
jp_json="books/no-longer-human/work/bilingual/preview/no-longer-human.jp-main.partial.json"
build_root="${NO_LONGER_HUMAN_BUILD_ROOT:-build/no-longer-human}"
cover_image="assets/covers/no-longer-human/no-longer-human-cover.png"

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir"

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "人間失格" \
  --book-title-zh-reading "rén jiān shī gé" \
  --book-title-ja "人間失格" \
  --book-title-ja-reading "にん げん しっ かく" \
  --author "太宰治" \
  --author-reading "だざい おさむ" \
  --source-markdown "books/no-longer-human/markdown/zh.md" \
  --source-epub "sources/no-longer-human/人間失格-2.pdf" \
  --source-markdown-ja "books/no-longer-human/markdown/ja.md" \
  --source-epub-ja "sources/no-longer-human/人間失格.pdf" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --merge-continuation-units \
  --output-pdf "$build_root/zh-main/color/人間失格（にんげんしっかく）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "人間失格" \
  --book-title-zh-reading "rén jiān shī gé" \
  --book-title-ja "人間失格" \
  --book-title-ja-reading "にん げん しっ かく" \
  --author "太宰治" \
  --author-reading "だざい おさむ" \
  --source-markdown "books/no-longer-human/markdown/zh.md" \
  --source-epub "sources/no-longer-human/人間失格-2.pdf" \
  --source-markdown-ja "books/no-longer-human/markdown/ja.md" \
  --source-epub-ja "sources/no-longer-human/人間失格.pdf" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --merge-continuation-units \
  --output-pdf "$build_root/zh-main/blackwhite/人間失格（にんげんしっかく）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "人間失格" \
  --book-title-zh-reading "rén jiān shī gé" \
  --book-title-ja "人間失格" \
  --book-title-ja-reading "にん げん しっ かく" \
  --source-markdown "books/no-longer-human/markdown/zh.md" \
  --source-epub "sources/no-longer-human/人間失格-2.pdf" \
  --source-markdown-ja "books/no-longer-human/markdown/ja.md" \
  --source-epub-ja "sources/no-longer-human/人間失格.pdf" \
  --author "太宰治" \
  --author-reading "だざい おさむ" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/color/人間失格（中文注）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "人間失格" \
  --book-title-zh-reading "rén jiān shī gé" \
  --book-title-ja "人間失格" \
  --book-title-ja-reading "にん げん しっ かく" \
  --source-markdown "books/no-longer-human/markdown/zh.md" \
  --source-epub "sources/no-longer-human/人間失格-2.pdf" \
  --source-markdown-ja "books/no-longer-human/markdown/ja.md" \
  --source-epub-ja "sources/no-longer-human/人間失格.pdf" \
  --author "太宰治" \
  --author-reading "だざい おさむ" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/blackwhite/人間失格（中文注）.pdf" \
  --allow-missing

if [[ "${COMMIT_PROGRESS:-1}" != "0" ]]; then
  bash scripts/interlinear/commit_no_longer_human_progress.sh
fi
