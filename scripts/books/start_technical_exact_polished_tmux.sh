#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-technical-exact-polished}"
source_queue="${SOURCE_QUEUE:-data/source-plan/technical-exact-polished-queue.json}"
prepared_queue="${PREPARED_QUEUE:-build-pocket-polished/tasks/technical-exact-queue.json}"
status="${STATUS:-build-pocket-polished/status-technical-exact.json}"
prepare_force="${PREPARE_FORCE:-0}"

prepare_args=(
  --queue "$source_queue"
  --output-queue "$prepared_queue"
)
if [[ "$prepare_force" == "1" ]]; then
  prepare_args+=(--force)
fi

python scripts/books/prepare_build_pocket_polished.py "${prepare_args[@]}"

WORKERS="${WORKERS:-5}" \
MODEL="${MODEL:-gpt-5.6-sol}" \
REASONING="${REASONING:-low}" \
QUEUE="$prepared_queue" \
STATUS="$status" \
SMOKE_BOOK="${SMOKE_BOOK:-game-theory-mathpix-exact-book}" \
bash scripts/books/start_build_pocket_polished_tmux.sh "$session"
