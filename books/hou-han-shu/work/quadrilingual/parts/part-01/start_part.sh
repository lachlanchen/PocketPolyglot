#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$ROOT"

SESSION="${1:-zhjpbook-hou-han-shu-part-01-100-low}"

WORKERS="${WORKERS:-100}" \
MODEL="${MODEL:-gpt-5.5}" \
REASONING="${REASONING:-low}" \
CLAIM_TTL_SECONDS="${CLAIM_TTL_SECONDS:-1800}" \
CODEX_TIMEOUT_SECONDS="${CODEX_TIMEOUT_SECONDS:-1200}" \
CODEX_EXEC_IGNORE_USER_CONFIG="${CODEX_EXEC_IGNORE_USER_CONFIG:-1}" \
CODEX_EXEC_IGNORE_RULES="${CODEX_EXEC_IGNORE_RULES:-1}" \
MAIN_LAYERS="${MAIN_LAYERS:-wenyan}" \
START_INDEX="1" \
END_INDEX="4377" \
MANIFEST_OVERRIDE="books/hou-han-shu/work/quadrilingual/parts/part-01/manifest.json" \
WORK_ROOT_OVERRIDE="books/hou-han-shu/work/quadrilingual/parts/part-01/parallel-json" \
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "hou-han-shu" "$SESSION"
