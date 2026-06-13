"""Task functions for RAG ingestion and sync operations.

Each function receives a ``ctx`` dict. Tasks are registered in
``TASK_REGISTRY`` and dispatched by :class:`TaskDispatcher`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.services.rag_document import RAGDocumentService
from backend.services.rag_sync import RAGSyncService

logger = logging.getLogger(__name__)

# Registry: maps task name -> async callable(ctx, **kwargs)
TASK_REGISTRY: dict[str, Any] = {}


def _register(fn):
    """Decorator to register a task function."""
    TASK_REGISTRY[fn.__name__] = fn
    return fn


@_register
async def ingest_document_task(
    ctx: dict,
    rag_document_id: str,
    collection_name: str,
    filepath: str,
    source_path: str,
    replace: bool = True,
) -> dict:
    """Process a single file through the RAG ingestion pipeline.

    Called by :meth:`RAGDocumentService.dispatch_upload`.

    Steps:
      1. Build the IngestionService
      2. Parse, chunk, embed, and store the document
      3. Mark the tracked record as done (or error)
    """
    logger.info(
        "[WORKER] Starting ingestion: doc=%s, collection=%s, file=%s",
        rag_document_id,
        collection_name,
        filepath,
    )

    from backend.services.rag.embeddings import EmbeddingService
    from backend.services.rag.documents import DocumentProcessor
    from backend.services.rag.vectorstore import MilvusVectorStore as VectorStore
    from backend.services.rag.ingestion import IngestionService

    try:
        rag_settings = settings.rag
        embed_service = EmbeddingService(settings=rag_settings)
        vector_store = VectorStore(settings=rag_settings, embedding_service=embed_service)
        processor = DocumentProcessor(settings=rag_settings)
        ingestion = IngestionService(processor=processor, vector_store=vector_store)

        result = await ingestion.ingest_file(
            filepath=Path(filepath),
            collection_name=collection_name,
            replace=replace,
            source_path=source_path,
        )

        # Create a DB session to update the tracked document record
        from backend.core.database import open_session

        async with open_session() as session:
            doc_service = RAGDocumentService(db=session)
            if result.status.value == "done" and result.document_id:
                await doc_service.complete_ingestion(
                    doc_id=rag_document_id,
                    vector_document_id=result.document_id,
                    chunk_count=0,  # could be tracked from result
                )
            elif result.status.value == "error":
                await doc_service.fail_ingestion(
                    doc_id=rag_document_id,
                    error_message=result.error_message or "Unknown error",
                )

        logger.info(
            "[WORKER] Ingestion complete: doc=%s, status=%s",
            rag_document_id,
            result.status,
        )
        return {"status": result.status.value, "document_id": result.document_id}

    except Exception as exc:
        logger.exception("[WORKER] Ingestion failed: doc=%s", rag_document_id)
        from backend.core.database import open_session

        async with open_session() as session:
            doc_service = RAGDocumentService(db=session)
            await doc_service.fail_ingestion(
                doc_id=rag_document_id,
                error_message=str(exc),
            )
        return {"status": "error", "message": str(exc)}


@_register
async def sync_collection_task(
    ctx: dict,
    sync_log_id: str,
    source: str,
    collection_name: str,
    mode: str,
    path: str | None = None,
) -> dict:
    """Sync a local directory or source into the RAG collection.

    Called by :meth:`RAGSyncService.start_local_sync`.
    """
    logger.info(
        "[WORKER] Starting sync: log=%s, collection=%s, mode=%s, path=%s",
        sync_log_id,
        collection_name,
        mode,
        path,
    )

    from backend.services.rag.embeddings import EmbeddingService
    from backend.services.rag.documents import DocumentProcessor
    from backend.services.rag.vectorstore import MilvusVectorStore as VectorStore
    from backend.services.rag.ingestion import IngestionService

    try:
        rag_settings = settings.rag
        embed_service = EmbeddingService(settings=rag_settings)
        vector_store = VectorStore(settings=rag_settings, embedding_service=embed_service)
        processor = DocumentProcessor(settings=rag_settings)
        ingestion = IngestionService(processor=processor, vector_store=vector_store)

        ingested = 0
        failed = 0
        skipped = 0

        if path and Path(path).is_dir():
            allowed_exts = {".pdf", ".docx", ".txt", ".md"}
            files = [p for p in Path(path).iterdir() if p.suffix.lower() in allowed_exts]
            total = len(files)
            logger.info("[WORKER] Found %d files to sync from %s", total, path)

            for filepath in files:
                result = await ingestion.ingest_file(
                    filepath=filepath,
                    collection_name=collection_name,
                    replace=(mode == "full"),
                    source_path=str(filepath),
                )
                if result.status.value == "done":
                    ingested += 1
                elif result.status.value == "error":
                    failed += 1
                else:
                    skipped += 1
        else:
            total = 0
            logger.warning("[WORKER] No valid path provided for sync")

        from backend.core.database import open_session

        async with open_session() as session:
            sync_service = RAGSyncService(db=session)
            await sync_service.complete_sync(
                sync_id=sync_log_id,
                status="done" if failed == 0 else "partial",
                total_files=total,
                ingested=ingested,
                updated=0,
                skipped=skipped,
                failed=failed,
            )

        logger.info(
            "[WORKER] Sync complete: log=%s, ingested=%d, failed=%d",
            sync_log_id,
            ingested,
            failed,
        )
        return {
            "status": "done",
            "total": total,
            "ingested": ingested,
            "failed": failed,
            "skipped": skipped,
        }

    except Exception as exc:
        logger.exception("[WORKER] Sync failed: log=%s", sync_log_id)
        from backend.core.database import open_session

        async with open_session() as session:
            sync_service = RAGSyncService(db=session)
            await sync_service.complete_sync(
                sync_id=sync_log_id,
                status="error",
                error_message=str(exc),
            )
        return {"status": "error", "message": str(exc)}


@_register
async def sync_single_source_task(
    ctx: dict,
    source_id: str,
    sync_log_id: str,
) -> dict:
    """Sync a single configured sync source.

    Called by :meth:`SyncSourceService.trigger_sync`.
    """
    logger.info("[WORKER] Starting source sync: source=%s, log=%s", source_id, sync_log_id)

    from backend.core.database import open_session
    from backend.services.sync_source import SyncSourceService

    try:
        async with open_session() as session:
            source_service = SyncSourceService(db=session)
            source = await source_service.get_source(source_id)

            # For local-file connectors, sync the configured path
            connector_type = source.connector_type
            config = source.config if isinstance(source.config, dict) else {}

            if "path" in config:
                result = await sync_collection_task(
                    ctx,
                    sync_log_id=sync_log_id,
                    source=connector_type,
                    collection_name=source.collection_name,
                    mode=source.sync_mode,
                    path=config["path"],
                )

                await source_service.update_after_sync(
                    source_id=source_id,
                    status=result.get("status", "error"),
                    error=result.get("message"),
                )
                return result
            else:
                await source_service.update_after_sync(
                    source_id=source_id,
                    status="error",
                    error="No path configured in source config",
                )
                return {"status": "error", "message": "No path configured"}

    except Exception as exc:
        logger.exception("[WORKER] Source sync failed: source=%s", source_id)
        async with open_session() as session:
            source_service = SyncSourceService(db=session)
            await source_service.update_after_sync(
                source_id=source_id,
                status="error",
                error=str(exc),
            )
        return {"status": "error", "message": str(exc)}
