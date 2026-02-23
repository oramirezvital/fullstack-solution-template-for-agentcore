# Investment Portfolio Memory Strategy

## Overview
For an Investment Advisor agent that needs to track user investments and calculate earnings over time, we need a robust long-term memory strategy that goes beyond simple conversation history.

## Current State
Your agent currently has **short-term memory only** (conversation history):
```typescript
MemoryStrategies: [], // Empty = short-term only
```

## Recommended Approach: Hybrid Memory Strategy

### Option 1: AgentCore Long-Term Memory Strategies (RECOMMENDED)
Use AgentCore's built-in AI-powered memory strategies to automatically extract and store investment data.

#### Implementation:

**1. Enable Memory Strategies in CDK** (`infra-cdk/lib/backend-stack.ts`):

```typescript
const memory = new cdk.CfnResource(this, "AgentMemory", {
  type: "AWS::BedrockAgentCore::Memory",
  properties: {
    Name: cdk.Names.uniqueResourceName(this, { maxLength: 48 }),
    EventExpiryDuration: 90, // 90 days for investment tracking
    Description: `Investment portfolio memory for ${config.stack_name_base}`,
    MemoryStrategies: [
      {
        // Extract and store important facts (investments, transactions)
        SemanticMemoryStrategy: {
          Name: "InvestmentFactExtractor",
          Namespaces: ["/investments/{actorId}"],
        },
      },
      {
        // Learn user preferences (risk tolerance, sectors, strategies)
        UserPreferenceMemoryStrategy: {
          Name: "InvestorPreferenceLearner",
          Namespaces: ["/preferences/{actorId}"],
        },
      },
      {
        // Summarize investment sessions and decisions
        SummaryMemoryStrategy: {
          Name: "InvestmentSessionSummarizer",
          Namespaces: ["/summaries/{actorId}/{sessionId}"],
        },
      },
    ],
    MemoryExecutionRoleArn: agentRole.roleArn,
  },
});
```

**2. Update Agent Code** (`patterns/strands-single-agent/basic_agent.py`):

```python
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig
)

# Configure memory with retrieval from investment namespace
config = AgentCoreMemoryConfig(
    memory_id=memory_id,
    session_id=session_id,
    actor_id=user_id,
    retrieval_config={
        # Retrieve investment facts with high relevance
        "/investments/{actorId}": RetrievalConfig(
            top_k=50,  # Retrieve up to 50 investment records
            relevance_score=0.3  # Lower threshold to get all investments
        ),
        # Retrieve user preferences
        "/preferences/{actorId}": RetrievalConfig(
            top_k=10,
            relevance_score=0.5
        ),
    }
)

session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=config,
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
)
```

**3. Update System Prompt** to guide memory extraction:

```python
system_prompt = """You are an experienced Investment Advisor with long-term memory 
of user portfolios and investment decisions.

MEMORY MANAGEMENT:
When users tell you about investments they've made, ALWAYS acknowledge and confirm:
- Stock symbol
- Number of shares
- Purchase price per share
- Purchase date
- Total investment amount

Example: "I've recorded your investment: 100 shares of AAPL at $150.00 per share 
on 2024-01-15, total investment $15,000."

When users ask about their portfolio:
1. Retrieve their investment history from memory
2. Fetch current prices from Alpha Vantage
3. Calculate current value and gains/losses
4. Provide detailed performance analysis with charts

IMPORTANT: Your memory system will automatically extract and store investment facts 
from our conversations. Always be explicit about investment details so they're 
captured correctly.

Available Tools:
- Alpha Vantage: Real-time prices, historical data, fundamentals
- Code Interpreter: Calculate returns, generate portfolio charts
- Memory: Access user's investment history and preferences
"""
```

#### How It Works:

1. **User tells agent**: "I bought 100 shares of Apple at $150 on January 15, 2024"
2. **Agent confirms**: "Recorded: 100 AAPL @ $150.00 on 2024-01-15 = $15,000 invested"
3. **AI extracts fact**: SemanticMemoryStrategy automatically stores this in `/investments/{actorId}`
4. **Later, user asks**: "What's my portfolio performance?"
5. **Agent retrieves**: All investments from memory namespace
6. **Agent calculates**: 
   - Fetches current AAPL price from Alpha Vantage
   - Calculates: Current value = 100 × $current_price
   - Calculates: Gain/Loss = (current_value - $15,000) / $15,000 × 100%
