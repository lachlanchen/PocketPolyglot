#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prompt_tools/interlinear-book/run-bilingual-book-pipeline.sh [options]

Convert Chinese and Japanese EPUB/Markdown sources into a Chinese-main,
Japanese-original-comment interlinear pocket book. The worker uses fresh
isolated Codex calls and processes chunks in order.

Options:
  --zh-epub <path>          Chinese EPUB input (default: sources/心.epub)
  --jp-epub <path>          Japanese anthology EPUB input
  --book-id <id>            stable book id (default: kokoro)
  --jp-source-id <id>       Japanese full Markdown folder id (default: natsume-complete)
  --title-zh <text>         Chinese book title (default: 心)
  --title-zh-reading <pin>  pinyin for title (default: xīn)
  --title-ja <text>         Japanese title (default: こころ)
  --title-ja-reading <txt>  furigana for title (default: こころ)
  --zh-start-heading <text> source section heading in Chinese Markdown (default: 心)
  --jp-start-heading <text> source section heading in Japanese Markdown
  --chunk-mode <mode>       paragraph|size (default: paragraph)
  --max-chars <n>           max Chinese source characters per chunk in size mode (default: 450)
  --reference-scope <scope> chapter|subsection|section JP context (default: chapter)
  --artifact-dir <path>     reusable paragraph artifact store
  --model <name>            Codex model (default: gpt-5.5)
  --reasoning <level>       low|medium|high|xhigh (default: xhigh)
  --max-chunks <n>          process only first n chunks; 0 means all
  --start-index <n>         start at 1-based chunk index (default: 1)
  --output-pdf <path>       named PDF path (default: build/interlinear-block/<title>.pdf)
  --skip-codex              only convert/split/assemble existing chunks
  --no-hydrate              do not prefill chunks from paragraph artifacts
  --no-compile-each-chunk   do not compile partial preview PDF after each chunk
  --resume-last             accepted for old callers; bilingual calls stay isolated
  --no-commit               skip git commit at the end
  -h, --help                show help
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
zh_epub="sources/心.epub"
jp_epub="sources/夏目 漱石 作品全集.epub"
book_id="kokoro"
jp_source_id="natsume-complete"
title_zh="心"
title_zh_reading="xīn"
title_ja="こころ"
title_ja_reading="こころ"
zh_start_heading="心"
jp_start_heading="第25章 こころ (新字新仮名)"
chunk_mode="paragraph"
max_chars=450
reference_scope="chapter"
artifact_dir=""
model="${ZHJPBOOK_CODEX_MODEL:-gpt-5.5}"
reasoning="${ZHJPBOOK_CODEX_REASONING:-xhigh}"
max_chunks=0
start_index=1
output_pdf=""
skip_codex=0
hydrate=1
compile_each_chunk=1
resume_last=0
do_commit=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --zh-epub) zh_epub="${2:-}"; shift 2 ;;
    --jp-epub) jp_epub="${2:-}"; shift 2 ;;
    --book-id) book_id="${2:-}"; shift 2 ;;
    --jp-source-id) jp_source_id="${2:-}"; shift 2 ;;
    --title-zh) title_zh="${2:-}"; shift 2 ;;
    --title-zh-reading) title_zh_reading="${2:-}"; shift 2 ;;
    --title-ja) title_ja="${2:-}"; shift 2 ;;
    --title-ja-reading) title_ja_reading="${2:-}"; shift 2 ;;
    --zh-start-heading) zh_start_heading="${2:-}"; shift 2 ;;
    --jp-start-heading) jp_start_heading="${2:-}"; shift 2 ;;
    --chunk-mode) chunk_mode="${2:-}"; shift 2 ;;
    --max-chars) max_chars="${2:-}"; shift 2 ;;
    --reference-scope) reference_scope="${2:-}"; shift 2 ;;
    --artifact-dir) artifact_dir="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --reasoning) reasoning="${2:-}"; shift 2 ;;
    --max-chunks) max_chunks="${2:-0}"; shift 2 ;;
    --start-index) start_index="${2:-1}"; shift 2 ;;
    --output-pdf) output_pdf="${2:-}"; shift 2 ;;
    --skip-codex) skip_codex=1; shift ;;
    --no-hydrate) hydrate=0; shift ;;
    --no-compile-each-chunk) compile_each_chunk=0; shift ;;
    --resume-last) resume_last=1; shift ;;
    --no-commit) do_commit=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

cd "$root"

zh_raw_md="books/$book_id/markdown/book.raw.md"
zh_clean_md="books/$book_id/markdown/book.md"
zh_section_md="books/$book_id/markdown/zh.md"
jp_raw_md="books/$jp_source_id/markdown/book.raw.md"
jp_clean_md="books/$jp_source_id/markdown/book.md"
jp_section_md="books/$book_id/markdown/ja.section.md"
jp_markdown="books/$book_id/markdown/ja.md"
work_dir="books/$book_id/work/bilingual"
chunks_jsonl="$work_dir/chunks/chunks.jsonl"
manifest="$work_dir/chunks/manifest.json"
chunk_json_dir="$work_dir/interlinear/chunks"
assembled_json="data/interlinear/$book_id/assembled/current.json"
preview_json="$work_dir/preview/$book_id.partial.json"
artifact_dir="${artifact_dir:-data/interlinear/$book_id/artifacts/paragraphs}"
if [[ -z "$output_pdf" ]]; then
  if [[ "$title_zh" == "$title_ja" ]]; then
    output_pdf="build/interlinear-block/${title_zh}.pdf"
  else
    output_pdf="build/interlinear-block/${title_zh}（${title_ja}）.pdf"
  fi
