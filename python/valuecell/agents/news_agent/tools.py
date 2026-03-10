"""News-related tools for the News Agent."""

import os
from datetime import datetime
from typing import Optional

from agno.agent import Agent
from loguru import logger

from valuecell.adapters.models import create_model


async def web_search(query: str) -> str:
    """Search web for the given query and return a summary of the top results.

    This function uses the centralized configuration system to create model instances.
    It supports multiple search providers:
    - Google (Gemini with search enabled) - when WEB_SEARCH_PROVIDER=google and GOOGLE_API_KEY is set
    - Perplexity (via OpenRouter) - when OPENROUTER_API_KEY is set
    - Fallback to primary provider (no real-time search)

    Args:
        query: The search query string.

    Returns:
        A summary of the top search results.
    """
    # Option 1: Google Gemini with search grounding
    if os.getenv("WEB_SEARCH_PROVIDER", "google").lower() == "google" and os.getenv(
        "GOOGLE_API_KEY"
    ):
        return await _web_search_google(query)

    # Option 2: Perplexity Sonar via OpenRouter
    if os.getenv("OPENROUTER_API_KEY"):
        model = create_model(
            provider="openrouter",
            model_id="perplexity/sonar",
            max_tokens=None,
            use_fallback=False,
        )
        response = await Agent(model=model).arun(query)
        return response.content

    # Option 3: Fallback to primary provider (no real-time search capability)
    logger.warning(
        "No web search provider configured (GOOGLE_API_KEY or OPENROUTER_API_KEY). "
        "Using primary provider without real-time search."
    )
    model = create_model()
    response = await Agent(model=model).arun(
        f"Based on your knowledge, provide information about: {query}"
    )
    return response.content


async def _web_search_google(query: str) -> str:
    """Search Google for the given query and return a summary of the top results.

    Uses Google Gemini with search grounding enabled for real-time web information.

    Args:
        query: The search query string.

    Returns:
        A summary of the top search results.
    """
    # Use Google Gemini with search enabled
    # The search=True parameter enables Google Search grounding for real-time information
    model = create_model(
        provider="google",
        model_id="gemini-2.5-flash",
        search=True,  # Enable Google Search grounding
    )
    response = await Agent(model=model).arun(query)
    return response.content


async def get_breaking_news() -> str:
    """Get breaking news and urgent updates.

    Returns:
        Formatted string containing breaking news
    """
    try:
        search_query = "breaking news urgent updates today"
        logger.info("Fetching breaking news")

        news_content = await web_search(search_query)
        return news_content

    except Exception as e:
        logger.error(f"Error fetching breaking news: {e}")
        return f"Error fetching breaking news: {str(e)}"


async def get_financial_news(
    ticker: Optional[str] = None, sector: Optional[str] = None
) -> str:
    """Get financial and market news.

    Args:
        ticker: Stock ticker symbol for company-specific news
        sector: Industry sector for sector-specific news

    Returns:
        Formatted string containing financial news
    """
    try:
        search_query = "financial market news"

        if ticker:
            search_query = f"{ticker} stock news financial market"
        elif sector:
            search_query = f"{sector} sector financial news market"

        # Add time constraint for recent news
        today = datetime.now().strftime("%Y-%m-%d")
        search_query += f" {today}"

        logger.info(f"Searching for financial news with query: {search_query}")

        news_content = await web_search(search_query)
        return news_content

    except Exception as e:
        logger.error(f"Error fetching financial news: {e}")
        return f"Error fetching financial news: {str(e)}"
