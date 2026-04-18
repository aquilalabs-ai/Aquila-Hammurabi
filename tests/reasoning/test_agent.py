"""Tests for the agent state helpers and message serialisation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from hammurabi.reasoning.agent import (
    _deserialise_messages,
    _serialise_messages,
)
from hammurabi.reasoning.prompts import MAX_TOOL_CALLS


class TestMessageSerialisation:
    def test_roundtrip_human(self) -> None:
        msgs = [HumanMessage(content="hello")]
        assert _deserialise_messages(_serialise_messages(msgs))[0].content == "hello"

    def test_roundtrip_ai(self) -> None:
        msgs = [AIMessage(content="world")]
        result = _deserialise_messages(_serialise_messages(msgs))
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "world"

    def test_roundtrip_system_excluded_on_deserialise(self) -> None:
        msgs = [SystemMessage(content="sys")]
        serialised = _serialise_messages(msgs)
        assert serialised[0]["role"] == "system"
        deserialised = _deserialise_messages(serialised)
        assert isinstance(deserialised[0], SystemMessage)

    def test_roundtrip_tool_message(self) -> None:
        msgs = [ToolMessage(content="result", tool_call_id="abc123")]
        result = _deserialise_messages(_serialise_messages(msgs))
        assert isinstance(result[0], ToolMessage)
        assert result[0].tool_call_id == "abc123"

    def test_empty_list(self) -> None:
        assert _serialise_messages([]) == []
        assert _deserialise_messages([]) == []

    def test_mixed_conversation(self) -> None:
        msgs = [
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
            HumanMessage(content="q2"),
        ]
        serialised = _serialise_messages(msgs)
        assert len(serialised) == 3
        assert serialised[0]["role"] == "human"
        assert serialised[1]["role"] == "ai"
        assert serialised[2]["role"] == "human"

        deserialised = _deserialise_messages(serialised)
        assert len(deserialised) == 3
        assert isinstance(deserialised[0], HumanMessage)
        assert isinstance(deserialised[1], AIMessage)


class TestMaxToolCalls:
    def test_max_tool_calls_is_five(self) -> None:
        assert MAX_TOOL_CALLS == 5


class TestAfterReasoningEdge:
    """Test the routing logic after the reasoning node."""

    def _make_state(
        self, tool_calls: list[dict] | None, tool_call_count: int
    ) -> dict:
        from langchain_core.messages import AIMessage

        msg = AIMessage(content="")
        if tool_calls:
            msg = AIMessage(content="", tool_calls=tool_calls)  # type: ignore[call-arg]
        return {
            "messages": [msg],
            "tool_call_count": tool_call_count,
        }

    def test_routes_to_tools_when_tool_calls_present(self) -> None:
        from hammurabi.reasoning.agent import _after_reasoning, AgentState

        state = self._make_state(
            [{"name": "statute_lookup", "id": "tc1", "args": {}}], 0
        )
        assert _after_reasoning(state) == "tools"  # type: ignore[arg-type]

    def test_routes_to_formatter_when_no_tool_calls(self) -> None:
        from hammurabi.reasoning.agent import _after_reasoning

        state = self._make_state(None, 0)
        assert _after_reasoning(state) == "formatter"  # type: ignore[arg-type]

    def test_routes_to_formatter_when_max_calls_reached(self) -> None:
        from hammurabi.reasoning.agent import _after_reasoning

        state = self._make_state(
            [{"name": "statute_lookup", "id": "tc1", "args": {}}], MAX_TOOL_CALLS
        )
        assert _after_reasoning(state) == "formatter"  # type: ignore[arg-type]


class TestAfterRouterEdge:
    def test_analysis_goes_to_retrieval(self) -> None:
        from hammurabi.reasoning.agent import _after_router

        assert _after_router({"route": "analysis"}) == "retrieval"  # type: ignore[arg-type]

    def test_research_goes_to_retrieval(self) -> None:
        from hammurabi.reasoning.agent import _after_router

        assert _after_router({"route": "research"}) == "retrieval"  # type: ignore[arg-type]

    def test_drafting_goes_to_reasoning(self) -> None:
        from hammurabi.reasoning.agent import _after_router

        assert _after_router({"route": "drafting"}) == "reasoning"  # type: ignore[arg-type]

    def test_learning_goes_to_reasoning(self) -> None:
        from hammurabi.reasoning.agent import _after_router

        assert _after_router({"route": "learning"}) == "reasoning"  # type: ignore[arg-type]

    def test_direct_goes_to_reasoning(self) -> None:
        from hammurabi.reasoning.agent import _after_router

        assert _after_router({"route": "direct"}) == "reasoning"  # type: ignore[arg-type]
