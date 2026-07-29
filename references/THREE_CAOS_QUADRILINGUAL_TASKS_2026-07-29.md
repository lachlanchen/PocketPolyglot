# Three Caos Quadrilingual Tasks - 2026-07-29

The complete public-domain collections of Cao Cao, Cao Pi, and Cao Zhi are
prepared as independent PocketPolyglot tasks. Each task uses the original
wenyan text as the immutable main layer and requests English, readable modern
Japanese, and modern Chinese.

The queue was started on 2026-07-29 with ten `gpt-5.6-sol` low-reasoning
workers. It runs one book at a time in Cao Cao, Cao Pi, Cao Zhi order:

`data/source-plan/three-caos-quadrilingual-queue.json`

## Prepared Tasks

| Priority | Task ID | Work | Sections | Source paragraphs | Chunks | Coverage |
| ---: | --- | --- | ---: | ---: | ---: | --- |
| 1 | `cao-cao-wei-wudi-ji` | `魏武帝集` / *Collected Works of Cao Cao* | 170 | 255 | 260 | Complete root-page collection, volumes 1-4 |
| 2 | `cao-pi-wei-wendi-ji` | `魏文帝集` / *Collected Works of Cao Pi* | 52 | 75 | 76 | Complete root-page collection |
| 3 | `cao-zhi-cao-zijian-ji` | `曹子建集` / *Collected Works of Cao Zhi* | 219 | 266 | 289 | Complete volumes 1-10 |

Each task has:

- `books/<task-id>/book-plan.json`
- `books/<task-id>/markdown/wenyan.md`
- `books/<task-id>/work/quadrilingual/chunks/manifest.json`
- a local ignored `chunks.jsonl` beside the manifest

## Source Inventory

| Work | Role | Pages | Local path | SHA-256 |
| --- | --- | ---: | --- | --- |
| Cao Cao | Searchable public witness | 36 | `sources/jianan-literature/cao-cao/wenyan/book/魏武帝集-曹操.pdf` | `9eb2c61f431eb624fcb4184056538c7e2cc3eea21558ddd69b5204a41099db5c` |
| Cao Cao | Private annotated reference | 352 | `sources/jianan-literature/cao-cao/zh-modern/annotated-reference/建安文学全书-曹操集校注.pdf` | `bf19f99af825eecdf5d4b60d4c90cec022d1b6dc760ec94829756c3452773502` |
| Cao Pi | Searchable public witness | 19 | `sources/jianan-literature/cao-pi/wenyan/book/魏文帝集-曹丕.pdf` | `89dd553bf16d6298d562ce20ea4ce13f291ea41491c13a80f799a44ede1f1a4d` |
| Cao Pi | Private annotated reference | 351 | `sources/jianan-literature/cao-pi/zh-modern/annotated-reference/建安文学全书-曹丕集校注.pdf` | `2b7894a4efef4b931e1a642a72dc17563a72e94fc60121cc47721cd01d7c698b` |
| Cao Zhi | Searchable public witness | 110 | `sources/jianan-literature/cao-zhi/wenyan/book/曹子建集-曹植.pdf` | `cb1e01c51ef6ba2a91803e508e2f6333c7eaecf30a07e4477d13c9425e84f27a` |
| Cao Zhi | Private annotated reference | 540 | `sources/jianan-literature/cao-zhi/zh-modern/annotated-reference/曹植全集-汇校汇注汇评.pdf` | `8ed7963d0a5a2a8e21d5a04c76e63272cdd6a989e682573e40d861f98f50f5f5` |

The canonical text trees, including raw wikitext, rendered HTML, and manifests,
are under each work's `wenyan/wikisource/` directory. The copied source assets
are ignored and are not committed.

## Source And Translation Policy

- The sectioned Chinese Wikisource tree is the authoritative source spine.
- Work-level and nested headings are retained instead of flattening a whole
  collection into one generic chapter.
- Source `<br>` boundaries are retained where they encode verse lines.
- Cao Zhi volume pages are sorted by Chinese-number volume labels, not by
  download filename.
- The annotated Chinese scans are collation and interpretation references. They
  require OCR and passage alignment before their prose may enter a prompt.
- No full local English or Japanese edition was found. English and modern
  Japanese are generated from the verified wenyan source, informed by aligned
  Chinese notes only where evidence exists.
- Duplicate historical work titles are retained because their source texts are
  distinct; chunk and chapter IDs remain unique.

## Validation

The preparation audit verified:

- every split chunk exactly matches the ordered source text;
- every Markdown spine exactly matches the extracted source sections;
- all chunk and paragraph IDs are unique;
- all ten Cao Zhi volumes occur in canonical order;
- no `#重定向`, Wikisource chrome, HTML, or wiki markup appears in task text;
- no private annotation prose was copied into generated task content;
- every chunk carries the task-specific translation policy;
- source Markdown hashes match their manifests.

Regression coverage is in:

`scripts/interlinear/test_prepare_classical_quadrilingual_task.py`

Runtime state is written to `books/_queues/three-caos/state.json`. Covers and
final PDF export remain post-generation work.
