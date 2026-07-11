# Hawking And Brian Greene Trilingual Queue - 2026-07-11

Prepared only. No writer, reviewer, tmux generation, cover generation, or PDF
compile was started for this queue.

The queue file is:

`data/source-plan/popular-science-trilingual-queue.json`

The prepared task shape is modern nonfiction `en-jp-zh`: English source spine,
readable modern Japanese, readable modern Chinese, and grammar-color-capable
JSON for later rendering.

## Quality-First Order

| Order | Book ID | Title | Author | Chunks | Launch manifest |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `elegant-universe` | *The Elegant Universe* | Brian Greene | 334 | `books/elegant-universe/work/trilingual/chunks/manifest.json` |
| 2 | `a-brief-history-of-time` | *A Brief History of Time* | Stephen Hawking | 167 | `books/a-brief-history-of-time/work/trilingual/chunks/manifest.json` |
| 3 | `fabric-of-the-cosmos` | *The Fabric of the Cosmos* | Brian Greene | 516 | `books/fabric-of-the-cosmos/work/trilingual/chunks/manifest.json` |
| 4 | `a-briefer-history-of-time` | *A Briefer History of Time* | Stephen Hawking and Leonard Mlodinow | 101 | `books/a-briefer-history-of-time/work/trilingual/chunks/manifest.json` |
| 5 | `universe-in-a-nutshell` | *The Universe in a Nutshell* | Stephen Hawking | 91 | `books/universe-in-a-nutshell/work/trilingual/chunks/manifest.json` |
| 6 | `grand-design` | *The Grand Design* | Stephen Hawking and Leonard Mlodinow | 104 | `books/grand-design/work/trilingual/chunks/manifest.json` |
| 7 | `hidden-reality` | *The Hidden Reality* | Brian Greene | 338 | `books/hidden-reality/work/trilingual/chunks/manifest.json` |
| 8 | `until-end-of-time` | *Until the End of Time* | Brian Greene | 330 | `books/until-end-of-time/work/trilingual/chunks/manifest.json` |
| 9 | `brief-answers-big-questions` | *Brief Answers to the Big Questions* | Stephen Hawking | 106 | `books/brief-answers-big-questions/work/trilingual/chunks/manifest.json` |
| 10 | `black-holes-baby-universes` | *Black Holes and Baby Universes and Other Essays* | Stephen Hawking | 134 | `books/black-holes-baby-universes/work/trilingual/chunks/manifest.json` |
| 11 | `nature-of-space-time` | *The Nature of Space and Time* | Stephen Hawking and Roger Penrose | 96 | `books/nature-of-space-time/work/trilingual/chunks/manifest.json` |
| 12 | `my-brief-history` | *My Brief History* | Stephen Hawking | 54 | `books/my-brief-history/work/trilingual/chunks/manifest.json` |
| 13 | `icarus-edge-of-time` | *Icarus at the Edge of Time* | Brian Greene | 5 | `books/icarus-edge-of-time/work/trilingual/chunks/manifest.json` |

## Preparation Notes

- `The Elegant Universe` and `The Grand Design` required OCR caches because the
  source PDFs did not expose enough embedded text.
- `Light Falls` was excluded from this queue because the local source is a ZIP,
  not a clean book text source.
- Front matter, notes, references, indexes, promotional pages, and copyright
  back matter were trimmed by start/stop markers and reusable parser cleanup.
- `pdf_text_or_ocr.py` now captures `pdftotext` stdout only, so stderr warnings
  such as `Syntax Warning: Invalid Font Weight` cannot enter book text.
- Formula-heavy and illustration-heavy books may still need final render review
  if exact diagrams or equations are required; the current task preparation is
  optimized for clean readable text chunks.

## Verification

Run coverage verification:

```sh
python - <<'PY'
import json
from pathlib import Path
q = json.loads(Path('data/source-plan/popular-science-trilingual-queue.json').read_text())
for t in q['tasks']:
    bid = t['book_id']
    manifest = json.loads((Path('books') / bid / 'work/trilingual/chunks/manifest.json').read_text())
    lines = sum(1 for _ in (Path('books') / bid / 'work/trilingual/chunks/chunks.jsonl').open())
    assert lines == manifest['chunk_count'] == t['chunk_count'], bid
    assert t['status'] == 'chunked_launchable', bid
print('popular-science-trilingual queue is launchable')
PY
```
