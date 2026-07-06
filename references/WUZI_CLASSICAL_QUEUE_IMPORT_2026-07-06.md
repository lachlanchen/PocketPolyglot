# Wuzi Classical Queue Import - 2026-07-06

Wu Qi / Wuzi materials were copied from the sibling Books repository into this
repo's ignored source tree, then registered as a launchable quadrilingual
PocketPolyglot task.

## Local Source Paths

| Layer | Purpose | Path |
| --- | --- | --- |
| `wenyan` | Chinese Wikisource spine | `sources/chinese-military-classics/wuzi/zh/wikisource/` |
| `zh_modern` | Chinese reference EPUB | `sources/chinese-military-classics/wuzi/zh/吴起兵书.epub` |
| `en` | English/Chinese anthology reference | `sources/chinese-military-classics/anthologies/en/Chinese Martial Code - Sun Tzu Sima Rangju Wu Zi.epub` |
| `en` | Secondary military anthology | `sources/chinese-military-classics/anthologies/en/Military Strategy Classics of Ancient China - English and Chinese.epub` |
| `ja_modern` | Japanese Wikisource reference | `sources/chinese-military-classics/wuzi/jp/wikisource/` |
| `wiki` | Context snapshots | `sources/chinese-military-classics/wuzi/wiki-snapshots/` |

## Prepared Task

| Field | Value |
| --- | --- |
| Book ID | `wuzi` |
| Title | `吳子` / `吴子` / `呉子` / `Wuzi` |
| Author | `吳起` |
| Chapters | 6 |
| Chunks | 44 |
| Markdown | `books/wuzi/markdown/wenyan.md` |
| Manifest | `books/wuzi/work/quadrilingual/chunks/manifest.json` |
| Chunks JSONL | `books/wuzi/work/quadrilingual/chunks/chunks.jsonl` |

The Chinese Wikisource source is one root page, so the source plan uses six
chapter anchors: `圖國第一`, `料敵第二`, `治兵第三`, `論將第四`, `應變第五`,
and `勵士第六`.

Reference extraction for `wuzi` opens the shared military anthologies near
Wuzi-specific headings/phrases, avoiding unrelated Sunzi or Wu Zixu front
matter in generation prompts.
