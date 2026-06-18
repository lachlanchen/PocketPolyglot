#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="${1:-data/source-plan/incremental-backfill-phases/phase-1-normal-english.json}"
variants=(${VARIANTS:-color blackwhite})

mapfile -t books < <(
  python - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

root = Path.cwd()
manifest = json.loads((root / sys.argv[1]).read_text(encoding="utf-8"))
for item in sorted(manifest.get("books", []), key=lambda row: row.get("priority", 9999)):
    book_id = item["book_id"]
    total = int(item.get("chunk_count") or 0)
    if item.get("dependency") != "base_chunks_exist" or total <= 0:
        continue
    durable = root / "data" / "interlinear-overlays" / "en-modern-ja" / book_id / "chunks"
    work = root / "books" / book_id / "work" / "incremental" / "en-modern-ja" / "overlays" / "chunks"
    done = {path.stem for directory in (durable, work) if directory.exists() for path in directory.glob("*.json")}
    if len(done) >= total:
        print(book_id)
PY
)

if [[ "${#books[@]}" -eq 0 ]]; then
  echo "No completed bilingual-overlay books found in $manifest" >&2
  exit 1
fi

for book_id in "${books[@]}"; do
  echo "== $book_id =="
  for variant in "${variants[@]}"; do
    bash scripts/interlinear/compile_bilingual_overlay_en_notes_book.sh \
      --book-id "$book_id" \
      --color-mode "$variant"
  done
done
