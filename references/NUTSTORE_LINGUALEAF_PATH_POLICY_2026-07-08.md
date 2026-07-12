# Nutstore LinguaLeaf Path Policy - 2026-07-08

The LinguaLeaf project export folder has been moved into Nutstore `NoSync`:

`/home/lachlan/Nutstore Files/NoSync/Projects/LinguaLeaf`

Use `scripts/books/nutstore_paths.py` for new sync/export scripts.

Do not use or recreate the old synced project path:

`/home/lachlan/Nutstore Files/Projects/LinguaLeaf`

## Default Resolution

Project exports prefer the first existing path, and default to the `NoSync`
path when none exists:

1. `/home/lachlan/Nutstore Files/NoSync/Projects/LinguaLeaf`
2. `/home/lachlan/Nutstore Files/NOSync/Projects/LinguaLeaf`
3. `/home/lachlan/Nutstore Files/No Sync/Projects/LinguaLeaf`

Share exports remain:

`/home/lachlan/Nutstore Files/Share/LinguaLeaf`

## Share Eligibility

Nutstore Share is for maximum-language public editions only. Do not sync
lower-priority fallback PDFs when a richer language family already exists for
the same book. If the richest completed family is `jp-zh`, then `jp-zh` is the
maximum-language public edition and should be synced to Share. Later, if an
`en-jp-zh` or quadrilingual edition is completed, remove the older lower-family
Share PDFs during the new sync.

## Environment Overrides

- `NUTSTORE_ROOT`
- `LINGUALEAF_NUTSTORE_PROJECT`
- `LINGUALEAF_PROJECT_ROOT`
- `LINGUALEAF_NUTSTORE_SHARE`
- `LINGUALEAF_SHARE_ROOT`

Current running jobs may still write to the old path if they started before
this policy was updated. New Python sync scripts must follow the resolver.
