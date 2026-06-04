#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/ocr/start_sanxingdui_ocr_tmux.sh [session]

Start the Sanxingdui OCR pipeline in tmux. It builds searchable PDFs that
preserve the original figures, sidecar text, Markdown, and per-book status.

Environment:
  OCR_JOBS=4
  OCR_LANG=chi_sim+eng
  OCR_PSM=3
  OCR_PAGES=all
  OCR_FORCE=0
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-sanxingdui-ocr}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

work_root="books/sanxingdui/work/ocr"
log_dir="books/sanxingdui/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$log_dir"

force_arg=()
if [[ "${OCR_FORCE:-0}" == "1" ]]; then
  force_arg=(--force)
fi
force_flags="${force_arg[*]}"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
export PATH="\$HOME/.local/bin:\$PATH"
python scripts/ocr/run_sanxingdui_ocr_batch.py \\
  --jobs '${OCR_JOBS:-4}' \\
  --lang '${OCR_LANG:-chi_sim+eng}' \\
  --psm '${OCR_PSM:-3}' \\
  --pages '${OCR_PAGES:-all}' $force_flags
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n ocr "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "run_script: $run_script"
