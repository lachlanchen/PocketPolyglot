#!/usr/bin/env python3
"""Compile English-only exact textbook pocket PDFs from Mathpix TeX output.

This runner intentionally avoids the multilingual interlinear pipeline. It
uses Mathpix whole-PDF TeX archives when available and can submit/download the
archive when requested. The resulting PDF is a pocket-size English TeX draft
that preserves formulas, tables, and figures for page-by-page review.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BEGIN_DOCUMENT_RE = re.compile(r"\\begin\{document\}")
END_DOCUMENT_RE = re.compile(r"\\end\{document\}")
MATHPIX_TITLE_RE = re.compile(
    r"\\title\{.*?\\date\{\}\s*",
    re.DOTALL,
)
INCLUDEGRAPHICS_RE = re.compile(r"(\\includegraphics(?:\[[^\]]*\])?\{)([^}]+)(\})")
IMAGE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
ALIGN_TRAILING_DISPLAY_RE = re.compile(
    r"(\\end\{align\*\})[ \t]*"
    r"([,;]?\s*\\(?:quad|left|boldsymbol|frac|overline|begin\{(?:array|matrix|pmatrix|bmatrix)\})[\s\S]*?)"
    r"(\n\s*\n)"
)
DISPLAY_NESTED_ALIGN_RE = re.compile(
    r"\\\[\s*([^\n]*?)\\begin\{align\*\}([\s\S]*?)\\end\{align\*\}\s*"
    r"\\\[(.*?)\\\]\s*\\\]",
    re.DOTALL,
)
DISPLAY_ALIGN_TRAILING_INLINE_RE = re.compile(
    r"\\\[\s*([^\n]*?)\\begin\{align\*\}([\s\S]*?)\\end\{align\*\}\s*"
    r"(\\left[\s\S]*?)\\\]",
    re.DOTALL,
)
INLINE_MATH_RE = re.compile(r"\\\((.*?)\\\)", re.DOTALL)
DISPLAY_MATH_RE = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
TABULAR_RE = re.compile(r"(\\begin\{tabular\})\s*(\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\})([\s\S]*?)(\\end\{tabular\})")


def run(cmd: list[str], *, check: bool = True, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plan_for(book_id: str) -> dict[str, Any]:
    path = ROOT / "books" / book_id / "book-plan.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return load_json(path)


def job_dir(book_id: str) -> Path:
    return ROOT / "books" / book_id / "work/exact-tex/mathpix-pdf"


def job_file(book_id: str) -> Path:
    return job_dir(book_id) / "job.json"


def find_mathpix_tex(book_id: str) -> Path | None:
    base = job_dir(book_id)
    texzip_root = base / "texzip"
    candidates = [
        path
        for path in sorted(texzip_root.glob("**/*.tex"))
        if path.is_file()
    ]
    if candidates:
        return candidates[0]

    downloads = base / "downloads"
    for archive in sorted(downloads.glob("*.tex.zip")):
        extract_dir = texzip_root / archive.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)
        candidates = sorted(extract_dir.glob("**/*.tex"))
        if candidates:
            return candidates[0]
    return None


def ensure_mathpix_tex(book_id: str, *, submit: bool, wait: bool, download: bool, interval: int) -> Path:
    existing = find_mathpix_tex(book_id)
    if existing:
        return existing
    if not submit:
        raise FileNotFoundError(
            f"No Mathpix TeX archive found for {book_id}. "
            "Run with --submit-missing to submit the whole-PDF OCR job."
        )

    helper = ROOT / "scripts/interlinear/textbook_mathpix_pdf_job.py"
    if job_file(book_id).exists():
        print(f"[{book_id}] reusing existing Mathpix job file", flush=True)
    else:
        print(f"[{book_id}] submitting Mathpix whole-PDF job", flush=True)
        print(run(["python", str(helper), "submit", "--book-id", book_id]).stdout, flush=True)
    if wait:
        print(f"[{book_id}] waiting for Mathpix conversions", flush=True)
        print(
            run(
                [
                    "python",
                    str(helper),
                    "wait",
                    "--book-id",
                    book_id,
                    "--interval",
                    str(interval),
                ]
            ).stdout,
            flush=True,
        )
    if download:
        print(f"[{book_id}] downloading Mathpix artifacts", flush=True)
        print(run(["python", str(helper), "download", "--book-id", book_id]).stdout, flush=True)
    existing = find_mathpix_tex(book_id)
    if existing:
        return existing
    raise FileNotFoundError(f"Mathpix TeX still missing after submit/download for {book_id}")


def strip_mathpix_document(text: str) -> str:
    begin = BEGIN_DOCUMENT_RE.search(text)
    if begin:
        text = text[begin.end() :]
    end = END_DOCUMENT_RE.search(text)
    if end:
        text = text[: end.start()]
    text = MATHPIX_TITLE_RE.sub("", text)
    text = text.replace("\\maketitle", "")
    text = text.replace("\\pagebreak", "\\clearpage")
    text = text.replace("\\graphicspath{ {./images/} }", "")
    return text.strip() + "\n"


def resolve_image_paths(body: str, image_dir: Path) -> str:
    """Rewrite extensionless Mathpix image names to repo-relative files."""
    image_lookup: dict[str, Path] = {}
    if image_dir.exists():
        for path in image_dir.iterdir():
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                image_lookup[path.stem] = path
                image_lookup[path.name] = path

    def replace(match: re.Match[str]) -> str:
        prefix, raw_name, suffix = match.groups()
        name = raw_name.strip()
        if name.startswith("/") or name.startswith("build/") or name.startswith("./"):
            return match.group(0)
        path = image_lookup.get(name)
        if path is None:
            path = image_lookup.get(Path(name).stem)
        if path is None:
            return match.group(0)
        return prefix + str(path.relative_to(ROOT)) + suffix

    return INCLUDEGRAPHICS_RE.sub(replace, body)


def normalize_includegraphics_options(body: str) -> str:
    """Constrain all OCR-extracted figures for pocket-page output."""

    def replace(match: re.Match[str]) -> str:
        _, raw_name, _ = match.groups()
        options = r"max width=.94\linewidth,max totalheight=.62\textheight,keepaspectratio,center"
        return rf"\noindent\includegraphics[{options}]{{{raw_name.strip()}}}"

    body = INCLUDEGRAPHICS_RE.sub(replace, body)
    return re.sub(r"(\\includegraphics\[[^\]]+\]\{[^}]+\})\\\\", r"\1\\par\\smallskip", body)


def count_simple_columns(spec: str) -> int:
    spec = re.sub(r"\|", "", spec)
    spec = re.sub(r"@\{[^{}]*\}", "", spec)
    spec = re.sub(r">\{[^{}]*\}|<\{[^{}]*\}", "", spec)
    spec = re.sub(r"[pmb]\{[^{}]*\}", "c", spec)
    return len(re.findall(r"[lcrX]", spec))


def count_row_columns(row: str) -> int:
    row = row.strip()
    if not row or row.startswith(r"\hline") or row.startswith(r"\cline"):
        return 0
    multicol = re.match(r"\\multicolumn\{(\d+)\}", row)
    if multicol:
        return int(multicol.group(1)) + row[multicol.end() :].count("&")
    return len(re.findall(r"(?<!\\)&", row)) + 1


def widen_simple_tabular_specs(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        begin, spec_group, spec, content, end = match.groups()
        declared = count_simple_columns(spec)
        rows = re.split(r"(?<!\\)\\\\", content)
        actual = max((count_row_columns(row) for row in rows), default=0)
        if actual <= declared or actual <= 0:
            return match.group(0)
        tokens = re.findall(r"[lcrX]", re.sub(r"[pmb]\{[^{}]*\}", "c", spec))
        first = tokens[0] if tokens else "l"
        fixed_spec = "| " + " ".join([first] + ["c"] * (actual - 1)) + " |"
        return f"{begin}{{{fixed_spec}}}{content}{end}"

    return TABULAR_RE.sub(replace, body)


def balance_math_delimiters(content: str) -> str:
    """Downgrade unmatched stretch delimiters inside one math fragment.

    Mathpix sometimes emits a valid ``\left(...\right.`` pair for the first
    term of a tuple and then a later ``\right)`` for the tuple close. XeLaTeX
    rejects the later delimiter because the original ``\left`` was already
    closed. A literal delimiter is safer than a fatal compile error; source
    review tasks still catch the page for semantic cleanup.
    """
    left_count = len(re.findall(r"\\left(?:\\[{}]|[.\[(|{}]|\\[A-Za-z]+)", content))
    right_tokens = list(re.finditer(r"\\right(?:\\[{}]|[.\])|{}]|\\[A-Za-z]+)", content))
    if left_count > len(right_tokens):
        return content + (r"\right." * (left_count - len(right_tokens)))
    surplus = len(right_tokens) - left_count
    if surplus <= 0:
        return content

    replacements = {
        r"\right)": ")",
        r"\right]": "]",
        r"\right|": "|",
        r"\right.": "",
        r"\right\}": r"\}",
        r"\right\{": r"\{",
        r"\right\vert": r"\vert",
        r"\right\rangle": r"\rangle",
        r"\right\langle": r"\langle",
    }
    pieces: list[str] = []
    last = 0
    drop_starts = {match.start() for match in right_tokens[-surplus:]}
    for match in right_tokens:
        pieces.append(content[last : match.start()])
        token = match.group(0)
        if match.start() in drop_starts:
            pieces.append(replacements.get(token, token.replace(r"\right", "")))
        else:
            pieces.append(token)
        last = match.end()
    pieces.append(content[last:])
    return "".join(pieces)


def sanitize_math_fragments(body: str) -> str:
    def replace_inline(match: re.Match[str]) -> str:
        return r"\(" + balance_math_delimiters(match.group(1)) + r"\)"

    def replace_display(match: re.Match[str]) -> str:
        return r"\[" + balance_math_delimiters(match.group(1)) + r"\]"

    body = INLINE_MATH_RE.sub(replace_inline, body)
    return DISPLAY_MATH_RE.sub(replace_display, body)


def sanitize_mathpix_body(body: str) -> str:
    """Fix common Mathpix TeX fragments that are invalid in a book wrapper."""
    body = DISPLAY_ALIGN_TRAILING_INLINE_RE.sub(r"\\begin{align*}\n& \1 \\\\\2\\\\\n& \3\n\\end{align*}", body)
    body = DISPLAY_NESTED_ALIGN_RE.sub(r"\\begin{align*}\n& \1 \\\\\2\\\\\n& \3\n\\end{align*}", body)
    body = ALIGN_TRAILING_DISPLAY_RE.sub(r"\1\n\\[\2\n\\]\3", body)
    body = body.replace(r"\textbackslash left.", "")
    body = re.sub(r"\\section\*\{\s*-\s*", r"\\section*{", body)
    body = normalize_includegraphics_options(body)
    body = sanitize_math_fragments(body)
    body = re.sub(r"\\\[\s*(\\begin\{itemize\})", r"\1", body)
    body = re.sub(r"(\\end\{itemize\})\s*\\\]", r"\1", body)
    body = body.replace(r"\begin{verbatim}", r"\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\scriptsize]")
    body = body.replace(r"\end{verbatim}", r"\end{Verbatim}")
    body = re.sub(
        r"\\begin\{tabular\}(\{[^}]+\})",
        r"\\begin{adjustbox}{max width=\\linewidth}\\begin{tabular}\1",
        body,
    )
    body = body.replace(r"\end{tabular}", r"\end{tabular}\end{adjustbox}")
    body = widen_simple_tabular_specs(body)
    return body


def metadata(plan: dict[str, Any]) -> tuple[str, str]:
    title = plan.get("book_title_en") or plan.get("title_en") or plan.get("book_id", "Textbook")
    author = plan.get("author") or ""
    return str(title), str(author)


def build_source(book_id: str, mathpix_tex: Path) -> Path:
    plan = plan_for(book_id)
    title, author = metadata(plan)
    out_dir = ROOT / "build" / f"{book_id}-exact-pocket" / "english"
    out_dir.mkdir(parents=True, exist_ok=True)

    src_images = mathpix_tex.parent / "images"
    dst_images = out_dir / "images"
    if dst_images.exists():
        shutil.rmtree(dst_images)
    if src_images.exists():
        shutil.copytree(src_images, dst_images)

    body = strip_mathpix_document(mathpix_tex.read_text(encoding="utf-8", errors="replace"))
    body = resolve_image_paths(body, dst_images)
    body = sanitize_mathpix_body(body)
    source = out_dir / "source.tex"
    source.write_text(
        "\n".join(
            [
                f"\\TextbookPdfMeta{{{escape_braces(title)}}}{{{escape_braces(author)}}}{{English exact pocket TeX draft}}",
                "\\TextbookTitlePage",
                f"  {{{escape_braces(title)}}}",
                f"  {{{escape_braces(author)}}}",
                "  {AgInTiFlow curated}",
                "  {https://flow.lazying.art}",
                "  {powered by LazyingArt}",
                "  {English-only exact pocket TeX draft from Mathpix OCR; formulas, tables, and figures are preserved for page-by-page review.}",
                "",
                "\\begingroup",
                "\\footnotesize",
                "\\everydisplay{\\scriptsize}",
                "\\setlength{\\tabcolsep}{2pt}",
                "\\renewcommand{\\arraystretch}{0.92}",
                "\\setlength{\\parindent}{1.1em}",
                "\\setlength{\\parskip}{0pt}",
                f"\\graphicspath{{{{{str(dst_images.relative_to(ROOT))}/}}{{images/}}{{./images/}}}}",
                body,
                "\\endgroup",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return source


def escape_braces(text: str) -> str:
    return text.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


def compile_pdf(book_id: str, source: Path, *, passes: int) -> Path:
    out_dir = source.parent
    job = f"{book_id}-english-pocket"
    wrapper = (
        "\\def\\TextbookPocketSource{"
        + str(source.relative_to(ROOT))
        + "}\\input{tex/textbook-pocket/book.tex}"
    )
    last_output = ""
    for index in range(passes):
        proc = run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-jobname",
                job,
                "-output-directory",
                str(out_dir),
                wrapper,
            ],
            check=False,
        )
        last_output = proc.stdout
        (out_dir / f"compile-pass-{index + 1}.log").write_text(last_output, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"XeLaTeX failed for {book_id}; see {out_dir / f'compile-pass-{index + 1}.log'}")
    pdf = out_dir / f"{job}.pdf"
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    return pdf


def summarize_pdf(pdf: Path) -> dict[str, Any]:
    info = run(["pdfinfo", str(pdf)], check=False).stdout
    pages = None
    for line in info.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split(":", 1)[1].strip())
            break
    log = pdf.with_suffix(".log")
    overfull = 0
    missing = 0
    if log.exists():
        text = log.read_text(encoding="utf-8", errors="replace")
        overfull = text.count("Overfull \\hbox")
        missing = text.count("File `") + text.count("not found")
    return {"pdf": str(pdf.relative_to(ROOT)), "pages": pages, "overfull_hbox_count": overfull, "missing_file_marker_count": missing}


def run_book(book_id: str, args: argparse.Namespace) -> dict[str, Any]:
    mathpix_tex = ensure_mathpix_tex(
        book_id,
        submit=args.submit_missing,
        wait=args.wait,
        download=args.download,
        interval=args.interval,
    )
    print(f"[{book_id}] mathpix_tex={mathpix_tex.relative_to(ROOT)}", flush=True)
    source = build_source(book_id, mathpix_tex)
    print(f"[{book_id}] source={source.relative_to(ROOT)}", flush=True)
    pdf = compile_pdf(book_id, source, passes=args.passes)
    summary = summarize_pdf(pdf)
    write_json(source.parent / "summary.json", summary)
    print(f"[{book_id}] pdf={summary['pdf']} pages={summary['pages']} overfull={summary['overfull_hbox_count']}", flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", action="append", required=True, help="Book id to compile; repeatable.")
    parser.add_argument("--submit-missing", action="store_true", help="Submit Mathpix OCR when TeX output is missing.")
    parser.add_argument("--wait", action="store_true", help="Wait for submitted Mathpix jobs to finish.")
    parser.add_argument("--download", action="store_true", help="Download Mathpix artifacts after wait.")
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()

    summaries = []
    for book_id in args.book_id:
        try:
            summaries.append(run_book(book_id, args))
        except Exception as exc:
            print(f"[{book_id}] failed: {exc}", file=sys.stderr, flush=True)
            return 1
        time.sleep(1)
    print(json.dumps({"compiled": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
