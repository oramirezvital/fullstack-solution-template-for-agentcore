# Multi-Agent Architecture Performance Fix Plan

## Problem Analysis

### Current Architecture Issues

**Simple query "give me my portfolio details" takes 15-20 seconds because:**

1. **Orchestrator LLM call** (~3-5s): Decides to use `portfolio_specialist` tool
2. **Portfolio Agent LLM call** (~3-5s): Decides to use `get_portfolio_performance` tool  
3. **DynamoDB query** (~1-2s): Actual data retrieval
4. **Portfolio Agent response generation** (~2-3s): Formats the response
5. **Orchestrator response generation** (~2-3s): Passes through or reformats

**Total: 11-18 seconds for a simple database lookup!**

### Root Cause

The orchestrator creates FULL AGENT INSTANCES for direct tools:
```python
_portfolio_agent = create_portfolio_agent(...)  # Full agent with LLM

@tool
def portfolio_specialist(query: str) -> str:
    return str(_portfolio_agent(query))  # ← Invokes FULL AGENT (LLM call)
```

This defeats the purpose of the "direct path" - we're still going through 2 LLM layers.

## Proposed Solution: Tool-Only Direct Path

### Architecture Change

**BEFORE (Current - 2 LLM calls)**:
```
User: "show my portfolio"
  ↓
Orchestrator Agent (LLM) → decides: portfolio_specialist
  ↓
Portfolio Agent (LLM) → decides: get_portfolio_performance
  ↓
DynamoDB → returns data
```

**AFTER (Proposed - 1 LLM call)**:
```
User: "show my portfolio"
  ↓
Orchestrator Agent (LLM) → decides: get_portfolio_performance_direct
  ↓
DynamoDB → returns data (NO intermediate agent)
```

### Implementation Strategy

**Option 1: Direct Tool Exposure (RECOMMENDED)**
- Expose ALL underlying tools directly to the orchestrator
- Remove intermediate agent wrappers for direct path
- Keep agent wrappers ONLY for ReWOO pipeline

**Option 2: Smart Tool Routing**
- Orchestrator has both direct tools AND agent wrappers
- Prompt explicitly tells it: use direct tools for simple queries
- Use agent wrappers only for complex analysis

**Option 3: Hybrid with Tool Categories**
- Group tools by category (portfolio, market_data, research)
- Direct tools for CRUD operations
- Agent wrappers for analysis/synthesis

## Recommended Implementation: Option 1

### Changes Required

#### 1. Orchestrator Tool Definitions

**REMOVE** agent wrapper tools:
```python
# ❌ DELETE THIS
@tool
def portfolio_specialist(query: str) -> str:
    return str(_portfolio_agent(query))
```

**ADD** direct tool exposure:
```python
# ✅ ADD THIS
@tool
def get_portfolio_performance(user_id: str) -> str:
    """Get portfolio performance summary directly."""
    result = tracker.get_performance_summary(user_id=user_id)
    return json.dumps(result, default=str)

@tool
def record_investment(user_id: str, symbol: str, ...) -> str:
    """Record investment transaction directly."""
    result = tracker.record_investment(...)
    return json.dumps(result, default=str)
```

#### 2. Orchestrator Prompt Update

**BEFORE**:
```
TOOLS AVAILABLE:
• portfolio_specialist - record/view/delete/export portfolio
```

**AFTER**:
```
DIRECT TOOLS (use these for simple queries):
• get_portfolio_performance(user_id) - view portfolio summary
• record_investment(user_id, symbol, ...) - record new transaction
• update_investment_price(user_id, transaction_id, price) - update price
• delete_investment(user_id, transaction_id) - delete transaction
• get_stock_quote(symbol) - get current price
• search_news(query) - search investment news

ANALYSIS TOOLS (use for complex queries):
• run_investment_analysis(query) - full ReWOO pipeline with mental models
```

#### 3. Agent Instantiation Strategy

**BEFORE** (eager instantiation):
```python
_portfolio_agent = create_portfolio_agent(...)  # Created upfront
_market_agent = create_market_data_agent(...)   # Created upfront
_research_agent = create_research_agent(...)    # Created upfront
```

**AFTER** (no agents for direct path):
```python
# Create tool instances directly (no agent wrappers)
tracker = InvestmentTracker(table_name=table_name, region=region)
# MCP tools will be exposed directly via Strands MCP integration
```

### Expected Performance Improvement

| Query Type | Before | After | Improvement |
|---|---|---|---|
| "Show my portfolio" | 15-20s | 3-5s | **75% faster** |
| "What's AAPL price?" | 10-15s | 3-5s | **70% faster** |
| "Record 10 AAPL @ $150" | 15-20s | 3-5s | **75% faster** |
| "Analyze NVDA" | 30-45s | 30-45s | No change (already optimized) |

### Implementation Steps

1. **Create new orchestrator with direct tools** (orchestrator_agent_v2.py)
2. **Test with simple queries** to verify 1 LLM call only
3. **Update basic_agent.py** to use new orchestrator
4. **Deploy and test** on frontend
5. **Monitor CloudWatch logs** to confirm single LLM call
6. **Update MULTI_AGENT_ARCHITECTURE.md** with new design

### Risks & Mitigation

**Risk 1**: Too many tools overwhelm the orchestrator
- **Mitigation**: Group tools logically, use clear naming conventions

**Risk 2**: Orchestrator makes wrong tool choices
- **Mitigation**: Explicit prompt instructions with examples

**Risk 3**: Loss of agent-level reasoning for edge cases
- **Mitigation**: Keep agent wrappers available for ReWOO pipeline

## Alternative: Simpler Single-Agent with Smart Routing

If the above is too complex, consider:

**Flatten to single agent with smart tool routing**:
- One agent with ALL tools exposed directly
- Prompt-based routing (simple vs analysis)
- No sub-agents at all
- Expected latency: 3-5s for simple, 15-20s for analysis

This is simpler but loses the ReWOO parallel execution benefit.

## Decision Required

**Which approach do you prefer?**

1. **Option 1**: Direct tool exposure (recommended, 75% faster for simple queries)
2. **Option 2**: Smart tool routing (moderate improvement, 50% faster)
3. **Option 3**: Flatten to single agent (simplest, 60% faster)

Let me know and I'll implement immediately.
