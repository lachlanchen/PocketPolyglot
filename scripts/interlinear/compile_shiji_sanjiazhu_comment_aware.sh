#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

limit="${LIMIT:-4622}"
sidecar="books/shiji-sanjiazhu-comment-aware/work/commentary/commentary-sidecar.jsonl"
renderer="books/shiji/work/aginti/render_three_layer_tex.py"
cover="assets/covers/shiji-aginti/cover.png"
build_root="build/shiji-sanjiazhu-comment-aware/maximum-language-large-font/wenyan-main-jp-zh"

if [[ ! -s "$sidecar" ]]; then
  echo "Missing commentary sidecar: $sidecar" >&2
  exit 1
fi

compile_variant() {
  local mode="$1"
  local out="$build_root/$mode"
  local bw=()
  local cover_args=()
  [[ "$mode" == "blackwhite" ]] && bw=(--bw)
  [[ -f "$cover" ]] && cover_args=(--cover-image "$cover")
  python "$renderer" \
    --direction zh_main \
    --start 1 \
    --limit "$limit" \
    --out-dir "$out" \
    --commentary-sidecar "$sidecar" \
    "${bw[@]}" \
    "${cover_args[@]}"
  (
    cd "$out"
    xelatex -interaction=nonstopmode -halt-on-error book.tex >/dev/null
    xelatex -interaction=nonstopmode -halt-on-error book.tex >/dev/null
  )
  local suffix="彩色"
  [[ "$mode" == "blackwhite" ]] && suffix="黑白"
  mv -f "$out/book.pdf" "$out/史記三家注（本文・日本語・現代中文）・大字版・${suffix}.pdf"
}

compile_variant color
compile_variant blackwhite
