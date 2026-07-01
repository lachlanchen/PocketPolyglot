#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_quran_arabic_quadrilingual_book.sh [--main-layer ar|en|ja|zh] [--color-mode color|blackwhite]
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

main_layer="ar"
color_mode="color"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-layer) main_layer="$2"; shift 2 ;;
    --color-mode) color_mode="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done
case "$main_layer" in ar|en|ja|zh) ;; *) echo "Unsupported main layer: $main_layer" >&2; exit 1 ;; esac
case "$color_mode" in color|blackwhite) ;; *) echo "Unsupported color mode: $color_mode" >&2; exit 1 ;; esac

python scripts/interlinear/fetch_qurancom_word_data.py
python scripts/interlinear/build_quran_arabic_quadrilingual_json.py
assembled_json="books/quran/work/arabic-quadrilingual/preview/quran.full.json"
python scripts/interlinear/validate_quran_arabic_quadrilingual_json.py "$assembled_json"

cover="assets/covers/quran/cover.png"
if [[ ! -s "$cover" ]]; then
  python scripts/interlinear/render_quran_cover.py --output "$cover"
fi

build_dir="build/quran/${main_layer}-main-quadrilingual/$color_mode"
mkdir -p "$build_dir"

case "$main_layer" in
  ar) note_order="en,ja,zh"; base_title="القرآن الكريم（English・日本語・中文注）" ;;
  en) note_order="ar,ja,zh"; base_title="The Quran（العربية・日本語・中文注）" ;;
  ja) note_order="ar,en,zh"; base_title="クルアーン（العربية・English・中文注）" ;;
  zh) note_order="ar,en,ja"; base_title="古蘭經（العربية・English・日本語注）" ;;
esac
if [[ "$color_mode" == "blackwhite" ]]; then
  pdf_name="${base_title%）}・黑白）.pdf"
else
  pdf_name="${base_title}.pdf"
fi

python scripts/interlinear/json_to_arabic_quadrilingual_tex.py \
  "$assembled_json" \
  --main-layer "$main_layer" \
  --note-order "$note_order" \
  --color-mode "$color_mode" \
  --cover-image "$cover" \
  -o "$build_dir/source.tex"

cat > "$build_dir/book.tex" <<EOF
\\def\\QuranSource{$build_dir/source.tex}\\input{tex/interlinear-arabic-quadrilingual/book.tex}
EOF

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
mv -f "$build_dir/book.pdf" "$build_dir/$pdf_name"
python - "$main_layer" "$color_mode" "$build_dir/$pdf_name" <<'PY'
import json
import sys
from pathlib import Path

main_layer, color_mode, pdf_path = sys.argv[1:4]
plan_path = Path("books/quran/book-plan.json")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
plan["status"] = "compiled"
plan["launchable"] = True
plan["assembled_json"] = "books/quran/work/arabic-quadrilingual/preview/quran.full.json"
plan["cover_image"] = "assets/covers/quran/cover.png"
plan["pipeline_scripts"] = [
    "scripts/interlinear/fetch_qurancom_word_data.py",
    "scripts/interlinear/build_quran_arabic_quadrilingual_json.py",
    "scripts/interlinear/validate_quran_arabic_quadrilingual_json.py",
    "scripts/interlinear/json_to_arabic_quadrilingual_tex.py",
    "scripts/interlinear/compile_quran_arabic_quadrilingual_book.sh",
]
plan.setdefault("compiled_outputs", {}).setdefault(main_layer, {})[color_mode] = pdf_path
plan["required_pipeline_work"] = []
plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
echo "$build_dir/$pdf_name"
