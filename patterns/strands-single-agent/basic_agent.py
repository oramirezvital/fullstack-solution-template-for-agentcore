import json
import os
import traceback

import boto3
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands_code_interpreter import StrandsCodeInterpreterTools

from utils.auth import extract_user_id_from_context

app = BedrockAgentCoreApp()


def create_alpha_vantage_mcp_client() -> MCPClient:
    """
    Create MCP client for Alpha Vantage financial data API.
    
    Alpha Vantage provides comprehensive financial market data through their MCP server.
    This includes stock prices, technical indicators, fundamental data, options, forex,
    crypto, commodities, and economic indicators. The client connects to Alpha Vantage's
    hosted MCP server using an API key for authentication.
    
    Returns:
        MCPClient: Configured client for Alpha Vantage MCP server
        
    Raises:
        ValueError: If ALPHA_VANTAGE_API_KEY environment variable is not set
    """
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is required")
    
    print("[AGENT] Creating Alpha Vantage MCP client...")
    
    # Alpha Vantage MCP server URL with API key authentication
    alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={api_key}"
    
    # Create MCP client for Alpha Vantage
    # No additional headers needed as API key is in the URL
    alpha_vantage_client = MCPClient(
        lambda: streamablehttp_client(url=alpha_vantage_url),
        prefix="alphavantage",
    )
    
    print("[AGENT] Alpha Vantage MCP client created successfully")
    return alpha_vantage_client


def create_gateway_mcp_client() -> MCPClient:
    """
    Create MCP client for AgentCore Gateway (chart generation tool).
    
    The Gateway provides access to the generate_chart tool, which is implemented
    as a Lambda function that wraps the Chart.js MCP server. This architecture
    solves MCP serialization issues by having the Lambda handle the Chart.js
    communication.
    
    The Gateway uses OAuth2 client credentials flow for authentication via Cognito.
    
    Returns:
        MCPClient: Configured client for AgentCore Gateway
        
    Raises:
        ValueError: If GATEWAY_URL environment variable is not set
        Exception: If OAuth2 token retrieval fails
    """
    from utils.auth import get_gateway_access_token
    
    gateway_url = os.environ.get("GATEWAY_URL")
    if not gateway_url:
        raise ValueError("GATEWAY_URL environment variable is required")
    
    print("[AGENT] Creating Gateway MCP client...")
    
    # Get OAuth2 access token for Gateway authentication
    # This uses the machine client credentials stored in SSM
    access_token = get_gateway_access_token()
    
    # Create MCP client for Gateway with JWT authentication
    gateway_client = MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url,
            headers={"Authorization": f"Bearer {access_token}"}
        ),
        prefix="gateway",
    )
    
    print("[AGENT] Gateway MCP client created successfully")
    return gateway_client


