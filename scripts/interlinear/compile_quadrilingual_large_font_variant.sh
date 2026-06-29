#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

exec bash scripts/interlinear/compile_quadrilingual_shiji_font_variant.sh "$@"
