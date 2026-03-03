"""
Portfolio Agent - Specialized agent for portfolio tracking and management.

Owns all investment tracking tools: record transactions, view performance,
update prices, delete transactions, compare forecasts, and export to Excel.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from strands import Agent, tool
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

# Most advanced model available on Bedrock (Claude Sonnet 4.6)
# Uses Inference Profile for cross-region routing
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a Portfolio Management Specialist responsible for tracking and managing investment portfolios.

Your sole responsibility is to accurately record, retrieve, update, and report on investment transactions.

CAPABILITIES:
- Record new investment transactions with full details
- Retrieve portfolio performance and current positions
- Update current market prices for positions
- Delete incorrect or unwanted transactions
- Compare forecasted vs actual performance
- Export portfolio data to Excel

RULES:
- ALWAYS use the exact user_id provided - never substitute or guess
- Accept ALL dates as provided - do NOT assume future dates are typos (we are in February 2026)
- For historical transactions, use the transaction_date parameter
- Confirm every action taken with exact details (symbol, units, price, date)
- When recording investments, always confirm: symbol, units, price, total cost, date
- Never make investment recommendations - only manage records

TRANSACTION RECORDING FORMAT:
When recording: "Recorded [units] shares of [SYMBOL] at $[price] on [date]. Total: $[total]. Transaction ID: [id]"

PERFORMANCE REPORTING FORMAT:
- Total invested vs current value
- Overall gain/loss in $ and %
- Individual position breakdown
- Best and worst performers
"""


def create_portfolio_agent(table_name: str, region: str) -> Agent:
    """
    Create a specialized Portfolio Agent with investment tracking tools.

    This agent manages all portfolio operations: recording transactions,
    tracking performance, and exporting data. It does not make recommendations.

    Args:
        table_name: DynamoDB table name for storing investment transactions
        region: AWS region where DynamoDB table is deployed

    Returns:
        Agent: Configured portfolio agent with investment tracking tools

    Raises:
        ValueError: If table_name or region is empty or None
        RuntimeError: If investment tracker initialization fails
    """
    if not table_name:
        raise ValueError("table_name is required and cannot be empty")
    if not region:
        raise ValueError("region is required and cannot be empty")

    logger.info("Creating Portfolio Agent with investment tracking tools...")

    # Import here to avoid circular imports and keep dependencies explicit
    from utils.investment_tracker import InvestmentTracker

    tracker = InvestmentTracker(table_name=table_name, region=region)

    # Define all portfolio tools as closures over the tracker instance.
    # Each tool is decorated with @tool so Strands can register it with the agent.

    @tool
    def record_investment(
        user_id: str,
        symbol: str,
        company_name: str,
        units: float,
        price_per_unit: float,
        recommendation_reason: str,
        forecast_target_price: Optional[float] = None,
        forecast_timeframe_days: Optional[int] = None,
        transaction_date: Optional[str] = None,
    ) -> str:
        """
        Record a new investment transaction in the portfolio.

        Args:
            user_id: Unique identifier for the user
            symbol: Stock ticker symbol (e.g., 'AAPL')
            company_name: Full company name (e.g., 'Apple Inc.')
            units: Number of shares purchased
            price_per_unit: Purchase price per share in USD
            recommendation_reason: Rationale for the investment decision
            forecast_target_price: Predicted target price (optional)
            forecast_timeframe_days: Forecast horizon in days (optional)
            transaction_date: ISO format date YYYY-MM-DD for historical transactions (optional)

        Returns:
            JSON string with transaction confirmation and details
        """
        result = tracker.record_investment(
            user_id=user_id,
            symbol=symbol,
            company_name=company_name,
            units=units,
            price_per_unit=price_per_unit,
            recommendation_reason=recommendation_reason,
            forecast_target_price=forecast_target_price,
            forecast_timeframe_days=forecast_timeframe_days,
            transaction_date=transaction_date,
        )
        return json.dumps(result, default=str)

    @tool
    def get_portfolio_performance(user_id: str) -> str:
        """
        Retrieve full portfolio performance summary for a user.

        Args:
            user_id: Unique identifier for the user

        Returns:
            JSON string with total invested, current value, gain/loss, and all positions
        """
        result = tracker.get_performance_summary(user_id=user_id)
        return json.dumps(result, default=str)

    @tool
    def update_investment_price(
        user_id: str,
        transaction_id: str,
        current_price: float,
    ) -> str:
        """
        Update the current market price for a specific investment position.

        Args:
            user_id: Unique identifier for the user
            transaction_id: Transaction ID to update (from get_portfolio_performance)
            current_price: Current market price per share in USD

        Returns:
            JSON string with updated position details and recalculated gain/loss
        """
        result = tracker.update_position_price(
            user_id=user_id,
            transaction_id=transaction_id,
            current_price=current_price,
        )
        return json.dumps(result, default=str)

    @tool
    def delete_investment(user_id: str, transaction_id: str) -> str:
        """
        Permanently delete an investment transaction from the portfolio.

        Args:
            user_id: Unique identifier for the user
            transaction_id: Transaction ID to delete (from get_portfolio_performance)

        Returns:
            JSON string with deletion confirmation and deleted transaction details
        """
        result = tracker.delete_investment(
            user_id=user_id,
            transaction_id=transaction_id,
        )
        return json.dumps(result, default=str)

    @tool
    def compare_forecast_actual(user_id: str, transaction_id: str) -> str:
        """
        Compare the original forecast against actual performance for an investment.

        Args:
            user_id: Unique identifier for the user
            transaction_id: Transaction ID to analyze (from get_portfolio_performance)

        Returns:
            JSON string with forecast vs actual comparison and accuracy percentage
        """
        result = tracker.compare_forecast_vs_actual(
            user_id=user_id,
            transaction_id=transaction_id,
        )
        return json.dumps(result, default=str)

    @tool
    def export_portfolio_to_excel(user_id: str) -> str:
        """
        Export the full portfolio to a multi-sheet Excel workbook.

        Generates sheets: Summary, Transactions, Active Positions, Forecasts.
        Returns base64-encoded Excel data for frontend download.

        Args:
            user_id: Unique identifier for the user

        Returns:
            JSON string with base64-encoded Excel file, filename, and metadata
        """
        from utils.excel_export import create_portfolio_excel

        summary = tracker.get_performance_summary(user_id=user_id)
        full_positions = tracker.get_active_positions(user_id=user_id)

        portfolio_data = {
            "total_positions": summary.get("total_positions", 0),
            "total_invested": summary.get("total_invested", 0),
            "current_value": summary.get("current_value", 0),
            "total_gain_loss": summary.get("total_gain_loss", 0),
            "total_gain_loss_pct": summary.get("total_gain_loss_pct", 0),
            "positions": full_positions,
        }

        excel_base64 = create_portfolio_excel(
            portfolio_data=portfolio_data,
            user_email=user_id,
        )

        result = {
            "success": True,
            "filename": f"portfolio_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "data": excel_base64,
            "size_kb": len(excel_base64) * 3 / 4 / 1024,
            "sheets": ["Summary", "Transactions", "Active Positions", "Forecasts"],
            "total_positions": portfolio_data.get("total_positions", 0),
        }

        return json.dumps(result, default=str)

    bedrock_model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0.0,  # Zero temperature for deterministic portfolio operations
    )

    agent = Agent(
        name="PortfolioAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            record_investment,
            get_portfolio_performance,
            update_investment_price,
            delete_investment,
            compare_forecast_actual,
            export_portfolio_to_excel,
        ],
        model=bedrock_model,
    )

    logger.info("Portfolio Agent created successfully")
    return agent
