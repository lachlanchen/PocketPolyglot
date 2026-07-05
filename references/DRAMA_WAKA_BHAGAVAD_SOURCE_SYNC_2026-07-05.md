# Drama, Waka, Buddhist, Guoyu, And Bhagavad Source Sync - 2026-07-05

These local source files were copied from `/home/lachlan/Downloads` into
ignored `sources/` folders. The original downloads were not moved. This file is
the tracked inventory; the copied PDFs/EPUBs/MOBI files remain local assets and
are not committed.

| Work | Language / Role | Source file | Stored path |
| --- | --- | --- | --- |
| 西廂記 / The Story of the Western Wing | English translation | `/home/lachlan/Downloads/The Story of the Western Wing.pdf` | `sources/xixiangji/en/english-translation/The Story of the Western Wing.pdf` |
| 牡丹亭 / The Peony Pavilion | English translation | `/home/lachlan/Downloads/The Peony Pavilion _ Mudan ting.pdf` | `sources/mudanting/en/english-translation/The Peony Pavilion - Mudan ting.pdf` |
| 万葉集 | Japanese study | `/home/lachlan/Downloads/万葉の詩情 (ディスカヴァーebook選書).epub` | `sources/manyoshu/jp/modern-study-epub/万葉の詩情（ディスカヴァーebook選書）.epub` |
| 万葉集 | Japanese modern selection | `/home/lachlan/Downloads/体感訳 万葉集 令和に読みたい名歌３６.epub` | `sources/manyoshu/jp/modern-selection-epub/体感訳 万葉集 令和に読みたい名歌36.epub` |
| Man'yoshu | English lyrics/reference | `/home/lachlan/Downloads/Land of the Reed Plains_ Ancient Japanese Lyrics from the Manyoshu.mobi` | `sources/manyoshu/en/english-lyrics/Land of the Reed Plains - Ancient Japanese Lyrics from the Manyoshu.mobi` |
| Man'yoshu | English translation | `/home/lachlan/Downloads/The Manyōshū _ the Nippon Gakujutsu Shinkōkai translation of one thousand poems.pdf` | `sources/manyoshu/en/english-translation/The Manyoshu - Nippon Gakujutsu Shinkokai Translation of One Thousand Poems.pdf` |
| Man'yoshu | English translation | `/home/lachlan/Downloads/1000 Poems from the Manyoshu_ The Complete Nippon Gakujutsu Shinkokai Translation  .pdf` | `sources/manyoshu/en/english-translation/1000 Poems from the Manyoshu - Complete Nippon Gakujutsu Shinkokai Translation.pdf` |
| 新古今和歌集 | Japanese modern translation/commentary | `/home/lachlan/Downloads/新古今和歌集（現代語訳・評釈付）.epub` | `sources/shinkokin-wakashu/jp/modern-translation-epub/新古今和歌集（現代語訳・評釈付）.epub` |
| 古今和歌集 / Japanese poetry | English anthology | `/home/lachlan/Downloads/100 Poems from the Japanese.epub` | `sources/kokin-wakashu/en/english-anthology/100 Poems from the Japanese.epub` |
| Japanese literature anthology | English anthology | `/home/lachlan/Downloads/Traditional Japanese Literature. An Anthology, Beginnings to 1600, Abridged Edition.epub` | `sources/japanese-literature-anthology/en/Traditional Japanese Literature - An Anthology Beginnings to 1600 Abridged Edition.epub` |
| 古今和歌集 | Spanish reference | `/home/lachlan/Downloads/Poesía clásica japonesa [Kokinwakashū].pdf` | `sources/kokin-wakashu/es/spanish-translation/Poesía clásica japonesa [Kokinwakashu].pdf` |
| Bhagavad Gita / 薄伽梵歌 | English Sanskrit-aware translation | `/home/lachlan/Downloads/The Bhagavad Gita.pdf` | `sources/bhagavad-gita/en/english-translation/The Bhagavad Gita.pdf` |
| Bhagavad Gita / 薄伽梵歌 | Chinese scan/reference | `/home/lachlan/Downloads/薄伽梵歌.pdf` | `sources/bhagavad-gita/zh/chinese-translation/薄伽梵歌.pdf` |
| 國語 / Guoyu | Chinese commentary | `/home/lachlan/Downloads/国语集解.pdf` | `sources/guoyu/zh/chinese-commentary/国语集解.pdf` |
| 古今和歌集 | Japanese source PDF | `/home/lachlan/Downloads/古今和歌集.pdf` | `sources/kokin-wakashu/jp/source-pdf/古今和歌集.pdf` |
| 古今和歌集 | Japanese modern translation | `/home/lachlan/Downloads/古今和歌集（全現代語訳付）.epub` | `sources/kokin-wakashu/jp/modern-translation-epub/古今和歌集（全現代語訳付）.epub` |
| 維摩詰所說經 | English translation | `/home/lachlan/Downloads/VIMALAKIRTI NIRDESA SUTRA.pdf` | `sources/vimalakirti-sutra/en/english-translation/VIMALAKIRTI NIRDESA SUTRA.pdf` |
| 西廂記 | Chinese edition | `/home/lachlan/Downloads/西廂記.pdf` | `sources/xixiangji/zh/chinese-edition/西廂記.pdf` |
| 六祖壇經 / Platform Sutra | English translation | `/home/lachlan/Downloads/The Platform Sutra of the Sixth Patriarch.pdf` | `sources/platform-sutra/en/english-translation/The Platform Sutra of the Sixth Patriarch.pdf` |
| 六祖壇經 / Platform Sutra | Chinese edition | `/home/lachlan/Downloads/六祖大師法寶壇經.pdf` | `sources/platform-sutra/zh/chinese-edition/六祖大師法寶壇經.pdf` |
| 維摩詰所說經 | Chinese source EPUB | `/home/lachlan/Downloads/维摩诘所说经.epub` | `sources/vimalakirti-sutra/zh/source-epub/维摩诘所说经.epub` |

## Prepared Task

`bhagavad-gita` is prepared as an English-spine trilingual task:

- task plan: `books/bhagavad-gita/book-plan.json`
- extracted Markdown spine: `books/bhagavad-gita/markdown/en.md`
- manifest: `books/bhagavad-gita/work/trilingual/chunks/manifest.json`
- local chunk tasks: `books/bhagavad-gita/work/trilingual/chunks/chunks.jsonl`

The Sargeant PDF is scholarly and contains Sanskrit, transliteration,
word-by-word glosses, and grammatical notes. The preparation script extracts the
English verse translation block as the source spine and keeps the Sanskrit/gloss
material as reference only.
