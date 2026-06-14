# Incremental English and Modern Japanese Overlay Plan

This plan prepares new language overlays for older PocketPolyglot books without
rewriting or deleting any existing JSON. It is preparation only: no writer,
reviewer, tmux worker, or model call is started by this plan.

## Goal

Older bilingual books should gain understandable English. Classical Chinese
books should use a modern Chinese bridge first when it is missing, then generate
English and, when requested, modern readable Japanese from that bridge. The
Sichuan folk story volume should gain modern, readable Japanese based on the
corrected Chinese text.

## Prepared Task Data

Global manifest:

```text
data/source-plan/incremental-english-modern-japanese.json
```

Per-book manifests and task lists:

```text
data/source-plan/incremental-en-modern-ja/<book-id>/manifest.json
data/source-plan/incremental-en-modern-ja/<book-id>/tasks.jsonl
```

Each JSONL row is one chunk task. The old chunk JSON is read-only. New work must
write overlay files, then merge only after validation.

## Output Policy

Work outputs should be written first to:

```text
books/<book-id>/work/incremental/en-modern-ja/overlays/chunks/<chunk-id>.json
```

After validation, durable overlays may be copied to:

```text
data/interlinear-overlays/en-modern-ja/<book-id>/chunks/<chunk-id>.json
```

The merge policy is additive:

- preserve all existing fields exactly;
- add `zh_modern` for classical Chinese books when no reliable modern Chinese
  bridge exists;
- add `en` for clear, natural English;
- add `ja_modern` only for classical Chinese, difficult kanbun-style Japanese,
  or OCR-corrected Chinese folk text;
- never overwrite legacy `ja`, `zh`, `zh_modern`, `corrected_text`, ruby,
  grammar, or source alignment fields.

## Source Priority

When generating English or modern Japanese, prefer stable existing fields in
this order:

```text
overlay.zh_modern > zh_modern > corrected_text > zh_original > zh > source_text
```

For Japanese source comparison, use the existing `ja` field as a reference, but
do not assume it is reader-friendly when the task asks for `ja_modern`.

## Prepared Scope

English overlays are prepared for all listed older books. Modern Chinese is
explicitly prepared for:

- `sishu-jizhu`
- `sishu-jizhu-aginti`

Modern Japanese is also prepared for:

- `sichuan-folk-stories-vol1`
- `sishu-jizhu`
- `sishu-jizhu-aginti`
- `kojiki`

`shiji-aginti` already has `zh_original` and `zh_modern`; the current
incremental task only backfills English and preserves existing Japanese.

`ginga-tetsudo` and `chumon-no-ooi-ryoriten` are listed with a dependency on
their current bilingual completion, so they should not be consumed until their
base bilingual chunks are complete.

## Validation Requirements

Before accepting any overlay chunk:

- the chunk id must match the source chunk;
- the source text must not be shortened or silently omitted;
- `zh_modern`, when requested, must be accurate, readable modern Chinese and
  must not replace the classical source field;
- English must be natural and complete;
- `ja_modern` must be modern, understandable Japanese, not only kana or a
  kanbun gloss;
- kanji in `ja_modern` should have furigana/ruby data when the renderer expects
  it;
- grammar roles, if added later, must use the unified English role names already
  used by the renderer.

## Usage Budget Gate

The tmux launcher can be configured to avoid consuming quota when remaining
Codex usage is too low. Example:

```sh
MIN_CODEX_REMAINING_PERCENT=50 \
CODEX_USAGE_STATUS_FILE=books/_incremental-overlays/work/usage-status.json \
bash scripts/interlinear/start_incremental_overlay_tmux.sh
```

The status file may contain `weekly_remaining_percent`, `remaining_percent`, or
similar numeric keys. If a threshold is configured and no usable usage source is
available, workers stop with retry code `86` and the tmux supervisor waits before
trying again.
