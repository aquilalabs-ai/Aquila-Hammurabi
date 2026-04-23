"""LangGraph IRAC routing agent.

Graph topology
--------------
START
  → router          — classifies query into one of 5 routes
  → retrieval       — jurisdiction-aware retrieval (analysis + research only)
  → reasoning       — LLM inference with tool-call loop
  ↔ tools           — executes pending tool calls (loops back to reasoning)
  → formatter       — produces final structured output (IRAC / draft / pedagogy / plain)
END
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from hammurabi.config import settings
from hammurabi.reasoning.prompts import (
    EMPTY_CONTEXT_GATE,
    EMPTY_RESPONSE_RECOVERY,
    FORMAT_PROMPTS,
    LOOP_BREAK_INSTRUCTION,
    MAX_TOOL_CALLS,
    ROUTER_PROMPT,
    SKILL_PROMPTS,
    SYSTEM_BASE,
)
from hammurabi.reasoning.tools import build_tools

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    session_id: str
    query: str
    jurisdiction: str
    document_text: str  # empty string when no document is attached
    route: str  # "analysis" | "research" | "drafting" | "learning" | "simulation" | "report" | "direct"
    force_route: str  # non-empty bypasses router classification
    skill_prompt: str
    messages: Annotated[list[BaseMessage], add_messages]
    tool_call_count: int
    retrieved_context: str
    formatted_response: str


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _make_llm(bind_tools: list[Any] | None = None) -> ChatOpenAI:
    llm: ChatOpenAI = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model,
        temperature=0,
        streaming=True,
    )
    if bind_tools:
        return llm.bind_tools(bind_tools)  # type: ignore[return-value]
    return llm


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def router_node(state: AgentState, llm_plain: ChatOpenAI) -> dict[str, Any]:
    """Classify the query and inject the appropriate skill prompt fragment."""
    forced = state.get("force_route", "")
    if forced and forced in SKILL_PROMPTS:
        log.debug("[router] forced route=%s", forced)
        return {"route": forced, "skill_prompt": SKILL_PROMPTS[forced]}

    log.debug("[router] classifying query (len=%d)", len(state["query"]))
    t0 = time.monotonic()
    prompt = ROUTER_PROMPT.format(query=state["query"])
    response = await llm_plain.ainvoke([HumanMessage(content=prompt)])
    raw = str(response.content).strip().lower().split()[0] if response.content else "research"
    # Unknown labels (e.g. "irac", "analyse") fall back to "research" — never "direct",
    # because "direct" skips retrieval and conflicts with the strict grounding rule.
    route = raw if raw in SKILL_PROMPTS else "research"
    log.info("[router] route=%s raw=%r (%.2fs)", route, raw, time.monotonic() - t0)
    return {
        "route": route,
        "skill_prompt": SKILL_PROMPTS[route],
    }


_REWRITE_PROMPT = """\
Translate the following user question into {n} concise legal search queries \
in the same language ({lang}), using precise legal terminology (statutes, civil liability, \
obligations, contract law, etc.). Return only the queries, one per line, no numbering or explanation.

