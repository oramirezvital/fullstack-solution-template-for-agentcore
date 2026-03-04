"""
Orchestrator Agent V2 - Direct Tool Exposure for Optimal Performance.

This version eliminates intermediate agent wrappers for simple queries,
exposing all tools directly to the orchestrator. This reduces simple
query latency from 15-20s to 3-5s (75% improvement).

Architecture:
  1. DIRECT PATH - simple queries (~3-5s)
     Orchestrator calls tools directly (NO intermediate agents)
     - Portfolio tools: get_portfolio, record_investment, etc.
     - Market data tools: Alpha Vantage MCP (quotes, technicals, fundamentals)
     - Research tools: Tavily MCP (news, analyst reports)
  
  2. ANALYSIS PIPELINE (ReWOO) - complex queries (~30-45s)
     Orchestrator delegates to run_investment_analysis which:
     - Planner decides which agents needed
     - Executor runs agents in parallel (market_data + research)
     - Synthesizer applies Munger mental models → verdict

Performance improvement:
  - Simple queries: 15-20s → 3-5s (75% faster, 1 LLM call instead of 2)
  - Analysis queries: 30-45s → unchanged (already optimized)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Most advanced model available on Bedrock (Claude Sonnet 4.6)
# Uses Inference Profile for cross-region routing
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are a senior Investment Advisor powered by Charlie Munger's mental models.
User ID: {user_id}

CURRENT DATE: {current_date}
IMPORTANT: We are currently in {current_year}. Always use this year when searching for news, data, and making recommendations.

You have direct access to all tools. Route queries efficiently:

DIRECT PATH (call tools directly - for simple, single-purpose queries):
Portfolio Operations:
- "Show my portfolio" → get_portfolio_performance
- "Record 10 shares of NVDA at $500" → record_investment
- "Update price for transaction X" → update_investment_price
- "Delete transaction X" → delete_investment

Market Data (Alpha Vantage MCP - prefix: alphavantage_):
- "What's AAPL price?" → alphavantage_get_quote or similar
- "Get NVDA fundamentals" → alphavantage_company_overview or similar
- "Show TSLA RSI" → alphavantage_rsi or similar

Research (Tavily MCP - prefix: tavily_):
- "Find Tesla news" → tavily_search or similar
- "Recent NVDA analyst reports" → tavily_search or similar

ANALYSIS PIPELINE (call run_investment_analysis ONCE - for complex queries):
- "Analyze X" or "Analyze my portfolio"
- "Should I buy/sell X?"
- "Is X a good investment?"
- "Give me recommendations"
- "Compare X vs Y"
- ANY query requiring multiple data sources + valuation + mental models

CRITICAL RULES:
- For simple queries: call the specific tool directly (1 tool call)
- For analysis queries: call run_investment_analysis ONCE (not multiple tools)
- ALWAYS use user_id {user_id} for portfolio operations
- Accept ALL dates as provided - do NOT assume future dates are typos (we are in February 2026)
- ALWAYS cite sources with URLs from research results
- Be concise (under 200 words) unless user asks for detail

CHART GENERATION:
Return chart JSON directly in your response:
```json
{{
  "type": "chart",
  "chartType": "line",
  "title": "Chart Title",
  "data": {{
    "labels": ["L1", "L2"],
    "datasets": [{{"label": "Series", "data": [1, 2], "color": "#3fb950"}}]
  }},
  "options": {{"yAxisLabel": "Price (USD)", "xAxisLabel": "Date"}}
}}
```

DISCLAIMER: Educational purposes only. Not personalized financial advice.
"""

