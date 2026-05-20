#!/usr/bin/env python3
"""Render three-layer chunk JSONs into JP-main and ZH-main LaTeX.

Produces LaTeX for pocket-size XeLaTeX compilation with:
- JP-main: ja (Japanese) primary, zh_original (classical Chinese), zh_modern
- ZH-main: zh_original primary, ja (Japanese), zh_modern
- Color grammar roles; BlackWhiteMode for BW
- TOC, title page, author with ruby
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CHUNKS_DIR = Path("data/interlinear/shiji-aginti/chunks")
BUILD_DIR = Path("build/shiji-aginti")

GRAM_COLORS = {
    "subject": "GramSubject",
    "predicate": "GramPredicate",
    "object": "GramObject",
    "attributive": "GramAttributive",
    "adverbial": "GramAdverbial",
    "complement": "GramComplement",
    "topic": "GramTopic",
    "function": "GramFunction",
}


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def render_tokens(tokens: list[dict], ruby_cmd: str) -> str:
    parts = []
    for tok in tokens:
        t = tok.get("t", "")
        r = tok.get("r", "")
        g = tok.get("g", "")
        if r:
            inner = rf"\{ruby_cmd}{{{tex_escape(t)}}}{{{tex_escape(r)}}}"
        else:
            inner = tex_escape(t)
        if g and g in GRAM_COLORS:
            inner = rf"\{GRAM_COLORS[g]}{{{inner}}}"
        parts.append(inner)
    return "".join(parts)


def render_unit(unit: dict, direction: str) -> str:
    """direction: 'jp_main' or 'zh_main'"""
    lines = []

    zh_orig = unit.get("zh_original", [])
    ja = unit.get("ja", [])
    zh_mod = unit.get("zh_modern", [])

    if direction == "jp_main":
        lines.append(r"\JpMainLine{" + render_tokens(ja, "jpruby") + "}")
        lines.append(r"\ZhOrigLine{" + render_tokens(zh_orig, "zhcnruby") + "}")
    else:
        lines.append(r"\ZhMainLine{" + render_tokens(zh_orig, "zhcnruby") + "}")
        lines.append(r"\JaCommentLine{" + render_tokens(ja, "jpruby") + "}")

    lines.append(r"\ZhModernLine{" + render_tokens(zh_mod, "zhcnruby") + "}")
    return "\n".join(lines)


def produce_tex(chunk_ids: list[str], direction: str, bw: bool) -> str:
    """Produce complete LaTeX document."""
    tex_lines = [r"\documentclass[10pt]{book}", r"\input{style.tex}"]
    if bw:
        tex_lines.append(r"\BlackWhiteMode")
    tex_lines.append(r"\begin{document}")
    tex_lines.append(r"\pagestyle{empty}")
    tex_lines.append("")
    tex_lines.append(r"\begin{center}")
    tex_lines.append(r"{\large\jpfont \zhcnruby{史}{shǐ}\zhcnruby{記}{jì}}")
    tex_lines.append(r"\vspace{0.5em}")
    tex_lines.append(r"{\normalsize \zhcnruby{司}{sī}\zhcnruby{馬}{mǎ}\zhcnruby{遷}{qiān}}")
    tex_lines.append(r"\vspace{1em}")
    tex_lines.append(r"{\footnotesize AgInTiFlow curated}")
    tex_lines.append(r"{\footnotesize https://flow.lazying.art}")
    tex_lines.append(r"{\footnotesize powered by LazyingArt}")
    tex_lines.append(r"\end{center}")
    tex_lines.append(r"\tableofcontents")
    tex_lines.append(r"\clearpage")
    tex_lines.append(r"\pagestyle{fancy}")

    for cid in chunk_ids:
        path = CHUNKS_DIR / f"{cid}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        section = data.get("section", {})
        sec_id = section.get("id", cid)
        tex_lines.append(r"\section{" + tex_escape(sec_id) + "}")

        for para in data.get("paragraphs", []):
            for unit in para.get("units", []):
                tex_lines.append(render_unit(unit, direction))
                tex_lines.append(r"\vspace{0.3em}")
            tex_lines.append(r"\vspace{0.5em}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)


def write_style_tex(out_dir: Path) -> None:
    """Write the style.tex with grammar colors and geometry."""
    style = r"""