User question: {query}"""


async def _rewrite_query(query: str, jurisdiction: str, llm: Any, n: int = 2) -> list[str]:
    """Return up to *n* legal-terminology reformulations of *query*."""
    lang = "French" if jurisdiction.upper() == "FR" else "English"
    prompt = _REWRITE_PROMPT.format(query=query, n=n, lang=lang)
    log.debug("[retrieval] rewriting query into %d legal variants", n)
    t0 = time.monotonic()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        lines = [l.strip() for l in str(response.content).splitlines() if l.strip()]
        result = lines[:n]
        log.debug("[retrieval] rewrites done (%.2fs): %s", time.monotonic() - t0, result)
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("[retrieval] query rewrite failed (%.2fs): %s", time.monotonic() - t0, exc)
        return []


async def retrieval_node(state: AgentState, knowledge: Any, llm: Any) -> dict[str, Any]:
    """Retrieve initial context for analysis and research routes.

    Runs the original query *and* LLM-rewritten legal-terminology variants so that
    colloquial questions ("abîme ma voiture") map to the correct statute articles.
    """
    t0 = time.monotonic()
    jur = state["jurisdiction"]
    query = state["query"]
    top_k = 5 if (state["route"] == "analysis" and state["document_text"]) else 8

    log.info("[retrieval] start  route=%s jur=%s top_k=%d", state["route"], jur, top_k)

    # Build query list: original + legal reformulations
    extra = await _rewrite_query(query, jur, llm, n=2)
    queries = [query] + extra
    log.debug("[retrieval] queries: %s", queries)

    seen_ids: set[str] = set()
    merged: list[Any] = []

    for i, q in enumerate(queries):
        log.debug("[retrieval] searching query %d/%d: %r", i + 1, len(queries), q[:80])
        qt = time.monotonic()
        try:
            results = await knowledge.search(q, jurisdiction=jur, top_k=top_k)
            log.debug("[retrieval] q%d: %d hits (%.2fs)", i + 1, len(results), time.monotonic() - qt)  # noqa: E501
        except Exception as exc:
            log.warning("[retrieval] q%d failed (%.2fs): %s", i + 1, time.monotonic() - qt, exc)
            continue
        for r in results:
            uid = r.article_id or r.case_id or r.text[:60]
            if uid not in seen_ids:
                seen_ids.add(uid)
                merged.append(r)

    # Re-rank by score and keep top_k
    merged.sort(key=lambda r: r.score, reverse=True)
    merged = merged[:top_k]

    log.info("[retrieval] done  %d unique results (%.2fs)", len(merged), time.monotonic() - t0)

    if not merged:
        return {"retrieved_context": ""}

    context_parts: list[str] = []
    for r in merged:
        label = r.article_id or r.case_id or "doc"
        context_parts.append(f"[{label}] {r.text[:400]}")

    return {"retrieved_context": "\n\n".join(context_parts)}


async def reasoning_node(state: AgentState, llm_with_tools: Any) -> dict[str, Any]:
    """Run the LLM with tools. Injects loop-break and recovery guards."""
    t0 = time.monotonic()
    log.info("[reasoning] start  tool_calls_so_far=%d", state["tool_call_count"])
    today = date.today().isoformat()
    jur = state["jurisdiction"]
    system_content = SYSTEM_BASE.format(jurisdiction=jur, today=today)
    if state["skill_prompt"]:
        system_content += "\n\n" + state["skill_prompt"]

    # Prepend retrieved context when available
    if state.get("retrieved_context"):
        system_content += f"\n\n## Retrieved Context\n{state['retrieved_context']}"

    system_msg = SystemMessage(content=system_content)
    messages = state["messages"]

    # Detect follow-up: more than one HumanMessage means prior turns exist in history.
    # On follow-ups the LLM already has prior tool results in its context window, so the
    # empty-context gate must not fire — it would force redundant tool calls.
    is_followup = sum(1 for m in messages if isinstance(m, HumanMessage)) > 1

    # Empty-context gate fires only for routes that went through retrieval_node
    # and got nothing back.  "direct" and tool-driven routes must be excluded:
    # "direct" + SYSTEM_BASE's strict grounding rule creates an impossible
    # situation that forces the LLM into an infinite tool-call loop.
    if (
        not state.get("retrieved_context")
        and state["tool_call_count"] == 0
        and not is_followup
        and state["route"] in _RETRIEVAL_ROUTES
    ):
        messages = [*messages, HumanMessage(content=EMPTY_CONTEXT_GATE)]

    # Loop-break guard
    if state["tool_call_count"] >= MAX_TOOL_CALLS:
        guard = HumanMessage(
            content=LOOP_BREAK_INSTRUCTION.format(count=state["tool_call_count"])
        )
        messages = [*messages, guard]

    # Empty-response recovery
    if messages and isinstance(messages[-1], AIMessage):
        last_content = messages[-1].content
        if not last_content or (isinstance(last_content, str) and not last_content.strip()):
            messages = [*messages, HumanMessage(content=EMPTY_RESPONSE_RECOVERY)]

    all_messages = [system_msg, *messages]
    response = await llm_with_tools.ainvoke(all_messages)
    has_tools = bool(getattr(response, "tool_calls", None))
    log.info("[reasoning] done  has_tool_calls=%s (%.2fs)", has_tools, time.monotonic() - t0)

    return {
        "messages": [response],
        "tool_call_count": state["tool_call_count"],  # incremented in tools_node
    }


async def tools_node(state: AgentState, tools_by_name: dict[str, Any]) -> dict[str, Any]:
    """Execute all tool calls from the last AI message."""
    last: BaseMessage = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        log.debug("[tools] no tool calls to execute")
        return {"tool_call_count": state["tool_call_count"]}

    names = [tc["name"] for tc in last.tool_calls]
    log.info("[tools] executing %d tool(s): %s", len(names), names)

    tool_messages: list[ToolMessage] = []
    for tc in last.tool_calls:
        tool = tools_by_name.get(tc["name"])
        t0 = time.monotonic()
        if tool is None:
            log.warning("[tools] unknown tool: %s", tc["name"])
            result = f"Unknown tool: {tc['name']}"
        else:
            log.debug("[tools] start %s  args=%s", tc["name"], list(tc.get("args", {}).keys()))
            try:
                args: dict[str, Any] = tc.get("args", {})
                result = await tool.arun(args)
                log.info("[tools] %s done (%.2fs)", tc["name"], time.monotonic() - t0)
            except Exception as exc:  # noqa: BLE001
                log.error("[tools] %s failed (%.2fs): %s", tc["name"], time.monotonic() - t0, exc)
                result = f"Tool error: {exc}"
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )

    return {
        "messages": tool_messages,
        "tool_call_count": state["tool_call_count"] + len(last.tool_calls),
    }


async def formatter_node(state: AgentState, llm_plain: ChatOpenAI) -> dict[str, Any]:
    """Produce the final structured output based on the active route."""
    t0 = time.monotonic()
    route = state.get("route", "direct")
    log.info("[formatter] start  route=%s", route)
    format_prompt = FORMAT_PROMPTS.get(route, FORMAT_PROMPTS["direct"])

    # Gather conversation text (exclude system messages)
    conversation = [
        m for m in state["messages"] if not isinstance(m, SystemMessage)
    ]

    # If the last AI message is already valid JSON (e.g. a concept card or quiz produced
    # by the reasoning node), pass it through directly — do not reformat it as IRAC prose.
    last_ai = next(
        (m for m in reversed(conversation) if isinstance(m, AIMessage) and m.content),
        None,
    )
    if last_ai and isinstance(last_ai.content, str):
        stripped = last_ai.content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json.loads(stripped)
                log.info("[formatter] pass-through JSON (%.2fs)", time.monotonic() - t0)
                return {
                    "formatted_response": stripped,
                    "messages": [AIMessage(content=stripped)],
                }
            except json.JSONDecodeError:
                pass

    # Provide retrieved context so the formatter can verify what was actually retrieved
    system_parts = [
        "You are Hammurabi, an expert AI legal assistant. "
        "Produce the final formatted answer from the research already completed in this conversation. "
        "Respond in the same language the user used."
    ]
    if state.get("retrieved_context"):
        system_parts.append(
            f"## Retrieved Context (available for this session)\n{state['retrieved_context']}"
        )

    messages_for_format = [
        SystemMessage(content="\n\n".join(system_parts)),
        *conversation,
        HumanMessage(content=format_prompt),
    ]
    response = await llm_plain.ainvoke(messages_for_format)
    final = str(response.content)
    log.info("[formatter] done  response_len=%d (%.2fs)", len(final), time.monotonic() - t0)

    return {
        "formatted_response": final,
        "messages": [AIMessage(content=final)],
    }


# ---------------------------------------------------------------------------
# Edge conditions
# ---------------------------------------------------------------------------


_RETRIEVAL_ROUTES = frozenset({
    "analysis", "research", "simulation",
    "irac", "analyse", "analysis_irac",  # common LLM mis-labels, treated as research
})


def _after_router(state: AgentState) -> str:
    return "retrieval" if state["route"] in _RETRIEVAL_ROUTES else "reasoning"


def _after_reasoning(state: AgentState) -> str:
    last = state["messages"][-1] if state["messages"] else None
    if (
        isinstance(last, AIMessage)
        and last.tool_calls
        and state["tool_call_count"] < MAX_TOOL_CALLS
    ):
        return "tools"
    return "formatter"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(knowledge: Any) -> Any:
    """Compile the LangGraph agent.  Returns an invocable Pregel graph."""
    llm_plain = _make_llm()
    tools = build_tools(knowledge=knowledge, llm=llm_plain)
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = _make_llm(bind_tools=tools)

    builder: StateGraph = StateGraph(AgentState)

    # Register nodes (bind dependencies via async closures)
    async def _router(s: AgentState) -> dict[str, Any]:
        return await router_node(s, llm_plain)

    async def _retrieval(s: AgentState) -> dict[str, Any]:
        return await retrieval_node(s, knowledge, llm_plain)

    async def _reasoning(s: AgentState) -> dict[str, Any]:
        return await reasoning_node(s, llm_with_tools)

    async def _tools(s: AgentState) -> dict[str, Any]:
        return await tools_node(s, tools_by_name)

    async def _formatter(s: AgentState) -> dict[str, Any]:
        return await formatter_node(s, llm_plain)

    builder.add_node("router", _router)
    builder.add_node("retrieval", _retrieval)
    builder.add_node("reasoning", _reasoning)
    builder.add_node("tools", _tools)
    builder.add_node("formatter", _formatter)

    # Edges
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", _after_router, {"retrieval": "retrieval", "reasoning": "reasoning"})
    builder.add_edge("retrieval", "reasoning")
    builder.add_conditional_edges("reasoning", _after_reasoning, {"tools": "tools", "formatter": "formatter"})
    builder.add_edge("tools", "reasoning")
    builder.add_edge("formatter", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# High-level async API
# ---------------------------------------------------------------------------


class IRACAgent:
    """High-level wrapper around the compiled LangGraph agent.

    Handles session loading/saving and provides a clean async interface.
    """

    def __init__(self, knowledge: Any) -> None:
        self._knowledge = knowledge
        self._graph = build_graph(knowledge)

    async def invoke(
        self,
        query: str,
        *,
        session_id: str = "default",
        jurisdiction: str | None = None,
        document_text: str = "",
        history: list[BaseMessage] | None = None,
        force_route: str = "",
    ) -> str:
        """Run a single query through the agent and return the final response."""
        from hammurabi.reasoning.session import load_messages, save_messages

        t0 = time.monotonic()
        log.info("[invoke] start  sid=%s jur=%s route=%r", session_id, jurisdiction, force_route)

        jur = jurisdiction or settings.default_jurisdiction
        log.debug("[invoke] loading session messages")
        stored = await load_messages(session_id)
        prior_messages = _deserialise_messages(stored)
        log.debug("[invoke] loaded %d prior messages", len(prior_messages))
        initial_messages = [*prior_messages, HumanMessage(content=query)]
        if history:
            initial_messages = [*history, HumanMessage(content=query)]

        initial_state: AgentState = {
            "session_id": session_id,
            "query": query,
            "jurisdiction": jur,
            "document_text": document_text,
            "route": "direct",
            "force_route": force_route,
            "skill_prompt": "",
            "messages": initial_messages,
            "tool_call_count": 0,
            "retrieved_context": "",
            "formatted_response": "",
        }

        log.debug("[invoke] running graph")
        final_state: dict[str, Any] = await self._graph.ainvoke(initial_state)
        response: str = final_state.get("formatted_response", "")

        # Persist updated conversation
        all_messages = final_state.get("messages", [])
        log.debug("[invoke] saving %d messages", len(all_messages))
        await save_messages(session_id, _serialise_messages(all_messages))
        log.info("[invoke] done  response_len=%d (%.2fs)", len(response), time.monotonic() - t0)

        return response

    async def invoke_with_sources(
        self,
        query: str,
        *,
        session_id: str = "default",
        jurisdiction: str | None = None,
        document_text: str = "",
        force_route: str = "",
    ) -> tuple[str, list[BaseMessage]]:
        """Like invoke() but also returns the full message list for source extraction."""
        from hammurabi.reasoning.session import load_messages, save_messages

        t0 = time.monotonic()
        log.info("[invoke_with_sources] start  session=%s", session_id)
        jur = jurisdiction or settings.default_jurisdiction
        stored = await load_messages(session_id)
        prior_messages = _deserialise_messages(stored)
        initial_messages = [*prior_messages, HumanMessage(content=query)]

        initial_state: AgentState = {
            "session_id": session_id,
            "query": query,
            "jurisdiction": jur,
            "document_text": document_text,
            "route": "direct",
            "force_route": force_route,
            "skill_prompt": "",
            "messages": initial_messages,
            "tool_call_count": 0,
            "retrieved_context": "",
            "formatted_response": "",
        }

        final_state: dict[str, Any] = await self._graph.ainvoke(initial_state)
        response: str = final_state.get("formatted_response", "")
        all_messages: list[BaseMessage] = final_state.get("messages", [])

        await save_messages(session_id, _serialise_messages(all_messages))
        log.info("[invoke_with_sources] done (%.2fs)", time.monotonic() - t0)
        return response, all_messages

    async def stream(
        self,
        query: str,
        *,
        session_id: str = "default",
        jurisdiction: str | None = None,
        document_text: str = "",
        force_route: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream agent events token-by-token via astream_events."""
        from hammurabi.reasoning.session import load_messages, save_messages

        t0 = time.monotonic()
        log.info("[stream] start  session=%s jur=%s", session_id, jurisdiction)
        jur = jurisdiction or settings.default_jurisdiction
        stored = await load_messages(session_id)
        prior_messages = _deserialise_messages(stored)
        log.debug("[stream] loaded %d prior messages", len(prior_messages))
        initial_messages = [*prior_messages, HumanMessage(content=query)]

        initial_state: AgentState = {
            "session_id": session_id,
            "query": query,
            "jurisdiction": jur,
            "document_text": document_text,
            "route": "direct",
            "force_route": force_route,
            "skill_prompt": "",
            "messages": initial_messages,
            "tool_call_count": 0,
            "retrieved_context": "",
            "formatted_response": "",
        }

        final_messages: list[BaseMessage] = []

        async for event in self._graph.astream_events(initial_state, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            # DEBUG: log all event kinds/names/metadata to diagnose streaming
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "SSE event kind=%s name=%s meta=%s",
                kind, name, event.get("metadata", {}),
            )

            # Emit route classification as a status event
            if kind == "on_chain_end" and name == "router":
                route = event.get("data", {}).get("output", {}).get("route", "")
                yield {"type": "status", "content": f"route:{route}"}

            # Stream tokens from the formatter node only (reasoning is internal)
            elif kind == "on_chat_model_stream":
                node = event.get("metadata", {}).get("langgraph_node", "")
                if node == "formatter":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield {"type": "token", "content": chunk.content}

            # Emit tool call status events
            elif kind == "on_tool_start":
                yield {"type": "status", "content": f"tool:{name}"}

            # Capture final state for session persistence
            elif kind == "on_chain_end" and name == "LangGraph":
                output = event.get("data", {}).get("output", {})
                final_messages = output.get("messages", [])

        if final_messages:
            log.debug("[stream] saving %d messages", len(final_messages))
            await save_messages(session_id, _serialise_messages(final_messages))
        log.info("[stream] done (%.2fs)", time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Message serialisation helpers (BaseMessage ↔ plain dict for PostgreSQL)
# ---------------------------------------------------------------------------


def _serialise_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "human", "content": str(m.content)})
        elif isinstance(m, AIMessage):
            out.append({"role": "ai", "content": str(m.content)})
        elif isinstance(m, SystemMessage):
            out.append({"role": "system", "content": str(m.content)})
        elif isinstance(m, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "content": str(m.content),
                    "tool_call_id": m.tool_call_id,
                }
            )
        else:
            out.append({"role": "unknown", "content": str(m.content)})
    return out


def _deserialise_messages(raw: list[dict[str, Any]]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for item in raw:
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if role == "human":
            result.append(HumanMessage(content=content))
        elif role == "ai":
            result.append(AIMessage(content=content))
        elif role == "system":
            result.append(SystemMessage(content=content))
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=item.get("tool_call_id", ""),
                )
            )
    return result
