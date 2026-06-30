# LinguaLeaf Problem Log And Robust Task Rules - 2026-07-01

This note records the main problems we hit while building LinguaLeaf /
PocketPolyglot books and the rules that should prevent the same failures in
future long-running tasks.

## Core Rule

Treat each book as a durable data pipeline, not a one-shot generation job:

1. prepare sources and a stable manifest;
2. generate or backfill JSON incrementally;
3. validate and promote only current-manifest chunks;
4. compile from JSON without regenerating text;
5. review rendered PDFs;
6. sync final artifacts with clean names.

Never delete or overwrite expensive generated data unless a backup exists and
the new output has passed validation.

## Problems, Fixes, And Future Rules

| Problem | Symptom | Fix Used | Future Rule |
| --- | --- | --- | --- |
| Manifest ignored by tools | A part build or progress report counted a whole book instead of only the selected part. | Updated progress and assembly scripts to filter source chunks by `manifest["chunks"]`. | Every report, assembler, reviewer, and compiler must treat the manifest as the source of truth. |
| Misleading page counts | PDFs had fewer pages or stopped growing even though tasks seemed active. | Checked manifest coverage, stale chunks, failed chunks, and TeX logs instead of page count alone. | Completion requires `missing=0`, `stale=0`, valid chunks, and successful PDF compile. |
| Unstable chunking | Changing chunk size restarted work from zero. | Moved toward stable chunk ids and field-level overlays. | Split first, then run independent passes for translation, ruby, grammar, and review. |
| Generated data overwritten | New prompts risked flushing old translations, ruby, or grammar. | Added backup folders and incremental repair/backfill flows. | Backfill must add or repair fields, not regenerate the whole chunk unless explicitly requested. |
| Parallel worker conflicts | Parallel writers could write the same output or leave inconsistent partials. | Used disjoint shard ranges, one output path per chunk, then deterministic promotion. | Parallelism is safe only when each worker owns a non-overlapping chunk set. |
| Quota/rate-limit stalls | tmux sessions stopped at Codex usage limits. | Added wait/retry behavior and allowed pausing without losing chunks. | Long runners should checkpoint, sleep on limits, and resume without changing manifests. |
| Monitor too passive | A worker could stall while the PDF remained old. | Added progress probes, retry of old failed chunks, and sequential part runners. | A monitor should detect no-progress windows, failed chunks, and stale outputs, then requeue gently. |
| Reviewer too narrow | Mechanical validation passed while semantic or layout errors remained. | Split deterministic schema/render review from deeper semantic review. | Deterministic review must always run; semantic review can run async but should not block raw generation unless it finds severe defects. |
| All-one-color grammar | Pages appeared mostly one color, especially grammar annotations. | Normalized grammar roles to English-only labels and repaired role assignment. | Validate role vocabulary and role distribution; no aliases such as mixed Chinese/English role names. |
| English spaces lost | English grammar-colored text was joined without spaces. | Added language-specific joining/rendering rules. | English tokens must preserve word spaces; CJK tokens may join without spaces. |
| Ruby/pinyin misaligned | Furigana or pinyin appeared over long phrases or wrong text. | Enforced token-level readings: pinyin on its Chinese token; furigana only on kanji-bearing Japanese tokens. | JSON must store readings per token, not per sentence. |
| Japanese not actually Japanese | Some requested Japanese fields were Chinese or kana-only nonsense. | Added stricter prompts and target-language checks. | Validators should reject fields whose script distribution is incompatible with the target language. |
| `注` used for continuation | Modern novels and classical translations showed `注` although the text was really sentence continuation. | Stopped rendering generic continuation fields as notes and separated continuation/gloss/comment. | Schema must distinguish `main`, `continuation`, `gloss`, `comment`, `note`, and `source_annotation`. |
| Classical commentary lost | Pei Songzhi commentary and similar layers were omitted or not colored. | Created separate additive tasks that reuse base JSON and add commentary streams. | Classical books need explicit textual layers: base wenyan, inherited commentary, modern Chinese, modern Japanese, English, and optional notes. |
| Bracketed note markers failed validation | A pure marker like `[一二]` required English prose and blocked a chunk. | Added note-marker detection so pure bracket markers are not treated as content requiring translation. | Validators should classify markers, punctuation, and labels before applying language-content rules. |
| Redirect stubs entered books | Zuozhuan output contained `#重定向`. | Filtered redirect-only Wikisource stubs during task preparation and rebuilt affected manifests. | Source preparation must remove redirects, navigation pages, and index stubs before chunking. |
| OCR noise entered polished books | Sanxingdui TeX had messy captions, page labels, or garbled image text. | Added OCR-polish workflow: page-by-page correction, caption repair, and figure preservation. | OCR books must be rewritten as clean books, not dumped as raw OCR or page-image notes. |
| Original-page placeholders | Text like `原书第 2 页` appeared in new books. | Removed page-placeholder prose and used real chapters, captions, and figures. | A new TeX book should read as a self-contained book, not as an OCR audit log. |
| Figures too small or awkward | Figure-heavy books lost visual value. | Made image-heavy pages capable of full-page figure placement. | For artifact or archaeology books, default large figures to full-page unless text demands otherwise. |
| Formula/table conversion risk | Technical books need exact equations, tables, and diagrams. | Prepared exact-TeX conversion protocol with OCR/formula tools and page validation. | For math books, use text/TeX equations, not page images; check formulas, tables, overflow, and source-page evidence. |
| Cover duplicated title overlays | Some covers had a generated title plus a TeX title shadow/overlay. | Changed cover rendering so a provided cover image is full-page without a second title overlay. | Cover composition owns cover text; TeX should not add duplicate title text when `cover_image` exists. |
| Cover text too intrusive | Overlay covered too much artwork or contained workflow phrases. | Reduced overlay size and removed technical phrases like OCR/TeX run names. | Public covers should show title, author, language edition, and credit only. |
| Missing covers in variants | Color had a cover but black-white or reverse editions did not. | Reused the same cover source across variants and audited variant outputs. | Every final PDF variant must have a cover unless explicitly marked as a draft. |
| TOC reflected OCR noise | Sanxingdui TOC had missing numbering or fake entries. | Corrected headings based on the actual content structure, not by copying OCR TOC artifacts. | TOC must be generated from curated chapter headings in TeX/JSON. |
| Chapters did not start cleanly | New chapters sometimes followed the previous page. | Updated renderers to support chapter page breaks. | Final book renderers should start major chapters on a new page. |
| Long line overflow | Some pages had lone long lines or clipped annotations. | Checked TeX logs and adjusted wrapping/macros. | Compile gates must inspect overfull boxes and sample pages, especially long ruby/comment lines. |
| TeX wrapper macro bug | Manual wrappers used `##1` where TeX required `#1`, causing fatal compile errors. | Replaced ad hoc wrappers with reusable compile scripts. | Compile scripts should generate wrappers consistently; avoid hand-written one-off TeX macro patches. |
| Large-font inconsistency | New books looked smaller than Shiji AgInTi-style outputs. | Standardized public exports on `large-font` / `大字版`. | Use the large-font profile by default for final LinguaLeaf exports. |
| Output naming drift | Same book variants used inconsistent language names or ugly internal labels. | Introduced cleaner language-set and variant naming. | Public filenames should include title, language set, and color/BW variant; internal terms like `shiji-font` should not appear. |
| Build folder sprawl | Old outputs used incompatible folder layouts. | Archived legacy folders and moved final PDFs toward consolidated export paths. | New outputs should use `build/<book>/<language-set>/large-font/{color,blackwhite}/`. |
| Nutstore sync gaps | Some newly compiled PDFs were not in Share or Projects folders. | Added post-compile copy steps and flattened Share folders by color/BW. | A task is not complete until final PDFs are synced to the requested destinations. |
| PDFs too heavy for code repo | Final PDFs risked bloating Git history and GitHub. | Kept large PDFs ignored locally and prepared a separate LinguaLeaf PDF repo/export path. | Code repo tracks scripts, TeX, schemas, prompts, and small previews; final PDFs belong in release/export storage. |
| AgInTi hardcoding risk | Task-specific book logic leaked into generic AgInTi tool design. | Moved task-specific rules into skills/custom workflow docs and kept core principles general. | Core agent logic should be task-neutral: contract, evidence, validation, replan, self-repair. |