7. **Agent visualizes**: Creates chart showing portfolio performance over time

#### Advantages:
✅ **AI-Powered Extraction**: Automatically identifies investment data from natural conversation
✅ **No Schema Required**: Flexible, handles various ways users describe investments
✅ **Cross-Session**: Data persists across all conversations
✅ **User-Scoped**: Each user has their own investment namespace
✅ **Semantic Search**: Can find investments by company name, sector, date range, etc.
✅ **AWS Managed**: No additional database infrastructure needed

#### Limitations:
⚠️ **Eventual Consistency**: Memory extraction happens asynchronously (slight delay)
⚠️ **No Transactions**: Can't guarantee ACID properties for financial data
⚠️ **Limited Querying**: Semantic search, not SQL-like queries
⚠️ **No Direct Updates**: Can't easily "edit" a stored investment (would add new fact)

---

### Option 2: DynamoDB for Structured Portfolio Data (ALTERNATIVE)

For more control and structured data, use DynamoDB alongside AgentCore Memory.

#### Implementation:

**1. Create DynamoDB Table** (`infra-cdk/lib/backend-stack.ts`):

```typescript
// Portfolio tracking table
const portfolioTable = new dynamodb.Table(this, "PortfolioTable", {
  partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
  sortKey: { name: "investmentId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  removalPolicy: cdk.RemovalPolicy.RETAIN, // Keep investment data
  pointInTimeRecovery: true, // Enable backups
});

// Add GSI for querying by symbol
portfolioTable.addGlobalSecondaryIndex({
  indexName: "SymbolIndex",
  partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
  sortKey: { name: "symbol", type: dynamodb.AttributeType.STRING },
});

// Grant agent access
portfolioTable.grantReadWriteData(agentRole);

// Store table name in environment
envVars.PORTFOLIO_TABLE_NAME = portfolioTable.tableName;
```

**2. Create Portfolio Management Tool** (`gateway/tools/portfolio_tool/portfolio_tool_lambda.py`):

```python
import boto3
import json
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['PORTFOLIO_TABLE_NAME'])

def lambda_handler(event, context):
    """
    Portfolio management tool for tracking investments.
    
    Operations:
    - add_investment: Record a new investment
    - get_portfolio: Retrieve all investments for a user
    - get_investment: Get specific investment details
    - update_investment: Modify an investment (e.g., add shares)
    - calculate_performance: Calculate gains/losses
    """
    operation = event.get('operation')
    user_id = event.get('userId')
    
    if operation == 'add_investment':
        return add_investment(
            user_id=user_id,
            symbol=event['symbol'],
            shares=Decimal(str(event['shares'])),
            purchase_price=Decimal(str(event['purchasePrice'])),
            purchase_date=event['purchaseDate'],
            notes=event.get('notes', '')
        )
    
    elif operation == 'get_portfolio':
        return get_portfolio(user_id)
    
    elif operation == 'calculate_performance':
        return calculate_performance(user_id, event.get('currentPrices', {}))
    
    # ... other operations

def add_investment(user_id, symbol, shares, purchase_price, purchase_date, notes):
    """Add a new investment to the portfolio"""
    investment_id = f"{symbol}_{purchase_date}_{datetime.now().timestamp()}"
    
    item = {
        'userId': user_id,
        'investmentId': investment_id,
        'symbol': symbol,
        'shares': shares,
        'purchasePrice': purchase_price,
        'purchaseDate': purchase_date,
        'totalInvested': shares * purchase_price,
        'notes': notes,
        'createdAt': datetime.now().isoformat(),
    }
    
    table.put_item(Item=item)
    return {'success': True, 'investment': item}

def get_portfolio(user_id):
    """Retrieve all investments for a user"""
    response = table.query(
        KeyConditionExpression='userId = :uid',
        ExpressionAttributeValues={':uid': user_id}
    )
    return {'investments': response['Items']}

def calculate_performance(user_id, current_prices):
    """Calculate portfolio performance with current prices"""
    portfolio = get_portfolio(user_id)
    
    results = []
    total_invested = Decimal('0')
    total_current = Decimal('0')
    
    for investment in portfolio['investments']:
        symbol = investment['symbol']
        shares = investment['shares']
        purchase_price = investment['purchasePrice']
        current_price = Decimal(str(current_prices.get(symbol, 0)))
        
        invested = shares * purchase_price
        current_value = shares * current_price
        gain_loss = current_value - invested
        gain_loss_pct = (gain_loss / invested * 100) if invested > 0 else 0
        
        results.append({
            'symbol': symbol,
            'shares': float(shares),
            'purchasePrice': float(purchase_price),
            'currentPrice': float(current_price),
            'invested': float(invested),
            'currentValue': float(current_value),
            'gainLoss': float(gain_loss),
            'gainLossPct': float(gain_loss_pct),
        })
        
        total_invested += invested
        total_current += current_value
    
    total_gain_loss = total_current - total_invested
    total_gain_loss_pct = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0
    
    return {
        'investments': results,
        'summary': {
            'totalInvested': float(total_invested),
            'totalCurrent': float(total_current),
            'totalGainLoss': float(total_gain_loss),
            'totalGainLossPct': float(total_gain_loss_pct),
        }
    }
```

