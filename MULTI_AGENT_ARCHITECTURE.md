# Multi-Agent Investment Advisor Architecture

## Overview

The Investment Advisor has been refactored from a single monolithic agent into an optimized multi-agent system using the **Hybrid ReWOO + Agents-as-Tools** pattern.

## Architecture V2 (Direct Tool Exposure)

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  ORCHESTRATOR V2 (Claude Sonnet 4.6)                     │
│  Direct access to ALL tools (no intermediate agents)     │
│                                                           │
│  Tools:                                                   │
│  • Portfolio: get_portfolio, record_investment, etc.     │
│  • Market Data: Alpha Vantage MCP (100+ endpoints)       │
│  • Research: Tavily MCP (web search)                     │
│  • Analysis: run_investment_analysis (ReWOO pipeline)    │
└──────┬───────────────────────────────────────────────────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
DIRECT   REWOO ANALYSIS PIPELINE
TOOLS    ┌──────────────────────────┐
(1 LLM)  │ 1. PLANNER               │
         │    Decides which agents  │
         │    needed & what to ask  │
         │                          │
         │ 2. EXECUTOR (parallel)   │
         │    ├─ Market Data Agent  │
         │    ├─ Research Agent     │
         │    └─ Valuation Agent    │
         │                          │
         │ 3. SYNTHESIZER           │
         │    Applies Munger mental │
         │    models → verdict      │
         └──────────────────────────┘
```

**Key Change**: Simple queries now call tools directly (1 LLM call) instead of going through intermediate agents (2 LLM calls).

## Agents

### 1. Orchestrator Agent V2
- **Model**: Claude Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6`)
- **Temperature**: 0.1
- **Role**: Routes queries and executes tools directly (no intermediate agents for simple queries)
- **Direct Tools**: 
  - Portfolio: `get_portfolio_performance`, `record_investment`, `update_investment_price`, `delete_investment`, `compare_forecast_actual`, `export_portfolio_to_excel`
  - Market Data: Alpha Vantage MCP (100+ endpoints, prefix: `alphavantage_`)
  - Research: Tavily MCP (web search, prefix: `tavily_`)
  - Analysis: `run_investment_analysis` (triggers ReWOO pipeline)
- **Performance**: Simple queries now 1 LLM call instead of 2 (75% faster)

### 2. Market Data Agent
- **Model**: Claude Sonnet 4.6
- **Temperature**: 0.0 (deterministic data retrieval)
- **Role**: Fetches real-time quotes, OHLCV, technical indicators, fundamentals
- **Tools**: Alpha Vantage MCP (100+ financial data endpoints)
- **Instantiation**: Lazy (created only when planner selects it)

### 3. Research Agent
- **Model**: Claude Sonnet 4.6
- **Temperature**: 0.1 (slight creativity for synthesis)
- **Role**: Searches news, analyst reports, SEC filings, competitive intelligence
- **Tools**: Tavily MCP (web search with source citations)
- **Instantiation**: Lazy (created only when planner selects it)

### 4. Portfolio Agent
- **Model**: Claude Sonnet 4.6
- **Temperature**: 0.0 (deterministic portfolio operations)
- **Role**: Records, views, updates, deletes, and exports investment transactions
- **Tools**: DynamoDB investment tracker (6 operations)
- **Instantiation**: Eager (always available for direct orchestrator calls)

### 5. Valuation Agent
- **Model**: Claude Sonnet 4.6
- **Temperature**: 0.1 (NOT 1 - avoids extended thinking latency)
- **Role**: DCF models, ratio analysis, margin of safety, mental models application
- **Tools**: Code Interpreter (secure Python sandbox)
- **Instantiation**: Lazy (created only when planner selects it)

## Performance Optimizations

### 1. Lazy Agent Instantiation
Sub-agents in the ReWOO pipeline are created only when the planner selects them:
- Simple price lookup → only Market Data Agent created
- News search → only Research Agent created
- Full analysis → all three created

### 2. Parallel Execution
Market Data and Research agents run concurrently via `asyncio.gather`:
```python
tasks = {
    "market_data": run_agent_async(market_data_agent, query),
    "research": run_agent_async(research_agent, query),
}
results = await asyncio.gather(*tasks.values())
```

### 3. Module-Level API Key Caching
API keys retrieved once per Lambda cold start and cached:
```python
_cached_alpha_vantage_key: str | None = None
_cached_tavily_key: str | None = None
```

### 4. No Extended Thinking on Valuation
Valuation agent uses `temperature=0.1` (not `1`) with explicit reasoning instructions in the prompt. This avoids the 60-120s latency penalty of Claude 3.7's extended thinking mode while maintaining analysis quality.

### 5. Direct Path for Simple Queries
Simple queries bypass the multi-agent pipeline entirely:
- "What's AAPL price?" → orchestrator calls `market_data_specialist` directly (~5s)
- "Record my trade" → orchestrator calls `portfolio_specialist` directly (~5s)

## Query Routing

| Query Type | Example | Path | Expected Latency |
|---|---|---|---|
| Price lookup | "What's AAPL price?" | Direct → Alpha Vantage MCP | ~3-5s |
| News search | "Recent AAPL news?" | Direct → Tavily MCP | ~3-5s |
| Portfolio view | "Show my portfolio" | Direct → DynamoDB | ~3-5s |
| Portfolio action | "Record 10 AAPL @ $150" | Direct → DynamoDB | ~3-5s |
| Full analysis | "Should I buy NVDA?" | ReWOO Pipeline | ~30-45s |

