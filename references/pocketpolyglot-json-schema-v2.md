# PocketPolyglot JSON Schema v2

This repository keeps old generated fields intact and adds a small schema
contract around them. The goal is to remove ambiguity without deleting expensive
language work.

## Rule

Chunk JSON is append-only. Existing fields such as `zh`, `zh_original`,
`zh_modern`, `ja`, `ja_modern`, `en`, `jie`, `zhu`, `explanation`, ruby, pinyin,
and grammar roles must be preserved unless a human explicitly asks to rewrite
that field.

## Canonical Layers

Renderers and workers should interpret legacy fields through these layers:

| Layer | Field | Meaning |
| --- | --- | --- |
| `wenyan` | `zh_original` or classical `zh` | Classical Chinese source text |
| `zh` | `zh` | Modern Chinese source/translation for normal books |
| `zh_modern` | `zh_modern` | Readable modern Chinese bridge for classical texts |
| `ja` | `ja` | Existing Japanese source, gloss, or legacy aligned text |
| `ja_modern` | `ja_modern` | Reader-friendly modern Japanese overlay |
| `en` | `en` | Reader-friendly English overlay |
| notes | `jie`, `zhu`, `explanation`, `comment`, `note` | Extra commentary/explanation; never delete silently |

## Japanese Line Roles

`ja` can be either a flat token list or a list of semantic line arrays. When it
is a list of line arrays, `ja_line_roles` must disambiguate the meaning:

- `translation`: main Japanese translation line;
- `continuation`: continuation of the same Japanese sentence;
- `gloss`: kanbun/classical-style gloss;
- `modern_explanation` or `explanatory_comment`: separate explanatory layer;
- `note`, `zhu`, `annotation`: true note/comment layer.

Do not use a second Japanese line as a physical line break. Long continuous text
should be one semantic translation with `continuation` only for legacy split
data. A renderer may merge `translation + continuation`, but must separate
`explanatory_comment`.

## Book Profiles

Modern bilingual books use:

```text
zh / ja / optional en
```

Modern trilingual books use:

```text
en / zh / ja
```

Classical Chinese books use:

```text
wenyan / ja / zh_modern / en / optional notes
```

If `zh_modern` is missing, backfill it before generating English or modern
Japanese. For Shiji-style chunks that already contain `zh_original` and
`zh_modern`, generate English from `zh_modern` and preserve existing Japanese.

## Migration

Use:

```sh
python scripts/interlinear/migrate_interlinear_json_schema.py --dry-run
python scripts/interlinear/migrate_interlinear_json_schema.py
```

The script backs up changed files under `backups/` before rewriting. Backups are
local and ignored by Git.