**3. Register Tool in Gateway** (`gateway/tools/portfolio_tool/tool_spec.json`):

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Portfolio Management Tool",
    "version": "1.0.0",
    "description": "Track and analyze investment portfolios"
  },
  "servers": [
    {
      "url": "/"
    }
  ],
  "paths": {
    "/add_investment": {
      "post": {
        "summary": "Add a new investment to the portfolio",
        "operationId": "addInvestment",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "symbol": {"type": "string", "description": "Stock symbol (e.g., AAPL)"},
                  "shares": {"type": "number", "description": "Number of shares purchased"},
                  "purchasePrice": {"type": "number", "description": "Price per share at purchase"},
                  "purchaseDate": {"type": "string", "format": "date", "description": "Date of purchase (YYYY-MM-DD)"},
                  "notes": {"type": "string", "description": "Optional notes about the investment"}
                },
                "required": ["symbol", "shares", "purchasePrice", "purchaseDate"]
              }
            }
          }
        }
      }
    },
    "/get_portfolio": {
      "get": {
        "summary": "Retrieve all investments in the portfolio",
        "operationId": "getPortfolio"
      }
    },
    "/calculate_performance": {
      "post": {
        "summary": "Calculate portfolio performance with current prices",
        "operationId": "calculatePerformance",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "currentPrices": {
                    "type": "object",
                    "description": "Map of symbol to current price",
                    "additionalProperties": {"type": "number"}
                  }
                },
                "required": ["currentPrices"]
              }
            }
          }
        }
      }
    }
  }
}
```

**4. Agent Workflow**:

```python
# User: "I bought 100 shares of Apple at $150 on January 15, 2024"

# Agent calls portfolio tool:
await portfolio_tool.add_investment(
    symbol="AAPL",
    shares=100,
    purchase_price=150.00,
    purchase_date="2024-01-15"
)

# User: "What's my portfolio performance?"

# Agent workflow:
# 1. Get portfolio from DynamoDB
portfolio = await portfolio_tool.get_portfolio()

# 2. Fetch current prices from Alpha Vantage
current_prices = {}
for investment in portfolio['investments']:
    quote = await alpha_vantage.GLOBAL_QUOTE(symbol=investment['symbol'])
    current_prices[investment['symbol']] = quote['price']

# 3. Calculate performance
performance = await portfolio_tool.calculate_performance(
    current_prices=current_prices
)

# 4. Generate chart with Code Interpreter
chart = await code_interpreter.execute_python("""
import matplotlib.pyplot as plt
import pandas as pd

# Create performance visualization
# ... chart code ...
""")

# 5. Return analysis with chart
```

#### Advantages:
✅ **Structured Data**: Precise schema for financial data
✅ **ACID Transactions**: Reliable data consistency
✅ **Complex Queries**: GSI for filtering by symbol, date, etc.
✅ **Direct Updates**: Easy to modify investments
✅ **Immediate Consistency**: No extraction delay
✅ **Audit Trail**: Can track all changes with DynamoDB Streams
✅ **Backup & Recovery**: Point-in-time recovery enabled

#### Limitations:
⚠️ **More Infrastructure**: Need to manage DynamoDB table
⚠️ **Explicit Tool Calls**: Agent must explicitly call portfolio tools
⚠️ **Less Natural**: User must provide structured data
⚠️ **Additional Cost**: DynamoDB charges (though minimal with on-demand)

---

## Recommended Hybrid Approach

**Best of Both Worlds**: Combine AgentCore Memory + DynamoDB

### Architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Investment Advisor Agent                  │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
    ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
    │   AgentCore  │  │  DynamoDB   │  │Alpha Vantage │
    │    Memory    │  │  Portfolio  │  │     MCP      │
    │              │  │    Table    │  │              │
    │ - Preferences│  │ - Positions │  │ - Prices     │
    │ - Summaries  │  │ - Trades    │  │ - Indicators │
    │ - Context    │  │ - History   │  │ - Fundamentals│
    └──────────────┘  └─────────────┘  └──────────────┘
```

