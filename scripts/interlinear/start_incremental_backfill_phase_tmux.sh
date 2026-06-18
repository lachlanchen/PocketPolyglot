#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

phase="${1:-phase-1-normal-english}"
case "$phase" in
  phase-1-normal-english|phase-2-shiji-en-ja-modern|phase-3-sishu-zhmodern-en-ja-modern) ;;
  *)
    echo "Unknown phase: $phase" >&2
    echo "Use one of: phase-1-normal-english, phase-2-shiji-en-ja-modern, phase-3-sishu-zhmodern-en-ja-modern" >&2
    exit 2
    ;;
esac

manifest="data/source-plan/incremental-backfill-phases/${phase}.json"
if [[ ! -f "$manifest" ]]; then
  python scripts/interlinear/prepare_incremental_en_modern_ja_tasks.py
  python scripts/interlinear/prepare_incremental_backfill_phase_manifests.py
fi

export MODEL="${MODEL:-gpt-5.5}"
export REASONING="${REASONING:-medium}"
export GLOBAL_MANIFEST="$manifest"
export WORK_DIR="${WORK_DIR:-books/_incremental-overlays/work/${phase}}"
export WORKERS="${WORKERS:-10}"

session="${2:-zhjpbook-backfill-${phase}}"
exec bash scripts/interlinear/start_incremental_overlay_tmux.sh "$session"
