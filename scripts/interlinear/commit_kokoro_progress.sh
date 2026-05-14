#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/kokoro/work/bilingual/chunks/manifest.json"
chunk_dir="books/kokoro/work/bilingual/interlinear/chunks"
tracked_dir="data/interlinear/kokoro/chunks"
progress_json="data/interlinear/kokoro/progress.json"

python scripts/interlinear/sync_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-dir "$tracked_dir" \
  --progress-json "$progress_json"

git add "$tracked_dir" "$progress_json"

if git diff --cached --quiet -- data/interlinear/kokoro; then
  echo "No tracked Kokoro progress changes to commit."
  exit 0
fi

last_valid="$(python - <<'PY'
import json
from pathlib import Path
data=json.loads(Path("data/interlinear/kokoro/progress.json").read_text(encoding="utf-8"))
print(data.get("last_valid") or "no-chunk")
PY
)"

git commit -m "Update Kokoro interlinear progress ${last_valid}" -- data/interlinear/kokoro
