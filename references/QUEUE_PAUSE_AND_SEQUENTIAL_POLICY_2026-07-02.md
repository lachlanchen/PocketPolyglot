# Queue Pause And Sequential Policy - 2026-07-02

The user asked to stop all current LinguaLeaf/PocketPolyglot background book
tasks and continue future work one book at a time, with Bible and Quran at the
end of the queue.

## Stopped Sessions

These tmux sessions were stopped:

| Session | Book | Role |
| --- | --- | --- |
| `zhjpbook-bible-10-low` | `bible` | Trilingual writer |
| `zhjpbook-bible-10-low-repair` | `bible` | Stall repair / reviewer |
| `zhjpbook-manyoshu-10-low` | `manyoshu` | Trilingual writer |
| `zhjpbook-manyoshu-10-low-repair` | `manyoshu` | Stall repair / reviewer |

Remaining matching ZhJpBook pipeline workers and compilers were checked after
the stop. No matching `scripts/interlinear`, `xelatex`, `xdvipdfmx`, or
`zhjpbook-*` book task process remained.

## Saved Progress

| Book | Manifest | Valid | Missing | Stale | First missing |
| --- | ---: | ---: | ---: | ---: | --- |
| `bible` | 2113 | 624 | 1489 | 0 | `bible-chunk-00625` |
| `manyoshu` | 4562 | 3106 | 1456 | 0 | `manyoshu-chunk-3107` |

`zhuangzi` was also checked because the status table still said it was running.
It has no active worker and reports `892/892` valid chunks; large-font color
and black-white PDFs exist.

## Future Run Rule

Run only one book at a time unless the user explicitly asks for a parallel
batch. A book run should finish the full loop before the next book starts:

1. Generate or resume chunk JSON.
2. Review and sanitize existing plus new chunks without deleting valid data.
3. Compile color and black-white PDFs.
4. Sync final PDFs to the requested folders.
5. Commit durable tracked artifacts and status notes.

Bible and Quran stay at the end. Quran Arabic-main is already complete; any
reverse-main Quran editions wait until the other active queue work is complete
and the user explicitly asks for them.

## Nutstore Share Rule

`/home/lachlan/Nutstore Files/Share/LinguaLeaf` is a public browsing folder and
should contain only maximum-language large-font editions. Do not put the 12
intermediate pair PDFs there by default.

Allowed public Share families:

- `wenyan-en-jp-zh`: classical Chinese source, English, modern Japanese, modern Chinese.
- `wayakana-en-jp-zh`: Japanese classical/waka/kana source, English, modern Japanese, modern Chinese.
- `en-jp-zh`: modern English/Japanese/Chinese maximum-language edition.
- `jp-zh`: bilingual maximum-language fallback when no English layer exists.
- `ar-en-jp-zh`: Arabic source, English, modern Japanese, modern Chinese.

In these labels, `jp` and `zh` mean modern Japanese and modern Chinese unless
an explicit source layer such as `wenyan`, `wayakana`, or `ar` is present.
Pair-only PDFs may be copied to
`/home/lachlan/Nutstore Files/NoSync/Projects/LinguaLeaf` for archival
browsing, but Share should stay maximum-language only. Do not recreate
`/home/lachlan/Nutstore Files/Projects/LinguaLeaf`.

For `wayakana-*` books, the public maximum-language edition must not use
English as the main text. The original Japanese source layer, such as waka/kana
or classical Japanese prose, is the main stream, matching the way `wenyan-*`
uses the original Chinese source as the main stream. If a separate modern
Japanese layer has not yet been backfilled, publish source Japanese with the
available English and modern Chinese notes, and keep the edition path explicit
as `wayakana-main-en-zh` rather than relabeling an English-main PDF.
