#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

src_book="zizhi-tongjian"
dst_book="zizhi-tongjian-comment-aware"

mkdir -p \
  "books/$dst_book/work/quadrilingual/chunks" \
  "books/$dst_book/work/quadrilingual/interlinear" \
  "books/$dst_book/work/comment-aware" \
  "books/$dst_book/work/pdf-font-map"

cp -a --reflink=auto \
  "books/$src_book/work/quadrilingual/chunks/manifest.json" \
  "books/$dst_book/work/quadrilingual/chunks/manifest.json"
cp -a --reflink=auto \
  "books/$src_book/work/quadrilingual/chunks/chunks.jsonl" \
  "books/$dst_book/work/quadrilingual/chunks/chunks.jsonl"

if [[ ! -d "books/$dst_book/work/quadrilingual/interlinear/chunks" ]]; then
  cp -a --reflink=auto \
    "books/$src_book/work/quadrilingual/interlinear/chunks" \
    "books/$dst_book/work/quadrilingual/interlinear/chunks"
fi

echo "copied JSON project: books/$dst_book"

