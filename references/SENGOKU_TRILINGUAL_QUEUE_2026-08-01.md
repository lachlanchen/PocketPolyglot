# Sengoku History Trilingual Queue - 2026-08-01

This handoff organizes the supplied Sengoku-period books for modern English,
Japanese, and Chinese PocketPolyglot editions. Source files are local ignored
assets under `sources/`; they are not committed to Git. The machine-readable
queue is `data/source-plan/sengoku-history-trilingual-queue.json`.

## Quality Order And Readiness

The order prioritizes source value and historical scholarship. Historical
novels remain useful reading projects, but they are explicitly separated from
historical evidence.

| Priority | Book | Role / quality | Preparation status | Chunks | Chapters |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | `The Chronicle of Lord Nobunaga` / `信長公記` | A+ scholarly English translation of a primary source | Launchable | 465 | 18 |
| 2 | `Japan Emerging: Premodern History to 1850` | A modern academic survey | Blocked: page-aware outline segmentation required | 0 | 0 |
| 3 | Mary Elizabeth Berry, `Hideyoshi` | A scholarly monograph | Launchable | 292 | 9 |
| 4 | George Sansom, `A History of Japan, 1334-1615` | A- classic synthesis; dated in places | Launchable | 521 | 26 |
| 5 | Jeroen P. Lamers, `Japonius Tyrannus` | A- focused modern scholarship | Blocked: image-only OCR and heading review required | 0 | 0 |
| 6 | Conrad D. Totman, `Tokugawa Ieyasu: Shogun` | A- scholarly biography | Blocked: image-only OCR and heading review required | 0 | 0 |
| 7 | Stephen Turnbull, `The Samurai Sourcebook` | B+ comprehensive illustrated reference | Blocked: structured OCR required | 0 | 0 |
| 8 | Stephen Turnbull, `War in Japan 1467-1615` | B+ concise illustrated military history | Blocked: two-column page-aware extraction required | 0 | 0 |
| 9 | Stephen Turnbull, `Samurai: The World of the Warrior` | B illustrated thematic overview | Blocked: two-column page-aware extraction required | 0 | 0 |
| 10 | Noel Perrin, `Giving Up the Gun` | B readable but historically disputed thesis | Blocked: headings and illustrations require page-aware review | 0 | 0 |
| 11 | Eiji Yoshikawa, `Taiko` | A historical novel; not historical evidence | Launchable | 1,093 | 56 |
| 12 | Yamaoka Sohachi, `Tokugawa Ieyasu` | A historical novel in Chinese translation; not historical evidence | Launchable | 1,054 | 445 |

The old 79-chunk extraction for `War in Japan 1467-1615` is retained as
provisional evidence only. Its two visual columns were interleaved with captions,
so those chunks must not be sent to a translation model.

## Organized Modern Sources

| Work | Local source path |
| --- | --- |
| `The Chronicle of Lord Nobunaga` | `sources/japan-history/sengoku/primary-source-translations/shincho-koki/en/The Chronicle of Lord Nobunaga - Ota Gyuichi.pdf` |
| `Japan Emerging` | `sources/japan-history/sengoku/surveys/en/Japan Emerging - Premodern History to 1850 - Karl F Friday.pdf` |
| `Hideyoshi` | `sources/japan-history/sengoku/biographies/hideyoshi/en/Hideyoshi - Mary Elizabeth Berry.pdf` |
| `A History of Japan, 1334-1615` | `sources/japan-history/sengoku/surveys/en/A History of Japan 1334-1615 - George Sansom.pdf` |
| `Japonius Tyrannus` | `sources/japan-history/sengoku/biographies/nobunaga/en/Japonius Tyrannus - Jeroen P Lamers.pdf` |
| `Tokugawa Ieyasu: Shogun` | `sources/japan-history/sengoku/biographies/tokugawa-ieyasu/en/Tokugawa Ieyasu - Shogun - Conrad Totman.pdf` |
| `The Samurai Sourcebook` | `sources/japan-history/sengoku/reference-works/en/The Samurai Sourcebook - Stephen Turnbull.pdf` |
| `War in Japan 1467-1615` | `sources/japan-history/sengoku/military-history/en/War in Japan 1467-1615 - Stephen Turnbull.pdf` |
| `Samurai: The World of the Warrior` | `sources/japan-history/sengoku/military-history/en/Samurai - The World of the Warrior - Stephen Turnbull.pdf` |
| `Giving Up the Gun` | `sources/japan-history/sengoku/military-history/en/Giving Up the Gun - Noel Perrin.pdf` |
| `Taiko` | `sources/japan-history/sengoku/historical-fiction/taiko/en/Taiko - Eiji Yoshikawa.epub` |
| `Tokugawa Ieyasu` | `sources/japan-history/sengoku/historical-fiction/tokugawa-ieyasu/zh/德川家康大全集 - 山冈庄八.epub` |

