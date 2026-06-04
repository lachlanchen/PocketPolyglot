#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-gone-with-the-wind-trilingual}"
exec bash scripts/interlinear/start_trilingual_book_tmux.sh gone-with-the-wind "$session"
