#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="no-longer-human"
book_dir="books/$book_id"
markdown_dir="$book_dir/markdown"
work_dir="$book_dir/work/bilingual"

ja_pdf="sources/no-longer-human/人間失格.pdf"
zh_pdf="sources/no-longer-human/人間失格-2.pdf"

for required in "$ja_pdf" "$zh_pdf"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing source PDF: $required" >&2
    exit 1
  fi
done

mkdir -p "$markdown_dir" "$work_dir/chunks" "$work_dir/interlinear/chunks" "$work_dir/reviewed/chunks"

python scripts/books/normalize_no_longer_human_markdown.py \
  --zh-pdf "$zh_pdf" \
  --ja-pdf "$ja_pdf" \
  --output-dir "$markdown_dir"

python scripts/interlinear/chunk_bilingual_markdown_book.py \
  --zh-markdown "$markdown_dir/zh.md" \
  --ja-markdown "$markdown_dir/ja.md" \
  --book-id "$book_id" \
  --book-title-zh "人間失格" \
  --book-title-zh-reading "rén jiān shī gé" \
  --book-title-ja "人間失格" \
  --book-title-ja-reading "にん げん しっ かく" \
  --author "太宰治" \
  --book-description "太宰治《人間失格》 / Dazai Osamu's No Longer Human" \
  --chunks-jsonl "$work_dir/chunks/chunks.jsonl" \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-mode paragraph \
  --reference-scope chapter

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-dir "$work_dir/reviewed/chunks"
