"""RAG API routes — collections, search, documents, upload, sync, SSE status.

All endpoints are prefixed with ``/api/rag``.
Authentication is optional for search; admin/owner checks apply on mutations.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.dependencies import get_db_session
from backend.schemas.rag import (
    RAGCollectionInfo,
    RAGCollectionList,
    RAGDocumentList,
    RAGIngestResponse,
    RAGMessageResponse,
    RAGRetryResponse,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSyncLogList,
    RAGSyncRequest,
    RAGSyncResponse,
    RAGTrackedDocumentList,
)
from backend.schemas.sync_source import (
    ConnectorList,
    SyncSourceCreate,
    SyncSourceList,
    SyncSourceRead,
    SyncSourceUpdate,
)
from backend.services.rag.embeddings import EmbeddingService
from backend.services.rag.vectorstore import MilvusVectorStore as VectorStore
from backend.services.rag.retrieval import RetrievalService
from backend.services.rag.ingestion import IngestionService
from backend.services.rag.documents import DocumentProcessor
from backend.services.rag_document import RAGDocumentService
from backend.services.rag_sync import RAGSyncService
from backend.services.rag_status import RAGStatusService
from backend.services.sync_source import SyncSourceService
from backend.rag.connectors import CONNECTOR_REGISTRY

router = APIRouter(prefix="/api/rag", tags=["rag"])

# ── Vector store helpers (lazily initialised) ─────────────────────────────


def _get_vector_store() -> VectorStore:
    """Return a shared VectorStore instance for route handlers."""
    rag_settings = settings.rag
    embed_service = EmbeddingService(settings=rag_settings)
    return VectorStore(settings=rag_settings, embedding_service=embed_service)


def _get_ingestion_service() -> IngestionService:
    """Return a shared IngestionService instance."""
    rag_settings = settings.rag
    embed_service = EmbeddingService(settings=rag_settings)
    vector_store = VectorStore(settings=rag_settings, embedding_service=embed_service)
    processor = DocumentProcessor(settings=rag_settings)
    return IngestionService(processor=processor, vector_store=vector_store)


# ── Auth helper ───────────────────────────────────────────────────────────


async def _resolve_user_id(
    authorization: str | None = Header(None),
) -> str | None:
    """Resolve user from Bearer token (optional for RAG endpoints)."""
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        from backend.core.database import resolve_auth_token

        return await resolve_auth_token(token)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Collection Management
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/collections", response_model=RAGCollectionList)
async def list_collections() -> RAGCollectionList:
    """List all available vector store collections."""
    store = _get_vector_store()
    names = await store.list_collections()
    return RAGCollectionList(items=names)


@router.get("/collections/{name}", response_model=RAGCollectionInfo)
async def get_collection_info(name: str) -> RAGCollectionInfo:
    """Get metadata and stats about a specific collection."""
    store = _get_vector_store()
    try:
        info = await store.get_collection_info(name)
        return RAGCollectionInfo(
            name=info.name,
            total_vectors=info.total_vectors,
            dim=info.dim,
            indexing_status=info.indexing_status,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Collection not found: {exc}") from exc


@router.post("/collections", response_model=RAGMessageResponse)
async def create_collection(name: str = Query(..., description="Collection name")) -> RAGMessageResponse:
    """Create a new empty collection."""
    store = _get_vector_store()
    try:
        await store.create_collection(name)
        return RAGMessageResponse(message=f"Collection '{name}' created")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/collections/{name}", response_model=RAGMessageResponse)
async def delete_collection(name: str) -> RAGMessageResponse:
    """Delete a collection and all its data."""
    store = _get_vector_store()
    await store.delete_collection(name)
    return RAGMessageResponse(message=f"Collection '{name}' deleted")


# ═══════════════════════════════════════════════════════════════════════════
#  Vector Search
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/search", response_model=RAGSearchResponse)
async def search_rag(
    body: RAGSearchRequest,
) -> RAGSearchResponse:
    """Search across one or more collections."""
    rag_settings = settings.rag
    embed_service = EmbeddingService(settings=rag_settings)
    store = VectorStore(settings=rag_settings, embedding_service=embed_service)
    retrieval = RetrievalService(vector_store=store, settings=rag_settings)

    collection_names = body.collection_names or [body.collection_name]

    if len(collection_names) == 1:
        results = await retrieval.retrieve(
            query=body.query,
            collection_name=collection_names[0],
            limit=body.limit,
            min_score=body.min_score,
            filter=body.filter or "",
        )
    else:
        results = await retrieval.retrieve_multi(
            query=body.query,
            collection_names=collection_names,
            limit=body.limit,
            min_score=body.min_score,
        )

    return RAGSearchResponse(
        results=[
            {
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
                "parent_doc_id": r.parent_doc_id or "",
            }
            for r in results
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Document Tracking (SQL-backed)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/documents", response_model=RAGTrackedDocumentList)
async def list_documents(
    collection_name: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> RAGTrackedDocumentList:
    """List tracked RAG documents, optionally filtered by collection."""
    service = RAGDocumentService(db=session)
    return await service.list_documents(collection_name=collection_name)


@router.get("/documents/{doc_id}", response_model=RAGTrackedDocumentList)
async def get_document(
    doc_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGTrackedDocumentList:
    """Get details for a specific tracked document (wrapped in list for consistency)."""
    service = RAGDocumentService(db=session)
    doc = await service.get_document(doc_id)
    from backend.schemas.rag import RAGTrackedDocumentItem, RAGTrackedDocumentList

    return RAGTrackedDocumentList(
        items=[
            RAGTrackedDocumentItem(
                id=str(doc.id),
                collection_name=doc.collection_name,
                filename=doc.filename,
                filesize=doc.filesize,
                filetype=doc.filetype,
                status=doc.status,
                error_message=doc.error_message,
                vector_document_id=doc.vector_document_id,
                chunk_count=doc.chunk_count,
                has_file=bool(doc.storage_path),
                created_at=doc.created_at.isoformat() if doc.created_at else None,
                completed_at=doc.completed_at.isoformat() if doc.completed_at else None,
            )
        ],
        total=1,
    )


@router.delete("/documents/{doc_id}", response_model=RAGMessageResponse)
async def delete_document(
    doc_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGMessageResponse:
    """Delete a document from tracking and cascade to vector store + file storage."""
    service = RAGDocumentService(db=session)
    ingestion = _get_ingestion_service()
    await service.delete_document(doc_id, ingestion_service=ingestion)
    return RAGMessageResponse(message=f"Document '{doc_id}' deleted")


@router.post("/documents/{doc_id}/retry", response_model=RAGRetryResponse)
async def retry_document(
    doc_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGRetryResponse:
    """Retry ingestion for a failed document."""
    service = RAGDocumentService(db=session)
    try:
        doc = await service.retry_ingestion(doc_id)
        return RAGRetryResponse(
            id=str(doc.id),
            status=doc.status,
            message="Document queued for retry",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Download the original file for a tracked document."""
    service = RAGDocumentService(db=session)
    try:
        file_path, filename, mime_type = await service.get_download_info(doc_id)
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=mime_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
#  File Upload & Ingestion
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/upload", response_model=RAGIngestResponse)
@router.post("/upload/{collection_name}", response_model=RAGIngestResponse)
async def upload_document(
    file: UploadFile,
    collection_name: str = "documents",
    replace: bool = Query(True, description="Replace existing document with same name"),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload a file for RAG ingestion.

    Supported formats: PDF, DOCX, TXT, MD (based on configured parser).
    The file is validated, stored, tracked in the database, and queued for
    background ingestion via ARQ.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_data = await file.read()
    service = RAGDocumentService(db=session)
    store = _get_vector_store()

    try:
        result = await service.dispatch_upload(
            collection_name=collection_name,
            file_data=file_data,
            filename=file.filename,
            replace=replace,
            vector_store=store,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
#  Sync Operations
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/sync-logs", response_model=RAGSyncLogList)
async def list_sync_logs(
    collection_name: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> RAGSyncLogList:
    """List RAG sync operation logs."""
    service = RAGSyncService(db=session)
    return await service.list_sync_logs(collection_name=collection_name, limit=limit)


@router.post("/sync", response_model=RAGSyncResponse)
async def trigger_sync(
    body: RAGSyncRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RAGSyncResponse:
    """Trigger a sync operation for a local path."""
    service = RAGSyncService(db=session)
    try:
        sync_log = await service.start_local_sync(
            collection_name=body.collection_name,
            mode=body.mode,
            path=body.path or None,
        )
        return RAGSyncResponse(
            id=str(sync_log.id),
            status=sync_log.status,
            message=f"Sync started for collection '{body.collection_name}'",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync/{sync_id}/cancel", response_model=RAGMessageResponse)
async def cancel_sync(
    sync_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGMessageResponse:
    """Cancel a running sync operation."""
    service = RAGSyncService(db=session)
    try:
        await service.cancel_sync(sync_id)
        return RAGMessageResponse(message=f"Sync '{sync_id}' cancelled")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Status Streaming
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/status")
async def stream_rag_status():
    """SSE endpoint that streams RAG ingestion status events.

    Events are consumed from a Redis pub/sub channel ``rag_status``.
    Each event has ``event: status`` and JSON data.
    """
    status_service = RAGStatusService()
    return StreamingResponse(
        status_service.stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Connectors
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/connectors", response_model=ConnectorList)
async def list_connectors() -> ConnectorList:
    """List available sync source connector types."""
    return SyncSourceService.list_connectors()


# ═══════════════════════════════════════════════════════════════════════════
#  Sync Sources (CRUD + trigger)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/sources", response_model=SyncSourceList)
async def list_sources(
    is_active: bool | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> SyncSourceList:
    """List sync source configurations."""
    service = SyncSourceService(db=session)
    return await service.list_sources(is_active=is_active)


@router.get("/sources/{source_id}", response_model=SyncSourceRead)
async def get_source(
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> SyncSourceRead:
    """Get a specific sync source."""
    service = SyncSourceService(db=session)
    try:
        source = await service.get_source(source_id)
        return service._to_read(source)  # type: ignore[return-value]
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sources", response_model=SyncSourceRead, status_code=201)
async def create_source(
    body: SyncSourceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> SyncSourceRead:
    """Create a new sync source configuration."""
    service = SyncSourceService(db=session)
    try:
        return await service.create_source(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/sources/{source_id}", response_model=SyncSourceRead)
async def update_source(
    source_id: str,
    body: SyncSourceUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> SyncSourceRead:
    """Update an existing sync source."""
    service = SyncSourceService(db=session)
    try:
        return await service.update_source(source_id, body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/sources/{source_id}", response_model=RAGMessageResponse)
async def delete_source(
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGMessageResponse:
    """Delete a sync source."""
    service = SyncSourceService(db=session)
    try:
        await service.delete_source(source_id)
        return RAGMessageResponse(message=f"Source '{source_id}' deleted")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sources/{source_id}/sync", response_model=RAGSyncResponse)
async def trigger_source_sync(
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RAGSyncResponse:
    """Trigger an immediate sync for a configured source."""
    service = SyncSourceService(db=session)
    try:
        sync_log = await service.trigger_sync(source_id)
        return RAGSyncResponse(
            id=str(sync_log.id),
            status=sync_log.status,
            message=f"Sync triggered for source '{source_id}'",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
