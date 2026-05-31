#!/usr/bin/env bash
set -euo pipefail

exec bash scripts/interlinear/commit_interlinear_progress.sh \
  --book-id "sichuan-folk-stories-vol1" \
  --manifest "books/sichuan-folk-stories-vol1/work/bilingual/chunks/manifest.json" \
  --chunks-jsonl "books/sichuan-folk-stories-vol1/work/bilingual/chunks/chunks.jsonl" \
  --chunk-dir "${SICHUAN_FOLK_CHUNK_DIR:-books/sichuan-folk-stories-vol1/work/bilingual/reviewed-v2/chunks}" \
  --tracked-dir "data/interlinear/sichuan-folk-stories-vol1/chunks" \
  --progress-json "data/interlinear/sichuan-folk-stories-vol1/progress.json" \
  --artifact-dir "data/interlinear/sichuan-folk-stories-vol1/artifacts/paragraphs" \
  --pdf "build/sichuan-folk-stories-vol1/zh-main/color/中国民间故事集成四川卷上（日文注）.pdf" \
  --pdf "build/sichuan-folk-stories-vol1/zh-main/blackwhite/中国民间故事集成四川卷上（日文注）.pdf" \
  --pdf "build/sichuan-folk-stories-vol1/jp-main/color/中国民間故事集成四川巻上（中文注）.pdf" \
  --pdf "build/sichuan-folk-stories-vol1/jp-main/blackwhite/中国民間故事集成四川巻上（中文注）.pdf" \
  --extra "books/sichuan-folk-stories-vol1/markdown/zh.md" \
  --extra "assets/covers/sichuan-folk-stories-vol1" \
  --message-prefix "Update Sichuan Folk Stories interlinear progress"
