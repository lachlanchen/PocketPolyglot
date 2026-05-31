<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-Hans.md">中文</a> ·
  <a href="README.ja.md">日本語</a>
</p>

# PocketPolyglot

言語学習向けに、美しいポケットサイズのインターリニア本を生成します。

PocketPolyglot は、二言語テキストをルビ、ふりがな、ピンイン、文法色分け、行単位の対応を持つ PDF 小冊子に変換するためのツールキットです。現在の制作ワークフローは中国語と日本語を中心にしていますが、JSON モデルは言語ペアに依存しません。英日、中英、古典語と現代語の対読などにも応用できます。

このリポジトリは原典テキストの配布場所ではなく、テンプレート、スクリプト、サンプル、プレビュー、制作手順をまとめたものです。完全な書籍 PDF を公開する場合は、原文と翻訳の再配布権を確認してください。

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
make readme-previews
```

## 主な構成

| パス | 役割 |
| --- | --- |
| `tex/` | XeLaTeX のポケット本テンプレート |
| `scripts/books/` | EPUB/PDF/Markdown 前処理とプレビュー生成 |
| `scripts/interlinear/` | JSON 分割、検証、レンダリング、コンパイル |
| `data/interlinear/sample.json` | 公開用の構造化サンプル |
| `assets/readme-previews/` | PDF の第一ページから作る README プレビュー |
| `sources/` | ローカル原典ファイル、Git では無視 |
| `build/` | 生成 PDF と中間ファイル、Git では無視 |

Website: [learn.lazying.art](https://learn.lazying.art)
