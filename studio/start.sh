#!/usr/bin/env bash
set -euo pipefail

studio_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$studio_root/.." && pwd)"
host="${POCKETPOLYGLOT_HOST:-127.0.0.1}"
port="${POCKETPOLYGLOT_PORT:-8765}"

cd "$studio_root/web"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build

cd "$repo_root"
export PYTHONPATH="$studio_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="$repo_root/.pocketpolyglot-studio/venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python)"
fi
exec "$python_bin" -m pocketpolyglot_studio.cli serve --host "$host" --port "$port"
