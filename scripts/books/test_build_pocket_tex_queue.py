#!/usr/bin/env python3
"""Focused tests for structured illustrated PDF completion gates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_pocket_tex_queue as queue


def report(figures: int) -> dict[str, object]:
    return {
        "tex": "build-pocket/test-book/exact/tex/book.tex",
        "text_chars": 20_000,
        "worst_overfull_pt": 0,
        "latex_error_markers": [],
        "figure_inventory": {
            "existing_count": figures,
            "missing_count": 0,
            "sequence_sha256": "same-sequence",
        },
    }


class IllustratedExactTests(unittest.TestCase):
    def test_index_tables_flatten_in_column_order_without_losing_cells(self) -> None:
        source = """# Chapter

| keep | table |
| --- | --- |
| one | two |

## *Index*

| Alpha<br>detail | Beta |
| --- | --- |
| Apple | Book |
"""
        flattened, count = queue.flatten_markdown_tables_after_heading(
            source,
            heading_pattern=r"^## \*Index\*\s*$",
        )
        self.assertEqual(count, 1)
        self.assertIn("| keep | table |", flattened)
        self.assertNotIn("| Alpha", flattened)
        self.assertLess(flattened.index("Alpha detail"), flattened.index("Apple"))
        self.assertLess(flattened.index("Apple"), flattened.index("Beta"))
        self.assertIn("Book", flattened)

    def test_contents_cleanup_preserves_trailing_illustration(self) -> None:
        tex = r"""before
\hypertarget{contents}{%
\chapter{Contents}
\begin{longtable}{ll}
items
\end{longtable}
List of Illustrations
\includegraphics{/tmp/map.jpg}
\textbf{Figure 0.1. Map}
\hypertarget{preface}{%
\chapter{Preface}
after
"""
        cleaned = queue.remove_source_contents_block(tex)
        self.assertNotIn(r"\begin{longtable}", cleaned)
        self.assertIn(r"\includegraphics{/tmp/map.jpg}", cleaned)
        self.assertIn("Figure 0.1. Map", cleaned)
        self.assertIn(r"\chapter{Preface}", cleaned)

    def test_contents_cleanup_accepts_introduction_boundary(self) -> None:
        tex = r"""before
\hypertarget{contents}{%
\subsubsection{Contents}
\begin{longtable}{lllll}
duplicate printed contents
\end{longtable}
Index 94
\hypertarget{introduction}{%
\subsection{Introduction}
body
"""
        cleaned = queue.remove_source_contents_block(tex)
        self.assertNotIn("duplicate printed contents", cleaned)
        self.assertIn(r"\subsection{Introduction}", cleaned)
        self.assertIn("body", cleaned)

    def test_queue_task_defaults_are_applied_without_overriding_task_values(self) -> None:
        tasks = queue.iter_tasks(
            {
                "task_defaults": {"markdown_reader": "commonmark_x", "workers": 1},
                "tasks": [{"book_id": "one"}, {"book_id": "two", "workers": 2}],
            },
            None,
        )
        self.assertEqual(tasks[0]["markdown_reader"], "commonmark_x")
        self.assertEqual(tasks[0]["workers"], 1)
        self.assertEqual(tasks[1]["workers"], 2)

    def test_illustrated_profile_requires_configured_figure_count_without_math(self) -> None:
        structure = {
            "source": {
                "pages": 100,
                "text_chars": 18_000,
                "embedded_images": 12,
            },
            "generated": {
                "text_chars": 20_000,
                "includegraphics_count": 4,
                "display_math_count": 0,
                "inline_math_count": 0,
                "has_toc": True,
            },
        }
        task = {
            "validation_profile": "illustrated_exact",
            "minimum_generated_figure_count": 5,
            "minimum_source_text_coverage_ratio": 0.5,
        }
        with mock.patch.object(queue, "generated_structure_report", return_value=structure):
            issues, _ = queue.completion_issues(task, Path("source.pdf"), report(4), report(4))

        self.assertTrue(any("only 4 figures" in issue for issue in issues))
        self.assertFalse(any("math blocks" in issue for issue in issues))

    def test_required_source_evidenced_figure_hash_must_reach_both_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_dir = root / "build-pocket/test-book"
            required = task_dir / "review/source-figures/map.jpg"
            required.parent.mkdir(parents=True)
            required.write_bytes(b"required-map")
            digest = queue.sha256_file(required)
            structure = {
                "source": {"pages": 10, "text_chars": 10_000, "embedded_images": 1},
                "generated": {
                    "text_chars": 10_000,
                    "includegraphics_count": 1,
                    "display_math_count": 0,
                    "inline_math_count": 0,
                    "has_toc": True,
                },
            }
            exact = report(1)
            pocket = report(1)
            exact["figure_inventory"]["figures"] = [{"sha256": digest}]
            pocket["figure_inventory"]["figures"] = [{"sha256": "wrong"}]
            task = {
                "validation_profile": "illustrated_exact",
                "required_generated_figure_files": ["review/source-figures/map.jpg"],
            }
            with (
                mock.patch.object(queue, "ROOT", root),
                mock.patch.object(queue, "generated_structure_report", return_value=structure),
            ):
                issues, _ = queue.completion_issues(task, Path("source.pdf"), exact, pocket)
        self.assertFalse(any("exact TeX omits" in issue for issue in issues))
        self.assertTrue(any("pocket TeX omits" in issue for issue in issues))

    def test_prepared_markdown_is_resolved_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = root / "reviewed/book.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("Reviewed text. " * 80, encoding="utf-8")
            with mock.patch.object(queue, "ROOT", root):
                resolved = queue.resolve_prepared_markdown(
                    {"prepared_markdown": "reviewed/book.md"}
                )
        self.assertEqual(resolved, markdown.resolve())

    def test_markdown_review_rebases_relative_figure_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source/book.md"
            image = root / "source/assets/figure.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"figure")
            source.write_text("# Book\n\n![](assets/figure.jpg)\n" + "Text. " * 100, encoding="utf-8")
            task_dir = root / "build-pocket/book"
            with mock.patch.object(queue, "ROOT", root):
                reviewed = queue.apply_task_markdown_fixes(
                    source,
                    {"validation_profile": "illustrated_exact"},
                    task_dir,
                )
            self.assertIn(image.resolve().as_posix(), reviewed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
