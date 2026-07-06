#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_zizhi_tongjian_comment_aware.sh [--color-mode color|blackwhite] [--skip-spans]

Builds a derived Zizhi Tongjian PDF from copied JSON.  It does not regenerate
or refetch model JSON.  Main/comment spans are inferred from the source PDF font
layer and stored as a sidecar under books/zizhi-tongjian-comment-aware/work/.
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="zizhi-tongjian-comment-aware"
color_mode="color"
skip_spans=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --color-mode) color_mode="$2"; shift 2 ;;
    --skip-spans) skip_spans=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

case "$color_mode" in
  color|blackwhite) ;;
  *) echo "Unsupported color mode: $color_mode" >&2; exit 1 ;;
esac

bash scripts/interlinear/setup_zizhi_tongjian_comment_aware_project.sh

plan="books/$book_id/book-plan.json"
manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
source_pdf="$(jq -r '.source_paths.commented_classical_source' "$plan")"
xml_cache="books/$book_id/work/pdf-font-map/zizhi-tongjian.xml"
sidecar="books/$book_id/work/comment-aware/comment-spans.jsonl"
span_report="books/$book_id/work/comment-aware/comment-span-report.json"
assembled_json="books/$book_id/work/quadrilingual/preview/$book_id.partial.json"
build_dir="build/$book_id/maximum-language-large-font/wenyan-main-quadrilingual/$color_mode"
mkdir -p "$(dirname "$assembled_json")" "$build_dir"

if [[ "$skip_spans" != "1" || ! -s "$sidecar" ]]; then
  python scripts/interlinear/build_zizhi_tongjian_comment_spans.py \
    --manifest "$manifest" \
    --chunks-jsonl "$chunks_jsonl" \
    --chunk-dir "$chunk_dir" \
    --source-pdf "$source_pdf" \
    --xml-cache "$xml_cache" \
    --output "$sidecar" \
    --report "$span_report"
fi

python scripts/interlinear/assemble_quadrilingual_json.py \
  --manifest "$manifest" \
  --chunks-jsonl "$chunks_jsonl" \
  --chunk-dir "$chunk_dir" \
  --output "$assembled_json"
python scripts/interlinear/validate_quadrilingual_interlinear_json.py "$assembled_json"

author="$(jq -r '.author // ""' "$plan")"
author_reading="$(jq -r '.author_reading_ja // ""' "$plan")"
cover="$(jq -r '.cover_image // ""' "$plan")"
note_order="$(jq -r '.default_note_order.wenyan // [] | join(",")' "$plan")"

tex_args=(
  "$assembled_json"
  --main-layer wenyan
  --color-mode "$color_mode"
  --author "$author"
  --author-reading "$author_reading"
  --cover-image "$cover"
  --comment-sidecar "$sidecar"
  -o "$build_dir/source.tex"
)
if [[ -n "$note_order" ]]; then
  tex_args+=(--note-order "$note_order")
fi
python scripts/interlinear/json_to_quadrilingual_wenyan_comment_aware_tex.py "${tex_args[@]}"

cat > "$build_dir/book.tex" <<EOF
\\documentclass[UTF8,fontset=none,10pt,openany]{ctexbook}
\\input{tex/interlinear-quadrilingual/style.tex}

% Large-font profile plus comment-aware Zizhi Tongjian main-line styling.
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

\\newcommand{\\QuadAnnotationBadge}[1]{%
  {\\begingroup\\setlength{\\fboxsep}{0.55pt}\\sffamily\\bfseries\\fontsize{5.8pt}{6.2pt}\\selectfont
  \\ifBWMode\\fbox{\\strut #1}\\else\\colorbox{BookFaint}{\\textcolor{BookRed}{\\strut #1}}\\fi\\endgroup}%
}
\\newcommand{\\QuadMainWenyanComment}[1]{{\\zhfont\\fontsize{11.2pt}{16.8pt}\\selectfont\\color{BookNote}\\QuadAnnotationBadge{注}\\thinspace #1}}
\\newcommand{\\QuadMainWenyanPronunciation}[1]{{\\zhfont\\fontsize{10.8pt}{16.2pt}\\selectfont\\color{BookNote}\\QuadAnnotationBadge{音}\\thinspace #1}}
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

if [[ "$color_mode" == "blackwhite" ]]; then
  pdf_name="資治通鑑（正文注釋辨識版・英文・現代日本語・現代中文注・黑白）・大字版.pdf"
else
  pdf_name="資治通鑑（正文注釋辨識版・英文・現代日本語・現代中文注）・大字版.pdf"
fi

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" > "$build_dir/xelatex-pass1.log"
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$build_dir" "$build_dir/book.tex" > "$build_dir/xelatex-pass2.log"
mv -f "$build_dir/book.pdf" "$build_dir/$pdf_name"

if rg -n "Overfull \\\\hbox" "$build_dir/book.log" > "$build_dir/overfull-lines.txt"; then
  echo "overfull warnings: $build_dir/overfull-lines.txt" >&2
else
  rm -f "$build_dir/overfull-lines.txt"
fi
echo "$build_dir/$pdf_name"

