#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="books/kokoro/work/bilingual/chunks/manifest.json"
chunks_jsonl="books/kokoro/work/bilingual/chunks/chunks.jsonl"
chunk_dir="books/kokoro/work/bilingual/interlinear/chunks"
tracked_dir="data/interlinear/kokoro/chunks"
progress_json="data/interlinear/kokoro/progress.json"
zh_pdf="build/interlinear-block/心（こころ）.pdf"
zh_build_pdf="build/interlinear-block/book.pdf"
jp_pdf="build/interlinear-jp-main/こころ（心）.pdf"
jp_build_pdf="build/interlinear-jp-main/book.pdf"

python scripts/interlinear/sync_interlinear_progress.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_dir" \
  --output-dir "$tracked_dir" \
  --progress-json "$progress_json"

git add "$tracked_dir" "$progress_json" "$manifest" "$chunks_jsonl" "$chunk_dir"
for pdf in "$zh_pdf" "$zh_build_pdf" "$jp_pdf" "$jp_build_pdf"; do
  if [[ -f "$pdf" ]]; then
    git add "$pdf"
  fi
done

if git diff --cached --quiet -- data/interlinear/kokoro books/kokoro/work/bilingual build/interlinear-block build/interlinear-jp-main; then
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

git commit -m "Update Kokoro interlinear progress ${last_valid}" -- \
  data/interlinear/kokoro \
  books/kokoro/work/bilingual \
  build/interlinear-block \
  build/interlinear-jp-main
