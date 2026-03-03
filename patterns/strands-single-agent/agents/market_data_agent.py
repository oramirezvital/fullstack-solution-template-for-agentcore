"""
Market Data Agent - Specialized agent for real-time and historical market data.

Owns all Alpha Vantage MCP tools: stock quotes, OHLCV, technical indicators,
options chains, forex, crypto, commodities, and economic indicators.
"""

import logging
import os

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Most advanced model available on Bedrock (Claude Sonnet 4.6)
# Uses Inference Profile for cross-region routing
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a Market Data Specialist with deep expertise in financial market data.

Your sole responsibility is to retrieve accurate, real-time and historical market data using Alpha Vantage tools.

CAPABILITIES:
- Real-time stock quotes (price, volume, change %)
- Historical OHLCV data (daily, weekly, monthly)
- Technical indicators: RSI, MACD, Bollinger Bands, SMA, EMA, ATR, ADX, Stochastic
- Fundamental data: earnings, income statements, balance sheets, cash flows, P/E, EPS
- Options chains: calls, puts, implied volatility, open interest
- Sector and industry performance
- Forex rates and crypto prices
- Commodities: oil, gold, silver
- Economic indicators: GDP, CPI, unemployment, interest rates

RULES:
- Always return raw data with exact values - do NOT interpret or recommend
- Include timestamps and data freshness information
- If data is unavailable, state clearly what is missing and why
- Return structured data that can be easily parsed by other agents
- Never make investment recommendations - that is not your role

RESPONSE FORMAT:
Return data in a clear, structured format with:
1. Data retrieved (exact values)
2. Timestamp / data freshness
3. Any data gaps or limitations noted
"""


def create_market_data_agent(alpha_vantage_api_key: str) -> Agent:
    """
    Create a specialized Market Data Agent with Alpha Vantage MCP tools.

    This agent is responsible exclusively for retrieving market data.
    It does not make recommendations - it only fetches and returns data.

    Args:
        alpha_vantage_api_key: Valid Alpha Vantage API key for MCP server authentication

    Returns:
        Agent: Configured market data agent with Alpha Vantage tools

    Raises:
        ValueError: If alpha_vantage_api_key is empty or None
        RuntimeError: If MCP client creation fails
    """
    if not alpha_vantage_api_key:
        raise ValueError("alpha_vantage_api_key is required and cannot be empty")

    logger.info("Creating Market Data Agent with Alpha Vantage MCP...")

    # Alpha Vantage MCP server URL with API key authentication
    alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={alpha_vantage_api_key}"

    try:
        alpha_vantage_client = MCPClient(
            lambda: streamablehttp_client(url=alpha_vantage_url),
            prefix="alphavantage",
        )
    except Exception as e:
        logger.error("Failed to create Alpha Vantage MCP client: %s", e)
        raise RuntimeError(f"Failed to initialize Alpha Vantage MCP client: {str(e)}") from e

    bedrock_model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0.0,  # Zero temperature for deterministic data retrieval
    )

    agent = Agent(
        name="MarketDataAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[alpha_vantage_client],
        model=bedrock_model,
    )

    logger.info("Market Data Agent created successfully")
    return agent
