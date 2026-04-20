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
from datetime import date
from typing import Annotated, Any, AsyncIterator

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
        return {"route": forced, "skill_prompt": SKILL_PROMPTS[forced]}

    prompt = ROUTER_PROMPT.format(query=state["query"])
    response = await llm_plain.ainvoke([HumanMessage(content=prompt)])
    raw = str(response.content).strip().lower().split()[0] if response.content else "direct"
    route = raw if raw in SKILL_PROMPTS else "direct"
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
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        lines = [l.strip() for l in str(response.content).splitlines() if l.strip()]
        return lines[:n]
    except Exception:  # noqa: BLE001
        return []


async def retrieval_node(state: AgentState, knowledge: Any, llm: Any) -> dict[str, Any]:
    """Retrieve initial context for analysis and research routes.

    Runs the original query *and* LLM-rewritten legal-terminology variants so that
    colloquial questions ("abîme ma voiture") map to the correct statute articles.
    """
    import logging as _logging

    log = _logging.getLogger(__name__)
    jur = state["jurisdiction"]
    query = state["query"]
    top_k = 5 if (state["route"] == "analysis" and state["document_text"]) else 8

    # Build query list: original + legal reformulations
    extra = await _rewrite_query(query, jur, llm, n=2)
    queries = [query] + extra
    log.debug("retrieval queries: %s", queries)

    seen_ids: set[str] = set()
    merged: list[Any] = []

    for q in queries:
        try:
            results = await knowledge.search(q, jurisdiction=jur, top_k=top_k)
        except Exception as exc:
            log.warning("Retrieval failed for query %r: %s", q, exc)
            continue
        for r in results:
            uid = r.article_id or r.case_id or r.text[:60]
            if uid not in seen_ids:
                seen_ids.add(uid)
                merged.append(r)

    # Re-rank by score and keep top_k
    merged.sort(key=lambda r: r.score, reverse=True)
    merged = merged[:top_k]

    if not merged:
        return {"retrieved_context": ""}

    context_parts: list[str] = []
    for r in merged:
        label = r.article_id or r.case_id or "doc"
        context_parts.append(f"[{label}] {r.text[:400]}")

    return {"retrieved_context": "\n\n".join(context_parts)}


async def reasoning_node(state: AgentState, llm_with_tools: Any) -> dict[str, Any]:
    """Run the LLM with tools. Injects loop-break and recovery guards."""
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

    # Routes that start with no KB context and drive retrieval entirely through tools —
    # injecting the empty-context gate here would conflict with their skill prompts.
    _TOOL_DRIVEN_ROUTES = {
        "report", "report_problematic", "report_plan", "report_critique", "report_coherence",
        "drafting", "learning",
    }

    # Empty-context gate — only for the very first message of a session.
    if (
        not state.get("retrieved_context")
        and state["tool_call_count"] == 0
        and not is_followup
        and state["route"] not in _TOOL_DRIVEN_ROUTES
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

    return {
        "messages": [response],
        "tool_call_count": state["tool_call_count"],  # incremented in tools_node
    }


async def tools_node(state: AgentState, tools_by_name: dict[str, Any]) -> dict[str, Any]:
    """Execute all tool calls from the last AI message."""
    last: BaseMessage = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"tool_call_count": state["tool_call_count"]}

    tool_messages: list[ToolMessage] = []
    for tc in last.tool_calls:
        tool = tools_by_name.get(tc["name"])
        if tool is None:
            result = f"Unknown tool: {tc['name']}"
        else:
            try:
                args: dict[str, Any] = tc.get("args", {})
                result = await tool.arun(args)
            except Exception as exc:  # noqa: BLE001
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
    route = state.get("route", "direct")
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

    return {
        "formatted_response": final,
        "messages": [AIMessage(content=final)],
    }


# ---------------------------------------------------------------------------
# Edge conditions
# ---------------------------------------------------------------------------


def _after_router(state: AgentState) -> str:
    return "retrieval" if state["route"] in ("analysis", "research", "simulation") else "reasoning"


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
        print("invoke: loading session : ", session_id)

        jur = jurisdiction or settings.default_jurisdiction
        stored = await load_messages(session_id)
        prior_messages = _deserialise_messages(stored)
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

        final_state: dict[str, Any] = await self._graph.ainvoke(initial_state)
        response: str = final_state.get("formatted_response", "")

        # Persist updated conversation
        all_messages = final_state.get("messages", [])
        await save_messages(session_id, _serialise_messages(all_messages))

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
        print("invoke_with_sources: loading session : ", session_id)
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
            await save_messages(session_id, _serialise_messages(final_messages))


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
