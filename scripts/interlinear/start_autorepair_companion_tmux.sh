#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/interlinear/start_autorepair_companion_tmux.sh --name NAME [options]

Generic tmux launcher for scripts/autorepair_companion.py.  The companion is
task-neutral: pass it a primary tmux session, a cheap health command, watched
artifact paths, and an optional deterministic restart command.

Common options:
  --name NAME
  --session TMUX_SESSION
  --state-dir DIR
  --primary-session TMUX_SESSION
  --health-command COMMAND
  --health-nonzero-ok
  --complete-key KEY=VALUE
  --complete-key-eq LEFT=RIGHT
  --complete-ratio KEY
  --watch PATH_OR_GLOB
  --log PATH_OR_GLOB
  --py-compile PATH_OR_GLOB
  --start-command COMMAND
  --allow-repair

Environment:
  AUTOREPAIR_INTERVAL_SECONDS=600
  AUTOREPAIR_STALL_SECONDS=1800
  AUTOREPAIR_ACTIVE_STALL_SECONDS=7200
  AUTOREPAIR_COOLDOWN_SECONDS=7200
  AUTOREPAIR_MODEL=gpt-5.5
  AUTOREPAIR_MAX_REASONING=high

Backward compatibility:
  If the first argument is not an option, this script delegates to the legacy
  interlinear self-healing guardian for book-id based calls.
USAGE
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

if [[ "${1:-}" != --* ]]; then
  exec bash scripts/interlinear/start_self_healing_guardian_tmux.sh "$@"
fi

name=""
session=""
state_dir=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      name="$2"
      args+=("$1" "$2")
      shift 2
      ;;
    --session)
      session="$2"
      shift 2
      ;;
    --state-dir)
      state_dir="$2"
      args+=("$1" "$2")
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      args+=("$1")
      if [[ $# -gt 1 && "${2:-}" != --* ]]; then
        args+=("$2")
        shift 2
      else
        shift
      fi
      ;;
  esac
done

if [[ -z "$name" ]]; then
  echo "Missing --name" >&2
  exit 1
fi
if [[ -z "$state_dir" ]]; then
  state_dir="logs/autorepair/$name"
  args+=(--state-dir "$state_dir")
fi
if [[ -z "$session" ]]; then
  session="${name}-autorepair"
fi
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux autorepair companion already exists: $session"
  exit 0
fi

mkdir -p "$state_dir"
run_script="$state_dir/${session}.run.sh"
log="$state_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

quoted_args=()
for arg in "${args[@]}"; do
  quoted_args+=("$(printf '%q' "$arg")")
done

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "$root")
python -u scripts/autorepair_companion.py ${quoted_args[*]} 2>&1 | tee -a $(printf '%q' "$log")
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n autorepair "bash '$run_script'"

echo "tmux: $session"
echo "name: $name"
echo "state_dir: $state_dir"
echo "log: $log"
echo "run_script: $run_script"
