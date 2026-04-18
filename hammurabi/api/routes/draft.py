"""Document drafting and improvement endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from hammurabi.api import store
from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import AgentDep
from hammurabi.api.models import DraftImproveRequest, DraftRequest, DraftResponse

router = APIRouter(prefix="/draft", tags=["Drafting"], dependencies=[Depends(require_api_key)])


def _draft_prompt(body: DraftRequest) -> str:
    template_hint = {
        "contract": "a formal contract",
        "memo": "a legal memorandum",
        "pleading": "a legal pleading",
        "clause": "a contract clause",
    }.get(body.template_type, f"a {body.template_type}")
    return f"Draft {template_hint}: {body.prompt}"


@router.post("", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(body: DraftRequest, agent: AgentDep) -> DraftResponse:
    import uuid

    draft_id = str(uuid.uuid4())
    content = await agent.invoke(
        _draft_prompt(body),
        session_id=f"draft-{draft_id}",
        jurisdiction=body.jurisdiction,
        document_text=body.context,
    )
    rec = await store.create_draft(
        content=content,
        prompt=body.prompt,
        jurisdiction=body.jurisdiction,
        template_type=body.template_type,
    )
    return DraftResponse(
        id=rec["id"],
        content=rec["content"],
        prompt=rec["prompt"],
        jurisdiction=rec["jurisdiction"],
        template_type=rec["template_type"],
        created_at=rec["created_at"],
    )


@router.get("/{doc_id}", response_model=DraftResponse)
async def get_draft(doc_id: str) -> DraftResponse:
    rec = await store.get_draft(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Draft not found")
    return DraftResponse(
        id=rec["id"],
        content=rec["content"],
        prompt=rec["prompt"],
        jurisdiction=rec["jurisdiction"],
        template_type=rec["template_type"],
        created_at=rec["created_at"],
    )


@router.post("/{doc_id}/improve", response_model=DraftResponse)
async def improve_draft(
    doc_id: str,
    body: DraftImproveRequest,
    agent: AgentDep,
) -> DraftResponse:
    rec = await store.get_draft(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Draft not found")

    improved = await agent.invoke(
        f"Improve the following document according to these instructions: {body.instructions}",
        session_id=f"improve-{doc_id}",
        jurisdiction=body.jurisdiction,
        document_text=rec["content"],
    )
    await store.update_draft_content(doc_id, improved)
    updated = await store.get_draft(doc_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Draft update failed")
    return DraftResponse(
        id=updated["id"],
        content=improved,
        prompt=updated["prompt"],
        jurisdiction=updated["jurisdiction"],
        template_type=updated["template_type"],
        created_at=updated["created_at"],
    )
