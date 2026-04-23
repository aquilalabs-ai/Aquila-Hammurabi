"""Document upload, async analysis, and risk-report endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from hammurabi.api import jobs as job_store
from hammurabi.api import store
from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import AgentDep
from hammurabi.api.models import (
    AnalysisStatus,
    AnalyzeRequest,
    DocumentDetail,
    DocumentSummary,
    RiskFlagItem,
    RiskReportResponse,
)
from hammurabi.config import settings

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/docs",
    tags=["Documents"],
    dependencies=[Depends(require_api_key)],
)


async def _run_analysis(
    doc_id: str,
    job_id: str,
    agent: Any,
    doc_text: str,
    jurisdiction: str,
) -> None:
    t0 = time.monotonic()
    log.info("[analysis] job=%s doc=%s  jur=%s len=%d", job_id, doc_id, jurisdiction, len(doc_text))
    await job_store.update_job(job_id, status="running")
    await store.update_document_analysis(doc_id, job_id, "analyzing")

    try:
        from hammurabi.reasoning.risk import ClauseRiskScorer

        log.debug("[analysis] job=%s invoking agent", job_id)
        t1 = time.monotonic()
        response = await agent.invoke(
            "Perform a full IRAC analysis of this document, identifying key obligations, "
            "risks, and legal issues.",
            session_id=f"analysis-{doc_id}",
            jurisdiction=jurisdiction,
            document_text=doc_text,
        )
        log.info("[analysis] job=%s agent done (%.2fs)", job_id, time.monotonic() - t1)

        log.debug("[analysis] job=%s scoring clauses", job_id)
        scorer = ClauseRiskScorer(jurisdiction=jurisdiction)
        clauses = [s.strip() for s in doc_text.split("\n") if len(s.strip()) > 50][:30]
        risk_reports = scorer.score_document(clauses)
        log.debug("[analysis] job=%s clauses=%d flags=%d", job_id, len(clauses), len(risk_reports))

        result: dict[str, Any] = {
            "analysis": response,
            "risk_flags": [scorer.to_dict(r) for r in risk_reports],
            "jurisdiction": jurisdiction,
        }

        await store.update_document_analysis(doc_id, job_id, "ready", result)
        await job_store.update_job(job_id, status="completed", result=result)
        log.info("[analysis] job=%s completed (%.2fs total)", job_id, time.monotonic() - t0)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "[analysis] job=%s failed (%.2fs): %s",
            job_id, time.monotonic() - t0, exc, exc_info=True,
        )
        await store.update_document_analysis(doc_id, job_id, "failed")
        await job_store.update_job(job_id, status="failed", error=str(exc))


async def _extract_text(file: UploadFile) -> str:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        from hammurabi.ingestion.loaders import PDFLoader

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        try:
            doc = await asyncio.to_thread(PDFLoader().load, tmp_path)
            return "\n".join(p.text for p in doc.pages)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    if suffix == ".docx":
        from hammurabi.ingestion.loaders import DOCXLoader

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        try:
            doc = await asyncio.to_thread(DOCXLoader().load, tmp_path)
            return "\n".join(p.text for p in doc.pages)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    raw = await file.read()
    return raw.decode("utf-8", errors="replace")


@router.post("/upload", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    corpus_id: str | None = None,
    document_type: str = "contract",
    jurisdiction: str = settings.default_jurisdiction,
) -> DocumentSummary:
    try:
        content = await _extract_text(file)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}") from exc

    rec = await store.create_document(
        filename=file.filename or "upload",
        document_type=document_type,
        content=content,
        corpus_id=corpus_id,
        jurisdiction=jurisdiction,
    )
    return DocumentSummary(
        id=rec["id"],
        corpus_id=rec["corpus_id"],
        filename=rec["filename"],
        document_type=rec["document_type"],
        status=rec["status"],
        created_at=rec["created_at"],
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str) -> DocumentDetail:
    rec = await store.get_document(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetail(**{k: v for k, v in rec.items() if k in DocumentDetail.model_fields})


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str) -> None:
    if not await store.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    await store.delete_document_record(doc_id)


@router.post("/{doc_id}/analyze", response_model=AnalysisStatus, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    doc_id: str,
    body: AnalyzeRequest,
    agent: AgentDep,
) -> AnalysisStatus:
    rec = await store.get_document(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")

    job = await job_store.create_job("analyze")
    asyncio.create_task(
        _run_analysis(
            doc_id=doc_id,
            job_id=job.id,
            agent=agent,
            doc_text=rec["content"],
            jurisdiction=body.jurisdiction,
        )
    )
    return AnalysisStatus(document_id=doc_id, job_id=job.id, status="pending")


@router.get("/{doc_id}/analysis", response_model=AnalysisStatus)
async def get_analysis(doc_id: str) -> AnalysisStatus:
    rec = await store.get_document(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")

    job_id: str | None = rec.get("analysis_job_id")
    raw_result = rec.get("analysis_result")

    result: dict[str, Any] | None = None
    if isinstance(raw_result, str):
        try:
            result = json.loads(raw_result)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(raw_result, dict):
        result = raw_result

    job = await job_store.get_job(job_id) if job_id else None
    return AnalysisStatus(
        document_id=doc_id,
        job_id=job_id,
        status=rec["status"],
        result=result,
        error=job.error if job else None,
    )


@router.get("/{doc_id}/risk-report", response_model=RiskReportResponse)
async def get_risk_report(doc_id: str) -> RiskReportResponse:
    rec = await store.get_document(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")

    jurisdiction: str = rec.get("jurisdiction") or settings.default_jurisdiction

    raw_result = rec.get("analysis_result")
    result: dict[str, Any] | None = None
    if isinstance(raw_result, str):
        try:
            result = json.loads(raw_result)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(raw_result, dict):
        result = raw_result

    if result and result.get("risk_flags"):
        flags = [RiskFlagItem(**f) for f in result["risk_flags"]]
        return RiskReportResponse(document_id=doc_id, jurisdiction=jurisdiction, flags=flags)

    from hammurabi.reasoning.risk import ClauseRiskScorer

    scorer = ClauseRiskScorer(jurisdiction=jurisdiction)
    clauses = [s.strip() for s in rec["content"].split("\n") if len(s.strip()) > 50][:30]
    reports = scorer.score_document(clauses)
    flags = [RiskFlagItem(**scorer.to_dict(r)) for r in reports]
    return RiskReportResponse(document_id=doc_id, jurisdiction=jurisdiction, flags=flags)
