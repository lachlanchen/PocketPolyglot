# Book Processing Status

This table is the working order for PocketPolyglot/LinguaLeaf book production. Keep processed books separate from the future queue. Put large anthology, reference, "complete works", and classical collection projects later unless the user explicitly promotes one.

## Production Target

The default future pipeline is trilingual EN/JP/ZH. Prepare one strict JSON source first, then compile 12 PDFs from it: `zh-en`, `en-zh`, `zh-ja`, `ja-zh`, `ja-en`, and `en-ja`, each in `color` and `blackwhite`. Use English as the alignment spine for modern world literature when a reliable English source is available.

For classical Chinese books, keep the classical original as a preserved source layer, but generate Japanese and English from the modern Chinese translation/paraphrase rather than directly from ambiguous OCR or terse classical syntax. The modern Chinese layer is the meaning bridge; the classical text remains visible as the original where the renderer supports it.

## Processed / Compiled

| Order | Book ID | Title | Source Area | Status | Notes |
|---:|---|---|---|---|---|
| 1 | `kokoro` | 心 / こころ | `sources/kokoro` | Complete | Early pipeline book; compiled both directions. |
| 2 | `snow-country` | 雪国 | `sources/snow-country` | Complete | Compiled both directions, color and blackwhite. |
| 3 | `no-longer-human` | 人間失格 | `sources/no-longer-human` | Complete | Compiled both directions, color and blackwhite. |
| 4 | `rashomon-stories` | 羅生門短篇集 | `sources/罗生门` | Complete | Short-story collection, compiled both directions. |
| 5 | `sichuan-folk-stories-vol1` | 中国民间故事集成 四川卷 上 | source PDF at root | Provisional compiled | OCR-heavy; output exists, but source recognition needs deeper cleanup. |
| 6 | `kinkakuji` | 金阁寺 / 金閣寺 | `sources/金阁寺` | Complete | Compiled both directions. |
| 7 | `sishu-jizhu` / `sishu-jizhu-aginti` | 四書章句集註 | `sources/sishu` | Compiled | Classical text; keep future refinements separate from main novel queue. |
| 8 | `shiji-aginti` | 史記 | `sources/shiji` | Prototype compiled | AgInTi version exists; full robust Shiji pass remains a later classical task. |
| 9 | `the-old-capital` | 古都 | root EPUB/PDF sources | Complete | Compiled both directions. |
| 10 | `izu-no-odori` | 伊豆的舞女 / 伊豆の踊子 | root EPUB source | Complete | Compiled both directions. |
| 11 | `genji-modern` | 源氏物语 / 源氏物語 | `sources/源氏物语` | Complete | Large modern-language Genji pass. |
| 12 | `kojiki` | 古事記 | `sources/kojiki` | Complete | Compiled from prepared sources. |
| 13 | `woman-in-the-dunes` | 砂女 / 砂の女 | `sources/砂女` | Complete | 1150/1150 chunks reviewed; four PDFs compiled. |
| 14 | `gone-with-the-wind` | Gone With the Wind / 飘 / 風と共に去りぬ | `sources/gone-with-the-wind` | Complete | Trilingual EN-JP-ZH; 12 PDFs compiled. |
| 15 | `botchan` | 少爷 / 坊っちゃん / Botchan | `sources/少爷 - Botchan` + Natsume source reservoir | Complete | Trilingual EN-JP-ZH; 261/261 chunks, 12 PDFs compiled. |
| 16 | `i-am-a-cat` | 我是猫 / 吾輩は猫である / I Am a Cat | `sources/I-am-a-cat` + Natsume source reservoir | Complete | Trilingual EN-JP-ZH; 251/251 chunks, 12 PDFs compiled. |

## Recommended Future Queue

This order prioritizes intriguing, readable, narrative books first. Prepared books with existing Markdown/chunks are marked, but short anthologies and classical collections are moved lower unless they are especially attractive.

