#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prompt_tools/interlinear-book/run-book-pipeline.sh [options]

Convert an EPUB to cleaned Markdown, split it into paragraph chunks, ask one
resumable Codex session to create interlinear JSON chunk by chunk, assemble the
JSON, validate it, compile the pocket PDF, and commit tracked book changes.

Options:
  --epub <path>             EPUB input (default: sources/心.epub)
  --book-id <id>            stable book id (default: kokoro)
  --title-zh <text>         Chinese book title (default: 心)
  --title-zh-reading <pin>  pinyin for title (default: xīn)
  --title-ja <text>         Japanese title (default: 心)
  --title-ja-reading <txt>  furigana for title (default: こころ)
  --start-heading <text>    first Markdown heading to keep (default: 总序)
  --max-chars <n>           max source characters per chunk (default: 1800)
  --model <name>            Codex model (default: gpt-5.5)
  --reasoning <level>       low|medium|high|xhigh (default: high)
  --max-chunks <n>          process only first n chunks; 0 means all
  --start-index <n>         start at 1-based chunk index (default: 1)
  --skip-codex              only convert/split/assemble existing chunks
  --resume-last             resume newest Codex session for first missing chunk
  --no-commit               skip git commit at the end
  -h, --help                show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
epub="sources/心.epub"
book_id="kokoro"
title_zh="心"
title_zh_reading="xīn"
title_ja="心"
title_ja_reading="こころ"
start_heading="总序"
max_chars=1800
model="${ZHJPBOOK_CODEX_MODEL:-gpt-5.5}"
reasoning="${ZHJPBOOK_CODEX_REASONING:-high}"
max_chunks=0
start_index=1
skip_codex=0
resume_last=0
do_commit=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --epub) epub="${2:-}"; shift 2 ;;
    --book-id) book_id="${2:-}"; shift 2 ;;
    --title-zh) title_zh="${2:-}"; shift 2 ;;
    --title-zh-reading) title_zh_reading="${2:-}"; shift 2 ;;
    --title-ja) title_ja="${2:-}"; shift 2 ;;
    --title-ja-reading) title_ja_reading="${2:-}"; shift 2 ;;
    --start-heading) start_heading="${2:-}"; shift 2 ;;
    --max-chars) max_chars="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --reasoning) reasoning="${2:-}"; shift 2 ;;
    --max-chunks) max_chunks="${2:-0}"; shift 2 ;;
    --start-index) start_index="${2:-1}"; shift 2 ;;
    --skip-codex) skip_codex=1; shift ;;
    --resume-last) resume_last=1; shift ;;
    --no-commit) do_commit=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

cd "$root"

raw_md="books/$book_id/markdown/book.raw.md"
clean_md="books/$book_id/markdown/book.md"
work_dir="books/$book_id/work"
chunks_jsonl="$work_dir/chunks/chunks.jsonl"
manifest="$work_dir/chunks/manifest.json"
chunk_json_dir="$work_dir/interlinear/chunks"
assembled_json="data/interlinear/$book_id/assembled/current.json"

mkdir -p "books/$book_id/markdown" "$work_dir" "$chunk_json_dir" "$(dirname "$assembled_json")"

python scripts/books/epub_to_markdown.py "$epub" \
  --raw-output "$raw_md" \
  --clean-output "$clean_md" \
  --start-heading "$start_heading"

python scripts/interlinear/chunk_markdown_book.py "$clean_md" \
  --book-id "$book_id" \
  --chunks-jsonl "$chunks_jsonl" \
  --manifest "$manifest" \
  --max-chars "$max_chars"

if [[ "$skip_codex" -eq 0 ]]; then
  codex_worker_cmd=(
    python scripts/interlinear/codex_chunk_worker.py
    --chunks-jsonl "$chunks_jsonl" \
    --output-dir "$chunk_json_dir" \
    --work-dir "$work_dir/codex" \
    --model "$model" \
    --reasoning "$reasoning" \
    --max-chunks "$max_chunks" \
    --start-index "$start_index"
  )
  if [[ "$resume_last" -eq 1 ]]; then
    codex_worker_cmd+=(--resume-last)
  fi
  "${codex_worker_cmd[@]}"
fi

python scripts/interlinear/assemble_chunk_json.py \
  --manifest "$manifest" \
  --chunk-dir "$chunk_json_dir" \
  --output "$assembled_json" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --source-markdown "$clean_md" \
  --source-epub "$epub"

python scripts/interlinear/validate_interlinear_json.py "$assembled_json"
make interlinear INTERLINEAR_DATA="$assembled_json"

if [[ "$do_commit" -eq 1 ]]; then
  git add .gitignore Makefile README.md scripts prompt_tools books/"$book_id"/markdown data/interlinear/"$book_id"/assembled
  if ! git diff --cached --quiet; then
    git commit -m "Add $book_id interlinear book pipeline output"
  else
    echo "No tracked changes to commit."
  fi
fi

echo "Markdown: $clean_md"
echo "JSON:     $assembled_json"
echo "PDF:      build/interlinear-block/book.pdf"
