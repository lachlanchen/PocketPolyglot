from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Workflow = Literal["lingualeaf", "pocket_exact", "pocket_polished", "custom"]


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = ""
    workflow: Workflow = "lingualeaf"
    book_id: str = ""
    source_language: str = "en"
    primary_language: str = "en"
    target_languages: list[str] = Field(default_factory=lambda: ["ja", "zh"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    title: str | None = None
    workflow: Workflow | None = None
    book_id: str | None = None
    source_language: str | None = None
    primary_language: str | None = None
    target_languages: list[str] | None = None
    metadata: dict[str, Any] | None = None
    status: str | None = None


class SourceRegister(BaseModel):
    path: str
    role: str = "reference"
    language: str = ""


class JobLaunch(BaseModel):
    capability_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    project_id: str
    message: str = Field(min_length=1)
    profile: Literal["auto", "fast", "balanced", "deep", "ultra"] = "auto"
    agent_mode: bool = True


class PipelineUpdate(BaseModel):
    pipeline: dict[str, Any]
