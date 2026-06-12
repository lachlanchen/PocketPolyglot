#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_trilingual_en_notes_book.sh --book-id <id> [--color-mode color|blackwhite]

Compile one trilingual edition with English as main text and indented Japanese
and Chinese notes under each English unit.
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
book_id=""
color_mode="color"
allow_missing=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="${2:-}"; shift 2 ;;
    --color-mode) color_mode="${2:-}"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$book_id" ]]; then
  usage >&2
  exit 1
fi
case "$color_mode" in color|blackwhite) ;; *) echo "Invalid --color-mode: $color_mode" >&2; exit 1 ;; esac

cd "$root"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
title_en="$(jq -r '.book_title_en' "$plan")"
author="$(jq -r '.author' "$plan")"
author_reading="$(jq -r '.author_reading_ja // empty' "$plan")"
curated_by="$(jq -r '.curated_by // "AgInTiFlow curated"' "$plan")"
curated_url="$(jq -r '.curated_url // "https://flow.lazying.art"' "$plan")"
powered_by="$(jq -r '.powered_by // "powered by LazyingArt"' "$plan")"

cover_image=""
if [[ -f "assets/covers/$book_id/cover.png" ]]; then
  cover_image="assets/covers/$book_id/cover.png"
elif [[ -f "assets/covers/$book_id/background.png" ]]; then
  cover_image="assets/covers/$book_id/background.png"
fi

build_dir="build/$book_id/en-main-jp-zh/$color_mode"
assembled_json="books/$book_id/work/trilingual/preview/$book_id.partial.json"
base_title="${title_en}（日文・中文注）"
if [[ "$color_mode" == "blackwhite" ]]; then
  base_title="${base_title%）}・黑白）"
fi
output_pdf="$build_dir/$base_title.pdf"

mkdir -p "$build_dir" "$(dirname "$assembled_json")"

assemble_args=(
  python scripts/interlinear/assemble_trilingual_json.py
  --manifest "$manifest"
  --chunks-jsonl "$chunks_jsonl"
  --chunk-dir "$chunk_dir"
  --output "$assembled_json"
)
if [[ "$allow_missing" -eq 1 ]]; then
  assemble_args+=(--allow-missing)
fi
"${assemble_args[@]}"
python scripts/interlinear/validate_trilingual_interlinear_json.py "$assembled_json"

python scripts/interlinear/json_to_trilingual_en_notes_tex.py "$assembled_json" \
  -o "$build_dir/source.tex" \
  --color-mode "$color_mode" \
  --author "$author" \
  --author-reading "$author_reading" \
  --curated-by "$curated_by" \
  --curated-url "$curated_url" \
  --powered-by "$powered_by" \
  --cover-image "$cover_image"

rm -f "$build_dir/book.aux" "$build_dir/book.out" "$build_dir/book.toc" "$build_dir/book.log"
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\TriAllSource{$build_dir/source.tex}\\input{tex/interlinear-trilingual-en-notes/book.tex}" \
  > "$build_dir/xelatex-pass1.log" 2>&1
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\TriAllSource{$build_dir/source.tex}\\input{tex/interlinear-trilingual-en-notes/book.tex}" \
  > "$build_dir/xelatex-pass2.log" 2>&1
cp "$build_dir/book.pdf" "$output_pdf"
rm -f "$build_dir/book.pdf"
cp "$build_dir/source.tex" "$build_dir/$base_title.tex"
echo "PDF: $output_pdf"
