#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/ocr/start_sanxingdui_ocr_review_tmux.sh [session]

Start a Codex OCR-review worker for Sanxingdui raw OCR Markdown. It polls
books/sanxingdui/markdown/*.ocr.md and writes reviewed page JSON plus assembled
*.reviewed.md files.

Environment:
  REVIEW_MODEL=gpt-5.5
  REVIEW_REASONING=high
  REVIEW_POLL_SECONDS=300
  REVIEW_MAX_PAGES=0
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-sanxingdui-ocr-review}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

work_root="books/sanxingdui/work/ocr-review"
log_dir="books/sanxingdui/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$log_dir"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
export CODEX_USAGE_LIMIT_WAIT_SECONDS="\${CODEX_USAGE_LIMIT_WAIT_SECONDS:-3600}"
python scripts/ocr/codex_review_ocr_pages.py \\
  --model '${REVIEW_MODEL:-gpt-5.5}' \\
  --reasoning '${REVIEW_REASONING:-high}' \\
  --poll-seconds '${REVIEW_POLL_SECONDS:-300}' \\
  --max-pages '${REVIEW_MAX_PAGES:-0}'
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n review "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "run_script: $run_script"
