#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

exec bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id kokoro \
  --pdf "build/kokoro/zh-main/color/心（こころ）.pdf" \
  --pdf "build/kokoro/zh-main/blackwhite/心（こころ）.pdf" \
  --pdf "build/kokoro/jp-main/color/こころ（心）.pdf" \
  --pdf "build/kokoro/jp-main/blackwhite/こころ（心）.pdf" \
  --extra "books/kokoro/work/bilingual/grammar-role-repair/state.json" \
  --extra "books/kokoro/work/bilingual/review-backfix-state.json" \
  --message-prefix "Update Kokoro interlinear progress"
