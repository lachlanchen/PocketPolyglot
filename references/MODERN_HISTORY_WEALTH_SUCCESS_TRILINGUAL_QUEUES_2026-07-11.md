# Modern History And Wealth-Success Trilingual Queues - 2026-07-11

These queues prepare modern nonfiction LinguaLeaf/PocketPolyglot tasks with English as the source spine and generated modern Japanese and modern Chinese commentary. Each chunk carries a translation contract requiring complete, accurate, modern, understandable translation plus downstream grammar-role analysis for color/black-white PDF builds.

## Shared Preparation

- Preparation script: `scripts/interlinear/prepare_modern_nonfiction_trilingual.py`.
- Worker prompt support: `scripts/interlinear/codex_trilingual_plain_json_worker.py` now passes the per-chunk `translation_contract` into the model prompt.
- EPUB fallback extraction is built into the preparation script for malformed EPUBs that `pandoc` cannot read.
- The parser now uses body-specific start anchors, minimum chunk-count gates, exact short stop markers, and filters PDF/EPUB/OCR page artifacts before chunking.
- Final run expectation: maximum-language `en-jp-zh` large-font color and black-white PDFs, cover, TOC, grammar roles, and Nutstore/LinguaLeaf sync after completion.

## Launch Commands

```bash
# History queue: Codex Spark low, one book at a time
prompt_tools/run_modern_nonfiction_trilingual_queues.sh history

# Wealth-success queue: GPT-5.5 low, one book at a time
prompt_tools/run_modern_nonfiction_trilingual_queues.sh wealth

# Start both queues
prompt_tools/run_modern_nonfiction_trilingual_queues.sh both
```

## Modern History / Popular Science Queue

- Queue JSON: `data/source-plan/modern-history-trilingual-queue.json`
- Model: `gpt-5.3-codex-spark`
- Reasoning: `low`
- Workers: `10`
- Status: `chunked_launchable`

| # | Book ID | Title | Source | Chunks | Chapters |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | `ancient-egypt-history` | The Oxford History of Ancient Egypt | `sources/world-history/ancient-egypt/en/The Oxford History of Ancient Egypt - Ian Shaw.pdf` | 159 | 3 |
| 2 | `babylon-mesopotamia` | Babylon: Mesopotamia and the Birth of Civilization | `sources/world-history/mesopotamia/en/Babylon - Mesopotamia and the Birth of Civilization - Paul Kriwaczek.pdf` | 145 | 2 |
| 3 | `ancient-assyria-vsi` | Ancient Assyria: A Very Short Introduction | `sources/world-history/ancient-assyria/en/Ancient Assyria - A Very Short Introduction - Karen Radner.epub` | 107 | 17 |
| 4 | `holy-roman-empire-history` | Heart of Europe: A History of the Holy Roman Empire | `sources/world-history/holy-roman-empire/en/Heart of Europe - A History of the Holy Roman Empire - Peter H Wilson.pdf` | 793 | 46 |
| 5 | `persian-fire` | Persian Fire: The First World Empire and the Battle for the West | `sources/world-history/persian-empire/en/Persian Fire - Tom Holland.pdf` | 395 | 37 |
| 6 | `ancient-near-east-weavers-scribes-kings` | Weavers, Scribes, and Kings: A New History of the Ancient Near East | `sources/world-history/ancient-near-east/en/Weavers Scribes and Kings - Amanda H Podany.pdf` | 558 | 30 |
| 7 | `iran-empire-of-the-mind` | A History of Iran: Empire of the Mind | `sources/world-history/iran/en/A History of Iran - Empire of the Mind - Michael Axworthy.pdf` | 309 | 6 |
| 8 | `habsburgs-to-rule-the-world` | The Habsburgs: To Rule the World | `sources/world-history/habsburgs/en/The Habsburgs - To Rule the World - Martyn Rady.epub` | 347 | 5 |
| 9 | `ottomans-khans-caesars-caliphs` | The Ottomans: Khans, Caesars and Caliphs | `sources/world-history/ottomans/en/The Ottomans - Khans, Caesars and Caliphs - Marc David Baer.pdf` | 419 | 7 |
| 10 | `elegant-universe` | The Elegant Universe | `sources/popular-science/brian-greene/en/The Elegant Universe - Brian Greene.pdf` | 343 | 24 |