## Public Japanese Source Evidence

| Work | Searchable / scan evidence |
| --- | --- |
| `信長公記` | `sources/japan-history/sengoku/primary-sources/shincho-koki/ja-book/信長公記-太田牛一.pdf`; Wikisource manifest and three 1881 NDL scan volumes are retained beside it |
| `太閤記` | `sources/japan-history/sengoku/primary-sources/taikoki/ja-book/太閤記-小瀬甫庵.pdf`; a 21-record Wikisource tree is retained beside it |
| `甲陽軍鑑` | `sources/japan-history/sengoku/primary-sources/koyo-gunkan/ja-book/甲陽軍鑑.pdf`; a 61-record Wikisource tree and Waseda scan are retained beside it |
| `難波戦記` | Three NDL scans under `sources/japan-history/sengoku/primary-sources/naniwa-senki/ja-ndl-scan/` |

These sources are evidence and terminology references. They are not assumed to
be sentence-aligned with every modern English source. The Yamaoka and Yoshikawa
novels must never be used to fill gaps in scholarly claims.

## Generation Contract

- Output shape: English source/main text with readable modern Japanese and
  modern Chinese, later promoted to token JSON with Japanese ruby, Chinese
  pinyin, and color-capable grammar roles.
- Preserve every source unit and paragraph in order. Do not summarize, omit,
  merge unrelated units, or introduce unsupported historical claims.
- Preserve scholarly notes as notes and distinguish them from the translated
  primary text.
- Unmapped Latin-script personal names stay unchanged in Chinese. Japanese uses
  stable katakana, or the Latin spelling when uncertain; the model must not
  invent Chinese characters or kanji for personal names. Institutions and
  places use an established translation or transparent transliteration.
- A per-book terminology sheet overrides fallback name behavior. For the first
  book it fixes `Lord Nobunaga` as `信長公` / `信长公`, `Initial Book` as `首巻`
  / `首卷`, and verifies `Paul Yachita Tsuchihashi` as `土橋八千太` / `土桥八千太`.
- Historically meaningful terms are required and validator-gated. Ordinary
  transliteration choices may be marked `preferred`, so a harmless natural
  variant cannot trigger wasteful whole-chunk regeneration.
- Final book work includes a table of contents, maximum-language large-font
  color and black-white editions, cover validation, overflow checks, and
  explicit evidence before completion.

## Model And Escalation Policy

1. Pilot two chunks with one worker before bulk generation.
2. Start with `gpt-5.4-mini` at low reasoning only when the pilot is both
   structurally valid and semantically consistent.
3. If low reasoning drifts in terminology or naturalness, use
   `gpt-5.4-mini` at medium for that book.
4. Escalate only failed or semantically uncertain chunks to `gpt-5.6-sol` low;
   never regenerate a whole accepted book merely because one unit needs repair.
5. Bulk generation runs one book at a time with three claim-safe workers.

## Pilot Evidence

- The first low-reasoning pilot passed structural validation but translated
  `Lord Nobunaga` as the false title `信长公爵`. The new terminology validator
  rejects that output.
- A clean low-reasoning pilot then passed schema checks but drifted between
  `ラメルス` and `ラーマース` and produced the redundant phrase `全訳英訳`.
- A medium-reasoning pilot improved naturalness and consistency, but exposed a
  general unsafe-name behavior in Chinese. The worker now explicitly forbids
  invented character spellings for unmapped Latin names.
- Name authority checks use the National Diet Library/CiNii records for
  [土橋八千太](https://id.ndl.go.jp/auth/ndlna/00086909) and
  [Japanese Chronological Tables](https://ci.nii.ac.jp/ncid/BA14297025).

Pilot archives are preserved under
`books/chronicle-lord-nobunaga/work/trilingual/parallel-json.pilot-*` so model
selection remains auditable.

## Validation

```sh
python3 -m py_compile \
  scripts/interlinear/prepare_modern_nonfiction_trilingual.py \
  scripts/interlinear/codex_trilingual_plain_json_worker.py \
  scripts/interlinear/validate_trilingual_interlinear_json.py

python3 scripts/interlinear/test_prepare_modern_nonfiction_trilingual.py
python3 scripts/interlinear/test_codex_trilingual_plain_json_worker.py
```

The first book's pilot/session logs live under
`books/chronicle-lord-nobunaga/work/trilingual/parallel-json/logs/`.
