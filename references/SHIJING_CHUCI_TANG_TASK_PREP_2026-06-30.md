# Shijing, Chuci, And Tang Poetry Task Prep - 2026-06-30

The curated source folders from `/home/lachlan/ProjectsLFS/Books/resources/curated-books/chinese-classics/` were copied into local ignored `sources/` folders in this repository. Original files were not moved.

| Work | Local source folder | Task status | Chapters | Chunks | Order rule |
| --- | --- | --- | ---: | ---: | --- |
| `詩經` | `sources/shijing/` | Prepared only | 300 | 949 | Chinese Wikisource root anthology order |
| `楚辭` | `sources/chuci/` | Prepared only | 17 | 178 | Received anthology order with root/commentary pages filtered |
| `唐詩三百首` | `sources/tangshi-sanbai/` | Prepared only | 320 | 647 | Chinese Wikisource root anthology order |

Prepared artifacts:

| Work | Plan | Manifest | Markdown |
| --- | --- | --- | --- |
| `詩經` | `books/shijing/book-plan.json` | `books/shijing/work/quadrilingual/chunks/manifest.json` | `books/shijing/markdown/wenyan.md` |
| `楚辭` | `books/chuci/book-plan.json` | `books/chuci/work/quadrilingual/chunks/manifest.json` | `books/chuci/markdown/wenyan.md` |
| `唐詩三百首` | `books/tangshi-sanbai/book-plan.json` | `books/tangshi-sanbai/work/quadrilingual/chunks/manifest.json` | `books/tangshi-sanbai/markdown/wenyan.md` |

Notes:

- Source PDFs, EPUBs, raw Wikisource trees, and rendered HTML are local assets under ignored `sources/`.
- `唐詩三百首` has 320 prepared poem chapters after excluding the root page and the unrelated `千家詩` side link.
- The preparer now derives root-link order for standalone anthology source trees so fetch order does not determine book order.
