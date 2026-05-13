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
