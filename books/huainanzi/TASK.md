# Huainanzi Quadrilingual Task

Status: prepared, not started.

This task builds `淮南子 / Huainanzi` as a LinguaLeaf classical quadrilingual
pocket book:

- main stream: `wenyan` classical Chinese;
- note layers: English, readable modern Japanese, and modern Chinese;
- final target: large-font color and black-white PDFs with cover and TOC.

Prepared files:

- `books/huainanzi/book-plan.json`
- `books/huainanzi/markdown/wenyan.md`
- `books/huainanzi/work/quadrilingual/chunks/manifest.json`
- local ignored chunk source: `books/huainanzi/work/quadrilingual/chunks/chunks.jsonl`

Source assets are local and ignored under `sources/huainanzi/`.

Current prepared scope:

- source sections: 22
- chunks: 544
- first section: `敘目`
- last section: `要略`

Primary references:

- Chinese spine: `sources/huainanzi/zh/wikisource-export`
- Modern Chinese: `sources/huainanzi/zh/modern-reference/[中华经典名著全本全注全译丛书] 陈广忠 译注 - 淮南子 (2011, 中华书局) - libgen.li.pdf`
- English: `sources/huainanzi/en/modern-reference/[Translations from the Asian classics] Major, John S._Liu, An - The Huainanzi_ a guide to the theory and practice of government in early Han China (2010_2011, Columbia University Press) - libgen.li.epub`
- Japanese: `sources/huainanzi/jp/public-domain/NDL976851_淮南子_-_現代語訳_part*.pdf`

To start later with the large-run default:

```sh
WORKERS=100 MODEL=gpt-5.5 REASONING=low \
  scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  huainanzi zhjpbook-huainanzi-100-low
```

For a gentler run:

```sh
WORKERS=10 MODEL=gpt-5.5 REASONING=low \
  scripts/interlinear/start_quadrilingual_wenyan_tmux.sh \
  huainanzi zhjpbook-huainanzi-10-low
```

Progress check:

```sh
python scripts/interlinear/report_quadrilingual_progress.py \
  --manifest books/huainanzi/work/quadrilingual/chunks/manifest.json \
  --chunks-jsonl books/huainanzi/work/quadrilingual/chunks/chunks.jsonl \
  --chunk-dir books/huainanzi/work/quadrilingual/interlinear/chunks
```
