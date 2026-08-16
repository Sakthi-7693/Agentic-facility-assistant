"""Vector database (ChromaDB).

Chroma embeds locally with a bundled ONNX MiniLM model - no server, no account,
no cost, no GPU. Only this file imports chromadb, so swapping to Qdrant or
pgvector means rewriting this file alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import VECTOR_STORE_DIR, settings
from app.logging_setup import get_logger
from app.rag.chunker import Chunk, build_chunks
from app.tracing import span, update_span

log = get_logger(__name__)

COLLECTION_NAME = "facility_knowledge_base"


@dataclass
class RetrievedChunk:
    text: str
    source: str
    section: str
    vector_score: float  # 0..1, higher is better
    rerank_score: float = 0.0

    @property
    def citation(self) -> str:
        return f"{self.source} > {self.section}"


class VectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=str(VECTOR_STORE_DIR),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._new_collection()

    def _new_collection(self):
        # Cosine distance suits normalised sentence embeddings.
        return self._client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._collection.count()

    def ingest(self, chunks: list[Chunk] | None = None, rebuild: bool = False) -> int:
        """Safe to call on every start-up - returns immediately if already built."""
        if rebuild:
            log.info("Rebuilding vector store from scratch")
            self._client.delete_collection(COLLECTION_NAME)
            self._collection = self._new_collection()
        elif self.count() > 0:
            log.info("Vector store already contains %d chunks - skipping", self.count())
            return self.count()

        chunks = chunks or build_chunks()
        self._collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"source": c.source, "section": c.section} for c in chunks],
        )
        log.info("Indexed %d chunks", len(chunks))
        return len(chunks)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or settings.retrieve_top_k

        with span("rag.vector_search", input={"query": query, "top_k": top_k}):
            if self.count() == 0:
                log.warning("Vector store is empty - run scripts/ingest.py")
                return []

            raw: dict[str, Any] = self._collection.query(
                query_texts=[query], n_results=min(top_k, self.count())
            )
            hits = [
                RetrievedChunk(
                    text=document,
                    source=metadata.get("source", "unknown"),
                    section=metadata.get("section", ""),
                    # Cosine distance: 0 = identical, 2 = opposite.
                    vector_score=max(0.0, 1.0 - float(distance)),
                )
                for document, metadata, distance in zip(
                    raw["documents"][0], raw["metadatas"][0], raw["distances"][0]
                )
            ]

            update_span(output={"hits": [h.citation for h in hits]})
            return hits


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
