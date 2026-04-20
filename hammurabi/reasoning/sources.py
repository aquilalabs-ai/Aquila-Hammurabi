"""Parse structured sources from agent tool message results."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from hammurabi.api.models import ReportSourceItem


# ---------------------------------------------------------------------------
# News block parser  (LegalNewsSearchTool output format)
# ---------------------------------------------------------------------------

def parse_news_sources(text: str) -> list[ReportSourceItem]:
    """
    Parse a legal_news_search result block into structured sources.

    Expected format per entry:
        **[N] Title**
        Date : value
        Source : value
        Lien : https://...
        body text...
    """
    sources: list[ReportSourceItem] = []
    # Split at the start of each numbered entry
    blocks = re.split(r"(?=\*\*\[\d+\])", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        title_m = re.match(r"\*\*\[\d+\]\s+(.+?)\*\*", block)
        if not title_m:
            continue
        url_m = re.search(r"Lien\s*:\s*(https?://\S+)", block)
        date_m = re.search(r"Date\s*:\s*(.+?)(?:\n|$)", block)
        pub_m = re.search(r"Source\s*:\s*(.+?)(?:\n|$)", block)

        sources.append(
            ReportSourceItem(
                type="web",
                title=title_m.group(1).strip(),
                url=url_m.group(1).strip() if url_m else None,
                publication=pub_m.group(1).strip() if pub_m else None,
                date=date_m.group(1).strip() if date_m else None,
            )
        )
    return [s for s in sources if s.url]  # drop entries without a URL


# ---------------------------------------------------------------------------
# Statute block parser  (StatuteLookupTool output format)
# ---------------------------------------------------------------------------

def parse_statute_source(text: str) -> ReportSourceItem | None:
    """
    Parse a statute_lookup result block into a structured KB source.

    Expected format:
        ## Article {article_id}
        Code: ...
        Jurisdiction: ...
        Heading: ...

        {article text}
        ...
    """
    id_m = re.match(r"## Article\s+(\S+)", text)
    if not id_m:
        return None
    article_id = id_m.group(1).strip()
    heading_m = re.search(r"Heading:\s*(.+?)(?:\n|$)", text)

    # Extract article text: the block after the metadata header lines
    # Header lines: Code, Jurisdiction, Heading (up to the first blank line)
    excerpt = ""
    body_m = re.search(
        r"(?:Heading:[^\n]*\n+|Jurisdiction:[^\n]*\n+)(.*?)(?:\n###|$)",
        text,
        re.DOTALL,
    )
    if body_m:
        excerpt = body_m.group(1).strip()[:400]

    return ReportSourceItem(
        type="kb",
        title=heading_m.group(1).strip() if heading_m else article_id,
        article_id=article_id,
        excerpt=excerpt or None,
    )


# ---------------------------------------------------------------------------
# Full extractor — scans all tool messages in a conversation
# ---------------------------------------------------------------------------

def extract_kb_sources(messages: list[Any]) -> list[ReportSourceItem]:
    """
    Extract KB sources (statute_lookup results) from the agent's tool messages.
    Web sources from pre-fetched news are handled separately in report.py.
    """
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        return []

    # Map tool_call_id → tool_name by scanning AIMessage.tool_calls
    tool_names: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_names[tc["id"]] = tc["name"]

    sources: list[ReportSourceItem] = []
    seen_ids: set[str] = set()

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        tool_name = tool_names.get(msg.tool_call_id, "")
        if tool_name != "statute_lookup":
            continue
        src = parse_statute_source(str(msg.content))
        if src and src.article_id and src.article_id not in seen_ids:
            seen_ids.add(src.article_id)
            sources.append(src)

    return sources
