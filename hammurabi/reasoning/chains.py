"""Specialised LangChain chains for discrete legal tasks.

Each chain is a thin async callable that wraps an LLM prompt + optional
knowledge-layer retrieval.  They are used both by the LangGraph agent
(as sub-routines inside nodes) and can be called standalone.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

# ---------------------------------------------------------------------------
# 1. Document analysis chain
# Extracts clauses, obligations, parties, and risk flags from a contract.
# ---------------------------------------------------------------------------

_DOC_ANALYSIS_SYSTEM = """\
You are an expert contract lawyer. Analyse the provided document and extract:
1. Parties and their roles
2. Main obligations (numbered list)
3. Key dates and deadlines
4. Notable clauses (limitation of liability, IP transfer, non-compete, governing law)
5. Potential ambiguities or missing provisions

Be precise and reference clause numbers where visible.
"""


async def document_analysis_chain(
    llm: Any,
    document_text: str,
    jurisdiction: str = "FR",
) -> str:
    """Extract structure and obligations from a contract or regulatory document."""
    messages = [
        SystemMessage(content=_DOC_ANALYSIS_SYSTEM + f"\nJurisdiction: {jurisdiction}"),
        HumanMessage(content=document_text[:8000]),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)


# ---------------------------------------------------------------------------
# 2. IRAC reasoning chain
# Produces a structured Issue / Rule / Application / Conclusion answer.
# ---------------------------------------------------------------------------

_IRAC_SYSTEM = """\
You are a legal analyst. Answer the question using the IRAC method:

## Issue
## Rule
## Application
## Conclusion

Rules:
- Cite every statute as [article-id] and every case as [case-id]
- The Rule section must reference specific articles, not general principles
- The Conclusion must directly and unambiguously answer the question
- If the law is unsettled, say so and explain both positions

Context provided: {context}
Jurisdiction: {jurisdiction}
"""


async def irac_chain(
    llm: Any,
    question: str,
    context: str = "",
    jurisdiction: str = "FR",
) -> str:
    """Produce a structured IRAC answer for a legal question."""
    system = _IRAC_SYSTEM.format(
        context=context[:4000] if context else "none",
        jurisdiction=jurisdiction,
    )
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=question),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)


# ---------------------------------------------------------------------------
# 3. Drafting chain
# Generates a contract clause, memo section, or pleading fragment.
# ---------------------------------------------------------------------------

_DRAFTING_SYSTEM = """\
You are a senior legal drafter. Produce formal, publication-ready legal text.

Requirements:
- Use clear, unambiguous language
- Number sub-provisions (a), (b), (c)…
- Insert [PARTY A] / [PARTY B] placeholders where party names are unknown
- Add a note at the end if any provision requires local legal review

Jurisdiction: {jurisdiction}
"""


async def drafting_chain(
    llm: Any,
    instruction: str,
    existing_text: str = "",
    jurisdiction: str = "FR",
) -> str:
    """Draft or redraft a legal clause based on the instruction."""
    human_parts = [f"Instruction: {instruction}"]
    if existing_text:
        human_parts.append(f"\nExisting text to improve:\n{existing_text}")
    human_parts.append("\nProduce the drafted clause only.")

    messages = [
        SystemMessage(content=_DRAFTING_SYSTEM.format(jurisdiction=jurisdiction)),
        HumanMessage(content="\n".join(human_parts)),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)


# ---------------------------------------------------------------------------
# 4. Statute explanation chain
# Plain-language explanation of a statute article with context.
# ---------------------------------------------------------------------------

_STATUTE_EXPLAIN_SYSTEM = """\
You are a legal educator. Explain the provided statute article in plain language.

Structure your explanation as:
1. **What it says** — a one-sentence plain-language summary
2. **Why it matters** — practical significance
3. **Key concepts** — define any technical terms used
4. **Example** — a concrete scenario illustrating the article
5. **Related articles** — mention closely related provisions if known

Jurisdiction: {jurisdiction}
Audience: {audience}
"""


async def statute_explanation_chain(
    llm: Any,
    article_text: str,
    article_id: str = "",
    jurisdiction: str = "FR",
    audience: str = "student",
) -> str:
    """Explain a statute article in plain language."""
    messages = [
        SystemMessage(
            content=_STATUTE_EXPLAIN_SYSTEM.format(jurisdiction=jurisdiction, audience=audience)
        ),
        HumanMessage(
            content=f"Article: {article_id}\n\n{article_text}"
        ),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)


# ---------------------------------------------------------------------------
# 5. Case law summary chain
# Extract ratio decidendi and operative part from a judgment.
# ---------------------------------------------------------------------------

_CASE_SUMMARY_SYSTEM = """\
You are a legal analyst specialising in case law. Summarise the provided judgment.

Structure:
## Facts
## Legal Issues
## Ratio Decidendi
## Decision / Operative Part
## Significance

Be precise. Quote key passages where relevant (under 2 sentences each).
Jurisdiction: {jurisdiction}
"""


async def case_law_summary_chain(
    llm: Any,
    judgment_text: str,
    case_id: str = "",
    jurisdiction: str = "FR",
) -> str:
    """Extract ratio decidendi and operative part from a judgment."""
    messages = [
        SystemMessage(content=_CASE_SUMMARY_SYSTEM.format(jurisdiction=jurisdiction)),
        HumanMessage(content=f"Case: {case_id}\n\n{judgment_text[:6000]}"),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)


# ---------------------------------------------------------------------------
# 6. Comparative chain
# Compare how two jurisdictions treat the same legal issue.
# ---------------------------------------------------------------------------

_COMPARATIVE_SYSTEM = """\
You are a comparative law expert. Compare how the two specified jurisdictions
treat the legal issue provided.

Structure:
## Issue
## {jur_a} Approach
## {jur_b} Approach
## Key Differences
## Practical Implications

Cite specific statutes and cases for each jurisdiction. Be objective.
"""


async def comparative_chain(
    llm: Any,
    question: str,
    jurisdiction_a: str,
    jurisdiction_b: str,
    context_a: str = "",
    context_b: str = "",
) -> str:
    """Compare how two jurisdictions treat the same legal issue."""
    context_block = ""
    if context_a:
        context_block += f"\n### {jurisdiction_a} Context:\n{context_a[:2000]}"
    if context_b:
        context_block += f"\n### {jurisdiction_b} Context:\n{context_b[:2000]}"

    messages = [
        SystemMessage(
            content=_COMPARATIVE_SYSTEM.format(jur_a=jurisdiction_a, jur_b=jurisdiction_b)
        ),
        HumanMessage(content=f"Question: {question}{context_block}"),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content)
