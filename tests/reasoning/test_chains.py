"""Tests for the specialised LangChain chains (using mocked LLMs)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage


def _mock_llm(response_text: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=response_text))
    return llm


class TestDocumentAnalysisChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import document_analysis_chain

        llm = _mock_llm("Parties: A and B. Obligations: ...")
        result = await document_analysis_chain(llm, "Contract text here", jurisdiction="FR")
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_passes_jurisdiction(self) -> None:
        from hammurabi.reasoning.chains import document_analysis_chain

        llm = _mock_llm("Analysis result")
        await document_analysis_chain(llm, "text", jurisdiction="EU")
        call_args = llm.ainvoke.call_args
        messages = call_args[0][0]
        system_content = messages[0].content
        assert "EU" in system_content


class TestIRACChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import irac_chain

        llm = _mock_llm("## Issue\n## Rule\n## Application\n## Conclusion")
        result = await irac_chain(llm, "Is silence acceptance?", jurisdiction="FR")
        assert isinstance(result, str)

    async def test_context_included(self) -> None:
        from hammurabi.reasoning.chains import irac_chain

        llm = _mock_llm("answer")
        await irac_chain(llm, "question", context="some context", jurisdiction="FR")
        call_args = llm.ainvoke.call_args
        messages = call_args[0][0]
        system_content = messages[0].content
        assert "some context" in system_content


class TestDraftingChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import drafting_chain

        llm = _mock_llm("CLAUSE 1. The parties agree...")
        result = await drafting_chain(llm, "limitation of liability clause", jurisdiction="FR")
        assert isinstance(result, str)

    async def test_includes_existing_text(self) -> None:
        from hammurabi.reasoning.chains import drafting_chain

        llm = _mock_llm("Improved clause")
        await drafting_chain(llm, "improve this", existing_text="old clause text", jurisdiction="FR")
        call_args = llm.ainvoke.call_args
        messages = call_args[0][0]
        human_content = messages[1].content
        assert "old clause text" in human_content


class TestStatuteExplanationChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import statute_explanation_chain

        llm = _mock_llm("**What it says**: This article...")
        result = await statute_explanation_chain(
            llm, "article text", article_id="fr-civil-1103", jurisdiction="FR"
        )
        assert isinstance(result, str)

    async def test_article_id_in_message(self) -> None:
        from hammurabi.reasoning.chains import statute_explanation_chain

        llm = _mock_llm("explanation")
        await statute_explanation_chain(
            llm, "text", article_id="fr-civil-1134", jurisdiction="FR"
        )
        call_args = llm.ainvoke.call_args
        messages = call_args[0][0]
        human_content = messages[1].content
        assert "fr-civil-1134" in human_content


class TestCaseLawSummaryChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import case_law_summary_chain

        llm = _mock_llm("## Facts\n...")
        result = await case_law_summary_chain(llm, "judgment text", case_id="case-001")
        assert isinstance(result, str)


class TestComparativeChain:
    async def test_returns_string(self) -> None:
        from hammurabi.reasoning.chains import comparative_chain

        llm = _mock_llm("## Issue\n## FR Approach\n## EU Approach")
        result = await comparative_chain(llm, "force majeure", "FR", "EU")
        assert isinstance(result, str)

    async def test_both_jurisdictions_in_system(self) -> None:
        from hammurabi.reasoning.chains import comparative_chain

        llm = _mock_llm("comparison")
        await comparative_chain(llm, "question", "FR", "DE")
        call_args = llm.ainvoke.call_args
        messages = call_args[0][0]
        system_content = messages[0].content
        assert "FR" in system_content
        assert "DE" in system_content
