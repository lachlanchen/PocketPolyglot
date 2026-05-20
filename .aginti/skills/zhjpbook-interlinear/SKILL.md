---
id: zhjpbook-interlinear
label: ZhJpBook Chinese-Japanese Interlinear Pipeline
description: Project-local rules for this repository's Chinese/Japanese pocket books, including JP-main and ZH-main render variants, ruby/pinyin JSON, grammar coloring, and source-preserving validation.
triggers:
  - ZhJpBook
  - zhjpbook
  - zh-jp
  - jp-main
  - zh-main
  - Chinese Japanese
  - furigana
  - pinyin
  - Shiji
  - Sishu
tools:
  - read_file
  - write_file
  - run_command
  - tmux_start_session
  - tmux_capture_pane
---
# ZhJpBook Chinese-Japanese Interlinear Pipeline

Use this skill only inside `/home/lachlan/ProjectsLFS/ZhJpBook` or a direct fork of this repository. It contains project-specific choices that should not be copied into AgInTiFlow core.

## Repository Rules

- Read `AGENTS.md` before editing.
- Do not commit original PDFs, EPUBs, or large raw files from `sources/`.
- Keep raw sources, cleaned Markdown, JSON chunks, TeX renderers, PDFs, logs, and status files in their existing repository areas.
- Commit tracked scripts, TeX, stable JSON, and named PDF checkpoints after meaningful edits.

## Data Contract

Promoted chunk JSON uses short token fields:

- `t`: visible token text.
- `r`: reading, pinyin for Chinese/Hanzi or furigana for Japanese/kanji.
- `g`: one grammar role: `subject`, `predicate`, `object`, `attributive`, `adverbial`, `complement`, `topic`, or `function`; punctuation may use `""`.

For normal modern novels, show only the original JP and translated ZH unless the user explicitly asks for additional notes. For classical Chinese projects such as Shiji or Sishu, use the three-layer structure:

- `zh_original`: source Classical Chinese by the original author.
- `ja`: Japanese correspondence or gloss/comment line.
- `zh_modern`: modern Chinese explanation requested by the user.

Chinese Hanzi and Japanese kanji that carry readings should be single-character tokens unless a project validator explicitly allows another shape. Kana should not receive furigana. Do not accept placeholder Japanese such as `注`, empty commentary, kana-only filler for kanji-heavy passages, or repeated compound readings like `釜(ふざん)山(ふざん)`.

## Rendering Contract

When renderers exist, compile both directions:

- JP-main: Japanese is the main line; Classical Chinese and/or modern Chinese are comment lines.
- ZH-main: Chinese is the main line; Japanese and/or modern Chinese are comment lines.

For grammar-color books, also compile blackwhite variants by remapping grammar colors to black in TeX, not by deleting `g` from JSON. Keep PDF outputs under `build/<book-id>/jp-main/{color,blackwhite}/` and `build/<book-id>/zh-main/{color,blackwhite}/` unless the user requested another structure.

## Long-Run Workflow

1. Convert or verify Markdown/source manifests before writing annotation JSON.
2. Split work into stable paragraph/chapter tasks with persistent IDs and source hashes.
3. Use provider workers per chunk or sentence when needed, but promote only validator-passing JSON.
4. Keep writer, deterministic reviewer, semantic reviewer, repairer, monitor, merge, and compile loops separate.
5. Reviewers may fix old chunks asynchronously, but writers should continue forward unless a schema bug would corrupt new work.
6. Compile previews after checkpoints and verify current-manifest coverage before trusting page counts.
