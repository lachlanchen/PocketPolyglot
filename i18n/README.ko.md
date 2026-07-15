[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

언어 학습을 위한 아름다운 포켓 크기 인터리니어 책을 생성합니다.

PocketPolyglot은 이중 언어 텍스트를 루비, 후리가나, 병음, 문법 색상, 줄 단위 정렬을 갖춘 작은 PDF 책으로 바꿉니다. 현재 제작 예시는 중국어와 일본어 중심이지만, 같은 모델은 EN-JP, ZH-EN, 고전-현대 대조 읽기 등 다른 언어 조합에도 사용할 수 있습니다.

이 저장소는 원문 도서 배포처가 아니라 도구 모음입니다. TeX 템플릿, Python 스크립트, JSON 예시, 미리보기 이미지, 파이프라인 노트를 제공합니다. 전체 책 PDF는 원문과 번역의 재배포 권리가 명확할 때만 공개하세요.

## PocketPolyglot 후원

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

## PocketPolyglot Studio

Studio는 LinguaLeaf, OCR, PDF-to-TeX, 검증, 내보내기를 로컬 웹 앱과 CLI에 통합합니다. 재개 가능한 tmux 작업은 증거 검증을 통과한 뒤에만 완료됩니다.

[![기술 도서 처리 대기열을 실행 중인 PocketPolyglot Studio](../studio/docs/images/pocketpolyglot-studio-queue.png)](../studio/docs/images/pocketpolyglot-studio-queue.png)

## 한 문장 전체 너비 보기

Kokoro JP-main 예시입니다. 일본어 본문에는 후리가나, 중국어 주석에는 병음, 대응 단어에는 문법 색상이 들어갑니다.

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-jp-main-sentence-page-20.png" alt="후리가나, 중국어 주석, 병음, 문법 색상이 있는 Kokoro JP-main 문장" width="100%">
  </a>
</p>

## 네 가지 판형

같은 Kokoro 본문 페이지를 네 가지 표준 판형으로 렌더링한 예시입니다.

<p align="center">
  <a href="../assets/edition-comparisons/kokoro-four-editions-page-20.png">
    <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="Kokoro four PocketPolyglot editions" width="100%">
  </a>
</p>

## 출력

| 본문 언어 | 컬러 | 흑백 |
| --- | --- | --- |
| 중국어 본문, 일본어 주석 | 문법 색상, 병음, 후리가나 | 전자잉크 화면용 |
| 일본어 본문, 중국어 주석 | 문법 색상, 후리가나, 병음 | 전자잉크 화면용 |

## 명령

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-assets
```

사이트: [learn.lazying.art](https://learn.lazying.art)

## 인용

연구나 교육에 PocketPolyglot을 사용한다면 이 저장소를 인용해 주세요. GitHub는 [CITATION.cff](../CITATION.cff)를 읽어 **Cite this repository**를 표시합니다.

```bibtex
@software{chen_pocketpolyglot_2026,
  author = {Chen, Lachlan},
  title = {PocketPolyglot: Multilingual Interlinear Pocket-Book Studio},
  year = {2026},
  url = {https://github.com/lachlanchen/PocketPolyglot}
}
```
