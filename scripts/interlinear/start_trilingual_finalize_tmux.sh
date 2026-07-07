#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_trilingual_finalize_tmux.sh <book-id> <writer-session> [finalize-session]

Wait for a trilingual writer tmux session to finish, then finalize the book:
  - merge accepted candidates one final time
  - require full manifest coverage
  - backfill deterministic grammar roles
  - compile all 12 standard PDFs with ALLOW_MISSING=0
  - generate/prepend a cover page when needed
  - sync the finished PDFs to Nutstore Projects
  - sync durable JSON to data/interlinear/<book-id>/
  - commit the durable JSON artifacts if they changed
USAGE
}

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
writer_session="$2"
session="${3:-zhjpbook-${book_id}-trilingual-finalize}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
raw_chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
assembled_json="$(jq -r '.assembled_json // .preview_json // empty' "$plan")"
if [[ -z "$assembled_json" ]]; then
  assembled_json="books/$book_id/work/trilingual/preview/$book_id.partial.json"
fi
work_root="books/$book_id/work/trilingual/finalize"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$log_dir"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'

while tmux has-session -t '=$writer_session' 2>/dev/null; do
  echo "waiting_for_writer=$writer_session at \$(date -Is)"
  python scripts/interlinear/report_trilingual_progress.py --manifest '$manifest' --chunk-dir '$raw_chunk_dir' || true
  sleep 300
done

python scripts/interlinear/merge_trilingual_json_candidates.py \\
  --chunks-jsonl '$chunks_jsonl' \\
  --candidate-dir 'books/$book_id/work/trilingual/parallel-json/candidates' \\
  --canonical-dir '$raw_chunk_dir' \\
  --merged-dir 'books/$book_id/work/trilingual/parallel-json/merged'

python scripts/interlinear/report_trilingual_progress.py --manifest '$manifest' --chunk-dir '$raw_chunk_dir'

python - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('$manifest').read_text(encoding='utf-8'))
chunk_dir = Path('$raw_chunk_dir')
missing = [item['chunk_id'] for item in manifest.get('chunks', []) if not (chunk_dir / f"{item['chunk_id']}.json").exists()]
if missing:
    raise SystemExit(f"incomplete_chunks={len(missing)} first_missing={missing[0]}")
print(f"complete_chunks={len(manifest.get('chunks', []))}")
PY

python scripts/interlinear/backfill_trilingual_grammar_roles.py \\
  --chunk-dir '$raw_chunk_dir' \\
  --chunks-jsonl '$chunks_jsonl' \\
  --overwrite-collapsed

ALLOW_MISSING=0 bash scripts/interlinear/compile_trilingual_book_12_previews.sh '$book_id'

if [[ ! -f 'assets/covers/$book_id/cover.png' ]]; then
  node scripts/books/generate_aginti_cover_assets.mjs --book '$book_id'
fi
python scripts/books/prepend_cover_pages.py --book '$book_id' --replace-existing
python scripts/books/sync_trilingual_pair_book_to_nutstore.py '$book_id'

mkdir -p "\$(dirname '$assembled_json')"
python scripts/interlinear/assemble_trilingual_json.py \\
  --manifest '$manifest' \\
  --chunks-jsonl '$chunks_jsonl' \\
  --chunk-dir '$raw_chunk_dir' \\
  --output '$assembled_json'

python scripts/interlinear/validate_trilingual_interlinear_json.py '$assembled_json'

mkdir -p 'data/interlinear/$book_id/chunks' 'data/interlinear/$book_id/assembled'
rsync -a --delete --include='*.json' --exclude='*' '$raw_chunk_dir/' 'data/interlinear/$book_id/chunks/'
cp '$assembled_json' 'data/interlinear/$book_id/assembled/$book_id.trilingual.json'
python scripts/interlinear/validate_trilingual_interlinear_json.py 'data/interlinear/$book_id/assembled/$book_id.trilingual.json'

git add 'data/interlinear/$book_id'
if git diff --cached --quiet; then
  echo "no_data_changes_to_commit"
else
  git commit -m "Complete $book_id trilingual artifacts"
fi
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n finalize "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "book_id: $book_id"
echo "writer_session: $writer_session"
echo "run_script: $run_script"
