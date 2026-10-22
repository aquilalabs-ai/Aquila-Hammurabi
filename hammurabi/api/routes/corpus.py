"""Corpus management — ingest, list, stats, delete."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from hammurabi.api import jobs as job_store
from hammurabi.api import store
from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import KnowledgeDep
from hammurabi.api.models import (
    CorpusIngestResponse,
    CorpusRegisterRequest,
    CorpusStats,
    CorpusSummary,
)
from hammurabi.config import settings

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/corpus",
    tags=["Corpus"],
    dependencies=[Depends(require_api_key)],
)


async def _run_ingestion(
    corpus_id: str,
    job_id: str,
    knowledge: Any,
    source: str,
    source_type: str,
    jurisdiction: str,
    cleanup_path: str | None,
) -> None:
    """Background worker: load → segment → NER → chunk → ingest."""
    from hammurabi.ingestion.chunker import LegalChunker
    from hammurabi.ingestion.ner import LegalNERPipeline
    from hammurabi.ingestion.segmenter import LegalDocumentSegmenter

    t0 = time.monotonic()
    log.info("[ingest] job=%s  corpus=%s  %s/%s", job_id, corpus_id, source_type, jurisdiction)
    await job_store.update_job(job_id, status="running")
    await store.update_corpus_status(corpus_id, "ingesting")

    try:
        if source_type == "pdf":
            from hammurabi.ingestion.loaders import PDFLoader

            loader: Any = PDFLoader()
        elif source_type == "docx":
            from hammurabi.ingestion.loaders import DOCXLoader

            loader = DOCXLoader()
        elif source_type in ("xml", "json"):
            from hammurabi.ingestion.loaders import StructuredCodeLoader

            loader = StructuredCodeLoader()
        else:
            from hammurabi.ingestion.loaders import URLLoader

            loader = URLLoader()

        log.debug("[ingest] job=%s loading source: %s", job_id, source[:120])
        t1 = time.monotonic()
        doc = await asyncio.to_thread(loader.load, source)
        pages = len(getattr(doc, "pages", []))
        log.info("[ingest] job=%s loaded  pages=%d (%.2fs)", job_id, pages, time.monotonic() - t1)

        ner = LegalNERPipeline()
        chunker = LegalChunker()

        if not doc.segments:
            log.debug("[ingest] job=%s segmenting document", job_id)
            t1 = time.monotonic()
            segmenter = LegalDocumentSegmenter()
            doc.segments = await asyncio.to_thread(segmenter.segment, doc)
            log.info(
                "[ingest] job=%s segmentation done  segments=%d (%.2fs)",
                job_id, len(doc.segments), time.monotonic() - t1,
            )

        log.debug("[ingest] job=%s chunking", job_id)
        t1 = time.monotonic()
        chunks = await asyncio.to_thread(
            chunker.chunk_document, doc, None, jurisdiction
        )
        log.info("[ingest] job=%s chunks=%d (%.2fs)", job_id, len(chunks), time.monotonic() - t1)

        log.debug("[ingest] job=%s running NER on %d chunks", job_id, len(chunks))
        t1 = time.monotonic()
        for chunk in chunks:
            ner_result = ner.extract(chunk.text)
            chunk.tags = list(set(chunk.tags + ner_result.tags))
        log.info("[ingest] job=%s NER done (%.2fs)", job_id, time.monotonic() - t1)

        log.debug("[ingest] job=%s writing to graph + vector store", job_id)
        t1 = time.monotonic()
        summary = await knowledge.ingest_chunks(chunks, corpus_id=corpus_id)
        log.info(
            "[ingest] job=%s write done  a=%d c=%d v=%d err=%d (%.2fs)",
            job_id, summary.articles_merged, summary.cases_merged,
            summary.chunks_upserted, len(summary.errors), time.monotonic() - t1,
        )
        if summary.errors:
            log.warning("[ingest] job=%s ingestion errors: %s", job_id, summary.errors[:5])

        await store.update_corpus_status(
            corpus_id,
            "ready",
            article_count=summary.articles_merged,
            case_count=summary.cases_merged,
            chunk_count=summary.chunks_upserted,
        )
        await job_store.update_job(
            job_id,
            status="completed",
            result={
                "corpus_id": corpus_id,
                "articles_merged": summary.articles_merged,
                "cases_merged": summary.cases_merged,
                "chunks_upserted": summary.chunks_upserted,
                "errors": summary.errors,
            },
        )
        log.info("[ingest] job=%s completed (%.2fs total)", job_id, time.monotonic() - t0)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "[ingest] job=%s failed (%.2fs): %s", job_id, time.monotonic() - t0, exc, exc_info=True
        )
        await store.update_corpus_status(corpus_id, "failed")
        await job_store.update_job(job_id, status="failed", error=str(exc))
    finally:
        if cleanup_path:
            Path(cleanup_path).unlink(missing_ok=True)


@router.post("", response_model=CorpusIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_corpus(
    knowledge: KnowledgeDep,
    name: str = Form(...),
    jurisdiction: str = Form(default=settings.default_jurisdiction),
    source_type: str = Form(default="url"),
    url: str | None = Form(default=None),
    file: UploadFile | None = None,
) -> CorpusIngestResponse:
    if not url and not file:
        raise HTTPException(status_code=400, detail="Provide either 'url' or 'file'")

    corpus_rec = await store.create_corpus(name, jurisdiction)
    corpus_id = corpus_rec["id"]
    job = await job_store.create_job("ingest")

    source_path: str | None = None
    cleanup_path: str | None = None

    if file:
        suffix = Path(file.filename or "upload").suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            source_path = tmp.name
        cleanup_path = source_path

    source = url or source_path or ""
    asyncio.create_task(
        _run_ingestion(
            corpus_id=corpus_id,
            job_id=job.id,
            knowledge=knowledge,
            source=source,
            source_type=source_type,
            jurisdiction=jurisdiction,
            cleanup_path=cleanup_path,
        )
    )

    return CorpusIngestResponse(corpus_id=corpus_id, job_id=job.id, status="pending")


@router.post("/register", response_model=CorpusSummary, status_code=status.HTTP_201_CREATED)
async def register_corpus(body: CorpusRegisterRequest) -> CorpusSummary:
    """Register a corpus whose data was already ingested directly into Neo4j/Qdrant."""
    rec = await store.create_corpus(body.name, body.jurisdiction)
    await store.update_corpus_status(
        rec["id"],
        "ready",
        article_count=body.article_count,
        case_count=body.case_count,
        chunk_count=body.chunk_count,
    )
    rec["status"] = "ready"
    rec["article_count"] = body.article_count
    rec["case_count"] = body.case_count
    rec["chunk_count"] = body.chunk_count
    return CorpusSummary(**rec)


@router.get("", response_model=list[CorpusSummary])
async def list_corpora() -> list[CorpusSummary]:
    rows = await store.list_corpora()
    return [CorpusSummary(**r) for r in rows]


@router.get("/{corpus_id}/stats", response_model=CorpusStats)
async def corpus_stats(corpus_id: str) -> CorpusStats:
    rec = await store.get_corpus(corpus_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return CorpusStats(
        corpus_id=corpus_id,
        article_count=rec["article_count"],
        case_count=rec["case_count"],
        chunk_count=rec["chunk_count"],
    )


@router.delete("/{corpus_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_corpus(
    corpus_id: str,
    knowledge: KnowledgeDep,
    delete_sessions: bool = False,
) -> None:
    rec = await store.get_corpus(corpus_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Corpus not found")

    if delete_sessions:
        from hammurabi.reasoning.session import delete_session as del_session

        for s in await store.list_corpus_sessions(corpus_id):
            await del_session(s["session_id"])

    await knowledge.delete_corpus(corpus_id)
    await store.delete_corpus_record(corpus_id)
