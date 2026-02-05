from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from .models import AnswerStatus, DocumentStatus, EvaluationStatus, ProjectScope, ProjectStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentOut(ORMModel):
    id: str
    filename: str
    content_type: str
    status: DocumentStatus
    created_at: datetime


class ProjectOut(ORMModel):
    id: str
    name: str
    description: str | None
    scope: ProjectScope
    status: ProjectStatus
    config: dict
    created_at: datetime
    updated_at: datetime


class QuestionOut(ORMModel):
    id: str
    project_id: str
    section: str | None
    order_index: int
    text: str


class AnswerOut(ORMModel):
    id: str
    question_id: str
    status: AnswerStatus
    ai_answer_text: str | None
    ai_answerable: bool | None
    ai_confidence: float | None
    ai_citations: list | None
    manual_answer_text: str | None
    manual_answerable: bool | None
    manual_updated_at: datetime | None
    updated_at: datetime


class EvaluationOut(ORMModel):
    id: str
    project_id: str
    status: EvaluationStatus
    metrics: dict | None
    created_at: datetime


class ReviewUpdate(BaseModel):
    status: AnswerStatus
    manual_answer_text: str | None = None
    manual_answerable: bool | None = None


class ProjectCreateResponse(BaseModel):
    project: ProjectOut
    questions_created: int


class GenerateResponse(BaseModel):
    project_id: str
    status: ProjectStatus


class ProjectUpdate(BaseModel):
    config: dict | None = None
    scope: ProjectScope | None = None
    document_ids: list[str] | None = None
    auto_regenerate: bool = False


class EvaluationRequest(BaseModel):
    ground_truth: list[dict] = Field(..., description="List of {question_id, answer_text}")


class EvaluationResponse(BaseModel):
    evaluation: EvaluationOut


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer_text: str
    answerable: bool
    confidence: float
    citations: list


class StatusResponse(BaseModel):
    status: ProjectStatus
    detail: str | None = None
