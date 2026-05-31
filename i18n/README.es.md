[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

# PocketPolyglot

Genera libros interlineales bonitos, de bolsillo, para aprender idiomas.

PocketPolyglot convierte textos bilingües en pequeños PDF con ruby, furigana, pinyin, color gramatical y alineación por líneas. La producción actual se centra en chino y japonés, pero el modelo sirve para otros pares como EN-JP, ZH-EN o lecturas clásico-moderno.

Este repositorio es una caja de herramientas: plantillas TeX, scripts Python, JSON de ejemplo, vistas previas y notas de flujo. Publica libros completos solo cuando los textos y traducciones tengan derechos claros de redistribución.

## Cuatro Ediciones

La misma página interior de Kokoro renderizada en las cuatro ediciones estándar:

<p align="center">
  <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro en cuatro ediciones PocketPolyglot" width="100%">
</p>

## Salidas

| Texto principal | Color | Blanco y negro |
| --- | --- | --- |
| Chino con notas japonesas | Color gramatical, pinyin, furigana | Para pantallas de tinta electrónica |
| Japonés con notas chinas | Color gramatical, furigana, pinyin | Para pantallas de tinta electrónica |

## Comandos

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

Sitio: [learn.lazying.art](https://learn.lazying.art)
