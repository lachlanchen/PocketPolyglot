#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_quadrilingual_wenyan_part_large_font.sh --book-id <id> --part part-01 [--main-layer wenyan] [--color-mode color|blackwhite] [--cover-image path]

Builds a large-font quadrilingual PDF for one prepared task part using the
part manifest under:

  books/<book-id>/work/quadrilingual/parts/<part>/manifest.json
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id=""
part=""
main_layer="wenyan"
color_mode="color"
cover_image=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="$2"; shift 2 ;;
    --part) part="$2"; shift 2 ;;
    --main-layer) main_layer="$2"; shift 2 ;;
    --color-mode) color_mode="$2"; shift 2 ;;
    --cover-image) cover_image="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$book_id" || -z "$part" ]]; then
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
part_manifest="books/$book_id/work/quadrilingual/parts/$part/manifest.json"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
part_number="$(jq -r '.part.part_number // empty' "$part_manifest")"
if [[ -z "$part_number" ]]; then
  echo "Part manifest lacks .part.part_number: $part_manifest" >&2
  exit 1
fi

case "$part_number" in
  1) part_zh="第一部"; part_en="Part I" ;;
  2) part_zh="第二部"; part_en="Part II" ;;
  3) part_zh="第三部"; part_en="Part III" ;;
  4) part_zh="第四部"; part_en="Part IV" ;;
  5) part_zh="第五部"; part_en="Part V" ;;
  6) part_zh="第六部"; part_en="Part VI" ;;
  7) part_zh="第七部"; part_en="Part VII" ;;
  8) part_zh="第八部"; part_en="Part VIII" ;;
  9) part_zh="第九部"; part_en="Part IX" ;;
  10) part_zh="第十部"; part_en="Part X" ;;
  *) part_zh="第${part_number}部"; part_en="Part ${part_number}" ;;
esac

assembled_json="books/$book_id/work/quadrilingual/preview/$book_id.$part.json"
build_dir="build/$book_id-$part/${main_layer}-main-quadrilingual/large-font/$color_mode"
mkdir -p "$(dirname "$assembled_json")" "$build_dir"

grammar_marker="$chunk_dir/.grammar-backfill-overwrite-collapsed.done"
if [[ ! -f "$grammar_marker" ]] || find "$chunk_dir" -maxdepth 1 -name '*.json' -newer "$grammar_marker" -print -quit | grep -q .; then
  python scripts/interlinear/backfill_quadrilingual_grammar_roles.py \
    --chunk-dir "$chunk_dir" \
    --chunks-jsonl "$chunks_jsonl" \
    --overwrite-collapsed >/dev/null
  touch "$grammar_marker"
fi

python scripts/interlinear/assemble_quadrilingual_json.py \
  --manifest "$part_manifest" \
  --chunks-jsonl "$chunks_jsonl" \
  --chunk-dir "$chunk_dir" \
  --output "$assembled_json"

PYTHONPATH=scripts/interlinear python - "$assembled_json" "$plan" "$part_zh" "$part_en" <<'PY'
import json
import sys
from pathlib import Path
from codex_trilingual_plain_json_worker import tokenize_en, tokenize_ja, tokenize_zh

assembled = Path(sys.argv[1])
plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
part_zh = sys.argv[3]
part_en = sys.argv[4]
data = json.loads(assembled.read_text(encoding="utf-8"))
title_wenyan = (plan.get("book_title_wenyan") or plan.get("book_title_zh") or plan["book_id"]) + part_zh
title_zh = (plan.get("book_title_zh") or plan.get("book_title_wenyan") or plan["book_id"]) + part_zh
title_ja = (plan.get("book_title_ja") or plan.get("book_title_wenyan") or plan["book_id"]) + part_zh
title_en = (plan.get("book_title_en") or plan["book_id"]) + ", " + part_en
data["title"] = {
    "wenyan": tokenize_zh(title_wenyan),
    "zh_modern": tokenize_zh(title_zh),
    "ja_modern": tokenize_ja(title_ja),
    "en": tokenize_en(title_en),
}
data.setdefault("source", {})["part_label"] = {"zh": part_zh, "en": part_en}
assembled.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

python scripts/interlinear/validate_quadrilingual_interlinear_json.py "$assembled_json"

