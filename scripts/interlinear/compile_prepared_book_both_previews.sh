#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="${1:-}"
if [[ -z "$book_id" ]]; then
  echo "Usage: scripts/interlinear/compile_prepared_book_both_previews.sh <book-id>" >&2
  exit 1
fi

lock_dir="books/$book_id/work/bilingual/preview"
mkdir -p "$lock_dir"
lock_file="$lock_dir/compile.lock"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "Preview compile already running for $book_id; skipping duplicate launch."
  exit 0
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
manifest="$(jq -r '.chunks_manifest' "$plan")"
chunk_dir="$(jq -r '.reviewed_chunk_dir' "$plan")"
title_zh="$(jq -r '.book_title_zh' "$plan")"
title_zh_reading="$(jq -r '.book_title_zh_reading' "$plan")"
title_ja="$(jq -r '.book_title_ja' "$plan")"
title_ja_reading="$(jq -r '.book_title_ja_reading' "$plan")"
author="$(jq -r '.author' "$plan")"
author_reading_zh="$(jq -r '.author_reading_zh' "$plan")"
author_reading_ja="$(jq -r '.author_reading_ja' "$plan")"
render_secondary_ja="$(jq -r '.render_secondary_ja // true' "$plan")"
secondary_ja_mode="$(jq -r '.secondary_ja_mode // empty' "$plan")"
drop_editorial_notes="$(jq -r '.drop_editorial_notes // false' "$plan")"
mapfile -t render_section_titles_zh < <(jq -r '.render_section_titles_zh[]? // empty' "$plan")
cover_image="${COVER_IMAGE:-}"
if [[ -z "$cover_image" && -f "assets/covers/$book_id/cover.png" ]]; then
  cover_image="assets/covers/$book_id/cover.png"
fi

if [[ ! -d "$chunk_dir" ]]; then
  echo "No reviewed chunk directory yet: $chunk_dir" >&2
  exit 0
fi

mkdir -p "build/$book_id/zh-main/color" "build/$book_id/zh-main/blackwhite" \
  "build/$book_id/jp-main/color" "build/$book_id/jp-main/blackwhite" \
  "$lock_dir"
if [[ -z "$secondary_ja_mode" ]]; then
  if [[ "$render_secondary_ja" == "false" ]]; then
    secondary_ja_mode="hide"
  else
    secondary_ja_mode="auto"
  fi
fi
secondary_ja_args=(--secondary-ja-mode "$secondary_ja_mode")
render_filter_args=()
for title in "${render_section_titles_zh[@]}"; do
  if [[ -n "$title" ]]; then
    render_filter_args+=(--include-section-title-zh "$title")
  fi
done
if [[ "$drop_editorial_notes" == "true" ]]; then
  render_filter_args+=(--drop-editorial-notes)
fi

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "books/$book_id/work/bilingual/preview/$book_id.partial.json" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --output-pdf "build/$book_id/zh-main/color/${title_zh}（日文注）.pdf" \
  --author "$author" \
  --author-reading "$author_reading_zh" \
  --cover-image "$cover_image" \
  --build-dir "build/$book_id/zh-main/color" \
  --color-mode color \
  "${secondary_ja_args[@]}" \
  "${render_filter_args[@]}" \
  --allow-missing
cp "build/$book_id/zh-main/color/source.tex" "build/$book_id/zh-main/color/${title_zh}（日文注）.tex"

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "books/$book_id/work/bilingual/preview/$book_id.partial.json" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --output-pdf "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.pdf" \
  --author "$author" \
  --author-reading "$author_reading_zh" \
  --cover-image "$cover_image" \
  --build-dir "build/$book_id/zh-main/blackwhite" \
  --color-mode blackwhite \
  "${secondary_ja_args[@]}" \
  "${render_filter_args[@]}" \
  --allow-missing
cp "build/$book_id/zh-main/blackwhite/source.tex" "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.tex"

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "books/$book_id/work/bilingual/preview/$book_id.jp-main.partial.json" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --output-pdf "build/$book_id/jp-main/color/${title_ja}（中文注）.pdf" \
  --author "$author" \
  --author-reading "$author_reading_ja" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "build/$book_id/jp-main/color" \
  --color-mode color \
  "${secondary_ja_args[@]}" \
  "${render_filter_args[@]}" \
  --allow-missing
cp "build/$book_id/jp-main/color/source.tex" "build/$book_id/jp-main/color/${title_ja}（中文注）.tex"

bash scripts/interlinear/compile_jp_main_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-json "books/$book_id/work/bilingual/preview/$book_id.jp-main.partial.json" \
  --source-epub "$source_path" \
  --source-markdown "$source_markdown" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --output-pdf "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.pdf" \
  --author "$author" \
  --author-reading "$author_reading_ja" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
  --cover-image "$cover_image" \
  --build-dir "build/$book_id/jp-main/blackwhite" \
  --color-mode blackwhite \
  "${secondary_ja_args[@]}" \
  "${render_filter_args[@]}" \
  --allow-missing
cp "build/$book_id/jp-main/blackwhite/source.tex" "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.tex"

if [[ "${COMMIT_PROGRESS:-1}" == "1" ]]; then
  bash scripts/interlinear/commit_prepared_book_progress.sh "$book_id"
fi
