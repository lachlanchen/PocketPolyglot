#!/usr/bin/env python3
"""Compile exact open-source pocket facsimile TeX books from source PDFs.

This is the no-Mathpix path for formula-heavy textbooks. It does not pretend
that generic PDF text extraction can faithfully retype formulas. Instead, it
creates a pocket-size TeX document that includes the original PDF pages as
scaled page art, preserving formulas, tables, figures, and layout exactly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def plan_for(book_id: str) -> dict[str, Any]:
    plan = ROOT / "books" / book_id / "book-plan.json"
    if not plan.exists():
        raise FileNotFoundError(plan)
    return load_json(plan)


def source_pdf(plan: dict[str, Any]) -> Path:
    source = plan.get("source_paths", {}).get("exact_source")
    if not source:
        raise RuntimeError("book-plan.json missing source_paths.exact_source")
    path = ROOT / source
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def pdf_pages(path: Path) -> int | None:
    proc = run(["pdfinfo", str(path)], check=False)
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return None


def normalize_pdf(input_pdf: Path, output_pdf: Path) -> None:
    qpdf = shutil.which("qpdf")
    if qpdf:
        qpdf_out = output_pdf.with_name(output_pdf.stem + "-qpdf.pdf")
        proc = run(
            [
                qpdf,
                "--linearize",
                "--object-streams=generate",
                str(input_pdf),
                str(qpdf_out),
            ],
            check=False,
        )
        (output_pdf.parent / "qpdf-normalize.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
        if proc.returncode == 0 and qpdf_out.exists():
            qpdf_out.replace(output_pdf)
            return

    gs = shutil.which("gs")
    if not gs:
        raise RuntimeError("Ghostscript `gs` or qpdf is required to normalize malformed PDFs")
    proc = run(
        [
            gs,
            "-dBATCH",
            "-dNOPAUSE",
            "-dSAFER",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.5",
            "-dPDFSETTINGS=/prepress",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            f"-sOutputFile={output_pdf}",
            str(input_pdf),
        ],
        check=False,
    )
    (output_pdf.parent / "ghostscript-normalize.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not output_pdf.exists():
        raise RuntimeError(f"Ghostscript normalization failed for {input_pdf}")


def write_source_tex(book_id: str, source_filename: str) -> Path:
    plan = plan_for(book_id)
    out_dir = ROOT / "build" / f"{book_id}-exact-pocket" / "facsimile"
    out_dir.mkdir(parents=True, exist_ok=True)

    title = str(plan.get("book_title_en") or book_id)
    author = str(plan.get("author") or "")
    source_tex = out_dir / "source.tex"
    source_tex.write_text(
        rf"""\documentclass[UTF8,fontset=none,10pt,openany]{{ctexbook}}