author="$(jq -r '.author // ""' "$plan")"
author_reading="$(jq -r '.author_reading_ja // ""' "$plan")"
note_order="$(jq -r --arg layer "$main_layer" '.default_note_order[$layer] // [] | join(",")' "$plan")"
tex_args=(
  "$assembled_json"
  --main-layer "$main_layer"
  --color-mode "$color_mode"
  --author "$author"
  --author-reading "$author_reading"
  --cover-image "$cover_image"
  -o "$build_dir/source.tex"
)
if [[ -n "$note_order" ]]; then
  tex_args+=(--note-order "$note_order")
fi
python scripts/interlinear/json_to_quadrilingual_wenyan_tex.py "${tex_args[@]}"

cat > "$build_dir/book.tex" <<EOF
\\documentclass[UTF8,fontset=none,10pt,openany]{ctexbook}
\\input{tex/interlinear-quadrilingual/style.tex}

% Large LinguaLeaf readability profile.
\\renewcommand{\\RubyFont}{\\fontsize{3.6pt}{4pt}\\selectfont}
\\renewcommand{\\QuadMainWenyan}[1]{{\\zhfont\\fontsize{11.6pt}{17.2pt}\\selectfont\\color{BookInk}#1}}
\\renewcommand{\\QuadMainZhModern}[1]{{\\zhfont\\fontsize{11.2pt}{16.8pt}\\selectfont\\color{BookInk}#1}}
\\renewcommand{\\QuadMainJaModern}[1]{{\\jpfont\\fontsize{11.2pt}{16.8pt}\\selectfont\\color{BookInk}#1}}
\\renewcommand{\\QuadMainEn}[1]{{\\enfont\\fontsize{10.8pt}{14.2pt}\\selectfont\\color{BookInk}#1}}
\\renewcommand{\\QuadNoteWenyan}[1]{{\\zhfont\\fontsize{9.6pt}{12.7pt}\\selectfont\\color{BookNote}#1}}
\\renewcommand{\\QuadNoteJaModern}[1]{{\\jpfont\\fontsize{9.6pt}{12.7pt}\\selectfont\\color{BookNote}#1}}
\\renewcommand{\\QuadNoteZhModern}[1]{{\\zhfont\\fontsize{8.25pt}{10.9pt}\\selectfont\\color{BookNote}#1}}
\\renewcommand{\\QuadNoteEn}[1]{{\\enfont\\fontsize{8.9pt}{11.7pt}\\selectfont\\color{BookNote}#1}}
\\renewcommand{\\TinyLabel}[1]{{\\sffamily\\bfseries\\fontsize{5.8pt}{5.8pt}\\selectfont\\textcolor{BookRed}{#1}}}
\\renewcommand{\\GrammarLegend}{%
  {\\sffamily\\fontsize{5.8pt}{7pt}\\selectfont
  \\textcolor{GramSubject}{subject}\\quad
  \\textcolor{GramPredicate}{predicate}\\quad
  \\textcolor{GramObject}{object}\\quad
  \\textcolor{GramAttributive}{attributive}\\quad
  \\textcolor{GramAdverbial}{adverbial}\\quad
  \\textcolor{GramComplement}{complement}\\quad
  \\textcolor{GramTopic}{topic}\\quad
  \\textcolor{GramFunction}{function}}%
}

\\begin{document}
\\def\\QuadSource{$build_dir/source.tex}
\\input{\\QuadSource}
\\end{document}
EOF

title_wenyan="$(jq -r '.book_title_wenyan // .book_title_zh // .book_title_ja // .book_title_en // .book_id' "$plan")$part_zh"
case "$main_layer" in
  wenyan) base_title="${title_wenyan}（英文・現代日本語・現代中文注）" ;;
  zh_modern) base_title="${title_wenyan}（現代中文主文・文言・現代日本語・英文注）" ;;
  ja_modern) base_title="${title_wenyan}（現代日本語主文・文言・現代中文・英文注）" ;;
  en) base_title="${title_wenyan}（英文主文・文言・現代日本語・現代中文注）" ;;
esac
if [[ "$color_mode" == "blackwhite" ]]; then
  pdf_name="${base_title%）}・黑白）・大字版.pdf"
else
  pdf_name="${base_title}・大字版.pdf"
fi

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" >/dev/null
mv -f "$build_dir/book.pdf" "$build_dir/$pdf_name"
echo "$build_dir/$pdf_name"
