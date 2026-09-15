"""Persistent Chroma collection for semantic (embedding) search. FR-7."""
from typing import Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

_client = chromadb.PersistentClient(path=settings.vector_store_dir)
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=settings.embedding_model
)
_collection = _client.get_or_create_collection(
    name="shariah_documents",
    embedding_function=_embedding_fn,
    metadata={"hnsw:space": "cosine"},
)


def upsert_chunks(chunk_ids: List[str], texts: List[str], metadatas: List[Dict]) -> None:
    _collection.upsert(ids=chunk_ids, documents=texts, metadatas=metadatas)


def delete_document_chunks(chunk_ids: List[str]) -> None:
    if chunk_ids:
        _collection.delete(ids=chunk_ids)


def semantic_search(query: str, top_k: int, where: Optional[Dict] = None) -> List[Dict]:
    """Returns list of {chunk_id, text, metadata, distance}."""
    result = _collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where or None,
    )
    hits = []
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    for i in range(len(ids)):
        hits.append({
            "chunk_id": ids[i],
            "text": docs[i],
            "metadata": metas[i],
            "distance": dists[i],
        })
    return hits
