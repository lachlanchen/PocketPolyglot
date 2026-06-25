#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

set +u
[[ -f "$HOME/.profile" ]] && source "$HOME/.profile"
[[ -f "$HOME/.bashrc" ]] && source "$HOME/.bashrc"
set -u

BOOKS=(
  game-theory
  game-theory-101
  nonlinear-dynamics-and-chaos
  chaos-making-new-science
  qft-gifted-amateur
)

INTERVAL="${MATHPIX_WAIT_INTERVAL:-180}"
PASSES="${TEXTBOOK_LATEX_PASSES:-2}"

for book_id in "${BOOKS[@]}"; do
  echo "[$(date -Is)] start editable English pocket: ${book_id}"
  python scripts/interlinear/compile_textbook_english_pocket.py \
    --book-id "${book_id}" \
    --submit-missing \
    --wait \
    --download \
    --interval "${INTERVAL}" \
    --passes "${PASSES}"

  build_dir="build/${book_id}-exact-pocket/english"
  python scripts/interlinear/validate_textbook_editable_pdf.py \
    --build-dir "${build_dir}" \
    --output "${build_dir}/validation-report.json"

  python scripts/interlinear/prepare_textbook_editable_review_tasks.py \
    --book-id "${book_id}" \
    --build-dir "${build_dir}" \
    --render-images

  git add \
    "books/${book_id}/tasks/editable-review/manifest.json" \
    "books/${book_id}/tasks/editable-review/tasks.jsonl"
  git commit -m "Update ${book_id} editable textbook review tasks" || true
  echo "[$(date -Is)] done editable English pocket: ${book_id}"
done
