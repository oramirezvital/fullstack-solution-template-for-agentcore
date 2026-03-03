"""
Orchestrator Agent - Hybrid ReWOO + Agents-as-Tools investment advisor.

Routes queries through two paths for optimal latency:
  1. DIRECT PATH  - simple lookups / portfolio actions (~5s)
     Orchestrator calls tools directly without spinning up sub-agents.
  2. ANALYSIS PIPELINE (ReWOO) - full investment analysis (~30-45s)
     Planner decides which sub-agents are needed → Executor calls only
     those agents (lazily, in parallel where possible) → Synthesizer
     applies Munger's mental models and produces the final recommendation.

Sub-agents are instantiated lazily (only when the planner selects them)
to avoid paying initialization cost for agents that aren't needed.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from strands import Agent, tool
from strands.models import BedrockModel

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

You coordinate a team of specialist agents. Route every query through the correct path:

DIRECT PATH (call tools yourself, no sub-agents):
- Stock price / quote lookups
- Portfolio record / view / delete / export actions
- Simple news searches
- Chart generation from already-available data

ANALYSIS PIPELINE (call run_investment_analysis):
- "Should I buy/sell X?"
- "Analyze X for me"
- "Is X a good investment?"
- "Compare X vs Y"
- Any request requiring valuation, DCF, or mental models synthesis

TOOLS AVAILABLE (direct path):
• market_data_specialist  - real-time quotes, technicals, fundamentals
• research_specialist     - news, analyst reports, web search
• portfolio_specialist    - record/view/delete/export portfolio (always pass user_id={user_id})
• run_investment_analysis - full ReWOO analysis pipeline (use for recommendations)

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

CRITICAL RULES:
- ALWAYS use user_id {user_id} for portfolio operations
- Accept ALL dates as provided - do NOT assume future dates are typos (we are in February 2026)
- ALWAYS cite sources with URLs from research results
- Be concise (under 200 words) unless user asks for detail

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
# ReWOO Analysis Pipeline
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
    Create the top-level Orchestrator Agent with hybrid ReWOO routing.

    The orchestrator exposes four direct tools (market data, research, portfolio,
    and the full analysis pipeline). Simple queries are handled directly; complex
    analysis queries are routed through the ReWOO pipeline which lazily instantiates
    only the sub-agents needed.

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
        RuntimeError: If any agent or tool initialization fails
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

    logger.info("Initializing orchestrator for user: %s", user_id)

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

    # Create direct-access agents for the orchestrator's own tool calls.
    # These are created upfront because the orchestrator uses them for simple queries.
    from agents.market_data_agent import create_market_data_agent
    from agents.research_agent import create_research_agent
    from agents.portfolio_agent import create_portfolio_agent

    _market_agent = create_market_data_agent(alpha_vantage_api_key=alpha_vantage_api_key)
    _research_agent = create_research_agent(tavily_api_key=tavily_api_key)
    _portfolio_agent = create_portfolio_agent(table_name=table_name, region=region)

    # --- Define orchestrator tools ---
    # Each tool wraps a specialist agent or the analysis pipeline.

    @tool
    def market_data_specialist(query: str) -> str:
        """
        Retrieve real-time market data, quotes, technical indicators, and fundamentals.

        Use for: stock prices, OHLCV, RSI/MACD/Bollinger Bands, earnings, options,
        forex, crypto, commodities, economic indicators.

        Args:
            query: Specific data request (e.g., "Get AAPL current price and 14-day RSI")

        Returns:
            Structured market data with exact values and timestamps
        """
        logger.info("Direct market data call: %s", query)
        return str(_market_agent(query))

    @tool
    def research_specialist(query: str) -> str:
        """
        Search for investment news, analyst reports, and qualitative intelligence.

        Use for: latest news, analyst upgrades/downgrades, earnings summaries,
        SEC filings, competitive analysis, industry trends.
        Always cite sources with URLs.

        Args:
            query: Research request (e.g., "Find recent AAPL news and analyst views")

        Returns:
            Research summary with cited sources and URLs
        """
        logger.info("Direct research call: %s", query)
        return str(_research_agent(query))

    @tool
    def portfolio_specialist(query: str) -> str:
        """
        Manage portfolio records: record, view, update, delete, and export investments.

        Use for: recording new trades, viewing performance, updating prices,
        deleting transactions, comparing forecast vs actual, exporting to Excel.
        Always include the user_id in the query.

        Args:
            query: Portfolio request including user_id
                   (e.g., "Record 10 shares of AAPL at $150 for user abc123")

        Returns:
            Portfolio operation confirmation or performance summary
        """
        logger.info("Direct portfolio call: %s", query)
        return str(_portfolio_agent(query))

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

    orchestrator = Agent(
        name="InvestmentAdvisorOrchestrator",
        system_prompt=system_prompt,
        tools=[
            market_data_specialist,
            research_specialist,
            portfolio_specialist,
            run_investment_analysis,
        ],
        model=BedrockModel(model_id=MODEL_ID, temperature=0.1),
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
        },
    )

    logger.info("Orchestrator Agent ready for user: %s", user_id)
    return orchestrator
