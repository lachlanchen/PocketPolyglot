# Yantielun Source Sync - 2026-07-10

`鹽鐵論` / `盐铁论` was not already present in local `sources/`,
`resources/`, `books/`, `data/`, or `references/` searches.

## Synced Sources

| Layer | Source | Local path | Status |
| --- | --- | --- | --- |
| `wenyan` | Chinese Wikisource `鹽鐵論` source tree | `sources/yantielun/zh/wenyan-wikisource/` | 13 fetched pages; use normal `卷01`-`卷10` spine |
| `wenyan` | Chinese Wikisource EPUB export | `sources/yantielun/zh/wenyan-wikisource-export/鹽鐵論-Wikisource.epub` | OK |
| `wenyan` | Combined Wikisource PDF | `sources/yantielun/zh/wenyan-wikisource-export/鹽鐵論-Wikisource.pdf` | OK |
| `wenyan` | Rendered Wikisource snapshot PDF | `sources/yantielun/wiki-snapshots/wikisource/zh/wikisource-zh-鹽鐵論.pdf` | OK |
| `zh_modern` | Chinese Wikipedia `盐铁论` context | `sources/yantielun/wiki-snapshots/wikipedia/zh/wikipedia-zh-盐铁论.pdf` | OK |
| `en` | English Wikipedia `Discourses on Salt and Iron` context | `sources/yantielun/wiki-snapshots/wikipedia/en/wikipedia-en-Discourses on Salt and Iron.pdf` | OK |
| `ja_modern` | Japanese Wikipedia `塩鉄論` context | `sources/yantielun/wiki-snapshots/wikipedia/ja/wikipedia-ja-塩鉄論.pdf` | OK |

## Generation Notes

- No existing local Yantielun PDF was found before syncing.
- No full English or Japanese Wikisource text was found; English and modern
  Japanese should be generated from the `wenyan` source, with the wiki snapshots
  used only as context.
- The fetched folder includes root and edition-reference pages. The task uses
  the normal `鹽鐵論/卷01` through `鹽鐵論/卷10` subpages as the book spine.

