# Classical Queue After Fantasy - 2026-07-06

Prepared the next wenyan-main quadrilingual queue requested after the active
fantasy trilingual queue. Each task uses the PocketPolyglot/LinguaLeaf
quadrilingual shape:

`wenyan` main text + English + readable modern Japanese + modern Chinese,
with grammar-color-capable JSON and the large-font final-render path available.

## Waiting Monitor

The monitor tmux session is:

```sh
zhjpbook-classics-after-fantasy
```

It waits until these fantasy books are complete and no related fantasy writer,
finalizer, repair, or queue tmux session is active:

`the-two-towers`, `return-of-the-king`, `harry-potter-2` through
`harry-potter-7`, `a-clash-of-kings`, `a-storm-of-swords`,
`a-feast-for-crows`, and `a-dance-with-dragons`.

After that, it starts the classics one by one with:

```sh
WORKERS=100 MODEL=gpt-5.5 REASONING=low MAIN_LAYERS=wenyan
```

Runtime state is written to
`books/_queues/fantasy-then-classics/state.json` and is not a durable source
artifact.

## Prepared Classical Queue

| Order | Book ID | Title | Chapters | Chunks |
| ---: | --- | --- | ---: | ---: |
| 1 | `lunyu` | 論語 | 20 | 506 |
| 2 | `mengzi` | 孟子 | 14 | 742 |
| 3 | `xunzi` | 荀子 | 33 | 592 |
| 4 | `mozi` | 墨子 | 53 | 660 |
| 5 | `hanfeizi` | 韓非子 | 20 | 763 |
| 6 | `guiguzi` | 鬼谷子 | 7 | 128 |
| 7 | `lushi-chunqiu` | 呂氏春秋 | 26 | 765 |
| 8 | `sunbin-bingfa` | 孫臏兵法 | 1 | 70 |
| 9 | `simafa` | 司馬法 | 1 | 68 |
| 10 | `weiliaozi` | 尉繚子 | 1 | 86 |

## Source Notes

- New small Wikisource mirrors were fetched under ignored `sources/**` folders
  for local reproducibility, but source PDFs/EPUBs remain untracked by design.
- The durable task artifacts are `books/<id>/book-plan.json`,
  `books/<id>/markdown/wenyan.md`, `books/<id>/work/quadrilingual/chunks/manifest.json`,
  and the force-tracked `chunks.jsonl`.
- `hanfeizi` is prepared from the volume pages only to avoid duplicating named
  article pages.
- `mengzi`, `xunzi`, `mozi`, `guiguzi`, and `lushi-chunqiu` use explicit
  canonical sorting in `prepare_classical_quadrilingual_task.py`.
