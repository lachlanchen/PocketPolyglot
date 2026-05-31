[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

أنشئ كتبا interlinear جميلة بحجم الجيب لتعلم اللغات.

PocketPolyglot يحول النصوص الثنائية اللغة إلى ملفات PDF صغيرة تحتوي على ruby وfurigana وpinyin وتلوين نحوي ومحاذاة سطرا بسطر. يركز سير العمل الحالي على الصينية واليابانية، لكن نموذج البيانات يصلح لأزواج أخرى مثل EN-JP وZH-EN والقراءة بين النص الكلاسيكي والحديث.

هذا المستودع هو مجموعة أدوات: قوالب TeX، وسكربتات Python، وعينات JSON، وصور معاينة، وملاحظات pipeline. انشر الكتب الكاملة فقط عندما تكون حقوق النص والترجمة واضحة وقابلة لإعادة التوزيع.

## أربع نسخ

الصفحة الداخلية نفسها من Kokoro معروضة في النسخ الأربع القياسية:

<p align="center">
  <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro in four PocketPolyglot editions" width="100%">
</p>

## المخرجات

| النص الرئيسي | ملون | أبيض وأسود |
| --- | --- | --- |
| الصينية كنص رئيسي مع ملاحظات يابانية | تلوين نحوي، pinyin، furigana | مناسب لشاشات e-ink |
| اليابانية كنص رئيسي مع ملاحظات صينية | تلوين نحوي، furigana، pinyin | مناسب لشاشات e-ink |

## الأوامر

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

الموقع: [learn.lazying.art](https://learn.lazying.art)
