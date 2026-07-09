# Huainanzi Source Sync And Task Prep - 2026-07-09

Huainanzi sources were copied into this repository for a future LinguaLeaf
quadrilingual classical task. Large source assets are intentionally ignored by
Git under `sources/` and `resources/`.

## Copied Sources

| Layer | Source | Stored path |
| --- | --- | --- |
| Wenyan | Chinese Wikisource raw/HTML export | `sources/huainanzi/zh/wikisource-export/` |
| Wenyan reference | Public-domain Chinese scan | `sources/huainanzi/zh/public-domain/NTUL-9900013603_淮南子.pdf` |
| Modern Chinese | Chen Guangzhong annotated translation | `sources/huainanzi/zh/modern-reference/[中华经典名著全本全注全译丛书] 陈广忠 译注 - 淮南子 (2011, 中华书局) - libgen.li.pdf` |
| English | Major/Liu Columbia translation EPUB | `sources/huainanzi/en/modern-reference/[Translations from the Asian classics] Major, John S._Liu, An - The Huainanzi_ a guide to the theory and practice of government in early Han China (2010_2011, Columbia University Press) - libgen.li.epub` |
| English | Sacred Texts public-domain selection | `sources/huainanzi/en/sacred-texts-tao-great-luminant/` |
| Japanese | NDL public-domain modern translation scans | `sources/huainanzi/jp/public-domain/` |
| Open refs | ZH/EN/JA wiki and Wikisource snapshots | `sources/huainanzi/wiki-snapshots/` |

The same source set was mirrored into ignored archival storage:

- `resources/curated-books/chinese-classics/huainanzi/`
- `resources/curated-books/wiki-snapshots/chinese-classics/huainanzi/`

## Prepared Task

Registered `huainanzi` in
`data/source-plan/classical-quadrilingual-source-batch.json`, then generated:

- `books/huainanzi/book-plan.json`
- `books/huainanzi/markdown/wenyan.md`
- `books/huainanzi/work/quadrilingual/chunks/manifest.json`
- `books/huainanzi/work/quadrilingual/chunks/chunks.jsonl`
- `books/huainanzi/TASK.md`

Prepared scope:

| Metric | Value |
| --- | ---: |
| Source sections | 22 |
| Chunks | 544 |
| Initial progress | `0/544` |

## Validation

```sh
python -m py_compile scripts/interlinear/prepare_classical_quadrilingual_task.py
python -m json.tool data/source-plan/classical-quadrilingual-source-batch.json >/dev/null
python scripts/interlinear/prepare_classical_quadrilingual_task.py --book-id huainanzi --force
python scripts/interlinear/report_quadrilingual_progress.py \
  --manifest books/huainanzi/work/quadrilingual/chunks/manifest.json \
  --chunks-jsonl books/huainanzi/work/quadrilingual/chunks/chunks.jsonl \
  --chunk-dir books/huainanzi/work/quadrilingual/interlinear/chunks
```

Current progress is `0/544`; no writer was started.
