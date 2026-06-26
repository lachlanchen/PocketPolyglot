#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-sanguozhi-pei-zhu}"
workers="${WORKERS:-10}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"

python scripts/interlinear/prepare_sanguozhi_pei_zhu_task.py

chunks_jsonl="data/source-plan/sanguozhi-pei-zhu-maintext/chunks.jsonl"
manifest="data/source-plan/sanguozhi-pei-zhu-maintext/manifest.json"
canonical_dir="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/interlinear/chunks"
candidate_dir="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/parallel-json"
work_root="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/worker"
log_dir="books/sanguozhi-pei-zhu/work/logs"
run_script="books/sanguozhi-pei-zhu/work/pei-zhu-maintext/run-pei-zhu-workers.sh"
mkdir -p "$(dirname "$run_script")" "$log_dir"

cat > "$run_script" <<RUN
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
workers='$workers'
model='$model'
reasoning='$reasoning'
echo "starting sanguozhi-pei-zhu workers=\$workers model=\$model reasoning=\$reasoning"
for i in \$(seq 1 '$workers'); do
  wid=\$(printf 'pei-zhu-%02d' "\$i")
  python -u scripts/interlinear/codex_quadrilingual_wenyan_worker.py \\
    --chunks-jsonl '$chunks_jsonl' \\
    --canonical-dir '$canonical_dir' \\
    --candidate-dir '$candidate_dir' \\
    --work-dir "$work_root/\$wid" \\
    --worker-id "\$wid" \\
    --model "\$model" \\
    --reasoning "\$reasoning" \\
    --retries 3 \\
    2>&1 | tee "$log_dir/\$wid.log" &
done
wait
python scripts/interlinear/report_quadrilingual_progress.py \\
  --manifest '$manifest' \\
  --chunks-jsonl '$chunks_jsonl' \\
  --chunk-dir '$canonical_dir'
bash scripts/interlinear/compile_sanguozhi_pei_zhu_book.sh --main-layer wenyan --color-mode color
bash scripts/interlinear/compile_sanguozhi_pei_zhu_book.sh --main-layer wenyan --color-mode blackwhite
RUN
chmod +x "$run_script"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

tmux new-session -d -s "$session" -n pei-zhu "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"
echo "$session"
echo "progress: python scripts/interlinear/report_quadrilingual_progress.py --manifest '$manifest' --chunks-jsonl '$chunks_jsonl' --chunk-dir '$canonical_dir'"
