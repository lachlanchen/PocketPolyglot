#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
source_pdf="sources/中国民间故事集成 四川卷 上 10978512.pdf"
markdown_dir="books/$book_id/markdown"
work_dir="books/$book_id/work/bilingual"
raw_markdown="$markdown_dir/zh.raw.md"
clean_markdown="$markdown_dir/zh.md"
pages="${OCR_PAGES:-79-804}"
ocr_dpi="${OCR_DPI:-220}"
ocr_workers="${OCR_WORKERS:-8}"
ocr_lang="${OCR_LANG:-chi_sim}"
ocr_psm="${OCR_PSM:-4}"
chunk_mode="${CHUNK_MODE:-paragraph}"
max_chars="${MAX_CHARS:-1400}"

mkdir -p "$markdown_dir" "$work_dir/chunks" "$work_dir/interlinear/chunks" "$work_dir/reviewed/chunks"

if [[ ! -f "$source_pdf" ]]; then
  echo "Missing source PDF: $source_pdf" >&2
  exit 1
fi

if [[ ! -s "$raw_markdown" || "${FORCE_OCR:-0}" == "1" ]]; then
  python scripts/ocr/pdf_to_markdown.py "$source_pdf" \
    --pages "$pages" \
    --output "$raw_markdown" \
    --lang "$ocr_lang" \
    --psm "$ocr_psm" \
    --dpi "$ocr_dpi" \
    --workers "$ocr_workers" \
    --crop \
    --threshold
fi

python scripts/books/normalize_sichuan_folk_markdown.py \
  --input "$raw_markdown" \
  --output "$clean_markdown" \
  --start-page 79

python scripts/interlinear/chunk_markdown_book.py "$clean_markdown" \
  --book-id "$book_id" \
  --book-title-zh "中国民间故事集成四川卷上" \
  --book-title-zh-reading "zhōng guó mín jiān gù shì jí chéng sì chuān juǎn shàng" \
  --book-title-ja "中国民間故事集成四川巻上" \
  --book-title-ja-reading "ちゅう ごく みん かん こ じ しゅう せい し せん かん じょう" \
  --author "钟敬文主编" \
  --book-description "中国民间故事集成 四川卷 上 / Sichuan volume one of the Chinese folk-story collection" \
  --requires-ocr-correction \
  --chunks-jsonl "$work_dir/chunks/chunks.jsonl" \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-mode "$chunk_mode" \
  --max-chars "$max_chars"

python scripts/interlinear/report_interlinear_progress.py \
  --manifest "$work_dir/chunks/manifest.json" \
  --chunk-dir "$work_dir/reviewed/chunks"
