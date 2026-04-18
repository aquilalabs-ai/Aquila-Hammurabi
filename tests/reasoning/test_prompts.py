"""Tests for prompt constants and skill fragments."""

from __future__ import annotations

from hammurabi.reasoning.prompts import (
    FORMAT_PROMPTS,
    MAX_TOOL_CALLS,
    ROUTER_PROMPT,
    SKILL_PROMPTS,
    SYSTEM_BASE,
    LOOP_BREAK_INSTRUCTION,
    EMPTY_RESPONSE_RECOVERY,
)


def test_skill_prompts_cover_all_routes() -> None:
    expected = {"analysis", "research", "drafting", "learning", "direct"}
    assert set(SKILL_PROMPTS.keys()) == expected


def test_format_prompts_cover_all_routes() -> None:
    expected = {"analysis", "research", "drafting", "learning", "direct"}
    assert set(FORMAT_PROMPTS.keys()) == expected


def test_direct_skill_is_empty() -> None:
    assert SKILL_PROMPTS["direct"] == ""


def test_system_base_has_placeholders() -> None:
    assert "{jurisdiction}" in SYSTEM_BASE
    assert "{today}" in SYSTEM_BASE


def test_router_prompt_has_placeholder() -> None:
    assert "{query}" in ROUTER_PROMPT


def test_router_prompt_lists_five_categories() -> None:
    for cat in ("analysis", "research", "drafting", "learning", "direct"):
        assert cat in ROUTER_PROMPT


def test_loop_break_has_count_placeholder() -> None:
    assert "{count}" in LOOP_BREAK_INSTRUCTION


def test_max_tool_calls_positive() -> None:
    assert MAX_TOOL_CALLS > 0


def test_empty_response_recovery_non_empty() -> None:
    assert len(EMPTY_RESPONSE_RECOVERY) > 20


def test_irac_format_prompt_contains_headings() -> None:
    irac = FORMAT_PROMPTS["analysis"]
    for heading in ("Issue", "Rule", "Application", "Conclusion"):
        assert heading in irac


def test_skill_prompts_non_empty_for_active_routes() -> None:
    for route in ("analysis", "research", "drafting", "learning"):
        assert len(SKILL_PROMPTS[route]) > 50, f"Skill prompt for {route!r} is too short"
