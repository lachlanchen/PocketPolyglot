# README Preview Assets

These PNGs are first-page previews rendered from local flat PDF exports with:

```sh
make readme-previews
```

The script reads `build/books/manifest.json`, picks the `zh-main` / `color` edition for each book when available, and writes a compact preview plus `manifest.json`. Do not treat these previews as full book assets; full PDFs should only be published when source and translation rights allow redistribution.
