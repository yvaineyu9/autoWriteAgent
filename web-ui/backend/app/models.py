from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


ContentStatusValue = Literal[
    "idea",
    "selected",
    "drafting",
    "draft",
    "revising",
    "final",
    "publishing",
    "published",
    "archived",
]

TaskStateValue = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class InspirationSummary(BaseModel):
    path: str
    title: str
    summary: str
    source: str | None = None
    persona: str | None = None
    platform: str | None = None
    tags: list[str] = Field(default_factory=list)
    created: str | None = None
    status: ContentStatusValue = "idea"
    content_id: str | None = None


class InspirationCreate(BaseModel):
    title: str
    body: str
    source: str = "human"
    persona: str | None = None
    platform: str | None = None
    tags: list[str] = Field(default_factory=list)


class InspirationUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    source: str | None = None
    persona: str | None = None
    platform: str | None = None
    tags: list[str] | None = None


class DraftRequest(BaseModel):
    persona: str
    platform: str
    input_text: str | None = None
    input_path: str | None = None


class ReviseRequest(BaseModel):
    instruction: str


class ContentSaveRequest(BaseModel):
    body: str
    title: str | None = None


class SelectionRequest(BaseModel):
    goal: str
    persona: str | None = None
    platform: str | None = None
    limit: int = 10


class SelectionConfirmRequest(BaseModel):
    content_ids: list[str]


class PublicationMarkPublished(BaseModel):
    post_url: str | None = None
    published_at: str | None = None


class PublicationMetricCreate(BaseModel):
    views: int = 0
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: int = 0
    notes: str | None = None


class TaskEnvelope(BaseModel):
    task_id: str
    content_id: str | None = None
    task_type: str
    status: TaskStateValue
    started_at: datetime | None = None
    ended_at: datetime | None = None


class TaskEvent(BaseModel):
    event: str
    task_id: str
    content_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
