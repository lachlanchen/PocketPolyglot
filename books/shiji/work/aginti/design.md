# Shiji Three-Layer AgInTi Pipeline — Design

## 1. Directory Layout

```
books/shiji/                          # existing source chunks, markdown, book-plan
  work/
    aginti/                            # AgInTi runtime artefacts (this document)
      design.md
      validate_shiji_chunk.py
      generate_chunk.py
      render_jp_main_tex.py
      render_zh_main_tex.py
      pilot_validation_report.txt
      logs/                            # per-chunk generation + validation logs

data/interlinear/shiji-aginti/        # AgInTi-generated chunk JSON files
  shiji-chunk-0001.json
  shiji-chunk-0002.json
  ...

build/shiji-aginti/                   # compiled PDFs and intermediate TeX
  jp-color/
  jp-bw/
  zh-color/
  zh-bw/
  preview/                             # pilot preview PDFs
```

Existing bilingual chunks (`books/shiji/work/bilingual/chunks/`) are read-only inputs.  
Existing Codex scripts in `scripts/interlinear/` are untouched.  
New AgInTi renderers are placed beside the pipeline scripts under `books/shiji/work/aginti/`.

## 2. JSON Schema (per chunk)

Each chunk is one JSON file. The `mode` tag discriminates this schema from the older two-layer `zh_main_ja_comment` schema.

```json
{
  "mode": "zh_classical_three_layer",
  "chunk_id": "shiji-chunk-0001",
  "book_title_zh": "史記",
  "book_title_zh_reading": "shǐ jì",
  "book_title_ja": "史記",
  "book_title_ja_reading": "し き",
  "author": "司馬遷",
  "author_reading_zh": "sī mǎ qiān",
  "author_reading_ja": "し ば せん",
  "section": {
    "id": "五帝本紀",
    "title_zh_original": [{"t": "五", "r": "wǔ", "g": ""}, ...],
    "title_ja": [{"t": "五", "r": "ご", "g": ""}, ...]
  },
  "paragraphs": [
    {
      "id": "shiji-zh-p00001",
      "source_text": "黃帝者，少典之子，姓公孫，名曰軒轅。…",
      "units": [
        {
          "source_text": "黃帝者，少典之子，姓公孫，名曰軒轅。",
          "zh_original": [
            {"t": "黃", "r": "huáng", "g": "attributive"},
            {"t": "帝", "r": "dì", "g": "topic"},
            {"t": "者", "r": "zhě", "g": "function"},
            {"t": "，", "r": "", "g": ""},
            {"t": "少", "r": "shào", "g": "attributive"},
            {"t": "典", "r": "diǎn", "g": "attributive"},
            {"t": "之", "r": "zhī", "g": "function"},
            {"t": "子", "r": "zǐ", "g": "predicate"},
            {"t": "，", "r": "", "g": ""},
            {"t": "姓", "r": "xìng", "g": "predicate"},
            {"t": "公", "r": "gōng", "g": "attributive"},
            {"t": "孫", "r": "sūn", "g": "object"},
            {"t": "，", "r": "", "g": ""},
            {"t": "名", "r": "míng", "g": "predicate"},
            {"t": "曰", "r": "yuē", "g": "function"},
            {"t": "軒", "r": "xuān", "g": "attributive"},
            {"t": "轅", "r": "yuán", "g": "object"},
            {"t": "。", "r": "", "g": ""}
          ],
          "ja": [
            {"t": "黄", "r": "こう", "g": "attributive"},
            {"t": "帝", "r": "てい", "g": "topic"},
            {"t": "は", "r": "", "g": "function"},
            {"t": "少", "r": "しょう", "g": "attributive"},
            {"t": "典", "r": "てん", "g": "attributive"},
            {"t": "の", "r": "", "g": "function"},
            {"t": "子", "r": "こ", "g": "predicate"},
            {"t": "で", "r": "", "g": "function"},
            {"t": "あ", "r": "", "g": ""},
            {"t": "る", "r": "", "g": ""},
            {"t": "、", "r": "", "g": ""},
            {"t": "姓", "r": "せい", "g": "predicate"},
            {"t": "は", "r": "", "g": "function"},
            {"t": "公", "r": "こう", "g": "attributive"},
            {"t": "孫", "r": "そん", "g": "object"},
            {"t": "、", "r": "", "g": ""},
            {"t": "名", "r": "な", "g": "predicate"},
            {"t": "は", "r": "", "g": "function"},
            {"t": "軒", "r": "けん", "g": "attributive"},
            {"t": "轅", "r": "えん", "g": "object"},
            {"t": "と", "r": "", "g": "function"},
            {"t": "い", "r": "", "g": ""},
            {"t": "う", "r": "", "g": ""},
            {"t": "。", "r": "", "g": ""}
          ],
          "zh_modern": [
            {"t": "黄", "r": "huáng", "g": "attributive"},
            {"t": "帝", "r": "dì", "g": "topic"},
            {"t": "是", "r": "shì", "g": "function"},
            {"t": "少", "r": "shào", "g": "attributive"},
            {"t": "典", "r": "diǎn", "g": "attributive"},
            {"t": "的", "r": "de", "g": "function"},
            {"t": "儿", "r": "ér", "g": "object"},
            {"t": "子", "r": "zi", "g": "object"},
            ...
          ]
        }
      ]
    }
  ]
}
```

