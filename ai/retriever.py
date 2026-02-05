from typing import Iterable

import chromadb

from backend.settings import settings
from ai.embeddings import embed_texts


_client = chromadb.PersistentClient(path=settings.chroma_path)


def get_collection():
    return _client.get_or_create_collection(name="documents", metadata={"hnsw:space": "cosine"})


def upsert_chunks(chunks: Iterable[dict]) -> None:
    collection = get_collection()
    chunks = list(chunks)
    if not chunks:
        return
    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(texts)
    ids = [chunk["id"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)


def query(question: str, top_k: int, where: dict | None = None) -> dict:
    collection = get_collection()
    embedding = embed_texts([question])[0]
    return collection.query(query_embeddings=[embedding], n_results=top_k, where=where)
