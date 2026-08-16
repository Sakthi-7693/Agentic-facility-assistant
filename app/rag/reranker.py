"""Reranking - a second, sharper pass over the retrieved chunks.

Vector search compares averaged meanings, so it happily returns a chunk about
chiller filters when you asked about AHU filters. The reranker re-scores each
candidate against the exact query wording. Retrieve 8 cheaply, keep the best 4.

FlashRank (a ~4 MB ONNX cross-encoder) is used when installed. Otherwise the
lexical reranker takes over, so the project works on a clean machine.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from app.config import settings
from app.logging_setup import get_logger
from app.rag.vector_store import RetrievedChunk
from app.tracing import span

log = get_logger(__name__)

TOKEN_PATTERN = re.compile(r"[a-z0-9\-]+")

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "for",
    "and", "or", "it", "this", "that", "what", "why", "how", "do", "does", "i",
    "we", "you", "should", "can", "with", "at", "be", "my", "me", "if", "when",
}


def _tokenise(text: str) -> set[str]:
    return {
        t for t in TOKEN_PATTERN.findall(text.lower())
        if t not in STOP_WORDS and len(t) > 1
    }


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class LexicalReranker:
    """BM25-style term overlap, blended with the vector score.

    Rare terms ("inwc", "ahu-02") count for much more than common ones
    ("temperature"), which is what makes it work on technical text.
    """

    name = "lexical"
    VECTOR_WEIGHT = 0.6
    LEXICAL_WEIGHT = 0.4

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        query_terms = _tokenise(query)
        if not chunks or not query_terms:
            return chunks

        documents = [_tokenise(c.text) for c in chunks]
        idf = {
            term: math.log(1 + len(documents) / (1 + sum(term in d for d in documents)))
            for term in query_terms
        }
        max_possible = sum(idf.values()) or 1.0

        for chunk, terms in zip(chunks, documents):
            matched = sum(idf[t] for t in query_terms if t in terms)
            chunk.rerank_score = round(
                self.VECTOR_WEIGHT * chunk.vector_score
                + self.LEXICAL_WEIGHT * (matched / max_possible),
                4,
            )

        return sorted(chunks, key=lambda c: c.rerank_score, reverse=True)


class FlashRankReranker:
    """Cross-encoder reranker using FlashRank's small ONNX model."""

    name = "flashrank"

    def __init__(self) -> None:
        from flashrank import Ranker  # imported here so it stays optional

        self._ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []

        from flashrank import RerankRequest

        passages = [{"id": i, "text": c.text} for i, c in enumerate(chunks)]
        results = self._ranker.rerank(RerankRequest(query=query, passages=passages))

        ordered = []
        for result in results:
            chunk = chunks[int(result["id"])]
            chunk.rerank_score = round(float(result["score"]), 4)
            ordered.append(chunk)
        return ordered


class NoOpReranker:
    """Keeps the vector order. Set RERANKER=none to measure the reranker's value."""

    name = "none"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        for chunk in chunks:
            chunk.rerank_score = chunk.vector_score
        return chunks


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is not None:
        return _reranker

    choice = settings.reranker.lower()
    if choice == "none":
        _reranker = NoOpReranker()
    elif choice in {"flashrank", "auto"}:
        try:
            _reranker = FlashRankReranker()
        except Exception as exc:  # noqa: BLE001
            if choice == "flashrank":
                log.warning("FlashRank unavailable (%s) - using lexical.", exc)
            _reranker = LexicalReranker()
    else:
        _reranker = LexicalReranker()

    log.info("Reranker: %s", _reranker.name)
    return _reranker


def rerank_chunks(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    with span("rag.rerank", input={"query": query, "candidates": len(chunks)}):
        return get_reranker().rerank(query, chunks)[: settings.rerank_top_n]
