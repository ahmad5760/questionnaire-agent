from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.db import Base, SessionLocal, engine, get_db
from backend.models import (
    Answer,
    AnswerStatus,
    Document,
    DocumentStatus,
    Project,
    ProjectDocument,
    ProjectScope,
    ProjectStatus,
    Question,
)
from backend.schemas import (
    AnswerOut,
    ChatRequest,
    ChatResponse,
    DocumentOut,
    EvaluationRequest,
    EvaluationResponse,
    GenerateResponse,
    ProjectCreateResponse,
    ProjectOut,
    ProjectUpdate,
    QuestionOut,
    ReviewUpdate,
)
from backend.services.evaluation import evaluate_project
from backend.services.ingestion import process_document
from backend.services.qa import build_prompt, generate_answers_for_project
from backend.services.questionnaires import parse_questionnaire_file, parse_questionnaire_text
from backend.services.storage import save_upload_file
from backend.settings import settings
from ai.llm import generate_answer
from ai.retriever import query

app = FastAPI(title="Questionnaire Agent")

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse("frontend/index.html")


def _process_document_task(document_id: str) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc:
            process_document(db, doc)
    finally:
        db.close()


def _generate_answers_task(project_id: str) -> None:
    db = SessionLocal()
    try:
        generate_answers_for_project(db, project_id)
    finally:
        db.close()


@app.post("/documents", response_model=DocumentOut)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    doc = Document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.UPLOADED,
        storage_path="",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    dest = Path(settings.storage_path) / f"{doc.id}_{file.filename}"
    save_upload_file(file, dest)
    doc.storage_path = str(dest)
    db.commit()

    background_tasks.add_task(_process_document_task, doc.id)
    return doc


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@app.post("/projects", response_model=ProjectCreateResponse)
def create_project(
    background_tasks: BackgroundTasks,
    name: Annotated[str, Form(...)],
    scope: Annotated[ProjectScope, Form(...)] = ProjectScope.ALL_DOCS,
    description: Annotated[str | None, Form()] = None,
    document_ids: Annotated[str | None, Form(...)] = None,
    auto_generate: Annotated[bool, Form(...)] = True,
    questionnaire_text: Annotated[str | None, Form(...)] = None,
    questionnaire: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> ProjectCreateResponse:
    project = Project(name=name, description=description, scope=scope, status=ProjectStatus.PARSING)
    db.add(project)
    db.commit()
    db.refresh(project)

    if scope == ProjectScope.SELECTED_DOCS and document_ids:
        for doc_id in [d.strip() for d in document_ids.split(",") if d.strip()]:
            db.add(ProjectDocument(project_id=project.id, document_id=doc_id))
        db.commit()

    cleaned_text = (questionnaire_text or "").strip()
    if cleaned_text:
        parsed_questions = parse_questionnaire_text(cleaned_text)
    elif questionnaire is not None:
        parsed_questions = parse_questionnaire_file(questionnaire)
    else:
        raise HTTPException(status_code=400, detail="Questionnaire text is required.")
    questions_created = 0
    for q in parsed_questions:
        question = Question(
            project_id=project.id,
            section=q["section"],
            order_index=q["order_index"],
            text=q["text"],
        )
        db.add(question)
        db.flush()
        db.add(Answer(question_id=question.id, status=AnswerStatus.PENDING))
        questions_created += 1
    db.commit()

    project.status = ProjectStatus.READY
    db.commit()

    if auto_generate:
        background_tasks.add_task(_generate_answers_task, project.id)

    return ProjectCreateResponse(project=project, questions_created=questions_created)


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.config is not None:
        project.config = payload.config

    if payload.scope is not None:
        project.scope = payload.scope

    if payload.document_ids is not None:
        db.query(ProjectDocument).filter(ProjectDocument.project_id == project_id).delete()
        for doc_id in payload.document_ids:
            db.add(ProjectDocument(project_id=project_id, document_id=doc_id))

    project.status = ProjectStatus.OUTDATED
    for question in project.questions:
        for answer in question.answers:
            answer.status = AnswerStatus.STALE

    db.commit()

    if payload.auto_regenerate:
        background_tasks.add_task(_generate_answers_task, project.id)

    return project


@app.post("/projects/{project_id}/generate", response_model=GenerateResponse)
def generate_project_answers(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = ProjectStatus.GENERATING
    db.commit()
    background_tasks.add_task(_generate_answers_task, project.id)
    return GenerateResponse(project_id=project.id, status=project.status)


@app.get("/projects/{project_id}/questions", response_model=list[QuestionOut])
def list_questions(project_id: str, db: Session = Depends(get_db)) -> list:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.questions


@app.get("/projects/{project_id}/answers", response_model=list[AnswerOut])
def list_answers(project_id: str, db: Session = Depends(get_db)) -> list:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    answers = []
    for question in project.questions:
        answers.extend(question.answers)
    return answers


@app.patch("/answers/{answer_id}/review", response_model=AnswerOut)
def review_answer(answer_id: str, payload: ReviewUpdate, db: Session = Depends(get_db)) -> Answer:
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer.status = payload.status
    answer.manual_answer_text = payload.manual_answer_text
    answer.manual_answerable = payload.manual_answerable
    answer.manual_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(answer)
    return answer


@app.post("/projects/{project_id}/evaluate", response_model=EvaluationResponse)
def evaluate(project_id: str, payload: EvaluationRequest, db: Session = Depends(get_db)) -> EvaluationResponse:
    evaluation = evaluate_project(db, project_id, payload.ground_truth)
    return EvaluationResponse(evaluation=evaluation)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    results = query(payload.query, settings.top_k)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not documents:
        return ChatResponse(answer_text="No relevant documents found.", answerable=False, confidence=0.0, citations=[])

    confidence = sum(max(0.0, 1.0 - d) for d in distances) / max(1, len(distances))
    citations = []
    for meta, dist, text in zip(metadatas, distances, documents):
        citations.append({
            "chunk_id": meta.get("chunk_id"),
            "document_id": meta.get("document_id"),
            "page": meta.get("page"),
            "bbox": meta.get("bbox"),
            "similarity": round(max(0.0, 1.0 - dist), 3),
            "text_snippet": text[:240],
        })

    prompt = build_prompt(payload.query, documents)
    answer_text = generate_answer(prompt)

    return ChatResponse(
        answer_text=answer_text,
        answerable=True,
        confidence=round(confidence, 3),
        citations=citations,
    )


