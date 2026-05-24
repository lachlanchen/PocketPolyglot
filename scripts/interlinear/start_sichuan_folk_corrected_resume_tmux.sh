#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
reviewed_chunk_dir="${SICHUAN_FOLK_CHUNK_DIR:-books/$book_id/work/bilingual/reviewed-v2/chunks}"
writer_session="${WRITER_SESSION:-zhjpbook-sichuan-folk-json}"
sanitizer_session="${SANITIZER_SESSION:-zhjpbook-sichuan-folk-sanitizer}"
monitor_session="${MONITOR_SESSION:-zhjpbook-sichuan-folk-monitor}"
enable_legacy_sanitizer="${ENABLE_LEGACY_SANITIZER:-0}"

bash scripts/interlinear/prepare_sichuan_folk_sources.sh

report="$(
  python scripts/interlinear/report_interlinear_progress.py \
    --manifest "books/$book_id/work/bilingual/chunks/manifest.json" \
    --chunk-dir "$reviewed_chunk_dir"
)"
echo "$report"
first_missing="$(awk -F= '/^first_missing=/ {print $2}' <<<"$report")"
if [[ -n "$first_missing" && "$first_missing" =~ -chunk-([0-9]+)$ ]]; then
  resume_index="$((10#${BASH_REMATCH[1]}))"
else
  resume_index=1
fi
sanitize_end="$((resume_index - 1))"

if [[ "$enable_legacy_sanitizer" != "1" ]]; then
  echo "legacy sanitizer skipped; async review-v2 is the repair/sanitize path"
elif [[ "$sanitize_end" -ge 1 ]]; then
  if ! tmux has-session -t "$sanitizer_session" 2>/dev/null; then
    START_INDEX=1 \
    END_INDEX="$sanitize_end" \
    MODEL="$model" \
    REASONING="$reasoning" \
    RETRY_FAILED=1 \
    bash scripts/interlinear/start_sichuan_folk_sanitizer_tmux.sh "$sanitizer_session"
  else
    echo "sanitizer already running: $sanitizer_session"
  fi
else
  echo "sanitizer skipped: no completed range before resume_index=$resume_index"
fi

if ! tmux has-session -t "$writer_session" 2>/dev/null; then
  START_INDEX="$resume_index" \
  SICHUAN_FOLK_CHUNK_DIR="$reviewed_chunk_dir" \
  MODEL="$model" \
  REASONING="$reasoning" \
  RETRY_FAILED=1 \
  bash scripts/interlinear/start_sichuan_folk_parallel_json_tmux.sh "$writer_session"
else
  echo "writer already running: $writer_session"
fi

if ! tmux has-session -t "$monitor_session" 2>/dev/null; then
  BOOK_ID="$book_id" \
  MONITOR_SESSION="$monitor_session" \
  WORKER_SESSION="$writer_session" \
  REVIEW_SESSION="$writer_session" \
  INTERVAL_SECONDS="${INTERVAL_SECONDS:-1800}" \
  STALL_SECONDS="${STALL_SECONDS:-3600}" \
  COMPILE_COMMAND="SICHUAN_FOLK_CHUNK_DIR=$reviewed_chunk_dir bash scripts/interlinear/compile_sichuan_folk_both_previews.sh" \
  START_COMMAND="SICHUAN_FOLK_CHUNK_DIR=$reviewed_chunk_dir MODEL=$model REASONING=$reasoning RETRY_FAILED=1 bash scripts/interlinear/start_sichuan_folk_parallel_json_tmux.sh $writer_session" \
  bash scripts/interlinear/start_interlinear_monitor_tmux.sh "$book_id"
else
  echo "monitor already running: $monitor_session"
fi

echo "resume_index: $resume_index"
echo "sanitize_end: $sanitize_end"
echo "model: $model"
echo "reasoning: $reasoning"
