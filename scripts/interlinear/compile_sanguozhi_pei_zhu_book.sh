#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_sanguozhi_pei_zhu_book.sh [--main-layer wenyan|zh_modern|ja_modern|en] [--color-mode color|blackwhite] [--allow-missing]
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

main_layer="wenyan"
color_mode="color"
allow_missing="${ALLOW_MISSING:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-layer) main_layer="$2"; shift 2 ;;
    --color-mode) color_mode="$2"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

case "$main_layer" in
  wenyan|zh_modern|ja_modern|en) ;;
  *) echo "Unsupported main layer: $main_layer" >&2; exit 1 ;;
esac
case "$color_mode" in
  color|blackwhite) ;;
  *) echo "Unsupported color mode: $color_mode" >&2; exit 1 ;;
esac

book_id="sanguozhi-pei-zhu"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  python scripts/interlinear/prepare_sanguozhi_pei_zhu_task.py
fi

base_json="$(jq -r '.base_current_assembled_json' "$plan")"
if [[ ! -f "$base_json" ]]; then
  python scripts/interlinear/assemble_quadrilingual_json.py \
    --manifest "$(jq -r '.base_current_manifest' "$plan")" \
    --chunks-jsonl "$(jq -r '.base_current_chunks_jsonl' "$plan")" \
    --chunk-dir "$(jq -r '.base_current_chunk_dir' "$plan")" \
    --output "$base_json"
fi

assembled_json="$(jq -r '.assembled_json' "$plan")"
build_dir="build/$book_id/${main_layer}-main-quadrilingual/$color_mode"
mkdir -p "$(dirname "$assembled_json")" "$build_dir"

assemble_args=(
  --current-book-json "$base_json"
  --pei-manifest "$(jq -r '.pei_chunks_manifest' "$plan")"
  --pei-chunks-jsonl "$(jq -r '.pei_chunks_jsonl' "$plan")"
  --pei-chunk-dir "$(jq -r '.pei_raw_chunk_dir' "$plan")"
  --output "$assembled_json"
)
if [[ "$allow_missing" == "1" ]]; then
  assemble_args+=(--allow-missing)
fi
python scripts/interlinear/assemble_sanguozhi_pei_zhu_json.py "${assemble_args[@]}"
python scripts/interlinear/validate_quadrilingual_interlinear_json.py "$assembled_json"

author="$(jq -r '.author // ""' "$plan")"
author_reading="$(jq -r '.author_reading_ja // ""' "$plan")"
cover="$(jq -r '.cover_image // ""' "$plan")"
note_order="$(jq -r --arg layer "$main_layer" '.default_note_order[$layer] // [] | join(",")' "$plan")"
tex_args=(
  "$assembled_json"
  --main-layer "$main_layer"
  --color-mode "$color_mode"
  --author "$author"
  --author-reading "$author_reading"
  --cover-image "$cover"
  -o "$build_dir/source.tex"
)
if [[ -n "$note_order" ]]; then
  tex_args+=(--note-order "$note_order")
fi
python scripts/interlinear/json_to_quadrilingual_wenyan_tex.py "${tex_args[@]}"

cat > "$build_dir/book.tex" <<EOF
\\def\\QuadSource{$build_dir/source.tex}\\input{tex/interlinear-quadrilingual/book.tex}
EOF

case "$main_layer" in
  wenyan) base_title="三國志裴松之注（英文・現代日本語・現代中文注）" ;;
  zh_modern) base_title="三国志裴松之注（現代中文主文・文言・現代日本語・英文注）" ;;
  ja_modern) base_title="三国志裴松之注（現代日本語主文・文言・現代中文・英文注）" ;;
  en) base_title="Records of the Three Kingdoms with Pei Songzhi Commentary（英文主文・文言・現代日本語・現代中文注）" ;;
esac
if [[ "$color_mode" == "blackwhite" ]]; then
  pdf_name="${base_title%）}・黑白）.pdf"
else
  pdf_name="$base_title.pdf"
fi

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
mv -f "$build_dir/book.pdf" "$build_dir/$pdf_name"
echo "$build_dir/$pdf_name"
