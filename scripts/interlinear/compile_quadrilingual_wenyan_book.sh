#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_quadrilingual_wenyan_book.sh --book-id <id> [--main-layer wenyan|zh_modern|ja_modern|en] [--color-mode color|blackwhite] [--allow-missing]
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id=""
main_layer="wenyan"
color_mode="color"
allow_missing="${ALLOW_MISSING:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="$2"; shift 2 ;;
    --main-layer) main_layer="$2"; shift 2 ;;
    --color-mode) color_mode="$2"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done
if [[ -z "$book_id" ]]; then
  usage >&2
  exit 1
fi
case "$main_layer" in
  wenyan|zh_modern|ja_modern|en) ;;
  *) echo "Unsupported main layer: $main_layer" >&2; exit 1 ;;
esac
case "$color_mode" in
  color|blackwhite) ;;
  *) echo "Unsupported color mode: $color_mode" >&2; exit 1 ;;
esac

plan="books/$book_id/book-plan.json"
manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
assembled_json="books/$book_id/work/quadrilingual/preview/$book_id.partial.json"
build_dir="build/$book_id/${main_layer}-main-quadrilingual/$color_mode"
mkdir -p "$(dirname "$assembled_json")" "$build_dir"

if find "$chunk_dir" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
  python scripts/interlinear/backfill_quadrilingual_grammar_roles.py \
    --chunk-dir "$chunk_dir" \
    --chunks-jsonl "$chunks_jsonl" \
    --overwrite-collapsed
fi

assemble_args=(
  --manifest "$manifest"
  --chunks-jsonl "$chunks_jsonl"
  --chunk-dir "$chunk_dir"
  --output "$assembled_json"
)
if [[ "$allow_missing" == "1" ]]; then
  assemble_args+=(--allow-missing)
fi
python scripts/interlinear/assemble_quadrilingual_json.py "${assemble_args[@]}"
python scripts/interlinear/validate_quadrilingual_interlinear_json.py "$assembled_json"

author="$(jq -r '.author // ""' "$plan")"
author_reading="$(jq -r '.author_reading_ja // ""' "$plan")"
cover="$(jq -r '.cover_image // ""' "$plan")"
python scripts/interlinear/json_to_quadrilingual_wenyan_tex.py "$assembled_json" \
  --main-layer "$main_layer" \
  --color-mode "$color_mode" \
  --author "$author" \
  --author-reading "$author_reading" \
  --cover-image "$cover" \
  -o "$build_dir/source.tex"

cat > "$build_dir/book.tex" <<EOF
\\def\\QuadSource{$build_dir/source.tex}\\input{tex/interlinear-quadrilingual/book.tex}
EOF

title_wenyan="$(jq -r '.book_title_wenyan // .book_title_zh // .book_title_ja // .book_title_en // .book_id' "$plan")"
title_zh="$(jq -r '.book_title_zh // .book_title_wenyan // .book_title_ja // .book_title_en // .book_id' "$plan")"
title_ja="$(jq -r '.book_title_ja // .book_title_wenyan // .book_title_zh // .book_title_en // .book_id' "$plan")"
title_en="$(jq -r '.book_title_en // .book_title_wenyan // .book_title_zh // .book_title_ja // .book_id' "$plan")"
case "$main_layer" in
  wenyan) base_title="${title_wenyan}（現代日本語・現代中文・英文注）" ;;
  zh_modern) base_title="${title_zh}（現代中文主文・文言・現代日本語・英文注）" ;;
  ja_modern) base_title="${title_ja}（現代日本語主文・文言・現代中文・英文注）" ;;
  en) base_title="${title_en}（英文主文・文言・現代日本語・現代中文注）" ;;
esac
if [[ "$color_mode" == "blackwhite" ]]; then
  if [[ "$base_title" == *"）" ]]; then
    pdf_name="${base_title%）}・黑白）.pdf"
  else
    pdf_name="${base_title}・黑白.pdf"
  fi
else
  pdf_name="${base_title}.pdf"
fi

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
mv -f "$build_dir/book.pdf" "$build_dir/$pdf_name"
echo "$build_dir/$pdf_name"
