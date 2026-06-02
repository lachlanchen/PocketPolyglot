#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="gone-with-the-wind"
allow_missing_arg=()
if [[ "${ALLOW_MISSING:-1}" != "0" ]]; then
  allow_missing_arg=(--allow-missing)
fi

compile_one() {
  local main_lang="$1"
  local comment_lang="$2"
  local color_mode="$3"
  bash scripts/interlinear/compile_trilingual_pair_book.sh \
    --book-id "$book_id" \
    --main-lang "$main_lang" \
    --comment-lang "$comment_lang" \
    --color-mode "$color_mode" \
    "${allow_missing_arg[@]}"
}

for color_mode in color blackwhite; do
  compile_one zh en "$color_mode"
  compile_one en zh "$color_mode"
  compile_one zh ja "$color_mode"
  compile_one ja zh "$color_mode"
  compile_one ja en "$color_mode"
  compile_one en ja "$color_mode"
done