## Current Robustness Pattern

For each future book, create these durable artifacts before generation:

```text
books/<book>/book-plan.json
books/<book>/markdown/
books/<book>/work/<workflow>/chunks/chunks.jsonl
books/<book>/work/<workflow>/chunks/manifest.json
books/<book>/work/<workflow>/interlinear/chunks/
books/<book>/work/<workflow>/review/
build/<book>/<language-set>/large-font/{color,blackwhite}/
```

If the book is too large, split the manifest into parts:

```text
books/<book>/work/<workflow>/parts/part-01/manifest.json
books/<book>/work/<workflow>/parts/part-01/start_part.sh
books/<book>/work/<workflow>/parts/run_parts_sequential.sh
```

Part compilers and reporters must respect the part manifest. They must not scan
all book chunks unless explicitly building the full book.

## Validation Gates

Before a generated chunk is promoted:

- chunk id exists in the active manifest;
- source text is complete;
- required languages are present;
- target-language fields pass script checks;
- ruby/furigana/pinyin are token-level;
- grammar roles use the normalized vocabulary;
- English preserves spaces;
- pure markers and punctuation are classified correctly;
- no HTML, redirects, navigation text, OCR garbage, or placeholder page labels.

Before a PDF is accepted:

- color and black-white variants compile;
- requested main-language direction exists;
- cover exists and is not duplicated by TeX overlays;
- TOC is generated from curated headings;
- chapter starts are clean;
- TeX log has no fatal errors and no serious overflow;
- representative pages are visually inspected;
- final PDFs are synced to Share/Projects or the requested export folder.

