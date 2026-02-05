import uuid
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from backend.settings import settings
from backend.services.ingestion import extract_pages
from backend.services.storage import save_upload_file


def parse_questionnaire_text(text: str) -> list[dict]:
    questions: list[dict] = []
    current_section: str | None = None
    order_index = 1

    cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in cleaned_lines:
        if line.lower().startswith("section:"):
            current_section = line.split(":", 1)[1].strip() or current_section
            continue

        if line.startswith("#"):
            current_section = line.lstrip("#").strip() or current_section
            continue

        questions.append({
            "section": current_section,
            "order_index": order_index,
            "text": line,
        })
        order_index += 1

    if questions:
        return questions

    # Fallback: if everything was treated as a section header, treat those lines as questions.
    order_index = 1
    for line in cleaned_lines:
        if line.lower().startswith("section:"):
            candidate = line.split(":", 1)[1].strip()
        elif line.startswith("#"):
            candidate = line.lstrip("#").strip()
        else:
            candidate = line
        if not candidate:
            continue
        questions.append({
            "section": None,
            "order_index": order_index,
            "text": candidate,
        })
        order_index += 1

    return questions


def parse_questionnaire_file(upload: UploadFile) -> list[dict]:
    dest_dir = Path(settings.storage_path).parent / "questionnaires"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4()}_{upload.filename}"
    save_upload_file(upload, dest)

    pages = extract_pages(dest)
    full_text = "\n".join(page.get("text", "") for page in pages)
    return parse_questionnaire_text(full_text)
