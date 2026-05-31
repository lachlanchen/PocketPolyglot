#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

exec bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id no-longer-human \
  --manifest "books/no-longer-human/work/bilingual/chunks/manifest.json" \
  --chunks-jsonl "books/no-longer-human/work/bilingual/chunks/chunks.jsonl" \
  --chunk-dir "${NO_LONGER_HUMAN_CHUNK_DIR:-books/no-longer-human/work/bilingual/reviewed/chunks}" \
  --pdf "build/no-longer-human/zh-main/color/人間失格（にんげんしっかく）.pdf" \
  --pdf "build/no-longer-human/zh-main/blackwhite/人間失格（にんげんしっかく）.pdf" \
  --pdf "build/no-longer-human/jp-main/color/人間失格（中文注）.pdf" \
  --pdf "build/no-longer-human/jp-main/blackwhite/人間失格（中文注）.pdf" \
  --extra "assets/covers/no-longer-human" \
  --message-prefix "Update No Longer Human interlinear progress"
