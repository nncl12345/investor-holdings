"""
LLM service — Groq + Tavily for filing enrichment.

Two functions:
  summarize_transaction_purpose  — quick 1-2 sentence thesis from Item 4 text (Groq only)
  research_filing                — deep research: web search + LLM synthesis (Tavily + Groq)
"""

import logging

from groq import AsyncGroq

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUMMARIZE_SYSTEM = (
    "You are a financial analyst assistant. You receive raw Item 4 text from SEC 13D/G filings "
    "and produce a concise 1-2 sentence investment thesis summary. "
    "Strip all legal boilerplate, amendment language ('the Schedule 13D is hereby amended...'), "
    "and repetitive preamble. Focus on: WHY the investor is taking or increasing the position "
    "and WHAT outcome they are seeking (operational changes, strategic review, M&A, management, etc.). "
    "Write in plain English. Be specific about the company if the name is clear from context. "
    "If the text contains no substantive rationale (e.g. it is purely procedural), reply with an empty string."
)

_RESEARCH_SYSTEM = (
    "You are a financial analyst. You are given data about an SEC 13D/G filing and web search results "
    "about the investor and the target company. "
    "Write a clear 4-6 sentence investment context note. "
    "CRITICAL RULES: "
    "(1) Base your analysis ONLY on what the search results actually say. Do NOT invent or assume details "
    "not in the results. "
    "(2) Do NOT default to 'activist pressure' or 'seeking board seats' unless the search results explicitly say so — "
    "many large 13D filers are founders, sponsors, long-term holders, or passive investors trimming a stake. "
    "(3) Accurately characterise the nature of the position: is this a founding/sponsor stake, activist campaign, "
    "passive holding, M&A-related position, or gradual monetisation? "
    "(4) Cover: who the investor is, the true nature of their relationship with this company, "
    "what they are actually doing (based on evidence), and any relevant macro or industry context. "
    "If the search results are thin, say so honestly rather than filling gaps with assumptions."
)


async def summarize_transaction_purpose(raw_text: str) -> str | None:
    """
    Use Groq to turn verbose 13D/G Item 4 text into a clean 1-2 sentence thesis.
    Returns None if the API key is not configured or the text yields no useful summary.
    """
    if not settings.groq_api_key:
        logger.debug("GROQ_API_KEY not set — skipping summarization")
        return None

    if not raw_text or len(raw_text.strip()) < 30:
        return None

    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM},
                {"role": "user", "content": f"Summarise this Item 4 text:\n\n{raw_text[:4000]}"},
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        summary = content.strip() if content else ""
        return summary or None
    except Exception:
        logger.exception("Groq summarization failed — check GROQ_API_KEY and rate limits")
        return None


