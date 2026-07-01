# Foguo Ji / 佛國記 LibGen And Wiki Sync - 2026-06-30

This records the LibGen pages opened and the local Wikisource/Wikipedia
downloads for `佛國記 / Foguo Ji / 仏国記`. Large local assets live under
ignored `resources/`; this Markdown file is the tracked audit trail.

## ZhJpBook Local Copy

The Books archive materials were copied into this repository on 2026-07-01.
The active task uses `sources/foguoji/`, which is intentionally ignored by Git
because it contains source assets and exports.

| Layer | Active path in this repo |
| --- | --- |
| Chinese wenyan source | `sources/foguoji/zh/wenyan-wikisource/` |
| Chinese Wikisource EPUB | `sources/foguoji/zh/wikisource-export/佛國記-Wikisource.epub` |
| Chinese author reference | `sources/foguoji/zh/wikipedia-reference/` |
| English translation reference | `sources/foguoji/en/wikisource-record-of-buddhistic-kingdoms/` |
| English Wikisource EPUB | `sources/foguoji/en/wikisource-export/Record-of-the-Buddhistic-Kingdoms-Wikisource.epub` |
| English author reference | `sources/foguoji/en/wikipedia-reference/` |
| Japanese work/author references | `sources/foguoji/jp/wikipedia-reference/` |
| Export summary metadata | `sources/foguoji/metadata/wiki-export-summary-2026-06-30.json` |

## LibGen Pages Opened

| Language | Page opened | URL | Note |
| --- | --- | --- | --- |
| Chinese | `佛國記` | `https://libgen.pw/book/114629417` | Exact title PDF candidate, attributed to `釋法顯`. |
| English | `A Record of Buddhistic Kingdoms` | `https://libgen.pw/book/91743953` | Exact English translation candidate, James Legge / Fa-Hien. |
| Japanese | `仏国記 法顕` search | `https://libgen.pw/search?query=%E4%BB%8F%E5%9B%BD%E8%A8%98+%E6%B3%95%E9%A1%95&collection=libgen` | No clean Japanese detail candidate was found; opened exact search page instead. |

## Wikisource Downloads

| Work | Language | Source | Local path | Status |
| --- | --- | --- | --- | --- |
| `佛國記` | Chinese | `https://zh.wikisource.org/wiki/佛國記` | `resources/curated-books/chinese-classics/foguoji/zh-wikisource/` | 1 raw/HTML page, 0 errors. |
| `Record of the Buddhistic Kingdoms` | English | `https://en.wikisource.org/wiki/Record_of_the_Buddhistic_Kingdoms` | `resources/curated-books/chinese-classics/foguoji/en-wikisource-record-of-buddhistic-kingdoms/` | 1 raw/HTML page, 0 errors. |

## Wikisource EPUB Exports

| Work | Language | Local EPUB | Status |
| --- | --- | --- | --- |
| `佛國記` | Chinese | `resources/curated-books/chinese-classics/foguoji/zh-wikisource-export/佛國記-Wikisource.epub` | Valid EPUB. |
| `Record of the Buddhistic Kingdoms` | English | `resources/curated-books/chinese-classics/foguoji/en-wikisource-export/Record-of-the-Buddhistic-Kingdoms-Wikisource.epub` | Valid EPUB. |

Wikisource PDF export returned HTTP 503 for both Chinese and English export
attempts. No Japanese Wikisource full text page was found for `仏国記`,
`佛國記`, `法顕伝`, or related exact queries.

## Wikipedia Reference Downloads

| Topic | Language | Local path | Note |
| --- | --- | --- | --- |
| `法显` | Chinese | `resources/curated-books/chinese-classics/foguoji/zh-wikipedia-reference/` | Chinese reference page; `佛國記` itself is not a Chinese Wikipedia page. |
| `Faxian` | English | `resources/curated-books/chinese-classics/foguoji/en-wikipedia-reference/` | English reference page for the author/traveler. |
| `仏国記` | Japanese | `resources/curated-books/chinese-classics/foguoji/ja-wikipedia-reference/` | Japanese reference page for the work. |
| `法顕` | Japanese | `resources/curated-books/chinese-classics/foguoji/ja-wikipedia-reference/` | Japanese reference page for the author/traveler. |

## Tools Used

- `libgen_browser_context_search.py` searched LibGen through the existing
  Chrome/CDP context.
- `libgen_no_redirect_open.py` opened the selected LibGen pages with the
  redirect guard active.
- `tools/public_domain/wikisource_fetch_work.py` fetched raw wikitext, rendered
  HTML, `manifest.json`, and local README files from Wikisource.
- Wikisource WS Export generated EPUB files. PDF export was attempted and
  failed with HTTP 503.
- Wikimedia API `parse` saved Wikipedia reference HTML and JSON files.
