[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

言語学習向けに、美しいポケットサイズのインターリニア本を生成します。

PocketPolyglot は、二言語テキストをルビ、ふりがな、ピンイン、文法色分け、行単位の対応を持つ PDF 小冊子に変換するためのツールキットです。現在の制作ワークフローは中国語と日本語を中心にしていますが、JSON モデルは言語ペアに依存しません。英日、中英、古典語と現代語の対読などにも応用できます。

このリポジトリは原典テキストの配布場所ではなく、テンプレート、スクリプト、サンプル、プレビュー、制作手順をまとめたものです。完全な書籍 PDF を公開する場合は、原文と翻訳の再配布権を確認してください。

## 四種類の出力例

同じ『こころ』の本文ページを、標準の四種類としてレンダリングした例です。

<p align="center">
  <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="こころの中国語本文カラー、中国語本文白黒、日本語本文カラー、日本語本文白黒の四種類" width="100%">
</p>

中国語と日本語は現在の代表例です。対応テキストと読みを用意すれば、英日、中英、古典語と現代語、教師注釈付きリーダーなど、ほかの言語ペアにも同じモデルを使えます。

## 出力形式

完成した本は通常、次の四種類で出力できます。

| 主本文 | カラー版 | 白黒版 |
| --- | --- | --- |
| 中国語本文、日本語注 | 文法色、ピンイン、ふりがな | 電子ペーパー向け |
| 日本語本文、中国語注 | 文法色、ふりがな、ピンイン | 電子ペーパー向け |

## よく使うコマンド

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

## 主な構成

| パス | 役割 |
| --- | --- |
| `tex/` | XeLaTeX のポケット本テンプレート |
| `scripts/books/` | EPUB/PDF/Markdown 前処理とプレビュー生成 |
| `scripts/interlinear/` | JSON 分割、検証、レンダリング、コンパイル |
| `data/interlinear/sample.json` | 公開用の構造化サンプル |
| `assets/readme-previews/` | PDF の第一ページから作る README プレビュー |
| `assets/edition-comparisons/` | 同じ PDF ページから作る四種類比較画像 |
| `sources/` | ローカル原典ファイル、Git では無視 |
| `build/` | 生成 PDF と中間ファイル、Git では無視 |

Website: [learn.lazying.art](https://learn.lazying.art)
