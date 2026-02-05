import math
import re
from statistics import mean

from sqlalchemy.orm import Session

from ai.embeddings import embed_texts
from backend.models import Answer, Evaluation, EvaluationStatus, Project, ProjectStatus


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _keyword_overlap(a: str, b: str) -> float:
    tokens_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def evaluate_project(db: Session, project_id: str, ground_truth: list[dict]) -> Evaluation:
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found")

    project.status = ProjectStatus.EVALUATING
    db.commit()

    evaluation = Evaluation(project_id=project_id, status=EvaluationStatus.PENDING)
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    gt_map = {item["question_id"]: item["answer_text"] for item in ground_truth}

    per_question = []
    semantic_scores = []
    keyword_scores = []

    for question in project.questions:
        answer: Answer | None = question.answers[0] if question.answers else None
        ai_text = (answer.ai_answer_text or "") if answer else ""
        human_text = gt_map.get(question.id, "")

        embeddings = embed_texts([ai_text, human_text])
        sem_sim = _cosine_similarity(embeddings[0], embeddings[1])
        key_sim = _keyword_overlap(ai_text, human_text)
        score = round(0.7 * sem_sim + 0.3 * key_sim, 3)

        per_question.append({
            "question_id": question.id,
            "semantic_similarity": round(sem_sim, 3),
            "keyword_overlap": round(key_sim, 3),
            "score": score,
            "ai_answer": ai_text,
            "human_answer": human_text,
        })

        semantic_scores.append(sem_sim)
        keyword_scores.append(key_sim)

    metrics = {
        "per_question": per_question,
        "aggregate": {
            "semantic_similarity_avg": round(mean(semantic_scores), 3) if semantic_scores else 0.0,
            "keyword_overlap_avg": round(mean(keyword_scores), 3) if keyword_scores else 0.0,
            "overall_score": round(mean([q["score"] for q in per_question]), 3) if per_question else 0.0,
        },
    }

    evaluation.metrics = metrics
    evaluation.status = EvaluationStatus.COMPLETED
    project.status = ProjectStatus.EVALUATED
    db.commit()

    return evaluation
