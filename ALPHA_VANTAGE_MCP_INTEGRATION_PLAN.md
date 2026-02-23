# Alpha Vantage MCP Server Integration Plan

## Overview
Instead of using a custom Lambda tool, we can connect the agent directly to Alpha Vantage's official MCP server, which provides 100+ financial tools including stock data, technical indicators, fundamental data, and more.

## Current Architecture vs Proposed Architecture

### Current (Custom Lambda Tool):
```
Agent → AgentCore Gateway → Stock Tool Lambda → Alpha Vantage API
```

### Proposed (Direct MCP Connection):
```
Agent → Alpha Vantage MCP Server (https://mcp.alphavantage.co/mcp)
```

## Benefits of Using Alpha Vantage MCP Server

1. **100+ Tools Available**: Access to comprehensive financial data
   - Stock prices (TIME_SERIES_DAILY, GLOBAL_QUOTE, etc.)
   - Technical indicators (RSI, MACD, Bollinger Bands, etc.)
   - Fundamental data (COMPANY_OVERVIEW, EARNINGS, etc.)
   - Options data, Forex, Crypto, Commodities, Economic indicators

2. **No Lambda Maintenance**: No need to maintain custom Lambda code

3. **Progressive Tool Discovery**: Optimized token usage

4. **Always Up-to-Date**: Alpha Vantage maintains the server

5. **Standardized**: Official MCP implementation

## Integration Options

### Option 1: Connect Agent Directly to Alpha Vantage MCP (Recommended)
The Strands agent can connect to multiple MCP servers simultaneously.

**Implementation**:
- Modify `patterns/strands-single-agent/basic_agent.py`
- Add Alpha Vantage MCP server connection alongside the gateway
- Agent will have access to both gateway tools AND Alpha Vantage tools

**Pros**:
- Simple integration
- Keep existing gateway tools
- Access to 100+ Alpha Vantage tools
- No infrastructure changes

**Cons**:
- Agent connects to two MCP servers
- Slightly more complex agent code

### Option 2: Proxy Alpha Vantage MCP Through Gateway
Create a Lambda that acts as a proxy to Alpha Vantage MCP server.

**Implementation**:
- Create a Lambda that forwards requests to Alpha Vantage MCP
- Register it as a gateway target
- Agent only connects to gateway

**Pros**:
- Single connection point for agent
- Centralized tool management
- Can add custom logic/caching

**Cons**:
- More complex infrastructure
- Additional Lambda costs
- Adds latency

### Option 3: Replace Gateway with Alpha Vantage MCP Only
Remove the custom gateway entirely and use only Alpha Vantage MCP.

**Implementation**:
- Remove gateway infrastructure
- Connect agent directly to Alpha Vantage MCP
- Lose sample tools (text analysis)

**Pros**:
- Simplest architecture
- No gateway maintenance
- Lower AWS costs

**Cons**:
- Lose custom tools capability
- Less flexible for future tools

## Recommended Approach: Option 1

Connect the agent to both the gateway AND Alpha Vantage MCP server.

### Implementation Steps:

1. **Update Agent Code** (`patterns/strands-single-agent/basic_agent.py`)
   - Add Alpha Vantage MCP connection
   - Load tools from both servers
   - Combine tool lists

2. **Update Environment Variables**
   - Add `ALPHA_VANTAGE_MCP_URL` environment variable
   - Keep existing gateway configuration

3. **Test Integration**
   - Verify agent can access both tool sets
   - Test stock queries use Alpha Vantage tools
   - Ensure gateway tools still work

### Code Changes Required:

**File**: `patterns/strands-single-agent/basic_agent.py`

```python
# Add Alpha Vantage MCP connection
alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={ALPHA_VANTAGE_API_KEY}"

# Connect to both MCP servers
gateway_tools = await load_tools_from_gateway(gateway_url, access_token)
alpha_vantage_tools = await load_tools_from_mcp(alpha_vantage_url)

# Combine tools
all_tools = gateway_tools + alpha_vantage_tools
```

**File**: `infra-cdk/lib/backend-stack.ts`

```typescript
// Add Alpha Vantage API key to runtime environment
environment: {
  ALPHA_VANTAGE_API_KEY: "6I7SGM9D7G40YB1I",
  // ... other env vars
}
```

## Available Alpha Vantage Tools

Once integrated, the agent will have access to:

### Stock Data:
- TIME_SERIES_DAILY - Daily OHLCV data
- GLOBAL_QUOTE - Latest price and volume
- COMPANY_OVERVIEW - Company fundamentals
- EARNINGS - Earnings data
- NEWS_SENTIMENT - Market news with sentiment

### Technical Indicators:
- RSI - Relative Strength Index
- MACD - Moving Average Convergence Divergence
- BBANDS - Bollinger Bands
- SMA, EMA, WMA - Moving averages
- And 50+ more indicators

### Advanced Data:
- REALTIME_OPTIONS - Options data with Greeks
- INSIDER_TRANSACTIONS - Insider trading data
- EARNINGS_CALL_TRANSCRIPT - Earnings call transcripts
- TOP_GAINERS_LOSERS - Market movers

## Testing Plan

1. **Deploy Updated Agent**
   ```bash
   cd infra-cdk
   cdk deploy
   ```

2. **Test Stock Queries**
   - "What's the current price of Apple stock?"
   - "Show me the RSI for MSFT"
   - "Get company overview for GOOGL"

3. **Verify Gateway Tools Still Work**
   - Test text analysis tool
   - Ensure both tool sets are available

## Migration Path

### Phase 1: Add Alpha Vantage MCP (Keep Custom Tool)
- Implement Option 1
- Agent has access to both
- Test and validate

### Phase 2: Deprecate Custom Stock Tool (Optional)
- Remove custom stock Lambda
- Use only Alpha Vantage MCP for stock data
- Keep gateway for other custom tools

## Cost Comparison

### Current (Custom Lambda):
- Lambda invocations: ~$0.20 per 1M requests
- Lambda duration: ~$0.0000166667 per GB-second
- Gateway: Included in AgentCore pricing

### With Alpha Vantage MCP:
- Alpha Vantage API: Free tier (25 requests/day)
- Premium: $49.99/month (unlimited requests)
- No Lambda costs for stock tool

## Next Steps

1. **Confirm Approach**: Choose Option 1, 2, or 3
2. **Implement Changes**: Update agent code and infrastructure
3. **Deploy and Test**: Verify integration works
4. **Document**: Update README with new capabilities

---

**Recommendation**: Start with Option 1 to get the best of both worlds - keep your custom gateway for flexibility while gaining access to Alpha Vantage's comprehensive financial tools.