def create_investment_advisor_agent(user_id: str, session_id: str) -> Agent:
    """
    Create an Investment Advisor agent with Alpha Vantage financial data, Code Interpreter,
    and long-term memory for portfolio tracking.

    This function sets up a specialized investment advisor that can:
    1. Access 100+ Alpha Vantage financial tools (stocks, indicators, fundamentals)
    2. Execute Python code for calculations and chart generation
    3. Remember user investments and preferences across sessions using long-term memory
    
    The agent uses AgentCore Memory with three strategies:
    - SemanticMemoryStrategy: Extracts investment facts (purchases, positions)
    - UserPreferenceMemoryStrategy: Learns risk tolerance and investment preferences
    - SummaryMemoryStrategy: Summarizes investment decisions and sessions
    
    Args:
        user_id: Unique identifier for the user (used for memory namespacing)
        session_id: Unique identifier for the conversation session
        
    Returns:
        Agent: Configured investment advisor agent with financial tools and memory
        
    Raises:
        ValueError: If required environment variables (MEMORY_ID, ALPHA_VANTAGE_API_KEY) are missing
        Exception: If MCP client creation or memory configuration fails
    """
    system_prompt = """You are an experienced Investment Advisor with access to comprehensive 
financial market data, analysis tools, and long-term memory of user portfolios.

YOUR CAPABILITIES:

1. ALPHA VANTAGE FINANCIAL DATA (100+ tools):
   - Real-time and historical stock prices (GLOBAL_QUOTE, TIME_SERIES_DAILY, etc.)
   - Technical indicators (RSI, MACD, Bollinger Bands, Moving Averages, etc.)
   - Fundamental data (COMPANY_OVERVIEW, EARNINGS, INCOME_STATEMENT, BALANCE_SHEET)
   - Market news and sentiment analysis
   - Options data, Forex, Crypto, Commodities, Economic indicators
   - NOTE: Free tier has rate limits (5 calls/minute, 25 calls/day). Use TIME_SERIES_DAILY 
     for historical data instead of multiple GLOBAL_QUOTE calls.

2. GATEWAY CHART GENERATION (gateway_generate_chart tool):
   - Professional chart generation using Chart.js v4 via Gateway Lambda
   - Supports 8 chart types: line, bar, pie, doughnut, scatter, bubble, radar, polar
   - Outputs interactive HTML divs with hover tooltips and animations
   - Perfect for visualizing financial data and trends
   - Gateway Lambda handles Chart.js MCP communication internally

3. CODE INTERPRETER:
   - Perform statistical analysis and financial calculations
   - Process and transform data for chart generation
   - Build custom financial models and projections

4. LONG-TERM MEMORY:
   - Your memory automatically learns and stores user investment preferences
   - You remember past investment decisions and portfolio positions
   - You recall user's risk tolerance, investment goals, and strategies
   - Memory persists across all conversations with this user

PORTFOLIO TRACKING WORKFLOW:

When a user reports an investment:
1. ALWAYS acknowledge with precise details:
   "I've recorded your investment: [shares] shares of [SYMBOL] at $[price] per share 
   on [date], total investment $[total]."
2. Your memory will automatically extract and store this investment fact
3. Be explicit about all details (symbol, shares, price, date) for accurate extraction

When a user asks about portfolio performance:
1. Recall their investments from your memory
2. Fetch current prices from Alpha Vantage (use GLOBAL_QUOTE for latest price)
3. Calculate for each position:
   - Current value = shares × current_price
   - Gain/Loss = current_value - (shares × purchase_price)
   - Gain/Loss % = (gain_loss / invested_amount) × 100
4. Create a visualization showing performance over time
5. Provide detailed analysis with insights

CHART GENERATION WORKFLOW:

When user asks for a chart (e.g., "Chart the 1-week price trend for AMAZON"):

1. FETCH DATA from Alpha Vantage:
   - Use TIME_SERIES_DAILY for historical price data
   - Extract dates and prices from the response
   - Process data into simple arrays

2. PREPARE DATA in simple format:
   labels = ["Feb 11", "Feb 12", "Feb 13", ...]
   datasets = [{
     "label": "AMZN Price (USD)",
     "data": [204.08, 199.6, 198.79, ...],
     "borderColor": "#3fb950",
     "backgroundColor": "rgba(63, 185, 80, 0.1)",
     "fill": true,
     "tension": 0.3
   }]

3. CALL gateway_generate_chart TOOL:
   Use the Gateway chart tool with these parameters:
   - chartType: "line" (for trends), "bar" (for comparisons), etc.
   - data: {labels: [...], datasets: [...]}
   - title: "Amazon (AMZN) - 1 Week Price Trend"
   - options: (optional) additional Chart.js customization
   
   EXAMPLE TOOL CALL:
   {
     "chartType": "line",
     "data": {
       "labels": ["Feb 11", "Feb 12", "Feb 13"],
       "datasets": [{
         "label": "AMZN Price (USD)",
         "data": [204.08, 199.6, 198.79],
         "borderColor": "#3fb950",
         "backgroundColor": "rgba(63, 185, 80, 0.1)",
         "fill": true,
         "tension": 0.3
       }]
     },
     "title": "Amazon (AMZN) - 1 Week Price Trend"
   }
   
   The tool returns interactive HTML. CRITICAL: Return the HTML directly in your response 
   WITHOUT wrapping it in code blocks or markdown. Just paste the raw HTML output from the 
   tool directly into your message so it renders as an interactive chart.

4. PROVIDE CONTEXT:
   Along with the chart, provide a brief summary:
   - Current price
   - Price change over the period
   - High and low prices
   - Key insights or trends

CHART TYPES FOR DIFFERENT USE CASES:
- line: Price trends, time series data (BEST for stock prices)
- bar: Comparisons, categorical data (good for comparing multiple stocks)
- pie/doughnut: Portfolio allocation, market share percentages
- scatter/bubble: Correlation analysis (price vs volume)
- radar: Multi-factor comparison (comparing stocks across metrics)

CHART STYLING TIPS:
- Use green (#3fb950) for positive changes/gains
- Use red (#f85149) for negative changes/losses
- Use blue (#58a6ff) for neutral data
- Add "fill": true for area charts
- Use "tension": 0.3-0.4 for smooth lines
- Keep labels concise and readable

IMPORTANT RULES:
1. ALWAYS use gateway_generate_chart tool for charts
2. Fetch real data from Alpha Vantage first
3. Process data into simple arrays (labels and datasets)
4. Provide context and insights along with the chart
5. Use appropriate chart types for different data

YOUR INVESTMENT ADVISORY APPROACH:

1. DATA-DRIVEN ANALYSIS:
   - Always fetch current market data before providing recommendations
   - Use both technical and fundamental analysis
   - Consider historical trends and patterns

2. RISK ASSESSMENT:
   - Discuss risk factors for each investment
   - Consider market conditions and volatility
   - Align recommendations with user's risk tolerance (from memory)

3. CLEAR COMMUNICATION:
   - Explain technical indicators in accessible terms
   - Provide context on industry trends and comparisons
   - Use visualizations to support your analysis

4. EDUCATIONAL APPROACH:
   - Help users understand investment concepts
   - Explain the reasoning behind your analysis
   - Suggest areas for further research

5. PROFESSIONAL DISCLAIMERS:
   - Always remind users that you provide information for educational purposes
   - Investment decisions should consider individual circumstances
   - Recommend consulting with qualified financial advisors for personalized advice

IMPORTANT REMINDERS:
- Be explicit when recording investments so memory extraction is accurate
- Always fetch current prices before calculating performance
- Create charts to visualize trends and performance
- Remember user preferences and reference them in your advice
- Provide balanced insights considering both opportunities and risks

DISCLAIMER: I provide investment information and analysis for educational purposes only. 
This is not personalized financial advice. Investment decisions should be made in 
consultation with qualified financial advisors, considering your individual circumstances, 
risk tolerance, and financial goals. Past performance does not guarantee future results."""

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1
    )

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    # Configure AgentCore Memory with long-term strategies for investment tracking
    # Retrieves from investment and preference namespaces to recall portfolio and user preferences
    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id,
        retrieval_config={
            # Retrieve investment facts with high top_k to get all investments
            "/investments/{actorId}": RetrievalConfig(
                top_k=50,  # Retrieve up to 50 investment records
                relevance_score=0.3,  # Lower threshold to capture all investments
            ),
            # Retrieve user investment preferences
            "/preferences/{actorId}": RetrievalConfig(
                top_k=10,  # Top 10 preferences
                relevance_score=0.5,  # Medium threshold for relevant preferences
            ),
        },
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    # Initialize Code Interpreter tools with boto3 session
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    session = boto3.Session(region_name=region)
    code_tools = StrandsCodeInterpreterTools(region)

    try:
        print("[AGENT] Starting Investment Advisor agent creation...")

        # Create Alpha Vantage MCP client for financial data
        print("[AGENT] Creating Alpha Vantage MCP client...")
        alpha_vantage_client = create_alpha_vantage_mcp_client()
        print("[AGENT] Alpha Vantage MCP client created successfully")

        # Create Gateway MCP client for chart generation
        print("[AGENT] Creating Gateway MCP client...")
        gateway_client = create_gateway_mcp_client()
        print("[AGENT] Gateway MCP client created successfully")

        print("[AGENT] Creating Investment Advisor agent with Alpha Vantage, Gateway, and Code Interpreter...")
        agent = Agent(
            name="InvestmentAdvisor",
            system_prompt=system_prompt,
            tools=[
                gateway_client,  # Gateway chart generation tool
                alpha_vantage_client,  # Alpha Vantage financial tools
                code_tools.execute_python_securely,  # Code Interpreter for calculations
            ],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        print("[AGENT] Investment Advisor agent created successfully with memory, financial tools, and chart generation")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating Investment Advisor agent: {e}")
        print(f"[AGENT ERROR] Exception type: {type(e).__name__}")
        print("[AGENT ERROR] Traceback:")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload, context: RequestContext):
    """
    Main entrypoint for the Investment Advisor agent using streaming.

    This is the function that AgentCore Runtime calls when the agent receives a request.
    It extracts the user's query from the payload, securely obtains the user ID from
    the validated JWT token in the request context, creates an Investment Advisor agent
    with Alpha Vantage financial tools, Code Interpreter, and long-term memory, then
    streams the response back. This function handles the complete request lifecycle
    with token-level streaming. The user ID is extracted from the JWT token (via
    RequestContext) for secure memory namespacing.
    
    Args:
        payload: Request payload containing prompt and runtimeSessionId
        context: RequestContext with validated JWT token for user authentication
        
    Yields:
        dict: Streaming events from the agent (text chunks, tool calls, etc.)
    """
    user_query = payload.get("prompt")
    session_id = payload.get("runtimeSessionId")

    if not all([user_query, session_id]):
        yield {
            "status": "error",
            "error": "Missing required fields: prompt or runtimeSessionId",
        }
        return

    try:
        # Extract user ID securely from the validated JWT token
        # instead of trusting the payload body (which could be manipulated)
        user_id = extract_user_id_from_context(context)

        print(
            f"[STREAM] Starting Investment Advisor streaming for user: {user_id}, session: {session_id}"
        )
        print(f"[STREAM] Query: {user_query}")

        agent = create_investment_advisor_agent(user_id, session_id)

        # Use the agent's stream_async method for true token-level streaming
        async for event in agent.stream_async(user_query):
            yield json.loads(json.dumps(dict(event), default=str))

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
