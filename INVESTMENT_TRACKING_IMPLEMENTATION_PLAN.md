# Investment Tracking & Performance Analysis Implementation Plan

## Overview

Implement a feature to track investments made based on agent recommendations, storing transaction details (date, symbol, units, price) and enabling performance comparison between forecasted and actual returns.

## Current State

**Existing Memory System:**
- ✅ AgentCore Memory with long-term strategies
- ✅ SemanticMemoryStrategy for investment facts
- ✅ UserPreferenceMemoryStrategy for preferences
- ✅ SummaryMemoryStrategy for session summaries

**Gap:**
- ❌ No structured storage for recommendation tracking
- ❌ No forecast vs. actual comparison capability
- ❌ No performance analytics over time

---

## Proposed Solution

### Architecture: Hybrid Approach

**1. AgentCore Memory** - For conversational context
**2. DynamoDB Table** - For structured investment tracking
**3. Agent Logic** - For performance analysis

---

## Part 1: Data Model Design

### DynamoDB Table: Investment Transactions

**Table Name:** `{stack_name}-investment-transactions`

**Primary Key:**
- Partition Key: `user_id` (STRING)
- Sort Key: `transaction_id` (STRING) - Format: `{timestamp}#{symbol}`

**Attributes:**

```json
{
  "user_id": "cognito-user-id",
  "transaction_id": "2026-02-23T10:30:00Z#AAPL",
  "transaction_date": "2026-02-23T10:30:00Z",
  "symbol": "AAPL",
  "company_name": "Apple Inc.",
  "transaction_type": "BUY",
  "units": 10,
  "price_per_unit": 185.50,
  "total_investment": 1855.00,
  "currency": "USD",
  
  // Recommendation Context
  "recommendation_id": "rec_abc123",
  "recommendation_date": "2026-02-23T10:25:00Z",
  "recommendation_reason": "Strong Q1 earnings, positive analyst sentiment",
  "forecast_target_price": 210.00,
  "forecast_timeframe_days": 90,
  "forecast_expected_return_pct": 13.2,
  "session_id": "session-xyz",
  
  // Performance Tracking
  "status": "ACTIVE",  // ACTIVE, SOLD, CLOSED
  "current_price": 189.25,  // Updated periodically
  "current_value": 1892.50,
  "unrealized_gain_loss": 37.50,
  "unrealized_gain_loss_pct": 2.02,
  "last_price_update": "2026-02-24T09:00:00Z",
  
  // Metadata
  "created_at": "2026-02-23T10:30:00Z",
  "updated_at": "2026-02-24T09:00:00Z"
}
```

**Global Secondary Indexes (GSI):**

1. **GSI-1: BySymbol**
   - Partition Key: `symbol`
   - Sort Key: `transaction_date`
   - Use: Query all transactions for a specific stock

2. **GSI-2: ByStatus**
   - Partition Key: `user_id`
   - Sort Key: `status#transaction_date`
   - Use: Query active/closed positions

3. **GSI-3: ByRecommendation**
   - Partition Key: `recommendation_id`
   - Sort Key: `transaction_date`
   - Use: Track all investments from a specific recommendation

---

## Part 2: Infrastructure Changes (CDK)

### File: `infra-cdk/lib/backend-stack.ts`

**Add DynamoDB Table:**