\usepackage{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\usepackage{{xcolor}}
\usepackage{{hyperref}}
\usepackage{{pdfpages}}
\usepackage{{fancyhdr}}

\geometry{{
  paperwidth=105mm,
  paperheight=148mm,
  inner=5mm,
  outer=5mm,
  top=6mm,
  bottom=7mm,
  headheight=0pt,
  headsep=0pt,
  footskip=4.5mm
}}

\setmainfont{{TeX Gyre Pagella}}
\setsansfont{{Noto Sans}}
\setmonofont{{TeX Gyre Cursor}}
\setCJKmainfont{{Noto Serif CJK SC}}
\setCJKsansfont{{Noto Sans CJK SC}}
\hypersetup{{
  colorlinks=true,
  linkcolor=black,
  urlcolor=black,
  pdftitle={{{tex_escape(title)}}},
  pdfauthor={{{tex_escape(author)}}},
  pdfsubject={{Pocket-size exact facsimile TeX edition}}
}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyfoot[C]{{\fontsize{{6pt}}{{7pt}}\selectfont\thepage}}
\renewcommand{{\headrulewidth}}{{0pt}}

\begin{{document}}
\frontmatter
\thispagestyle{{empty}}
\vspace*{{0.17\textheight}}
\begin{{center}}
{{\Large {tex_escape(title)}\par}}
\vspace{{0.9em}}
{{\normalsize {tex_escape(author)}\par}}
\vfill
{{\sffamily\fontsize{{6pt}}{{7.5pt}}\selectfont AgInTiFlow curated\quad https://flow.lazying.art\par powered by LazyingArt\par}}
\vspace{{0.8em}}
{{\sffamily\fontsize{{5.6pt}}{{7pt}}\selectfont Open-source exact facsimile pocket TeX edition. Original pages are scaled into pocket format so formulas, tables, and figures remain visually faithful.\par}}
\end{{center}}
\clearpage
\tableofcontents
\clearpage
\mainmatter
\chapter*{{Exact Facsimile}}
\addcontentsline{{toc}}{{chapter}}{{Exact Facsimile}}
\includepdf[
  pages=-,
  width=\textwidth,
  height=\textheight,
  keepaspectratio,
  pagecommand={{\thispagestyle{{plain}}}}
]{{{tex_escape(source_filename)}}}
\end{{document}}
""",
        encoding="utf-8",
    )
    return source_tex


def build_source(book_id: str) -> tuple[Path, Path]:
    plan = plan_for(book_id)
    src = source_pdf(plan)
    out_dir = ROOT / "build" / f"{book_id}-exact-pocket" / "facsimile"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_pdf = out_dir / "source.pdf"
    shutil.copy2(src, local_pdf)
    return out_dir, write_source_tex(book_id, "source.pdf")


def run_xelatex(out_dir: Path, source_tex: Path, jobname: str, *, passes: int) -> int:
    last_return = 0
    for index in range(1, passes + 1):
        proc = run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-jobname",
                jobname,
                str(source_tex.name),
            ],
            cwd=out_dir,
            check=False,
        )
        (out_dir / f"compile-pass-{index}.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
        last_return = proc.returncode
        if proc.returncode != 0:
            break
    return last_return


def compile_book(book_id: str, *, passes: int) -> dict[str, Any]:
    out_dir, source_tex = build_source(book_id)
    jobname = f"{book_id}-english-facsimile-pocket"
    last_return = run_xelatex(out_dir, source_tex, jobname, passes=passes)
    if last_return != 0:
        normalize_pdf(out_dir / "source.pdf", out_dir / "source-normalized.pdf")
        source_tex = write_source_tex(book_id, "source-normalized.pdf")
        last_return = run_xelatex(out_dir, source_tex, jobname, passes=passes)
    pdf = out_dir / f"{jobname}.pdf"
    log = out_dir / f"{jobname}.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    summary = {
        "book_id": book_id,
        "returncode": last_return,
        "source_tex": str(source_tex.relative_to(ROOT)),
        "pdf": str(pdf.relative_to(ROOT)) if pdf.exists() else None,
        "pages": pdf_pages(pdf) if pdf.exists() else None,
        "overfull_hbox_count": log_text.count("Overfull \\hbox"),
        "missing_file_marker_count": log_text.count("not found") + log_text.count("File `"),
        "mode": "open_source_exact_facsimile_no_mathpix",
    }
    write_json(out_dir / "summary.json", summary)
    if last_return != 0 or not pdf.exists():
        raise RuntimeError(f"{book_id} facsimile compile failed; see {out_dir}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True, help="Book id to compile; repeatable.")
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()

    results = []
    for book_id in args.book_id:
        print(f"[{book_id}] compiling open-source facsimile pocket TeX", flush=True)
        summary = compile_book(book_id, passes=args.passes)
        print(
            f"[{book_id}] pdf={summary['pdf']} pages={summary['pages']} "
            f"overfull={summary['overfull_hbox_count']}",
            flush=True,
        )
        results.append(summary)
    print(json.dumps({"compiled": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
