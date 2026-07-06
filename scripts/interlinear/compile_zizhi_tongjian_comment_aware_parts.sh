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

for part in $parts; do
  for mode in "${modes[@]}"; do
    echo "==> $part $mode"
    bash scripts/interlinear/compile_zizhi_tongjian_comment_aware.sh \
      --part "$part" \
      --color-mode "$mode" \
      --skip-spans
  done
done