```typescript
private createInvestmentTrackingTable(config: AppConfig): dynamodb.Table {
  const table = new dynamodb.Table(this, "InvestmentTransactions", {
    tableName: `${config.stack_name_base}-investment-transactions`,
    partitionKey: {
      name: "user_id",
      type: dynamodb.AttributeType.STRING,
    },
    sortKey: {
      name: "transaction_id",
      type: dynamodb.AttributeType.STRING,
    },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    removalPolicy: cdk.RemovalPolicy.RETAIN, // Keep data on stack deletion
    pointInTimeRecoverySpecification: {
      pointInTimeRecoveryEnabled: true,
    },
    encryption: dynamodb.TableEncryption.AWS_MANAGED,
  });

  // GSI-1: Query by symbol
  table.addGlobalSecondaryIndex({
    indexName: "symbol-date-index",
    partitionKey: {
      name: "symbol",
      type: dynamodb.AttributeType.STRING,
    },
    sortKey: {
      name: "transaction_date",
      type: dynamodb.AttributeType.STRING,
    },
    projectionType: dynamodb.ProjectionType.ALL,
  });

  // GSI-2: Query by status
  table.addGlobalSecondaryIndex({
    indexName: "user-status-index",
    partitionKey: {
      name: "user_id",
      type: dynamodb.AttributeType.STRING,
    },
    sortKey: {
      name: "status",
      type: dynamodb.AttributeType.STRING,
    },
    projectionType: dynamodb.ProjectionType.ALL,
  });

  return table;
}
```

**Update Runtime Environment:**


```typescript
// In createAgentCoreRuntime method, add table to environment
const investmentTable = this.createInvestmentTrackingTable(config);

// Grant agent role access to the table
investmentTable.grantReadWriteData(agentRole);

// Add to environment variables
const envVars: { [key: string]: string } = {
  AWS_REGION: stack.region,
  AWS_DEFAULT_REGION: stack.region,
  MEMORY_ID: memoryId,
  STACK_NAME: config.stack_name_base,
  GATEWAY_URL: this.gatewayUrl,
  INVESTMENT_TABLE_NAME: investmentTable.tableName, // Add this
};
```

---

## Part 3: Python Utilities

### File: `patterns/utils/investment_tracker.py`

Create a new utility module for investment tracking operations:


```python
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
            
        Returns:
            Dict containing the created transaction record
            
        Raises:
            ValueError: If required parameters are invalid
        """
        if units <= 0:
            raise ValueError("Units must be greater than 0")
        if price_per_unit <= 0:
            raise ValueError("Price per unit must be greater than 0")
        
        now = datetime.now(timezone.utc)
        timestamp_str = now.isoformat()
        
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
```

---

## Part 4: Agent Integration

### Update: `patterns/strands-single-agent/basic_agent.py`

Add investment tracking tools to the agent:


```python
# Add to imports
from utils.investment_tracker import InvestmentTracker

# Create investment tracking tools wrapper
class InvestmentTrackingTools:
    """Strands wrapper for investment tracking tools."""
    
    def __init__(self, table_name: str, region: str):
        """Initialize investment tracking tools."""
        self.tracker = InvestmentTracker(table_name=table_name, region=region)
    
    @tool
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
    ) -> str:
        """
        Record a new investment transaction based on recommendation.
        
        Args:
            user_id: User identifier
            symbol: Stock ticker symbol
            company_name: Company name
            units: Number of shares purchased
            price_per_unit: Purchase price per share
            recommendation_reason: Why this investment was recommended
            forecast_target_price: Predicted target price (optional)
            forecast_timeframe_days: Forecast timeframe in days (optional)
            
        Returns:
            JSON string with transaction details
        """
        result = self.tracker.record_investment(
            user_id=user_id,
            symbol=symbol,
            company_name=company_name,
            units=units,
            price_per_unit=price_per_unit,
            recommendation_reason=recommendation_reason,
            forecast_target_price=forecast_target_price,
            forecast_timeframe_days=forecast_timeframe_days,
        )
        return json.dumps(result, default=str)
    
    @tool
    def get_portfolio_performance(self, user_id: str) -> str:
        """
        Get performance summary for all active investments.
        
        Args:
            user_id: User identifier
            
        Returns:
            JSON string with performance metrics
        """
        result = self.tracker.get_performance_summary(user_id=user_id)
        return json.dumps(result, default=str)
    
    @tool
    def compare_forecast_actual(self, user_id: str, transaction_id: str) -> str:
        """
        Compare forecasted vs. actual performance for an investment.
        
        Args:
            user_id: User identifier
            transaction_id: Transaction ID to analyze
            
        Returns:
            JSON string with forecast vs. actual comparison
        """
        result = self.tracker.compare_forecast_vs_actual(
            user_id=user_id,
            transaction_id=transaction_id
        )
        return json.dumps(result, default=str)

# In create_investment_advisor_agent function, add tracking tools
def create_investment_advisor_agent(user_id: str, session_id: str) -> Agent:
    # ... existing code ...
    
    # Initialize investment tracking tools
    table_name = os.environ.get("INVESTMENT_TABLE_NAME")
    if not table_name:
        raise ValueError("INVESTMENT_TABLE_NAME environment variable is required")
    
    tracking_tools = InvestmentTrackingTools(
        table_name=table_name,
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    
    # Create agent with tracking tools
    agent = Agent(
        name="InvestmentAdvisor",
        system_prompt=system_prompt,
        tools=[
            alpha_vantage_client,
            code_tools.execute_python_securely,
            tracking_tools.record_investment,  # Add tracking tools
            tracking_tools.get_portfolio_performance,
            tracking_tools.compare_forecast_actual,
        ],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
        },
    )
    
    return agent
```