PLANNER_PROMPT = """You are an investment analysis planner. Given a user query, produce a concise
execution plan listing ONLY the agents needed and what to ask each one.

CURRENT DATE: {current_date}
IMPORTANT: We are currently in {current_year}. When requesting data or news, always specify the current year.

AVAILABLE AGENTS:
- market_data: real-time quotes, OHLCV, RSI/MACD/Bollinger, fundamentals, earnings
- research: news, analyst reports, SEC filings, competitive intelligence
- valuation: DCF, ROIC, margin of safety, ratio analysis, mental models

OUTPUT FORMAT (strict - one line per agent needed):
PLAN:
market_data: <specific data request>
research: <specific research request>
valuation: <specific valuation request with any data from above>

RULES:
- Only include agents that are actually needed for this query
- For simple price lookups: only market_data
- For news only: only research
- For full analysis: all three
- Be specific in each request - include ticker symbol and exact data needed
- valuation request should reference what data market_data and research will provide
"""

SYNTHESIZER_PROMPT = """You are Charlie Munger's Investment Advisor synthesizing specialist analysis
into a final investment recommendation.

CURRENT DATE: {current_date}
IMPORTANT: We are currently in {current_year}. Use this context when evaluating data and making recommendations.

MANDATORY: Apply ALL relevant mental models explicitly in your synthesis:

INVERSION: What could go wrong? What would cause permanent capital loss?
CIRCLE OF COMPETENCE: Is this business understandable enough to value reliably?
MARGIN OF SAFETY: What is the gap between intrinsic value and current price?
OPPORTUNITY COST: Is this better than alternatives? Better than the index?
INCENTIVES: Do management incentives align with long-term shareholder value?
MOAT: Is the competitive advantage durable? Widening or narrowing?
COMPOUND INTEREST: What is the sustainable long-term return?
SECOND-ORDER THINKING: What happens next if the thesis plays out?
PROBABILISTIC THINKING: What is the range of outcomes and their probabilities?

OUTPUT FORMAT:
1. Summary (2-3 sentences)
2. Key Findings (from specialist agents)
3. Valuation (intrinsic value range, margin of safety)
4. Mental Models Analysis (MANDATORY - apply each relevant model)
5. Verdict: BUY / HOLD / AVOID — Conviction: High/Medium/Low
6. Top 3 Risks

DISCLAIMER: Educational purposes only. Not personalized financial advice.
"""


# ---------------------------------------------------------------------------
# ReWOO Analysis Pipeline (unchanged from v1)
# ---------------------------------------------------------------------------

