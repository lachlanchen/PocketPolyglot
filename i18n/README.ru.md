[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

Создавайте красивые карманные интерлинейные книги для изучения языков.

PocketPolyglot превращает двуязычные тексты в небольшие PDF с ruby, фуриганой, пиньинем, грамматической цветовой разметкой и построчным выравниванием. Сейчас основной пример — китайский и японский, но модель подходит и для EN-JP, ZH-EN, классический-современный и других пар языков.

Этот репозиторий является набором инструментов: шаблоны TeX, Python-скрипты, пример JSON, изображения предпросмотра и заметки о pipeline. Полные книги стоит публиковать только при наличии прав на распространение текста и перевода.

## Поддержать PocketPolyglot

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

## PocketPolyglot Studio

Studio объединяет LinguaLeaf, OCR, преобразование PDF в TeX, проверку и экспорт в локальном веб-приложении и CLI. Возобновляемые задания tmux завершаются только после проверки доказательств.

[![PocketPolyglot Studio с активной очередью технических книг](../studio/docs/images/pocketpolyglot-studio-queue.png)](../studio/docs/images/pocketpolyglot-studio-queue.png)

## Один Сегмент На Всю Ширину

Пример JP-main из Kokoro: японский основной текст с фуриганой, китайский комментарий с пиньинем и грамматические цвета на выровненных словах.

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="JP-main фрагмент Kokoro с фуриганой, китайским комментарием, пиньинем и грамматическими цветами" width="100%">
  </a>
</p>

## Четыре Издания

Одна и та же внутренняя страница Kokoro, отрисованная в четырех стандартных вариантах:

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro in four PocketPolyglot editions" width="100%">
  </a>
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

## Цитирование

Если вы используете PocketPolyglot в исследованиях или преподавании, процитируйте репозиторий. GitHub читает [CITATION.cff](../CITATION.cff) и показывает **Cite this repository**.

```bibtex
@software{chen_pocketpolyglot_2026,
  author = {Chen, Lachlan},
  title = {PocketPolyglot: Multilingual Interlinear Pocket-Book Studio},
  year = {2026},
  url = {https://github.com/lachlanchen/PocketPolyglot}
}
```
