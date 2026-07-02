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
