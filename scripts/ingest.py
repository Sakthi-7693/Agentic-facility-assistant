"""Build or rebuild the RAG vector index.

    python -m scripts.ingest
    python -m scripts.ingest --rebuild

The API also ingests on start-up, so you only need this after editing the
documents in data/knowledge_base/.
"""

from __future__ import annotations

import argparse
from collections import Counter

from app.rag.chunker import build_chunks
from app.rag.vector_store import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the facility knowledge base")
    parser.add_argument("--rebuild", action="store_true", help="delete and rebuild the index")
    args = parser.parse_args()

    chunks = build_chunks()
    print(f"\nBuilt {len(chunks)} chunks:\n")
    for source, count in sorted(Counter(c.source for c in chunks).items()):
        print(f"  {count:>3} chunks   {source}")

    store = get_vector_store()
    store.ingest(chunks, rebuild=args.rebuild)
    print(f"\nVector store now holds {store.count()} chunks.")

    print("\nSmoke test - 'what should I check if AHU airflow is low?'\n")
    for hit in store.search("what should I check if AHU airflow is low?", top_k=3):
        print(f"  {hit.vector_score:.3f}  {hit.citation}")


if __name__ == "__main__":
    main()
