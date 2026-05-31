[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

為語言學習生成漂亮的口袋尺寸逐行對照書。

PocketPolyglot 可以把雙語文本轉換成帶注音、拼音、語法顏色和逐行對齊的 PDF 小書。目前工作流主要展示中日雙語，但資料模型不限定語言：英日、中英、古今對讀、文言與現代譯文也能使用同一套結構。

本專案是工具包，不是原始圖書倉庫。它包含 TeX 模板、Python 腳本、JSON 範例、預覽圖和流水線說明。公開發布完整圖書前，請確認原文和譯文都有可再分發權利。

## 單句全寬示例

《心》的日文主文示例：日文主文帶假名，中文註釋帶拼音，並保留逐詞語法顏色。

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="《心》的日文主文單句示例，含假名、中文註釋、拼音和語法顏色" width="100%">
  </a>
</p>

## 四種版本示例

同一頁《心》可以渲染成四種標準版本：

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="《心》的四種 PocketPolyglot 版本" width="100%">
  </a>
</p>

## 輸出形式

| 主文本 | 彩色版 | 黑白版 |
| --- | --- | --- |
| 中文主文，日文註釋 | 語法顏色、拼音、假名 | 適合電紙書 |
| 日文主文，中文註釋 | 語法顏色、假名、拼音 | 適合電紙書 |

## 常用命令

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

網站：[learn.lazying.art](https://learn.lazying.art)