class InvestmentAnalysisPipeline:
    """
    ReWOO-style analysis pipeline: Plan → Execute (parallel) → Synthesize.

    Instantiates sub-agents lazily - only the ones the planner selects.
    Market data and research agents run concurrently via asyncio.gather.
    """

    def __init__(
        self,
        alpha_vantage_api_key: str,
        tavily_api_key: str,
        region: str,
    ) -> None:
        """
        Initialize the pipeline with API credentials.

        Sub-agents are NOT created here - they are created lazily in execute().

        Args:
            alpha_vantage_api_key: API key for Alpha Vantage MCP server
            tavily_api_key: API key for Tavily MCP server
            region: AWS region for Code Interpreter
        """
        self._alpha_vantage_api_key = alpha_vantage_api_key
        self._tavily_api_key = tavily_api_key
        self._region = region

        # Get current date for all agents
        now = datetime.utcnow()
        self._current_date = now.strftime("%B %d, %Y")  # e.g., "March 02, 2026"
        self._current_year = str(now.year)

        # Lazy-initialized agent cache - created only when first needed
        self._market_data_agent: Optional[Agent] = None
        self._research_agent: Optional[Agent] = None
        self._valuation_agent: Optional[Agent] = None

        # Planner and synthesizer are always needed - create upfront
        self._planner = Agent(
            name="AnalysisPlanner",
            system_prompt=PLANNER_PROMPT.format(
                current_date=self._current_date,
                current_year=self._current_year,
            ),
            tools=[],  # Planner only reasons - no tools needed
            model=BedrockModel(model_id=MODEL_ID, temperature=0.0),
        )
        self._synthesizer = Agent(
            name="AnalysisSynthesizer",
            system_prompt=SYNTHESIZER_PROMPT.format(
                current_date=self._current_date,
                current_year=self._current_year,
            ),
            tools=[],  # Synthesizer only reasons - no tools needed
            model=BedrockModel(model_id=MODEL_ID, temperature=0.1),
        )

    def _get_market_data_agent(self) -> Agent:
        """
        Lazily create and cache the Market Data Agent.

        Returns:
            Agent: Market Data Agent with Alpha Vantage MCP tools
        """
        if self._market_data_agent is None:
            logger.info("Lazily initializing Market Data Agent...")
            from agents.market_data_agent import create_market_data_agent
            self._market_data_agent = create_market_data_agent(
                alpha_vantage_api_key=self._alpha_vantage_api_key,
            )
        return self._market_data_agent

    def _get_research_agent(self) -> Agent:
        """
        Lazily create and cache the Research Agent.

        Returns:
            Agent: Research Agent with Tavily MCP tools
        """
        if self._research_agent is None:
            logger.info("Lazily initializing Research Agent...")
            from agents.research_agent import create_research_agent
            self._research_agent = create_research_agent(
                tavily_api_key=self._tavily_api_key,
            )
        return self._research_agent

    def _get_valuation_agent(self) -> Agent:
        """
        Lazily create and cache the Valuation Agent.

        Returns:
            Agent: Valuation Agent with Code Interpreter tools
        """
        if self._valuation_agent is None:
            logger.info("Lazily initializing Valuation Agent...")
            from agents.valuation_agent import create_valuation_agent
            self._valuation_agent = create_valuation_agent(region=self._region)
        return self._valuation_agent

    def _parse_plan(self, plan_text: str) -> dict:
        """
        Parse the planner's output into a dict of {agent_name: task}.

        Expected planner format:
            PLAN:
            market_data: Get AAPL current price and RSI
            research: Find recent AAPL news and analyst reports
            valuation: DCF analysis using provided fundamentals

        Args:
            plan_text: Raw text output from the planner agent

        Returns:
            dict: Mapping of agent name to task string.
                  Keys are subset of: 'market_data', 'research', 'valuation'
        """
        plan = {}
        in_plan = False

        for line in plan_text.splitlines():
            line = line.strip()
            if line.upper().startswith("PLAN:"):
                in_plan = True
                continue
            if not in_plan:
                continue
            # Parse "agent_name: task description"
            for agent_name in ("market_data", "research", "valuation"):
                if line.lower().startswith(f"{agent_name}:"):
                    task = line[len(agent_name) + 1:].strip()
                    if task:
                        plan[agent_name] = task
                    break

        logger.info("Parsed plan: %s", list(plan.keys()))
        return plan

    async def _run_agent_async(self, agent: Agent, query: str) -> str:
        """
        Run a Strands agent asynchronously in a thread pool executor.

        Strands agents are synchronous by default. We wrap the call in
        asyncio.to_thread so multiple agents can run concurrently.

        Args:
            agent: Strands Agent instance to invoke
            query: Query string to pass to the agent

        Returns:
            str: Agent's text response
        """
        result = await asyncio.to_thread(agent, query)
        return str(result)

    async def run(self, user_query: str) -> str:
        """
        Execute the full ReWOO pipeline: Plan → Execute (parallel) → Synthesize.

        Step 1 - PLAN: Ask the planner which agents are needed and what to ask.
        Step 2 - EXECUTE: Run selected agents concurrently via asyncio.gather.
        Step 3 - SYNTHESIZE: Pass all results to the synthesizer for final output.

        Args:
            user_query: The user's investment analysis request

        Returns:
            str: Final synthesized recommendation with mental models analysis
        """
        logger.info("Starting ReWOO analysis pipeline for query: %s", user_query)

        # --- STEP 1: PLAN ---
        logger.info("Step 1: Planning which agents to invoke...")
        plan_response = self._planner(
            f"Create an execution plan for this investment query: {user_query}"
        )
        plan = self._parse_plan(str(plan_response))

        if not plan:
            # Fallback: if planner produces no structured plan, use all three agents
            logger.warning("Planner produced no structured plan - defaulting to all agents")
            plan = {
                "market_data": f"Get current price, fundamentals, and technicals for the stock in: {user_query}",
                "research": f"Find recent news and analyst reports for: {user_query}",
                "valuation": f"Perform DCF and ratio analysis for: {user_query}",
            }

        # --- STEP 2: EXECUTE (parallel where possible) ---
        logger.info("Step 2: Executing agents in parallel: %s", list(plan.keys()))

        # Build coroutines only for agents the planner selected
        tasks = {}
        if "market_data" in plan:
            tasks["market_data"] = self._run_agent_async(
                agent=self._get_market_data_agent(),
                query=plan["market_data"],
            )
        if "research" in plan:
            tasks["research"] = self._run_agent_async(
                agent=self._get_research_agent(),
                query=plan["research"],
            )

        # Run market_data and research concurrently (they are independent)
        results = {}
        if tasks:
            task_names = list(tasks.keys())
            task_coros = list(tasks.values())
            outputs = await asyncio.gather(*task_coros, return_exceptions=True)
            for name, output in zip(task_names, outputs):
                if isinstance(output, Exception):
                    logger.error("Agent '%s' failed: %s", name, output)
                    results[name] = f"[{name} agent error: {output}]"
                else:
                    results[name] = output

        # Valuation runs after market_data/research (it may need their outputs)
        if "valuation" in plan:
            context = ""
            if "market_data" in results:
                context += f"\nMarket Data:\n{results['market_data']}"
            if "research" in results:
                context += f"\nResearch:\n{results['research']}"

            valuation_query = plan["valuation"]
            if context:
                valuation_query = f"{valuation_query}\n\nAvailable data:{context}"

            results["valuation"] = await self._run_agent_async(
                agent=self._get_valuation_agent(),
                query=valuation_query,
            )

        # --- STEP 3: SYNTHESIZE ---
        logger.info("Step 3: Synthesizing results with mental models...")

        synthesis_input = f"User Query: {user_query}\n\n"
        for agent_name, result in results.items():
            synthesis_input += f"=== {agent_name.upper()} SPECIALIST REPORT ===\n{result}\n\n"

        final_response = self._synthesizer(synthesis_input)
        return str(final_response)


