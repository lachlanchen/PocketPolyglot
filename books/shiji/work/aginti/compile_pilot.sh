#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RENDERER="$SCRIPT_DIR/render_three_layer_tex.py"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
BUILD_DIR="$ROOT_DIR/build/shiji-aginti"

JP_COLOR="$BUILD_DIR/jp-main/color"
JP_BW="$BUILD_DIR/jp-main/blackwhite"
ZH_COLOR="$BUILD_DIR/zh-main/color"
ZH_BW="$BUILD_DIR/zh-main/blackwhite"

MODE="--color"
if [[ "${1:-}" == "--blackwhite" ]]; then
  MODE="--blackwhite"
fi

compile_dir() {
  local dir="$1"
  local pdf="$2"
  local direction="$3"
  local bw_flag=""
  if [[ "$MODE" == "--blackwhite" ]]; then
    bw_flag="--bw"
  fi
  python3 "$RENDERER" --direction "$direction" $bw_flag --start 1 --limit 3 --out-dir "$dir"
  cd "$dir"
  xelatex -interaction=nonstopmode book.tex
  xelatex -interaction=nonstopmode book.tex
  xelatex -interaction=nonstopmode book.tex
  if [[ -f book.pdf ]]; then
    cp book.pdf "$pdf"
    echo "OK: $pdf"
  else
    echo "FAIL: book.pdf not produced in $dir"
    return 1
  fi
  cd - > /dev/null
}

mkdir -p "$JP_COLOR" "$JP_BW" "$ZH_COLOR" "$ZH_BW"

if [[ "$MODE" == "--blackwhite" ]]; then
  echo "=== Compiling BLACKWHITE ==="
  compile_dir "$JP_BW"  "$JP_BW/史記（中文注・白黒）.pdf"  jp_main
  compile_dir "$ZH_BW"  "$ZH_BW/史記（日本語注・白黒）.pdf"  zh_main
else
  echo "=== Compiling COLOR ==="
  compile_dir "$JP_COLOR" "$JP_COLOR/史記（中文注）.pdf" jp_main
  compile_dir "$ZH_COLOR" "$ZH_COLOR/史記（日本語注）.pdf" zh_main
fi

echo "Done."
