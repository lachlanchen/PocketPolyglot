#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="${1:-}"
if [[ -z "$book_id" ]]; then
  echo "Usage: scripts/interlinear/compile_prepared_book_both_previews.sh <book-id>" >&2
  exit 1
fi

plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

launchable="$(jq -r '.launchable' "$plan")"
if [[ "$launchable" != "true" ]]; then
  echo "Book is not launchable in the current zh-jp pipeline: $book_id" >&2
  exit 1
fi

source_path="$(jq -r '.source_path' "$plan")"
source_markdown="$(jq -r '.source_markdown' "$plan")"
chunk_dir="$(jq -r '.reviewed_chunk_dir' "$plan")"
title_zh="$(jq -r '.book_title_zh' "$plan")"
title_zh_reading="$(jq -r '.book_title_zh_reading' "$plan")"
title_ja="$(jq -r '.book_title_ja' "$plan")"
title_ja_reading="$(jq -r '.book_title_ja_reading' "$plan")"
author="$(jq -r '.author' "$plan")"
author_reading_zh="$(jq -r '.author_reading_zh' "$plan")"
author_reading_ja="$(jq -r '.author_reading_ja' "$plan")"
cover_image="${COVER_IMAGE:-}"
if [[ -z "$cover_image" && -f "assets/covers/$book_id/cover.png" ]]; then
  cover_image="assets/covers/$book_id/cover.png"
fi

if [[ ! -d "$chunk_dir" ]]; then
  echo "No reviewed chunk directory yet: $chunk_dir" >&2
  exit 0
fi

mkdir -p "build/$book_id/zh-main/color" "build/$book_id/zh-main/blackwhite" \
  "build/$book_id/jp-main/color" "build/$book_id/jp-main/blackwhite"

bash scripts/interlinear/compile_interlinear_book.sh \
  --chunk-dir "$chunk_dir" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --output-pdf "build/$book_id/zh-main/color/${title_zh}（日文注）.pdf" \
  --tex-output "build/$book_id/zh-main/color/${title_zh}（日文注）.tex" \
  --book-title "$title_zh" \
  --book-title-reading "$title_zh_reading" \
  --author "$author" \
  --author-reading "$author_reading_zh" \
  --curator "AgInTiFlow curated with https://flow.lazying.art powered by LazyingArt" \
  --cover-image "$cover_image" \
  --color

bash scripts/interlinear/compile_interlinear_book.sh \
  --chunk-dir "$chunk_dir" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --output-pdf "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.pdf" \
  --tex-output "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.tex" \
  --book-title "$title_zh" \
  --book-title-reading "$title_zh_reading" \
  --author "$author" \
  --author-reading "$author_reading_zh" \
  --curator "AgInTiFlow curated with https://flow.lazying.art powered by LazyingArt" \
  --cover-image "$cover_image"

bash scripts/interlinear/compile_jp_main_book.sh \
  --chunk-dir "$chunk_dir" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --output-pdf "build/$book_id/jp-main/color/${title_ja}（中文注）.pdf" \
  --tex-output "build/$book_id/jp-main/color/${title_ja}（中文注）.tex" \
  --book-title "$title_ja" \
  --book-title-reading "$title_ja_reading" \
  --author "$author" \
  --author-reading "$author_reading_ja" \
  --curator "AgInTiFlow curated with https://flow.lazying.art powered by LazyingArt" \
  --cover-image "$cover_image" \
  --color

bash scripts/interlinear/compile_jp_main_book.sh \
  --chunk-dir "$chunk_dir" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --output-pdf "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.pdf" \
  --tex-output "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.tex" \
  --book-title "$title_ja" \
  --book-title-reading "$title_ja_reading" \
  --author "$author" \
  --author-reading "$author_reading_ja" \
  --curator "AgInTiFlow curated with https://flow.lazying.art powered by LazyingArt" \
  --cover-image "$cover_image"

if [[ "${COMMIT_PROGRESS:-1}" == "1" ]]; then
  bash scripts/interlinear/commit_prepared_book_progress.sh "$book_id"
fi
