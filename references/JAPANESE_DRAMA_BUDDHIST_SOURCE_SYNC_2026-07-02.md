# Japanese, Drama, And Buddhist Source Sync - 2026-07-02

This note records local source preparation for future LinguaLeaf/PocketPolyglot
tasks. Original media and Wikisource mirrors are stored under ignored
`sources/`, so this tracked file is the durable inventory.

## Local Downloads Copied

| Work | Language | Source file | Stored path | Size |
| --- | --- | --- | --- | ---: |
| `古今和歌集` | Japanese | `/home/lachlan/Downloads/古今和歌集（全現代語訳付）.epub` | `sources/kokin-wakashu/jp/modern-translation-epub/古今和歌集（全現代語訳付）.epub` | 647.15 KiB |
| `西廂記` | Chinese | `/home/lachlan/Downloads/西廂記.pdf` | `sources/xixiangji/zh/chinese-edition/西廂記.pdf` | 2.03 MiB |
| `六祖大師法寶壇經` | Chinese | `/home/lachlan/Downloads/六祖大師法寶壇經.pdf` | `sources/platform-sutra/zh/chinese-edition/六祖大師法寶壇經.pdf` | 1.13 MiB |
| `The Platform Sutra of the Sixth Patriarch` | English | `/home/lachlan/Downloads/The Platform Sutra of the Sixth Patriarch.pdf` | `sources/platform-sutra/en/english-translation/The Platform Sutra of the Sixth Patriarch.pdf` | 1.17 MiB |
| `維摩詰所說經` | Chinese | `/home/lachlan/Downloads/维摩诘所说经.epub` | `sources/vimalakirti-sutra/zh/source-epub/维摩诘所说经.epub` | 676.28 KiB |
| `Vimalakirti Nirdesa Sutra` | English | `/home/lachlan/Downloads/VIMALAKIRTI NIRDESA SUTRA.pdf` | `sources/vimalakirti-sutra/en/english-translation/VIMALAKIRTI NIRDESA SUTRA.pdf` | 322.77 KiB |

## Wikisource Mirrors

Each mirror contains `raw/`, `html/`, `manifest.json`, and `README.md`. Missing
roots are recorded explicitly with `ok_pages=0` instead of being omitted.

| Work | Lang | Requested root | Stored path | OK pages | Status |
| --- | --- | --- | --- | ---: | --- |
| `古今和歌集` | ja | `古今和歌集` | `sources/kokin-wakashu/jp/wikisource/` | 24 | available |
| `古今和歌集` | zh | `古今和歌集` | `sources/kokin-wakashu/zh/wikisource/` | 0 | missing root |
| `Kokin Wakashu` | en | `Kokin Wakashū` | `sources/kokin-wakashu/en/wikisource/` | 0 | missing root |
| `万葉集` | ja | `万葉集` | `sources/manyoshu/jp/wikisource/` | 34 | available |
| `萬葉集` | zh | `萬葉集` | `sources/manyoshu/zh/wikisource/` | 0 | missing root |
| `Manyoshu` | en | `Manyoshu` | `sources/manyoshu/en/wikisource/` | 0 | missing root |
| `西廂記` | zh | `西廂記` | `sources/xixiangji/zh/wikisource/` | 8 | available |
| `西廂記` | ja | `西廂記` | `sources/xixiangji/jp/wikisource/` | 0 | missing root |
| `The Story of the Western Wing` | en | `The Story of the Western Wing` | `sources/xixiangji/en/wikisource/` | 0 | missing root |
| `牡丹亭` | zh | `牡丹亭` | `sources/mudanting/zh/wikisource/` | 59 | available |
| `牡丹亭` | ja | `牡丹亭` | `sources/mudanting/jp/wikisource/` | 0 | missing root |
| `The Peony Pavilion` | en | `The Peony Pavilion` | `sources/mudanting/en/wikisource/` | 0 | missing root |
| `六祖大師法寶壇經` | zh | `六祖大師法寶壇經` | `sources/platform-sutra/zh/wikisource/` | 1 | available |
| `六祖壇經` | ja | `六祖壇經` | `sources/platform-sutra/jp/wikisource/` | 0 | missing root |
| `The Platform Sutra` | en | `The Platform Sutra of the Sixth Patriarch` | `sources/platform-sutra/en/wikisource/` | 0 | missing root |
| `維摩詰所說經` | zh | `維摩詰所說經` | `sources/vimalakirti-sutra/zh/wikisource/` | 19 | available |
| `維摩経` | ja | `維摩経` | `sources/vimalakirti-sutra/jp/wikisource/` | 0 | missing root |
| `Vimalakirti Nirdesa Sutra` | en | `Vimalakirti Nirdesa Sutra` | `sources/vimalakirti-sutra/en/wikisource/` | 0 | missing root |

## Notes

- `万葉集` exists on Japanese Wikisource under the modern root `万葉集`; the
  older root `萬葉集` did not resolve to the main text.
- The English and Japanese missing roots above do not mean no translation exists
  elsewhere; they only mean the requested root was not available on the queried
  Wikisource language edition.
- `scripts/books/fetch_wikisource_tree.py` was added for reusable root/subpage
  mirroring with retry/backoff and explicit missing-root manifests.