| Priority | Proposed ID | Title | Source Path | Readiness | Reason |
|---:|---|---|---|---|---|
| 1 | `silence` | 沉默 / Silence | `sources/Silence.epub` | English Markdown exists | Powerful story; needs JP/ZH source pairing strategy. |
| 2 | `inugami-curse` | 犬神家族 / The Inugami Curse | `sources/犬神家族 - The Inugami Curse` | Sources grouped | Mystery novel, engaging and readable. |
| 3 | `spring-snow` | 春雪 / Spring Snow | `sources/春雪 - Spring Snow` | Sources grouped | Mishima, strong literary priority. |
| 4 | `temple-of-dawn` | 晓寺 / The Temple of Dawn | `sources/晓寺 - The Temple of Dawn` | Sources grouped | Continue Mishima sequence after Spring Snow. |
| 5 | `silent-cry` | 万延元年的足球队 / The Silent Cry | `sources/The Silent Cry` | Sources grouped | Major Oe work; high literary value. |
| 6 | `personal-matter` | 个人的体验 | `sources/个人的体验` | Sources grouped | Important Oe, likely manageable. |
| 7 | `heike` | 平家物语 / 平家物語 | `sources/平家物语` | Sources grouped | Epic and famous; harder than modern novels but very attractive. |
| 8 | `pillow-book` | 枕草子 | `sources/枕草子` | Sources grouped | Classic prose; good after narrative-first queue. |
| 9 | `ginga-tetsudo` | 銀河鉄道の夜 | `sources/銀河鉄道の夜` | Prepared, 604 chunks | Short and beloved; good when we want a faster run. |
| 10 | `chumon-no-ooi-ryoriten` | 注文の多い料理店 | `sources/注文の多い料理店` | Prepared, 2698 chunks | Children’s stories; keep after stronger single-book priorities. |
| 11 | `kitchen` | 厨房 / Kitchen | `sources/厨房.epub` | Source only | Modern, accessible, good learner book if paired sources can be found. |
| 12 | `norwegian-wood` | 挪威的森林 / Norwegian Wood | `sources/Norwegian Wood.epub` | Source only | Popular but source pairing needs care. |
| 13 | `kafka-on-the-shore` | 海边的卡夫卡 / Kafka on the Shore | `sources/Kafka on the Shore  .epub` | Source only | Popular, long, likely costly. |
| 14 | `hard-boiled-wonderland` | 世界尽头与冷酷仙境 | `sources/Hard-Boiled Wonderland and the End of the World.epub` | Source only | Interesting Murakami, long. |
| 15 | `inspector-imanishi` | 砂器 / Inspector Imanishi Investigates | `sources/Inspector Imanishi Investigates.epub` | Source only | Mystery; needs Japanese/Chinese pairing source. |
| 16 | `byakuyako` | 白夜行 | `sources/[東野圭吾] 白夜行.epub` | Source only | Popular mystery, long. |
| 17 | `suspect-x` | 嫌疑人X的献身 | `sources/嫌疑人X的献身 (东野圭吾作品).epub` | Source only | Popular and compact; needs source pairing. |
| 18 | `runaway-horses` | 奔马 | root EPUB source | Source only | Sea of Fertility volume 2; place after Spring Snow. |
| 19 | `decay-of-the-angel` | 天人五衰 / The Decay of the Angel | `sources/The Decay of the Angel.epub` | Source only | Sea of Fertility volume 4; keep after earlier volumes. |
| 20 | `sound-of-waves` | 潮骚 | root PDF source | Source only | Mishima, attractive but PDF-only. |
| 21 | `box-man` | 箱男 | root EPUB source | Source only | Abe Kobo; interesting after 砂女. |
| 22 | `setting-sun` | 斜陽 | `sources/斜陽.epub` | Source only | Dazai, good but source pairing must be prepared. |
| 23 | `hell-screen` | 地狱变 / 地獄変 | `sources/地狱变.epub` | Source only | Short Akutagawa; can be paired with Akutagawa collections if useful. |
| 24 | `ten-nights` | 十夜之梦 | `sources/十夜之梦.pdf` | Source only | Short Soseki; PDF extraction likely needed. |

## Late Anthology / Reference Backlog

These are valuable, but they behave more like almanac/collection/reference projects. Keep them later because they are large, structurally uneven, OCR-heavy, or less immediately story-driven.

| Late Order | Proposed ID | Title / Group | Source Path | Why Later |
|---:|---|---|---|---|
| A1 | `shiji-full` | 史記 full robust edition | `sources/shiji` | Very large classical multi-source task; keep for AgInTi/deep review. |
| A2 | `shijing` | 詩經 | `sources/shijing` plus root 詩経 files | Classical anthology with commentary layers. |
| A3 | `chuci` | 楚辞 | `sources/chuci` | Classical poetry/commentary; alignment is specialized. |
| A4 | `guwen-guanzhi` | 古文观止 | `sources/guwen-guanzhi` | Anthology of many essays; needs item-by-item structure. |
| A5 | `sishu-refinement` | 四書 / 朱子集注 refinements | `sources/sishu` | Already compiled once; future work should be a dedicated classical pass. |
| A6 | `zhuzi-quanshu` | 朱子全书 | root `朱子全书 *.pdf` | Huge reference set, not a first-pass learner book. |
| A7 | `guwen-cileizuan` | 古文辞类纂 | root `中华传世文选...古文辞类纂.pdf` | Large anthology/reference. |
| A8 | `xianqin-poetry-dict` | 先秦诗鉴赏辞典 | root PDF | Reference dictionary, not continuous reading. |
| A9 | `natsume-complete` | 夏目漱石作品全集 | root EPUB | Useful source reservoir, but individual works should be processed separately. |
| A10 | `akutagawa-complete` | 芥川龙之介全集 1-5 | root PDFs | Use as source reservoir for selected stories. |
| A11 | `dazai-selected` | 太宰治小说精选 | root PDF | Anthology; use for individual work extraction. |
| A12 | `kawabata-volume-5` | 川端康成十卷集 5 | root PDF | Collection/source reservoir; individual works first. |
| A13 | `hundred-percent-girl` | 遇到百分之百的女孩 | root PDF | Murakami short-story collection; defer after single novels. |
| A14 | `higashino-set` | 东野圭吾天王套装 | root EPUB | Box set; process individual novels first. |
| A15 | `kojiki-commentary` | 诸神流窜 | root PDF | Secondary commentary, not primary interlinear text. |
| A16 | `shijing-intro` | 『詩経』歌の原始 | root PDF | Secondary scholarly source. |
| A17 | `hard-boiled-study` | 世界尽头哲学解读 | root EPUB | Secondary commentary, not primary interlinear text. |
| A18 | `ancient-chinese-english-origin` | 古漢語是英語的母語 | root PDF | Outside main bilingual literature pipeline. |

## Maintenance Rules

- Move a title from the future queue to processed only after full chunk coverage, no stale chunks, and compiled PDFs are available.
- Keep processed books in the processed table even if later refinements are needed.
- Future single-title books should target EN/JP/ZH JSON and 12 PDFs unless the user explicitly asks for a smaller bilingual pass.
- For classical Chinese, generate JP/EN from the modern Chinese meaning bridge and retain the classical original as source/original text.
- Prefer one named work over a complete works volume or anthology.
- Promote an anthology only when the user asks for that specific collection.
- For future queue ordering, prefer readable, intriguing narrative works before reference/almanac-style collections.
