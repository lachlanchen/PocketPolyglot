#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

exec bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id snow-country \
  --manifest "books/snow-country/work/bilingual/chunks/manifest.json" \
  --chunks-jsonl "books/snow-country/work/bilingual/chunks/chunks.jsonl" \
  --chunk-dir "${SNOW_CHUNK_DIR:-books/snow-country/work/bilingual/reviewed/chunks}" \
  --pdf "build/interlinear-block/雪国（ゆきぐに）.pdf" \
  --pdf "build/interlinear-block/book.pdf" \
  --pdf "build/interlinear-jp-main/雪国（中文注）.pdf" \
  --pdf "build/interlinear-jp-main/book.pdf" \
  --message-prefix "Update Snow Country interlinear progress"