### Token conventions (inherited from existing pipeline)

| Field | Meaning | Required |
|-------|---------|----------|
| `t`   | surface token text | yes |
| `r`   | pinyin (Chinese) / furigana (Japanese) reading | only for single Han / kanji characters |
| `g`   | grammar role — one of: `subject`, `predicate`, `object`, `attributive`, `adverbial`, `complement`, `topic`, `function`, or `""` for punctuation | yes |

### Key naming rationale

- `zh_original` — classical Chinese original tokens with pinyin. Never abbreviated to `zh`.
- `zh_modern` — modern explanatory Chinese with pinyin. Always distinct from `zh_original`.
- `ja` — a flat list of dict tokens (list[dict]) representing the Japanese correspondence. Each kanji is a one-character token with furigana; kana tokens may be multi-character and must carry a valid `g` role unless punctuation. The token list represents the Japanese reading directly; there is no second kana-duplicate line — TeX ruby wrapping is a renderer concern.

## 3. Validation Rules (deterministic)

The validator (`validate_shiji_chunk.py`) checks each chunk JSON file:

1. **Structure** — `mode` == `"zh_classical_three_layer"`, chunk has `chunk_id`, `paragraphs` array with at least one paragraph.
2. **Source-text reconstruction** — joining all `zh_original[].t` within a **unit** reconstructs `unit.source_text` modulo whitespace. Joining across all units within a paragraph reconstructs `paragraph.source_text`.
3. **Han-character token shape (zh_original, zh_modern)** — every CJK Unified Ideograph (U+3400–U+4DBF, U+4E00–U+9FFF, U+F900–U+FAFF) must appear as a one-character token with a non-empty `r` (pinyin). Punctuation and non-Han characters may lack `r`.
4. **Kanji token shape (ja)** — every kanji (same Unicode ranges) must appear as a one-character token with a non-empty `r` (furigana). Kana tokens may be multi-character and, if not punctuation, must carry a valid `g` role. All tokens may carry `r` only when appropriate.
5. **Grammar roles** — every token must have `g`; non-punctuation tokens must have `g` in `{subject, predicate, object, attributive, adverbial, complement, topic, function}`. Punctuation may have `g == ""`.
6. **Japanese placeholder rejection** — no `ja` token line may be empty, equal to `"注"`, `"注。"`, `"。"`, or `"日本語"`. The joined ja text must contain at least one kanji or kana character.
7. **Modern Chinese distinctness** — `zh_modern` token text joined must differ from `zh_original` token text joined (cannot be a mere copy of the classical source).
8. **Ja flatness** — `ja` must be a flat `list[dict]` (single token list), not `list[list[dict]]`. There is no second kana-duplicate line; TeX ruby wrapping is a renderer concern.

