#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from build_source_repair_ledger import build_ledger


class SourceRepairLedgerTests(unittest.TestCase):
    def test_explicit_rejection_precedes_shape_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            audit = root / "audit.json"
            decisions = root / "decisions.json"
            source.write_text("The valid OCR defect remains here.\n", encoding="utf-8")
            audit.write_text(
                json.dumps(
                    {
                        "repairs": [
                            {
                                "before": "valid OCR",
                                "after": "valid source",
                                "confidence": "high",
                                "category": "broken_word",
                                "reason": "verified",
                            },
                            {
                                "before": "same",
                                "after": "same",
                                "confidence": "high",
                                "category": "other",
                                "reason": "model no-op",
                            },
                            {
                                "before": "split\nline",
                                "after": "split line",
                                "confidence": "high",
                                "category": "broken_word",
                                "reason": "handled structurally",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            decisions.write_text(
                json.dumps(
                    {
                        "book_id": "fixture",
                        "rejected_repairs": [
                            {"before": "same", "after": "same", "reason": "no-op"},
                            {
                                "before": "split\nline",
                                "after": "split line",
                                "reason": "parser already joins this boundary",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            ledger = build_ledger(
                book_id="fixture",
                source_markdown=source,
                audit_paths=[audit],
                accepted={"high"},
                review_decisions=decisions,
            )
            self.assertEqual(len(ledger["repairs"]), 1)
            self.assertEqual(len(ledger["rejected_repairs"]), 2)

    def test_unused_rejection_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            audit = root / "audit.json"
            decisions = root / "decisions.json"
            source.write_text("Text.\n", encoding="utf-8")
            audit.write_text(json.dumps({"repairs": []}), encoding="utf-8")
            decisions.write_text(
                json.dumps(
                    {
                        "book_id": "fixture",
                        "rejected_repairs": [
                            {"before": "missing", "after": "fixed", "reason": "test"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "do not match"):
                build_ledger(
                    book_id="fixture",
                    source_markdown=source,
                    audit_paths=[audit],
                    accepted={"high"},
                    review_decisions=decisions,
                )

    def test_shorter_repair_can_be_superseded_by_verified_longer_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            audit = root / "audit.json"
            source.write_text("The Honnöji incident ended.\n", encoding="utf-8")
            audit.write_text(
                json.dumps(
                    {
                        "repairs": [
                            {
                                "before": "Honnöji incident",
                                "after": "Honnōji incident",
                                "confidence": "high",
                                "category": "romanization",
                                "reason": "contextual repair",
                            },
                            {
                                "before": "Honnöji",
                                "after": "Honnōji",
                                "confidence": "high",
                                "category": "romanization",
                                "reason": "generic repair",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            ledger = build_ledger(
                book_id="fixture",
                source_markdown=source,
                audit_paths=[audit],
                accepted={"high"},
            )
            self.assertEqual(len(ledger["repairs"]), 1)
            self.assertEqual(len(ledger["superseded_repairs"]), 1)


if __name__ == "__main__":
    unittest.main()