---

## Part 5: System Prompt Updates

Add to the agent's system prompt:


```
5. INVESTMENT TRACKING & PERFORMANCE ANALYSIS:
   - Record investments made based on your recommendations
   - Track transaction details (date, symbol, units, price)
   - Store forecast predictions (target price, timeframe, expected return)
   - Compare forecasted vs. actual performance
   - Provide accountability for recommendations

INVESTMENT TRACKING WORKFLOW:

When making an investment recommendation:
1. Provide clear recommendation with rationale
2. Include forecast: target price, timeframe, expected return
3. If user decides to invest, record the transaction:
   - Use record_investment tool
   - Include all transaction details
   - Store your forecast for future comparison

Example:
"I recommend buying 10 shares of AAPL at $185.50. Based on strong Q1 earnings 
and positive analyst sentiment, I forecast a target price of $210 within 90 days, 
representing a 13.2% expected return.

Would you like me to record this investment for tracking?"

If user confirms, call:
record_investment(
    user_id="{user_id}",
    symbol="AAPL",
    company_name="Apple Inc.",
    units=10,
    price_per_unit=185.50,
    recommendation_reason="Strong Q1 earnings, positive analyst sentiment",
    forecast_target_price=210.00,
    forecast_timeframe_days=90
)

When user asks about portfolio performance:
1. Use get_portfolio_performance tool to fetch current positions
2. Update prices using alphavantage_GLOBAL_QUOTE for each position
3. Calculate total returns and individual position performance
4. Provide insights and recommendations

When analyzing recommendation accuracy:
1. Use compare_forecast_actual tool for specific investments
2. Show forecast vs. actual performance
3. Explain what factors caused differences
4. Learn from outcomes to improve future recommendations
5. Be transparent about both successes and misses

PERFORMANCE ANALYSIS TIPS:
- Always update prices before showing performance
- Acknowledge when forecasts were inaccurate
- Explain market factors that affected outcomes
- Use past performance to refine future recommendations
- Celebrate wins, learn from losses
```

---

## Part 6: Testing Strategy

### Unit Tests

Create: `patterns/strands-single-agent/tests/test_investment_tracker.py`


