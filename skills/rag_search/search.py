"""RAG document search tools for the agent.

Provides async tool functions that search ingested documents via Milvus
vector store and return relevant chunks with source metadata.
"""

from __future__ import annotations

from typing import Any

from backend.core.config import settings
from backend.services.rag.embeddings import EmbeddingService
from backend.services.rag.retrieval import RetrievalService
from backend.services.rag.vectorstore import MilvusVectorStore as VectorStore

# ── Lazy singleton ──────────────────────────────────────────────────────────

_retrieval: RetrievalService | None = None
_vector_store: VectorStore | None = None


def _get_services() -> tuple[RetrievalService | None, VectorStore | None]:
    """Build RetrievalService + VectorStore singletons (lazy)."""
    global _retrieval, _vector_store
    if _retrieval is not None:
        return _retrieval, _vector_store
    try:
        rag_settings = settings.rag
        embed_service = EmbeddingService(settings=rag_settings)
        _vector_store = VectorStore(settings=rag_settings, embedding_service=embed_service)
        _retrieval = RetrievalService(vector_store=_vector_store, settings=rag_settings)
        return _retrieval, _vector_store
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("RAG retrieval unavailable: %s", exc)
        return None, None


# ── Tool functions ──────────────────────────────────────────────────────────


async def rag_search(
    query: str,
    collection_name: str = "documents",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search ingested documents for information relevant to the query.

    Use this tool when the user asks about content in uploaded documents
    (PDFs, DOCX, TXT, MD files). Returns a list of relevant text chunks
    with their source filename, page number, and relevance score.

    Args:
        query: The search question or keywords to look up in the documents.
        collection_name: Which document collection to search (default: "documents").
        limit: Maximum number of results to return (1-10, default: 5).

    Returns:
        A list of result dicts, each with keys:
        - content: The matching text chunk
        - score: Relevance score (0.0-1.0, higher is better)
        - filename: Source document filename
        - filetype: File type (pdf, docx, txt, md)
        - page_num: Page number in the source document (if applicable)
        - chunk_num: Chunk sequence number within the document
    """
    retrieval, _ = _get_services()
    if retrieval is None:
        return [
            {
                "content": "",
                "score": 0.0,
                "error": "RAG search is not available — check EMBEDDING_BASE_URL configuration.",
            }
        ]

    results = await retrieval.retrieve(
        query=query,
        collection_name=collection_name,
        limit=min(limit, 10),
        min_score=0.0,
    )

    return [
        {
            "content": r.content,
            "score": round(r.score, 4),
            "filename": r.metadata.get("filename", "unknown"),
            "filetype": r.metadata.get("filetype", ""),
            "page_num": r.metadata.get("page_num", 0),
            "chunk_num": r.metadata.get("chunk_num", 0),
            "source_path": r.metadata.get("source_path", ""),
        }
        for r in results
    ]


async def rag_search_by_document(
    query: str,
    filename: str,
    collection_name: str = "documents",
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Search within a specific uploaded document by filename.

    Use this when the user wants to find information in a particular file.

    Args:
        query: The search question or keywords.
        filename: The filename to restrict results to (e.g., "report.pdf").
        collection_name: Which document collection to search (default: "documents").
        limit: Maximum number of results to return (1-10, default: 3).

    Returns:
        A list of result dicts with content, score, filename, and source metadata.
    """
    retrieval, _ = _get_services()
    if retrieval is None:
        return [
            {
                "content": "",
                "score": 0.0,
                "error": "RAG search is not available — check EMBEDDING_BASE_URL configuration.",
            }
        ]

    results = await retrieval.retrieve(
        query=query,
        collection_name=collection_name,
        limit=min(limit * 3, 30),  # fetch more for post-filtering
        min_score=0.0,
    )

    # Filter results by filename
    filtered = [
        r for r in results if r.metadata.get("filename", "").lower() == filename.lower()
    ]

    return [
        {
            "content": r.content,
            "score": round(r.score, 4),
            "filename": r.metadata.get("filename", "unknown"),
            "filetype": r.metadata.get("filetype", ""),
            "page_num": r.metadata.get("page_num", 0),
            "chunk_num": r.metadata.get("chunk_num", 0),
        }
        for r in filtered[:limit]
    ]


async def rag_list_collections() -> list[str]:
    """List available document collections that can be searched.

    Returns:
        A list of collection names (e.g., ["documents"]).
    """
    try:
        rag_settings = settings.rag
        embed_service = EmbeddingService(settings=rag_settings)
        store = VectorStore(settings=rag_settings, embedding_service=embed_service)
        collections = await store.list_collections()
        return collections
    except Exception:
        return []
