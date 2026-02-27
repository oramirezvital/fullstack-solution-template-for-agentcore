"""Investment tracking utilities for storing and analyzing transactions."""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


class InvestmentTracker:
    """
    Manages investment transaction storage and performance tracking.
    
    This class provides methods to record investment transactions based on
    agent recommendations and analyze performance by comparing forecasted
    vs. actual returns.
    """
    
    def __init__(self, table_name: str, region: str = "us-east-1"):
        """
        Initialize the investment tracker.
        
        Args:
            table_name: DynamoDB table name for investment transactions
            region: AWS region for DynamoDB client
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(table_name)
        logger.info("Initialized InvestmentTracker with table: %s", table_name)

    
    def record_investment(
        self,
        user_id: str,
        symbol: str,
        company_name: str,
        units: float,
        price_per_unit: float,
        recommendation_reason: str,
        forecast_target_price: Optional[float] = None,
        forecast_timeframe_days: Optional[int] = None,
        session_id: Optional[str] = None,
        transaction_date: Optional[str] = None,
    ) -> Dict:
        """
        Record a new investment transaction.
        
        Args:
            user_id: Cognito user ID
            symbol: Stock ticker symbol
            company_name: Company name
            units: Number of shares/units purchased
            price_per_unit: Purchase price per unit
            recommendation_reason: Why this investment was recommended
            forecast_target_price: Predicted target price (optional)
            forecast_timeframe_days: Forecast timeframe in days (optional)
            session_id: Conversation session ID (optional)
            transaction_date: Date of transaction in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
                            Defaults to current date if not provided. (optional)
            
        Returns:
            Dict containing the created transaction record
            
        Raises:
            ValueError: If required parameters are invalid or date format is incorrect
        """
        if units <= 0:
            raise ValueError("Units must be greater than 0")
        if price_per_unit <= 0:
            raise ValueError("Price per unit must be greater than 0")
        
        # Use provided date or default to now
        if transaction_date:
            # Parse and validate the provided date
            try:
                # Handle both date-only and full timestamp formats
                tx_date = datetime.fromisoformat(transaction_date.replace('Z', '+00:00'))
                # Ensure timezone awareness
                if tx_date.tzinfo is None:
                    tx_date = tx_date.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError) as e:
                raise ValueError(
                    f"Invalid transaction_date format: {transaction_date}. "
                    "Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                ) from e
        else:
            tx_date = datetime.now(timezone.utc)
        
        timestamp_str = tx_date.isoformat()
        
        # Generate unique IDs
        transaction_id = f"{timestamp_str}#{symbol}"
        recommendation_id = f"rec_{uuid4().hex[:12]}"
        
        # Calculate values
        total_investment = Decimal(str(units * price_per_unit))
        
        # Calculate forecast expected return if target price provided
        forecast_expected_return_pct = None
        if forecast_target_price:
            forecast_expected_return_pct = (
                (forecast_target_price - price_per_unit) / price_per_unit * 100
            )
        
        transaction = {
            "user_id": user_id,
            "transaction_id": transaction_id,
            "transaction_date": timestamp_str,
            "symbol": symbol.upper(),
            "company_name": company_name,
            "transaction_type": "BUY",
            "units": Decimal(str(units)),
            "price_per_unit": Decimal(str(price_per_unit)),
            "total_investment": total_investment,
            "currency": "USD",
            "recommendation_id": recommendation_id,
            "recommendation_date": timestamp_str,
            "recommendation_reason": recommendation_reason,
            "session_id": session_id or "unknown",
            "status": "ACTIVE",
            "current_price": Decimal(str(price_per_unit)),
            "current_value": total_investment,
            "unrealized_gain_loss": Decimal("0"),
            "unrealized_gain_loss_pct": Decimal("0"),
            "last_price_update": timestamp_str,
            "created_at": timestamp_str,
            "updated_at": timestamp_str,
        }
        
        # Add optional forecast fields
        if forecast_target_price:
            transaction["forecast_target_price"] = Decimal(str(forecast_target_price))
        if forecast_timeframe_days:
            transaction["forecast_timeframe_days"] = forecast_timeframe_days
        if forecast_expected_return_pct is not None:
            transaction["forecast_expected_return_pct"] = Decimal(
                str(round(forecast_expected_return_pct, 2))
            )
        
        try:
            self.table.put_item(Item=transaction)
            logger.info(
                "Recorded investment: user=%s, symbol=%s, units=%s, price=%s",
                user_id, symbol, units, price_per_unit
            )
            return transaction
        except Exception as e:
            logger.error("Failed to record investment: %s", e)
            raise RuntimeError(f"Failed to record investment: {str(e)}") from e

    
    def update_position_price(
        self,
        user_id: str,
        transaction_id: str,
        current_price: float
    ) -> Dict:
        """
        Update the current price and calculate unrealized gains/losses.
        
        Args:
            user_id: Cognito user ID
            transaction_id: Transaction ID to update
            current_price: Current market price
            
        Returns:
            Dict containing updated transaction record
            
        Raises:
            ValueError: If transaction not found or price invalid
        """
        if current_price <= 0:
            raise ValueError("Current price must be greater than 0")
        
        try:
            # Get existing transaction
            response = self.table.get_item(
                Key={"user_id": user_id, "transaction_id": transaction_id}
            )
            
            if "Item" not in response:
                raise ValueError(f"Transaction not found: {transaction_id}")
            
            item = response["Item"]
            units = float(item["units"])
            price_per_unit = float(item["price_per_unit"])
            total_investment = float(item["total_investment"])
            
            # Calculate new values
            current_value = units * current_price
            unrealized_gain_loss = current_value - total_investment
            unrealized_gain_loss_pct = (unrealized_gain_loss / total_investment) * 100
            
            now = datetime.now(timezone.utc).isoformat()
            
            # Update item
            self.table.update_item(
                Key={"user_id": user_id, "transaction_id": transaction_id},
                UpdateExpression=(
                    "SET current_price = :price, "
                    "current_value = :value, "
                    "unrealized_gain_loss = :gain_loss, "
                    "unrealized_gain_loss_pct = :gain_loss_pct, "
                    "last_price_update = :update_time, "
                    "updated_at = :update_time"
                ),
                ExpressionAttributeValues={
                    ":price": Decimal(str(current_price)),
                    ":value": Decimal(str(current_value)),
                    ":gain_loss": Decimal(str(unrealized_gain_loss)),
                    ":gain_loss_pct": Decimal(str(round(unrealized_gain_loss_pct, 2))),
                    ":update_time": now,
                },
            )
            
            logger.info(
                "Updated position: %s, price=%s, gain/loss=%s%%",
                transaction_id, current_price, round(unrealized_gain_loss_pct, 2)
            )
            
            # Return updated item
            return {
                **item,
                "current_price": Decimal(str(current_price)),
                "current_value": Decimal(str(current_value)),
                "unrealized_gain_loss": Decimal(str(unrealized_gain_loss)),
                "unrealized_gain_loss_pct": Decimal(str(round(unrealized_gain_loss_pct, 2))),
            }
            
        except Exception as e:
            logger.error("Failed to update position price: %s", e)
            raise RuntimeError(f"Failed to update position: {str(e)}") from e
    
    def delete_investment(
        self,
        user_id: str,
        transaction_id: str,
    ) -> Dict:
        """
        Delete an investment transaction.
        
        This permanently removes a transaction from the portfolio. Use with caution
        as this action cannot be undone.
        
        Args:
            user_id: Cognito user ID
            transaction_id: Transaction ID to delete
            
        Returns:
            Dict containing confirmation of deletion
            
        Raises:
            ValueError: If transaction not found
        """
        try:
            # First verify the transaction exists
            response = self.table.get_item(
                Key={"user_id": user_id, "transaction_id": transaction_id}
            )
            
            if "Item" not in response:
                raise ValueError(f"Transaction not found: {transaction_id}")
            
            item = response["Item"]
            
            # Delete the transaction
            self.table.delete_item(
                Key={"user_id": user_id, "transaction_id": transaction_id}
            )
            
            logger.info(
                "Deleted investment: user=%s, transaction_id=%s, symbol=%s",
                user_id, transaction_id, item.get("symbol")
            )
            
            return {
                "status": "deleted",
                "transaction_id": transaction_id,
                "symbol": item.get("symbol"),
                "message": f"Successfully deleted transaction {transaction_id}"
            }
            
        except Exception as e:
            logger.error("Failed to delete investment: %s", e)
            raise RuntimeError(f"Failed to delete investment: {str(e)}") from e
    
    def get_active_positions(self, user_id: str) -> List[Dict]:
        """
        Get all active investment positions for a user.
        
        Args:
            user_id: Cognito user ID
            
        Returns:
            List of active transaction records
        """
        try:
            response = self.table.query(
                IndexName="user-status-index",
                KeyConditionExpression=Key("user_id").eq(user_id) & Key("status").eq("ACTIVE")
            )
            
            items = response.get("Items", [])
            logger.info("Retrieved %d active positions for user: %s", len(items), user_id)
            return items
            
        except Exception as e:
            logger.error("Failed to get active positions: %s", e)
            raise RuntimeError(f"Failed to get active positions: {str(e)}") from e
    
    def get_performance_summary(self, user_id: str) -> Dict:
        """
        Calculate performance summary for all active positions.
        
        Args:
            user_id: Cognito user ID
            
        Returns:
            Dict containing performance metrics
        """
        positions = self.get_active_positions(user_id)
        
        if not positions:
            return {
                "total_positions": 0,
                "total_invested": 0,
                "current_value": 0,
                "total_gain_loss": 0,
                "total_gain_loss_pct": 0,
                "positions": []
            }
        
        total_invested = sum(float(p["total_investment"]) for p in positions)
        current_value = sum(float(p["current_value"]) for p in positions)
        total_gain_loss = current_value - total_invested
        total_gain_loss_pct = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0
        
        return {
            "total_positions": len(positions),
            "total_invested": round(total_invested, 2),
            "current_value": round(current_value, 2),
            "total_gain_loss": round(total_gain_loss, 2),
            "total_gain_loss_pct": round(total_gain_loss_pct, 2),
            "positions": [
                {
                    "symbol": p["symbol"],
                    "company_name": p["company_name"],
                    "units": float(p["units"]),
                    "invested": float(p["total_investment"]),
                    "current_value": float(p["current_value"]),
                    "gain_loss": float(p["unrealized_gain_loss"]),
                    "gain_loss_pct": float(p["unrealized_gain_loss_pct"]),
                    "transaction_date": p["transaction_date"],
                    "transaction_id": p["transaction_id"],
                }
                for p in positions
            ]
        }
    
    def compare_forecast_vs_actual(self, user_id: str, transaction_id: str) -> Dict:
        """
        Compare forecasted performance vs. actual performance.
        
        Args:
            user_id: Cognito user ID
            transaction_id: Transaction ID to analyze
            
        Returns:
            Dict containing forecast vs. actual comparison
            
        Raises:
            ValueError: If transaction not found or no forecast data
        """
        try:
            response = self.table.get_item(
                Key={"user_id": user_id, "transaction_id": transaction_id}
            )
            
            if "Item" not in response:
                raise ValueError(f"Transaction not found: {transaction_id}")
            
            item = response["Item"]
            
            # Check if forecast data exists
            if "forecast_target_price" not in item:
                raise ValueError("No forecast data available for this transaction")
            
            forecast_target = float(item["forecast_target_price"])
            forecast_return_pct = float(item.get("forecast_expected_return_pct", 0))
            actual_return_pct = float(item["unrealized_gain_loss_pct"])
            current_price = float(item["current_price"])
            
            # Calculate accuracy
            forecast_accuracy = 100 - abs(forecast_return_pct - actual_return_pct)
            
            return {
                "symbol": item["symbol"],
                "transaction_date": item["transaction_date"],
                "purchase_price": float(item["price_per_unit"]),
                "current_price": current_price,
                "forecast": {
                    "target_price": forecast_target,
                    "expected_return_pct": forecast_return_pct,
                    "timeframe_days": item.get("forecast_timeframe_days"),
                },
                "actual": {
                    "return_pct": actual_return_pct,
                    "gain_loss": float(item["unrealized_gain_loss"]),
                },
                "comparison": {
                    "forecast_accuracy_pct": round(forecast_accuracy, 2),
                    "outperformed": actual_return_pct > forecast_return_pct,
                    "difference_pct": round(actual_return_pct - forecast_return_pct, 2),
                }
            }
            
        except Exception as e:
            logger.error("Failed to compare forecast vs actual: %s", e)
            raise RuntimeError(f"Failed to compare performance: {str(e)}") from e
