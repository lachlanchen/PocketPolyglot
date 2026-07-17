#!/usr/bin/env python3
"""Focused regression checks for the resumable pocket-polish pipeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_pocket_polish_worker import (
    canonicalize_writer_result,
    load_cached_segment,
    load_pending_review_segments,
    migrate_legacy_cached_output,
    remove_surplus_protected_tokens,
    sanitize_reviewer_corrections,
    salvage_reviewed_chunk_segments,
    save_cached_segment,
)
from assemble_build_pocket_polished import (
    demote_secondary_captions,
    fit_short_simple_longtables,
    fit_short_complex_longtables,
    fuse_english_main_japanese_secondary,
    normalize_unwrapped_math_fragments,
    pocket_layout,
    remove_legacy_full_page_cover,
    restore_secondary_list_scaffold,
    wrap_long_simple_longtables,
    restore_split_optional_linebreaks,
    split_shared_environment_scaffold,
)
from build_pocket_tex_queue import (
    inject_cover_page,
    wrap_wide_display_math,
    wrap_wide_inline_math,
    wrap_wide_math_environments,
)
from ensure_textless_pocket_polished_cover import cover_sandbox, recover_generated_cover
from pocket_polished_common import (
    apply_exact_paragraph_drops,
    apply_exact_text_replacements,
    chunk_subset,
    command_signature,
    machine_review_observations,
    normalize_page_boundary_artifacts,
    normalize_split_prose_paragraphs,
    numeric_signature,
    numeric_signature_matches,
    sha256_text,
    split_tex_segments,
    structural_command_signature,
    table_signature,
    validate_segment_output,
    validate_tex_environment_balance,
)


def source_segment(segment_id: str, source_tex: str) -> dict:
    return {
        "segment_id": segment_id,
        "kind": "text",
        "source_sha256": sha256_text(source_tex),
        "source_tex": source_tex,
        "protected": [],
        "command_signature": command_signature(source_tex),
        "structural_command_signature": structural_command_signature(source_tex),
        "numeric_signature": numeric_signature(source_tex),
        "table_signature": table_signature(source_tex),
    }


class PocketPolishPipelineTest(unittest.TestCase):
    def test_source_environment_validation_rejects_crossed_closures(self):
        with self.assertRaisesRegex(
            ValueError,
            "closing adjustbox while Verbatim is open",
        ):
            validate_tex_environment_balance(
                r"\\begin{Verbatim}D\\begin{tabular}{cc}x&y\\end{tabular}"
                r"\\end{adjustbox}\\end{Verbatim}"
            )

    def test_source_environment_validation_accepts_nested_table(self):
        validate_tex_environment_balance(
            r"\\begin{center}\\begin{adjustbox}{max width=\\linewidth}"
            r"\\begin{tabular}{cc}x&y\\end{tabular}"
            r"\\end{adjustbox}\\end{center}"
        )

    def test_center_wrapped_nested_table_is_one_atomic_segment(self):
        from pocket_polished_common import split_tex_segments

        tex = r"\begin{document}\begin{center}\begin{adjustbox}{max width=\linewidth}\begin{tabular}{lll}\multirow{2}{*}{A} & B & C \\\\ \multicolumn{3}{l}{text}\end{tabular}\end{adjustbox}\end{center}\end{document}"
        segments = split_tex_segments(tex, "nested", validation_profile="technical_exact")
        body = [row for row in segments if "multicolumn" in row["source_tex"]]
        self.assertEqual(len(body), 1)
        self.assertIn(r"\begin{center}", body[0]["source_tex"])
        self.assertIn(r"\end{center}", body[0]["source_tex"])

    def test_notation_only_source_excludes_prose_labels(self):
        from pocket_polished_common import source_is_notation_only

        self.assertTrue(source_is_notation_only(r"@@PROTECTED_0001@@ (2) @@PROTECTED_0002@@"))
        self.assertTrue(source_is_notation_only(r"\begin{Verbatim}@@PROTECTED_0001@@\end{Verbatim}"))
        self.assertTrue(
            source_is_notation_only(
                r"\begin{Verbatim}[breaklines=true]\(\mathrm{EU}_{\text{left}}=4\)\end{Verbatim}"
            )
        )
        self.assertTrue(
            source_is_notation_only(
                r"\(\mathrm{EU}_{\text{up}}=\mathrm{EU}_{\text{down}}\) (2) \(7\sigma=3\)"
            )
        )
        self.assertTrue(
            source_is_notation_only(
                r"\graphicspath{{build/book/exact/images/}{build/book/work/images/}}"
                "\n"
                r"\captionsetup{singlelinecheck=false}"
                "\n"
                r"\begin{center}\noindent"
                r"\includegraphics[max width=.96\linewidth]{build/book/work/images/page-001.jpg}"
                r"\end{center}"
            )
        )
        self.assertFalse(source_is_notation_only(r"Result: @@PROTECTED_0001@@"))

    def test_notation_only_source_does_not_require_japanese_script(self):
        source = source_segment(
            "book-notation",
            r"\(\mathrm{EU}_{\text{up}}=\mathrm{EU}_{\text{down}}\) (2) \(7\sigma_{\text{left}}=3\)",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-notation: Japanese output contains no Japanese script",
            errors,
        )
        self.assertNotIn("book-notation: Japanese prose contains no kana", errors)

    def test_chord_progression_does_not_require_artificial_japanese_prose(self):
        source = source_segment(
            "book-chords",
            "Em7 Cmaj7 Am7 Bm7 Em7 i7 VImaj7 iv7 v7 i7",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-chords: Japanese output contains no Japanese script",
            errors,
        )

    def test_figure_chord_chart_accepts_kanji_only_figure_label(self):
        source = source_segment(
            "book-chord-figure",
            "Fig. 5 G7 Am7 Bm7b5 Cmaj7 Dm7 Em7 Fmaj7 Am7",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": "図5 G7 Am7 Bm7b5 Cmaj7 Dm7 Em7 Fmaj7 Am7",
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-chord-figure: Japanese prose contains no kana",
            errors,
        )

    def test_protected_roman_chord_progression_is_not_treated_as_prose(self):
        source = source_segment(
            "book-protected-chords",
            "i(maj7)-ii7@@PROTECTED_0001@@-@@PROTECTED_0002@@IIImaj7"
            "@@PROTECTED_0003@@-iv7-V7-@@PROTECTED_0004@@VImaj7-vii°7",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-protected-chords: Japanese output contains no Japanese script",
            errors,
        )

    def test_chord_table_structure_is_not_treated_as_prose(self):
        source = source_segment(
            "book-chord-table",
            "\\begin{longtable}[]{@{}llllllll@{}}\n"
            "i & ii° & @@PROTECTED_0001@@III & iv & v & ♭VI & ♭VII & \\\\\n"
            "Am & B° & C & Dm & Em & F & G & \\\\\n"
            "\\end{longtable}",
        )
        source["kind"] = "table"
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-chord-table: Japanese output contains no Japanese script",
            errors,
        )

    def test_altered_figure_chords_are_not_treated_as_prose(self):
        source = source_segment(
            "book-altered-chords",
            "Fig. 7 i7 iv7 Cm7 Fm7 V7alt VImaj7 G+7 Abmaj7",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-altered-chords: Japanese output contains no Japanese script",
            errors,
        )

    def test_music_prose_still_requires_a_japanese_translation(self):
        source = source_segment(
            "book-chord-prose",
            "The G7 chord creates tension and normally resolves to a C major chord.",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        self.assertIn(
            "book-chord-prose: Japanese output contains no Japanese script",
            validate_segment_output(task, source, output),
        )

    def test_task_specific_furigana_override_handles_rare_proper_name(self):
        rows = [
            {
                "kind": "protected",
                "source_tex": "\\documentclass{book}\n\\begin{document}\n",
            },
            {
                "kind": "text",
                "en_tex": "Yoshisuke Ueda discovered a strange attractor.",
                "ja_tex": "上田睆亮がストレンジ・アトラクターを発見した。",
            },
            {"kind": "protected", "source_tex": "\n\\end{document}\n"},
        ]
        fused, stats = fuse_english_main_japanese_secondary(
            rows,
            furigana_overrides={"上田睆亮": "うえだよしすけ"},
        )
        self.assertIn(r"\JpRuby{上田睆亮}{うえだよしすけ}", fused)
        self.assertNotIn("睆亮", stats.unknown_tokens)

    def test_kanji_only_technical_figure_caption_does_not_require_kana(self):
        source = source_segment(
            "book-figure-caption",
            "\\begin{figure}[h]\\caption{The dispersion relation.}\\end{figure}",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": "\\begin{figure}[h]\\caption{分散関係。}\\end{figure}",
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-figure-caption: Japanese prose contains no kana",
            errors,
        )

    def test_cross_segment_closing_brace_must_preserve_source_delta(self):
        source = source_segment("book-closing-fragment", "}\\end{center}\\end{figure}")
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-closing-fragment: en_tex changed brace balance",
            errors,
        )
        self.assertNotIn(
            "book-closing-fragment: ja_tex changed brace balance",
            errors,
        )

    def test_grounded_repair_may_balance_malformed_source_brace(self):
        source = source_segment(
            "book-malformed-brace",
            r"The actions are \{Yes and No.",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "The actions are Yes and No.",
            "ja_tex": "行動はYesとNoである。",
            "changes": [
                {
                    "before": r"\{Yes",
                    "after": "Yes",
                    "reason": "Remove an unmatched OCR brace.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-malformed-brace: en_tex changed brace balance",
            errors,
        )
        self.assertNotIn(
            "book-malformed-brace: ja_tex changed brace balance",
            errors,
        )

    def setUp(self) -> None:
        self.first = source_segment("book-s000001", "It ended.Then 2.87 million remained.")
        self.second = source_segment("book-s000002", "The value was 1905.")
        self.task = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "source_language": "en",
            "validation_profile": "prose_exact",
            "segment_count": 2,
            "segments": [self.first, self.second],
        }

    def test_cover_sandbox_falls_back_after_failed_probe(self) -> None:
        with patch(
            "ensure_textless_pocket_polished_cover.workspace_sandbox_available",
            return_value=(False, "RTM_NEWADDR denied"),
        ):
            sandbox, reason = cover_sandbox()
        self.assertEqual(sandbox, "danger-full-access")
        self.assertIn("RTM_NEWADDR denied", reason)

    def test_secondary_items_restore_source_list_scaffold(self) -> None:
        source = "\\begin{itemize}\n  \\item First.\n  \\item Second.\n\\end{itemize}\n"
        translated = "\\item 一つ目。\n  \\item 二つ目。"
        restored = restore_secondary_list_scaffold(source, translated)
        self.assertEqual(restored.count(r"\begin{itemize}"), 1)
        self.assertEqual(restored.count(r"\end{itemize}"), 1)
        self.assertEqual(restored.count(r"\item"), 2)

    def test_secondary_existing_list_gets_missing_first_item(self) -> None:
        source = "\\begin{itemize}\n\\item First.\n\\item Second.\n\\end{itemize}"
        translated = "\\begin{itemize}\n一つ目。\n\\item 二つ目。\n\\end{itemize}"
        restored = restore_secondary_list_scaffold(source, translated)
        self.assertIn("\\begin{itemize}\n\\item 一つ目。", restored)
        self.assertEqual(restored.count(r"\item"), 2)

    def test_secondary_list_preserves_translated_prefix_before_items(self) -> None:
        source = (
            "\\footnotetext{Note.\n}\\begin{itemize}\n"
            "\\item First.\n\\end{itemize}"
        )
        translated = (
            "\\footnotetext{注。\n}\\begin{itemize}\n"
            "\\item 一つ目。\n\\end{itemize}"
        )
        en_body, suffix, secondary = split_shared_environment_scaffold(
            source, translated
        )
        restored = restore_secondary_list_scaffold(en_body + suffix, secondary)
        self.assertTrue(restored.startswith("\\footnotetext{注。\n}\n"))
        self.assertIn("\\begin{itemize}\n\\item 一つ目。", restored)
        self.assertEqual(restored.count(r"\begin{itemize}"), 1)
        self.assertEqual(restored.count(r"\end{itemize}"), 1)

    def test_secondary_stream_does_not_duplicate_shared_inline_graphic(self) -> None:
        graphic = r"\includegraphics[width=1em]{shared-arrow.png}"
        source = graphic + " source continuation"
        translated = graphic + " 翻訳の続き"
        _, _, secondary = split_shared_environment_scaffold(source, translated)
        self.assertNotIn(r"\includegraphics", secondary)
        self.assertIn("翻訳の続き", secondary)

    def test_fusion_keeps_cross_segment_nested_lists_as_sibling_blocks(self) -> None:
        rows = [
            {
                "kind": "protected",
                "source_tex": "\\documentclass{book}\n\\begin{document}\n",
            },
            {
                "kind": "text",
                "en_tex": (
                    "\\begin{itemize}\n\\item\n\\begin{enumerate}\n"
                    "\\item Listen.\n\\end{enumerate}\n"
                ),
                "ja_tex": (
                    "\\begin{itemize}\n\\item\n\\begin{enumerate}\n"
                    "\\item 聴きなさい。\n\\end{enumerate}\n"
                ),
            },
            {
                "kind": "text",
                "en_tex": (
                    "\\item\n\\begin{enumerate}\n\\item Continue.\n"
                    "\\end{enumerate}\n\\end{itemize}\n"
                ),
                "ja_tex": (
                    "\\item\n\\begin{enumerate}\n\\item 続けなさい。\n"
                    "\\end{enumerate}\n\\end{itemize}\n"
                ),
            },
            {"kind": "protected", "source_tex": "\\end{document}\n"},
        ]
        fused, _ = fuse_english_main_japanese_secondary(rows)
        secondary_start = fused.index(r"\begin{JpSecondary}")
        self.assertLess(fused.index(r"\end{itemize}"), secondary_start)
        self.assertEqual(fused.count(r"\begin{itemize}"), 2)
        self.assertEqual(fused.count(r"\end{itemize}"), 2)
        self.assertEqual(fused.count(r"\begin{enumerate}"), 4)
        self.assertEqual(fused.count(r"\end{enumerate}"), 4)

    def test_secondary_caption_keeps_text_without_duplicate_float_command(self) -> None:
        translated = r"\caption{\JpRuby{図}{ず}235.1}"
        restored = demote_secondary_captions(translated)
        self.assertNotIn(r"\caption", restored)
        self.assertEqual(restored, r"\textit{\JpRuby{図}{ず}235.1}")

    def test_oversized_inline_math_is_fitted_without_changing_atom(self) -> None:
        body = r"x_1+" * 80 + "x_n"
        rendered, count = wrap_wide_inline_math(
            f"Before \\({body}\\) after.", layout="exact"
        )
        self.assertEqual(count, 1)
        self.assertIn(body, rendered)
        self.assertIn(r"\penalty0\hspace{0pt}", rendered)
        self.assertIn(r"\adjustbox{max width=.60\linewidth}", rendered)

    def test_oversized_inline_math_is_not_wrapped_inside_caption(self) -> None:
        body = r"x_1+" * 80 + "x_n"
        caption = rf"\caption{{Long formula \({body}\).}}"
        rendered, count = wrap_wide_inline_math(caption, layout="pocket")
        self.assertEqual(count, 0)
        self.assertEqual(rendered, caption)
        self.assertNotIn(r"\adjustbox", rendered)

    def test_long_pocket_decimal_run_is_fitted(self) -> None:
        body = ", ".join(f".{6290 + index}" for index in range(14))
        rendered, count = wrap_wide_inline_math(
            f"Values converge to \\({body}\\).", layout="pocket"
        )
        self.assertEqual(count, 1)
        self.assertIn(body, rendered)
        self.assertIn(r"\adjustbox{max width=.56\linewidth}", rendered)

    def test_evidence_layout_repair_restores_split_probability_identity(self) -> None:
        malformed = r"\(a +\) \(b^{1=b\text{, making prose}}) continuation"
        repaired, changes = apply_exact_text_replacements(
            malformed,
            [{
                "before": r"\(a +\) \(b^{1=b\text{, making prose}})",
                "after": r"\(a+b^1=b\)",
                "expected_count": 1,
            }],
        )
        self.assertEqual(repaired, r"\(a+b^1=b\) continuation")
        self.assertEqual(len(changes), 1)

    def test_evidence_layout_repair_restores_bibliography_prose(self) -> None:
        malformed = r"Before \({}^{R u b i n s t e i n}\) Extension after"
        repaired, _ = apply_exact_text_replacements(
            malformed,
            [{
                "before": r"\({}^{R u b i n s t e i n}\)",
                "after": "Rubinstein",
                "expected_count": 1,
            }],
        )
        self.assertEqual(repaired, "Before Rubinstein Extension after")

    def test_cover_handoff_copies_only_exact_reported_generated_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated = root / ".codex/generated_images/session/exact.png"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"png")
            target = root / "assets/covers/book/cover.png"
            output = f"Generated image: `{generated}`\n"
            with patch(
                "ensure_textless_pocket_polished_cover.valid_cover",
                side_effect=lambda path: path == generated,
            ):
                self.assertTrue(recover_generated_cover(output, target))
            self.assertEqual(target.read_bytes(), b"png")

            unrelated = root / ".codex/generated_images/session/unrelated.png"
            unrelated.write_bytes(b"other")
            ambiguous = output + f"Also: `{unrelated}`\n"
            with patch(
                "ensure_textless_pocket_polished_cover.valid_cover", return_value=True
            ):
                self.assertFalse(recover_generated_cover(ambiguous, target))

    def test_compact_writer_is_canonicalized_without_english_rewrite(self) -> None:
        raw = {
            "schema_version": 3,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": [
                {
                    "segment_id": self.first["segment_id"],
                    "source_sha256": self.first["source_sha256"],
                    "ja_tex": "それは終わった。その後、287万が残った。",
                    "repairs": [],
                    "unresolved": [],
                },
                {
                    "segment_id": self.second["segment_id"],
                    "source_sha256": self.second["source_sha256"],
                    "ja_tex": "その値は1905だった。",
                    "repairs": [],
                    "unresolved": [],
                },
            ],
        }
        canonical, errors = canonicalize_writer_result(self.task, raw)
        self.assertFalse(any(errors.values()))
        self.assertEqual(
            canonical[self.first["segment_id"]]["en_tex"],
            "It ended. Then 2.87 million remained.",
        )
        self.assertEqual(
            canonical[self.first["segment_id"]]["changes"][0]["before"],
            "ended.Then",
        )
        self.assertFalse(
            validate_segment_output(
                self.task, self.first, canonical[self.first["segment_id"]]
            )
        )

    def test_stale_writer_header_is_repaired_when_segment_identity_is_exact(self) -> None:
        raw = {
            "schema_version": 3,
            "book_id": "stale-book",
            "chunk_id": "stale-book-p00009",
            "segments": [
                {
                    "segment_id": source["segment_id"],
                    "ja_tex": "正確な訳。",
                    "repairs": [],
                    "unresolved": [],
                }
                for source in self.task["segments"]
            ],
        }
        canonical, errors = canonicalize_writer_result(self.task, raw)
        self.assertEqual(list(canonical), [self.first["segment_id"], self.second["segment_id"]])
        self.assertFalse(any(errors.values()))

    def test_stale_writer_header_is_rejected_when_segment_identity_is_not_exact(self) -> None:
        raw = {
            "schema_version": 3,
            "book_id": "stale-book",
            "chunk_id": "stale-book-p00009",
            "segments": [],
        }
        _canonical, errors = canonicalize_writer_result(self.task, raw)
        self.assertIn("book_id mismatch", errors[self.first["segment_id"]])
        self.assertIn("chunk_id mismatch", errors[self.first["segment_id"]])

    def test_japanese_numeric_reformat_is_semantic_observation_not_rejection(self) -> None:
        output = {
            "segment_id": self.first["segment_id"],
            "source_sha256": self.first["source_sha256"],
            "en_tex": "It ended. Then 2.87 million remained.",
            "ja_tex": "それは終わった。その後、287万が残った。",
            "changes": [
                {
                    "before": "ended.Then",
                    "after": "ended. Then",
                    "reason": "Restored missing whitespace after sentence punctuation.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(self.task, self.first, output))
        candidate = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": [output],
        }
        subset = chunk_subset(self.task, [self.first["segment_id"]])
        self.assertEqual(len(machine_review_observations(subset, candidate)), 1)

    def test_surplus_antecedent_placeholder_is_removed_without_weakening_inventory(self) -> None:
        source = source_segment(
            "book-protected",
            "player @@PROTECTED_0006@@'s payoff when he plays @@PROTECTED_0007@@",
        )
        translated = (
            "プレイヤー@@PROTECTED_0006@@の利得。"
            "プレイヤー@@PROTECTED_0006@@が@@PROTECTED_0007@@を用いる。"
        )
        repaired = remove_surplus_protected_tokens(source["source_tex"], translated)
        self.assertEqual(
            repaired,
            "プレイヤー@@PROTECTED_0006@@の利得。プレイヤーが@@PROTECTED_0007@@を用いる。",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": repaired,
            "changes": [],
            "unresolved": [],
        }
        task = {**self.task, "segments": [source], "validation_profile": "prose_exact"}
        self.assertFalse(validate_segment_output(task, source, output))

    def test_segment_cache_is_source_hash_gated(self) -> None:
        output = {
            "segment_id": self.second["segment_id"],
            "source_sha256": self.second["source_sha256"],
            "en_tex": self.second["source_tex"],
            "ja_tex": "その値は1905だった。",
            "changes": [],
            "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_cached_segment(
                self.task,
                self.second,
                output,
                {"accept": True, "issues": [], "summary": "ok"},
                root,
            )
            self.assertEqual(
                load_cached_segment(self.task, self.second, root), output
            )
            changed = dict(self.second, source_sha256="different")
            self.assertIsNone(load_cached_segment(self.task, changed, root))

    def test_segment_cache_survives_content_addressed_id_migration(self) -> None:
        output = {
            "segment_id": self.second["segment_id"],
            "source_sha256": self.second["source_sha256"],
            "en_tex": self.second["source_tex"],
            "ja_tex": "その値は1905だった。",
            "changes": [],
            "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_cached_segment(
                self.task,
                self.second,
                output,
                {"accept": True, "issues": [], "summary": "ok"},
                root,
            )
            migrated = dict(self.second, segment_id="book-scontenthash-01")
            task = dict(self.task, segments=[migrated], segment_count=1)
            reused = load_cached_segment(task, migrated, root)
            self.assertIsNotNone(reused)
            self.assertEqual(reused["segment_id"], migrated["segment_id"])

    def test_reviewed_chunk_salvages_only_currently_valid_segments(self) -> None:
        first_output = {
            "segment_id": self.first["segment_id"],
            "source_sha256": self.first["source_sha256"],
            "en_tex": "It ended. Then 287 million remained.",
            "ja_tex": "それは終わった。その後、287万が残った。",
            "changes": [],
            "unresolved": [],
        }
        second_output = {
            "segment_id": self.second["segment_id"],
            "source_sha256": self.second["source_sha256"],
            "en_tex": self.second["source_tex"],
            "ja_tex": "その値は1905だった。",
            "changes": [],
            "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_path = root / "json/book-p00001.json"
            review_path = root / "review/book-p00001.json"
            output_path.parent.mkdir(parents=True)
            review_path.parent.mkdir(parents=True)
            output_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "book_id": "book",
                        "chunk_id": "book-p00001",
                        "segments": [first_output, second_output],
                    }
                ),
                encoding="utf-8",
            )
            review_path.write_text(
                json.dumps({"accept": True, "issues": [], "summary": "reviewed"}),
                encoding="utf-8",
            )
            promoted = salvage_reviewed_chunk_segments(
                self.task, output_path, root
            )
            self.assertEqual(promoted, 1)
            self.assertIsNone(load_cached_segment(self.task, self.first, root))
            self.assertEqual(
                load_cached_segment(self.task, self.second, root), second_output
            )

    def test_pending_review_survives_content_addressed_id_migration(self) -> None:
        migrated = dict(self.second, segment_id="book-scontenthash-01")
        task = dict(self.task, segments=[migrated], segment_count=1)
        candidate = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": [
                {
                    "segment_id": "book-s000002",
                    "source_sha256": self.second["source_sha256"],
                    "en_tex": self.second["source_tex"],
                    "ja_tex": "その値は1905だった。",
                    "changes": [],
                    "unresolved": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = (
                root
                / "work/runs/older/attempts/book-p00001/attempt-03.pending-review.json"
            )
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(candidate), encoding="utf-8")
            recovered = load_pending_review_segments(task, root)
            self.assertEqual(list(recovered), [migrated["segment_id"]])
            self.assertEqual(
                recovered[migrated["segment_id"]]["segment_id"],
                migrated["segment_id"],
            )

    def test_semantically_rejected_pending_segment_is_not_recovered(self) -> None:
        candidate = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": [
                {
                    "segment_id": self.second["segment_id"],
                    "source_sha256": self.second["source_sha256"],
                    "en_tex": self.second["source_tex"],
                    "ja_tex": "その値は1905だった。",
                    "changes": [],
                    "unresolved": [],
                }
            ],
        }
        review = {
            "accept": False,
            "issues": [
                {
                    "segment_id": self.second["segment_id"],
                    "severity": "error",
                    "message": "Evidence is insufficient.",
                }
            ],
            "corrections": [],
            "summary": "Rejected.",
        }
        task = dict(self.task, segments=[self.second], segment_count=1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "work/runs/older/attempts/book-p00001/attempt-01"
            base.parent.mkdir(parents=True)
            base.with_suffix(".pending-review.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            base.with_suffix(".review.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            base.with_suffix(".writer-canonical.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            self.assertFalse(load_pending_review_segments(task, root))

    def test_validator_upgrade_recovers_unreviewed_canonical_segment(self) -> None:
        source = source_segment(
            "book-snumeric",
            "These concepts are ordina1ily introduced in college.",
        )
        task = dict(self.task, segments=[source], segment_count=1)
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "These concepts are ordinarily introduced in college.",
            "ja_tex": "これらの概念は通常、大学で初めて学ぶ。",
            "changes": [
                {
                    "before": "ordina1ily",
                    "after": "ordinarily",
                    "reason": "Repair an OCR substitution of one for lowercase l.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        candidate = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": [output],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = (
                root
                / "work/runs/older/attempts/book-p00001/attempt-01.writer-canonical.json"
            )
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(candidate), encoding="utf-8")
            recovered = load_pending_review_segments(task, root)
            self.assertEqual(recovered, {source["segment_id"]: output})

    def test_legacy_ambiguous_spacing_evidence_is_migrated(self) -> None:
        output = {
            "segment_id": self.first["segment_id"],
            "source_sha256": self.first["source_sha256"],
            "en_tex": "It ended. Then 2.87 million remained.",
            "ja_tex": "それは終わった。その後、287万が残った。",
            "changes": [
                {
                    "before": ".",
                    "after": ". ",
                    "reason": "Restored missing whitespace after sentence punctuation.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        migrated = migrate_legacy_cached_output(self.task, self.first, output)
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated["en_tex"], output["en_tex"])
        self.assertEqual(migrated["changes"][0]["before"], "ended.Then")
        self.assertFalse(
            validate_segment_output(self.task, self.first, migrated)
        )

    def test_equation_environment_is_immutable(self) -> None:
        tex = (
            "\\documentclass{book}\n\\begin{document}\n"
            "Text.\n\n\\begin{equation}E=mc^2\\end{equation}\n\nMore.\n"
            "\\end{document}\n"
        )
        segments = split_tex_segments(tex, "book", validation_profile="technical_exact")
        equation = next(item for item in segments if "E=mc^2" in item["source_tex"])
        self.assertEqual(equation["kind"], "protected")

    def test_segment_ids_are_stable_when_earlier_content_changes(self) -> None:
        first = (
            "\\documentclass{book}\n\\begin{document}\n"
            "Alpha paragraph.\n\nStable paragraph text.\n"
            "\\end{document}\n"
        )
        second = first.replace("Alpha paragraph.", "Different opening paragraph.")
        first_segments = split_tex_segments(first, "book")
        second_segments = split_tex_segments(second, "book")
        first_stable = next(
            row for row in first_segments if "Stable paragraph" in row["source_tex"]
        )
        second_stable = next(
            row for row in second_segments if "Stable paragraph" in row["source_tex"]
        )
        self.assertEqual(first_stable["segment_id"], second_stable["segment_id"])

    def test_placeholder_serial_is_not_a_numeric_fact(self) -> None:
        self.assertEqual(numeric_signature("x @@PROTECTED_0001@@ 1905"), ["1905"])

    def test_flattened_ocr_exponents_match_only_when_digits_are_preserved(self) -> None:
        self.assertTrue(
            numeric_signature_matches(
                ["1000", "10", "5", "3", "105", "3"],
                r"1000 K, 10^{-5}, \lambda^3, [R\times 10^5]^3",
            )
        )
        self.assertTrue(
            numeric_signature_matches(
                ["1051", "1028"],
                r"R\sim 10^{51}\,\mathrm{cm}; 10^{28}\,\mathrm{cm}",
            )
        )
        self.assertFalse(
            numeric_signature_matches(
                ["1051", "1028"],
                r"R\sim 10^{50}\,\mathrm{cm}; 10^{28}\,\mathrm{cm}",
            )
        )

    def test_grounded_numeric_ocr_repair_reaches_semantic_review(self) -> None:
        source = source_segment(
            "book-snumeric",
            "These concepts are ordina1ily introduced in college.",
        )
        task = dict(self.task, segments=[source], segment_count=1)
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "These concepts are ordinarily introduced in college.",
            "ja_tex": "これらの概念は通常、大学で初めて学ぶ。",
            "changes": [
                {
                    "before": "ordina1ily",
                    "after": "ordinarily",
                    "reason": "Repair an OCR substitution of one for lowercase l.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

    def test_short_catalog_control_fragment_need_not_invent_japanese(self) -> None:
        source_tex = (
            "\\begin{enumerate}\n"
            "\\def\\labelenumi{alph{enumi}.}\n"
            "\\setcounter{enumi}{15}\n"
            "\\tightlist\n"
            "\\item\n"
            "  cm.\n"
            "\\end{enumerate}"
        )
        source = source_segment("book-scatalog", source_tex)
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source_tex,
            "ja_tex": source_tex,
            "changes": [],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

    def test_automatic_repair_remains_idempotent_after_overlapping_patch(self) -> None:
        from pocket_polished_common import apply_grounded_english_repairs

        repaired, _changes, errors = apply_grounded_english_repairs(
            "Photons have wavelength 10−5 cm.Then continue.",
            [
                {
                    "before": "10−5 cm",
                    "after": r"\(10^{-5}\,\mathrm{cm}\)",
                    "reason": "Restore the exponent and unit markup.",
                    "confidence": 0.99,
                },
                {
                    "before": "cm.Then",
                    "after": "cm. Then",
                    "reason": "Restore sentence spacing.",
                    "confidence": 0.99,
                },
            ],
        )
        self.assertFalse(errors)
        self.assertEqual(
            repaired,
            r"Photons have wavelength \(10^{-5}\,\mathrm{cm}\). Then continue.",
        )

    def test_plain_subscript_log_relation_is_typeset_as_math(self) -> None:
        repaired, count = normalize_unwrapped_math_fragments(
            "Introduce a cutoff at u_o = log ε and continue."
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            repaired,
            r"Introduce a cutoff at \(u_o = \log \epsilon\) and continue.",
        )
        repaired, count = normalize_unwrapped_math_fragments(
            "ある点u_o = log εにカットオフを置く。"
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            repaired,
            r"ある点\(u_o = \log \epsilon\)にカットオフを置く。",
        )
        unchanged, count = normalize_unwrapped_math_fragments(
            r"Already \(u_o = \log \epsilon\)."
        )
        self.assertEqual(count, 0)
        self.assertEqual(unchanged, r"Already \(u_o = \log \epsilon\).")
        unchanged, count = normalize_unwrapped_math_fragments(
            r"Already \(u = u_1 = -log k\)."
        )
        self.assertEqual(count, 0)
        self.assertEqual(unchanged, r"Already \(u = u_1 = -log k\).")

    def test_plain_technical_power_expressions_are_typeset_as_math(self) -> None:
        source = (
            "Assume a(t) = a₀tᵖ. Then "
            r"t^{(1-p)d} \textless{} t^{d-1}.This follows when "
            "φ(r) ∼ r^{-4}Φ as r → ∞.It is finite."
        )
        repaired, count = normalize_unwrapped_math_fragments(source)
        self.assertEqual(count, 5)
        self.assertEqual(
            repaired,
            "Assume "
            r"\(a(t) = a_0 t^p\). Then "
            r"\(t^{(1-p)d} < t^{d-1}\). This follows when "
            r"\(\phi(r) \sim r^{-4}\Phi\) as r → ∞. It is finite.",
        )

    def test_plain_numeric_powers_are_typeset_without_nested_math(self) -> None:
        source = (
            "There are 10^90 photons; an electron weighs "
            "9 × 10^-31 kilograms; a googolplex is 10^googol."
        )
        repaired, count = normalize_unwrapped_math_fragments(source)
        self.assertEqual(count, 3)
        self.assertEqual(
            repaired,
            "There are "
            r"\(10^{90}\) photons; an electron weighs "
            r"\(9 \times 10^{-31}\) kilograms; a googolplex is "
            r"\(10^{\mathrm{googol}}\).",
        )

    def test_numeric_math_wrapping_difference_is_not_equation_loss(self) -> None:
        source = source_segment(
            "book-snumeric-power",
            "The total number of photons is about 1090.",
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "The total number of photons is about 10^90.",
            "ja_tex": "光子の総数はおよそ $10^{90}$ 個である。",
            "changes": [
                {
                    "before": "1090",
                    "after": "10^90",
                    "reason": "Restore a flattened exponent.",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

    def test_technical_math_inventory_allows_unit_wrapper_and_variable_placement(self) -> None:
        source_tex = (
            r"Photons of wavelength 10−5 cm satisfy "
            r"Nγ ∼ V λ3 ∼ R(cm) ⊗ 105 3."
        )
        source = source_segment("book-tech", source_tex)
        task = {
            "schema_version": 1,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "source_language": "en",
            "validation_profile": "technical_exact",
            "segment_count": 1,
            "segments": [source],
        }
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": (
                r"Photons of wavelength \(10^{-5}\) cm satisfy "
                r"\(N_\gamma \sim V/\lambda^3 \sim [R(\mathrm{cm})\times 10^5]^3\)."
            ),
            "ja_tex": (
                r"波長 \(10^{-5}\,\mathrm{cm}\) の光子について、半径 \(R\) の体積では "
                r"\(N_\gamma \sim V/\lambda^3 \sim [R(\mathrm{cm})\times 10^5]^3\) となる。"
            ),
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn(
            "book-tech: English/Japanese math inventory differs", errors
        )
        self.assertNotIn("book-tech: en_tex changed numeric facts/counts", errors)

    def test_angle_strategy_profile_is_not_html_and_translated_labels_match(self) -> None:
        source = source_segment("book-profile", "The equilibrium is <up, left>.")
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "The equilibrium is <up, left>.",
            "ja_tex": r"均衡は \(\langle\text{上},\text{左}\rangle\) である。",
            "changes": [],
            "unresolved": [],
        }
        errors = validate_segment_output(task, source, output)
        self.assertNotIn("book-profile: en_tex contains replacement/HTML text", errors)
        self.assertNotIn("book-profile: English/Japanese math inventory differs", errors)

    def test_real_html_is_still_rejected(self) -> None:
        source = source_segment("book-html", "Choose up.")
        task = dict(self.task, segments=[source], segment_count=1)
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "Choose <span>up</span>.",
            "ja_tex": "上を選ぶ。",
            "changes": [],
            "unresolved": [],
        }
        self.assertIn(
            "book-html: en_tex contains replacement/HTML text",
            validate_segment_output(task, source, output),
        )

    def test_signed_scalar_math_wrapper_is_presentation_only(self) -> None:
        source = source_segment("book-signed", "The payoff is -2.")
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "The payoff is -2.",
            "ja_tex": r"利得は \(-2\) である。",
            "changes": [],
            "unresolved": [],
        }
        self.assertNotIn(
            "book-signed: English/Japanese math inventory differs",
            validate_segment_output(task, source, output),
        )

    def test_reviewer_japanese_patch_note_does_not_force_regeneration(self) -> None:
        correction = {
            "segment_id": self.first["segment_id"],
            "source_sha256": self.first["source_sha256"],
            "ja_tex": "それは終わった。その後、287万が残った。",
            "repairs": [
                {
                    "before": "ended.Then",
                    "after": "ended. Then",
                    "reason": "Restore an English sentence boundary.",
                    "confidence": 0.99,
                },
                {
                    "before": "誤った日本語",
                    "after": "正しい日本語",
                    "reason": "Japanese edits belong in ja_tex.",
                    "confidence": 0.99,
                },
            ],
            "unresolved": [],
        }
        subset = chunk_subset(self.task, [self.first["segment_id"]])
        rows = sanitize_reviewer_corrections(subset, [correction])
        self.assertEqual(len(rows[0]["repairs"]), 1)
        raw = {
            "schema_version": 3,
            "book_id": "book",
            "chunk_id": "book-p00001",
            "segments": rows,
        }
        canonical, errors = canonicalize_writer_result(subset, raw)
        self.assertFalse(any(errors.values()))
        self.assertEqual(
            canonical[self.first["segment_id"]]["en_tex"],
            "It ended. Then 2.87 million remained.",
        )

    def test_running_header_between_sentence_halves_is_removed_with_evidence(self) -> None:
        source = (
            "We may be inside a gigantic black\n\n"
            "\\emph{Preface} xi\n\n"
            "hole caused by future collapse.\n"
        )
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(
            normalized,
            "We may be inside a gigantic black hole caused by future collapse.\n",
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["marker_text"], "Preface xi")

    def test_clearpage_between_sentence_halves_is_removed_with_evidence(self) -> None:
        source = (
            "We denote the vectors of nonnegative real numbers by the set of\n\n"
            "\\clearpage\n\n"
            "vectors whose coordinates are all nonnegative.\n"
        )
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(
            normalized,
            "We denote the vectors of nonnegative real numbers by the set of "
            "vectors whose coordinates are all nonnegative.\n",
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["type"], "page-boundary-command")
        self.assertEqual(changes[0]["marker_tex"], "\\clearpage")

    def test_clearpage_before_inline_math_continuation_is_joined(self) -> None:
        source = (
            "The outcome is defined for each\n\n"
            "\\clearpage\n\n"
            "\\(p \\in P\\). The result follows.\n"
        )
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(
            normalized,
            "The outcome is defined for each \\(p \\in P\\). The result follows.\n",
        )
        self.assertEqual(len(changes), 1)

    def test_bibliography_entry_may_remain_in_source_script(self) -> None:
        source = source_segment(
            "book-sbibliography",
            'Geanakoplos, J. (1992), "Common Knowledge", Journal of Economic Perspectives 6, 53-82. [85]',
        )
        task = dict(
            self.task,
            segments=[source],
            segment_count=1,
            validation_profile="technical_exact",
        )
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": source["source_tex"],
            "changes": [],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

        translated = dict(
            output,
            ja_tex=(
                "Geanakoplos, J.（1992）「共通知識」"
                "『Journal of Economic Perspectives』第6巻、53--82頁。[85]"
            ),
        )
        self.assertNotIn(
            "book-sbibliography: Japanese prose contains no kana",
            validate_segment_output(task, source, translated),
        )

    def test_clearpage_before_heading_is_preserved(self) -> None:
        source = (
            "This introductory discussion leads to\n\n"
            "\\clearpage\n\n"
            "\\section*{definitions}\n"
        )
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(normalized, source)
        self.assertFalse(changes)

    def test_real_heading_is_not_removed(self) -> None:
        source = "A complete sentence.\n\n\\textbf{Chapter 1}\n\nnext paragraph.\n"
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(normalized, source)
        self.assertFalse(changes)

    def test_equation_number_paragraph_is_not_removed(self) -> None:
        source = (
            "The equation gives\n\n"
            "2 2MG(r - 2MG) 1.3.14\n\n"
            "the required near-horizon limit.\n"
        )
        normalized, changes = normalize_page_boundary_artifacts(source)
        self.assertEqual(normalized, source)
        self.assertFalse(changes)

    def test_configured_running_header_drop_is_exact_and_auditable(self) -> None:
        source = "First paragraph.\n\n\\emph{Strings} 153\n\nNext paragraph.\n"
        normalized, changes = apply_exact_paragraph_drops(
            source,
            [
                {
                    "tex": "\\emph{Strings} 153",
                    "expected_count": 1,
                    "reason": "Printed running header inside body text.",
                }
            ],
        )
        self.assertNotIn("\\emph{Strings} 153", normalized)
        self.assertIn("Removed evidence-reviewed source artifact", normalized)
        self.assertEqual(changes[0]["marker_text"], "Strings 153")

    def test_plain_page_break_inside_prose_is_joined(self) -> None:
        source = (
            "The radial coordinate does not measure proper\n\n"
            "spatial distance from the origin, but instead measures area.\n"
        )
        normalized, changes = normalize_split_prose_paragraphs(source)
        self.assertIn("proper spatial distance", normalized)
        self.assertEqual(len(changes), 1)

    def test_figure_caption_is_not_joined_to_following_prose(self) -> None:
        source = (
            "Fig. 14.1 Free particle falling through a Rindler horizon\n\n"
            "coordinates then provide the independent time coordinate.\n"
        )
        normalized, changes = normalize_split_prose_paragraphs(source)
        self.assertEqual(normalized, source)
        self.assertFalse(changes)

    def test_epigraph_attribution_is_not_joined_to_body(self) -> None:
        source = (
            "-ROBERT A. HEINLEIN, STRANGER IN A STRANGE LAND\n\n"
            "omewhere on the savanna, an aging lion waits.\n"
        )
        normalized, changes = normalize_split_prose_paragraphs(source)
        self.assertEqual(normalized, source)
        self.assertFalse(changes)

    def test_exact_inline_running_header_repair_is_cardinality_checked(self) -> None:
        source = "The particle is probed by an Strings 155\n\nexperiment."
        normalized, changes = apply_exact_text_replacements(
            source,
            [
                {
                    "before": "an Strings 155\n\nexperiment",
                    "after": "an experiment",
                    "expected_count": 1,
                    "reason": "Printed running header inserted inside a sentence.",
                }
            ],
        )
        self.assertEqual(normalized, "The particle is probed by an experiment.")
        self.assertEqual(len(changes), 1)

    def test_japanese_may_reorder_immutable_tokens_without_changing_inventory(self) -> None:
        source = source_segment(
            "book-s000003",
            "At @@PROTECTED_0001@@, compare @@PROTECTED_0002@@.",
        )
        source["protected"] = [
            {"token": "@@PROTECTED_0001@@", "tex": "\\(x=1\\)"},
            {"token": "@@PROTECTED_0002@@", "tex": "\\(y=2\\)"},
        ]
        task = dict(self.task, segments=[source], segment_count=1)
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": source["source_tex"],
            "ja_tex": "@@PROTECTED_0002@@ を、@@PROTECTED_0001@@ において比較する。",
            "changes": [],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

    def test_overlapping_grounded_repairs_validate_by_ordered_replay(self) -> None:
        source = source_segment(
            "book-s000004",
            "Two regions, A and B.The Region A is interior.",
        )
        task = dict(self.task, segments=[source], segment_count=1)
        output = {
            "segment_id": source["segment_id"],
            "source_sha256": source["source_sha256"],
            "en_tex": "Two regions, A and B. Region A is interior.",
            "ja_tex": "AとBの二領域があり、領域Aは内側にある。",
            "changes": [
                {
                    "before": "B.The",
                    "after": "B. The",
                    "reason": "Restore sentence spacing.",
                    "confidence": 0.99,
                },
                {
                    "before": "The Region A",
                    "after": "Region A",
                    "reason": "Remove a definite duplicated article.",
                    "confidence": 0.99,
                },
            ],
            "unresolved": [],
        }
        self.assertFalse(validate_segment_output(task, source, output))

    def test_short_simple_longtable_is_width_fitted_without_page_breaking(self) -> None:
        source = (
            r"\begin{longtable}[]{@{}ll@{}}" "\n"
            r"A & B \\" "\n"
            r"C & D \\" "\n"
            r"\end{longtable}"
        )
        fitted, count = fit_short_simple_longtables(source)
        self.assertEqual(count, 1)
        self.assertNotIn(r"\begin{longtable}", fitted)
        self.assertIn(r"\resizebox{.84\paperwidth}{!}", fitted)
        self.assertIn(r"\begin{tabular}{@{}ll@{}}", fitted)

    def test_long_simple_longtable_keeps_page_breaking(self) -> None:
        body = "\n".join(f"{index} & value \\\\" for index in range(13))
        source = r"\begin{longtable}[]{@{}ll@{}}" + "\n" + body + "\n" + r"\end{longtable}"
        fitted, count = fit_short_simple_longtables(source)
        self.assertEqual(count, 0)
        self.assertEqual(fitted, source)

    def test_short_complex_longtable_is_width_fitted(self) -> None:
        source = (
            r"\begin{longtable}[]{@{}"
            r">{\raggedright\arraybackslash}p{.3\columnwidth}"
            r">{\centering\arraybackslash}p{.2\columnwidth}@{}}"
            "\nA & B \\\\\nC & D \\\\\n\\endhead\n"
            r"\end{longtable}"
        )
        fitted, count = fit_short_complex_longtables(source)
        self.assertEqual(count, 1)
        self.assertNotIn(r"\begin{longtable}", fitted)
        self.assertIn(r"\resizebox{.84\paperwidth}{!}", fitted)
        self.assertNotIn(r"\endhead", fitted)

    def test_long_simple_longtable_gets_wrapping_columns(self) -> None:
        rows = [f"{index}. & A deliberately long table description \\\\" for index in range(13)]
        source = (
            r"\begin{longtable}[]{@{}ll@{}}"
            + "\n"
            + "\n".join(rows)
            + "\n"
            + r"\end{longtable}"
        )
        fitted, count = wrap_long_simple_longtables(source)
        self.assertEqual(count, 1)
        self.assertIn(r"\begin{longtable}", fitted)
        self.assertIn(r">{\raggedright\arraybackslash}p{", fitted)

    def test_fusion_reconciles_protected_table_openers_with_translated_caption_closers(self) -> None:
        rows = [
            {
                "kind": "protected",
                "source_tex": "\\documentclass{book}\n\\begin{document}\n",
            },
            {
                "kind": "protected",
                "source_tex": "\\begin{table}[h]\n\\begin{center}\n",
            },
            {
                "kind": "protected",
                "source_tex": "\\begin{tabular}{cc}A&B\\\\\\n\\end{tabular}",
            },
            {
                "kind": "text",
                "en_tex": "\n\\caption{Full figure caption.}\n\\end{center}\n\\end{table}",
                "ja_tex": "\n\\caption{図の完全なキャプション。}\n\\end{center}\n\\end{table}",
            },
            {"kind": "protected", "source_tex": "\n\\end{document}\n"},
        ]
        fused, _ = fuse_english_main_japanese_secondary(rows)
        self.assertEqual(fused.count(r"\begin{table}"), 1)
        self.assertEqual(fused.count(r"\end{table}"), 1)
        self.assertIn("Full figure caption.", fused)
        self.assertIn("キャプション。", fused)
        self.assertLess(fused.index("キャプション。"), fused.index(r"\end{table}"))

    def test_fusion_places_translated_caption_after_source_figure_float(self) -> None:
        rows = [
            {
                "kind": "protected",
                "source_tex": "\\documentclass{book}\n\\begin{document}\n",
            },
            {
                "kind": "protected",
                "source_tex": "\\begin{figure}[h]\n\\begin{center}\n",
            },
            {
                "kind": "text",
                "en_tex": "\\caption{Full figure caption.}\n\\end{center}\n\\end{figure}",
                "ja_tex": "\\caption{図の完全なキャプション。}\n\\end{center}\n\\end{figure}",
            },
            {"kind": "protected", "source_tex": "\n\\end{document}\n"},
        ]
        fused, _ = fuse_english_main_japanese_secondary(rows)
        self.assertEqual(fused.count(r"\begin{figure}"), 1)
        self.assertEqual(fused.count(r"\end{figure}"), 1)
        self.assertIn("キャプション。", fused)
        self.assertLess(fused.index(r"\end{figure}"), fused.index("キャプション。"))

    def test_wide_math_wrapper_ignores_caption_optional_linebreak_spacing(self) -> None:
        source = restore_split_optional_linebreaks(
            "\\caption{Title}\\[0pt]\nText}\n\\[" + ("x+" * 60) + "y\\]"
        )
        rendered = wrap_wide_display_math(source, layout="pocket")
        self.assertIn(r"\caption{Title\\[0pt]", rendered)
        self.assertEqual(rendered.count(r"\begin{adjustbox}"), 1)
        self.assertEqual(restore_split_optional_linebreaks("\\\\\n[0,1]"), "\\\\{}\n[0,1]")
        self.assertEqual(
            restore_split_optional_linebreaks(
                "\\end{JpSecondary}\n\\\\[0pt]\nAfter"
            ),
            "\\end{JpSecondary}\n\\par\nAfter",
        )
        self.assertEqual(
            restore_split_optional_linebreaks(
                "\\caption{Title\n\\\\[0pt]\ncontinued}"
            ),
            "\\caption{Title\n\\\\[0pt]\ncontinued}",
        )

    def test_wide_math_environment_wrapper_is_idempotent(self) -> None:
        equation = (
            r"\begin{equation*}"
            + (r"\frac{x_1+x_2+x_3}{y_1+y_2+y_3}+" * 12)
            + r"z\tag{1}\end{equation*}"
        )
        rendered, fitted = wrap_wide_math_environments(equation, layout="pocket")
        repeated, repeated_fitted = wrap_wide_math_environments(
            rendered, layout="pocket"
        )
        self.assertEqual(fitted, 1)
        self.assertEqual(repeated_fitted, 0)
        self.assertEqual(repeated, rendered)
        self.assertEqual(rendered.count("BUILD_POCKET_WIDE_MATH_BEGIN"), 1)
        self.assertIn(equation, rendered)

    def test_legacy_full_page_cover_is_replaced_not_duplicated(self) -> None:
        source = (
            "\\begin{document}\n\\frontmatter\n\n"
            "\\thispagestyle{empty}\n"
            "\\noindent\\makebox[\\textwidth][c]{"
            "\\includegraphics[width=\\paperwidth,height=\\paperheight]{cover.png}}\n"
            "\\clearpage\n\\mainmatter\nBody\n\\end{document}"
        )
        cleaned, removed = remove_legacy_full_page_cover(source)
        self.assertEqual(removed, 1)
        self.assertNotIn("cover.png", cleaned)
        self.assertIn("\\frontmatter", cleaned)
        self.assertIn("\\mainmatter", cleaned)

    def test_pocket_layout_makes_self_labeled_urls_breakable(self) -> None:
        source = (
            "\\documentclass{book}\n\\usepackage{geometry}\n"
            "\\usepackage{hyperref}\n"
            "\\geometry{paperwidth=210mm,paperheight=297mm,inner=18mm,"
            "outer=18mm,top=18mm,bottom=20mm,footskip=10mm}\n"
            "\\begin{document}"
            "\\href{https://example.com/a/very/long/path}"
            "{https://example.com/a/very/long/path}"
            "\\end{document}"
        )
        rendered = pocket_layout(source)
        self.assertIn(r"\usepackage{xurl}", rendered)
        self.assertIn(r"\url{https://example.com/a/very/long/path}", rendered)
        self.assertNotIn(r"\href{https://example.com/a/very/long/path}", rendered)

    def test_cover_injection_preserves_document_paper_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tex_path = root / "book.tex"
            cover_path = root / "cover.png"
            tex_path.write_text(r"\documentclass{book}\begin{document}Text\end{document}", encoding="utf-8")
            cover_path.write_bytes(b"test-cover")
            self.assertTrue(inject_cover_page(tex_path, cover_path))
            rendered = tex_path.read_text(encoding="utf-8")
            self.assertNotIn("fitpaper=true", rendered)
            self.assertIn(r"width=\paperwidth,height=\paperheight", rendered)


if __name__ == "__main__":
    unittest.main()
