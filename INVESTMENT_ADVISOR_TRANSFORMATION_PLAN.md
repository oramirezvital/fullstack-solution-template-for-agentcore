# Investment Advisor Transformation Plan

## Overview
Transform the current FinancialAgent into a dedicated Investment Advisor that focuses solely on Alpha Vantage financial data and includes chart visualization capabilities.

## Goals
1. Remove custom Gateway tools (sample_tool, stock_tool, text analysis)
2. Focus agent exclusively on Alpha Vantage MCP server
3. Add chart visualization feature for financial data
4. Update agent personality and system prompt for investment advisory role

## Current Architecture
```
Agent → Gateway MCP (custom tools) + Alpha Vantage MCP (financial tools)
```

## Proposed Architecture
```
Agent → Alpha Vantage MCP (financial tools only) + Code Interpreter (for charts)
```

## Changes Required

### 1. Agent Code Changes (`patterns/strands-single-agent/basic_agent.py`)
- **Remove**: Gateway MCP client creation and connection
- **Remove**: OAuth2 token retrieval for Gateway
- **Keep**: Alpha Vantage MCP client
- **Keep**: Code Interpreter for chart generation
- **Update**: System prompt to investment advisor personality
- **Update**: Agent name from "FinancialAgent" to "InvestmentAdvisor"

### 2. Infrastructure Changes (`infra-cdk/lib/backend-stack.ts`)
- **Remove**: Gateway infrastructure (createAgentCoreGateway method call)
- **Remove**: Sample tool Lambda and infrastructure
- **Remove**: Stock tool Lambda and infrastructure
- **Remove**: Gateway SSM parameters
- **Keep**: Runtime with Alpha Vantage API key
- **Keep**: Code Interpreter permissions
- **Keep**: Memory and authentication

### 3. Chart Visualization Feature
**Implementation Strategy**: Use Code Interpreter to generate charts from Alpha Vantage data

**Workflow**:
1. Agent fetches data from Alpha Vantage MCP (e.g., TIME_SERIES_DAILY)
2. Agent uses Code Interpreter to:
   - Process the data with pandas
   - Create charts with matplotlib/plotly
   - Return chart as base64 image or interactive HTML

**Example Use Cases**:
- "Show me a chart of Apple stock price for the last 3 months"
- "Plot the RSI indicator for Tesla"
- "Compare Microsoft and Google stock performance"
- "Show me a candlestick chart for Amazon"

### 4. System Prompt Updates
Transform from generic financial assistant to investment advisor:
- Focus on investment analysis and recommendations
- Emphasize risk assessment and portfolio considerations
- Provide context on market trends and indicators
- Use professional investment advisory language
- Always include disclaimers about investment risks

### 5. Frontend Updates (Optional)
- Update welcome screen prompts to investment-focused queries
- Update agent name display
- Ensure chart rendering works properly in ChatMessage component

## Files to Modify

### Critical Files:
1. `patterns/strands-single-agent/basic_agent.py` - Remove Gateway, update prompts
2. `infra-cdk/lib/backend-stack.ts` - Remove Gateway infrastructure
3. `patterns/strands-single-agent/requirements.txt` - Ensure matplotlib/plotly included

### Files to Review:
4. `frontend/src/components/chat/ChatMessage.tsx` - Verify chart rendering
5. `frontend/src/components/chat/ChatInterface.tsx` - Update welcome prompts

### Files to Remove (Optional Cleanup):
6. `gateway/tools/sample_tool/` - No longer needed
7. `gateway/tools/stock_tool/` - No longer needed
8. `test-scripts/test-stock-tool.py` - No longer needed

## Memory Strategy Integration

### Long-Term Memory for Portfolio Tracking
Using AgentCore Memory Strategies (Option 1) to automatically extract and store investment data:

**Memory Namespaces**:
- `/investments/{actorId}` - Investment facts (purchases, positions)
- `/preferences/{actorId}` - User preferences (risk tolerance, sectors)
- `/summaries/{actorId}/{sessionId}` - Session summaries

**How It Works**:
1. User: "I bought 100 shares of Apple at $150 on January 15, 2024"
2. Agent confirms and AI extracts fact to `/investments/{actorId}`
3. Later, user asks: "What's my portfolio performance?"
4. Agent retrieves investments from memory, fetches current prices, calculates returns

## Implementation Steps

### Phase 1: Memory Configuration
1. Update `basic_agent.py`:
   - Remove `create_gateway_mcp_client()` function
   - Remove `get_gateway_access_token()` import and usage
   - Remove Gateway MCP client from agent tools list
   - Update system prompt for investment advisor role
   - Add chart generation examples to system prompt
   - Rename agent to "InvestmentAdvisor"

