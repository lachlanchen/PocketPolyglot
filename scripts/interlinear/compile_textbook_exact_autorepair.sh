#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  cat >&2 <<'USAGE'
Usage:
  scripts/interlinear/compile_textbook_exact_autorepair.sh <book-id> <mathpix|local> [extra args...]

Examples:
  scripts/interlinear/compile_textbook_exact_autorepair.sh game-theory mathpix
  scripts/interlinear/compile_textbook_exact_autorepair.sh tom-kolb-music-theory-guitarists local --allow-codex
  scripts/interlinear/compile_textbook_exact_autorepair.sh berklee-music-theory-book-1 local --force-marker

Defaults:
  passes=2, max-rounds=10, Codex fallback disabled unless --allow-codex is passed.
USAGE
  exit 2
fi

book_id="$1"
mode="$2"
shift 2

cd "$(dirname "$0")/../.."

python3 scripts/interlinear/compile_textbook_exact_autorepair.py \
  --book-id "$book_id" \
  --mode "$mode" \
  --passes "${TEXTBOOK_EXACT_PASSES:-2}" \
  --max-rounds "${TEXTBOOK_EXACT_MAX_ROUNDS:-10}" \
  "$@"
