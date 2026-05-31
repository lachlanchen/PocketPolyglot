#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/snow-country/work/bilingual/chunks/manifest.json"
chunk_dir="${SNOW_CHUNK_DIR:-books/snow-country/work/bilingual/reviewed/chunks}"
zh_json="books/snow-country/work/bilingual/preview/snow-country.partial.json"
jp_json="books/snow-country/work/bilingual/preview/snow-country.jp-main.partial.json"
build_root="${SNOW_BUILD_ROOT:-build/snow-country}"
cover_image="assets/covers/snow-country/snow-country-cover.png"

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir"

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "雪国" \
  --book-title-zh-reading "xuě guó" \
  --book-title-ja "雪国" \
  --book-title-ja-reading "ゆき ぐに" \
  --author "川端康成" \
  --author-reading "かわばた やすなり" \
  --source-markdown "books/snow-country/markdown/zh.md" \
  --source-epub "sources/snow-country/雪国.epub" \
  --source-markdown-ja "books/snow-country/markdown/ja.md" \
  --source-epub-ja "sources/snow-country/雪国(1).epub" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/color/雪国（ゆきぐに）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "雪国" \
  --book-title-zh-reading "xuě guó" \
  --book-title-ja "雪国" \
  --book-title-ja-reading "ゆき ぐに" \
  --author "川端康成" \
  --author-reading "かわばた やすなり" \
  --source-markdown "books/snow-country/markdown/zh.md" \
  --source-epub "sources/snow-country/雪国.epub" \
  --source-markdown-ja "books/snow-country/markdown/ja.md" \
  --source-epub-ja "sources/snow-country/雪国(1).epub" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/blackwhite/雪国（ゆきぐに）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "雪国" \
  --book-title-zh-reading "xuě guó" \
  --book-title-ja "雪国" \
  --book-title-ja-reading "ゆき ぐに" \
  --source-markdown "books/snow-country/markdown/zh.md" \
  --source-epub "sources/snow-country/雪国.epub" \
  --source-markdown-ja "books/snow-country/markdown/ja.md" \
  --source-epub-ja "sources/snow-country/雪国(1).epub" \
  --author "川端康成" \
  --author-reading "かわばた やすなり" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/color/雪国（中文注）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "雪国" \
  --book-title-zh-reading "xuě guó" \
  --book-title-ja "雪国" \
  --book-title-ja-reading "ゆき ぐに" \
  --source-markdown "books/snow-country/markdown/zh.md" \
  --source-epub "sources/snow-country/雪国.epub" \
  --source-markdown-ja "books/snow-country/markdown/ja.md" \
  --source-epub-ja "sources/snow-country/雪国(1).epub" \
  --author "川端康成" \
  --author-reading "かわばた やすなり" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/blackwhite/雪国（中文注）.pdf" \
  --allow-missing

if [[ "${COMMIT_PROGRESS:-1}" != "0" ]]; then
  bash scripts/interlinear/commit_snow_country_progress.sh
fi