```python
"""Unit tests for investment tracking functionality."""

import pytest
from decimal import Decimal
from moto import mock_dynamodb
import boto3
from utils.investment_tracker import InvestmentTracker


@mock_dynamodb
def test_record_investment():
    """Test recording a new investment transaction."""
    # Setup mock DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName="test-investments",
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "transaction_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "transaction_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    
    tracker = InvestmentTracker(table_name="test-investments", region="us-east-1")
    
    # Record investment
    result = tracker.record_investment(
        user_id="test-user",
        symbol="AAPL",
        company_name="Apple Inc.",
        units=10,
        price_per_unit=185.50,
        recommendation_reason="Strong earnings",
        forecast_target_price=210.00,
        forecast_timeframe_days=90,
    )
    
    # Assertions
    assert result["symbol"] == "AAPL"
    assert result["units"] == Decimal("10")
    assert result["price_per_unit"] == Decimal("185.50")
    assert result["total_investment"] == Decimal("1855.00")
    assert result["status"] == "ACTIVE"


@mock_dynamodb
def test_update_position_price():
    """Test updating position with current price."""
    # Setup and record initial investment
    # ... (similar setup as above)
    
    # Update price
    updated = tracker.update_position_price(
        user_id="test-user",
        transaction_id=result["transaction_id"],
        current_price=195.00
    )
    
    # Assertions
    assert updated["current_price"] == Decimal("195.00")
    assert float(updated["unrealized_gain_loss"]) > 0
    assert float(updated["unrealized_gain_loss_pct"]) > 0


@mock_dynamodb
def test_compare_forecast_vs_actual():
    """Test forecast vs. actual comparison."""
    # Setup, record, and update
    # ... (similar setup)
    
    comparison = tracker.compare_forecast_vs_actual(
        user_id="test-user",
        transaction_id=result["transaction_id"]
    )
    
    # Assertions
    assert "forecast" in comparison
    assert "actual" in comparison
    assert "comparison" in comparison
    assert "forecast_accuracy_pct" in comparison["comparison"]
```

### Integration Tests

Test end-to-end flow:
1. Agent makes recommendation
2. User confirms investment
3. Transaction recorded
4. Prices updated
5. Performance analyzed

---

## Part 7: Deployment Steps

### Step 1: Deploy Infrastructure
```bash
cd infra-cdk
cdk deploy
```

### Step 2: Verify Table Creation
```bash
aws dynamodb describe-table \
  --table-name FAST-stack-investment-transactions \
  --query 'Table.[TableName,TableStatus,ItemCount]'
```

### Step 3: Test Locally (Optional)
```bash
# Set environment variables
export INVESTMENT_TABLE_NAME=FAST-stack-investment-transactions
export AWS_DEFAULT_REGION=us-east-1

# Run tests
pytest patterns/strands-single-agent/tests/test_investment_tracker.py
```

### Step 4: Deploy Agent
```bash
# Agent will be redeployed automatically with CDK
# Or manually trigger redeployment if using ZIP
```

---

## Part 8: Usage Examples

### Example 1: Making a Recommendation with Tracking

**User**: "Should I invest in Tesla?"

**Agent**: 
```
Based on my analysis of Tesla (TSLA):

Current Price: $248.50
Recommendation: BUY

Rationale:
- Strong Q4 deliveries exceeded expectations
- Cybertruck production ramping up
- Energy storage business growing 50% YoY
- Technical indicators show bullish momentum

Forecast:
- Target Price: $285.00
- Timeframe: 60 days
- Expected Return: 14.7%

Risk Factors:
- High valuation (P/E ratio of 65)
- Competition intensifying
- Regulatory challenges

Would you like me to record this investment recommendation for tracking?
If you decide to invest, I can track the performance and compare my forecast 
against actual results.
```

**User**: "Yes, I'll buy 5 shares. Please track it."

**Agent**:
```
Perfect! I've recorded your investment:

Transaction Details:
- Symbol: TSLA
- Shares: 5
- Purchase Price: $248.50/share
- Total Investment: $1,242.50
- Transaction Date: 2026-02-23

Forecast Recorded:
- Target Price: $285.00
- Timeframe: 60 days
- Expected Return: 14.7%

I'll track this investment and we can compare my forecast against actual 
performance. You can ask me anytime: "How is my Tesla investment performing?"
```

### Example 2: Checking Portfolio Performance

**User**: "How is my portfolio performing?"