## ReWOO Pipeline Flow

For full investment analysis queries:

1. **PLAN** (Planner Agent)
   - Input: User query
   - Output: Structured plan listing which agents to call and what to ask
   - Example:
     ```
     PLAN:
     market_data: Get NVDA current price, P/E, ROIC, revenue growth
     research: Find recent NVDA news and analyst reports
     valuation: DCF analysis using provided fundamentals
     ```

2. **EXECUTE** (Parallel + Sequential)
   - **Parallel**: Market Data + Research run concurrently
   - **Sequential**: Valuation runs after (uses outputs from above)
   - Each agent returns structured results

3. **SYNTHESIZE** (Synthesizer Agent)
   - Input: All specialist reports + user query
   - Output: Final recommendation with:
     - Summary
     - Key findings
     - Valuation (intrinsic value range, margin of safety)
     - **Mental Models Analysis** (MANDATORY)
     - Verdict: BUY / HOLD / AVOID
     - Top 3 risks

## Mental Models Framework

Every investment recommendation MUST explicitly apply:

1. **INVERSION**: What could go wrong? What would cause permanent capital loss?
2. **CIRCLE OF COMPETENCE**: Is this business understandable enough to value?
3. **MARGIN OF SAFETY**: What is the gap between intrinsic value and price?
4. **OPPORTUNITY COST**: Is this better than alternatives?
5. **INCENTIVES**: Do management incentives align with shareholders?
6. **MOAT**: Is the competitive advantage durable?
7. **COMPOUND INTEREST**: What is the sustainable long-term return?
8. **SECOND-ORDER THINKING**: What happens next if the thesis plays out?
9. **PROBABILISTIC THINKING**: What is the range of outcomes?
10. **SCALE ECONOMIES**: Does the business get stronger as it grows?

## File Structure

```
patterns/strands-single-agent/
├── basic_agent.py                    # Entrypoint (creates orchestrator)
├── agents/
│   ├── __init__.py
│   ├── orchestrator_agent.py         # Direct tool exposure orchestrator (V2)
│   ├── market_data_agent.py          # Alpha Vantage specialist (used in ReWOO only)
│   ├── research_agent.py             # Tavily specialist (used in ReWOO only)
│   ├── portfolio_agent.py            # DynamoDB tracker specialist (used in ReWOO only)
│   └── valuation_agent.py            # Code Interpreter + DCF specialist
├── requirements.txt
└── Dockerfile
```

## Deployment

Deployed with CDK using `docker` artifact type:
```bash
cd infra-cdk
cdk deploy --require-approval never
```

**Note**: AgentCore Runtime does not support changing artifact type (docker ↔ zip) on existing runtimes. The runtime must be destroyed and recreated to change types.

## Testing

Test the system with queries of varying complexity:

**Simple (Direct Tools - ~3-5s)**:
- "What's the current price of AAPL?"
- "Show me my portfolio performance"
- "Give me my portfolio details"
- "Record 10 shares of TSLA at $250"
- "Find recent Tesla news"

**Analysis (ReWOO Pipeline - ~30-45s)**:
- "Should I invest in NVDA at current prices?"
- "Analyze Microsoft as a long-term investment"
- "Compare AAPL vs GOOGL for my portfolio"
- "Analyze my portfolio and give me recommendations"

## Key Improvements vs Previous Design

| Aspect | V1 (Before) | V2 (After) | Improvement |
|---|---|---|---|
| Simple query architecture | Orchestrator → Agent → Tool (2 LLM calls) | Orchestrator → Tool (1 LLM call) | 75% faster |
| Agent instantiation | Eager (all agents created upfront) | Lazy (only when needed) | Lower cold start |
| Simple queries latency | 15-20s | 3-5s | **75% faster** |
| Analysis queries latency | 30-45s | 30-45s | Unchanged (already optimized) |
| Parallel execution | Market data + research concurrent | Market data + research concurrent | Unchanged |
| API key retrieval | Cached per cold start | Cached per cold start | Unchanged |
| Tool exposure | Via intermediate agents | Direct to orchestrator | Simpler architecture |

## Monitoring

CloudWatch logs show agent routing decisions:
```
[INFO] Direct market data call: Get AAPL price
[INFO] Running ReWOO analysis pipeline for: Should I buy NVDA?
[INFO] Lazily initializing Market Data Agent...
[INFO] Lazily initializing Research Agent...
[INFO] Lazily initializing Valuation Agent...
```

## Future Enhancements

1. **Caching**: Cache market data responses for 1-5 minutes to avoid redundant API calls
2. **Streaming**: Stream partial results from each agent as they complete
3. **Fallback**: If one agent fails, continue with available results
4. **Confidence Scoring**: Track which mental models have highest predictive accuracy
5. **A/B Testing**: Compare single-agent vs multi-agent recommendations

---

**Deployed**: 2026-03-03 (V2: Direct Tool Exposure)
**Model**: Claude Sonnet 4.6 (us.anthropic.claude-sonnet-4-6)
**Pattern**: Hybrid ReWOO + Direct Tool Exposure
**Performance**: Simple queries 3-5s (75% faster than V1), Analysis queries 30-45s
**Status**: ✅ Production
