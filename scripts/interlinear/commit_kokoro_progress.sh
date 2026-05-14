#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

exec bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id kokoro \
  --pdf "build/interlinear-block/心（こころ）.pdf" \
  --pdf "build/interlinear-block/book.pdf" \
  --pdf "build/interlinear-jp-main/こころ（心）.pdf" \
  --pdf "build/interlinear-jp-main/book.pdf" \
  --message-prefix "Update Kokoro interlinear progress"
