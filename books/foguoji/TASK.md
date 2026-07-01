# Foguo Ji Quadrilingual Task

Status: prepared, not started.

This task builds `佛國記 / 佛国记 / 仏国記 / A Record of Buddhistic Kingdoms`
as a LinguaLeaf classical quadrilingual pocket book:

- main stream: `wenyan` classical Chinese;
- note layers: English, modern Japanese, modern Chinese;
- final export target: large-font color and black-white PDFs when generated.

Prepared files:

- `books/foguoji/book-plan.json`
- `books/foguoji/markdown/wenyan.md`
- `books/foguoji/work/quadrilingual/chunks/manifest.json`
- local ignored chunk source: `books/foguoji/work/quadrilingual/chunks/chunks.jsonl`

Source assets are local and ignored under `sources/foguoji/`.

To start later with 10 low-reasoning workers:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  foguoji zhjpbook-foguoji-10-low
```

Progress check:

```sh
python scripts/interlinear/report_quadrilingual_progress.py \
  --manifest books/foguoji/work/quadrilingual/chunks/manifest.json \
  --chunks-jsonl books/foguoji/work/quadrilingual/chunks/chunks.jsonl \
  --chunk-dir books/foguoji/work/quadrilingual/interlinear/chunks
```