## Wealth, Money, Business, And Success Queue

- Queue JSON: `data/source-plan/wealth-success-trilingual-queue.json`
- Model: `gpt-5.5`
- Reasoning: `low`
- Workers: `10`
- Status: `chunked_launchable`

| # | Book ID | Title | Source | Chunks | Chapters |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | `psychology-of-money` | The Psychology of Money | `sources/economics-finance/behavioral-finance/en/The Psychology of Money - Morgan Housel.pdf` | 148 | 22 |
| 2 | `your-money-or-your-life` | Your Money or Your Life | `sources/economics-finance/financial-independence/en/Your Money or Your Life - Vicki Robin Joe Dominguez and Mr Money Mustache.epub` | 264 | 41 |
| 3 | `simple-path-to-wealth` | The Simple Path to Wealth | `sources/economics-finance/financial-independence/en/The Simple Path to Wealth - J L Collins and Mr Money Mustache.epub` | 150 | 44 |
| 4 | `little-book-common-sense-investing` | The Little Book of Common Sense Investing | `sources/economics-finance/investing/en/The Little Book of Common Sense Investing - John C Bogle.epub` | 117 | 9 |
| 5 | `intelligent-investor` | The Intelligent Investor | `sources/economics-finance/investing/en/The Intelligent Investor - Benjamin Graham and Jason Zweig.pdf` | 121 | 34 |
| 6 | `mom-test` | The Mom Test | `sources/business-sales/customer-discovery/en/The Mom Test - Rob Fitzpatrick.epub` | 75 | 10 |
| 7 | `lean-startup` | The Lean Startup | `sources/startups/lean-startup/en/The Lean Startup - Eric Ries.pdf` | 297 | 104 |
| 8 | `inspired-product` | INSPIRED | `sources/product-management/inspired/en/INSPIRED - Marty Cagan.pdf` | 289 | 136 |
| 9 | `positioning-battle-for-your-mind` | Positioning: The Battle for Your Mind | `sources/business-marketing/positioning/en/Positioning - The Battle for Your Mind - Al Ries Jack Trout and Philip Kotler.pdf` | 171 | 6 |
| 10 | `spin-selling` | SPIN Selling | `sources/business-sales/sales-methods/en/SPIN Selling - Neil Rackham.pdf` | 215 | 81 |
| 11 | `good-strategy-bad-strategy` | Good Strategy Bad Strategy | `sources/business-strategy/strategy/en/Good Strategy Bad Strategy - Richard Rumelt.pdf` | 298 | 30 |
| 12 | `mans-search-for-meaning` | Man's Search for Meaning | `sources/philosophy-psychology/existential-psychology/en/Man's Search for Meaning - Viktor Frankl.pdf` | 126 | 7 |
| 13 | `economics-one-lesson` | Economics in One Lesson | `sources/economics-finance/economics/en/Economics in One Lesson - Henry Hazlitt.pdf` | 146 | 15 |
| 14 | `naval-almanack` | The Almanack of Naval Ravikant | `sources/almanacks/naval-ravikant/en/The Almanack of Naval Ravikant - Eric Jorgenson.pdf` | 113 | 3 |
| 15 | `questions-that-sell` | Questions That Sell | `sources/business-sales/question-based-selling/en/Questions That Sell - Paul Cherry.epub` | 110 | 2 |
| 16 | `secrets-question-based-selling` | Secrets of Question-Based Selling | `sources/business-sales/question-based-selling/en/Secrets of Question-Based Selling - Thomas Freese.pdf` | 335 | 34 |
| 17 | `trading-in-the-zone` | Trading in the Zone | `sources/economics-finance/trading/en/Trading in the Zone - Mark Douglas.pdf` | 202 | 26 |
