[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://github.com/lachlanchen/lachlanchen/blob/main/figs/banner.png)

# PocketPolyglot

언어 학습을 위한 아름다운 포켓 크기 인터리니어 책을 생성합니다.

PocketPolyglot은 이중 언어 텍스트를 루비, 후리가나, 병음, 문법 색상, 줄 단위 정렬을 갖춘 작은 PDF 책으로 바꿉니다. 현재 제작 예시는 중국어와 일본어 중심이지만, 같은 모델은 EN-JP, ZH-EN, 고전-현대 대조 읽기 등 다른 언어 조합에도 사용할 수 있습니다.

이 저장소는 원문 도서 배포처가 아니라 도구 모음입니다. TeX 템플릿, Python 스크립트, JSON 예시, 미리보기 이미지, 파이프라인 노트를 제공합니다. 전체 책 PDF는 원문과 번역의 재배포 권리가 명확할 때만 공개하세요.

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
