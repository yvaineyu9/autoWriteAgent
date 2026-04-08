from pydantic import BaseModel
from typing import Optional


# --- Response ---

class IdeaOut(BaseModel):
    id: str
    title: str
    tags: Optional[str] = None
    source: str
    status: str
    created_at: str
    updated_at: str


class ContentOut(BaseModel):
    content_id: str
    title: str
    persona_id: str
    platform: str
    status: str
    review_score: Optional[int] = None
    review_json: Optional[str] = None
    source_idea: Optional[str] = None
    created_at: str
    updated_at: str


class ContentBodyOut(BaseModel):
    content_id: str
    title: str
    body: str
    platform: str


class MetricsOut(BaseModel):
    views: int
    likes: int
    collects: int
    comments: int
    shares: int
    captured_at: str


class PublicationOut(BaseModel):
    id: int
    content_id: str
    persona_id: str
    platform: str
    status: str
    post_url: Optional[str] = None
    published_at: Optional[str] = None
    created_at: str
    content_title: Optional[str] = None
    latest_metrics: Optional[MetricsOut] = None


class TaskStatus(BaseModel):
    task_id: str
    task_type: str
    status: str
    current_step: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: str
    updated_at: str


# --- Request ---

class CreateArticleRequest(BaseModel):
    idea_id: str
    platform: str


class ReviseContentRequest(BaseModel):
    content_id: str
    feedback: str


class RecordMetricsRequest(BaseModel):
    views: int = 0
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: int = 0


class SaveContentBodyRequest(BaseModel):
    body: str


class TypesetRequest(BaseModel):
    tool: str = "v2"  # "v1" or "v2"
    cover_url: Optional[str] = None
    avatar_url: Optional[str] = None


class CreateIdeaRequest(BaseModel):
    title: str
    content: str
    tags: str = ""


class UpdateIdeaRequest(BaseModel):
    title: str
    content: str
    tags: str = ""


class CollectIdeasRequest(BaseModel):
    source: str  # URL, text, or keywords


class ExpandIdeaRequest(BaseModel):
    idea_id: str
    instruction: str  # what to research/expand


class UpdatePublicationRequest(BaseModel):
    status: str
    post_url: Optional[str] = None
