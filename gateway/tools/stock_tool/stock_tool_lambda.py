# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_stock_information(symbol: str, api_key: str) -> Dict[str, Any]:
    """
    Retrieves comprehensive stock information using Alpha Vantage API.

    This function fetches real-time stock data including price, volume, market metrics,
    and valuation ratios for a given stock symbol using Alpha Vantage's free API.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'MSFT')
        api_key: Alpha Vantage API key

    Returns:
        Dictionary containing stock information with the following keys:
        - symbol: Stock ticker symbol
        - name: Company name
        - current_price: Current stock price
        - currency: Currency of the stock price
        - daily_change: Price change in currency
        - daily_change_percent: Price change as percentage
        - volume: Trading volume
        - market_cap: Market capitalization
        - day_high: Highest price of the day
        - day_low: Lowest price of the day
        - week_52_high: 52-week high price
        - week_52_low: 52-week low price
        - pe_ratio: Price-to-earnings ratio

    Raises:
        ValueError: If the stock symbol is invalid or not found
        Exception: For other API or network errors
    """
    try:
        # Alpha Vantage API endpoints
        # GLOBAL_QUOTE: Real-time price and volume data
        quote_url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"

        # OVERVIEW: Company fundamentals and financial data
        overview_url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={api_key}"

        logger.info(f"Fetching quote data for {symbol}")

        # Fetch quote data (price, volume, change)
        with urllib.request.urlopen(quote_url, timeout=10) as response:
            quote_data = json.loads(response.read().decode())

        # Check for API errors
        if "Error Message" in quote_data:
            raise ValueError(f"Invalid stock symbol: {symbol}")

        if "Note" in quote_data:
            raise Exception("API rate limit reached. Please try again later.")

        if "Global Quote" not in quote_data or not quote_data["Global Quote"]:
            raise ValueError(f"No data found for symbol: {symbol}")

        quote = quote_data["Global Quote"]

        logger.info(f"Fetching overview data for {symbol}")

        # Fetch overview data (company info, market cap, PE ratio)
        with urllib.request.urlopen(overview_url, timeout=10) as response:
            overview_data = json.loads(response.read().decode())

        # Extract and format stock data
        stock_data = {
            "symbol": quote.get("01. symbol", symbol.upper()),
            "name": overview_data.get("Name", "N/A"),
            "current_price": float(quote.get("05. price", 0)),
            "currency": "USD",  # Alpha Vantage returns USD prices
            "daily_change": float(quote.get("09. change", 0)),
            "daily_change_percent": float(
                quote.get("10. change percent", "0").replace("%", "")
            ),
            "volume": int(quote.get("06. volume", 0)),
            "market_cap": int(overview_data.get("MarketCapitalization", 0))
            if overview_data.get("MarketCapitalization", "0").isdigit()
            else "N/A",
            "day_high": float(quote.get("03. high", 0)),
            "day_low": float(quote.get("04. low", 0)),
            "week_52_high": float(overview_data.get("52WeekHigh", 0))
            if overview_data.get("52WeekHigh")
            else "N/A",
            "week_52_low": float(overview_data.get("52WeekLow", 0))
            if overview_data.get("52WeekLow")
            else "N/A",
            "pe_ratio": float(overview_data.get("PERatio", 0))
            if overview_data.get("PERatio") and overview_data.get("PERatio") != "None"
            else "N/A",
        }

        return stock_data

    except urllib.error.HTTPError as e:
        logger.error(
            f"HTTP error fetching stock data for {symbol}: {e.code} - {e.reason}"
        )
        raise Exception(f"Failed to fetch stock data: HTTP {e.code}")
    except urllib.error.URLError as e:
        logger.error(f"Network error fetching stock data for {symbol}: {str(e)}")
        raise Exception(f"Network error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {symbol}: {str(e)}")
        raise Exception("Invalid response from stock data service")
    except Exception as e:
        logger.error(f"Error fetching stock data for {symbol}: {str(e)}")
        raise


