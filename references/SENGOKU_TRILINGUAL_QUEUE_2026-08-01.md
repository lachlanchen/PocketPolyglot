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
| 1 | `The Chronicle of Lord Nobunaga` / `信長公記` | A+ scholarly English translation of a primary source | Rebuilt after source-cleaning repair; 11/471 retained and a fresh chunks 12--16 pilot is required before bulk resume | 471 | 18 |
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

1. Pilot repaired failure-boundary chunks with one worker before bulk generation.
2. The `gpt-5.4-mini` low and medium pilots are rejected for this queue.
3. Use `gpt-5.6-sol` at low reasoning for the new pilot and bulk work only after
   semantic inspection passes; use `gpt-5.5` low only as an availability fallback.
4. Regenerate only failed or semantically uncertain chunks; never regenerate a
   whole accepted book merely because one unit needs repair.
5. Bulk generation runs one book at a time with three claim-safe workers in an
   observable, resumable tmux session.

## Pilot Evidence

- The first low-reasoning pilot passed structural validation but translated
  `Lord Nobunaga` as the false title `信长公爵`. The new terminology validator
  rejects that output.
- A clean low-reasoning pilot then passed schema checks but drifted between
  `ラメルス` and `ラーマース` and produced the redundant phrase `全訳英訳`.
- A medium-reasoning pilot improved naturalness and consistency, but exposed a
  general unsafe-name behavior in Chinese. The worker now explicitly forbids
  invented character spellings for unmapped Latin names.
- The first bulk attempt exposed three additional quality failures: `s. v.
  Tôzan` was split at an abbreviation boundary, one Japanese unit introduced
  Devanagari `विषय`, and ruby promotion duplicated Latin names containing
  macrons or cedillas. The queue was stopped before further generation. Shared
  deterministic repairs and regression tests now cover all three cases.
- The repaired `gpt-5.6-sol` low pilot passed chunks 3--6. It restored `年表`,
  kept `s. v. Tôzan` together, preserved quoted Japanese source phrases in
  Chinese, emitted no unrelated scripts, and reconstructed macron-bearing Latin
  names exactly. A manual authority review caught and repaired `Hino Hiroshi`
  as `日埜博司` before the bulk tmux run was approved.
- The first bulk semantic sample found `Sōtai`, the Chinese-derived name for
  the Censorial Board (`弾正台`), mistranslated as the unrelated word
  `総代` / `总代`. The run was stopped after chunk 10. The per-book terminology
  contract now requires `霜台`, retains `弾正台`, `弾正忠`, and `御史`, and
  regenerates only affected chunk 8 rather than discarding valid work.
- Monitoring the next bulk sample exposed an extraction defect rather than a
  translation defect: alternating page headers occurred both as `header 17`
  and `18 header`, while the old shared cleaner recognized only the first
  direction. The run was stopped before further promotion. The generic cleaner
  now removes only repeated exact bases in both directions, with a regression
  test that preserves real headings such as `BOOK I`.
- Chronology and list paragraphs used em dashes rather than sentence-final
  punctuation, producing source units as long as 10,459 characters. The shared
  splitter now uses lossless boundary-aware subdivision. The rebuilt manifest
  has 471 chunks and 2,252 source units, every unit is at most 900 characters,
  and concatenating the split units reproduces the cleaned source text.
- The same pilot showed that a structurally valid translation could still spell
  familiar Japanese historical names wholly in katakana. Shared model guidance
  now requires conventional kanji/kana for confidently identified Japanese
  historical people and titles, while preserving romanization when uncertain.
  Verified first-book spellings such as `織田吉法師`, `今川義元`, `斎藤道三`,
  `足利義昭`, `朝倉義景`, and `浅井長政` live in the project terminology sheet,
  not in shared worker code.
- Flattened dot-leader lists are now reconstructed deterministically before
  model calls: for example, `Map 1. Owari Province ... 52` becomes one clean
  source unit, rather than shifting page 52 onto the following map entry.
- Valid chunks 1--10 remain current. Pre-repair candidates, rejected attempts,
  and stale chunks 11--12 are archived under the book work tree; no generated
  translation was silently deleted or reused against a changed source unit.
- Name authority checks use the National Diet Library/CiNii records for
  [土橋八千太](https://id.ndl.go.jp/auth/ndlna/00086909) and
  [Japanese Chronological Tables](https://ci.nii.ac.jp/ncid/BA14297025).
- The repaired pilot also authority-checks [島正三](https://ci.nii.ac.jp/ncid/BN06202998),
  [日埜博司](https://ndlsearch.ndl.go.jp/search?cs=bib&from=0&q-author=%22%E6%97%A5%E5%9F%9C%2C+%E5%8D%9A%E5%8F%B8%22&size=20),
  and [大塚光信](https://ndlsearch.ndl.go.jp/books/R100000147-I900023643)
  rather than allowing the model to invent kanji spellings.
- The `Sōtai` correction is authority-checked against the
  [Kotobank entry for 霜台](https://kotobank.jp/word/%E9%9C%9C%E5%8F%B0-2056642).
  The historical reading and spelling of `Danjō no Jō` are checked against the
  [Kotobank entry for 弾正の忠](https://kotobank.jp/word/%E5%BC%BE%E6%AD%A3%E3%81%AE%E5%BF%A0-2061026).

Pilot archives are preserved under
`books/chronicle-lord-nobunaga/work/trilingual/parallel-json.pilot-*` so model
selection remains auditable.

## Local Extraction Preflight

A local Marker/Surya sample was run over the preface pages and compared with
embedded `pdftotext` extraction. Marker preserved emphasis and joined
page-spanning prose, but also inserted running headers such as `preface xi` and
`xii preface` into sentences. For this born-digital prose book, cleaned embedded
text is therefore the higher-fidelity translation spine. The cleaner now
recognizes repeated page heads whether the page number precedes or follows the
header, and long timeline/list units are losslessly bounded before model calls.
The shared structured
local extraction remains required for two-column, scanned, illustrated, and
figure-bearing books later in the queue.

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
