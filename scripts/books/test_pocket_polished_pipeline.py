#!/usr/bin/env python3
"""Focused regression checks for the resumable pocket-polish pipeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_pocket_polish_worker import (
    canonicalize_writer_result,
    load_cached_segment,
    load_pending_review_segments,
    migrate_legacy_cached_output,
    sanitize_reviewer_corrections,
    save_cached_segment,
)
from pocket_polished_common import (
    apply_exact_paragraph_drops,
    apply_exact_text_replacements,
    chunk_subset,
    command_signature,
    machine_review_observations,
    normalize_page_boundary_artifacts,
    normalize_split_prose_paragraphs,
    numeric_signature,
    sha256_text,
    split_tex_segments,
    structural_command_signature,
    table_signature,
    validate_segment_output,
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
            self.assertFalse(load_pending_review_segments(task, root))

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


if __name__ == "__main__":
    unittest.main()
