# Classical Quadrilingual Source Tasks - 2026-06-25

These tasks were prepared from the Books archive inventory at
`../Books/references/CLASSICAL_TEXT_VERSION_TABLE_2026-06-25.md` and later
local source imports.

## Default Task Shape

All listed works are classical Chinese tasks. The default output should keep
Chinese wenyan as the main stream and add three aligned note layers:

1. English
2. Modern Japanese
3. Modern Chinese

Machine-readable source plan:
`data/source-plan/classical-quadrilingual-source-batch.json`.

Default renderer target:
`quadrilingual_wenyan_main`, with `default_note_order.wenyan` set to
`["en", "ja_modern", "zh_modern"]`.

## Prepared Sources

| Work | Book ID | Main Source | Reference Layers | Caveat |
| --- | --- | --- | --- | --- |
| 莊子 / Zhuangzi | `zhuangzi` | `sources/zhuangzi/zh/wenyan-wikisource` | modern Chinese annotated PDF, Burton Watson English, Giles Gutenberg, Japanese scan | Japanese retelling files are secondary, not a complete aligned source. |
| 周易 / Book of Changes | `yijing` | `sources/yijing/zh/wenyan-wikisource` complete Chinese Wikisource mirror | Chinese annotated scan, two English references, Japanese study PDF | Reference PDFs are not aligned text; use them for meaning and terminology while keeping the Wikisource Wenyan spine complete. |
| 漢書 / Book of Han | `han-shu` | `sources/han-shu/zh/wenyan-wikisource` plus Gutenberg/EPUB alternates | Dubs English volume 1 | Japanese Wikisource is index-only; modern Japanese must be generated where needed. |
| 後漢書 / Book of Later Han | `hou-han-shu` | `sources/hou-han-shu/zh/wenyan-wikisource` plus 李賢注 scan | partial English military/history reference, 倭傳 Japanese excerpt | English/Japanese references are partial and chapter-limited. |
| 三國志 / Records of the Three Kingdoms | `sanguozhi` | `sources/sanguozhi/zh/wenyan-wikisource` plus Gutenberg/裴松之注 EPUB | incomplete English Wikisource, English selections | Japanese Wikisource is index-only; English references are incomplete. |
| 左傳 / Zuo Tradition | `zuozhuan` | Chinese Wikisource/Gutenberg exports plus local annotated EPUB | Legge scan, local English translation/commentary, Japanese study | Japanese reference is study material, not aligned translation. |
| 戰國策 / Strategies of the Warring States | `zhanguoce` | Chinese Wikisource export and local EPUB | Chan-kuo Ts'e English translation | Modern Japanese must be generated where no reliable source exists. |
| 山海經 / Classic of Mountains and Seas | `shanhaijing` | Chinese Wikisource/Gutenberg exports and local PDF | English translation PDF | Modern Japanese must be generated where no reliable source exists. |
| 徐霞客遊記 / Xu Xiake Youji | `xu-xiake-youji` | Chinese Wikisource/Gutenberg exports and local PDF | English study/reference | English study is not a complete aligned translation. |
| 水經注 / Commentary on the Water Classic | `shui-jing-zhu` | Chinese Wikisource export plus local editions | English/Japanese open references | English/Japanese references are background only, not complete translations. |
| 國語 / Discourses of the States | `guoyu` | `sources/guoyu/zh/wenyan-wikisource` plus 四庫全書 alternate | `国语集解.pdf`, Chinese/English/Japanese open references | Main wenyan spine drops Wikisource inline commentary; keep 集解/commentary as reference, not continuation lines. |
| 資治通鑑 / Zizhi Tongjian | `zizhi-tongjian` | `sources/zizhi-tongjian/zh/資治通鑑·繁體橫排版（胡三省注）294卷全.pdf` | three Later Han English translation volumes | English references cover only selected Later Han chapters; Japanese must be generated. |
| 世說新語 / A New Account of Tales of the World | `shishuo-xinyu` | `sources/shishuo-xinyu/zh/世說新語.pdf` | Chinese 笺疏 and English translation/reference | Keep 笺疏/commentary as notes; do not merge it into continuation lines. |

## Next Pipeline Step

Do not start generation directly from raw PDFs. First convert the selected
source layers to reviewed Markdown:

- extract the wenyan spine chapter by chapter;
- extract or OCR modern Chinese references where available;
- extract English and Japanese references only as broad chapter references;
- split the wenyan spine into stable paragraph-level chunks;
- generate quadrilingual chunk JSON without replacing any source text.

The first runnable task after this preparation should create
`books/<book-id>/work/quadrilingual/chunks/manifest.json` and
`books/<book-id>/book-plan.json`, then use:

```sh
scripts/interlinear/start_quadrilingual_wenyan_tmux.sh <book-id>
```
