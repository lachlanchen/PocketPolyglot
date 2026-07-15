[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

Erzeuge schöne interlineare Taschenbücher für das Sprachenlernen.

PocketPolyglot verwandelt zweisprachige Texte in kleine PDFs mit Ruby, Furigana, Pinyin, grammatischer Farbmarkierung und zeilenweiser Ausrichtung. Der aktuelle Produktionsfluss zeigt Chinesisch und Japanisch, das Datenmodell eignet sich aber auch für EN-JP, ZH-EN, klassisch-modern und andere Sprachpaare.

Dieses Repository ist ein Werkzeugkasten: TeX-Vorlagen, Python-Skripte, JSON-Beispiele, Vorschaubilder und Pipeline-Notizen. Vollständige Bücher sollten nur veröffentlicht werden, wenn Text und Übersetzung weiterverbreitet werden dürfen.

## PocketPolyglot unterstützen

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

## PocketPolyglot Studio

Studio bündelt LinguaLeaf, OCR, PDF-zu-TeX, Validierung und Export in einer lokalen Web-App und CLI. Wiederaufnehmbare tmux-Jobs werden erst nach evidenzbasierter Prüfung als abgeschlossen markiert.

[![PocketPolyglot Studio mit einer laufenden technischen Buchwarteschlange](../studio/docs/images/pocketpolyglot-studio-queue.png)](../studio/docs/images/pocketpolyglot-studio-queue.png)

## Ein Satz In Voller Breite

JP-main-Beispiel aus Kokoro: japanischer Haupttext mit Furigana, chinesischer Kommentar mit Pinyin und Grammatikfarben auf den ausgerichteten Wörtern.

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="Kokoro JP-main-Satz mit Furigana, chinesischem Kommentar, Pinyin und Grammatikfarben" width="100%">
  </a>
</p>

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

## Zitieren

Wenn du PocketPolyglot in Forschung oder Lehre verwendest, zitiere dieses Repository. GitHub liest [CITATION.cff](../CITATION.cff) und zeigt **Cite this repository** an.

```bibtex
@software{chen_pocketpolyglot_2026,
  author = {Chen, Lachlan},
  title = {PocketPolyglot: Multilingual Interlinear Pocket-Book Studio},
  year = {2026},
  url = {https://github.com/lachlanchen/PocketPolyglot}
}
```