fi

mkdir -p "books/$book_id/markdown" "books/$jp_source_id/markdown" "$work_dir" "$chunk_json_dir" "$(dirname "$assembled_json")"

python scripts/books/epub_to_markdown.py "$zh_epub" \
  --raw-output "$zh_raw_md" \
  --clean-output "$zh_clean_md" \
  --start-heading 总序

python scripts/books/epub_to_markdown.py "$jp_epub" \
  --raw-output "$jp_raw_md" \
  --clean-output "$jp_clean_md"

python scripts/books/extract_markdown_section.py "$zh_clean_md" \
  --start-heading "$zh_start_heading" \
  --output "$zh_section_md"

python scripts/books/extract_markdown_section.py "$jp_clean_md" \
  --start-heading "$jp_start_heading" \
  --output "$jp_section_md"

python scripts/books/normalize_kokoro_jp_markdown.py "$jp_section_md" \
  --output "$jp_markdown" \
  --title "$title_ja"

python scripts/interlinear/chunk_bilingual_markdown_book.py \
  --zh-markdown "$zh_section_md" \
  --ja-markdown "$jp_markdown" \
  --book-id "$book_id" \
  --chunks-jsonl "$chunks_jsonl" \
  --manifest "$manifest" \
  --chunk-mode "$chunk_mode" \
  --reference-scope "$reference_scope" \
  --max-chars "$max_chars"

if [[ "$hydrate" -eq 1 ]]; then
  python scripts/interlinear/hydrate_chunks_from_artifacts.py \
    --chunks-jsonl "$chunks_jsonl" \
    --artifact-dir "$artifact_dir" \
    --output-dir "$chunk_json_dir" \
    --require-feature translation \
    --require-feature zh_ruby \
    --require-feature ja_ruby \
    --require-feature grammar
fi

if [[ "$skip_codex" -eq 0 ]]; then
  compile_cmd=(
    bash "$root/scripts/interlinear/compile_interlinear_book.sh"
    --manifest "$manifest"
    --chunk-dir "$chunk_json_dir"
    --output-json "$preview_json"
    --book-title-zh "$title_zh"
    --book-title-zh-reading "$title_zh_reading"
    --book-title-ja "$title_ja"
    --book-title-ja-reading "$title_ja_reading"
    --source-markdown "$zh_section_md"
    --source-epub "$zh_epub"
    --source-markdown-ja "$jp_markdown"
    --source-epub-ja "$jp_epub"
    --output-pdf "$output_pdf"
    --allow-missing
  )
  printf -v compile_cmd_text '%q ' "${compile_cmd[@]}"
  after_chunk_command="$compile_cmd_text"
  if [[ "$do_commit" -eq 1 ]]; then
    commit_cmd=(
      bash "$root/scripts/interlinear/commit_interlinear_progress.sh"
      --book-id "$book_id"
      --manifest "$manifest"
      --chunks-jsonl "$chunks_jsonl"
      --chunk-dir "$chunk_json_dir"
      --artifact-dir "$artifact_dir"
      --pdf "$output_pdf"
      --pdf "build/interlinear-block/book.pdf"
    )
    printf -v commit_cmd_text '%q ' "${commit_cmd[@]}"
    after_chunk_command="${compile_cmd_text}&& ${commit_cmd_text}"
  fi

  codex_worker_cmd=(
    python scripts/interlinear/codex_bilingual_chunk_worker.py
    --chunks-jsonl "$chunks_jsonl" \
    --output-dir "$chunk_json_dir" \
    --work-dir "$work_dir/codex" \
    --model "$model" \
    --reasoning "$reasoning" \
    --max-chunks "$max_chunks" \
    --start-index "$start_index"
  )
  if [[ "$compile_each_chunk" -eq 1 ]]; then
    codex_worker_cmd+=(--after-chunk-command "$after_chunk_command")
  fi
  if [[ "$resume_last" -eq 1 ]]; then
    codex_worker_cmd+=(--resume-last)
  fi
  "${codex_worker_cmd[@]}"
fi

bash scripts/interlinear/compile_interlinear_book.sh \
  --manifest "$manifest" \
  --chunk-dir "$chunk_json_dir" \
  --output-json "$assembled_json" \
  --book-title-zh "$title_zh" \
  --book-title-zh-reading "$title_zh_reading" \
  --book-title-ja "$title_ja" \
  --book-title-ja-reading "$title_ja_reading" \
  --source-markdown "$zh_section_md" \
  --source-epub "$zh_epub" \
  --source-markdown-ja "$jp_markdown" \
  --source-epub-ja "$jp_epub" \
  --output-pdf "$output_pdf"

if [[ "$do_commit" -eq 1 ]]; then
  bash scripts/interlinear/commit_interlinear_progress.sh \
    --book-id "$book_id" \
    --manifest "$manifest" \
    --chunks-jsonl "$chunks_jsonl" \
    --chunk-dir "$chunk_json_dir" \
    --artifact-dir "$artifact_dir" \
    --pdf "$output_pdf" \
    --pdf "build/interlinear-block/book.pdf"

  git add .gitignore Makefile README.md scripts prompt_tools books/"$book_id"/markdown books/"$jp_source_id"/markdown/book.md data/interlinear/"$book_id"/assembled
  if ! git diff --cached --quiet; then
    git commit -m "Build bilingual $book_id interlinear source"
  else
    echo "No tracked changes to commit."
  fi
fi

echo "Chinese Markdown:  $zh_section_md"
echo "Japanese Markdown: $jp_markdown"
echo "JSON:              $assembled_json"
echo "PDF:               $output_pdf"
