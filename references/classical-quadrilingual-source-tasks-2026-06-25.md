# Classical Quadrilingual Source Tasks - 2026-06-25

These tasks were prepared from the Books archive inventory at
`../Books/references/CLASSICAL_TEXT_VERSION_TABLE_2026-06-25.md`.

## Default Task Shape

All four works are classical Chinese tasks. The default output should keep
Chinese wenyan as the main stream and add three aligned note layers:

1. English
2. Modern Japanese
3. Modern Chinese

Machine-readable source plan:
`data/source-plan/classical-quadrilingual-source-batch.json`.

Default renderer target:
`quadrilingual_wenyan_main`, with `default_note_order.wenyan` set to
`["en", "ja_modern", "zh_modern"]`.

## Prepared Sources

| Work | Book ID | Main Source | Reference Layers | Caveat |
| --- | --- | --- | --- | --- |
| 莊子 / Zhuangzi | `zhuangzi` | `sources/zhuangzi/zh/wenyan-wikisource` | modern Chinese annotated PDF, Burton Watson English, Giles Gutenberg, Japanese scan | Japanese retelling files are secondary, not a complete aligned source. |
| 漢書 / Book of Han | `han-shu` | `sources/han-shu/zh/wenyan-wikisource` plus Gutenberg/EPUB alternates | Dubs English volume 1 | Japanese Wikisource is index-only; modern Japanese must be generated where needed. |
| 後漢書 / Book of Later Han | `hou-han-shu` | `sources/hou-han-shu/zh/wenyan-wikisource` plus 李賢注 scan | partial English military/history reference, 倭傳 Japanese excerpt | English/Japanese references are partial and chapter-limited. |
| 三國志 / Records of the Three Kingdoms | `sanguozhi` | `sources/sanguozhi/zh/wenyan-wikisource` plus Gutenberg/裴松之注 EPUB | incomplete English Wikisource, English selections | Japanese Wikisource is index-only; English references are incomplete. |

## Next Pipeline Step

Do not start generation directly from raw PDFs. First convert the selected
source layers to reviewed Markdown:

- extract the wenyan spine chapter by chapter;
- extract or OCR modern Chinese references where available;
- extract English and Japanese references only as broad chapter references;
- split the wenyan spine into stable paragraph-level chunks;
- generate quadrilingual chunk JSON without replacing any source text.

The first runnable task after this preparation should create
`books/<book-id>/work/quadrilingual/chunks/manifest.json` and
`books/<book-id>/book-plan.json`, then use:

```sh
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh <book-id>
```

