#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_failed_retry_then_single_worker.sh <book-id>

Wait for or start a one-worker retry pass over failed quadrilingual chunks, then
start the normal one-worker quadrilingual run once the failed queue is clear.

Environment:
  RETRY_SESSION=zhjpbook-<book-id>-failed-one
  FULL_SESSION=zhjpbook-<book-id>-one
  MODEL=gpt-5.5
  REASONING=low
  RETRY_ROUNDS=3
  SUPERVISOR_SLEEP_SECONDS=120
  MERGE_INTERVAL=60
  COMPILE_INTERVAL_SECONDS=900
  FULL_COMPILE_INTERVAL_SECONDS=3600
  CODEX_TIMEOUT_SECONDS=1800
  CLAIM_TTL_SECONDS=3600
USAGE
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
raw_chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
candidate_dir="books/$book_id/work/quadrilingual/parallel-json/candidates"
failed_dir="$candidate_dir/failed"
retry_dir="books/$book_id/work/quadrilingual/retry-failed"

retry_session="${RETRY_SESSION:-zhjpbook-${book_id}-failed-one}"
full_session="${FULL_SESSION:-zhjpbook-${book_id}-one}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-low}"
retry_rounds="${RETRY_ROUNDS:-3}"
sleep_seconds="${SUPERVISOR_SLEEP_SECONDS:-120}"
merge_interval="${MERGE_INTERVAL:-60}"
retry_compile_interval="${COMPILE_INTERVAL_SECONDS:-900}"
full_compile_interval="${FULL_COMPILE_INTERVAL_SECONDS:-3600}"
timeout="${CODEX_TIMEOUT_SECONDS:-1800}"
claim_ttl="${CLAIM_TTL_SECONDS:-3600}"

count_failed() {
  find "$failed_dir" -maxdepth 1 -type f -name "${book_id}-chunk-*.json" 2>/dev/null | wc -l
}

write_retry_subset() {
  python - "$chunks_jsonl" "$manifest" "$failed_dir" "$retry_dir" <<'PY'
import json
import sys
from pathlib import Path

chunks_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
failed_dir = Path(sys.argv[3])
retry_dir = Path(sys.argv[4])
retry_dir.mkdir(parents=True, exist_ok=True)

failed_ids = sorted(path.stem for path in failed_dir.glob("*.json"))
chunks = []
with chunks_path.open("r", encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if line:
            chunks.append(json.loads(line))
by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
retry = [by_id[chunk_id] for chunk_id in failed_ids if chunk_id in by_id]

(retry_dir / "chunks.jsonl").write_text(
    "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in retry),
    encoding="utf-8",
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["status"] = "retry_failed_subset"
manifest["source_manifest"] = str(manifest_path)
manifest["chunk_count"] = len(retry)
manifest["chunks"] = [
    {
        "chunk_id": chunk["chunk_id"],
        "chapter_number": chunk.get("chapter_number"),
        "chapter_title": chunk.get("chapter_title"),
        "source_location": chunk.get("source_location"),
    }
    for chunk in retry
]
(retry_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(len(retry))
PY
}

start_retry_session() {
  local retry_count
  retry_count="$(write_retry_subset)"
  if [[ "$retry_count" == "0" ]]; then
    echo "retry_skipped=no_failed_chunks"
    return 0
  fi
  if tmux has-session -t "=$retry_session" 2>/dev/null; then
    echo "retry_session_already_running=$retry_session"
    return 0
  fi
  WORKERS=1 \
    MODEL="$model" \
    REASONING="$reasoning" \
    WORKER_PREFIX="${book_id}-failed-worker" \
    MERGE_INTERVAL="$merge_interval" \
    COMPILE_INTERVAL_SECONDS="$retry_compile_interval" \
    CODEX_TIMEOUT_SECONDS="$timeout" \
    CLAIM_TTL_SECONDS="$claim_ttl" \
    RETRY_FAILED=1 \
    FAILED_RETRY_AGE_SECONDS=0 \
    CHUNKS_JSONL_OVERRIDE="$retry_dir/chunks.jsonl" \
    MANIFEST_OVERRIDE="$retry_dir/manifest.json" \
    bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "$book_id" "$retry_session"
}

report_retry_progress() {
  if [[ -f "$retry_dir/manifest.json" && -f "$retry_dir/chunks.jsonl" ]]; then
    python scripts/interlinear/report_quadrilingual_progress.py \
      --manifest "$retry_dir/manifest.json" \
      --chunks-jsonl "$retry_dir/chunks.jsonl" \
      --chunk-dir "$raw_chunk_dir" || true
  fi
}

round=1
while [[ "$round" -le "$retry_rounds" ]]; do
  failed_before="$(count_failed)"
  echo "retry_round=$round failed_before=$failed_before"
  if [[ "$failed_before" == "0" ]]; then
    break
  fi
  start_retry_session
  while tmux has-session -t "=$retry_session" 2>/dev/null; do
    report_retry_progress
    echo "failed_now=$(count_failed)"
    sleep "$sleep_seconds"
  done
  report_retry_progress
  failed_after="$(count_failed)"
  echo "retry_round=$round failed_after=$failed_after"
  if [[ "$failed_after" == "0" ]]; then
    break
  fi
  if [[ "$failed_after" -ge "$failed_before" ]]; then
    echo "retry_stopped=no_failed_progress failed_before=$failed_before failed_after=$failed_after" >&2
    exit 2
  fi
  round=$((round + 1))
done

failed_remaining="$(count_failed)"
if [[ "$failed_remaining" != "0" ]]; then
  echo "failed_remaining=$failed_remaining; not starting full run yet" >&2
  exit 2
fi

if tmux has-session -t "=$full_session" 2>/dev/null; then
  echo "full_session_already_running=$full_session"
  exit 0
fi

WORKERS=1 \
  MODEL="$model" \
  REASONING="$reasoning" \
  WORKER_PREFIX="${book_id}-one-worker" \
  MERGE_INTERVAL="$merge_interval" \
  COMPILE_INTERVAL_SECONDS="$full_compile_interval" \
  CODEX_TIMEOUT_SECONDS="$timeout" \
  CLAIM_TTL_SECONDS="$claim_ttl" \
  RETRY_FAILED=1 \
  FAILED_RETRY_AGE_SECONDS=0 \
  bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "$book_id" "$full_session"
