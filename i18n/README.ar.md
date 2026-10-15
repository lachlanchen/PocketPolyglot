[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner — apps and four buddies](https://lazying.art/media/brand/lazyingart-intro.gif)](https://lazying.art)

# PocketPolyglot

أنشئ كتبا interlinear جميلة بحجم الجيب لتعلم اللغات.

PocketPolyglot يحول النصوص الثنائية اللغة إلى ملفات PDF صغيرة تحتوي على ruby وfurigana وpinyin وتلوين نحوي ومحاذاة سطرا بسطر. يركز سير العمل الحالي على الصينية واليابانية، لكن نموذج البيانات يصلح لأزواج أخرى مثل EN-JP وZH-EN والقراءة بين النص الكلاسيكي والحديث.

هذا المستودع هو مجموعة أدوات: قوالب TeX، وسكربتات Python، وعينات JSON، وصور معاينة، وملاحظات pipeline. انشر الكتب الكاملة فقط عندما تكون حقوق النص والترجمة واضحة وقابلة لإعادة التوزيع.

## دعم PocketPolyglot

<!-- support:start -->
[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen)
[![LazyingArt Support](https://img.shields.io/badge/LazyingArt-Support-0EA5E9?style=for-the-badge)](https://chat.lazying.art/donate)
[![PayPal Support](https://img.shields.io/badge/PayPal-Support-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen)
[![Stripe Support](https://img.shields.io/badge/Stripe-Support-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400)
<!-- support:end -->

## PocketPolyglot Studio

يجمع Studio عمليات LinguaLeaf وOCR وتحويل PDF إلى TeX والتحقق والتصدير في تطبيق ويب وواجهة CLI محلية، مع وظائف tmux قابلة للاستئناف وتحقق قائم على الأدلة.

[![PocketPolyglot Studio مع طابور تلميع تقني مباشر](../studio/docs/images/pocketpolyglot-studio-queue.png)](../studio/docs/images/pocketpolyglot-studio-queue.png)

## جملة واحدة بعرض كامل

مثال JP-main من Kokoro: نص ياباني مع furigana، وتعليق صيني مع pinyin، وألوان نحوية على الكلمات المتقابلة.

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="Kokoro JP-main sentence with furigana, Chinese comment, pinyin, and grammar color" width="100%">
  </a>
</p>

## أربع نسخ

الصفحة الداخلية نفسها من Kokoro معروضة في النسخ الأربع القياسية:

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro in four PocketPolyglot editions" width="100%">
  </a>
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

## الاستشهاد

إذا استخدمت PocketPolyglot في البحث أو التدريس، فاستشهد بالمستودع. يقرأ GitHub ملف [CITATION.cff](../CITATION.cff) ويعرض خيار **Cite this repository**.

```bibtex
@software{chen_pocketpolyglot_2026,
  author = {Chen, Lachlan},
  title = {PocketPolyglot: Multilingual Interlinear Pocket-Book Studio},
  year = {2026},
  url = {https://github.com/lachlanchen/PocketPolyglot}
}
```
