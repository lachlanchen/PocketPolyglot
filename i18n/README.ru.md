[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

# PocketPolyglot

Создавайте красивые карманные интерлинейные книги для изучения языков.

PocketPolyglot превращает двуязычные тексты в небольшие PDF с ruby, фуриганой, пиньинем, грамматической цветовой разметкой и построчным выравниванием. Сейчас основной пример — китайский и японский, но модель подходит и для EN-JP, ZH-EN, классический-современный и других пар языков.

Этот репозиторий является набором инструментов: шаблоны TeX, Python-скрипты, пример JSON, изображения предпросмотра и заметки о pipeline. Полные книги стоит публиковать только при наличии прав на распространение текста и перевода.

## Четыре Издания

Одна и та же внутренняя страница Kokoro, отрисованная в четырех стандартных вариантах:

<p align="center">
  <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro in four PocketPolyglot editions" width="100%">
</p>

## Вывод

| Основной текст | Цвет | Черно-белый |
| --- | --- | --- |
| Китайский текст с японскими примечаниями | Грамматические цвета, пиньинь, фуригана | Для e-ink |
| Японский текст с китайскими примечаниями | Грамматические цвета, фуригана, пиньинь | Для e-ink |

## Команды

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

Сайт: [learn.lazying.art](https://learn.lazying.art)