**Agent**:
```
Here's your portfolio performance summary:

Overall Performance:
- Total Positions: 3
- Total Invested: $5,450.00
- Current Value: $5,892.50
- Total Gain: $442.50 (+8.12%)

Individual Positions:

1. AAPL (Apple Inc.)
   - Invested: $1,855.00 (10 shares @ $185.50)
   - Current: $1,950.00 ($195.00/share)
   - Gain: $95.00 (+5.12%)
   - Held: 15 days

2. TSLA (Tesla Inc.)
   - Invested: $1,242.50 (5 shares @ $248.50)
   - Current: $1,425.00 ($285.00/share)
   - Gain: $182.50 (+14.69%)
   - Held: 8 days
   - ✅ Forecast: Target $285 in 60 days - ACHIEVED EARLY!

3. MSFT (Microsoft Corp.)
   - Invested: $2,352.50 (5 shares @ $470.50)
   - Current: $2,517.50 ($503.50/share)
   - Gain: $165.00 (+7.01%)
   - Held: 22 days

Your portfolio is performing well! Tesla has already hit my target price 
52 days early. Would you like me to analyze whether to take profits or 
hold for further gains?
```

### Example 3: Analyzing Forecast Accuracy

**User**: "How accurate was your Tesla forecast?"

**Agent**:
```
Let me analyze my Tesla (TSLA) forecast vs. actual performance:

Original Recommendation (Feb 23, 2026):
- Purchase Price: $248.50
- Target Price: $285.00
- Timeframe: 60 days
- Expected Return: 14.7%

Actual Performance (8 days later):
- Current Price: $285.00
- Actual Return: 14.69%
- Time to Target: 8 days (52 days early!)

Forecast Accuracy:
- Return Prediction: 99.9% accurate
- Timing: Significantly faster than expected
- Outcome: OUTPERFORMED forecast

Analysis:
My forecast was highly accurate on the price target, but I underestimated 
the speed of the move. The faster-than-expected gains were driven by:
1. Surprise announcement of new battery technology
2. Major institutional buying
3. Broader market rally in tech stocks

Recommendation:
You've achieved the target return. Consider:
- Taking partial profits (sell 50% to lock in gains)
- Setting a stop-loss at $270 to protect profits
- Holding remainder for potential further upside

This successful forecast demonstrates the value of combining fundamental 
analysis with technical indicators. Would you like me to suggest the next 
investment opportunity?
```

---

## Part 9: Benefits & ROI

### For Users:
- ✅ Track all investments in one place
- ✅ See real-time performance
- ✅ Hold agent accountable for recommendations
- ✅ Learn from past decisions
- ✅ Data-driven investment decisions

### For Agent:
- ✅ Learn from outcomes
- ✅ Improve recommendation accuracy
- ✅ Build trust through transparency
- ✅ Demonstrate value over time
- ✅ Personalized insights based on user's history

### For Product:
- ✅ Differentiation from competitors
- ✅ Increased user engagement
- ✅ Data for improving AI models
- ✅ Premium feature potential
- ✅ Regulatory compliance (audit trail)

---

## Part 10: Future Enhancements

### Phase 2 Features:
1. **Automated Price Updates** - Lambda function to update prices daily
2. **Performance Alerts** - Notify when positions hit targets
3. **Tax Reporting** - Generate tax documents (1099-B equivalent)
4. **Portfolio Rebalancing** - Suggest rebalancing based on allocation
5. **Risk Metrics** - Calculate portfolio beta, VaR, Sharpe ratio
6. **Benchmark Comparison** - Compare against S&P 500, sector indices
7. **Export Functionality** - Export to CSV, PDF reports
8. **Mobile Notifications** - Push notifications for significant moves

---

## Summary

This implementation provides:
- ✅ Structured investment tracking
- ✅ Forecast vs. actual comparison
- ✅ Performance analytics
- ✅ Agent accountability
- ✅ User portfolio management

**Estimated Implementation Time**: 2-3 days
**Estimated Cost**: ~$5-10/month (DynamoDB + Lambda)

Ready to proceed with implementation?
