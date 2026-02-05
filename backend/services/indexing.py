from sqlalchemy.orm import Session

from ai.retriever import upsert_chunks
from backend.models import AnswerStatus, Project, ProjectScope, ProjectStatus


def index_chunks(db: Session, document, chunk_models) -> None:
    payload = []
    for chunk in chunk_models:
        payload.append({
            "id": chunk.id,
            "text": chunk.text,
            "metadata": {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "page": chunk.page,
                "bbox": chunk.bbox,
            },
        })
    upsert_chunks(payload)


def mark_all_docs_outdated(db: Session) -> None:
    projects = db.query(Project).filter(Project.scope == ProjectScope.ALL_DOCS).all()
    for project in projects:
        project.status = ProjectStatus.OUTDATED
        for question in project.questions:
            for answer in question.answers:
                if answer.status == AnswerStatus.GENERATED:
                    answer.status = AnswerStatus.STALE
    db.commit()
