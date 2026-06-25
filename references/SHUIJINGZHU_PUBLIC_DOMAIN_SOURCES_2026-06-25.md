# Shuijingzhu Public-Domain/Open Sources - 2026-06-25

This records open/public-domain source downloads and references for
`水經注 / 水经注 / Shui Jing Zhu / 水経注`. Large files live under ignored
`resources/`; this Markdown file is the tracked audit trail.

Destination root:

`resources/curated-books/public-domain-classics/shuijingzhu/`

## Download Matrix

| Language | Source / Format | Local path | Status |
| --- | --- | --- | --- |
| Chinese | Chinese Wikisource raw tree | `resources/curated-books/public-domain-classics/shuijingzhu/zh-wikisource/` | 42 raw pages, 0 errors. |
| Chinese | Wikisource WS Export EPUB/PDF | `resources/curated-books/public-domain-classics/shuijingzhu/zh-wikisource-export/` | Valid EPUB and 1074-page PDF. |
| Chinese | Internet Archive `06082214.cn`-`06082231.cn` scan series | `resources/curated-books/public-domain-classics/shuijingzhu/zh-internet-archive-060822-series/` | 18 item folders; each has PDF, OCR TXT, and metadata JSON. |
| English | English Wikipedia open reference | `resources/curated-books/public-domain-classics/shuijingzhu/en-wikipedia-open-reference/` | API JSON and rendered HTML saved; not a full translation. |
| Japanese | Japanese Wikipedia open reference | `resources/curated-books/public-domain-classics/shuijingzhu/ja-wikipedia-open-reference/` | API JSON and rendered HTML saved; not a full translation. |
| Japanese | Waseda University Library catalogue/reference | `resources/curated-books/public-domain-classics/shuijingzhu/jp-waseda-catalog-reference/` | Catalogue HTML and viewer index saved. 16 PDF links recorded but not downloaded because no explicit open reuse license was confirmed. |

## Source URLs

| Source | URL |
| --- | --- |
| Chinese Wikisource `水經注` | <https://zh.wikisource.org/wiki/水經注> |
| Wikisource WS Export | <https://ws-export.wmcloud.org/?lang=zh&format=epub&page=%E6%B0%B4%E7%B6%93%E6%B3%A8> |
| Internet Archive search seed item | <https://archive.org/details/06082214.cn> |
| English Wikipedia reference page | <https://en.wikipedia.org/wiki/Commentary_on_the_Water_Classic> |
| Japanese Wikipedia reference page | <https://ja.wikipedia.org/wiki/%E6%B0%B4%E7%B5%8C%E6%B3%A8> |
| Waseda catalogue page | <https://www.wul.waseda.ac.jp/kotenseki/html/ru05/ru05_01554/index.html> |
| Waseda viewer index | <https://archive.wul.waseda.ac.jp/kosho/ru05/ru05_01554/> |

## Internet Archive Series

| Identifier | Coverage |
| --- | --- |
| `06082214.cn` | `水經注·卷一` |
| `06082215.cn` | `水經注·卷二` |
| `06082216.cn` | `水經注·卷三~卷四` |
| `06082217.cn` | `水經注·卷五` |
| `06082218.cn` | `水經注·卷六` |
| `06082219.cn` | `水經注·卷七~卷八` |
| `06082220.cn` | `水經注·卷九~卷十` |
| `06082221.cn` | `水經注·卷十一~卷十三` |
| `06082222.cn` | `水經注·卷十四~卷十六` |
| `06082223.cn` | `水經注·卷十七~卷十九` |
| `06082224.cn` | `水經注·卷二十~卷二十二` |
| `06082225.cn` | `水經注·卷二十三~卷二十四` |
| `06082226.cn` | `水經注·卷二十五~卷二十六` |
| `06082227.cn` | `水經注·卷二十七~卷二十九` |
| `06082228.cn` | `水經注·卷三十~卷三十二` |
| `06082229.cn` | `水經注·卷三十三~卷三十五` |
| `06082230.cn` | `水經注·卷三十六~卷三十七` |
| `06082231.cn` | `水經注·卷三十八~卷四十` |

## Search Outcome Notes

- No exact Project Gutenberg/Gutendex record was found for `水經注`,
  `水经注`, `Shui Jing Zhu`, `Shui-ching Chu`, or `Shuijingzhu`.
- No full English Wikisource translation page was found.
- No Japanese Wikisource `水経注` page was found.
- Waseda hosts an 1892 `水経注` scan catalogue with 16 PDF links. The metadata
  and link list were archived, but the PDFs were not downloaded in this pass
  because the page carries a Waseda copyright notice and no explicit open reuse
  license was confirmed.

## Tools And Validation

- `tools/public_domain/wikisource_fetch_work.py` fetched the Chinese Wikisource
  raw tree and wrote per-folder manifests.
- Wikisource WS Export generated `水經注-Wikisource.epub` and
  `水經注-Wikisource.pdf`.
- Internet Archive metadata and direct PDF/OCR TXT URLs were downloaded one item
  at a time with local `metadata.json` files.
- Wikimedia API/rendered HTML captured English and Japanese open reference
  pages.
- Validation used `file` and manifest inspection. EPUB/PDF signatures and
  Internet Archive JSON/TXT files were confirmed.
