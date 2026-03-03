# Multi-Agent Investment Advisor Architecture

## Overview

The Investment Advisor has been refactored from a single monolithic agent into an optimized multi-agent system using the **Hybrid ReWOO + Agents-as-Tools** pattern.

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│  ORCHESTRATOR (Claude 3.7 Sonnet)   │
│  Routes: simple → direct             │
│          analysis → ReWOO pipeline   │
└──────┬──────────────────────────────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
DIRECT   REWOO ANALYSIS PIPELINE
PATH     ┌──────────────────────────┐
         │ 1. PLANNER               │
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

## Agents

### 1. Orchestrator Agent
- **Model**: Claude 3.7 Sonnet (`us.anthropic.claude-3-7-sonnet-20250219-v1:0`)
- **Temperature**: 0.1
- **Role**: Routes queries to the appropriate path (direct or analysis pipeline)
- **Tools**: 
  - `market_data_specialist` - direct access to Alpha Vantage
  - `research_specialist` - direct access to Tavily
  - `portfolio_specialist` - direct access to DynamoDB
  - `run_investment_analysis` - triggers ReWOO pipeline

### 2. Market Data Agent
- **Model**: Claude 3.7 Sonnet
- **Temperature**: 0.0 (deterministic data retrieval)
- **Role**: Fetches real-time quotes, OHLCV, technical indicators, fundamentals
- **Tools**: Alpha Vantage MCP (100+ financial data endpoints)
- **Instantiation**: Lazy (created only when planner selects it)

### 3. Research Agent
- **Model**: Claude 3.7 Sonnet
- **Temperature**: 0.1 (slight creativity for synthesis)
- **Role**: Searches news, analyst reports, SEC filings, competitive intelligence
- **Tools**: Tavily MCP (web search with source citations)
- **Instantiation**: Lazy (created only when planner selects it)

### 4. Portfolio Agent
- **Model**: Claude 3.7 Sonnet
- **Temperature**: 0.0 (deterministic portfolio operations)
- **Role**: Records, views, updates, deletes, and exports investment transactions
- **Tools**: DynamoDB investment tracker (6 operations)
- **Instantiation**: Eager (always available for direct orchestrator calls)

### 5. Valuation Agent
- **Model**: Claude 3.7 Sonnet
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
| Price lookup | "What's AAPL price?" | Direct → Market Data | ~5s |
| News search | "Recent AAPL news?" | Direct → Research | ~8s |
| Portfolio action | "Record 10 AAPL @ $150" | Direct → Portfolio | ~5s |
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
│   ├── orchestrator_agent.py         # Hybrid ReWOO orchestrator
│   ├── market_data_agent.py          # Alpha Vantage specialist
│   ├── research_agent.py             # Tavily specialist
│   ├── portfolio_agent.py            # DynamoDB tracker specialist
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

**Simple (Direct Path - ~5s)**:
- "What's the current price of AAPL?"
- "Show me my portfolio performance"
- "Record 10 shares of TSLA at $250"

**Analysis (ReWOO Pipeline - ~30-45s)**:
- "Should I invest in NVDA at current prices?"
- "Analyze Microsoft as a long-term investment"
- "Compare AAPL vs GOOGL for my portfolio"

## Key Improvements vs Previous Design

| Aspect | Before | After |
|---|---|---|---|
| Agent instantiation | All 4 agents created upfront | Lazy (only when needed) |
| Simple queries | Routed through all agents | Direct path (no sub-agents) |
| Parallel execution | Sequential only | Market data + research concurrent |
| Valuation latency | 60-120s (temp=1) | 10-15s (temp=0.1) |
| API key retrieval | Every request | Cached per cold start |
| Expected latency (simple) | 60-120s | ~5s |
| Expected latency (analysis) | 120-180s | ~30-45s |

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

**Deployed**: 2026-03-02
**Model**: Claude 3.7 Sonnet (us.anthropic.claude-3-7-sonnet-20250219-v1:0)
**Pattern**: Hybrid ReWOO + Agents-as-Tools
**Status**: ✅ Production
