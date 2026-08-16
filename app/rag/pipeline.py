"""The RAG pipeline.

    query -> vector search -> rerank -> relevance gate -> grounded answer

Two independent guards stop the model inventing facts:
  1. Numeric gate  - best score below MIN_RELEVANCE_SCORE, refuse without an LLM call.
  2. Prompt gate   - the LLM may reply INSUFFICIENT_CONTEXT.

Either alone leaks. Together, refusal is the default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings
from app.llm.client import get_llm
from app.llm.models import ModelTier
from app.logging_setup import get_logger
from app.rag.reranker import rerank_chunks
from app.rag.vector_store import RetrievedChunk, get_vector_store
from app.tracing import traced, update_span

log = get_logger(__name__)

INSUFFICIENT = "INSUFFICIENT_CONTEXT"

NOT_FOUND_REPLY = (
    "I could not find that in the facility documentation. "
    "The knowledge base covers HVAC procedures, chiller and AHU manuals, "
    "maintenance, safety and facility policies. "
    "Would you like me to check the live building data instead?"
)

ANSWER_PROMPT = """You are a facility operations assistant answering from official documentation.

RULES
1. Use ONLY the numbered passages below. Never add outside knowledge.
2. If the passages do not contain the answer, reply with exactly: {insufficient}
3. Keep the answer under 80 words - it will be spoken aloud.
4. Do not read out document IDs or passage numbers.
5. Give concrete steps or numbers when the passages contain them.

PASSAGES
{context}

QUESTION
{question}

ANSWER:"""


@dataclass
class GroundedAnswer:
    answer: str
    sources: list[str] = field(default_factory=list)
    chunks: list[RetrievedChunk] = field(default_factory=list)
    found: bool = True
    top_score: float = 0.0

    def as_dict(self) -> dict:
        """Compact form, used when RAG is called as a tool by the agent."""
        return {
            "answer": self.answer,
            "sources": self.sources,
            "found": self.found,
            "top_score": self.top_score,
        }


class RAGPipeline:
    def __init__(self) -> None:
        self._store = get_vector_store()

    @traced("rag.retrieve")
    def retrieve(self, query: str) -> list[RetrievedChunk]:
        return rerank_chunks(query, self._store.search(query))

    @traced("rag.answer")
    async def answer(self, question: str) -> GroundedAnswer:
        chunks = self.retrieve(question)
        top_score = chunks[0].rerank_score if chunks else 0.0

        if not chunks or top_score < settings.min_relevance_score:
            log.info("Relevance gate rejected the query (score %.3f)", top_score)
            update_span(output={"found": False, "top_score": top_score})
            return GroundedAnswer(NOT_FOUND_REPLY, found=False, top_score=top_score, chunks=chunks)

        # Drop the chunks that did not clear the gate. Passing a near-irrelevant
        # passage to the LLM invites it to cite something it never used.
        chunks = [c for c in chunks if c.rerank_score >= settings.min_relevance_score]

        context = "\n\n".join(
            f"[{i + 1}] (source: {c.citation})\n{c.text}" for i, c in enumerate(chunks)
        )
        response = await get_llm().chat(
            [
                {
                    "role": "user",
                    "content": ANSWER_PROMPT.format(
                        insufficient=INSUFFICIENT, context=context, question=question
                    ),
                }
            ],
            tier=ModelTier.FAST,  # grounded summarising does not need the big model
            temperature=0.1,
        )

        if INSUFFICIENT in response.content.upper():
            update_span(output={"found": False, "reason": "model_declared_insufficient"})
            return GroundedAnswer(NOT_FOUND_REPLY, found=False, top_score=top_score, chunks=chunks)

        seen: set[str] = set()
        sources = [c.citation for c in chunks if not (c.citation in seen or seen.add(c.citation))]

        update_span(output={"found": True, "sources": sources})
        return GroundedAnswer(response.content, sources, chunks, True, top_score)


_pipeline: RAGPipeline | None = None


def get_rag() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
