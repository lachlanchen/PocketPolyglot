#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

export CURRENT_BOOK_ID="${CURRENT_BOOK_ID:-one-hundred-years-of-solitude}"
export BOOK_IDS="${BOOK_IDS:-wuthering-heights the-count-of-monte-cristo notre-dame-de-paris les-miserables}"
export WORKERS="${WORKERS:-10}"
export MODEL="${MODEL:-gpt-5.5}"
export REASONING="${REASONING:-high}"
export RETRY_FAILED="${RETRY_FAILED:-1}"
export INTERVAL_SECONDS="${INTERVAL_SECONDS:-1800}"
export MAX_ACTIVE_BOOKS="${MAX_ACTIVE_BOOKS:-1}"

exec bash scripts/interlinear/start_trilingual_queue_tmux.sh "${1:-zhjpbook-world-literature-queue}"
