from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pocketpolyglot_studio.capabilities import build_job_spec, list_capabilities
from pocketpolyglot_studio.config import Settings
from pocketpolyglot_studio.db import Database
from pocketpolyglot_studio.evidence import evaluate_all
from pocketpolyglot_studio.model_router import choose_model
from pocketpolyglot_studio.workflows import default_pipeline


class StudioCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "studio/web/dist").mkdir(parents=True)
        state = root / ".studio"
        self.settings = Settings(
            repo_root=root,
            state_root=state,
            database_path=state / "studio.sqlite3",
            projects_root=state / "projects",
            jobs_root=state / "jobs",
            uploads_root=state / "uploads",
            web_dist=root / "studio/web/dist",
            chat_model="gpt-5.6-sol",
            worker_model="gpt-5.6-sol",
            default_reasoning="low",
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_project(self, workflow: str = "lingualeaf", primary_language: str = "en") -> dict:
        return self.database.create_project(
            {
                "title": "Test Book",
                "book_id": "test-book",
                "workflow": workflow,
                "source_language": primary_language,
                "primary_language": primary_language,
                "target_languages": ["ja", "zh"],
            }
        )

    def test_project_round_trip_and_unique_slug(self) -> None:
        first = self.create_project()
        second = self.create_project()
        self.assertEqual(first["slug"], "test-book")
        self.assertEqual(second["slug"], "test-book-2")
        self.assertEqual(first["target_languages"], ["ja", "zh"])
        self.assertEqual(len(self.database.list_projects()), 2)

    def test_model_router_defaults_low_and_escalates_audits(self) -> None:
        fast = choose_model(self.settings, "What is the progress?", "auto")
        ultra = choose_model(self.settings, "Perform a final audit and prove correctness", "auto")
        self.assertEqual((fast.model, fast.reasoning), ("gpt-5.6-sol", "low"))
        self.assertEqual(ultra.reasoning, "xhigh")

    def test_evidence_requires_exit_and_artifact(self) -> None:
        artifact = self.settings.repo_root / "output.json"
        artifact.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        evidence = evaluate_all(
            self.settings.repo_root,
            [
                {"type": "path_exists", "label": "Artifact", "path": "output.json"},
                {"type": "json_field", "label": "Accepted", "path": "output.json", "field": "status", "equals": "complete"},
            ],
            0,
        )
        self.assertTrue(all(item["passed"] for item in evidence))
        rejected = evaluate_all(self.settings.repo_root, [], 1)
        self.assertFalse(rejected[0]["passed"])

    def test_capability_builds_real_pocket_polish_command(self) -> None:
        project = self.create_project("pocket_polished")
        spec = build_job_spec(self.settings, project, "pocket.polish.run", {"workers": 5})
        self.assertIn("scripts/books/run_build_pocket_polished_queue.py", spec.command)
        self.assertIn("5", spec.command)
        self.assertTrue(any(check["type"] == "json_field" for check in spec.acceptance))

    def test_queue_capability_exposes_progress_and_adaptive_workers(self) -> None:
        project = self.create_project("custom")
        spec = build_job_spec(
            self.settings,
            project,
            "pocket.polish.queue",
            {"workers": 5, "network_limit_mbps": 75},
        )
        self.assertIn("pocket-polish-queue", spec.command)
        self.assertIn("5", spec.command)
        self.assertIn("75.0", spec.command)
        self.assertTrue(spec.environment["POCKETPOLYGLOT_PROGRESS_PATH"].endswith("status-studio-technical-seven.json"))

    def test_default_pipeline_uses_wenyan_lingualeaf_adapter(self) -> None:
        project = self.create_project("lingualeaf", "wenyan")
        pipeline = default_pipeline(self.settings, project)
        self.assertEqual([stage["id"] for stage in pipeline["stages"]], ["generate", "compile", "export"])
        self.assertIn("lingualeaf-generate", pipeline["stages"][0]["argv"])

    def test_registry_covers_all_workflow_families(self) -> None:
        identifiers = {item["id"] for item in list_capabilities()}
        self.assertTrue(
            {
                "source.inspect",
                "project.prepare",
                "lingualeaf.generate",
                "pocket.exact",
                "pocket.polish.run",
                "pocket.polish.queue",
                "project.validate",
                "cover.generate",
                "export.nutstore",
            }.issubset(identifiers)
        )


if __name__ == "__main__":
    unittest.main()
