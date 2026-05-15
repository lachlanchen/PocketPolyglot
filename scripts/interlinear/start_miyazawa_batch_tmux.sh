#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

books=(
  "chumon-no-ooi-ryoriten"
  "ginga-tetsudo"
)

if [[ $# -gt 0 ]]; then
  books=("$@")
fi

WORKERS="${WORKERS:-10}" \
REVIEW_WORKERS="${REVIEW_WORKERS:-6}" \
bash scripts/interlinear/start_japanese_literature_batch_tmux.sh "${books[@]}"
