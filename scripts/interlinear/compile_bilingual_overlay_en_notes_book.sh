#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_bilingual_overlay_en_notes_book.sh --book-id <id> [--color-mode color|blackwhite] [--allow-missing]

Compile an English-main trilingual edition from an older bilingual JP/ZH
book plus incremental English overlay chunks.
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

build_dir="build/$book_id/en-main-jp-zh/$color_mode"
assembled_json="books/$book_id/work/incremental/en-modern-ja/preview/$book_id.trilingual-overlay.json"
mkdir -p "$build_dir" "$(dirname "$assembled_json")"

assemble_args=(
  python scripts/interlinear/assemble_bilingual_overlay_trilingual_json.py
  --book-id "$book_id"
  --output "$assembled_json"
)
if [[ "$allow_missing" -eq 1 ]]; then
  assemble_args+=(--allow-missing)
fi
"${assemble_args[@]}"

title_en="$(jq -r '.title.en | map(.t) | join("")' "$assembled_json")"
author="$(jq -r '.author.name // ""' "$assembled_json")"
author_reading="$(jq -r '.author.reading_ja // ""' "$assembled_json")"
safe_title="${title_en//\//／}"
base_title="${safe_title}（日文・中文注）"
if [[ "$color_mode" == "blackwhite" ]]; then
  base_title="${base_title%）}・黑白）"
fi

cover_image=""
for candidate in \
  "assets/covers/$book_id/cover.png" \
  "assets/covers/$book_id/background.png" \
  "assets/covers/$book_id/${book_id}-cover.png" \
  "assets/covers/$book_id/${book_id}-cover.jpeg" \
  "assets/covers/$book_id/${book_id}-cover.jpg" \
  "assets/covers/${book_id}-jp-main/kokoro-cover.jpeg"
do
  if [[ -f "$candidate" ]]; then
    cover_image="$candidate"
    break
  fi
done

output_pdf="$build_dir/$base_title.pdf"

python scripts/interlinear/json_to_trilingual_en_notes_tex.py "$assembled_json" \
  -o "$build_dir/source.tex" \
  --color-mode "$color_mode" \
  --author "$author" \
  --author-reading "$author_reading" \
  --curated-by "AgInTiFlow curated" \
  --curated-url "https://flow.lazying.art" \
  --powered-by "powered by LazyingArt" \
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
