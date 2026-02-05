from typing import Iterable

import httpx

from backend.settings import settings


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    with httpx.Client(base_url=settings.ollama_base_url, timeout=60.0) as client:
        for text in texts:
            payload = {"model": settings.embed_model, "prompt": text}
            resp = client.post("/api/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings.append(data["embedding"])
    return embeddings
