#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="${1:-}"
if [[ -z "$book_id" ]]; then
  echo "Usage: scripts/interlinear/commit_prepared_book_progress.sh <book-id>" >&2
  exit 1
fi

plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

title="$(jq -r '.book_title_zh // .book_id' "$plan")"
title_zh="$(jq -r '.book_title_zh' "$plan")"
title_ja="$(jq -r '.book_title_ja' "$plan")"
source_markdown="$(jq -r '.source_markdown' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
reviewed_dir="$(jq -r '.reviewed_chunk_dir' "$plan")"

extra_args=(
  --extra "$plan"
  --extra "$source_markdown"
  --extra "data/source-plan/japanese-literature-batch.json"
  --extra "build/$book_id/zh-main/color/${title_zh}（日文注）.tex"
  --extra "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.tex"
  --extra "build/$book_id/jp-main/color/${title_ja}（中文注）.tex"
  --extra "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.tex"
)
pdf_args=(
  --pdf "build/$book_id/zh-main/color/${title_zh}（日文注）.pdf"
  --pdf "build/$book_id/zh-main/blackwhite/${title_zh}（日文注・黑白）.pdf"
  --pdf "build/$book_id/jp-main/color/${title_ja}（中文注）.pdf"
  --pdf "build/$book_id/jp-main/blackwhite/${title_ja}（中文注・黑白）.pdf"
)

bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id "$book_id" \
  --manifest "$manifest" \
  --chunks-jsonl "$chunks_jsonl" \
  --chunk-dir "$reviewed_dir" \
  --tracked-dir "data/interlinear/$book_id/chunks" \
  --message-prefix "Update $title interlinear progress" \
  "${pdf_args[@]}" \
  "${extra_args[@]}"
