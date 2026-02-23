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


def create_chartjs_mcp_client() -> MCPClient:
    """
    Create MCP client for Chart.js chart generation.
    
    The Chart.js MCP server generates beautiful, professional charts using Chart.js v4.
    It supports multiple chart types (bar, line, pie, doughnut, scatter, bubble, radar, polar)
    and can output both PNG images and interactive HTML divs.
    
    The server runs as a subprocess using stdio transport, which is the standard
    way to communicate with command-line MCP servers.
    
    Returns:
        MCPClient: Configured client for Chart.js MCP server
    """
    print("[AGENT] Creating Chart.js MCP client...")
    
    # Chart.js MCP server runs via npx with stdio transport
    chartjs_client = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["@ax-crew/chartjs-mcp-server"]
            )
        ),
        prefix="chartjs",
    )
    
    print("[AGENT] Chart.js MCP client created successfully")
    return chartjs_client


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

2. CHART.JS MCP SERVER (chartjs_generateChart tool):
   - Professional chart generation using Chart.js v4
   - Supports 8 chart types: line, bar, pie, doughnut, scatter, bubble, radar, polar
   - Outputs interactive HTML divs with hover tooltips and animations
   - Perfect for visualizing financial data and trends

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

When user asks for a chart (e.g., "Chart the 6-month price trend for AMAZON"):

1. FETCH DATA from Alpha Vantage:
   - Use TIME_SERIES_DAILY for historical price data
   - Extract dates and prices from the response
   - Process data into arrays for charting

2. PREPARE CHART CONFIGURATION:
   Create a Chart.js configuration object. This MUST be a proper JSON object, NOT a string.
   
   EXAMPLE CONFIGURATION:
   {
     "type": "line",
     "data": {
       "labels": ["Sep 29", "Oct 02", "Oct 07"],
       "datasets": [{
         "label": "AMZN Price (USD)",
         "data": [222.17, 222.41, 221.78],
         "borderColor": "#58a6ff",
         "backgroundColor": "rgba(88, 166, 255, 0.2)",
         "fill": true
       }]
     },
     "options": {
       "responsive": true,
       "plugins": {
         "title": {
           "display": true,
           "text": "Amazon (AMZN) - 6 Month Price Trend"
         }
       }
     }
   }

3. CALL chartjs_generateChart TOOL:
   CRITICAL: When calling the tool, pass the configuration object directly, NOT as a string.
   
   CORRECT WAY TO CALL THE TOOL:
   Use the chartjs_generateChart tool with these exact parameters:
   - chartConfig: <the configuration object from step 2> (as an object, not a string!)
   - outputFormat: "html"
   
   DO NOT stringify the configuration. DO NOT add quotes around it.
   The tool expects: chartConfig={...object...}, NOT chartConfig="{...string...}"
   
   The tool will return self-contained HTML that displays automatically in the chat

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
- Add gradients for visual appeal: "rgba(88, 166, 255, 0.2)"
- Enable tooltips for interactivity
- Keep labels concise and readable

IMPORTANT RULES:
1. ALWAYS use chartjs_generateChart tool for charts - don't generate HTML manually
2. Fetch real data from Alpha Vantage first
3. Process data into proper arrays (labels and data must match in length)
4. Use outputFormat="html" for interactive charts
5. Provide context and insights along with the chart
6. CRITICAL: Pass chartConfig as a JSON object, NOT as a JSON string
   - WRONG: chartConfig="{\"type\": \"line\", ...}"
   - RIGHT: chartConfig={"type": "line", ...}

CHART GENERATION RULES:
1. When user asks for a chart, use the chartjs_generateChart tool
2. Fetch data from Alpha Vantage first, then format for Chart.js
3. Always use outputFormat="html" for interactive charts
4. Provide context and insights along with the chart
5. Use appropriate chart types for different data (line for trends, bar for comparisons, etc.)
6. Apply proper styling (colors, labels, tooltips)
7. Keep charts responsive and user-friendly

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

        # Create Chart.js MCP client for visualizations
        print("[AGENT] Creating Chart.js MCP client...")
        chartjs_client = create_chartjs_mcp_client()
        print("[AGENT] Chart.js MCP client created successfully")

        print("[AGENT] Creating Investment Advisor agent with Alpha Vantage, Chart.js, and Code Interpreter...")
        agent = Agent(
            name="InvestmentAdvisor",
            system_prompt=system_prompt,
            tools=[
                alpha_vantage_client,  # Alpha Vantage financial tools
                chartjs_client,  # Chart.js visualization tools
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
