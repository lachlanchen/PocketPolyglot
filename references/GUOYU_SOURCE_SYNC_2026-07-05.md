# Guoyu LibGen And Wikisource Sync - 2026-07-05

This records LibGen pages opened and Wikisource/Wikipedia downloads for the
Chinese classic `國語 / 国语 / Guoyu`, also known in English as `Discourses of
the States`. Large local assets are mirrored into ignored `sources/guoyu/` in this repo; this Markdown
file is the tracked audit trail for the copied sources and launchable task.

## LibGen Pages Opened

| Work | Language | Page opened | URL | Note |
| --- | --- | --- | --- | --- |
| `国语集解` | Chinese | Detail page | `https://libgen.pw/book/96633549` | Best exact Chinese commentary/edition candidate from browser-context search; PDF. |
| `国语集解` | Chinese | Exact search | `https://libgen.pw/search?query=%E5%9B%BD%E8%AF%AD%E9%9B%86%E8%A7%A3&collection=libgen` | Opened with redirect guard. |
| `Guoyu / Discourses of the States` | English | Exact search | `https://libgen.pw/search?query=Guoyu+Discourses+of+the+States&collection=libgen` | No clean English detail candidate selected. |
| `国語 (歴史書)` | Japanese | Exact search | `https://libgen.pw/search?query=%E5%9B%BD%E8%AA%9E+%E6%AD%B4%E5%8F%B2%E6%9B%B8&collection=libgen` | No clean Japanese detail candidate selected. |

## Wikisource Downloads

| Work | Language | Source | Local path | Status |
| --- | --- | --- | --- | --- |
| `國語` | Chinese | `https://zh.wikisource.org/wiki/國語` | `sources/guoyu/zh/wenyan-wikisource/` | 23 raw/HTML pages, 0 errors. |
| `國語 (四庫全書本)` | Chinese | `https://zh.wikisource.org/wiki/國語_(四庫全書本)` | `sources/guoyu/zh/wenyan-wikisource-siku/` | 22 raw/HTML pages, 0 errors. |

Exact English and Japanese Wikisource title checks for `Guoyu`,
`Guoyu (book)`, `Discourses of the States`, `Kuo Yu`, `国語`, `國語`,
`国語 (歴史書)`, and `春秋外伝` were missing, so no EN/JP Wikisource
main-text folders were created.

## Wikisource EPUB Exports

| Work | Language | Local EPUB | Status |
| --- | --- | --- | --- |
| `國語` | Chinese | `sources/guoyu/zh/wenyan-wikisource-export/國語-Wikisource.epub` | Valid EPUB, 428,936 bytes. |
| `國語 (四庫全書本)` | Chinese | `sources/guoyu/zh/wenyan-wikisource-export/國語 (四庫全書本)-Wikisource.epub` | Valid EPUB, 694,532 bytes. |

Wikisource PDF export returned HTTP 503 for both Chinese export attempts.

## Wikipedia Reference Downloads

| Topic | Language | Local path | Status |
| --- | --- | --- | --- |
| `國語 (書)`, `左丘明` | Chinese | `sources/guoyu/zh/wikipedia-reference/` | 2 pages, 0 errors. |
| `Guoyu (book)`, `Discourses of the States` | English | `sources/guoyu/en/wikipedia-reference/` | 2 pages, 0 errors. |
| `国語 (歴史書)`, `国語` | Japanese | `sources/guoyu/jp/wikipedia-reference/` | 2 pages, 0 errors. |


## ZhJpBook Local Source Copy

Additional downloaded PDF copied for the PocketPolyglot task:

| Work | Source | Local path | Status |
| --- | --- | --- | --- |
| `国语集解` | `/home/lachlan/Downloads/国语集解.pdf` | `sources/guoyu/zh/chinese-commentary/国语集解.pdf` | 612-page PDF copied locally; ignored by Git. |

Prepared task outputs are under `books/guoyu/` and use book id `guoyu`.

## Tools Used

- `tools/book_search/libgen_browser_context_search.py` searched LibGen through
  Chrome/CDP for candidate IDs.
- `tools/book_search/libgen_no_redirect_open.py` opened LibGen pages with
  redirect blocking enabled.
- `tools/public_domain/wikisource_fetch_work.py` fetched Chinese Wikisource
  raw wikitext, rendered HTML, manifests, and local README files.
- Wikisource WS Export generated EPUB files; PDF export failed with HTTP 503.
- Wikimedia API `parse` saved Chinese, English, and Japanese Wikipedia
  reference HTML and JSON files.
