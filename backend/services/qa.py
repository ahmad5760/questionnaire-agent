from statistics import mean

from sqlalchemy.orm import Session

from ai.llm import generate_answer
from ai.retriever import query
from backend.models import Answer, AnswerStatus, Project, ProjectScope, ProjectStatus
from backend.settings import settings


def build_prompt(question: str, contexts: list[str]) -> str:
    joined = "\n\n".join(contexts)
    return (
        "You are answering a questionnaire using the provided context. "
        "If the context does not contain the answer, say that it is not available. "
        "Provide a concise answer without citations or markdown.\n\n"
        f"Question: {question}\n\n"
        f"Context:\n{joined}\n\n"
        "Answer:"
    )


def _confidence_from_distances(distances: list[float]) -> float:
    if not distances:
        return 0.0
    sims = [max(0.0, 1.0 - d) for d in distances]
    avg = mean(sims)
    return round(min(1.0, max(0.0, avg)), 3)


def _prepare_citations(metadatas: list[dict], distances: list[float], documents: list[str]) -> list[dict]:
    citations: list[dict] = []
    for meta, dist, text in zip(metadatas, distances, documents):
        citations.append({
            "chunk_id": meta.get("chunk_id"),
            "document_id": meta.get("document_id"),
            "page": meta.get("page"),
            "bbox": meta.get("bbox"),
            "similarity": round(max(0.0, 1.0 - dist), 3),
            "text_snippet": text[:240],
        })
    return citations


def generate_answers_for_project(db: Session, project_id: str) -> None:
    project = db.get(Project, project_id)
    if project is None:
        return

    project.status = ProjectStatus.GENERATING
    db.commit()

    where = None
    if project.scope == ProjectScope.SELECTED_DOCS:
        doc_ids = [pd.document_id for pd in project.documents]
        where = {"document_id": {"$in": doc_ids}} if doc_ids else {"document_id": "__none__"}

    for question in project.questions:
        results = query(question.text, settings.top_k, where=where)
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        answer = question.answers[0] if question.answers else Answer(question_id=question.id)
        if not question.answers:
            db.add(answer)

        if not ids:
            answer.status = AnswerStatus.MISSING_DATA
            answer.ai_answer_text = "No relevant documents found."
            answer.ai_answerable = False
            answer.ai_confidence = 0.0
            answer.ai_citations = []
            continue

        confidence = _confidence_from_distances(distances)
        answerable = confidence >= settings.min_similarity

        if not answerable:
            answer.status = AnswerStatus.MISSING_DATA
            answer.ai_answer_text = "Insufficient evidence to answer from the indexed documents."
            answer.ai_answerable = False
            answer.ai_confidence = confidence
            answer.ai_citations = _prepare_citations(metadatas, distances, documents)
            continue

        prompt = build_prompt(question.text, documents)
        response = generate_answer(prompt)

        answer.status = AnswerStatus.GENERATED
        answer.ai_answer_text = response
        answer.ai_answerable = True
        answer.ai_confidence = confidence
        answer.ai_citations = _prepare_citations(metadatas, distances, documents)

    project.status = ProjectStatus.REVIEW
    db.commit()
