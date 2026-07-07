#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_zizhi_tongjian_comment_aware_parts.sh [--color-mode color|blackwhite|both] [--parts "part-01 part-02"]

Builds the final six-part comment-aware Zizhi Tongjian edition.  The source
JSON is copied from the completed base Zizhi Tongjian project, and the PDF font
alignment sidecar is reused once it exists.

Environment:
  PARTS="part-01 part-02"  Override the part list.
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

color_mode="both"
parts="${PARTS:-part-01 part-02 part-03 part-04 part-05 part-06}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --color-mode) color_mode="$2"; shift 2 ;;
    --parts) parts="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

case "$color_mode" in
  color) modes=(color) ;;
  blackwhite) modes=(blackwhite) ;;
  both) modes=(color blackwhite) ;;
  *) echo "Unsupported color mode: $color_mode" >&2; exit 1 ;;
esac

bash scripts/interlinear/setup_zizhi_tongjian_comment_aware_project.sh

book_id="zizhi-tongjian-comment-aware"
plan="books/$book_id/book-plan.json"
full_manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
source_pdf="$(jq -r '.source_paths.commented_classical_source' "$plan")"
xml_cache="$(jq -r '.pdf_font_xml_cache' "$plan")"
sidecar="$(jq -r '.comment_sidecar' "$plan")"
span_report="$(jq -r '.comment_span_report' "$plan")"
repair_report="books/$book_id/work/comment-aware/comment-span-repair-report.json"

if [[ ! -s "$sidecar" ]]; then
  echo "==> building full comment sidecar once"
  python scripts/interlinear/build_zizhi_tongjian_comment_spans.py \
    --manifest "$full_manifest" \
    --chunks-jsonl "$chunks_jsonl" \
    --chunk-dir "$chunk_dir" \
    --source-pdf "$source_pdf" \
    --xml-cache "$xml_cache" \
    --output "$sidecar" \
    --report "$span_report"
fi

echo "==> repairing structural main-text spans"
python scripts/interlinear/repair_zizhi_tongjian_comment_sidecar.py \
  --chunks-jsonl "$chunks_jsonl" \
  --chunk-dir "$chunk_dir" \
  --sidecar "$sidecar" \
  --report "$repair_report"

for part in $parts; do
  for mode in "${modes[@]}"; do
    echo "==> $part $mode"
    ZIZHI_SKIP_SIDECAR_REPAIR=1 bash scripts/interlinear/compile_zizhi_tongjian_comment_aware.sh \
      --part "$part" \
      --color-mode "$mode" \
      --skip-spans
  done
done