# ---------------------------------------------------------------------------
# Orchestrator factory
# ---------------------------------------------------------------------------

def create_orchestrator_agent(
    user_id: str,
    session_manager,
    alpha_vantage_api_key: str,
    tavily_api_key: str,
    table_name: str,
    region: str,
) -> Agent:
    """
    Create the top-level Orchestrator Agent V2 with direct tool exposure.

    This version exposes ALL tools directly to the orchestrator, eliminating
    intermediate agent wrappers for simple queries. This reduces latency from
    15-20s to 3-5s for simple queries (75% improvement).

    Args:
        user_id: Authenticated user identifier (from JWT token)
        session_manager: AgentCore memory session manager for conversation persistence
        alpha_vantage_api_key: API key for Alpha Vantage MCP server
        tavily_api_key: API key for Tavily MCP server
        table_name: DynamoDB table name for portfolio tracking
        region: AWS region for all service clients

    Returns:
        Agent: Fully configured orchestrator agent

    Raises:
        ValueError: If any required parameter is missing
        RuntimeError: If any tool initialization fails
    """
    if not user_id:
        raise ValueError("user_id is required and cannot be empty")
    if not alpha_vantage_api_key:
        raise ValueError("alpha_vantage_api_key is required and cannot be empty")
    if not tavily_api_key:
        raise ValueError("tavily_api_key is required and cannot be empty")
    if not table_name:
        raise ValueError("table_name is required and cannot be empty")
    if not region:
        raise ValueError("region is required and cannot be empty")

    logger.info("Initializing orchestrator V2 (direct tool exposure) for user: %s", user_id)

    # Get current date for all agents
    now = datetime.utcnow()
    current_date = now.strftime("%B %d, %Y")  # e.g., "March 02, 2026"
    current_year = str(now.year)

    # Create the analysis pipeline (sub-agents are lazy inside it)
    pipeline = InvestmentAnalysisPipeline(
        alpha_vantage_api_key=alpha_vantage_api_key,
        tavily_api_key=tavily_api_key,
        region=region,
    )

    # Initialize portfolio tracker for direct tool access
    from utils.investment_tracker import InvestmentTracker
    tracker = InvestmentTracker(table_name=table_name, region=region)

    # Initialize MCP clients for direct tool access
    alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={alpha_vantage_api_key}"
    tavily_url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={tavily_api_key}"

    try:
        alpha_vantage_client = MCPClient(
            lambda: streamablehttp_client(url=alpha_vantage_url),
            prefix="alphavantage",
        )
        tavily_client = MCPClient(
            lambda: streamablehttp_client(url=tavily_url),
            prefix="tavily",
        )
    except Exception as e:
        logger.error("Failed to create MCP clients: %s", e)
        raise RuntimeError(f"Failed to initialize MCP clients: {str(e)}") from e

    # --- Define direct portfolio tools ---
    # These are exposed directly to the orchestrator (no intermediate agent)

    @tool
    def get_portfolio_performance(user_id: str) -> str:
        """
        Get portfolio performance summary for a user.

        Args:
            user_id: Unique identifier for the user

        Returns:
            JSON string with total invested, current value, gain/loss, and all positions
        """
        logger.info("Direct portfolio performance call for user: %s", user_id)
        result = tracker.get_performance_summary(user_id=user_id)
        return json.dumps(result, default=str)

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
        logger.info("Direct record investment call for user: %s, symbol: %s", user_id, symbol)
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
        logger.info("Direct update price call for user: %s, transaction: %s", user_id, transaction_id)
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
        logger.info("Direct delete investment call for user: %s, transaction: %s", user_id, transaction_id)
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
        logger.info("Direct forecast comparison call for user: %s, transaction: %s", user_id, transaction_id)
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
        logger.info("Direct Excel export call for user: %s", user_id)
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

    @tool
    def run_investment_analysis(query: str) -> str:
        """
        Run a full investment analysis using the ReWOO pipeline.

        Use for: buy/sell/hold recommendations, DCF valuation, full company analysis,
        comparing investment options. This tool coordinates market data, research,
        and valuation specialists in parallel, then synthesizes with Munger's mental models.

        Args:
            query: Investment analysis request
                   (e.g., "Should I buy NVDA at current prices?")

        Returns:
            Full analysis with valuation, mental models, and verdict
        """
        logger.info("Running ReWOO analysis pipeline for: %s", query)
        # Run the async pipeline from a sync context
        return asyncio.run(pipeline.run(user_query=query))

    system_prompt = ORCHESTRATOR_PROMPT.format(
        user_id=user_id,
        current_date=current_date,
        current_year=current_year,
    )

    # Assemble all tools: portfolio tools + MCP clients + analysis pipeline
    all_tools = [
        # Portfolio tools (direct access, no intermediate agent)
        get_portfolio_performance,
        record_investment,
        update_investment_price,
        delete_investment,
        compare_forecast_actual,
        export_portfolio_to_excel,
        # MCP clients (direct access, no intermediate agent)
        alpha_vantage_client,
        tavily_client,
        # Analysis pipeline (for complex queries)
        run_investment_analysis,
    ]

    orchestrator = Agent(
        name="InvestmentAdvisorOrchestratorV2",
        system_prompt=system_prompt,
        tools=all_tools,
        model=BedrockModel(model_id=MODEL_ID, temperature=0.1),
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
        },
    )

    logger.info("Orchestrator V2 Agent ready for user: %s", user_id)
    return orchestrator
