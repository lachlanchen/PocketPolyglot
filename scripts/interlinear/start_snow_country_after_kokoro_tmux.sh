#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-snow-country-after-kokoro}"
poll_seconds="${POLL_SECONDS:-600}"
snow_session="${SNOW_SESSION:-zhjpbook-snow-country-json}"
script_path="$root/scripts/interlinear/start_snow_country_after_kokoro_tmux.sh"
log_dir="books/snow-country/work/logs"
mkdir -p "$log_dir"

if [[ "${2:-}" != "--run" && "${1:-}" != "--run" ]]; then
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "tmux wait session already exists: $session"
    exit 0
  fi
  tmux new-session -d -s "$session" -n wait-kokoro \
    "POLL_SECONDS='$poll_seconds' SNOW_SESSION='$snow_session' bash '$script_path' --run 2>&1 | tee -a '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"
  echo "tmux wait session: $session"
  echo "snow session: $snow_session"
  echo "poll_seconds: $poll_seconds"
  exit 0
fi

progress_value() {
  awk -F= -v key="$1" '$1 == key {print $2}' <<<"$2"
}

kokoro_progress() {
  python scripts/interlinear/report_interlinear_progress.py \
    --manifest books/kokoro/work/bilingual/chunks/manifest.json \
    --chunk-dir books/kokoro/work/bilingual/interlinear/chunks
}

kokoro_dirty() {
  git status --short -- \
    books/kokoro/work/bilingual/review-backfix-state.json \
    books/kokoro/work/bilingual/interlinear/chunks \
    data/interlinear/kokoro \
    build/interlinear-block/心（こころ）.pdf \
    build/interlinear-jp-main/こころ（心）.pdf
}

echo "waiting for Kokoro before Snow Country: $(date -Is)"
while true; do
  progress="$(kokoro_progress || true)"
  manifest_chunks="$(progress_value manifest_chunks "$progress")"
  valid_chunks="$(progress_value valid_chunks "$progress")"
  dirty="$(kokoro_dirty || true)"

  echo
  echo "===== $(date -Is) ====="
  echo "$progress"
  if tmux has-session -t zhjpbook-parallel-json 2>/dev/null; then
    echo "kokoro_session=active"
  else
    echo "kokoro_session=missing"
  fi
  if [[ -n "$dirty" ]]; then
    echo "kokoro_dirty=yes"
    echo "$dirty" | sed -n '1,80p'
  else
    echo "kokoro_dirty=no"
  fi

  if [[ -n "$manifest_chunks" && "$manifest_chunks" == "$valid_chunks" ]] \
    && ! tmux has-session -t zhjpbook-parallel-json 2>/dev/null \
    && [[ -z "$dirty" ]]; then
    echo "Kokoro is complete and clean; preparing and starting Snow Country."
    bash scripts/interlinear/prepare_snow_country_sources.sh
    START_INDEX="${START_INDEX:-1}" WORKERS="${WORKERS:-10}" MERGE_INTERVAL="${MERGE_INTERVAL:-180}" \
      MODEL="${MODEL:-gpt-5.5}" REASONING="${REASONING:-xhigh}" \
      bash scripts/interlinear/start_snow_country_parallel_json_tmux.sh "$snow_session"
    exit 0
  fi

  sleep "$poll_seconds"
done
