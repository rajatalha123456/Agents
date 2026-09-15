"""Keyword search side of the hybrid retriever. FR-7.

Simple, dependency-light approach: rebuild a BM25 index on the fly from whatever
chunk set the DB filters (FR-9) already narrowed down to. Fine at internal-tool
query volumes; swap for a persisted BM25/Elasticsearch index if corpus grows large.
"""
from typing import List

from rank_bm25 import BM25Okapi

from app.models.document import DocumentChunk


def keyword_search(query: str, candidate_chunks: List[DocumentChunk], top_k: int) -> List[DocumentChunk]:
    if not candidate_chunks:
        return []

    tokenized_corpus = [_tokenize(c.text) for c in candidate_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))

    ranked = sorted(zip(candidate_chunks, scores), key=lambda x: x[1], reverse=True)
    return [chunk for chunk, score in ranked[:top_k] if score > 0]


def _tokenize(text: str) -> List[str]:
    return text.lower().split()
