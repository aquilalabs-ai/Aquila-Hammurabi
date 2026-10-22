"""Reasoning layer — LangGraph IRAC agent, chains, and risk scoring."""

from __future__ import annotations

from hammurabi.reasoning.agent import AgentState, IRACAgent, build_graph
from hammurabi.reasoning.chains import (
    case_law_summary_chain,
    comparative_chain,
    document_analysis_chain,
    drafting_chain,
    irac_chain,
    statute_explanation_chain,
)
from hammurabi.reasoning.risk import ClauseRiskScorer, RiskReport, RiskType, Severity
from hammurabi.reasoning.session import (
    close_engine,
    delete_session,
    ensure_schema,
    load_messages,
    purge_expired,
    save_messages,
)
from hammurabi.reasoning.tools import build_tools

__all__ = [
    # Agent
    "IRACAgent",
    "AgentState",
    "build_graph",
    # Tools
    "build_tools",
    # Chains
    "document_analysis_chain",
    "irac_chain",
    "drafting_chain",
    "statute_explanation_chain",
    "case_law_summary_chain",
    "comparative_chain",
    # Risk engine
    "ClauseRiskScorer",
    "RiskReport",
    "RiskType",
    "Severity",
    # Session
    "ensure_schema",
    "load_messages",
    "save_messages",
    "delete_session",
    "purge_expired",
    "close_engine",
]