### Phase 3: Infrastructure Cleanup
1. Update `backend-stack.ts`:
   - Comment out or remove `createAgentCoreGateway()` call
   - Remove SampleToolLambda infrastructure
   - Remove StockToolLambda infrastructure
   - Remove Gateway SSM parameters
   - Keep runtime environment with ALPHA_VANTAGE_API_KEY

### Phase 4: Chart Visualization
1. Verify Code Interpreter has matplotlib/plotly available
2. Update system prompt with chart generation instructions
3. Test chart generation with sample queries

### Phase 5: Frontend Updates
1. Update welcome screen with investment-focused prompts:
   - "Analyze Apple stock performance"
   - "Show me tech sector trends"
   - "Compare dividend stocks"
   - "Chart Bitcoin price history"

### Phase 6: Testing
1. Test Alpha Vantage data retrieval
2. Test chart generation with various data types
3. Test investment advisory responses
4. Verify Gateway removal doesn't break anything

## Chart Generation Technical Details

### Code Interpreter Capabilities:
- Python 3.x with pandas, numpy, matplotlib, plotly
- Can generate static images (PNG) or interactive charts (HTML)
- Returns base64-encoded images or HTML strings

### Example Chart Generation Prompt:
```
"Use the TIME_SERIES_DAILY data for AAPL and create a line chart showing 
the closing price for the last 90 days. Include volume as a bar chart below. 
Use matplotlib and return the chart as a base64 PNG image."
```

### Chart Types to Support:
- Line charts (price over time)
- Candlestick charts (OHLC data)
- Bar charts (volume, comparisons)
- Technical indicator overlays (RSI, MACD, Bollinger Bands)
- Multi-stock comparisons
- Correlation heatmaps

## Investment Advisor System Prompt (Draft)

```
You are an experienced Investment Advisor with access to comprehensive financial 
market data and analysis tools. Your role is to help users make informed investment 
decisions through data-driven insights.

Available Tools:
1. Alpha Vantage Financial Data (100+ tools):
   - Real-time and historical stock prices
   - Technical indicators (RSI, MACD, Bollinger Bands, Moving Averages)
   - Fundamental data (earnings, income statements, balance sheets)
   - Company overviews and financial metrics
   - Market news and sentiment analysis
   - Options data, Forex, Crypto, Commodities

2. Code Interpreter:
   - Generate professional charts and visualizations
   - Perform statistical analysis and calculations
   - Create comparative analyses and correlations
   - Build custom financial models

Your Approach:
- Always fetch current data before providing analysis
- Create visualizations to support your recommendations
- Explain technical indicators in accessible terms
- Consider both fundamental and technical analysis
- Discuss risk factors and market conditions
- Provide context on industry trends and comparisons

When analyzing investments:
1. Gather relevant financial data
2. Create charts to visualize trends
3. Analyze key metrics and indicators
4. Provide balanced insights with risk considerations
5. Suggest areas for further research

IMPORTANT DISCLAIMER: Always remind users that you provide information and 
analysis for educational purposes. Investment decisions should be made in 
consultation with qualified financial advisors, considering individual 
circumstances, risk tolerance, and financial goals.
```

## Risk Assessment

### Low Risk:
- Removing Gateway infrastructure (not critical to core functionality)
- Updating system prompts (easily reversible)
- Frontend welcome screen updates (cosmetic)

### Medium Risk:
- Removing custom tools (ensure no dependencies)
- Infrastructure changes (test thoroughly before production)

### Mitigation:
- Test in development environment first
- Keep Gateway code commented out initially (don't delete)
- Maintain ability to rollback via git
- Test all Alpha Vantage tools work correctly

## Success Criteria

1. ✅ Agent connects only to Alpha Vantage MCP (no Gateway)
2. ✅ Agent can generate charts from financial data
3. ✅ Agent provides investment advisory responses
4. ✅ All custom Gateway tools removed from infrastructure
5. ✅ Deployment succeeds without errors
6. ✅ Frontend displays charts correctly
7. ✅ User can ask investment questions and get data-driven answers

## Timeline Estimate

- Phase 1 (Agent Code): 15 minutes
- Phase 2 (Infrastructure): 15 minutes
- Phase 3 (Chart Testing): 10 minutes
- Phase 4 (Frontend): 10 minutes
- Phase 5 (Testing): 10 minutes
- **Total**: ~60 minutes

## Next Steps

1. Get user approval for this plan
2. Start with Phase 1 (Agent Code Transformation)
3. Test locally if possible
4. Deploy and verify
5. Update frontend
6. Final testing

---

**Ready to proceed?** Once approved, I'll start with Phase 1: transforming the agent code.
