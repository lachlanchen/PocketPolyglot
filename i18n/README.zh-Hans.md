<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-Hans.md">中文</a> ·
  <a href="README.ja.md">日本語</a>
</p>

# PocketPolyglot

为语言学习生成漂亮的口袋尺寸逐行对照书。

PocketPolyglot 可以把双语文本转换成带注音、拼音、语法颜色和逐行对齐的 PDF 小书。当前工作流主要用于中日双语，但数据结构不限定语言：英日、中英、古今对读、文言和现代译文也可以使用同一套模型。

项目本身是工具包，不是原始图书仓库。它包含 TeX 模板、Python 脚本、JSON 示例、预览图和流水线说明。公开发布完整图书前，请确认原文和译文都有可再分发权利。

## 四种版本示例

同一页《心》可以渲染成四种标准版本：

<p align="center">
  <img src="../assets/edition-comparisons/kokoro-four-editions-page-20.png" alt="《心》的中文主文彩色、中文主文黑白、日文主文彩色、日文主文黑白四种版本" width="100%">
</p>

中日只是当前展示语言。只要准备好对齐文本和读音，同一模型也可以用于英日、中英、古今对读、教师注释本等其他语言组合。

## 输出形式

完整书籍通常生成四种选择：

| 主文本 | 彩色版 | 黑白版 |
| --- | --- | --- |
| 中文主文，日文注释 | 语法颜色、拼音、假名 | 适合电纸书 |
| 日文主文，中文注释 | 语法颜色、假名、拼音 | 适合电纸书 |

## 常用命令

```sh
make sample
make interlinear
make interlinear-jp-main
make export-books
make readme-previews
```

## 核心结构

| 路径 | 用途 |
| --- | --- |
| `tex/` | XeLaTeX 口袋书模板 |
| `scripts/books/` | EPUB/PDF/Markdown 预处理与预览图生成 |
| `scripts/interlinear/` | JSON 切分、校验、渲染和编译 |
| `data/interlinear/sample.json` | 可公开的结构化示例 |
| `assets/readme-previews/` | 从 PDF 第一页生成的 README 预览图 |
| `sources/` | 本地原始书源，Git 忽略 |
| `build/` | 生成的 PDF 和中间文件，Git 忽略 |

网站：[learn.lazying.art](https://learn.lazying.art)
