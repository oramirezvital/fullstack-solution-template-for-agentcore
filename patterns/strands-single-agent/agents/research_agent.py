"""
Research Agent - Specialized agent for investment research and news intelligence.

Owns all Tavily MCP tools: web search, news retrieval, analyst reports,
SEC filings, earnings call transcripts, and market sentiment analysis.
"""

import logging
from datetime import datetime

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Most advanced model available on Bedrock (Claude Sonnet 4.6)
# Uses Inference Profile for cross-region routing
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an Investment Research Specialist with expertise in financial intelligence gathering.

CURRENT DATE: {current_date}
IMPORTANT: We are currently in {current_year}. Always search for news and data from the current year.

Your sole responsibility is to find, retrieve, and summarize relevant research, news, and qualitative information.

CAPABILITIES:
- Latest financial news and market developments
- Analyst reports and price target changes
- Earnings call summaries and management commentary
- SEC filings (10-K, 10-Q, 8-K) key highlights
- Competitive landscape and industry trends
- Regulatory and macro environment changes
- ESG and governance issues
- Insider trading activity and institutional ownership changes
- Short interest and sentiment data

RESEARCH APPROACH:
1. Search for recent news (last 30-90 days prioritized)
2. Look for analyst consensus and diverging views
3. Identify key risks mentioned by multiple sources
4. Find management guidance and forward-looking statements
5. Note any red flags: accounting issues, legal problems, management changes

RULES:
- ALWAYS cite sources with full URLs
- Include publication dates for all sources
- Distinguish between facts and analyst opinions
- Flag conflicting information from different sources
- Do NOT make buy/sell recommendations - summarize what others say
- Note the credibility/authority of each source

RESPONSE FORMAT:
1. Key findings (bullet points with source URLs)
2. Analyst sentiment summary (bullish/bearish/neutral with reasons)
3. Key risks identified in research
4. Notable recent developments
5. Sources list with dates
"""


def create_research_agent(tavily_api_key: str) -> Agent:
    """
    Create a specialized Research Agent with Tavily MCP web search tools.

    This agent is responsible exclusively for gathering qualitative research,
    news, and intelligence. It does not make recommendations.

    Args:
        tavily_api_key: Valid Tavily API key for MCP server authentication

    Returns:
        Agent: Configured research agent with Tavily web search tools

    Raises:
        ValueError: If tavily_api_key is empty or None
        RuntimeError: If MCP client creation fails
    """
    if not tavily_api_key:
        raise ValueError("tavily_api_key is required and cannot be empty")

    logger.info("Creating Research Agent with Tavily MCP...")

    # Get current date for system prompt
    now = datetime.utcnow()
    current_date = now.strftime("%B %d, %Y")
    current_year = str(now.year)

    # Tavily MCP server URL - note: uses 'tavilyApiKey' parameter (not 'apikey')
    tavily_url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={tavily_api_key}"

    try:
        tavily_client = MCPClient(
            lambda: streamablehttp_client(url=tavily_url),
            prefix="tavily",
        )
    except Exception as e:
        logger.error("Failed to create Tavily MCP client: %s", e)
        raise RuntimeError(f"Failed to initialize Tavily MCP client: {str(e)}") from e

    bedrock_model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0.1,  # Slight creativity for synthesizing research narratives
    )

    agent = Agent(
        name="ResearchAgent",
        system_prompt=SYSTEM_PROMPT.format(
            current_date=current_date,
            current_year=current_year,
        ),
        tools=[tavily_client],
        model=bedrock_model,
    )

    logger.info("Research Agent created successfully")
    return agent
