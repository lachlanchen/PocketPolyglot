# Interlinear Data Layout

Top-level files are reserved for small shared demos such as `sample.json`.
Book-specific generated data lives under `data/interlinear/<book-id>/`.

For Kokoro:

- `kokoro/chunks/`: current validated chunk JSON snapshots.
- `kokoro/artifacts/paragraphs/`: durable paragraph-level translation, ruby, and grammar artifacts.
- `kokoro/progress.json`: current generated-progress summary.
- `kokoro/assembled/`: current full assembled book JSON from future full pipeline runs.
- `kokoro/legacy/`: older assembled JSON versions kept for reference.

Do not delete legacy JSON when changing chunking strategy. Prefer moving old
assembled outputs into `legacy/` and preserving paragraph artifacts whenever the
source paragraph hash still matches.
