#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/commit_interlinear_progress.sh --book-id <id> [options]

Sync valid chunk JSON into tracked data/interlinear/<id>/, stage only the
interlinear progress artifacts, and commit them if they changed.

Options:
  --book-id <id>          stable book id, e.g. kokoro
  --manifest <path>       chunk manifest
  --chunks-jsonl <path>   chunk source JSONL
  --chunk-dir <path>      generated chunk JSON directory
  --tracked-dir <path>    tracked chunk output directory
  --progress-json <path>  tracked progress JSON
  --artifact-dir <path>   tracked paragraph artifact directory
  --pdf <path>            generated PDF to include; may be repeated
  --extra <path>          extra tracked artifact to include if it exists; may be repeated
  --message-prefix <text> commit message prefix
  -h, --help              show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
book_id=""
manifest=""
chunks_jsonl=""
chunk_dir=""
tracked_dir=""
progress_json=""
artifact_dir=""
message_prefix=""
pdfs=()
extras=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --book-id) book_id="${2:-}"; shift 2 ;;
    --manifest) manifest="${2:-}"; shift 2 ;;
    --chunks-jsonl) chunks_jsonl="${2:-}"; shift 2 ;;
    --chunk-dir) chunk_dir="${2:-}"; shift 2 ;;
    --tracked-dir) tracked_dir="${2:-}"; shift 2 ;;
    --progress-json) progress_json="${2:-}"; shift 2 ;;
    --artifact-dir) artifact_dir="${2:-}"; shift 2 ;;
    --pdf) pdfs+=("${2:-}"); shift 2 ;;
    --extra) extras+=("${2:-}"); shift 2 ;;
    --message-prefix) message_prefix="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$book_id" ]]; then
  echo "Missing --book-id" >&2
  usage >&2
  exit 1
fi

cd "$root"

work_dir="books/$book_id/work/bilingual"
manifest="${manifest:-$work_dir/chunks/manifest.json}"
chunks_jsonl="${chunks_jsonl:-$work_dir/chunks/chunks.jsonl}"
chunk_dir="${chunk_dir:-$work_dir/interlinear/chunks}"
tracked_dir="${tracked_dir:-data/interlinear/$book_id/chunks}"
progress_json="${progress_json:-data/interlinear/$book_id/progress.json}"
artifact_dir="${artifact_dir:-data/interlinear/$book_id/artifacts/paragraphs}"
message_prefix="${message_prefix:-Update ${book_id} interlinear progress}"

for required_path in "$manifest" "$chunks_jsonl" "$chunk_dir"; do
  if [[ ! -e "$required_path" ]]; then
    echo "Missing required path: $required_path" >&2
    exit 1
  fi
done

python scripts/interlinear/sync_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-dir "$tracked_dir" \
  --progress-json "$progress_json"

python scripts/interlinear/export_paragraph_artifacts.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-dir "$artifact_dir"

pathspecs=("$tracked_dir" "$progress_json" "$artifact_dir" "$manifest" "$chunks_jsonl")
for pdf in "${pdfs[@]}"; do
  if [[ -f "$pdf" ]]; then
    pathspecs+=("$pdf")
  fi
done
for extra in "${extras[@]}"; do
  if [[ -e "$extra" ]]; then
    pathspecs+=("$extra")
  fi
done

filtered_pathspecs=()
for pathspec in "${pathspecs[@]}"; do
  if git ls-files --error-unmatch "$pathspec" >/dev/null 2>&1; then
    filtered_pathspecs+=("$pathspec")
  elif git check-ignore -q -- "$pathspec"; then
    echo "Skipping ignored untracked path: $pathspec"
  else
    filtered_pathspecs+=("$pathspec")
  fi
done

git add -- "${filtered_pathspecs[@]}"
echo "Progress git status:"
git status --short --untracked-files=no -- "${filtered_pathspecs[@]}" || true

if git diff --cached --quiet -- "${filtered_pathspecs[@]}"; then
  echo "No tracked ${book_id} progress changes to commit."
  exit 0
fi

last_valid="$(
  python - "$progress_json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("last_valid") or "no-chunk")
PY
)"

git commit -m "${message_prefix} ${last_valid}" -- "${filtered_pathspecs[@]}"
