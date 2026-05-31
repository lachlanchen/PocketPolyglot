#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
manifest="books/$book_id/work/bilingual/chunks/manifest.json"
chunk_dir="${SICHUAN_FOLK_CHUNK_DIR:-books/$book_id/work/bilingual/reviewed-v2/chunks}"
zh_json="books/$book_id/work/bilingual/preview/$book_id.partial.json"
jp_json="books/$book_id/work/bilingual/preview/$book_id.jp-main.partial.json"
build_root="${SICHUAN_FOLK_BUILD_ROOT:-build/$book_id}"
source_pdf="sources/中国民间故事集成 四川卷 上 10978512.pdf"
source_markdown="books/$book_id/markdown/zh.md"
cover_image="assets/covers/$book_id/sichuan-folk-stories-cover.png"

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir"

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "中国民间故事集成四川卷上" \
  --book-title-zh-reading "zhōng guó mín jiān gù shì jí chéng sì chuān juǎn shàng" \
  --book-title-ja "中国民間故事集成四川巻上" \
  --book-title-ja-reading "ちゅう ごく みん かん こ じ しゅう せい し せん かん じょう" \
  --author "钟敬文主编" \
  --author-reading "zhōng jìng wén zhǔ biān" \
  --source-markdown "$source_markdown" \
  --source-epub "$source_pdf" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/color/中国民间故事集成四川卷上（日文注）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$zh_json" \
  --book-title-zh "中国民间故事集成四川卷上" \
  --book-title-zh-reading "zhōng guó mín jiān gù shì jí chéng sì chuān juǎn shàng" \
  --book-title-ja "中国民間故事集成四川巻上" \
  --book-title-ja-reading "ちゅう ごく みん かん こ じ しゅう せい し せん かん じょう" \
  --author "钟敬文主编" \
  --author-reading "zhōng jìng wén zhǔ biān" \
  --source-markdown "$source_markdown" \
  --source-epub "$source_pdf" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/zh-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/zh-main/blackwhite/中国民间故事集成四川卷上（日文注）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "中国民间故事集成四川卷上" \
  --book-title-zh-reading "zhōng guó mín jiān gù shì jí chéng sì chuān juǎn shàng" \
  --book-title-ja "中国民間故事集成四川巻上" \
  --book-title-ja-reading "ちゅう ごく みん かん こ じ しゅう せい し せん かん じょう" \
  --source-markdown "$source_markdown" \
  --source-epub "$source_pdf" \
  --author "钟敬文主编" \
  --author-reading "しょう けい ぶん しゅ へん" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/color" \
  --color-mode color \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/color/中国民間故事集成四川巻上（中文注）.pdf" \
  --allow-missing

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "$jp_json" \
  --book-title-zh "中国民间故事集成四川卷上" \
  --book-title-zh-reading "zhōng guó mín jiān gù shì jí chéng sì chuān juǎn shàng" \
  --book-title-ja "中国民間故事集成四川巻上" \
  --book-title-ja-reading "ちゅう ごく みん かん こ じ しゅう せい し せん かん じょう" \
  --source-markdown "$source_markdown" \
  --source-epub "$source_pdf" \
  --author "钟敬文主编" \
  --author-reading "しょう けい ぶん しゅ へん" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "$build_root/jp-main/blackwhite" \
  --color-mode blackwhite \
  --secondary-ja-mode merge \
  --output-pdf "$build_root/jp-main/blackwhite/中国民間故事集成四川巻上（中文注）.pdf" \
  --allow-missing

if [[ "${COMMIT_PROGRESS:-1}" != "0" ]]; then
  bash scripts/interlinear/commit_sichuan_folk_progress.sh
fi
