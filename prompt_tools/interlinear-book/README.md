# Interlinear Book Pipeline

This prompt tool converts an EPUB into cleaned Markdown, chunks the Markdown by
section/story/paragraph, asks a single resumable `codex exec` session to create
Chinese-main/Japanese-comment JSON, validates source preservation, assembles the
book JSON, compiles the pocket PDF, and commits tracked results.

Default run for `sources/心.epub`:

```sh
prompt_tools/interlinear-book/start-book-tmux.sh --kill --no-attach -- \
  --epub sources/心.epub \
  --book-id kokoro \
  --title-zh 心 \
  --title-zh-reading xīn \
  --title-ja 心 \
  --title-ja-reading こころ \
  --model gpt-5.5 \
  --reasoning high
```

Attach or inspect logs:

```sh
tmux attach -t zhjpbook-interlinear
tail -f books/kokoro/work/logs/*.log
```

If the job is interrupted after a Codex session has already been created, restart
with `--resume-last` after the `--` separator. Existing valid chunk JSON files
are skipped automatically.

## Bilingual Japanese Source Mode

Use this mode when a Chinese translation and the Japanese original are both
available. The Chinese text remains the main continuous text; Codex uses the
Japanese source Markdown as the comment source instead of freely translating the
Chinese.

```sh
prompt_tools/interlinear-book/start-bilingual-book-tmux.sh --kill --no-attach -- \
  --zh-epub sources/心.epub \
  --jp-epub "sources/夏目 漱石 作品全集.epub" \
  --book-id kokoro \
  --title-zh 心 \
  --title-zh-reading xīn \
  --title-ja こころ \
  --title-ja-reading こころ \
  --model gpt-5.5 \
  --reasoning xhigh \
  --output-pdf "build/interlinear-block/心（こころ）.pdf"
```

The pipeline writes extracted source Markdown to `books/kokoro/markdown/zh.md`
and `books/kokoro/markdown/ja.md`, chunk work under
`books/kokoro/work/bilingual/`, assembled JSON to
`data/interlinear/kokoro/assembled/current.json`, reusable paragraph artifacts to
`data/interlinear/kokoro/artifacts/paragraphs/`, and a named pocket PDF to
`build/interlinear-block/心（こころ）.pdf`. By default it also compiles a partial
preview PDF after every newly completed chunk.

## Image-Only Japanese EPUBs

`sources/こころ.epub` is a fixed-layout manga adaptation
(`こころ -まんがで読破- 1巻`), not a selectable-text Japanese novel EPUB. Convert
it separately with OCR when you need review Markdown:

```sh
make kokoro-jp-ocr-md
```

That writes page-based OCR Markdown to `books/kokoro-jp/markdown/book.md`. It is
useful for inspection, but the faithful interlinear novel pipeline should use a
Japanese text source such as chapter 25 from `sources/夏目 漱石 作品全集.epub`.
