# Meditations Trilingual Task - 2026-08-03

## Scope

Prepare a maximum-language PocketPolyglot edition of Marcus Aurelius's
*Meditations* with English as the preserved main layer, readable modern
Japanese and modern Chinese as aligned secondary layers, normalized grammar
roles, and eventual large-font color and black-white PDFs.

The task covers the twelve books of the work itself. The Project Gutenberg
editorial introduction, appendix, notes, glossary, boilerplate, and license are
not part of the aligned main text.

## Local Sources

| Role | Path | Validation |
| --- | --- | --- |
| Immutable English spine | `sources/philosophy/stoicism/meditations/en/Meditations - George Long - Project Gutenberg.epub` | Valid EPUB; SHA-256 `963f8b817a94986bb999caa1f9cd200b328690379fb3df17c08d557c356aad72` |
| English page reference | `sources/philosophy/stoicism/meditations/en/Meditations - George Long - Project Gutenberg.pdf` | Searchable public-domain PDF; SHA-256 `4a29cc6eaf44fd3164e36a298ac36cc01d1b8c718d73d7c012f6130a8d492912` |
| English structural reference | `sources/philosophy/stoicism/meditations/en/Meditations - George Long - Project Gutenberg.html` | Gutenberg HTML copied with the EPUB |
| Chinese-English visual reference | `sources/philosophy/stoicism/meditations/zh-en/沉思录 - 中英双语典藏本.pdf` | 433-page image-only scan; SHA-256 `d5245431d05531695061b42d4f5d2a6677afb70183232564e96489ec7432fc9c` |

The bilingual scan's text layer contains only page breaks. It is registered as
valuable visual evidence, but raw OCR from it must not be treated as reviewed
translation text. A later OCR/alignment pass may promote verified Chinese
passages incrementally without deleting generated data.

## Prepared Contract

- Queue: `data/source-plan/meditations-trilingual-queue.json`
- Book id: `meditations-marcus-aurelius`
- Queue position: first (`priority: 1`, `queue_position: 1`)
- Execution policy: manual launch only (`autostart: false`)
- Source boundary: `THE FIRST BOOK` through the end of `THE TWELFTH BOOK`
- Model preference: `gpt-5.6-sol`, low reasoning
- Worker preference: `3`
- Task preparation itself does not start generation.

## Runtime

The prepared task was started manually on 2026-08-07 at 19:32 HKT with three
workers, `gpt-5.6-sol`, and low reasoning. The persistent sessions are:

- writer: `zhjpbook-meditations-marcus-aurelius-gpt56-low`;
- stall repair: `zhjpbook-meditations-marcus-aurelius-gpt56-low-repair`;
- autorepair: `zhjpbook-meditations-marcus-aurelius-gpt56-low-autorepair`.

The launch remains resumable and does not enable queue autostart for any other
book.

Completion requires current-manifest coverage with no missing or stale chunks,
all twelve books in order, strict trilingual JSON validation, a meaningful TOC,
and maximum-language large-font color and black-white exports.

## Preparation Evidence

The generic modern-prose preparer was run only after adding an explicit heading
contract for `THE FIRST BOOK` through `THE TWELFTH BOOK`. The first diagnostic
pass exposed that these source headings were not recognized by the generic
`Book I` pattern; the final task was regenerated rather than accepting a flat
one-chapter manifest.

Final prepared state:

- 12 source chapters;
- 144 stable chunks (`c0001` through `c0144`);
- 600 unique source paragraph ids with no duplication;
- no appendix, notes, glossary, Gutenberg boilerplate, or HTML fragments;
- no writer, reviewer, or model process was started by the preparation step.
