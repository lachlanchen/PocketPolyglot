#!/usr/bin/env python3
"""Build real-TeX exact and pocket PDFs from the build-pocket queue.

This runner is deliberately conservative: a successful book must have a real
TeX body and PDFs compiled from that body. If local extraction cannot produce a
credible TeX path, the book is marked blocked with evidence instead of emitting
an image-only placeholder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "build-pocket/tasks/source-queue-2026-07-12.json"
DEFAULT_HEADER = ROOT / "build-pocket/_common/pandoc-pocket-header.tex"

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MARKDOWN_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)\n]+)(\))")
OVERFULL_RE = re.compile(r"Overfull \\hbox \(([-0-9.]+)pt too wide\)")
LATEX_ERROR_RE = re.compile(r"^! |Fatal error|Emergency stop|Undefined control sequence", re.M)
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?(\{[^}]+\})")
LONGTABLE_SPEC_RE = re.compile(r"(\\begin\{longtable\}(?:\[[^\]]*\])?\{)([^{}]*(?:@\{\}[^{}]*)?)(\})")
SERVER_UNSAFE_FILENAME_CHARS = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "／",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)


def log(message: str) -> None:
    print(message, flush=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_name(name: str) -> str:
    safe = name.translate(SERVER_UNSAFE_FILENAME_CHARS)
    safe = re.sub(r"[\x00-\x1f\x7f]", "", safe)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe.rstrip(" .") or "untitled"


def run_stream(cmd: list[str], *, cwd: Path = ROOT, log_file: Path | None = None) -> int:
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / '.local/bin'}:{env.get('PATH', '')}"
    with subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    ) as proc:
        handle = log_file.open("a", encoding="utf-8") if log_file else None
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if handle:
                    handle.write(line)
        finally:
            if handle:
                handle.close()
        return proc.wait()


def run_capture(cmd: list[str], *, cwd: Path = ROOT, check: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / '.local/bin'}:{env.get('PATH', '')}"
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout)
    return result


def ensure_header() -> Path:
    DEFAULT_HEADER.parent.mkdir(parents=True, exist_ok=True)
    header = (
        r"""
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{graphicx}
\usepackage[export]{adjustbox}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{float}
\usepackage{caption}
\usepackage{needspace}
\setmainfont{TeX Gyre Pagella}
\setsansfont{TeX Gyre Heros}
\setmonofont{DejaVu Sans Mono}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{}
\setlength{\parindent}{1.2em}
\setlength{\parskip}{0.22em}
\emergencystretch=3em
\sloppy
\pagestyle{plain}
\captionsetup{font=small,labelfont=bf}
\makeatletter
\def\maxwidth{\ifdim\Gin@nat@width>\linewidth\linewidth\else\Gin@nat@width\fi}
\def\maxheight{\ifdim\Gin@nat@height>.72\textheight .72\textheight\else\Gin@nat@height\fi}
\makeatother
\setkeys{Gin}{width=\maxwidth,height=\maxheight,keepaspectratio}
""".strip()
        + "\n"
    )
    if not DEFAULT_HEADER.exists() or DEFAULT_HEADER.read_text(encoding="utf-8", errors="replace") != header:
        DEFAULT_HEADER.write_text(header, encoding="utf-8")
    return DEFAULT_HEADER


def clean_text(text: str) -> str:
    return CONTROL_RE.sub("", text).replace("\ufeff", "")


def remove_text_backslash_artifacts(text: str) -> str:
    r"""Repair OCR backslashes inside ordinary words.

    Local PDF extraction sometimes turns a letter into a stray backslash inside a
    word, for example ``sla\es``. That must not become a TeX command. The rule is
    deliberately narrow so real commands such as ``\alpha`` and ``\section`` are
    left alone.
    """

    return re.sub(r"(?<=[A-Za-z])\\(?=[A-Za-z])", "", text)


def normalize_longtable_spec(spec: str) -> str:
    """Convert unwrapped Pandoc table columns to paragraph columns.

    EPUB/PDF-derived tables often arrive as ``llll`` columns. That preserves
    semantics but cannot wrap on a pocket page. Convert simple column specs to
    equal-width paragraph columns while preserving outer ``@{}`` suppressors.
    """

    body = spec.replace("@{}", "")
    cols = re.findall(r"[lcrX]", body)
    if len(cols) < 2:
        return spec
    width = max(0.10, min(0.44, 0.92 / len(cols)))
    wrapped = "".join([rf"p{{{width:.3f}\linewidth}}" for _ in cols])
    prefix = "@{}" if spec.startswith("@{}") else ""
    suffix = "@{}" if spec.endswith("@{}") else ""
    return prefix + wrapped + suffix


def postprocess_tex(tex_path: Path, *, layout: str) -> None:
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    text = clean_text(text)
    text = INCLUDEGRAPHICS_RE.sub(
        r"\\includegraphics[max width=.94\\linewidth,max totalheight=.70\\textheight,keepaspectratio]\1",
        text,
    )
    text = LONGTABLE_SPEC_RE.sub(
        lambda match: match.group(1) + normalize_longtable_spec(match.group(2)) + match.group(3),
        text,
    )
    if layout == "pocket":
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\footnotesize\setlength{\tabcolsep}{2pt}\begin{longtable}",
        )
    else:
        text = text.replace(
            r"\begin{longtable}",
            r"\begingroup\small\setlength{\tabcolsep}{3pt}\begin{longtable}",
        )
    text = text.replace(r"\end{longtable}", r"\end{longtable}\endgroup")
    tex_path.write_text(text, encoding="utf-8")


def rewrite_markdown_image_paths(markdown: str, base: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix, raw, suffix = match.groups()
        target = raw.strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("/"):
            return match.group(0)
        path = (base / target).resolve()
        return f"{prefix}{path}{suffix}"

    return MARKDOWN_IMAGE_RE.sub(repl, markdown)


def marker_pdf_to_markdown(source: Path, task_dir: Path, *, force: bool) -> Path:
    marker_root = task_dir / "work/marker"
    marker_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(marker_root.glob("**/*.md"))
    if existing and not force:
        return existing[0]

    if shutil.which("marker_single", path=f"{Path.home() / '.local/bin'}:{os.environ.get('PATH', '')}") is None:
        raise RuntimeError("marker_single is not available; cannot run local PDF-to-TeX extraction")

    log_file = task_dir / "review/marker.log"
    if log_file.exists():
        log_file.unlink()
    cmd = [
        "marker_single",
        str(source),
        "--output_dir",
        str(marker_root),
        "--output_format",
        "markdown",
        "--disable_multiprocessing",
    ]
    code = run_stream(cmd, log_file=log_file)
    if code != 0:
        raise RuntimeError(f"marker_single failed with exit code {code}; see {log_file}")

    candidates = sorted(marker_root.glob("**/*.md"), key=lambda path: path.stat().st_size, reverse=True)
    if not candidates:
        raise RuntimeError(f"marker_single produced no Markdown under {marker_root}")
    raw_md = candidates[0]
    text = clean_text(raw_md.read_text(encoding="utf-8", errors="replace"))
    text = rewrite_markdown_image_paths(text, raw_md.parent)
    prepared = task_dir / "review/source-from-marker.md"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(text, encoding="utf-8")
    if len(re.sub(r"\s+", "", text)) < 500:
        raise RuntimeError(f"marker output too short to trust: {prepared}")
    return prepared


def pandoc_layout_args(layout: str) -> list[str]:
    common = [
        "-V",
        "documentclass=book",
        "-V",
        "classoption=oneside",
        "-V",
        "colorlinks=true",
        "-V",
        "linkcolor=blue",
        "-V",
        "urlcolor=blue",
    ]
    if layout == "exact":
        return common + [
            "-V",
            "fontsize=10pt",
            "-V",
            "geometry:paperwidth=148mm",
            "-V",
            "geometry:paperheight=210mm",
            "-V",
            "geometry:inner=14mm",
            "-V",
            "geometry:outer=12mm",
            "-V",
            "geometry:top=14mm",
            "-V",
            "geometry:bottom=16mm",
            "-V",
            "linestretch=1.08",
        ]
    if layout == "pocket":
        return common + [
            "-V",
            "fontsize=10pt",
            "-V",
            "geometry:paperwidth=105mm",
            "-V",
            "geometry:paperheight=148mm",
            "-V",
            "geometry:inner=6.5mm",
            "-V",
            "geometry:outer=5.5mm",
            "-V",
            "geometry:top=8mm",
            "-V",
            "geometry:bottom=9mm",
            "-V",
            "linestretch=1.12",
        ]
    raise ValueError(layout)


def pandoc_to_tex(
    source: Path,
    tex_path: Path,
    *,
    title: str,
    author: str,
    layout: str,
    source_format: str,
) -> None:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    header = ensure_header()
    figures_dir = tex_path.parents[1] / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        str(source),
        "--standalone",
        "--toc",
        "--top-level-division=chapter",
        "--wrap=preserve",
        "--metadata",
        f"title={title}",
        "--metadata",
        f"author={author}",
        "--include-in-header",
        str(header),
        "--extract-media",
        str(figures_dir),
        "--resource-path",
        f"{source.parent}:{ROOT}",
        "-o",
        str(tex_path),
    ]
    if source_format == "markdown":
        cmd[1:1] = ["--from", "markdown+tex_math_dollars+tex_math_single_backslash+raw_tex"]
    cmd.extend(pandoc_layout_args(layout))
    result = run_capture(cmd)
    if result.returncode:
        (tex_path.parent / "pandoc.log").write_text(result.stdout, encoding="utf-8")
        raise RuntimeError(f"pandoc failed for {source}; see {tex_path.parent / 'pandoc.log'}")
    postprocess_tex(tex_path, layout=layout)


def repair_undefined_word_command(tex_path: Path, log_file: Path) -> bool:
    """Repair one OCR-created backslash-in-word after a concrete XeLaTeX error."""

    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    if "Undefined control sequence" not in log_text:
        return False
    matches = list(re.finditer(r"\nl\.(\d+)\s", log_text))
    if matches:
        line_no = int(matches[-1].group(1))
    else:
        path_pattern = re.escape(str(tex_path))
        matches = list(re.finditer(rf"{path_pattern}:(\d+): Undefined control sequence\.", log_text))
        if not matches:
            return False
        line_no = int(matches[-1].group(1))
    lines = tex_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if line_no < 1 or line_no > len(lines):
        return False
    old = lines[line_no - 1]
    new = remove_text_backslash_artifacts(old)
    if new == old:
        return False
    lines[line_no - 1] = new
    tex_path.write_text("".join(lines), encoding="utf-8")
    display_path = tex_path.resolve()
    try:
        display_path = display_path.relative_to(ROOT)
    except ValueError:
        pass
    log(f"[repair] {display_path}:{line_no} removed OCR backslash artifact")
    return True


def compile_tex(tex_path: Path, out_pdf: Path) -> dict[str, Any]:
    build_dir = tex_path.parent / "latex-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    log_file = build_dir / "xelatex.log"
    if log_file.exists():
        log_file.unlink()
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-output-directory",
        str(build_dir),
        str(tex_path),
    ]
    passes = 0
    attempts = 0
    while passes < 2 and attempts < 6:
        attempts += 1
        code = run_stream(cmd, log_file=log_file)
        if code != 0:
            if repair_undefined_word_command(tex_path, log_file):
                continue
            raise RuntimeError(f"xelatex failed for {tex_path}; see {log_file}")
        passes += 1
    if passes < 2:
        raise RuntimeError(f"xelatex did not finish two clean passes for {tex_path}; see {log_file}")
    produced = build_dir / f"{tex_path.stem}.pdf"
    if not produced.exists():
        raise RuntimeError(f"xelatex did not produce {produced}")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(produced, out_pdf)
    return validate_pdf(out_pdf, build_dir / f"{tex_path.stem}.log", tex_path)


def pdf_info(pdf: Path) -> dict[str, str]:
    result = run_capture(["pdfinfo", str(pdf)])
    info: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return info


def pdf_text_chars(pdf: Path) -> int:
    result = run_capture(["pdftotext", "-layout", str(pdf), "-"])
    return len(re.sub(r"\s+", "", result.stdout))


def validate_pdf(pdf: Path, log_path: Path, tex_path: Path) -> dict[str, Any]:
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    overfull = [float(match.group(1)) for match in OVERFULL_RE.finditer(log_text)]
    tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
    return {
        "pdf": str(pdf.relative_to(ROOT)),
        "pdfinfo": pdf_info(pdf),
        "text_chars": pdf_text_chars(pdf),
        "tex": str(tex_path.relative_to(ROOT)),
        "includegraphics_count": tex_text.count("\\includegraphics"),
        "overfull_count": len(overfull),
        "worst_overfull_pt": max(overfull) if overfull else 0,
        "latex_error_markers": LATEX_ERROR_RE.findall(log_text)[:20],
    }


def classify_source(source: Path) -> str:
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    if suffix in {".mobi", ".azw3"}:
        return suffix[1:]
    return "unknown"


def build_one(task: dict[str, Any], *, force: bool, sync: bool, share_root: Path) -> dict[str, Any]:
    book_id = task["book_id"]
    task_dir = ROOT / "build-pocket" / book_id
    review_dir = task_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    status_path = review_dir / "status.json"
    if status_path.exists() and not force:
        prior = read_json(status_path)
        if prior.get("status") == "complete":
            log(f"[skip] {book_id} already complete")
            return prior

    source = (ROOT / task["source"]).resolve()
    title = task.get("title") or book_id
    author = task.get("author") or ""
    source_kind = classify_source(source)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    log(f"[start] {book_id} ({source_kind})")

    try:
        if not source.exists():
            raise FileNotFoundError(source)
        if source_kind == "pdf":
            body_source = marker_pdf_to_markdown(source, task_dir, force=force)
            pandoc_format = "markdown"
        elif source_kind == "epub":
            body_source = source
            pandoc_format = "epub"
        elif source_kind in {"mobi", "azw3"}:
            raise RuntimeError(
                f"{source_kind} requires a real ebook-to-TeX converter; calibre is not installed in this environment"
            )
        else:
            raise RuntimeError(f"Unsupported source format: {source.suffix}")

        exact_tex = task_dir / "exact/tex/book.tex"
        pocket_tex = task_dir / "pocket-large-font/tex/book.tex"
        pandoc_to_tex(body_source, exact_tex, title=title, author=author, layout="exact", source_format=pandoc_format)
        pandoc_to_tex(
            body_source,
            pocket_tex,
            title=title,
            author=author,
            layout="pocket",
            source_format=pandoc_format,
        )
        exact_report = compile_tex(exact_tex, task_dir / "exact/book.pdf")
        pocket_report = compile_tex(pocket_tex, task_dir / "pocket-large-font/book.pdf")

        synced_to = ""
        if sync:
            share_root.mkdir(parents=True, exist_ok=True)
            filename = safe_name(f"{title} - pocket large font.pdf")
            dest = share_root / filename
            shutil.copy2(task_dir / "pocket-large-font/book.pdf", dest)
            synced_to = str(dest)

        status = {
            "book_id": book_id,
            "status": "complete",
            "source": str(source.relative_to(ROOT)),
            "source_kind": source_kind,
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "exact": exact_report,
            "pocket": pocket_report,
            "synced_to": synced_to,
            "policy": "real TeX body only; no page-image-only output",
        }
    except Exception as exc:
        status = {
            "book_id": book_id,
            "status": "blocked",
            "source": str(source.relative_to(ROOT)) if source.exists() else str(source),
            "source_kind": source_kind,
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "reason": str(exc),
            "policy": "blocked instead of producing page-image-only output",
        }
        log(f"[blocked] {book_id}: {exc}")

    write_json(status_path, status)
    return status


def iter_tasks(queue: dict[str, Any], book_ids: set[str] | None) -> list[dict[str, Any]]:
    tasks = list(queue.get("tasks", []))
    if book_ids:
        tasks = [task for task in tasks if task.get("book_id") in book_ids]
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--continue-on-blocked", action="store_true")
    parser.add_argument("--share-root", type=Path, default=Path("/home/lachlan/Nutstore Files/Share/PocketBooks"))
    args = parser.parse_args()

    queue = read_json(args.queue)
    tasks = iter_tasks(queue, set(args.book_id) if args.book_id else None)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        log("No tasks selected.")
        return 0

    complete = 0
    blocked = 0
    for task in tasks:
        status = build_one(task, force=args.force, sync=args.sync, share_root=args.share_root)
        if status.get("status") == "complete":
            complete += 1
        else:
            blocked += 1
            if not args.continue_on_blocked:
                break

    summary = {
        "queue": str(args.queue),
        "selected": len(tasks),
        "complete": complete,
        "blocked": blocked,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    summary_path = ROOT / "build-pocket/last-run-summary.json"
    write_json(summary_path, summary)
    log(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if blocked == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