async def research_filing(
    investor_name: str,
    company_name: str,
    filing_type: str,
    filing_date: str,
    transaction_purpose: str | None,
    investor_id: int | None = None,
) -> str | None:
    """
    Deep research: search the web for context on this investor + company, then
    synthesize a rich investment context note using Groq.

    Requires both TAVILY_API_KEY and GROQ_API_KEY to be set.
    """
    if not settings.tavily_api_key or not settings.groq_api_key:
        logger.warning("TAVILY_API_KEY or GROQ_API_KEY not set — cannot run research")
        return None

    # 1. Web search for context
    search_results = await _tavily_search(investor_name, company_name)
    # Pass investor_id into filing history lookup
    _investor_id = investor_id
    if not search_results:
        logger.warning("Tavily returned no results for %s / %s", investor_name, company_name)

    # 2. Pull prior filings history for this investor+company from our own DB
    filing_history = await _get_filing_history(_investor_id, company_name)

    # 3. Build context block for the LLM
    context_parts = [
        f"Filing: {filing_type} filed by {investor_name} regarding {company_name} on {filing_date}.",
    ]
    if transaction_purpose:
        context_parts.append(f"\nItem 4 (Investment Purpose) from the filing:\n{transaction_purpose[:2000]}")

    if filing_history:
        context_parts.append(
            f"\nFiling history for {investor_name} regarding {company_name} (from SEC EDGAR):\n{filing_history}"
        )

    if search_results:
        context_parts.append("\nRelevant web search results:")
        for r in search_results:
            context_parts.append(f"\n[{r['title']}]\n{r['content'][:500]}")

    context = "\n".join(context_parts)

    # 3. Synthesize with Groq
    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=512,
            messages=[
                {"role": "system", "content": _RESEARCH_SYSTEM},
                {"role": "user", "content": context},
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        result = content.strip() if content else ""
        return result or None
    except Exception:
        logger.exception("Groq research synthesis failed")
        return None


async def _get_filing_history(investor_id: int | None, company_name: str) -> str:
    """
    Return a plain-text summary of all filings this investor has made regarding
    this company, pulled from our own database. Gives the LLM concrete evidence
    of the timeline and stake evolution.
    """
    if not investor_id:
        return ""
    try:
        from sqlalchemy import select

        from app.core.db import AsyncSessionLocal
        from app.models.filing import Filing

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    Filing.filing_type,
                    Filing.filing_date,
                    Filing.pct_owned,
                    Filing.shares_owned,
                    Filing.transaction_purpose,
                )
                .where(Filing.investor_id == investor_id)
                .where(Filing.subject_company_name.ilike(f"%{company_name.split()[0]}%"))
                .order_by(Filing.filing_date.asc())
            )
            rows = result.all()

        if not rows:
            return ""

        lines = [
            f"{r.filing_date} | {r.filing_type} | "
            f"{f'{r.pct_owned:.1f}% of class' if r.pct_owned else ''} "
            f"{f'| {r.shares_owned:,} shares' if r.shares_owned else ''}"
            for r in rows
        ]

        # Prefer the original 13D Item 4 (not an amendment) as it contains the founding thesis
        original_purpose = None
        for r in rows:
            if r.transaction_purpose and len(r.transaction_purpose) > 100:
                # Prefer non-amendment filings first
                if r.filing_type in ("SC 13D", "SCHEDULE 13D"):
                    original_purpose = r.transaction_purpose
                    break
        # Fall back to earliest amendment with content
        if not original_purpose:
            for r in rows:
                if r.transaction_purpose and len(r.transaction_purpose) > 100:
                    original_purpose = r.transaction_purpose
                    break

        if original_purpose:
            lines.append(f"\nOriginal investment thesis (from first 13D filing):\n{original_purpose[:1200]}")

        return "\n".join(lines)
    except Exception:
        logger.exception("Failed to fetch filing history")
        return ""


async def _tavily_search(investor_name: str, company_name: str) -> list[dict]:
    """
    Run two targeted searches and merge results:
    1. The specific investor-company relationship (history, why they own it)
    2. The company itself (business, recent news)
    """
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=settings.tavily_api_key)

        # Strip "L.P.", "LLC" etc for cleaner search matching
        import re

        short_investor = (
            re.sub(r"\b(L\.?P\.?|LLC|Inc\.?|Ltd\.?|Corp\.?|Management)\b", "", investor_name).strip().strip(",")
        )
        short_company = re.sub(r"\b(Corp\.?|Inc\.?|Ltd\.?|LLC|Holdings)\b", "", company_name).strip().strip(".")

        queries = [
            f'"{short_company}" IPO founded history Elliott sponsor 2016 2021',
            f'"{short_investor}" "{short_company}" stake investment history',
            f'"{short_company}" precious metals streaming royalty overview',
        ]

        all_results: list[dict] = []
        seen_urls: set[str] = set()
        for query in queries:
            response = await client.search(
                query=query,
                search_depth="advanced",
                max_results=4,
                include_answer=False,
            )
            for r in response.get("results", []):
                if r.get("url") not in seen_urls:
                    seen_urls.add(r.get("url", ""))
                    all_results.append(r)

        return all_results
    except Exception:
        logger.exception("Tavily search failed")
        return []
