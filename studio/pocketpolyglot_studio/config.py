from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
STUDIO_ROOT = PACKAGE_ROOT.parent
DEFAULT_REPO_ROOT = STUDIO_ROOT.parent


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    state_root: Path
    database_path: Path
    projects_root: Path
    jobs_root: Path
    uploads_root: Path
    web_dist: Path
    chat_model: str
    worker_model: str
    default_reasoning: str

    @classmethod
    def load(cls) -> "Settings":
        repo_root = Path(os.environ.get("POCKETPOLYGLOT_ROOT", DEFAULT_REPO_ROOT)).expanduser().resolve()
        state_root = Path(
            os.environ.get("POCKETPOLYGLOT_STATE", repo_root / ".pocketpolyglot-studio")
        ).expanduser().resolve()
        settings = cls(
            repo_root=repo_root,
            state_root=state_root,
            database_path=state_root / "studio.sqlite3",
            projects_root=state_root / "projects",
            jobs_root=state_root / "jobs",
            uploads_root=state_root / "uploads",
            web_dist=STUDIO_ROOT / "web" / "dist",
            chat_model=os.environ.get("POCKETPOLYGLOT_CHAT_MODEL", "gpt-5.6-sol"),
            worker_model=os.environ.get("POCKETPOLYGLOT_WORKER_MODEL", "gpt-5.6-sol"),
            default_reasoning=os.environ.get("POCKETPOLYGLOT_REASONING", "low"),
        )
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        for path in (self.state_root, self.projects_root, self.jobs_root, self.uploads_root):
            path.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        path = self.projects_root / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_root(self, job_id: str) -> Path:
        path = self.jobs_root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path
