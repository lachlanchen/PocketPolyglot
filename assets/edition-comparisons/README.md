# Edition Comparison Assets

These images show the same interior page rendered across the standard four PocketPolyglot editions:

- ZH main / color
- ZH main / black and white
- JP main / color
- JP main / black and white

Regenerate the Kokoro comparison with:

```sh
make edition-comparison
```

Regenerate the single JP-main sentence showcase with:

```sh
make sentence-showcase
```

The comparison uses true PDF page 20 from the local flat PDF export because it shows continuous reading text, ruby/furigana, pinyin, and grammar color clearly.

The default composite is rendered at 300 DPI with 760 px panels, producing a high-resolution image suitable for opening at full size from the README.
