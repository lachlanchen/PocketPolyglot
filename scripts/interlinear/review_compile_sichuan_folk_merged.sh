#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
chunks="${ZHJPBOOK_MERGED_CHUNKS:-}"
if [[ -z "$chunks" ]]; then
  echo "No merged chunks to review."
  exit 0
fi

model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
retries="${REVIEW_RETRIES:-2}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"

python scripts/interlinear/review_backfix_interlinear_chunks.py \
  --chunks-jsonl "books/$book_id/work/bilingual/chunks/chunks.jsonl" \
  --chunk-dir "books/$book_id/work/bilingual/interlinear/chunks" \
  --work-dir "books/$book_id/work/bilingual/review-backfix" \
  --state-json "books/$book_id/work/bilingual/review-backfix-state.json" \
  --chunk-ids "$chunks" \
  --model "$model" \
  --reasoning "$reasoning" \
  --codex-timeout-seconds "$codex_timeout_seconds" \
  --retries "$retries"

COMMIT_PROGRESS=0 bash scripts/interlinear/compile_sichuan_folk_both_previews.sh

for pdf in \
  "build/$book_id/zh-main/color/中国民间故事集成四川卷上（日文注）.pdf" \
  "build/$book_id/zh-main/blackwhite/中国民间故事集成四川卷上（日文注）.pdf" \
  "build/$book_id/jp-main/color/中国民間故事集成四川巻上（中文注）.pdf" \
  "build/$book_id/jp-main/blackwhite/中国民間故事集成四川巻上（中文注）.pdf"
do
  if [[ ! -s "$pdf" ]]; then
    echo "Missing or empty PDF: $pdf" >&2
    exit 1
  fi
  pages="$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/ {print $2}')"
  if [[ -z "$pages" || "$pages" -lt 1 ]]; then
    echo "PDF has no readable page count: $pdf" >&2
    exit 1
  fi
  echo "pdf_ok $pdf pages=$pages"
done

bash scripts/interlinear/commit_sichuan_folk_progress.sh
