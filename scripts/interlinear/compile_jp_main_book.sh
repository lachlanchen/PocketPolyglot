#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_jp_main_book.sh [options]

Assemble chunk JSON, validate it, compile a Japanese-main / Chinese-comment
PDF, and copy the PDF to a stable book-name output path.

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
  --author <text>                author name for title/metadata
  --author-reading <txt>         author ruby reading, split by spaces
  --curated-by <text>            curator line
  --curated-url <url>            curator URL
  --powered-by <text>            powered-by line
  --cover-image <path>           workspace-relative cover image path
  --build-dir <path>             TeX/PDF build directory
  --color-mode <mode>            color or blackwhite
  --output-pdf <path>            named PDF path
  --allow-missing                build from available chunks only
  --hide-secondary-ja            do not render ja[1] explanatory/comment lines
  --secondary-ja-mode <mode>     auto, comment, hide, or merge ja[1+] into Japanese text
  --include-section-title-zh <t> keep only a Chinese section title after assembly
  --drop-editorial-notes         drop note-only paragraphs such as [1]... footnotes
  -h, --help                     show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest=""
chunk_dir=""
output_json=""
build_dir="build/interlinear-jp-main"
color_mode="color"
book_title_zh="心"
book_title_zh_reading="xīn"
book_title_ja="こころ"
book_title_ja_reading="こころ"
source_markdown=""
source_epub=""
source_markdown_ja=""
source_epub_ja=""
author="夏目漱石"
author_reading=""
curated_by="AgInTiFlow curated"
curated_url="https://flow.lazying.art"
powered_by="powered by LazyingArt"
cover_image=""
output_pdf=""
allow_missing=0
hide_secondary_ja=0
secondary_ja_mode="auto"
include_section_title_zh=()
drop_editorial_notes=0

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
    --author) author="${2:-}"; shift 2 ;;
    --author-reading) author_reading="${2:-}"; shift 2 ;;
    --curated-by) curated_by="${2:-}"; shift 2 ;;
    --curated-url) curated_url="${2:-}"; shift 2 ;;
    --powered-by) powered_by="${2:-}"; shift 2 ;;
    --cover-image) cover_image="${2:-}"; shift 2 ;;
    --build-dir) build_dir="${2:-}"; shift 2 ;;
    --color-mode) color_mode="${2:-}"; shift 2 ;;
    --output-pdf) output_pdf="${2:-}"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    --hide-secondary-ja) hide_secondary_ja=1; shift ;;
    --secondary-ja-mode) secondary_ja_mode="${2:-}"; shift 2 ;;
    --include-section-title-zh) include_section_title_zh+=("${2:-}"); shift 2 ;;
    --drop-editorial-notes) drop_editorial_notes=1; shift ;;
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

case "$color_mode" in
  color|blackwhite) ;;
  *) echo "Invalid --color-mode: $color_mode" >&2; exit 1 ;;
esac
case "$secondary_ja_mode" in
  auto|comment|hide|merge) ;;
  *) echo "Invalid --secondary-ja-mode: $secondary_ja_mode" >&2; exit 1 ;;
esac

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
render_args=()
if [[ "$hide_secondary_ja" -eq 1 ]]; then
  secondary_ja_mode="hide"
fi
render_args+=(--secondary-ja-mode "$secondary_ja_mode")

"${assemble_cmd[@]}"
filter_args=()
for title in "${include_section_title_zh[@]}"; do
  if [[ -n "$title" ]]; then
    filter_args+=(--include-section-title-zh "$title")
  fi
done
if [[ "$drop_editorial_notes" -eq 1 ]]; then
  filter_args+=(--drop-editorial-notes)
fi
if [[ "${#filter_args[@]}" -gt 0 ]]; then
  python scripts/interlinear/filter_interlinear_json.py "$output_json" -o "$output_json" "${filter_args[@]}"
fi
python scripts/interlinear/validate_interlinear_json.py "$output_json"

if [[ "$color_mode" == "blackwhite" ]]; then
  cover_image=""
fi

mkdir -p "$build_dir"
python scripts/interlinear/json_to_jp_main_tex.py "$output_json" \
  -o "$build_dir/source.tex" \
  --author "$author" \
  --author-reading "$author_reading" \
  --curated-by "$curated_by" \
  --curated-url "$curated_url" \
  --powered-by "$powered_by" \
  --cover-image "$cover_image" \
  --color-mode "$color_mode" \
  "${render_args[@]}"
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\JpMainSource{$build_dir/source.tex}\\input{tex/interlinear-jp-main/book.tex}"
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\JpMainSource{$build_dir/source.tex}\\input{tex/interlinear-jp-main/book.tex}"
mkdir -p "$(dirname "$output_pdf")"
cp "$build_dir/book.pdf" "$output_pdf"
if [[ "$output_pdf" != "$build_dir/book.pdf" ]]; then
  rm -f "$build_dir/book.pdf"
fi
echo "PDF: $output_pdf"
