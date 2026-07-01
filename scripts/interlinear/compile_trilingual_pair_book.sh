#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_trilingual_pair_book.sh --book-id <id> --main-lang <en|zh|ja> --comment-lang <en|zh|ja> [options]

Assemble available trilingual chunks, validate the JSON, render one pair-direction
TeX source, compile it with XeLaTeX, and copy the PDF to a stable book-name path.

Options:
  --book-id <id>             book id, e.g. gone-with-the-wind
  --main-lang <en|zh|ja>     main text language
  --comment-lang <en|zh|ja>  comment language
  --color-mode <mode>        color or blackwhite
  --allow-missing            build a preview from available chunks
  --input-json <path>        render from an already assembled trilingual JSON
  --cover-image <path>       workspace-relative cover image
  TRILINGUAL_BACKFILL_GRAMMAR=0 disables the default color-role backfill
  -h, --help                 show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
book_id=""
main_lang=""
comment_lang=""
color_mode="color"
allow_missing=0
cover_image=""
input_json=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="${2:-}"; shift 2 ;;
    --main-lang) main_lang="${2:-}"; shift 2 ;;
    --comment-lang) comment_lang="${2:-}"; shift 2 ;;
    --color-mode) color_mode="${2:-}"; shift 2 ;;
    --allow-missing) allow_missing=1; shift ;;
    --input-json) input_json="${2:-}"; shift 2 ;;
    --cover-image) cover_image="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$book_id" || -z "$main_lang" || -z "$comment_lang" ]]; then
  usage >&2
  exit 1
fi
if [[ "$main_lang" == "$comment_lang" ]]; then
  echo "main and comment languages must differ" >&2
  exit 1
fi
case "$main_lang" in en|zh|ja) ;; *) echo "Invalid --main-lang: $main_lang" >&2; exit 1 ;; esac
case "$comment_lang" in en|zh|ja) ;; *) echo "Invalid --comment-lang: $comment_lang" >&2; exit 1 ;; esac
case "$color_mode" in color|blackwhite) ;; *) echo "Invalid --color-mode: $color_mode" >&2; exit 1 ;; esac

cd "$root"
lock_dir="books/$book_id/work/trilingual"
mkdir -p "$lock_dir"
exec 9>"$lock_dir/compile.lock"
flock 9

plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
title_en="$(jq -r '.book_title_en' "$plan")"
title_zh="$(jq -r '.book_title_zh' "$plan")"
title_ja="$(jq -r '.book_title_ja' "$plan")"
author="$(jq -r '.author' "$plan")"
author_reading="$(jq -r '.author_reading_ja // empty' "$plan")"
curated_by="$(jq -r '.curated_by // "AgInTiFlow curated"' "$plan")"
curated_url="$(jq -r '.curated_url // "https://flow.lazying.art"' "$plan")"
powered_by="$(jq -r '.powered_by // "powered by LazyingArt"' "$plan")"

if [[ -z "$cover_image" && -f "assets/covers/$book_id/cover.png" ]]; then
  cover_image="assets/covers/$book_id/cover.png"
fi

case "$main_lang:$comment_lang" in
  zh:en|en:zh) pair="zh-en" ;;
  zh:ja|ja:zh) pair="zh-jp" ;;
  jp:en|en:jp) pair="jp-en" ;;
  ja:en|en:ja) pair="jp-en" ;;
  *) pair="$main_lang-$comment_lang" ;;
esac
dir_lang() {
  case "$1" in
    ja) printf 'jp' ;;
    *) printf '%s' "$1" ;;
  esac
}

direction="$(dir_lang "$main_lang")-main"
build_dir="build/$book_id/$pair/$direction/$color_mode"
if [[ -n "$input_json" ]]; then
  assembled_json="$input_json"
else
  assembled_json="books/$book_id/work/trilingual/preview/$book_id.partial.json"
fi

lang_title() {
  case "$1" in
    en) printf '%s' "$title_en" ;;
    zh) printf '%s' "$title_zh" ;;
    ja) printf '%s' "$title_ja" ;;
  esac
}

comment_label() {
  case "$1" in
    en) printf '英文注' ;;
    zh) printf '中文注' ;;
    ja) printf '日文注' ;;
  esac
}

base_title="$(lang_title "$main_lang")（$(comment_label "$comment_lang")）"
if [[ "$color_mode" == "blackwhite" ]]; then
  base_title="${base_title%）}・黑白）"
fi
output_pdf="$build_dir/$base_title.pdf"

mkdir -p "$build_dir" "$(dirname "$assembled_json")"

if [[ -z "$input_json" ]]; then
  if [[ "$color_mode" == "color" && "${TRILINGUAL_BACKFILL_GRAMMAR:-1}" != "0" ]]; then
    if find "$chunk_dir" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
      python scripts/interlinear/backfill_trilingual_grammar_roles.py \
        --chunk-dir "$chunk_dir" \
        --chunks-jsonl "$chunks_jsonl" \
        --overwrite-collapsed
    fi
  fi

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
elif [[ ! -f "$assembled_json" ]]; then
  echo "Missing --input-json file: $assembled_json" >&2
  exit 1
fi
python scripts/interlinear/validate_trilingual_interlinear_json.py "$assembled_json"

python scripts/interlinear/json_to_trilingual_pair_tex.py "$assembled_json" \
  -o "$build_dir/source.tex" \
  --main-lang "$main_lang" \
  --comment-lang "$comment_lang" \
  --color-mode "$color_mode" \
  --author "$author" \
  --author-reading "$author_reading" \
  --curated-by "$curated_by" \
  --curated-url "$curated_url" \
  --powered-by "$powered_by" \
  --cover-image "$cover_image"

rm -f "$build_dir/book.aux" "$build_dir/book.out" "$build_dir/book.toc" "$build_dir/book.log"
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\TriPairSource{$build_dir/source.tex}\\input{tex/interlinear-trilingual-pair/book.tex}" \
  > "$build_dir/xelatex-pass1.log" 2>&1
xelatex -interaction=nonstopmode -halt-on-error -jobname=book -output-directory="$build_dir" \
  "\\def\\TriPairSource{$build_dir/source.tex}\\input{tex/interlinear-trilingual-pair/book.tex}" \
  > "$build_dir/xelatex-pass2.log" 2>&1
cp "$build_dir/book.pdf" "$output_pdf"
rm -f "$build_dir/book.pdf"
cp "$build_dir/source.tex" "$build_dir/$base_title.tex"
echo "PDF: $output_pdf"
