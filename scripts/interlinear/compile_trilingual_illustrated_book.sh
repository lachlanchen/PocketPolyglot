#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_trilingual_illustrated_book.sh --book-id <illustrated-id> [--color-mode color|blackwhite]

Compile an additive English-main/Japanese/Chinese illustrated edition from a
prepared plan. Existing source-book JSON and PDFs are never modified.
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
book_id=""
color_mode="color"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="${2:-}"; shift 2 ;;
    --color-mode) color_mode="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$book_id" ]]; then
  usage >&2
  exit 1
fi
case "$color_mode" in
  color|blackwhite) ;;
  *) echo "Invalid --color-mode: $color_mode" >&2; exit 1 ;;
esac

cd "$root"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing illustrated plan: $plan" >&2
  exit 1
fi

manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
assembled_json="$(jq -r '.assembled_json' "$plan")"
figure_count="$(jq -r '.figure_count' "$plan")"
title_en="$(jq -r '.book_title_en' "$plan")"
author="$(jq -r '.author // ""' "$plan")"
author_reading="$(jq -r '.author_reading_ja // ""' "$plan")"
curated_by="$(jq -r '.curated_by // "AgInTiFlow curated"' "$plan")"
curated_url="$(jq -r '.curated_url // "https://flow.lazying.art"' "$plan")"
powered_by="$(jq -r '.powered_by // "powered by LazyingArt"' "$plan")"
cover_image="$(jq -r '.cover_image // ""' "$plan")"

build_dir="build/$book_id/en-main-jp-zh/$color_mode"
mkdir -p "$build_dir" "$(dirname "$assembled_json")"

python scripts/interlinear/assemble_trilingual_json.py \
  --manifest "$manifest" \
  --chunks-jsonl "$chunks_jsonl" \
  --chunk-dir "$chunk_dir" \
  --output "$assembled_json"
python scripts/interlinear/validate_trilingual_interlinear_json.py "$assembled_json"
python scripts/interlinear/validate_trilingual_figure_assets.py \
  "$assembled_json" \
  --expected-count "$figure_count" \
  --report "books/$book_id/work/trilingual/figure-validation.json"

python scripts/interlinear/json_to_trilingual_en_notes_tex.py "$assembled_json" \
  -o "$build_dir/source.tex" \
  --color-mode "$color_mode" \
  --author "$author" \
  --author-reading "$author_reading" \
  --curated-by "$curated_by" \
  --curated-url "$curated_url" \
  --powered-by "$powered_by" \
  --cover-image "$cover_image" \
  --include-figures

rendered_count="$(grep -c '\\TriAllFigure' "$build_dir/source.tex" || true)"
if [[ "$rendered_count" != "$figure_count" ]]; then
  echo "Rendered figure count mismatch: expected=$figure_count actual=$rendered_count" >&2
  exit 1
fi

cat > "$build_dir/book.tex" <<EOF
\\def\\TriAllSource{$build_dir/source.tex}
\\input{tex/interlinear-trilingual-en-notes/book.tex}
EOF

base_title="${title_en}（図版収録・日文・中文注）"
if [[ "$color_mode" == "blackwhite" ]]; then
  base_title="${base_title%）}・黑白）"
fi
output_pdf="$build_dir/$base_title.pdf"

rm -f "$build_dir/book.aux" "$build_dir/book.out" "$build_dir/book.toc" "$build_dir/book.log"
xelatex -interaction=nonstopmode -halt-on-error -jobname=book \
  -output-directory="$build_dir" "$build_dir/book.tex" \
  > "$build_dir/xelatex-pass1.log" 2>&1
xelatex -interaction=nonstopmode -halt-on-error -jobname=book \
  -output-directory="$build_dir" "$build_dir/book.tex" \
  > "$build_dir/xelatex-pass2.log" 2>&1
mv -f "$build_dir/book.pdf" "$output_pdf"
echo "PDF: $output_pdf"