\usepackage{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{hyperref}

\geometry{paperwidth=105mm,paperheight=148mm,inner=8mm,outer=8mm,top=9mm,bottom=11mm,footskip=7mm}

\setmainfont{TeX Gyre Pagella}
\setCJKmainfont{Noto Serif CJK JP}
\newCJKfontfamily\zhfont{Noto Serif CJK SC}
\newCJKfontfamily\jpfont{Noto Serif CJK JP}

\definecolor{GramSubject}{HTML}{13795B}
\definecolor{GramPredicate}{HTML}{B23A48}
\definecolor{GramObject}{HTML}{286DA8}
\definecolor{GramAttributive}{HTML}{7C58A5}
\definecolor{GramAdverbial}{HTML}{A96523}
\definecolor{GramComplement}{HTML}{1D7F91}
\colorlet{GramTopic}{GramSubject}
\colorlet{GramFunction}{black}

\newcommand{\BlackWhiteMode}{%
  \colorlet{GramSubject}{black}%
  \colorlet{GramPredicate}{black}%
  \colorlet{GramObject}{black}%
  \colorlet{GramAttributive}{black}%
  \colorlet{GramAdverbial}{black}%
  \colorlet{GramComplement}{black}%
  \colorlet{GramTopic}{black}%
  \colorlet{GramFunction}{black}%
  \hypersetup{linkcolor=black,urlcolor=black}%
}

\hypersetup{colorlinks=true,linkcolor=black}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0pt}
\raggedbottom

\titleformat{\section}{\normalfont\normalsize\bfseries\jpfont}{\thesection}{0.5em}{}
\titlespacing*{\section}{0pt}{0.65em}{0.25em}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
\emergencystretch=3em
\linespread{1.05}
\XeTeXlinebreaklocale "ja"
\XeTeXlinebreakskip=0pt plus 0.18em

\newcommand{\RubyFont}{\fontsize{3.6pt}{4pt}\selectfont}
\NewDocumentCommand{\zhcnruby}{m m}{%
  \leavevmode\setbox0=\hbox{#1}\dimen0=\wd0%
  \vbox{\offinterlineskip%
    \hbox to \dimen0{\hss{\RubyFont #2}\hss}\kern0.06ex\box0}}
\NewDocumentCommand{\jpruby}{m m}{%
  \leavevmode\setbox0=\hbox{#1}\dimen0=\wd0%
  \vbox{\offinterlineskip%
    \hbox to \dimen0{\hss{\RubyFont #2}\hss}\kern0.06ex\box0}}

\newcommand{\GramSubject}[1]{{\color{GramSubject}#1}}
\newcommand{\GramPredicate}[1]{{\color{GramPredicate}#1}}
\newcommand{\GramObject}[1]{{\color{GramObject}#1}}
\newcommand{\GramAttributive}[1]{{\color{GramAttributive}#1}}
\newcommand{\GramAdverbial}[1]{{\color{GramAdverbial}#1}}
\newcommand{\GramComplement}[1]{{\color{GramComplement}#1}}
\newcommand{\GramTopic}[1]{{\color{GramTopic}#1}}
\newcommand{\GramFunction}[1]{{\color{GramFunction}#1}}

\NewDocumentCommand{\JpMainLine}{m}{{\large\jpfont #1}\par}
\NewDocumentCommand{\ZhMainLine}{m}{{\large\zhfont #1}\par}
\NewDocumentCommand{\ZhOrigLine}{m}{{\normalsize\zhfont #1}\par}
\NewDocumentCommand{\JaCommentLine}{m}{{\normalsize\jpfont #1}\par}
\NewDocumentCommand{\ZhModernLine}{m}{{\footnotesize\zhfont #1}\par}
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "style.tex").write_text(style, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", choices=["jp_main", "zh_main"], default="zh_main")
    parser.add_argument("--bw", action="store_true", help="Blackwhite mode")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--out-dir", help="Output directory for TeX")
    args = parser.parse_args()

    ids = [f"shiji-chunk-{n:04d}" for n in range(args.start, args.start + args.limit)]

    dir_key = f"{args.direction.replace('_','-')}"
    color_key = "blackwhite" if args.bw else "color"
    out_dir = Path(args.out_dir) if args.out_dir else BUILD_DIR / dir_key / color_key
    out_dir.mkdir(parents=True, exist_ok=True)

    write_style_tex(out_dir)

    tex = produce_tex(ids, args.direction, args.bw)
    tex_path = out_dir / "book.tex"
    tex_path.write_text(tex, encoding="utf-8")
    print(f"Wrote {tex_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
