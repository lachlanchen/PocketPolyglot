from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pocketpolyglot_studio.browser_control import BrowserConfig, summarize_progress
from pocketpolyglot_studio.config import Settings


class BrowserControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
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

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_browser_config_persists_and_reuses_identity(self) -> None:
        profile = Path(self.temporary.name) / "profile"
        configured = BrowserConfig.load(
            self.settings,
            {
                "studio_url": "http://127.0.0.1:8766",
                "display": ":95",
                "vnc_port": 5925,
                "novnc_port": 6125,
                "cdp_port": 9365,
                "profile": profile,
            },
        )
        configured.save()
        reused = BrowserConfig.load(self.settings)
        self.assertEqual(reused, configured)
        self.assertIn("127.0.0.1:6125", reused.novnc_url)
        self.assertIn("autoconnect=1", reused.novnc_url)

    def test_browser_config_rejects_port_collision(self) -> None:
        with self.assertRaises(ValueError):
            BrowserConfig.load(self.settings, {"vnc_port": 6000, "novnc_port": 6000})

    def test_progress_summary_keeps_runtime_health(self) -> None:
        summary = summarize_progress(
            {
                "inspected_at": "2026-07-15T00:00:00Z",
                "selected_project": "Technical Queue",
                "active_jobs": [
                    {
                        "id": "job-1",
                        "title": "Polish",
                        "status": "running",
                        "heartbeat_at": "now",
                        "progress_detail": {
                            "progress": 0.25,
                            "accepted_segments": 25,
                            "total_segments": 100,
                            "current_book": "book-a",
                            "books": {
                                "book-a": {
                                    "progress": 0.5,
                                    "valid_chunks": 10,
                                    "total_chunks": 20,
                                    "invalid_chunks": 1,
                                    "failed_chunks": 2,
                                }
                            },
                            "runtime": {
                                "active_codex_calls": 5,
                                "desired_concurrency": 5,
                                "network_mbps": 3.2,
                                "jammed": False,
                            },
                        },
                    }
                ],
            }
        )
        self.assertEqual(summary["jobs"][0]["accepted_segments"], 25)
        self.assertEqual(summary["jobs"][0]["active_codex_calls"], 5)
        self.assertEqual(summary["jobs"][0]["current_book_valid_chunks"], 10)
        self.assertEqual(summary["jobs"][0]["health"], "healthy")
        self.assertFalse(summary["jobs"][0]["jammed"])


if __name__ == "__main__":
    unittest.main()
