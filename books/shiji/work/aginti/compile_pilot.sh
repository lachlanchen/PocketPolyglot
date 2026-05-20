#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RENDERER="$SCRIPT_DIR/render_three_layer_tex.py"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
BUILD_DIR="$ROOT_DIR/build/shiji-aginti"
CHUNKS_DIR="$ROOT_DIR/data/interlinear/shiji-aginti/chunks"

JP_COLOR="$BUILD_DIR/jp-main/color"
JP_BW="$BUILD_DIR/jp-main/blackwhite"
ZH_COLOR="$BUILD_DIR/zh-main/color"
ZH_BW="$BUILD_DIR/zh-main/blackwhite"

MODE="--color"
if [[ "${1:-}" == "--blackwhite" ]]; then
  MODE="--blackwhite"
fi

LIMIT="${LIMIT:-}"
if [[ -z "$LIMIT" ]]; then
  LIMIT="$(python3 - "$CHUNKS_DIR" "$ROOT_DIR/books/shiji/work/aginti/validate_shiji_chunk.py" <<'PY'
import sys
import subprocess
from pathlib import Path

chunks = Path(sys.argv[1])
validator = Path(sys.argv[2])
n = 1
while True:
    path = chunks / f"shiji-chunk-{n:04d}.json"
    if not path.exists():
        break
    result = subprocess.run(
        [sys.executable, str(validator), str(path), "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if result.returncode != 0:
        break
    n += 1
print(max(0, n - 1))
PY
)"
fi

if [[ "$LIMIT" -lt 1 ]]; then
  echo "No Shiji chunks available to compile."
  exit 1
fi

echo "Compiling first $LIMIT Shiji chunks."

compile_dir() {
  local dir="$1"
  local pdf="$2"
  local direction="$3"
  local bw_flag=""
  if [[ "$MODE" == "--blackwhite" ]]; then
    bw_flag="--bw"
  fi
  python3 "$RENDERER" --direction "$direction" $bw_flag --start 1 --limit "$LIMIT" --out-dir "$dir"
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
