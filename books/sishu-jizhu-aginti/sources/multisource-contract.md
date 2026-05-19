# Multisource Book Preparation Contract

Schema version 1. Generated 2026-05-19. Applies to all bilingual/interlinear book pipelines in this repository.

## 1. Purpose

This contract defines how a bilingual book pipeline discovers, converts, validates, and bundles multiple source editions (main text, reference editions, alternate-language scans) before chunking or writer activation. It is source preparation only; it must not start book writers.

## 2. Source Roles

Every source in a bundle must be assigned exactly one role. A book may have zero or one source in each role.

| Role          | Cardinality | Description |
|---------------|-------------|-------------|
| `main_zh`     | 1           | Exact canonical Chinese text used for chunking and source reconstruction. Must be paragraph-addressable, clean of boilerplate, and sha256-stable. |
| `reference_zh`| 0..1        | A different Chinese edition (different publisher, year, or scan) that provides broader chapter-level context. Does not need to be paragraph-exact. |
| `reference_ja`| 0..1        | A Japanese edition (kana-attached, modern, or annotated) used as a reference during Japanese-comment generation. |
| `reference_en`| 0..1        | An English translation for semantic reference. |

### Role assignment rules

- `main_zh` must be the best structured, most reliable Chinese source. Prefer structured JSON/HTML extraction over PDF text extraction over OCR.
- If only one Chinese source exists, it is `main_zh`; `reference_zh` is absent.
- If a source is image-only (no extractable text layer) and requires OCR, assign it a role with `extraction_status: "requires_ocr"` and do not fabricate markdown. Placeholder metadata is acceptable.
- `reference_ja` should be chapter-addressable. Kana/furigana-tagged Japanese sources are ideal for interlinear reference.

## 3. Source Conversion Pipeline

### 3.1 Extraction Methods (in priority order)

1. **html** – Parse structured HTML (BeautifulSoup). Use for Wikisource, CText, or any source with `section.chapter` > `h2` + `p` structure. Preferred.
2. **wikisource_json** – Read a wikisource-book JSON manifest, follow the `html` path, extract as html.
3. **pdf_text** – Run `pdftotext -raw`. Use when the PDF has an embedded text layer. Fall back to OCR if empty.
4. **ocr** – Render with PyMuPDF, preprocess (crop, binarize), run Tesseract with CJK language models. Last resort.
5. **iiif_pdf** – For NDL IIIF-sourced PDFs. Check for text layer first; if absent, note the IIIF manifest URLs for future OCR.

### 3.2 Boilerplate Removal Rules

Remove only these clear categories:

- Wikisource public-domain notices (`此作品在全世界都属于公有领域`, `Public domain false false`)
- Navigation fragments (`←`, `→`, `◄`, `►`, `版本`, `目錄`)
- Isolated page numbers (regex `^\d{1,4}$`) on their own line
- Lines starting with `Source:`, `https://`, `http://`, `Generated from`, `Root source:`, `姊妹计划`, `姉妹プロジェクト`
- Extraction tool headers/footers (pdftotext page markers, OCR engine banners)

**Do not remove**: commentary, annotations, prefaces, appendices, or any prose between chapter boundaries unless they are clearly license boilerplate.

### 3.3 Markdown Structure

```
# Book Title

## Chapter Title

Paragraph text...

Paragraph text...

## Next Chapter Title
...
```

- `#` = book title (one per file)
- `##` = chapter/section headings
- Paragraphs separated by blank lines
- No inline HTML, no metadata frontmatter in the body
- Metadata lives in the source-bundle.json, not in the markdown

### 3.4 Output Path Convention

```
books/<book-id>/sources/markdown/<lang>_<role>.md
```

Examples:
- `books/sishu-jizhu-aginti/sources/markdown/zh_main.md`
- `books/sishu-jizhu-aginti/sources/markdown/zh_reference.md`
- `books/sishu-jizhu-aginti/sources/markdown/ja_reference.md`

The canonical markdown (for active chunking) may also exist at `books/<book-id>/markdown/zh.md` for backward compatibility, but the source bundle always references files under `sources/markdown/`.

## 4. Source Bundle Manifest

### 4.1 Schema (`source-bundle.json`)

```jsonc
{
  "schema_version": 1,
  "book_id": "sishu-jizhu-aginti",
  "generated_at": "ISO-8601",
  "sources": {
    "main_zh": { /* SourceEntry */ },
    "reference_zh": { /* SourceEntry or null */ },
    "reference_ja": { /* SourceEntry or null */ }
  },
  "validation": {
    "chapter_headings_main": 33,
    "chapter_headings_reference_zh": null,
    "chapter_headings_reference_ja": null,
    "main_text_chars": 123456,
    "reference_zh_text_chars": null,
    "reference_ja_text_chars": null,
    "notes": []
  }
}
```

### 4.2 SourceEntry Schema

