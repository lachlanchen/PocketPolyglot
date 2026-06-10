#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-world-literature-ocr}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux OCR session already exists: $session"
  exit 0
fi

log_dir="logs/world-literature-ocr"
mkdir -p "$log_dir"
log="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

target_args=()
if [[ -n "${OCR_TARGETS:-}" ]]; then
  read -r -a targets <<< "$OCR_TARGETS"
  for target in "${targets[@]}"; do
    target_args+=(--target "$target")
  done
fi

force_arg=()
if [[ "${FORCE_OCR:-0}" == "1" ]]; then
  force_arg=(--force)
fi

refresh_arg=()
if [[ "${REFRESH_PREPARED_BOOKS:-1}" == "0" ]]; then
  refresh_arg=(--no-refresh)
fi

tmux new-session -d -s "$session" -n ocr "\
cd '$root' && \
python -u scripts/ocr/world_literature_ocr_sources.py \
  --workers '${OCR_WORKERS:-6}' \
  --dpi '${OCR_DPI:-220}' \
  --pages '${OCR_PAGES:-all}' \
  ${target_args[*]} \
  ${force_arg[*]} \
  ${refresh_arg[*]} \
  2>&1 | tee -a '$log'"

echo "tmux OCR session: $session"
echo "log: $log"
echo "workers: ${OCR_WORKERS:-6}"
echo "dpi: ${OCR_DPI:-220}"
echo "pages: ${OCR_PAGES:-all}"
echo "targets: ${OCR_TARGETS:-all}"
