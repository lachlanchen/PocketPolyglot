[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

Erzeuge schöne interlineare Taschenbücher für das Sprachenlernen.

PocketPolyglot verwandelt zweisprachige Texte in kleine PDFs mit Ruby, Furigana, Pinyin, grammatischer Farbmarkierung und zeilenweiser Ausrichtung. Der aktuelle Produktionsfluss zeigt Chinesisch und Japanisch, das Datenmodell eignet sich aber auch für EN-JP, ZH-EN, klassisch-modern und andere Sprachpaare.

Dieses Repository ist ein Werkzeugkasten: TeX-Vorlagen, Python-Skripte, JSON-Beispiele, Vorschaubilder und Pipeline-Notizen. Vollständige Bücher sollten nur veröffentlicht werden, wenn Text und Übersetzung weiterverbreitet werden dürfen.

## Vier Ausgaben

Dieselbe Innenseite aus Kokoro als vier Standardausgaben:

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro in vier PocketPolyglot-Ausgaben" width="100%">
  </a>
</p>

## Ausgabeformen

| Haupttext | Farbe | Schwarzweiß |
| --- | --- | --- |
| Chinesisch mit japanischen Notizen | Grammatikfarben, Pinyin, Furigana | Für E-Ink-Geräte |
| Japanisch mit chinesischen Notizen | Grammatikfarben, Furigana, Pinyin | Für E-Ink-Geräte |

## Befehle

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

Website: [learn.lazying.art](https://learn.lazying.art)