## Long-Run Control

Use a conservative control loop:

1. writer workers generate disjoint chunks;
2. deterministic reviewer promotes valid chunks;
3. semantic reviewer repairs older chunks asynchronously;
4. monitor watches heartbeats, failure counts, stale chunks, and quota errors;
5. compiler builds previews from whatever is valid, without blocking generation;
6. final compiler waits for manifest completion.

Parallel generation can be high, but only when the output paths are disjoint and
the promoter is deterministic. If a task becomes fragile, reduce worker count
instead of changing the data model.

## Handoff Commands

Typical checks:

```sh
python scripts/interlinear/report_quadrilingual_progress.py \
  --manifest books/<book>/work/quadrilingual/chunks/manifest.json \
  --chunk-dir books/<book>/work/quadrilingual/interlinear/chunks

python scripts/interlinear/validate_interlinear_json.py <json>

grep -E "Fatal|Emergency|Overfull" build/<book>/**/*.log
```

Typical large-font quadrilingual part build:

```sh
scripts/interlinear/compile_quadrilingual_wenyan_part_large_font.sh \
  --book <book> \
  --part-manifest books/<book>/work/quadrilingual/parts/part-01/manifest.json \
  --part-label "第一部" \
  --cover-image assets/covers/<book>/part-01-cover.png
```

## Rule For Future Changes

When fixing a book-specific bug, first decide the correct layer:

- **source preparation** for redirects, OCR noise, missing headings, or bad
  input files;
- **JSON schema** for text layers, continuations, comments, readings, and
  grammar roles;
- **writer prompt** for target-language quality or missing translations;
- **validator/reviewer** for repeatable mechanical defects;
- **renderer/TeX** for layout, cover, TOC, ruby, spacing, and overflow;
- **sync/export** for filenames, folders, and distribution;
- **agent/core tooling** only for general task-contract, evidence, monitoring,
  retry, or self-repair behavior.

Do not patch the wrong layer just because it is faster. That creates repeated
failures in the next book.
