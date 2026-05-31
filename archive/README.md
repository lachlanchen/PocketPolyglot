# Archive

This folder keeps historical outputs that are useful for reference but are no
longer part of the active book build layout.

Active book PDFs should use the current structure:

```text
build/<book-slug>/<zh-main|jp-main>/<color|blackwhite>/<book-name>.pdf
```

The archived build material is grouped by purpose:

- `build/legacy-layouts/` keeps old global-layout PDFs and sample outputs.
- `build/previews/` keeps local preview images and smoke-test output; it is
  ignored because those files are bulky and regenerable.