## 4. Generation Worker

`generate_chunk.py` is a standalone Python script.

**Inputs:**
- `--chunk-id` e.g. `shiji-chunk-0001`
- `--chunks-jsonl` default `books/shiji/work/bilingual/chunks/chunks.jsonl`
- `--output-dir` default `data/interlinear/shiji-aginti/`
- `--provider` default `deepseek`
- `--retry` boolean, default false (set true to retry after validation failure)

**Algorithm:**
1. Grep the exact chunk JSONL line by chunk_id.
2. Extract `paragraphs[].text` (classical Chinese) and `jp_reference[]` (Japanese Wikisource paragraphs).
3. Build a DeepSeek prompt requesting tokenization into `zh_original`, `ja` (flat token list), `zh_modern` per unit.
4. Parse the LLM response, validate with `validate_shiji_chunk.py`.
5. On validation failure, feed errors back to the LLM for one retry. If still failing, write the raw response + errors to `logs/` and exit non-zero.
6. Write valid JSON to `data/interlinear/shiji-aginti/{chunk_id}.json`.

**Provider configuration:**
- Reads `DEEPSEEK_API_KEY` from environment or `.aginti/.env`.
- Uses OpenAI-compatible chat completions endpoint: `https://api.deepseek.com/v1/chat/completions`.
- Model: `deepseek-chat` (or `deepseek-reasoner` if more accuracy is needed).
- Temperature: 0.1 for deterministic output.

## 5. Renderer Strategy

Two TeX renderer scripts are needed, both writing to `build/shiji-aginti/`:

### 5.1 JP-main renderer (`render_jp_main_tex.py`)

**Output files:** `build/shiji-aginti/jp-color/book.tex`, `build/shiji-aginti/jp-bw/book.tex`

**Layout per unit:**
1. **Primary line** — `ja` tokens (kanji + furigana + kana), with `\jpruby` and `\Gram` wrappers, rendered in a larger font. TeX ruby wrapping is the renderer's responsibility; the data layer provides a flat token list.
2. **Classical Chinese line** — `zh_original` tokens with `\zhcnruby` and `\Gram`.
3. **Modern Chinese line** — `zh_modern` tokens with `\zhcnruby` and `\Gram`, in a smaller font.

### 5.2 ZH-main renderer (`render_zh_main_tex.py`)

**Output files:** `build/shiji-aginti/zh-color/book.tex`, `build/shiji-aginti/zh-bw/book.tex`

**Layout per unit:**
1. **Primary line** — `zh_original` with `\zhcnruby` and `\Gram`, large font.
2. **Japanese correspondence** — `ja` tokens with `\jpruby` and `\Gram`, smaller.
3. **Modern Chinese line** — `zh_modern` with `\zhcnruby` and `\Gram`, smallest.

### 5.3 TeX style

Both renderers copy and lightly adapt the existing `tex/interlinear-jp-main/style.tex`:
- Use `\BlackWhiteMode` to remap all `Gram*` colors to black for BW PDFs.
- Pocket size: 105mm × 148mm.
- Noto Serif CJK JP for Japanese, Noto Serif CJK SC for Chinese.
- TOC support via `\tableofcontents` + `\section{}` per chunk/section boundary.

### 5.4 Compilation

```sh
cd build/shiji-aginti/jp-color && xelatex -interaction=nonstopmode book.tex && xelatex book.tex
```

Two passes for TOC. Same for BW.

## 6. Pilot Plan

1. Generate chunks 1–5 with `generate_chunk.py`.
2. Validate all five with `validate_shiji_chunk.py`.
3. Collect chunks into a combined JSON array, feed to both renderers.
4. Compile four PDFs.
5. Record page counts in `pilot_validation_report.txt`.

## 7. Acceptance Criteria (reminder)

- All 5 pilot chunks pass validation.
- Four preview PDFs exist with non-zero page counts.
- Design document committed.
- No existing Codex scripts modified.
- `zh_original` and `zh_modern` never overloaded.
