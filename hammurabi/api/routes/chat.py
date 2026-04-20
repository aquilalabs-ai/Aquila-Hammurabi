"""Chat and session endpoints — JSON response or SSE streaming."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from hammurabi.api import store
from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import AgentDep, KnowledgeDep
from hammurabi.api.models import (
    CaseSimulationRequest,
    CaseSimulationResponse,
    ChatRequest,
    ChatResponse,
    GenerateCaseRequest,
    GenerateCaseResponse,
    SessionCreate,
    SessionSummary,
)

router = APIRouter(tags=["Chat"], dependencies=[Depends(require_api_key)])


def _last_ai_per_turn(messages: list[dict]) -> list[dict]:
    """For each human turn keep only the last ai message that follows it."""
    result: list[dict] = []
    pending_ai: dict | None = None
    for m in messages:
        role = m.get("role")
        if role == "human":
            if pending_ai is not None:
                result.append(pending_ai)
                pending_ai = None
            result.append(m)
        elif role == "ai":
            pending_ai = m  # overwrite — keep only the last ai message per turn
    if pending_ai is not None:
        result.append(pending_ai)
    return result


async def _sse_stream(
    agent: Any,
    message: str,
    session_id: str,
    jurisdiction: str,
    document_text: str,
    force_route: str = "",
) -> AsyncGenerator[str]:
    # Flush headers to the client immediately — without this the browser's
    # fetch() blocks until the first data chunk, which can be tens of seconds
    # away when the DB or LLM is slow.
    yield ": stream-start\n\n"
    try:
        async for event in agent.stream(
            message,
            session_id=session_id,
            jurisdiction=jurisdiction,
            document_text=document_text,
            force_route=force_route,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    except Exception as exc:
        import logging as _logging
        import traceback
        _logging.getLogger(__name__).error("SSE stream error: %s", traceback.format_exc())
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc) or repr(exc)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/chat", response_model=None)
async def chat_global(
    body: ChatRequest,
    agent: AgentDep,
) -> StreamingResponse | ChatResponse:
    """Chat without a corpus — uses the default jurisdiction, no document context."""
    import logging as _logging
    from hammurabi.config import settings

    session_id = body.session_id or str(uuid.uuid4())
    jurisdiction = body.jurisdiction or settings.default_jurisdiction

    try:
        await store.touch_global_session(session_id)
    except Exception as exc:
        _logging.getLogger(__name__).warning("touch_global_session failed (non-fatal): %s", exc)

    if body.stream:
        return StreamingResponse(
            _sse_stream(agent, body.message, session_id, jurisdiction, body.document_text),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )

    response = await agent.invoke(
        body.message,
        session_id=session_id,
        jurisdiction=jurisdiction,
        document_text=body.document_text,
    )
    return ChatResponse(session_id=session_id, response=response)


@router.post("/corpus/{corpus_id}/chat", response_model=None)
async def chat(
    corpus_id: str,
    body: ChatRequest,
    agent: AgentDep,
) -> StreamingResponse | ChatResponse:
    import logging as _logging

    try:
        rec = await store.get_corpus(corpus_id)
    except Exception as exc:
        _logging.getLogger(__name__).warning("get_corpus failed (non-fatal): %s", exc)
        rec = None
    if not rec:
        raise HTTPException(status_code=404, detail="Corpus not found")

    session_id = body.session_id or str(uuid.uuid4())
    jurisdiction = body.jurisdiction or rec["jurisdiction"]

    if body.stream:
        return StreamingResponse(
            _sse_stream(agent, body.message, session_id, jurisdiction, body.document_text),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )

    response = await agent.invoke(
        body.message,
        session_id=session_id,
        jurisdiction=jurisdiction,
        document_text=body.document_text,
    )
    return ChatResponse(session_id=session_id, response=response)


@router.post("/generate-case", response_model=GenerateCaseResponse)
async def generate_case(
    body: GenerateCaseRequest,
    knowledge: KnowledgeDep,
) -> GenerateCaseResponse:
    """Generate a grounded case scenario fact pattern for student practice."""
    import contextlib
    import json
    import re

    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    from hammurabi.config import settings

    jur = body.jurisdiction or settings.default_jurisdiction

    # Retrieve articles relevant to the topic so the scenario is grounded
    article_ids: list[str] = []
    article_snippets = ""
    try:
        results = await knowledge.search(
            body.topic or "contrat obligation", jurisdiction=jur, top_k=4
        )
        for r in results:
            if r.article_id:
                article_ids.append(r.article_id)
                article_snippets += f"\n- [{r.article_id}]: {r.text[:200]}"
    except Exception:  # noqa: BLE001
        pass

    difficulty_desc = {
        "easy": "straightforward, one main legal issue, clear facts",
        "medium": "moderately complex, two or three legal issues",
        "hard": "complex, overlapping issues and nuanced facts",
    }.get(body.difficulty, "moderately complex")

    articles_json = json.dumps(article_ids[:3])
    prompt = (
        f"You are a law professor writing an exam question.\n\n"
        f"Create a {body.difficulty} case scenario ({difficulty_desc}) "
        f"about: {body.topic or 'a contractual dispute'}.\n"
        f"Jurisdiction: {jur}\n"
        + (f"Ground the scenario in these real articles:{article_snippets}\n" if article_snippets else "")
        + f"\nReturn ONLY a JSON object, no markdown fences:\n"
        f'{{"scenario": "3-5 sentences of pure facts — named parties, what happened, '
        f'dates, amounts. No legal analysis.", '
        f'"relevant_articles": {articles_json}}}\n\n'
        f"The scenario must describe facts only. Never include the legal answer or IRAC."
    )

    llm = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model,
        temperature=0.7,
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = str(response.content)

    stripped = re.sub(r"```(?:json)?\n?", "", raw).replace("```", "").strip()
    data: dict[str, object] | None = None
    with contextlib.suppress(json.JSONDecodeError):
        data = json.loads(stripped)
    if data is None:
        m = re.search(r"\{[\s\S]*\}", stripped)
        if m:
            with contextlib.suppress(json.JSONDecodeError):
                data = json.loads(m.group(0))

    if data and isinstance(data.get("scenario"), str):
        return GenerateCaseResponse(
            scenario=data["scenario"],
            relevant_articles=data.get("relevant_articles", article_ids[:3]),
            difficulty=body.difficulty,
        )

    return GenerateCaseResponse(
        scenario=raw,
        relevant_articles=article_ids[:3],
        difficulty=body.difficulty,
    )


@router.post("/simulate", response_model=None)
async def simulate_case(
    body: CaseSimulationRequest,
    agent: AgentDep,
) -> StreamingResponse | CaseSimulationResponse:
    """Solve a case scenario using full IRAC analysis grounded in the knowledge base."""
    from hammurabi.config import settings

    session_id = body.session_id or str(uuid.uuid4())
    jurisdiction = body.jurisdiction or settings.default_jurisdiction

    try:
        await store.touch_global_session(session_id)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("touch_global_session failed (non-fatal): %s", exc)

    query = body.scenario
    if body.legal_domain:
        query = f"{body.scenario}\n\n[Legal domain hint: {body.legal_domain}]"

    if body.stream:
        return StreamingResponse(
            _sse_stream(agent, query, session_id, jurisdiction, "", force_route="simulation"),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )

    response = await agent.invoke(
        query,
        session_id=session_id,
        jurisdiction=jurisdiction,
        force_route="simulation",
    )
    return CaseSimulationResponse(session_id=session_id, scenario=body.scenario, response=response)


@router.get("/sessions")
async def list_global_sessions() -> list[dict]:
    return await store.list_global_sessions()


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_global_session(body: SessionCreate) -> dict:
    return await store.create_global_session(title=body.title or "")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_global_session(session_id: str) -> None:
    from hammurabi.reasoning.session import delete_session as del_msgs

    await del_msgs(session_id)
    await store.delete_global_session(session_id)


@router.get("/sessions/{session_id}/messages")
async def get_global_session_messages(session_id: str) -> list[dict]:
    from hammurabi.reasoning.session import load_messages

    raw = await load_messages(session_id)
    filtered = [m for m in raw if m.get("role") in ("human", "ai")]
    return _last_ai_per_turn(filtered)


@router.get("/corpus/{corpus_id}/sessions", response_model=list[SessionSummary])
async def list_sessions(corpus_id: str) -> list[SessionSummary]:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")
    rows = await store.list_corpus_sessions(corpus_id)
    return [SessionSummary(**r) for r in rows]


@router.post(
    "/corpus/{corpus_id}/sessions",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(corpus_id: str, _body: SessionCreate) -> SessionSummary:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")
    sess = await store.create_corpus_session(corpus_id)
    return SessionSummary(**sess)


@router.get("/corpus/{corpus_id}/sessions/{session_id}/messages")
async def get_session_messages(corpus_id: str, session_id: str) -> list[dict]:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")
    from hammurabi.reasoning.session import load_messages

    raw = await load_messages(session_id)
    filtered = [m for m in raw if m.get("role") in ("human", "ai")]
    return _last_ai_per_turn(filtered)


@router.delete(
    "/corpus/{corpus_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(corpus_id: str, session_id: str) -> None:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")
    from hammurabi.reasoning.session import delete_session as del_msg_session

    await del_msg_session(session_id)
    await store.delete_corpus_session(corpus_id, session_id)
