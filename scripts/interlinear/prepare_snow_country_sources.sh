#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="snow-country"
book_dir="books/$book_id"
markdown_dir="$book_dir/markdown"
work_dir="$book_dir/work/bilingual"

zh_epub="sources/snow-country/雪国.epub"
ja_epub="sources/snow-country/雪国(1).epub"

for required in "$zh_epub" "$ja_epub"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing source EPUB: $required" >&2
    exit 1
  fi
done

mkdir -p "$markdown_dir" "$work_dir/chunks" "$work_dir/interlinear/chunks"

python scripts/books/epub_to_markdown.py "$zh_epub" \
  --raw-output "$markdown_dir/zh.raw.md" \
  --clean-output "$markdown_dir/zh.clean.md"

python scripts/books/epub_to_markdown.py "$ja_epub" \
  --raw-output "$markdown_dir/ja.raw.md" \
  --clean-output "$markdown_dir/ja.clean.md"

python scripts/books/normalize_snow_country_markdown.py \
  --zh-clean "$markdown_dir/zh.clean.md" \
  --ja-clean "$markdown_dir/ja.clean.md" \
  --zh-output "$markdown_dir/zh.md" \
  --ja-output "$markdown_dir/ja.md"

python scripts/interlinear/chunk_bilingual_markdown_book.py \
  --zh-markdown "$markdown_dir/zh.md" \
  --ja-markdown "$markdown_dir/ja.md" \
  --book-id "$book_id" \
  --book-title-zh "雪国" \
  --book-title-zh-reading "xuě guó" \
  --book-title-ja "雪国" \
  --book-title-ja-reading "ゆき ぐに" \
  --author "川端康成" \
  --book-description "川端康成《雪国》 / Kawabata Yasunari's Snow Country" \
  --chunks-jsonl "$work_dir/chunks/chunks.jsonl" \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-mode paragraph \
  --reference-scope chapter

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-dir "$work_dir/interlinear/chunks"