### Use Each For:

**AgentCore Memory (Semantic)**:
- User investment preferences (risk tolerance, sectors, strategies)
- Investment goals and objectives
- Conversation context and summaries
- Learning from past advice and decisions
- Natural language queries about portfolio

**DynamoDB (Structured)**:
- Precise investment positions (symbol, shares, price, date)
- Transaction history (buys, sells, dividends)
- Portfolio calculations and performance metrics
- Audit trail of all changes
- Structured queries and reports

**Alpha Vantage MCP**:
- Real-time market data
- Historical prices for performance calculation
- Technical indicators for analysis
- Fundamental data for research

### Implementation:

```python
system_prompt = """You are an Investment Advisor with access to:

1. PORTFOLIO DATABASE (DynamoDB):
   - Use portfolio_tool to record precise investment transactions
   - Always call add_investment when user reports a purchase
   - Call get_portfolio to retrieve current holdings
   - Call calculate_performance for returns analysis

2. MEMORY (AgentCore):
   - Your memory automatically learns user preferences
   - Recall past conversations and investment decisions
   - Remember user's risk tolerance and goals

3. MARKET DATA (Alpha Vantage):
   - Fetch real-time prices and quotes
   - Get historical data for analysis
   - Access technical indicators and fundamentals

WORKFLOW for "I bought 100 AAPL at $150 on 2024-01-15":
1. Call portfolio_tool.add_investment() to record in database
2. Confirm: "Recorded: 100 AAPL @ $150.00 on 2024-01-15"
3. Your memory will also learn this for context

WORKFLOW for "What's my portfolio performance?":
1. Call portfolio_tool.get_portfolio() to get holdings
2. For each holding, call Alpha Vantage GLOBAL_QUOTE for current price
3. Call portfolio_tool.calculate_performance() with current prices
4. Use Code Interpreter to create performance chart
5. Provide detailed analysis with visualization
"""
```

---

## Comparison Matrix

| Feature | AgentCore Memory Only | DynamoDB Only | Hybrid (Recommended) |
|---------|----------------------|---------------|---------------------|
| **Natural Language Input** | ✅ Excellent | ⚠️ Requires structure | ✅ Excellent |
| **Precise Calculations** | ⚠️ May have errors | ✅ Exact | ✅ Exact |
| **User Preferences** | ✅ AI-learned | ❌ Manual | ✅ AI-learned |
| **Transaction History** | ⚠️ Semantic only | ✅ Complete | ✅ Complete |
| **Cross-Session Memory** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Complex Queries** | ⚠️ Limited | ✅ Full SQL-like | ✅ Full SQL-like |
| **Infrastructure** | ✅ Minimal | ⚠️ Additional | ⚠️ Additional |
| **Data Consistency** | ⚠️ Eventual | ✅ Immediate | ✅ Immediate |
| **Cost** | $ | $$ | $$$ |
| **Setup Complexity** | Low | Medium | Medium-High |

---

## My Recommendation

**Start with Option 1 (AgentCore Memory Strategies)** for MVP:
- Fastest to implement (just update CDK config)
- Good enough for tracking investments
- Natural conversation flow
- Can always add DynamoDB later if needed

**Upgrade to Hybrid** when you need:
- Precise financial calculations
- Regulatory compliance / audit trails
- Complex portfolio analytics
- Multiple users with large portfolios
- Integration with external systems

---

## Next Steps

1. **Choose your approach** (I recommend starting with Option 1)
2. **I'll update the transformation plan** to include memory configuration
3. **Implement and test** with sample investments
4. **Iterate** based on accuracy and user experience

Which approach would you like to proceed with?
