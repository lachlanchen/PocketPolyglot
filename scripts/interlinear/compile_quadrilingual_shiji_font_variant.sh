#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_quadrilingual_shiji_font_variant.sh --book-id <id> [--main-layer wenyan|zh_modern|ja_modern|en] [--color-mode color|blackwhite]

Builds a separate quadrilingual PDF variant using the larger PocketPolyglot
font profile originally tuned against the Shiji AgInTi layout. Existing source
JSON, source.tex, and PDFs are left untouched; this writes only under:

  build/<book-id>/<main-layer>-main-quadrilingual/large-font/<color-mode>/
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id=""
main_layer="wenyan"
color_mode="color"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="$2"; shift 2 ;;
    --main-layer) main_layer="$2"; shift 2 ;;
    --color-mode) color_mode="$2"; shift 2 ;;
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

base_dir="build/$book_id/${main_layer}-main-quadrilingual/$color_mode"
base_source="$base_dir/source.tex"
bash scripts/interlinear/compile_quadrilingual_wenyan_book.sh \
  --book-id "$book_id" \
  --main-layer "$main_layer" \
  --color-mode "$color_mode"
if [[ ! -f "$base_source" ]]; then
  echo "Missing source TeX: $base_source" >&2
  exit 1
fi

variant_dir="build/$book_id/${main_layer}-main-quadrilingual/large-font/$color_mode"
mkdir -p "$variant_dir"
cp "$base_source" "$variant_dir/source.tex"

cat > "$variant_dir/book.tex" <<EOF
\\documentclass[UTF8,fontset=none,10pt,openany]{ctexbook}
\\input{tex/interlinear-quadrilingual/style.tex}

% Font-only profile matched to the larger PocketPolyglot readability profile:
% main line around LaTeX \\large, first notes around \\normalsize,
% modern Chinese / English notes slightly smaller to preserve wrapping.
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
\\def\\QuadSource{$variant_dir/source.tex}
\\input{\\QuadSource}
\\end{document}
EOF

base_pdf="$(find "$base_dir" -maxdepth 1 -type f -name '*.pdf' | sort | head -n 1)"
if [[ -n "$base_pdf" ]]; then
  pdf_name="$(basename "${base_pdf%.pdf}")・大字版.pdf"
else
  pdf_name="${book_id}-${main_layer}-${color_mode}-large-font.pdf"
fi

xelatex -interaction=nonstopmode -halt-on-error -output-directory "$variant_dir" "$variant_dir/book.tex" >/dev/null
xelatex -interaction=nonstopmode -halt-on-error -output-directory "$variant_dir" "$variant_dir/book.tex" >/dev/null
mv -f "$variant_dir/book.pdf" "$variant_dir/$pdf_name"
echo "$variant_dir/$pdf_name"