```jsonc
{
  "role": "main_zh",
  "language": "zh",
  "title": "四書章句集註",
  "author": "朱熹",
  "source_path": "sources/sishu/四書章句集註（維基文庫） - 朱熹.json",
  "source_sha256": "d2e2ef63...",
  "markdown_path": "books/sishu-jizhu-aginti/sources/markdown/zh_main.md",
  "markdown_sha256": "902fd7de...",
  "extraction_method": "html",
  "extraction_status": "complete",
  "chapter_count": 33,
  "notes": "Wikisource HTML extraction via prepare_classical_source_batch.py. Cleaned of 2 PD boilerplate blocks."
}
```

Extraction status values: `complete`, `requires_ocr`, `failed`, `pending`.

## 5. Multisource Plan (`book-plan.multisource.json`)

### 5.1 Relationship to Active Plan

- `book-plan.json` is the **active** plan used by the current running pipeline. **Never overwrite** while writers are active.
- `book-plan.multisource.json` is a **prepared but inactive** plan that references the full source bundle. It can replace the active plan after all writers stop and the user approves the switch.
- Both follow the same schema (from `prepare_classical_source_batch.py`), but the multisource plan adds:
  - `reference_zh_markdown` / `reference_zh_sha256`
  - `reference_ja_markdown` / `reference_ja_sha256`
  - `source_bundle_path` pointing to the source-bundle.json
  - `multisource: true`

### 5.2 Activation Rules

A multisource plan must NOT be activated (copied over `book-plan.json`) until:
1. All active chunk writers and reviewers for the book have completed.
2. The `main_zh` markdown is identical between both plans (same sha256).
3. The user explicitly approves the switch.
4. Old chunks are backed up before regeneration with the new plan.

## 6. Reusable Script Contract

### 6.1 Script Location

`scripts/books/build_source_bundle.py` or `scripts/interlinear/build_source_bundle.py`

### 6.2 Interface

```
python scripts/books/build_source_bundle.py \
  --book-id sishu-jizhu-aginti \
  --source-dir sources/sishu \
  --output-dir books/sishu-jizhu-aginti/sources \
  [--main-zh sources/sishu/四書章句集註（維基文庫） - 朱熹.json] \
  [--reference-zh sources/sishu/四書章句集注 sishu zhangju jizhu.pdf] \
  [--reference-ja sources/sishu/四書 仮名附（NDL公開） - 朱熹 集注・後藤嘉幸 点.json] \
  [--validate]
```

### 6.3 Generalization Requirements

The script must:
- Accept any book-id, not hard-code Sishu.
- Accept any source file paths via CLI arguments.
- Auto-detect source type from file extension (.json → read mode; .pdf → check text layer → pdftotext or mark as requires_ocr).
- Read JSON source manifests and follow their `html` or `pdf` paths.
- Write markdown with metadata headers (YAML frontmatter) containing source path, sha256, extraction method.
- Generate source-bundle.json.
- Generate book-plan.multisource.json when a main source exists.
- Support `--validate` mode that prints a report without writing files.

## 7. Validation Contract

### 7.1 Validation Checks

A validation run must report:

| Check | Metric |
|-------|--------|
| Source count | Total sources discovered, by role |
| Main text | Character count, line count, chapter count |
| Reference ZH | Chapter count, character count (or "requires_ocr") |
| Reference JA | Chapter count, character count (or "requires_ocr") |
| Boilerplate removed | Count of boilerplate blocks removed |
| Chapter headings | List of all `## ` headings per source |
| SHA256 stability | Confirm sha256 matches recorded values |
| Extraction status | Per-source: complete / requires_ocr / failed / pending |

### 7.2 Quality Thresholds

- `main_zh` must have ≥10 chapters and ≥10,000 characters or it is considered corrupt.
- Reference sources have no minimum; `requires_ocr` is a valid state.
- The validation report is a JSON file at `books/<book-id>/sources/validation-report.json`.

## 8. Generalization To Other Source Types

### 8.1 EPUB Sources

- Extract to markdown via `scripts/books/epub_to_markdown.py`.
- Apply the same boilerplate rules.
- EPUB sources may be reference_ja (modern Japanese) or reference_en.

### 8.2 PDF Text-Layer Sources

- Use `pdftotext -raw` then chapter-detection via heading heuristics.
- Chinese: detect `第.*章` or `##` style headings.
- Japanese: detect `第.*章`, `その.*`, or kana-based section markers.

### 8.3 Wiki/JSON Sources

- Follow the `html` path in the JSON manifest.
- Extract with BeautifulSoup `section.chapter > h2 + p`.
- Apply boilerplate stripping.

### 8.4 OCR Sources

- Coordinate with `scripts/ocr/pdf_to_markdown.py`.
- OCR jobs for 100+ pages should be queued, not run inline.
- Always save preprocessed page images alongside OCR output for review.

## 9. Non-Goals (Explicit)

- This contract does NOT define how to split markdown into chunks (see `chunk_markdown_book.py`).
- This contract does NOT define how bilingual JSON is generated (see writer workers).
- This contract does NOT define LaTeX compilation or PDF output.
- Source conversion is idempotent: re-running must not corrupt existing validated markdown unless `--force` is used.
