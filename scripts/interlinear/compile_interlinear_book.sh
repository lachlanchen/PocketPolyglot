#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_interlinear_book.sh [options]

Assemble chunk JSON, validate it, compile the interlinear PDF, and copy the PDF
to a stable book-name output path.

Options:
  --manifest <path>              chunk manifest
  --chunk-dir <path>             directory containing chunk JSON files
  --output-json <path>           assembled interlinear JSON
  --book-title-zh <text>         Chinese book title
  --book-title-zh-reading <pin>  Chinese title pinyin
  --book-title-ja <text>         Japanese title
  --book-title-ja-reading <txt>  Japanese title reading
  --source-markdown <path>       Chinese source Markdown
  --source-epub <path>           Chinese source EPUB
  --source-markdown-ja <path>    Japanese source Markdown
  --source-epub-ja <path>        Japanese source EPUB
  --output-pdf <path>            named PDF path
  --allow-missing                build from available chunks only
  -h, --help                     show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest=""
chunk_dir=""
output_json=""
book_title_zh="心"
book_title_zh_reading="xīn"
book_title_ja="こころ"
book_title_ja_reading="こころ"
source_markdown=""
source_epub=""
source_markdown_ja=""
source_epub_ja=""
output_pdf=""
allow_missing=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) manifest="${2:-}"; shift 2 ;;
    --chunk-dir) chunk_dir="${2:-}"; shift 2 ;;
    --output-json) output_json="${2:-}"; shift 2 ;;
    --book-title-zh) book_title_zh="${2:-}"; shift 2 ;;
    --book-title-zh-reading) book_title_zh_reading="${2:-}"; shift 2 ;;
    --book-title-ja) book_title_ja="${2:-}"; shift 2 ;;
    --book-title-ja-reading) book_title_ja_reading="${2:-}"; shift 2 ;;
    --source-markdown) source_markdown="${2:-}"; shift 2 ;;
    --source-epub) source_epub="${2:-}"; shift 2 ;;
    --source-markdown-ja) source_markdown_ja="${2:-}"; shift 2 ;;
    --source-epub-ja) source_epub_ja="${2:-}"; shift 2 ;;
    --output-pdf) output_pdf="${2:-}"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

for required in manifest chunk_dir output_json source_markdown source_epub output_pdf; do
  if [[ -z "${!required}" ]]; then
    echo "Missing --${required//_/-}" >&2
    usage >&2
    exit 1
  fi
done

cd "$root"

assemble_cmd=(
  python scripts/interlinear/assemble_chunk_json.py
  --manifest "$manifest"
  --chunk-dir "$chunk_dir"
  --output "$output_json"
  --book-title-zh "$book_title_zh"
  --book-title-zh-reading "$book_title_zh_reading"
  --book-title-ja "$book_title_ja"
  --book-title-ja-reading "$book_title_ja_reading"
  --source-markdown "$source_markdown"
  --source-epub "$source_epub"
)

if [[ -n "$source_markdown_ja" ]]; then
  assemble_cmd+=(--source-markdown-ja "$source_markdown_ja")
fi
if [[ -n "$source_epub_ja" ]]; then
  assemble_cmd+=(--source-epub-ja "$source_epub_ja")
fi
if [[ "$allow_missing" -eq 1 ]]; then
  assemble_cmd+=(--allow-missing)
fi

"${assemble_cmd[@]}"
python scripts/interlinear/validate_interlinear_json.py "$output_json"
make interlinear INTERLINEAR_DATA="$output_json"

mkdir -p "$(dirname "$output_pdf")"
cp build/interlinear-block/book.pdf "$output_pdf"
echo "PDF: $output_pdf"