def format_stock_data(stock_data: Dict[str, Any]) -> str:
    """
    Formats stock data into a human-readable string.

    Args:
        stock_data: Dictionary containing stock information

    Returns:
        Formatted string with stock information
    """

    # Helper function to format numbers
    def format_number(value: Any, prefix: str = "", suffix: str = "") -> str:
        """Format a number with optional prefix and suffix, or return 'N/A'."""
        if value == "N/A" or value is None or value == 0:
            return "N/A"
        if isinstance(value, (int, float)):
            if abs(value) >= 1_000_000_000:
                return f"{prefix}{value / 1_000_000_000:.2f}B{suffix}"
            elif abs(value) >= 1_000_000:
                return f"{prefix}{value / 1_000_000:.2f}M{suffix}"
            elif abs(value) >= 1_000:
                return f"{prefix}{value / 1_000:.2f}K{suffix}"
            else:
                return f"{prefix}{value:.2f}{suffix}"
        return str(value)

    # Format daily change with sign
    daily_change = stock_data.get("daily_change", 0)
    daily_change_pct = stock_data.get("daily_change_percent", 0)

    sign = "+" if daily_change >= 0 else ""
    change_str = f"{sign}{daily_change:.2f} ({sign}{daily_change_pct:.2f}%)"

    # Build formatted output
    result = f"""Stock Information for {stock_data.get("name", "N/A")} ({stock_data.get("symbol", "N/A")})

Current Price: ${stock_data.get("current_price", 0):.2f}
Daily Change: {change_str}

Trading Metrics:
  Volume: {format_number(stock_data.get("volume"))}
  Day High: ${stock_data.get("day_high", 0):.2f}
  Day Low: ${stock_data.get("day_low", 0):.2f}

52-Week Range:
  High: {format_number(stock_data.get("week_52_high"), prefix="$")}
  Low: {format_number(stock_data.get("week_52_low"), prefix="$")}

Valuation:
  Market Cap: {format_number(stock_data.get("market_cap"), prefix="$")}
  P/E Ratio: {format_number(stock_data.get("pe_ratio"))}

Data provided by Alpha Vantage
"""

    return result


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Stock information tool Lambda function for FAST AgentCore Gateway.

    This Lambda follows the "one tool per Lambda" design pattern, implementing
    a single tool that retrieves comprehensive stock market data using Alpha Vantage API.

    DESIGN PATTERN:
    - One Lambda function implements exactly one tool (get_stock_info)
    - Clear separation of concerns with dedicated helper functions
    - Comprehensive error handling and logging
    - Type hints for better code maintainability
    - Secure API key management via environment variables

    INPUT FORMAT:
    - event: Contains tool arguments directly (not wrapped in HTTP body)
      Expected: {'symbol': 'AAPL'}
    - context.client_context.custom['bedrockAgentCoreToolName']: Full tool name with target prefix

    OUTPUT FORMAT:
    - Success: {'content': [{'type': 'text', 'text': '<formatted stock data>'}]}
    - Error: {'error': '<error message>'}

    Args:
        event: Dictionary containing tool arguments from gateway
        context: Lambda context with AgentCore metadata in client_context.custom

    Returns:
        Dictionary with 'content' array containing stock information or 'error' string
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Get tool name from context and strip the target prefix
        delimiter = "___"
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[
            original_tool_name.index(delimiter) + len(delimiter) :
        ]

        logger.info(f"Processing tool: {tool_name}")

        # This Lambda implements exactly one tool: get_stock_info
        if tool_name == "get_stock_info":
            # Extract and validate symbol parameter
            symbol = event.get("symbol")

            if not symbol:
                logger.error("Missing required parameter: symbol")
                return {
                    "error": "Missing required parameter 'symbol'. Please provide a stock ticker symbol (e.g., 'AAPL', 'GOOGL')."
                }

            # Get API key from environment variable
            api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
            if not api_key:
                logger.error("ALPHA_VANTAGE_API_KEY environment variable not set")
                return {"error": "Stock data service is not properly configured"}

            # Fetch stock information
            logger.info(f"Fetching stock information for symbol: {symbol}")
            stock_data = get_stock_information(symbol=symbol, api_key=api_key)

            # Format the response
            formatted_result = format_stock_data(stock_data=stock_data)

            logger.info(f"Successfully retrieved stock information for {symbol}")

            return {"content": [{"type": "text", "text": formatted_result}]}
        else:
            # This should never happen if gateway is configured correctly
            logger.error(f"Unexpected tool name: {tool_name}")
            return {
                "error": f"This Lambda only supports 'get_stock_info', received: {tool_name}"
            }

    except ValueError as e:
        # Handle invalid stock symbols
        logger.error(f"Invalid stock symbol: {str(e)}")
        return {
            "error": f"Invalid stock symbol: {str(e)}. Please provide a valid stock ticker symbol."
        }

    except Exception as e:
        # Handle all other errors
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return {"error": f"Failed to retrieve stock information: {str(e)}"}
